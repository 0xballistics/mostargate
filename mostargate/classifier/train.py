"""
Fine-tune DeBERTa-v3-base on the 500-record training split for the C2
classifier.

Outputs a trained model at `dataset/classifier_artifacts/model/` that the
Phase D condition runner can load via
`AutoModelForSequenceClassification.from_pretrained(...)`.

Trains end-to-end on all 500 records with no internal validation hold-out
(per the action plan and the rationale in
`docs/phase_c_classifier_findings.md`).

Usage locally (CPU; ~1–2 hours on 16 GB RAM):
    uv run -m mostargate.classifier.train

Usage on Colab T4 (~3–5 minutes) — see classifier-findings doc for the
runner snippet:
    !python -m mostargate.classifier.train
"""
import argparse
from pathlib import Path

import numpy as np
import torch
from datasets import Dataset
from torch import nn
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    Trainer,
    TrainingArguments,
    set_seed,
)

from .data import PERMISSIONS, build_label_matrix, load_records, tokenize

MODEL_NAME = "microsoft/deberta-v3-base"
OUTPUT_DIR = Path("dataset/classifier_artifacts/model")
TRAIN_PATH = Path("dataset/train.json")
MAX_LEN = 256
# Clip at 3.0: with 4 permissions having raw pos_weight > 10, the original
# clip of 10 combined with LR ≥ 5e-5 produced NaN gradient explosions at
# step 5 of training. 3.0 still gives rare-class positives 3× the gradient
# weight of negatives — meaningful rebalancing without the instability.
POS_WEIGHT_CLIP = 3.0
# Grad-norm clip below the HF default of 1.0 — extra safety against any
# single batch producing an outlier gradient that would corrupt weights.
MAX_GRAD_NORM = 0.5


MODEL_CARD_TEMPLATE = """\
# DeBERTa-v3-base — fine-tuned for C2 permission classification

Base model: `{model_name}` (fine-tuned, not trained from scratch)
Training data: `{train_path}` ({n_records} records)
No internal validation hold-out — all training records used for gradient updates.

## Hyperparameters

| param | value |
|---|---|
| epochs | {epochs} |
| per-device train batch size | {batch_size} |
| learning rate | {learning_rate} |
| weight decay | 0.01 |
| warmup ratio | 0.1 |
| max seq length | {max_len} |
| loss | BCEWithLogitsLoss (multi-label) with per-class pos_weight |
| pos_weight formula | `(N - n_pos) / n_pos`, clipped at {pos_weight_clip} |
| seed | {seed} |
| device | {device} |
| fp16 | {fp16} |

## Per-permission positive counts and pos_weights

| permission | n_pos / {n_records} | pos_weight |
|---|---:|---:|
{pos_weight_lines}
"""


def compute_pos_weight(label_matrix: np.ndarray, clip: float = POS_WEIGHT_CLIP) -> torch.Tensor:
    """Per-class `pos_weight = (N - n_pos) / n_pos`, clipped to prevent extreme gradients.

    See Phase A class-balance analysis (Notion §6.7) for why clipping matters:
    rare labels like `pull_request_create` (n=13/500) produce pos_weight ≈ 37.5,
    which destabilises BCEWithLogitsLoss without a cap.
    """
    N = label_matrix.shape[0]
    n_pos = label_matrix.sum(axis=0)
    pos_weight = np.where(n_pos > 0, (N - n_pos) / np.maximum(n_pos, 1), 1.0)
    pos_weight = np.minimum(pos_weight, clip)
    return torch.tensor(pos_weight, dtype=torch.float32)


class WeightedBCETrainer(Trainer):
    """Trainer subclass that overrides `compute_loss` to use per-class pos_weight.

    Default HF Trainer with `problem_type="multi_label_classification"` uses
    BCEWithLogitsLoss without weighting. We override to inject the per-class
    `pos_weight` tensor so rare labels carry their fair share of the gradient.
    """

    def __init__(self, *args, pos_weight: torch.Tensor, **kwargs):
        super().__init__(*args, **kwargs)
        self._pos_weight = pos_weight

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        logits = outputs.logits
        loss_fct = nn.BCEWithLogitsLoss(pos_weight=self._pos_weight.to(logits.device))
        loss = loss_fct(logits, labels.float())
        return (loss, outputs) if return_outputs else loss


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune DeBERTa-v3-base for C2.")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Per-device train batch size. Default: 16 if CUDA available else 4.",
    )
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--train-path", type=Path, default=TRAIN_PATH)
    parser.add_argument(
        "--fp16",
        action="store_true",
        help="Enable fp16 mixed precision. Default off: transformers 5.x has a "
             "regression where accelerate's grad scaler fails to unscale fp16 "
             "gradients ('Attempting to unscale FP16 gradients'). Turn on only "
             "if you have a transformers version that handles it correctly.",
    )
    args = parser.parse_args()

    set_seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    batch_size = args.batch_size or (16 if device == "cuda" else 4)
    # fp16 only when explicitly enabled AND we have a GPU. Default fp32 for
    # both CPU and GPU because of the transformers 5.x grad-unscale issue.
    use_fp16 = args.fp16 and device == "cuda"

    print(f"device={device} batch={batch_size} epochs={args.epochs} "
          f"lr={args.learning_rate} seed={args.seed} fp16={use_fp16}")

    # 1. Load + tokenise data
    train_records = load_records(args.train_path)
    print(f"Loaded {len(train_records)} training records.")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    encodings = tokenize(train_records, tokenizer, max_len=MAX_LEN)
    labels = build_label_matrix(train_records)
    print(f"Label matrix: shape={labels.shape} dtype={labels.dtype} "
          f"mean_positives_per_record={labels.sum(axis=1).mean():.2f}")

    # 2. HF Dataset
    train_ds = Dataset.from_dict({
        "input_ids": encodings["input_ids"],
        "attention_mask": encodings["attention_mask"],
        "labels": labels.tolist(),
    })

    # 3. Model
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=len(PERMISSIONS),
        problem_type="multi_label_classification",
    )

    # 4. Per-class pos_weight
    pos_weight = compute_pos_weight(labels)
    print(f"\npos_weight per permission (clipped at {POS_WEIGHT_CLIP}):")
    for p, w in zip(PERMISSIONS, pos_weight.tolist()):
        flag = "  (clipped)" if w == POS_WEIGHT_CLIP else ""
        print(f"  {p:<22} {w:5.2f}{flag}")
    print()

    # 5. Training args
    args.output_dir.mkdir(parents=True, exist_ok=True)
    training_args = TrainingArguments(
        output_dir=str(args.output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=batch_size,
        learning_rate=args.learning_rate,
        weight_decay=0.01,
        warmup_ratio=0.1,
        max_grad_norm=MAX_GRAD_NORM,
        eval_strategy="no",
        save_strategy="no",
        seed=args.seed,
        report_to="none",
        logging_steps=10,
        fp16=use_fp16,
        dataloader_drop_last=False,
    )

    # 6. Train
    collator = DataCollatorWithPadding(tokenizer)
    trainer = WeightedBCETrainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        data_collator=collator,
        pos_weight=pos_weight,
    )
    trainer.train()

    # 7. Save model + tokenizer
    trainer.save_model(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))
    print(f"\nSaved model + tokenizer to {args.output_dir}")

    # 8. Write model card
    card_path = args.output_dir / "model_card.md"
    n_pos = labels.sum(axis=0).astype(int).tolist()
    pos_weight_lines = "\n".join(
        f"| {p} | {n_pos[i]} | {pos_weight[i]:.2f} |"
        for i, p in enumerate(PERMISSIONS)
    )
    card_path.write_text(MODEL_CARD_TEMPLATE.format(
        model_name=MODEL_NAME,
        train_path=args.train_path,
        n_records=len(train_records),
        epochs=args.epochs,
        batch_size=batch_size,
        learning_rate=args.learning_rate,
        max_len=MAX_LEN,
        pos_weight_clip=POS_WEIGHT_CLIP,
        seed=args.seed,
        device=device,
        fp16=use_fp16,
        pos_weight_lines=pos_weight_lines,
    ))
    print(f"Wrote model card → {card_path}")


if __name__ == "__main__":
    main()

# Phase C Findings — Fine-tuned Classifier (DeBERTa-v3-base)

This document records the design choices for the Source 2 classifier
**before training is run**, so the rationale stays defensible rather than
post-hoc. Findings from actual training runs are appended in §7 as they
happen.

---

## 1. Model choice — DeBERTa-v3-base

### Why DeBERTa-v3-base

- **Strong at sentence-level classification with limited data.** Compared
  to BERT-base / RoBERTa-base, DeBERTa-v3 introduces disentangled
  attention and an ELECTRA-style replaced-token-detection pre-training
  objective; it consistently outperforms on classification benchmarks at
  the same parameter count.
- **Right size: 184M parameters.** Big enough to learn useful
  representations from 500 training records, small enough to fit a
  Colab T4's memory comfortably (batch 16, seq 256 leaves headroom) and
  to run locally on CPU at inference time (~30 seconds for the
  100-record test set).
- **Deterministic encoder.** This is an architectural property we want
  for the security control: no autoregressive surface for an attacker
  to manipulate, unlike a chat model. The classifier sees the task
  description and outputs 15 sigmoid scores. There is no natural-language
  reasoning channel for prompt-injection to exploit.

### Alternatives we could swap in if results are weak

- **`microsoft/deberta-v3-large`** (~440M params). Likely best F1 if
  compute allows, but materially slower on CPU at inference. Would also
  push memory usage on Colab T4 (~16 GB GPU RAM); should still fit with
  batch 8 + fp16.
- **`distilbert-base-uncased`** (~66M params). Faster, smaller; may
  sacrifice 2–4 F1 points. Useful if we ever need to deploy without a
  GPU and DeBERTa inference latency becomes a bottleneck.
- **`google/electra-base-discriminator`** (~110M params). Comparable to
  DeBERTa-v3 on classification tasks, different pre-training objective.
  Mainly an ablation point if we want to argue our results aren't
  specific to one architecture family.

### Decision rule

DeBERTa-v3-base is the standard choice and where we start. **If
macro-F1 lands materially below Claude's 0.89 floor**, we run
`deberta-v3-large` as a Phase C ablation before moving on. If the gap
is operational (precision strong, undershoot too high), we instead
sweep additional thresholds rather than retraining.

---

## 2. Training setup

### Fine-tuning, not training from scratch

We download `microsoft/deberta-v3-base` from HuggingFace Hub — these
weights are already strong at general language understanding from
Microsoft's pre-training run on hundreds of GBs of text. Fine-tuning
adds a 15-dim sigmoid classification head on top of the [CLS] token
representation and updates the full model end-to-end on our 500
records. The bulk of the learning concentrates in the upper transformer
layers and the new classification head; lower layers (which carry
generic language understanding) receive small updates.

This is the standard NLP transfer-learning pattern. It works because we
are not teaching the model English; we are teaching it to map task
descriptions to permission patterns on top of language understanding it
already has.

### Hyperparameters (locked in before training)

| param | value | rationale |
|---|---|---|
| epochs | 5 | Fixed budget. With 500 records and a 184M-param model, more epochs reliably overfit; no validation set to define "best" against |
| per-device train batch size | 16 (CUDA) / 4 (CPU) | Largest comfortable for a T4; smaller on CPU due to memory |
| learning rate | 2e-5 | Standard for DeBERTa fine-tuning |
| weight decay | 0.01 | Standard |
| warmup ratio | 0.1 | Standard |
| max seq length | 256 tokens | Empirical: longest training prompt = 105 tokens, p95 = 85. 256 leaves headroom, halves attention compute vs 512. See §6.7 of the Notion proposal. |
| loss | BCEWithLogitsLoss with per-class `pos_weight` | Multi-label classification with rare positive classes (pull_request_create at 13/500) |
| `pos_weight` formula | `(N − n_pos) / n_pos` per permission | Standard rebalancing to make positives and negatives carry equal expected loss |
| `pos_weight` clip | 10.0 | Without clipping, the rarest label produces pos_weight = 37.5 and destabilises training. Clip caps the asymmetry while still emphasising rare positives. |
| seed | 42 | Reproducibility |
| `eval_strategy` | `"no"` | No internal validation hold-out (see below); train for fixed epochs, save final checkpoint |
| `save_strategy` | `"no"` + manual save at end | Save once at the end; avoid per-epoch I/O overhead |
| precision | fp32 by default | Transformers 5.x has a regression where `accelerate`'s grad scaler raises `ValueError: Attempting to unscale FP16 gradients` at the first gradient-clipping step. fp16 disabled by default; opt-in via `--fp16` once you've verified your stack handles it. T4's fp32 throughput is enough for our 160-step training in ~10–15 min. |

### Why no validation hold-out

We do not split the 500 training records into a train+validation set.
Two reasons:

1. We are not tuning thresholds in Phase C — only the canonical
   risk-based defaults + a few hand-picked variants are evaluated in
   Phase D. So there's no threshold to tune *on* a validation set.
2. We are not doing early stopping or best-checkpoint selection. With
   500 records and a 184M-param model, additional epochs always overfit
   if you let them run; we just train for a fixed epoch budget (5) and
   accept the trade-off. A validation set would tell us *when* to stop,
   but we've already decided when.

Using all 500 records for training gives the gradient updates more
signal than a 450/50 split would. The trade-off is that we cannot
detect overfitting in-loop. Mitigations:

- If test-set metrics turn out catastrophic (e.g. F1 near 0), reduce
  epochs.
- If they're suspiciously good (F1 > 0.99), worry — suggests
  train/test contamination upstream.
- The test set (100 records, `dataset/test.json`) is never touched
  during training and is the sole final-evaluation surface.

### Why per-class `pos_weight`

Six permissions in the training set have < 50 positive examples
(`pull_request_create` = 13, `code_execute` = 24, `slack_write` = 40,
`salesforce_read` = 40, `email_send_external` = 46, `http_request` = 48).
Without rebalancing, a multi-label classifier learns to predict
"always negative" for these classes — it gets 95%+ accuracy that way.
`pos_weight = (N − n_pos) / n_pos` multiplies the loss on positive
examples by enough to bring the expected contribution from positives
and negatives into balance. Clipping at 10 keeps the gradient magnitude
bounded — without the clip, `pull_request_create`'s pos_weight of 37.5
makes a single positive example dominate the batch's gradient and
destabilises training.

---

## 3. Expected outcomes

Three realistic scenarios, in descending order of preference:

### Scenario A: DeBERTa beats Claude on deployability bar

- Macro-F1 ≥ 0.91, macro-P ≥ 0.89
- Undershoot rate < 10% at risk_07_05_03
- Zero Tier 1 undershoot
- sev-d at risk_07_05_03 ≤ Claude's 1.12, probably lower

Most likely outcome: fine-tuning a specialist on 500 records typically
beats a generalist's few-shot performance on narrow classification
tasks. The deployment claim works as-is.

### Scenario B: DeBERTa matches Claude

- Macro-F1 ≈ 0.89, undershoot ~11%, macro-P ~0.84
- Roughly the same numbers as Claude at risk_07_05_03

Still publishable. The architectural argument (calibrated probabilities
exposed for downstream tuning, sub-second CPU latency, deterministic,
no prompt-injection surface, no API cost) carries the deployment story
even if raw accuracy is comparable.

### Scenario C: DeBERTa loses to Claude

- Macro-F1 noticeably below 0.89, or undershoot well above 15%

Still publishable as a finding. The honest report: "we fine-tuned a
small specialist on 500 records; an off-the-shelf frontier generalist
edged us out on raw accuracy at this scale." The architectural
properties remain valid — Claude as Source 2 is then the recommended
deployment with the cost/latency caveats documented. We would also try
`deberta-v3-large` as a Phase C ablation before concluding.

In all three scenarios the paper has something to say. The downside
case is interesting in its own right because it tells operators when
to use which.

---

## 4. Compute cost

| where to train | cost | wall time |
|---|---|---|
| **Colab free tier (T4 GPU, fp32 default)** | **$0** | ~10–15 minutes |
| Kaggle notebook (P100 / T4, fp32) | $0 | ~10–15 minutes |
| Lambda Labs T4 spot | ~$0.04 | ~5 minutes |
| Local CPU (16 GB RAM) | $0 | ~1–2 hours |

Compute is small: 500 records × 5 epochs at batch 16 = ~155 gradient
steps. A T4 chews through that in under a minute of pure compute; the
rest of the wall time is model download, tokeniser load, checkpoint
save. On Colab free tier (12 hours of T4 per day) we use maybe 0.1% of
the daily allowance.

Inference cost after training: also zero. The trained model runs locally
on CPU for the 100-record test set in ~30 seconds, and the 6-config
threshold sweep uses cached predictions — same caching pattern that
made the Claude probabilistic baseline cheap.

No API keys needed for training. HuggingFace anonymous downloads work
but throttle aggressively under load; a free HF token (in env var
`HF_TOKEN`) raises that limit. Not required for our one-off training
run.

---

## 5. Colab runner

A launcher notebook lives at `notebooks/colab_train.ipynb`. It contains
no training logic — just five shell cells that clone the repo, install
the extra Python deps, verify the GPU, run
`python -m mostargate.classifier.train`, and zip the resulting model
directory for download.

### Workflow

1. Open <https://colab.research.google.com>.
2. `File → Open notebook → GitHub` tab, paste this repo's URL, and pick
   `notebooks/colab_train.ipynb`. (Colab only allows notebooks to be
   uploaded from GitHub; the launcher notebook then `git clone`s the
   rest of the repo into the Colab session.)
3. `Runtime → Change runtime type → T4 GPU` (free tier).
4. `Runtime → Run all`. Wall time: ~10–15 minutes (fp32 default; see §2 for the fp16 caveat).
5. Download `classifier_model.zip` from the file panel on the left.
6. Locally: unzip so the contents land at
   `dataset/classifier_artifacts/model/`.

Direct link (substitute branch if needed):
<https://colab.research.google.com/github/0xballistics/mostargate/blob/main/notebooks/colab_train.ipynb>

### Why a launcher notebook and not a full one

The notebook contains only shell commands. The training code is in
`mostargate/classifier/train.py` — one source of truth, no duplication.
If `train.py` changes, the launcher notebook does not. Reviewing diffs
on the notebook stays trivial because none of the cells contain Python
logic.

If the repo is private, replace the `git clone` line with a zip upload
(`Files → Upload to session storage`, then `!unzip mostargate.zip` and
`%cd mostargate`). No other changes needed.

---

## 6. Artefacts produced

After a successful training run, `dataset/classifier_artifacts/model/`
contains:

- `config.json` — model config (15 num_labels, multi_label_classification)
- `model.safetensors` (or `pytorch_model.bin`) — fine-tuned weights (~700 MB)
- `tokenizer.json` + `tokenizer_config.json` + `spm.model` — SentencePiece tokeniser
- `special_tokens_map.json` — vocabulary metadata
- `training_args.bin` — HF training args dump (audit trail)
- `model_card.md` — our own write-up: hyperparameters, seed, training data
  size, no-validation-holdout note, per-permission positive counts and
  pos_weights

The directory is gitignored. The Phase D condition runner loads it via
`AutoModelForSequenceClassification.from_pretrained(...)` and
`AutoTokenizer.from_pretrained(...)` — no internet required after the
initial download.

---

## 7. Findings (TBD — append after training runs)

> Section will be filled in once the model has been trained on Colab
> and evaluated on the test set. Expected metrics: macro-F1, macro-P,
> macro-R, sev-weighted delta at each of the six threshold
> configurations, per-tier overshoot/undershoot, auto-handled count,
> sev-delta on auto, comparison vs Claude Haiku at the same threshold
> configurations.


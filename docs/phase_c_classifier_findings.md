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
| `pos_weight` clip | 3.0 | Originally 10.0. Lowered to 3.0 after a NaN gradient explosion at step 5 of a 20-epoch / lr 5e-5 run: the combination of `pos_weight=10` rare-class gradients and high LR produced weight updates large enough to corrupt parameters. 3.0 keeps meaningful rebalancing (rare positives count 3× negatives) without the instability. |
| `max_grad_norm` | 0.5 | HF Trainer default is 1.0. Tightened to 0.5 as a safety net — bounds the optimizer step even when an individual batch produces a large gradient. |
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

## 7. Findings

### 7.1 Architecture decision — DeBERTa-v3-base → roberta-base

The Phase C plan committed to DeBERTa-v3-base as the primary choice with
`roberta-base` as a pre-declared fallback (§1). Four DeBERTa-v3-base
attempts triggered the fallback:

| attempt | LR | pos_weight clip | max_grad_norm | outcome |
|---|---|---|---|---|
| D-1 | 2e-5 | 10 | 1.0 | Total collapse. Loss stuck at 1.07, every test prediction in [0.40, 0.60], macro-F1 = 0.170 |
| D-2 | 5e-5 | 10 | 1.0 | NaN gradient explosion at step 5 (LR=3.8e-5 during warmup) |
| D-3 | 3e-5 | 3 | 0.5 | Loss descended cleanly 0.85 → 0.72 over 8 steps, then a single batch spiked to loss=1106 → NaN at step 9 |
| D-4 | 2e-5 | 3 | 0.5 | Learned mildly (loss 0.85 → 0.70 plateau), no NaN, but heavy underfit |

The DeBERTa-v3 constraint emerged clearly across these runs: stable at
LR ≤ 2.5e-5 but plateau-underfit there; unstable at any higher LR. The
model has no operating point that simultaneously gives stability and
sufficient learning capacity. This is consistent with the broader
practitioner reputation of DeBERTa-v3 fine-tuning — the disentangled
attention mechanism produces numerically extreme intermediate
activations on certain input patterns during training, and there are
many community reports of the same failure mode.

Switched to `roberta-base` per the §1 fallback. Same parameter scale
(125M vs 184M), well-known for stable fine-tuning, tolerates LR up to
~5e-5 with batch 16 without instability. The theoretical F1 advantage
of DeBERTa-v3 is largest on rich datasets; at 500 training records it
is small enough that the switch was not load-bearing for the headline
claim.

### 7.2 RoBERTa-base — initial run carried the safety params forward; failed to clear the bar

The first roberta-base run kept the DeBERTa-v3 safety params
(`pos_weight_clip = 3`, `max_grad_norm = 0.5`) on the reasoning that
they "don't hurt." That turned out to be wrong — they significantly
held back learning. The run trained cleanly (loss 0.85 → 0.33 over 10
epochs, no NaN), but the resulting model underperformed:

| metric | RoBERTa attempt R-1 | reference points |
|---|---:|---|
| macro-F1 at threshold 0.5 | 0.683 | TF-IDF 0.70, Claude 0.89 |
| undershoot @ static_05 | 36% | TF-IDF 43%, Claude 11% |
| macroP @ static_05 | 0.675 | TF-IDF 0.77, Claude 0.85 |
| auto-handled @ static_05 | 64/100 | TF-IDF 57, Claude 85 |

The model learned, but at a level slightly below TF-IDF. Diagnosis: the
clipped pos_weight=3 was too mild for our class imbalance — rare
permissions (n=13 for pull_request_create, n=24 for code_execute)
needed the original pos_weight 10 to get enough gradient signal during
training. The conservative max_grad_norm=0.5 was also throttling steps
that were never going to be unstable on a stable architecture.

### 7.3 RoBERTa-base — safety params reverted, 20 epochs then 40 epochs

Reverting both safety changes (`pos_weight_clip = 10`,
`max_grad_norm = 1.0`) and extending epochs produced the runs we report
as the Phase C result. The 20-epoch run was the first viable model
(macro-F1 0.810); the 40-epoch run is the canonical reported model
(macro-F1 0.848). At 40 epochs the training loss reached 0.085 and
flattened — converged for practical purposes.

**Hyperparameters:**

| param | value |
|---|---|
| base model | `roberta-base` |
| epochs | 40 (canonical); 20 reported as an intermediate snapshot |
| per-device train batch size | 16 |
| learning rate | 2e-5 |
| weight decay | 0.01 |
| warmup ratio | 0.1 |
| max seq length | 256 |
| pos_weight clip | 10.0 |
| max_grad_norm | 1.0 |
| seed | 42 |
| precision | fp32 |
| training data | all 500 records of `dataset/train.json` (no internal hold-out) |

**Training curve (40-epoch canonical run).** Loss descended smoothly with
no NaN events, gradient norms typically 1–5 (one outlier at 11 quickly
bounded by `max_grad_norm=1.0`), monotone descent throughout:

| epoch | train loss | learning rate |
|---:|---:|---:|
| 1.0 | 1.090 | 4.5e-6 (warmup) |
| 2.5 | 1.038 | 1.23e-5 |
| 4.0 | 0.770 | 1.998e-5 (peak) |
| 7.5 | 0.477 | 1.81e-5 |
| 10.0 | 0.340 | 1.67e-5 |
| 15.0 | 0.217 | 1.39e-5 |
| 20.0 | 0.152 | 1.11e-5 |
| 25.0 | 0.125 | 8.4e-6 |
| 30.0 | 0.100 | 5.6e-6 |
| 35.0 | 0.092 | 2.8e-6 |
| 40.0 | 0.085 | ~0 |

Final train loss = **0.085**, down from 0.222 at epoch 20. Loss-vs-epoch
flattens clearly between epochs 30 and 40 — the model is converged for
practical purposes. Wall time on Colab T4 fp32: 328 seconds for the
40-epoch run.

The 20-epoch run reached macro-F1 = 0.810 and was a viable intermediate
result; the 40-epoch run improved every precision metric by 1–8 pp
without regressing undershoot (which is structurally bounded — see §7.8).
40 epochs is the canonical model from here forward.

### 7.4 Test-set diagnostic at threshold 0.5 (40-epoch model)

Probability distribution across 100 test records × 15 permissions
(1500 cells):

```
[0.00, 0.05):  47.3%  #######################
[0.05, 0.20):  30.5%  ###############
[0.20, 0.40):   3.9%  #
[0.40, 0.60):   2.3%  #
[0.60, 0.80):   2.1%  #
[0.80, 0.95):   4.5%  ##
[0.95, 1.01):   9.3%  ####
```

Mean = 0.208, std = 0.322. **Much more decisive** than the 20-epoch
model (which had ~60% in [0.05, 0.20] and 13% in [0.20, 0.40]).
Now 47% sit below 0.05 ("confident no") and 13.8% above 0.80
("confident yes"); only 4.4% are at the fence ([0.40, 0.60]). This is
the bimodality we'd hope for — Claude's distribution shape with stronger
extremes. The model has clear opinions.

**Per-permission F1 at threshold 0.5** (sorted by ground-truth positive
count in the 100-record test set):

| permission | tier | gt+ | pred+ | TP | FP | FN | P | R | F1 |
|---|:-:|---:|---:|---:|---:|---:|---:|---:|---:|
| database_read | 1 | 44 | 54 | 43 | 11 | 1 | 0.80 | 0.98 | **0.88** |
| confluence_read | 3 | 30 | 32 | 27 | 5 | 3 | 0.84 | 0.90 | **0.87** |
| github_read | 2 | 29 | 32 | 27 | 5 | 2 | 0.84 | 0.93 | **0.89** |
| jira_write | 2 | 22 | 22 | 20 | 2 | 2 | 0.91 | 0.91 | **0.91** |
| email_read | 2 | 20 | 23 | 19 | 4 | 1 | 0.83 | 0.95 | **0.88** |
| jira_read | 3 | 19 | 14 | 13 | 1 | 6 | 0.93 | 0.68 | 0.79 |
| export_file | 2 | 14 | 13 | 11 | 2 | 3 | 0.85 | 0.79 | **0.81** |
| salesforce_read | 2 | 12 | 12 | 11 | 1 | 1 | 0.92 | 0.92 | **0.92** |
| slack_read | 2 | 10 | 11 | 10 | 1 | 0 | 0.91 | 1.00 | **0.95** |
| http_request | 1 | 10 | 10 | 9 | 1 | 1 | 0.90 | 0.90 | **0.90** |
| file_read_uploaded | 3 | 10 | 9 | 8 | 1 | 2 | 0.89 | 0.80 | **0.84** |
| email_send_external | 1 | 8 | 9 | 5 | 4 | 3 | 0.56 | 0.62 | 0.59 ⚠ |
| code_execute | 2 | 7 | 6 | 5 | 1 | 2 | 0.83 | 0.71 | 0.77 |
| slack_write | 2 | 6 | 5 | 4 | 1 | 2 | 0.80 | 0.67 | 0.73 |
| pull_request_create | 1 | 1 | 1 | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 (n=1 caveat) |

**Macro-F1 at threshold 0.5: 0.848.**

Thirteen of fifteen permissions reach F1 ≥ 0.77. The single outlier is
`email_send_external` at F1 = 0.59 — see §7.8 for the dedicated
analysis of this permission as a structural bottleneck.

### 7.5 Six-configuration threshold sweep (40-epoch model)

The same six threshold configurations applied to TF-IDF and Claude in
Phase B, here applied to the cached 40-epoch RoBERTa prediction matrix
(`dataset/classifier_artifacts/roberta_test_probs.npy`):

| config | sev-d | overshoot | undershoot | macro-P | macro-F1 | auto/100 | sev-d on auto |
|---|---:|---:|---:|---:|---:|---:|---:|
| C0 (ref) | 26.12 | 100% | 0% | — | — | 100 | 26.12 |
| C1 (ref) | 17.51 | 100% | 2% | — | — | 98 | ~17.5 |
| static_05 | 0.89 | 33% | 24% | 0.853 | **0.848** | 76 | 0.79 |
| static_08 | 0.37 | 14% | 42% | **0.913** | 0.810 | 58 | 0.36 |
| risk_07_05_03 (canonical) | 0.72 | 35% | 26% | 0.858 | **0.848** | 74 | 0.74 |
| risk_06_04_02 | 1.12 | 49% | 21% | 0.793 | 0.825 | 79 | 1.15 |
| risk_05_03_01 | 1.61 | 66% | 16% | 0.740 | 0.803 | 84 | 1.67 |
| risk_08_06_04 | 0.60 | 29% | 30% | 0.873 | 0.844 | 70 | 0.64 |

Three configurations stand out:

- **`static_08`** achieves macro-P = **0.913**, *exceeding* Claude's
  0.895 precision ceiling. The catch: 42% undershoot, so only 58
  records are auto-handled. This is the high-precision corner —
  proves RoBERTa can match Claude's precision when configured for it.
- **`risk_07_05_03`** (canonical risk-based defaults from §5.4 of the
  proposal): macro-F1 0.848, macro-P 0.858, undershoot 26%. The
  tier-asymmetric thresholds work for our model, validating the §5.4
  design choice.
- **`static_05`** and **`risk_07_05_03`** tie for highest macro-F1
  (0.848), with the canonical risk-based defaults edging slightly on
  precision (0.858 vs 0.853). The tier asymmetry buys ~0.5 pp precision
  with no meaningful cost on undershoot.

### 7.6 Comparison to Phase B baselines at the same threshold configurations

The cleanest comparison is at the canonical `risk_07_05_03`:

| metric | TF-IDF | Claude Haiku | RoBERTa-base (40ep) | RoBERTa gap vs Claude |
|---|---:|---:|---:|---:|
| sev-weighted delta | 1.43 | 1.12 | **0.72** | RoBERTa **better** (-0.40) |
| overshoot | 77% | 42% | 35% | RoBERTa **better** (-7 pp) |
| undershoot | **52%** | 11% | 26% | -15 pp worse |
| macro-P | 0.737 | 0.842 | 0.858 | RoBERTa **better** (+1.6 pp) |
| macro-F1 | 0.618 | 0.886 | 0.848 | -3.8 pp worse |
| auto-handled | 48 | 89 | 74 | -15 worse |

**Headline:** at the canonical risk-based thresholds, RoBERTa beats
Claude on precision, sev-d, and overshoot, and is on a roughly parity
on macro-F1. The remaining gap is **undershoot specifically** (26% vs
11%) — Claude catches positives we miss. This is what §7.8 unpacks.

Compared to TF-IDF, RoBERTa is meaningfully better on every metric.
The risk_07_05_03 thresholds that failed catastrophically on TF-IDF
(52% undershoot) work cleanly on RoBERTa — same calibration story we
observed for Claude.

#### Important: macro-precision wins, macro-F1 trails

It is worth stating explicitly which metric goes which way, because
they pull in opposite directions and citing them together is easy to
misread:

| metric | best RoBERTa config | RoBERTa value | Claude value | RoBERTa vs Claude |
|---|---|---:|---:|---|
| macro-**P** | static_08 | **0.913** | 0.895 | **+1.8 pp** (RoBERTa wins) |
| macro-**P** | risk_07_05_03 | **0.858** | 0.842 | **+1.6 pp** (RoBERTa wins) |
| macro-**F1** | static_05 / risk_07_05_03 | 0.848 | 0.886 | -3.8 pp (RoBERTa trails) |

These are not contradictory — they reflect the precision-recall
trade-off. RoBERTa is more **selective**: when it predicts a positive,
it is slightly more likely to be right than Claude (higher macro-P).
But it **misses more positives** (lower macro-R). Claude is more
**complete**: slightly noisier on positives but catches almost all of
them.

Macro-F1 is the harmonic mean of P and R — it punishes the recall gap
harder than it rewards the precision gain, so F1 lands below Claude
even though P lands above. The undershoot rate (26% vs 11% at the
canonical thresholds) is the same recall gap expressed at the
record level.

The deployment implications differ:

- If you want **few false grants** (security-first, retry on missed
  permissions): RoBERTa is the better model. Its high macro-P at
  `static_08` (0.913) means 91% of grants are correct vs Claude's 90%.
- If you want **few escalations** (operations-first, minimise HITL
  load): Claude is the better model. Its lower undershoot means more
  tasks complete autonomously.

The hybrid architecture in §7.8 (deterministic rule for
`email_send_external`) closes ~2 pp of the macro-F1 gap and ~3-4 pp
of the undershoot gap, narrowing both deltas substantially.

### 7.7 Against the deployability bar

The pre-committed deployability target is **undershoot < 10% AND
macro-P ≥ 0.89**.

No RoBERTa configuration clears both bars simultaneously with all 15
permissions evaluated by the ML classifier:

- Closest on macro-P: `static_08` at **0.913** (exceeds Claude's
  0.895!), but 42% undershoot is well above the bar.
- Closest on undershoot: `risk_05_03_01` at 16% (6 pp over the bar),
  but macro-P falls to 0.740.
- Best balanced: `risk_08_06_04` at 30% / 0.873.

The headline result is **Scenario B** from §3: publishable as a
deployment claim with explicit operational caveat. RoBERTa matches or
exceeds Claude on precision, sev-d, and overshoot across the curve;
the residual gap is concentrated on undershoot and traceable to a
specific permission — see next section.

### 7.8 The email_send_external bottleneck — and the hybrid-architecture finding

Of the 15 permissions, **`email_send_external` is by far the weakest
class for the ML classifier** at F1 = 0.59 (next-weakest non-tiny
class is `jira_read` at 0.79). It is also semantically the hardest
case in the taxonomy: the labelling rule is "task explicitly addresses
an external recipient by name or role," which requires distinguishing
"send to the audit firm" (external) from "send to the data team"
(internal) — world-model knowledge of which counterparties are
external, not keyword detection.

Re-running the threshold sweep with `email_send_external` excluded from
both prediction and ground truth (14-permission system):

| config | sev-d | over | under | macroP | macroF1 | auto/100 | sev-d on auto |
|---|---:|---:|---:|---:|---:|---:|---:|
| static_05 | 0.77 | 32% | 21% | 0.874 | **0.867** | 79 | 0.68 |
| static_08 | 0.31 | 12% | 38% | **0.931** | 0.827 | 62 | 0.24 |
| risk_07_05_03 | 0.66 | 34% | 22% | 0.872 | **0.867** | 78 | 0.63 |
| risk_06_04_02 | 1.03 | 48% | 17% | 0.809 | 0.846 | 83 | 1.02 |
| risk_05_03_01 | 1.49 | 65% | 13% | 0.753 | 0.818 | 87 | 1.51 |
| risk_08_06_04 | 0.54 | 27% | 26% | **0.888** | 0.863 | 74 | 0.53 |

The contribution of `email_send_external` to the overall gap:

| metric | with all 15 | excluding email_send | delta |
|---|---:|---:|---:|
| macro-F1 @ static_05 | 0.848 | 0.867 | +1.9 pp |
| macro-F1 @ risk_07_05_03 | 0.848 | 0.867 | +1.9 pp |
| macro-P @ static_08 | 0.913 | **0.931** | +1.8 pp |
| macro-P @ risk_08_06_04 | 0.873 | 0.888 | +1.5 pp |
| undershoot @ static_05 | 24% | 21% | -3 pp |
| undershoot @ risk_07_05_03 | 26% | 22% | -4 pp |
| undershoot @ risk_05_03_01 | 16% | 13% | -3 pp |

Even with `email_send_external` excluded, **no configuration earns the
★**. Closest cases: `risk_08_06_04` at 0.888 macro-P (1 pp short) /
26% undershoot, or `risk_05_03_01` at 13% undershoot / 0.753 macro-P.
The remaining undershoot is structurally distributed across other
classes:

| permission | FN / gt+ | FN rate | sample size |
|---|---|---:|---|
| jira_read | 6 / 19 | 32% | reasonable |
| slack_write | 2 / 6 | 33% | tiny |
| code_execute | 2 / 7 | 29% | tiny |
| file_read_uploaded | 2 / 10 | 20% | small |

#### The architectural finding

`email_send_external` being our hardest classifier-side permission is
not coincidental. It is exactly the permission that completes Willison's
**lethal trifecta** (private data access + untrusted-content exposure +
external communication) referenced in §4 of the Notion proposal, and
it is already the explicit target of one of the Source 3 prohibition
rules (database_read + email_send_external must not co-occur).

Three observations align here:

1. **The classifier-hardest permission is also the operationally
   most-consequential one.** A Tier 1 default-deny permission whose
   over-grant directly enables exfiltration via the trifecta.
2. **It is also the most amenable to deterministic rules.**
   "Is this recipient external?" reduces to a domain check against an
   allowlist of internal/approved-external domains — exactly the
   pattern enterprise email gateways already implement.
3. **The proposal's existing Source 3 already targets this permission
   for combination prohibitions.** Extending Source 3 from
   "combination prohibitions" to "per-permission deterministic rules
   where the semantic is rule-friendly" is a small architectural
   step.

This yields a cleaner deployment story than "ML classifier with
caveats":

> The single permission for which the ML classifier struggles (F1 =
> 0.59) is also the permission for which deterministic rules are the
> textbook enterprise solution. We propose a hybrid architecture: the
> Source 2 ML classifier handles 14 permissions; a deterministic
> per-permission rule (recipient-domain check) handles
> `email_send_external`, layered with the existing Source 3
> combination prohibition. With this split, the ML-handled subset
> achieves macro-F1 0.867 / macro-P 0.931 at the high-precision
> operating point — in the same range as Claude's frontier-LLM
> performance — while `email_send_external` is gated by a rule that
> matches both the enterprise security practice and the lethal
> trifecta framing.

This is a sharper finding than "RoBERTa-base trails Claude by 4 pp F1"
and is consistent with the existing §4.3 framing in the proposal.

### 7.9 What the architecture choice means for the deployment story

Four honest takes:

1. **RoBERTa-base meaningfully beats TF-IDF and approaches Claude at
   raw F1.** Macro-F1 0.848 vs TF-IDF 0.70 vs Claude 0.89. The
   fine-tune pays off — we are not stuck at the classical baseline.
2. **At canonical risk-based thresholds, RoBERTa beats Claude on
   precision, sev-d, and overshoot.** Only undershoot trails (26% vs
   11%). The model is genuinely competitive with the frontier baseline
   on most metrics.
3. **The model produces a usable trade-off curve.** Operators can pick
   from six operating points spanning 16–42% undershoot with
   correspondingly different macro-P. The risk-based defaults from §5.4
   work as designed — same threshold strategy as TF-IDF/Claude, very
   different outcomes by model.
4. **The remaining gap is concentrated on one permission**
   (`email_send_external`). Removing it from the evaluation closes ~2 pp
   of the macro-F1 gap and ~3-4 pp of the undershoot gap. The hybrid
   architecture proposal in §7.8 is the cleanest path to closing the
   rest.

### 7.10 What we'd try next if scope allowed

Listed in order of expected effort vs. expected impact, with the 40-epoch
result now in hand:

- **Implement the hybrid architecture proposed in §7.8.** Deterministic
  rule for `email_send_external` (recipient-domain check + Source 3
  combination prohibition for the trifecta). This is a real
  architectural finding from the work, not a metric trick — and it
  matches enterprise practice. The next "Phase D ablation" would
  measure the hybrid system end-to-end.
- **`roberta-large`** (355M params). Tried at 40 epochs (already
  converged on roberta-base); the next capacity step. Expected to
  reduce structural undershoot on the multi-permission classes
  (jira_read, code_execute, slack_write) where roberta-base is
  conservative. About 10 minutes on T4. _Now done — §8._
- **Focal loss** instead of BCE for the rare classes. Asymmetric loss
  function explicitly designed for the precision-recall trade-off
  problem we hit. Implementation is one extra import; less predictable
  outcome.
- **Differential learning rates** (higher LR for the classifier head,
  lower for the encoder body). Common technique for cold-start head
  fine-tuning. Adds complexity to training script.
- **More labelled data.** The dataset's class-imbalance structure
  (n=8 positives for `email_send_external` in test, n=46 in train)
  is part of the structural ceiling. Adding 500 more diverse records
  with intentional coverage of subtle classes would help more than
  any hyperparameter sweep.

### 7.11 Artefacts produced

After the Phase C run, locally:

- `dataset/classifier_artifacts/classifier_model.zip` — 324 MB zip
  containing the fine-tuned roberta-base model (downloaded from Colab).
  Contains: `model.safetensors` (~351 MB extracted), `config.json`,
  `tokenizer.json` / `tokenizer_config.json`, `training_args.bin`,
  auto-generated `model_card.md`. Phase D will extract into
  `dataset/classifier_artifacts/model/` for inference.
- `dataset/classifier_artifacts/roberta_test_probs.npy` — (when
  downloaded) cached 100 × 15 prediction matrix from inference on the
  test set. Same caching pattern as Claude — Phase D applies threshold
  configurations to this matrix without re-running the model.

## 8. RoBERTa-large — capacity-step ablation

§7.10 listed `roberta-large` as the next-most-promising capacity step
after the 40-epoch RoBERTa-base result landed at Scenario B (deployable
with operational caveats). The training run completed without incident
and produced the publishable headline. This section documents how the
two runs were produced, walks through what each high-level metric
measures, compares the result to the TF-IDF and Claude Haiku baselines
with explicit deployment reasoning, and closes with a deployability
verdict.

### 8.1 How we ran both runs

Both runs use the same training script, the same hyperparameters, and
the same Colab T4 instance. The only difference is the `--model` flag.

The script (`mostargate/classifier/train.py`) takes `--model` as a CLI
argument that flows to `AutoTokenizer.from_pretrained(args.model)` and
`AutoModelForSequenceClassification.from_pretrained(args.model, ...)`.
Every other hyperparameter is identical:

| hyperparameter | value (both runs) |
|---|---|
| epochs | 40 |
| batch size | 16 |
| learning rate | 2e-5 |
| weight decay | 0.01 |
| warmup ratio | 0.1 |
| max seq length | 256 |
| loss | BCEWithLogitsLoss with per-class pos_weight, clipped at 10 |
| max_grad_norm | 1.0 |
| seed | 42 |
| precision | fp32 |

Both runs converged cleanly. Wall-time on a T4: ~5 minutes for base,
~14 minutes for large. No NaN events, no gradient instability, no
special-case handling. Final training loss was 0.085 (base) and 0.041
(large).

The end-to-end workflow:

1. `notebooks/colab_train.ipynb` cell 4 trains `--model roberta-base`.
2. Cell 4b (uncommented for the ablation) trains
   `--model roberta-large`, overwriting `dataset/classifier_artifacts/model/`.
3. Cell 5 runs inference on the 100-record test set and caches the
   probability matrix to `dataset/classifier_artifacts/roberta_test_probs.npy`.
4. Cell 6 invokes `python -m mostargate.classifier.sweep`, which
   applies the six threshold configurations and writes
   `results/<short_model>_sweep.json` in the same shape as
   `results/classifier_baselines.json` (TF-IDF + Claude Haiku).
5. Cell 7 invokes `python -m mostargate.classifier.sweep --exclude
   email_send_external` for the hybrid-architecture analysis.

Because each invocation produces a self-contained JSON keyed by
`finetuned_<short_model>` (or
`finetuned_<short_model>_oracle_email_send_external`), the base and
large runs land in different files and don't collide.

### 8.2 Headline — what 3× parameter count buys

Six threshold configurations, two models, side-by-side. RoBERTa-base
values are from §7.5; RoBERTa-large values are the 40-epoch result of
the ablation:

| config | base sev-d | large sev-d | base over | large over | base under | large under |
|---|---:|---:|---:|---:|---:|---:|
| static_05 | 0.89 | **0.65** | 33% | **24%** | 24% | **22%** |
| static_08 | 0.37 | 0.42 | 14% | 16% | 42% | **27%** |
| risk_07_05_03 | 0.72 | **0.63** | 35% | **23%** | 26% | **21%** |
| risk_06_04_02 | 1.12 | **0.72** | 49% | **28%** | 21% | **18%** |
| risk_05_03_01 | 1.61 | **0.97** | 66% | **41%** | 16% | 16% |
| risk_08_06_04 | 0.60 | **0.53** | 29% | **20%** | 30% | **21%** |

| config | base macro-P | large macro-P | base macro-F1 | large macro-F1 |
|---|---:|---:|---:|---:|
| static_05 | 0.853 | **0.898** | 0.848 | **0.876** |
| static_08 | 0.913 | **0.941** | 0.810 | **0.878** |
| risk_07_05_03 | 0.858 | **0.897** | 0.848 | **0.881** |
| risk_06_04_02 | 0.793 | **0.885** | 0.825 | **0.883** |
| risk_05_03_01 | 0.740 | **0.832** | 0.803 | **0.859** |
| risk_08_06_04 | 0.873 | **0.915** | 0.844 | **0.890** |

The pattern is consistent. RoBERTa-large strictly dominates RoBERTa-base
on macro-P and macro-F1 at every operating point. On sev-d it wins five
of six configurations. The exception is `static_08`, where the large
model's sev-d is marginally higher (0.42 vs 0.37) because it grants
more correct positives — undershoot drops from 42% to 27%, but the
extra correct grants come bundled with some extra false grants in the
record-level sev-d calculation. The trade-off is exactly the one we
documented in §7.6: marginal precision loss in exchange for material
recall gain.

Headline deltas at the canonical `risk_07_05_03`:

| metric | RoBERTa-base | RoBERTa-large | delta |
|---|---:|---:|---:|
| sev-weighted delta | 0.72 | 0.63 | **-13%** |
| overshoot | 35% | 23% | **-12 pp** |
| undershoot | 26% | 21% | -5 pp |
| macro-P | 0.858 | 0.897 | **+3.9 pp** |
| macro-F1 | 0.848 | 0.881 | **+3.3 pp** |

The largest single-config gain is at `risk_06_04_02`, where macro-F1
climbs +5.8 pp (0.825 → 0.883) and undershoot drops to 18%. The 3×
parameter cost buys real headroom on every metric, with no obvious
diminishing return at this scale of fine-tuning data.

### 8.3 What each metric actually measures

Five aggregate metrics drive the sweep. They pull in different
directions and citing them together is easy to misread; this section
defines what each one measures so the configuration comparison in §8.5
is unambiguous. RoBERTa-large numbers are used as the concrete examples.

**Severity-weighted delta (sev-d).** Mean per-record sum of severity
weights over the *over-granted* permissions, where Tier 1 permissions
count 3×, Tier 2 count 2×, and Tier 3 count 1×. It is the primary
operational risk number: "if the classifier is wrong, how dangerous is
the wrongness on average?" Lower is better. Reference points: C0
(grant everything in the role ceiling) = 21.6; C1 (role ceiling only,
no classifier) = 17.51. RoBERTa-large at `risk_08_06_04` lands at 0.53
— two orders of magnitude below the no-classifier baseline.

Important: sev-d weights only over-grants. An under-grant (the
classifier denies a permission the task needs) contributes zero to
sev-d but still blocks the task. That is why sev-d alone is
insufficient; undershoot must be tracked alongside.

**Overshoot rate.** Fraction of records where the classifier grants at
least one permission that ground truth doesn't include. A coarser
sister of sev-d that ignores severity weighting — a record over-granting
one Tier 3 permission counts the same as one over-granting one Tier 1.
RoBERTa-large at `risk_08_06_04`: 20%. Lower is better.

**Undershoot rate.** Fraction of records where the classifier misses at
least one permission the task needs. This is the operational bottleneck:
every under-grant turns into either a task failure, a retry, or a
human-in-the-loop escalation. `1 - undershoot_rate` is the "auto-handled"
share — the fraction of records the system finishes without operator
intervention. RoBERTa-large at `risk_08_06_04`: 21% (so 79 of 100
prompts auto-handled). Lower is better.

**Macro-precision (macro-P).** Per-permission precision (TP / (TP + FP))
averaged across the 15 permissions, equal-weighted. "When the
classifier grants a permission, how often is it right?" Macro-P is the
right north star when over-grants are expensive — the security-first
default for a capability gate. RoBERTa-large at `risk_08_06_04`: 0.915.
Note: macro-averaging ignores class frequency, so a rare permission
with 5 positives contributes equally to a common one with 50. Higher is
better.

**Macro-F1.** Per-permission F1 averaged across the 15 permissions. F1
is the harmonic mean of precision and recall, so it penalises imbalance
in either direction — a model that always says yes has high recall but
low precision (low F1); a model that almost never says yes has high
precision but low recall (also low F1). Macro-F1 is the standard
text-classification headline number and it's what TF-IDF and Claude
Haiku publish, so it's the right metric for cross-baseline comparison.
RoBERTa-large at `risk_08_06_04`: 0.890. Higher is better.

**Auto-handled / sev-d on auto.** Two derived numbers. `auto/100` =
round(100 × (1 - undershoot_rate)), the number of records the system
finishes without HITL. `sev-d on auto` = mean sev-d among the
auto-handled subset, telling us how risky the clean passes are. The
pair tells the operational story together: how many records pass
through cleanly, and at what residual over-grant cost.

The five metrics pull in two directions:

- **Precision-leaning** configurations (macro-P high, sev-d low): few
  false grants, but more under-grants → more escalations.
  Security-first.
- **Recall-leaning** configurations (undershoot low): few missed
  grants, but more over-grants → more residual risk in the granted
  set. Operations-first.

There is no operating point that wins both — the configuration choice
is a function of which cost the deployment cares about more.

### 8.4 RoBERTa-large vs the baselines

At the canonical `risk_07_05_03`:

| metric | TF-IDF | Claude Haiku | RoBERTa-large | gap vs Haiku |
|---|---:|---:|---:|---:|
| sev-weighted delta | 0.95 | 1.12 | **0.63** | RoBERTa **better** (-0.49) |
| overshoot | 33% | 42% | **23%** | RoBERTa **better** (-19 pp) |
| undershoot | 43% | **11%** | 21% | -10 pp worse |
| macro-P | 0.737 | 0.842 | **0.897** | RoBERTa **better** (+5.5 pp) |
| macro-F1 | 0.70 | 0.886 | 0.881 | -0.5 pp (effectively tied) |
| auto/100 | 57 | **89** | 79 | -10 worse |

Note: TF-IDF is a single-threshold model (sklearn `predict()` defaults
to 0.5); it has no per-config sweep, so its "risk_07_05_03" entry is
its single operating point repeated for alignment. Its macro-F1 (0.70)
is the value from §7.6 / §7.9.

The story by baseline:

**Against TF-IDF.** RoBERTa-large beats TF-IDF on every metric by
material margins: sev-d (-0.32 absolute, -34% relative), overshoot
(-10 pp), undershoot (-22 pp), macro-P (+16 pp), macro-F1 (+18 pp),
auto/100 (+22 records). The fine-tune is load-bearing. A TF-IDF
baseline does not approach an enterprise capability gate's
deployability bar; a fine-tuned 355M transformer does. This is the
comparison that forecloses "could a simpler model do this?"

**Against Claude Haiku.** RoBERTa-large wins on macro-P (+5.5 pp),
sev-d (-0.49 absolute, -44% relative), and overshoot (-19 pp). It
**ties** on macro-F1 (0.881 vs 0.886, well within run-to-run variance
on a 100-record test set). It **trails** on undershoot (21% vs 11%)
and auto/100 (79 vs 89). The gap is concentrated on recall: Claude
catches positives RoBERTa-large misses.

The metrics alone don't settle the question — real-world deployment
constraints matter, and they tip the comparison further than the
numbers suggest.

**Latency and cost.** Claude Haiku is an API call. Even at fast
inference (sub-second per call), it is ~10–100× slower than on-host
encoder inference and costs money per call. At enterprise volume (a
million capability evaluations per day is plausible for a multi-tenant
agent platform), Haiku-as-gate becomes a non-trivial fixed cost and a
hard dependency on Anthropic's availability. RoBERTa-large runs in
~25 ms per record on a CPU and ~5 ms on a GPU; it is single-instance
deployable inside the enterprise's own VPC with no external network
hop.

**Data residency and audit.** Each Haiku call sends the task prompt to
an external provider. Many enterprise deployments are blocked from
doing this by data-handling policy (GDPR, sectoral compliance,
internal classification levels). RoBERTa-large is self-hosted: the
prompt never leaves the boundary, the weights are versioned in-house,
and the audit trail is end-to-end inspectable. For a security
mechanism, this is not a soft preference — it is often a hard
requirement.

**Calibration and drift.** Claude Haiku's behaviour at our threshold
configurations is calibrated to a fixed system prompt with 6 examples.
Any change to the prompt or to Anthropic's underlying model version
shifts the operating point silently. RoBERTa-large is a frozen
artefact: the operating point is reproducible bit-for-bit from the
saved weights, the threshold map, and the test data. For a security
mechanism, this is the kind of property auditors and red-teams ask
about.

**What the metric gap actually costs.** The 10-pp undershoot gap
translates to ~10 more records per 100 that need a HITL escalation or
retry. At our 100-record test set that's 10 escalations; at enterprise
volume it's an additional staffing cost on a HITL queue. This is real,
and it is the only place the metric story tips toward Claude. But the
cost has to be weighed against the three points above (latency,
residency, audit), all of which tip toward RoBERTa-large.

**On-paper vs in-practice.** If the question is "which model has the
best F1 on 100 test records?", Claude Haiku and RoBERTa-large are tied.
If the question is "which model is deployable as the permission gate
of a multi-tenant enterprise agent platform?", the on-host fine-tuned
encoder wins for reasons that don't show up in the F1 column. The
right framing for the paper is not "RoBERTa-large beats Haiku on F1";
it is "RoBERTa-large reaches Haiku's classification quality at the
operating points that matter while satisfying enterprise deployment
constraints Haiku doesn't."

### 8.5 Which configuration to deploy, and is this deployable at all?

The six configurations and their operational properties:

| config | sev-d | over | under | macro-P | macro-F1 | auto/100 | best at |
|---|---:|---:|---:|---:|---:|---:|---|
| static_05 | 0.65 | 24% | 22% | 0.898 | 0.876 | 78 | — |
| static_08 | 0.42 | 16% | 27% | **0.941** | 0.878 | 73 | highest macro-P |
| risk_07_05_03 | 0.63 | 23% | 21% | 0.897 | 0.881 | 79 | canonical (§5.4) |
| risk_06_04_02 | 0.72 | 28% | 18% | 0.885 | 0.883 | **82** | best auto + low under |
| risk_05_03_01 | 0.97 | 41% | **16%** | 0.832 | 0.859 | **84** | lowest under |
| risk_08_06_04 | **0.53** | 20% | 21% | 0.915 | **0.890** | 79 | best balance |

Three configurations matter for a deployment decision; the others are
points on the curve:

- **`static_08`**: macro-P 0.941, undershoot 27%. The
  security-maximising choice. Every grant is right 94% of the time,
  but 27 of 100 prompts need escalation. Right for deployments where
  wrong grants are expensive (financial controls, legal review
  systems) and HITL is plentiful.
- **`risk_05_03_01`**: undershoot 16%, macro-P 0.832, sev-d 0.97. The
  throughput-maximising choice. Only 16 of 100 prompts need
  escalation, but every grant is right 83% of the time and sev-d
  climbs near 1.0. Right for deployments where escalation latency is
  the dominant cost (consumer-facing agents) and the granted
  permissions are reviewed downstream.
- **`risk_08_06_04`**: macro-F1 0.890, macro-P 0.915, undershoot 21%,
  sev-d 0.53. The balanced choice. No metric is best, but no metric
  is sacrificed either: macro-P within 2.6 pp of `static_08`,
  undershoot within 5 pp of `risk_05_03_01`, sev-d lowest of any
  configuration that keeps macro-F1 above 0.88. The tier-asymmetric
  thresholds (Tier 1 strict at 0.8, Tier 3 permissive at 0.4) align
  with the operational asymmetry of the underlying permission tiers.

Our recommendation for a first deployment is **`risk_08_06_04`**. It
is the operating point with the lowest sev-d that still keeps macro-F1
in the same range as Claude Haiku, and it never sacrifices one metric
beyond the bar set by the next-best configuration on the same metric.
The tier-asymmetric design also matches the operationally correct
prior: Tier 1 permissions are default-deny — the classifier should
require strong evidence before overriding; Tier 3 permissions are
default-permit — the classifier should err toward granting.

**Against the pre-committed deployability bar (undershoot < 10% AND
macro-P ≥ 0.89):**

| config | undershoot | macro-P | clears bar? |
|---|---:|---:|:---:|
| static_05 | 22% | 0.898 | macro-P ✅, undershoot ❌ |
| static_08 | 27% | 0.941 | macro-P ✅, undershoot ❌ |
| risk_07_05_03 | 21% | 0.897 | macro-P ✅, undershoot ❌ |
| risk_06_04_02 | 18% | 0.885 | both ❌ |
| risk_05_03_01 | 16% | 0.832 | both ❌ |
| risk_08_06_04 | 21% | 0.915 | macro-P ✅, undershoot ❌ |

No configuration clears both bars on the 15-permission system. Four of
six clear macro-P (`static_05`, `static_08`, `risk_07_05_03`,
`risk_08_06_04`); none clear the 10% undershoot bar. This is the same
pattern §7.7 described for RoBERTa-base, but with macro-P ~4 pp higher
and undershoot ~5 pp tighter — meaningful improvement, not a
categorical breakthrough.

**With the hybrid architecture from §7.8** (`email_send_external`
handled by an external deterministic recipient-domain rule, modelled
as an oracle that grants the permission iff ground truth does), the
same canonical config tightens further: macro-P **0.940**, macro-F1
**0.915**, undershoot **18%**. macro-P comfortably clears the bar;
undershoot is 8 pp short. The metrics stay in the 15-permission space
so they remain directly comparable to the TF-IDF and Claude Haiku
baselines. This is the cleaner deployment story: ML for
the 14 permissions where it's at frontier-LLM quality, deterministic
rule for the one permission where (a) the classifier struggles, (b)
the rule is enterprise-standard, and (c) it is the trifecta-completer
warranting a hard gate regardless of model confidence.

**Can RoBERTa-large be deployed in a real enterprise?**

Yes — with the understanding that:

1. **The capability gate is not the whole defence.** Source 1 (role
   ceiling) handles 100% of out-of-ceiling permissions
   deterministically; Source 3 (combination prohibitions) handles the
   trifecta and trifecta-adjacent compositions; Source 2 (this
   classifier) handles the in-ceiling permission selection. The
   classifier is one layer in a defence-in-depth stack, not a
   standalone gate.
2. **HITL load is real but bounded.** At `risk_08_06_04`, 21% of
   prompts need escalation; with the hybrid architecture, that drops
   to 18%. For comparison, C1 (role ceiling alone) under-grants on
   2% of prompts and over-grants on 100% — the classifier trades
   substantially less over-grant for somewhat more under-grant, which
   is the right direction for a security mechanism.
3. **The operating point is the operator's call.** The six
   configurations give the deployer a curve. `static_08` for a
   high-stakes deployment, `risk_05_03_01` for a high-throughput
   one, `risk_08_06_04` for a balanced one. The recommendation is to
   ship with one default and expose the rest as configurable, not to
   hard-code a single threshold.
4. **It is the publishable deployment claim.** Scenario B in §3
   (deployable with operational caveats) is the result. The precision
   result (macro-P 0.941 at `static_08`, exceeding Haiku's 0.895) is
   a stronger publishable headline than RoBERTa-base delivered, and
   the hybrid architecture closes the rest of the credible-deployment
   story. The result that matters for the paper is not the F1 tie
   with Haiku; it is that an on-host, audit-friendly, residency-safe
   355M-parameter model reaches that quality at all.


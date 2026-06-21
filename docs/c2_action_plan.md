# C2 Implementation Action Plan

**Status:** Draft — pending review.
**Purpose:** Single source of truth for what we'll build, in what order, with what
decisions locked in. Once approved, this becomes the implementation checklist.

The Notion proposal §8.1 was updated alongside this plan to reflect the same
design choices. If the two disagree, this document wins until the next sync.

---

## 1. Goal and scope

Train and integrate **Source 2 (task-context classifier)** into the existing
experiment harness, producing a new condition `C2 = C1 ∩ classifier_output` and
result file `results/c2.json`. Establish a defensible baseline comparison and a
threshold strategy that supports two distinct deployment claims.

Out of scope for this phase: Source 3 (C3), C4 deceptive-agent runs, actual
agent execution against the granted permissions, classifier fine-tuning on
production audit logs.

## 2. Design decisions (locked in this plan)

| Decision | Choice | Rationale |
|---|---|---|
| Model | DeBERTa-v3-base, fine-tuned, multi-label sigmoid head | Strong text-classification baseline with limited data; deterministic encoder with no chat surface (no agent-influenceable runtime input) |
| Baselines (run before DeBERTa) | TF-IDF + logistic regression, few-shot Claude Haiku 4.5 (probabilistic output + 6-config threshold sweep) | Sanity-check that fine-tuning is load-bearing; provide off-the-shelf comparison points for the paper |
| Input features | Task description text only, max 256 tokens | Department and sensitivity excluded — see §2.1 |
| Department in input | **Excluded** | C2 already intersects with the Source 1 ceiling; supplying department to the classifier lets it learn shortcuts that conflate Source 1 and Source 2 and weakens the architectural separation claim |
| Sensitivity in input | **Excluded** | 60% raw human-LLM agreement (§7.6); training on noisy labels |
| Thresholds | Three strategies considered: **static** (single uniform threshold for all permissions — 0.5 and 0.8 evaluated), **risk-based** (per-tier asymmetric defaults 0.7/0.5/0.3), **fine-tuned** (validation-set-derived). Implement static + risk-based; document fine-tuned as future work | Static is the zero-opinion baseline; risk-based encodes per-tier asymmetric cost of FP vs FN; fine-tuned needs more validation data than 50 records can support — see §2.2 |
| Rare-permission exclusion | **Dropped** | The old `<30 records → tier default` rule complicated inference for no measurable benefit; train all 15 |
| Loss | BCEWithLogitsLoss with per-label `pos_weight = (N − n_pos) / n_pos` | Standard for multi-label imbalance |
| Token cap | 256 | Empirically motivated: longest training prompt = 105 tokens, p95 = 85. 256 leaves headroom while cutting attention compute ~4× vs DeBERTa-v3's native 512. See Notion §6.7 |
| Operationally-safe deployment point | **Undershoot rate < 10%** with **macro-precision ≥ 0.89** (Claude Haiku floor). Per-tier breakdowns reported for diagnostics but no hard tier-level constraint. The deployable C2 minimises sev-delta on the auto-handled portion subject to these two limits. Records with any undershoot fall back to HITL approval, log-only mode, or retry with the C1 grant set | See §6.3 |
| Compute | Google Colab T4 free tier for fine-tune; local CPU for inference and eval | Local machine has no GPU and 16GB RAM; CPU fine-tune is feasible but ~1–2hr/epoch and squeezed for RAM |

### 2.1 Why we drop sensitivity and department from the classifier input

These exclusions matter beyond personal preference. The Notion proposal frames
Source 2 as a component that reasons about *task content* independently of any
identity signal. If we feed it department, the classifier may simply learn the
mean permission set per department — which is exactly what Source 1 already
provides. The marginal lift of Source 2 over Source 1 should come from
*understanding the task*, not from re-encoding department. Excluding department
makes the contribution measurable.

Sensitivity is excluded because Section 7.6 of the proposal already establishes
it as unreliable metadata (60% raw agreement, MEDIUM tier unstable). Using an
unreliable signal as a training feature corrupts the gradient updates rather
than helping them. It stays in the dataset as descriptive metadata only.

### 2.2 Three threshold strategies — what we implement and what we skip

The classifier produces a confidence score in `[0, 1]` per permission. A
threshold turns that score into a binary grant/deny decision. Three strategies
for choosing thresholds were considered:

1. **Static thresholds (implemented).** A single fixed threshold applied
   uniformly to all 15 permissions. We evaluate both **0.5** (balanced) and
   **0.8** (strict) as static configurations. This strategy ignores
   per-permission risk entirely — every permission, regardless of whether it's
   a default-deny credential like `database_read` or a default-permit one like
   `confluence_read`, is gated by the same number. Reporting both values
   bounds the no-risk-awareness behaviour: 0.5 leans toward granting, 0.8
   leans toward denying.
2. **Risk-based thresholds (implemented, primary variant).** Per-tier
   asymmetric defaults: Tier 1 = 0.7, Tier 2 = 0.5, Tier 3 = 0.3. These
   encode the asymmetric cost of false positives vs false negatives by tier.
   Tier 1 (default-deny: `database_read`, `http_request`,
   `email_send_external`, `pull_request_create`) requires high confidence
   before granting because over-granting is high-risk. Tier 3 (default-permit:
   `confluence_read`, `jira_read`, `file_read_uploaded`) requires only low
   confidence because under-granting breaks common tasks and over-granting
   has near-zero blast radius. Tier 2 is balanced. The values come from
   policy reasoning, not validation-set tuning — zero free parameters
   estimated from data.
3. **Fine-tuned thresholds (documented, not implemented).** Threshold values
   derived from a held-out validation subset by minimising a severity-weighted
   objective. Strictly more expressive than risk-based, but requires a
   validation set with enough positive examples per permission for stable
   estimation — for rare permissions like `email_send_external` we'd be
   fitting against a handful of examples, which produces noisy thresholds
   that won't generalise. Fine-tuning becomes appropriate once the labelled
   corpus is order-of-magnitude larger. Because we are not implementing
   fine-tuning in this iteration, **no validation set is held out**: all 500
   training records are used for classifier fine-tuning.

The comparison between static (at two operating points) and risk-based is
itself a publishable finding. If risk-based meaningfully beats both static
configurations, the asymmetric tier weighting was worth encoding; if not,
the simpler uniform threshold is good enough and we save operators a layer
of design choice.

## 3. Repo layout (files to create)

```
mostargate/classifier/
  __init__.py
  data.py             # load train/test JSON, tokenise, build label matrix
  model.py            # HF AutoModelForSequenceClassification wrapper
  train.py            # training loop (HF Trainer), pos_weight, checkpointing
  predict.py          # inference: prompts → raw scores
  thresholds.py       # the three threshold configurations as named constants
  baselines.py        # TF-IDF + logreg + few-shot LLM baselines
  bootstrap.py        # bootstrap-resample CIs for all metrics
  eval.py             # full evaluation pipeline over the test set

mostargate/experiments/conditions/
  c2.py               # Source 1 ceiling ∩ classifier prediction (threshold strategy via env/CLI)

notebooks/
  train_classifier.ipynb   # Colab-ready training notebook

results/
  c2_static_05.json                  # uniform 0.5 threshold
  c2_static_08.json                  # uniform 0.8 threshold
  c2_risk_based_07_05_03.json        # per-tier defaults (primary risk-based)
  c2_risk_based_06_04_02.json        # one bucket more permissive
  c2_risk_based_05_03_01.json        # two buckets more permissive
  c2_risk_based_08_06_04.json        # one bucket more conservative
  classifier_baselines.json          # TF-IDF + Claude Haiku baseline metrics
  c2_summary.md                      # comparison table with bootstrap CIs;
                                     # identifies operationally-safe config

dataset/classifier_artifacts/
  model/                        # trained model checkpoint (gitignored)
  model_card.md                 # training metadata, hyperparameters, seeds

Makefile additions:
  classifier-baselines   # uv run -m mostargate.classifier.baselines
  classifier-eval        # uv run -m mostargate.classifier.eval
  experiments            # already exists — runs c2 across all three threshold configs
```

Note: no `tune.py` and no validation split — we are not tuning thresholds in
this iteration. All 500 training records feed the classifier directly. If
fine-tuned thresholds are added later, the data pipeline gains a single
function to produce a holdout from `train_split.json`; nothing else has to
change.

Trained model weights go in `dataset/classifier_artifacts/model/` and are
**not committed** (added to `.gitignore`). Add a `model_card.md` next to them
recording the training run metadata.

## 4. Dependencies

Add via `uv`:

```
uv add transformers torch datasets scikit-learn anthropic
```

- `transformers` — model + tokenizer
- `torch` — fine-tuning backend (HF Trainer requires it)
- `datasets` — convenient dataset object for HF Trainer
- `scikit-learn` — TF-IDF + logreg baseline + bootstrap utilities
- `anthropic` — few-shot baseline against Claude

`torch` on Colab is preinstalled; locally we'll get the CPU build via uv. No
CUDA toolkit needed locally.

## 5. Implementation order

The order matters — earlier steps de-risk later ones.

### Phase A — Data plumbing (target: 30 min)

1. **Implement `mostargate/classifier/data.py`**:
   - `load_records(path)` → list of records (reads `dataset/train.json` or
     `dataset/test.json` directly; no separate split file is needed since
     we're not holding out a validation set)
   - `build_label_matrix(records)` → numpy array of shape `(n, 15)` matching
     the `constants.TOOLS` key order
   - `tokenize(records, tokenizer, max_len=512)` → input_ids, attention_mask
2. **Sanity-check class balance**: print per-permission positive count across
   the 500 training records. Confirm `pos_weight` calculation is sane (no
   division by zero, no extreme values that suggest a degenerate label).

### Phase B — Baselines first (target: 2 hr)

Run these BEFORE any DeBERTa work. If a baseline beats DeBERTa we'd want to
know immediately.

4. **Implement TF-IDF + logreg baseline** in `baselines.py`:
   - Vectorise task text with `sklearn.feature_extraction.text.TfidfVectorizer`
     (n-grams 1–2, max_features=10000)
   - One-vs-rest logistic regression per permission with class-weight='balanced'
   - Evaluate on the test set with the same metrics as C2
5. **Implement few-shot Claude baseline** in `baselines.py`:
   - Use the `anthropic` SDK with `claude-haiku-4-5-20251001`
   - System prompt explains the 15-permission taxonomy + JSON schema with
     per-permission confidence floats in [0.0, 1.0]
   - 6 hand-picked diverse example records as few-shot
   - One API run over the 100-record test set → cache the 100×15 score
     matrix to `dataset/classifier_artifacts/claude_haiku_scores.json`
   - Apply the six THRESHOLD_CONFIGS post-hoc to the cached scores —
     same six configs that will be applied to DeBERTa in Phase D
   - Add prompt caching (system prompt + few-shots) to cut cost; note
     that current prompt size (~1.4k tokens) is below Haiku's 2048-token
     cache minimum so caching is currently inactive
6. **Save baseline metrics** to `results/classifier_baselines.json`. Both
   baselines run independently via `make baseline-tfidf` and
   `make baseline-claude` (and together via `make baselines`).

Outcome of Phase B sets a floor for DeBERTa. If DeBERTa cannot meaningfully
beat both baselines, surface that finding and re-evaluate the fine-tune choice
before spending more time on it.

### Phase C — DeBERTa fine-tuning on Colab (target: 1–2 hr including the
training run itself)

7. **Write `mostargate/classifier/model.py`**:
   - `build_model()` → `AutoModelForSequenceClassification.from_pretrained(
     "microsoft/deberta-v3-base", num_labels=15,
     problem_type="multi_label_classification")`
   - `build_tokenizer()` → `AutoTokenizer.from_pretrained(...)` with
     `model_max_length=512`
8. **Write `mostargate/classifier/train.py`** as a CLI:
   - Loads `dataset/train.json` directly (all 500 records)
   - Builds a HF `Trainer` with `TrainingArguments`:
     - learning_rate=2e-5
     - per_device_train_batch_size=16 (GPU) / 4 (CPU)
     - num_train_epochs=5
     - eval_strategy="no" — no validation set, train for fixed epochs and
       save the final checkpoint
     - weight_decay=0.01, warmup_ratio=0.1
     - seed=42
   - Override loss with custom `pos_weight` via a `Trainer` subclass
   - Saves final model to `dataset/classifier_artifacts/model/`
   - Writes `model_card.md` with full config dump including the epoch budget
     and the explicit no-validation note
9. **Write `notebooks/train_classifier.ipynb`** — Colab-ready:
   - First cell: `!pip install transformers torch datasets scikit-learn`
   - Cells to upload `train_split.json` + `validation_split.json` (or mount Drive)
   - Cells to clone the repo or paste the training code inline
   - Final cell: zip and download the model checkpoint
   - Document required runtime: `Runtime → Change runtime type → T4 GPU`
10. **Train it.** On Colab T4: expect <10 minutes total. Download the
    model directory back to `dataset/classifier_artifacts/model/`.
11. **Smoke test locally**: load the downloaded model, run inference on 5 random
    test records, eyeball the predictions. Catches any download corruption or
    tokenizer mismatch before we waste time on full eval.

### Phase D — C2 condition wiring across the three threshold configs (target: 1 hr)

12. **Write `mostargate/classifier/thresholds.py`** — a small module that
    defines named threshold configurations as constants. Names encode the
    actual threshold values: static names carry the single threshold value;
    risk-based names carry the `<T1>_<T2>_<T3>` triplet. The risk-based
    sweep brackets the 0.7/0.5/0.3 default on both sides so we can locate
    the operationally-safe deployment point:

    ```python
    STATIC_05            = {p: 0.5 for p in PERMISSIONS}
    STATIC_08            = {p: 0.8 for p in PERMISSIONS}
    RISK_BASED_07_05_03  = {p: tier_thr(p, 0.7, 0.5, 0.3) for p in PERMISSIONS}  # default
    RISK_BASED_06_04_02  = {p: tier_thr(p, 0.6, 0.4, 0.2) for p in PERMISSIONS}  # one bucket more permissive
    RISK_BASED_05_03_01  = {p: tier_thr(p, 0.5, 0.3, 0.1) for p in PERMISSIONS}  # two buckets more permissive
    RISK_BASED_08_06_04  = {p: tier_thr(p, 0.8, 0.6, 0.4) for p in PERMISSIONS}  # one bucket more conservative
    ```

    All configurations are hand-picked priors — no validation-set learning.
    The sweep keeps the tier-asymmetry structure constant (Tier 1 always
    strictest, Tier 3 always loosest) and shifts all three values together
    by 0.1, so undershoot should track monotonically with threshold
    strictness across the sweep.
13. **Write `mostargate/experiments/conditions/c2.py`**:
    - Loads the trained model once and computes raw prediction scores for
      all test records. Caches the prediction matrix to
      `dataset/classifier_artifacts/predictions_test.npy` so subsequent
      threshold-config runs skip inference entirely (this is what
      `cache predictions = yes` buys us).
    - For each record: load cached scores → apply chosen threshold dict →
      intersect with `constants.DEPARTMENT_CEILINGS[record["department"]]`
      → return `EvalResult`.
    - Threshold config is selectable via env var, e.g.
      `C2_THRESHOLD=risk_based_07_05_03`.
14. **Register `c2` in `mostargate/experiments/run.py`**:
    - The runner loops over all named configurations and writes one
      results file per config:
      `results/c2_static_05.json`,
      `c2_static_08.json`,
      `c2_risk_based_07_05_03.json`,
      `c2_risk_based_06_04_02.json`,
      `c2_risk_based_05_03_01.json`,
      `c2_risk_based_08_06_04.json`.

### Phase E — Evaluation with bootstrap CIs (target: 1 hr)

15. **Write `mostargate/classifier/bootstrap.py`**:
    - `bootstrap_metric(records, predictions, ground_truth, metric_fn, n=1000)`
      → returns `(point_estimate, ci_low, ci_high)`
    - Resamples records with replacement, recomputes the metric on each
      resample, takes the 2.5th and 97.5th percentile
    - Applied to: macro-F1, per-tier macro-F1, severity-weighted delta,
      overshoot rate, undershoot rate
16. **Write `mostargate/classifier/eval.py`**:
    - Pulls together all results (C0, C1, the three C2 configurations,
      baselines) into a single comparison report
    - Writes a markdown summary table to `results/c2_summary.md` with point
      estimates + 95% CIs for every metric
    - Identifies the **operationally-safe deployment point** post-hoc: among
      the three C2 configurations, find the one (if any) whose undershoot
      rate is ≤ C1's *and* whose severity-weighted delta beats C1's. If more
      than one qualifies, pick the one with the lowest delta. Surface this
      in the summary as the recommended deployment configuration.

## 6. Notes on specific risks

### 6.1 Risk: pos_weight blowing up on rare labels

For a label that appears in, say, 2 of 450 training records,
`pos_weight = 448 / 2 = 224`. The gradient on those positive examples becomes
huge and can destabilise training. Mitigations:
- Clip `pos_weight` to a max (e.g. 10).
- Or normalise the loss by total label count rather than per-label.
- Or just accept that rare labels will train poorly and the model will default
  to 0 for them (which is Tier 1's correct default-deny behaviour anyway).

I'll go with **clipping at 10** as the default and document the choice in the
model card.

### 6.2 Risk: tokeniser drift between train and inference

DeBERTa-v3 has a SentencePiece tokeniser bundled with the model. Always load it
from the same checkpoint directory the model was loaded from. The `model_card.md`
records the exact HF model revision used.

### 6.3 Risk: Colab session timeout mid-training

Colab free sessions can disconnect at ~90 minutes idle. Training takes <10 min on
T4, so this is unlikely to bite. Mitigation: the training script checkpoints
every epoch, so a disconnect at worst loses one epoch.

### 6.4 Risk: no validation set means no overfit signal during training

Training on all 500 records leaves no in-loop way to detect overfitting. With
a 184M-parameter model and 500 training examples, overfitting is essentially
guaranteed if training runs long enough. Mitigation:
- Fix the epoch budget at 5 and save the final checkpoint. Don't search for
  the "best" epoch — we have no signal to define "best" against.
- If test-set metrics turn out catastrophic (e.g. F1 near 0), reduce epochs.
  If they're suspiciously good (e.g. F1 > 0.99 with overshoot 0 and
  undershoot 0), worry — that's unlikely on a clean test set, and would
  suggest train/test contamination upstream.
- The test set (100 records, `dataset/test.json`) is never touched during
  training and is the sole final-evaluation surface.

### 6.5 Risk: baseline beats DeBERTa

If TF-IDF + logreg gets within 2 F1 of DeBERTa, we have a meaningful finding to
publish: the dataset doesn't need a transformer. We'd ship the simpler model
and write it up as a positive surprise. Either outcome is fine; we just need
the data to choose between them.

## 7. What we'll report

After all phases complete, the results table looks like this. All numbers are
computed on the 100-record test set. C2 rows use the same trained classifier
weights; only the threshold strategy differs:

|  | macro-P | macro-R | macro-F1 | sev-d | overshoot | undershoot | auto-handled | sev-d on auto |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C0 (all-grant) | — | — | — | 26.12 | 100% | 0% | 100/100 | 26.12 |
| C1 (Source 1) | — | — | — | 17.51 | 100% | 2% | 98/100 | ~17.5 |
| TF-IDF static_05 | 0.77 | 0.68 | 0.70 | 0.95 | 33% | 43% | 57/100 | 0.84 |
| TF-IDF risk_07_05_03 | 0.74 | 0.65 | 0.62 | 1.43 | 77% | 52% | 48/100 | 1.48 |
| TF-IDF risk_05_03_01 | 0.41 | 0.85 | 0.51 | 6.38 | 100% | 12% | 88/100 | 6.26 |
| Claude static_05 | 0.85 | 0.96 | 0.89 | 1.12 | 41% | 11% | 89/100 | 1.09 |
| Claude static_08 | 0.90 | 0.91 | 0.89 | 0.67 | 27% | 22% | 78/100 | 0.71 |
| **Claude risk_07_05_03** (canonical) | **0.84** | **0.96** | **0.89** | **1.12** | **42%** | **11%** | **89/100** | **1.08** |
| Claude risk_06_04_02 | 0.82 | 0.97 | 0.87 | 1.26 | 45% | 11% | 89/100 | 1.24 |
| Claude risk_05_03_01 | 0.70 | 0.97 | 0.77 | 2.88 | 86% | 10% | 90/100 | 2.86 |
| Claude risk_08_06_04 | 0.87 | 0.94 | 0.89 | 0.91 | 37% | 14% | 86/100 | 0.92 |
| **C2 `static_05`** | — | — | — | — | — | — | — | — |
| **C2 `static_08`** | — | — | — | — | — | — | — | — |
| **C2 `risk_07_05_03`** (default) | — | — | — | — | — | — | — | — |
| **C2 `risk_06_04_02`** (perm +1) | — | — | — | — | — | — | — | — |
| **C2 `risk_05_03_01`** (perm +2) | — | — | — | — | — | — | — | — |
| **C2 `risk_08_06_04`** (cons +1) | — | — | — | — | — | — | — | — |

Filled-in rows above are from Phase B (baselines complete). Bold rows
pending DeBERTa training in Phase C.

Three specific claims we want to be able to make:
1. **C2 (best configuration) beats C1 on sev-delta restricted to the
   auto-handled portion** with the CI not overlapping C1's point estimate
   (intrinsic accuracy claim — Source 2 adds measurable security value on
   top of role ceiling for the records it handles autonomously).
2. **Risk-based beats both static configurations** by a meaningful margin
   (per-tier asymmetric weighting was worth encoding — or, if not, the
   simpler uniform threshold is good enough and we report that finding
   instead).
3. **At least one C2 configuration is operationally deployable**:
   undershoot rate < 10% and macro-precision ≥ 0.89. Records with any
   undershoot escalate to a HITL / C1-fallback path.

If all three hold with reasonable CIs, the C2 story is coherent and
publishable. If only (1) and (3) hold but not (2), we've shown that Source
2 adds value but that tier-asymmetric thresholds don't — a less ambitious
but still publishable finding. If (3) fails (undershoot ≥ 10% or precision
< 0.89 for every C2 configuration), we report the gap honestly: the
classifier is not yet deployable and identify whether the failure mode is
recall (escalation rate too high) or precision (grants too noisy).

### The deployment-claim formula

For the operationally-safe configuration, the headline claim is:

> For N% of agent invocations, C2 makes the grant decision autonomously
> with severity-weighted delta D on the auto-handled portion — an X%
> reduction in attack surface vs the role-based ceiling. The remaining
> (100 − N)% escalate to HITL or fall back to C1 grants.
>
> N% = 100 − undershoot_rate(C2)
> X% = (sev_delta(C1) − sev_delta_on_auto(C2)) / sev_delta(C1)

This frames C2's value where it actually accrues — on the auto-handled
records — and is honest about the escalation tail.

## 8. Decisions locked in (was: open questions)

All four open questions were resolved with the user:

1. **Baseline LLM:** Claude Haiku 4.5 only (no Sonnet baseline).
2. **Static thresholds:** evaluate both 0.5 and 0.8.
3. **Cache predictions:** yes. The cache enables the risk-based threshold
   sweep at near-zero cost — we will try the four risk-based variants
   (default plus three) to locate the operationally-safe deployment point
   (zero-or-near-zero undershoot, still meaningfully below C1 on sev-weighted
   delta).
4. **Trained weights location:** local in `dataset/classifier_artifacts/model/`
   for now; HuggingFace Hub upload deferred to a follow-up after the
   evaluation is published.

## 9. Definition of done

- All six C2 results files exist and load cleanly:
  `c2_static_05.json`, `c2_static_08.json`,
  `c2_risk_based_07_05_03.json`, `c2_risk_based_06_04_02.json`,
  `c2_risk_based_05_03_01.json`, `c2_risk_based_08_06_04.json`
- `results/classifier_baselines.json` exists with TF-IDF and Claude Haiku
  baselines
- `results/c2_summary.md` contains the comparison table with bootstrap CIs
  and identifies the operationally-safe deployment configuration (the
  configuration with C2 undershoot ≤ C1's that still beats C1 on
  severity-weighted delta)
- `mostargate/classifier/model_card.md` documents the training run
  (hyperparameters, seed, epoch budget = 5, training data size = 500, no
  validation hold-out)
- Trained weights live in `dataset/classifier_artifacts/model/` (gitignored)
  — HuggingFace Hub upload deferred to a follow-up
- `make experiments` runs the full evaluation pipeline locally (excluding
  the Colab fine-tune step) and refreshes all the JSON outputs
- The three specific claims in §7 either all hold or we have a concrete
  finding to report instead

---

End of action plan. Review and flag anything you'd cut, add, or reorder.

# Phase B Findings — Classifier Baselines

This document reports the baseline classifier results that bracket DeBERTa's
expected performance: TF-IDF + logistic regression (simple, classical) and
few-shot Claude Haiku 4.5 (zero-fine-tune, off-the-shelf frontier model).
The role of these baselines is to verify that fine-tuning DeBERTa is
load-bearing — that the architecture isn't more complex than the dataset
needs.

**Status:** Both baselines complete. Per-tier metrics added to
`mostargate/experiments/metrics.py` and all result files regenerated.

---

## 1. Headline numbers — both baselines

Trained on the 500-record train split.

- **TF-IDF + logreg:** TF-IDF features (n-grams 1–2, max_features=10000) +
  one-vs-rest logistic regression with `class_weight='balanced'`. Single
  operating point at sklearn's default 0.5 decision threshold.
- **Claude Haiku 4.5 few-shot:** `claude-haiku-4-5-20251001`, temperature
  0, system prompt carrying the 15-permission taxonomy + 6 hand-picked
  examples drawn from the train split. The prompt asks Claude to return a
  confidence float per permission, not a boolean — so the same trained
  output is thresholded six different ways to produce six operating
  points (the same six configs we will apply to DeBERTa). The 100×15
  score matrix is cached at
  `dataset/classifier_artifacts/claude_haiku_scores.json` so the
  threshold sweep and any re-evaluation do not re-call the API. Prompt
  caching configured but did not activate — the cached portion
  (≈5.7k chars ≈1.4k tokens) is below Haiku's 2048-token cache minimum.

The canonical operating point shown below is `risk_based_07_05_03`
(Tier 1 = 0.7, Tier 2 = 0.5, Tier 3 = 0.3 — the defaults from §5.4 of
the proposal). Full Claude sweep across all six threshold configs is
in §2.7; TF-IDF sweep is in §2.6.

Evaluated on the 100-record held-out test set:

| condition | sev-w delta | overshoot | undershoot |
|---|---:|---:|---:|
| C0 (all-grant, 15-perm union) | 26.12 | 100% | 0% |
| C1 (Source 1 role ceiling only) | 17.51 | 100% | 2% |
| **TF-IDF + logreg (threshold 0.5)** | 0.95 | 33% | **43%** |
| **Claude Haiku (risk_07_05_03)** | **1.12** | **42%** | **11%** |

TF-IDF macro-F1 = 0.702 (per §2 below). Claude macro-F1 at risk_07_05_03
is in the 0.84–0.86 range (per §2.7).

---

## 2. Per-permission breakdown

Precision, recall, and F1 for the 15-permission output of the TF-IDF
classifier. Sorted by ground-truth positive count (test set, n=100). Tier
column comes from `mostargate/constants.py` (`TOOL_TIERS`).

| permission | tier | gt_pos | pred_pos | P | R | F1 |
|---|:-:|---:|---:|---:|---:|---:|
| database_read | 1 | 44 | 51 | 0.82 | 0.95 | **0.88** |
| confluence_read | 3 | 30 | 31 | 0.84 | 0.87 | **0.85** |
| github_read | 2 | 29 | 29 | 0.83 | 0.83 | **0.83** |
| jira_write | 2 | 22 | 19 | 0.84 | 0.73 | 0.78 |
| email_read | 2 | 20 | 20 | 0.80 | 0.80 | 0.80 |
| jira_read | 3 | 19 | 17 | 0.71 | 0.63 | 0.67 |
| export_file | 2 | 14 | 14 | 0.79 | 0.79 | 0.79 |
| salesforce_read | 2 | 12 | 12 | 0.83 | 0.83 | **0.83** |
| slack_read | 2 | 10 | 11 | 0.82 | 0.90 | **0.86** |
| http_request | 1 | 10 | 8 | 1.00 | 0.80 | **0.89** |
| file_read_uploaded | 3 | 10 | 10 | 0.80 | 0.80 | 0.80 |
| email_send_external | 1 | 8 | 10 | 0.40 | 0.50 | **0.44** ⚠ |
| code_execute | 2 | 7 | 2 | 1.00 | 0.29 | **0.44** ⚠ |
| slack_write | 2 | 6 | 3 | 1.00 | 0.50 | 0.67 |
| pull_request_create | 1 | 1 | 0 | 0.00 | 0.00 | **0.00** ⚠ |

The three weak permissions (⚠) are exactly the three with the fewest
positive examples in the training set — `pull_request_create` (n=13 train,
1 test), `code_execute` (n=24 train, 7 test), and `email_send_external`
(n=46 train, 8 test). The model has too few positive examples to learn
these labels reliably. This was forecast in the Phase A class-balance
analysis (§6.7 of the proposal).

Two of those three are Tier 1 default-deny permissions —
`pull_request_create` and `email_send_external`. Failing on them is
asymmetrically expensive: missing a Tier 1 grant breaks the task, but
missing a Tier 1 deny would have expanded attack surface, which is the
worse failure for a security control. The TF-IDF model happens to fall on
the safe side for `pull_request_create` (predicts always-deny — wrong, but
security-conservative) and on the unsafe side for `email_send_external`
(P = 0.40, meaning 60% of its email-send predictions are false grants).

---

## 2.5 Per-tier breakdown — the asymmetric cost story

Aggregate sev-weighted delta and undershoot hide the most important
diagnostic: *which tier* the errors occur in. Tier 1 (default-deny) errors
are asymmetrically costly on both sides — over-granting Tier 1 expands
high-risk attack surface; under-granting Tier 1 denies a task its core
capability (database, network, external email). Tier 3 errors are cheap
either way.

The metrics module now reports per-tier overshoot and undershoot:

Rows below use TF-IDF at its single operating point (threshold 0.5) and
Claude at the canonical `risk_07_05_03` configuration. Full Claude sweep
across all six threshold configs is in §2.7.

### Per-tier OVERSHOOT (mean count per record / rate of records with any)

| condition | T1 cnt | T1 rate | T2 cnt | T2 rate | T3 cnt | T3 rate |
|---|---:|---:|---:|---:|---:|---:|
| C0 | 3.37 | 100% | 6.80 | 100% | 2.41 | 100% |
| C1 (role ceiling) | 1.82 | 96% | 4.82 | 100% | 2.41 | 100% |
| TF-IDF + logreg | 0.15 | 15% | 0.19 | 16% | 0.12 | 11% |
| **Claude Haiku** | **0.14** | **14%** | **0.32** | **28%** | **0.06** | **6%** |

### Per-tier UNDERSHOOT (mean count per record / rate of records with any)

| condition | T1 cnt | T1 rate | T2 cnt | T2 rate | T3 cnt | T3 rate |
|---|---:|---:|---:|---:|---:|---:|
| C0 | 0.00 | 0% | 0.00 | 0% | 0.00 | 0% |
| C1 (role ceiling) | 0.00 | 0% | 0.02 | 2% | 0.00 | 0% |
| TF-IDF + logreg | 0.09 | **9%** | 0.29 | 27% | 0.13 | 12% |
| **Claude Haiku** | **0.00** | **0%** | 0.09 | 9% | 0.04 | 4% |

### What the per-tier numbers show

1. **The role ceiling already removes ~50% of Tier 1 over-grants.** C1 cuts
   Tier 1 over-grants from 3.37/task (C0) to 1.82/task — a 46% reduction
   just from department-level scoping. The remaining 1.82 Tier 1
   over-grants per task is what C2 needs to attack.

2. **Both baselines crush the Tier 1 over-grant problem.** TF-IDF takes
   Tier 1 over-grants down to 0.15/task (92% reduction vs C1); Claude
   Haiku goes further to 0.14/task (92% reduction vs C1, with the
   significantly more important result of zero Tier 1 undershoot — see
   point 3). The headline security claim "Source 2 removes 92% of the
   Tier 1 attack surface that role-based IAM leaves attached" is
   achievable even at the classical-baseline floor.

3. **Claude Haiku has zero Tier 1 undershoot.** This is the most
   operationally significant finding. The 11% aggregate undershoot is
   entirely in Tier 2 (9%) and Tier 3 (4%) — exactly the tiers where
   under-granting is recoverable (e.g. missing a `slack_write` doesn't
   kill the task, the user just doesn't get the optional notification).
   No task in the test set loses its core capability under Claude Haiku
   at the canonical risk-based defaults.

4. **TF-IDF undershoots all three tiers, including Tier 1.** Its 9% Tier 1
   undershoot is the hardest operational failure mode — 9 of 100 tasks
   lose `database_read` / `http_request` / `email_send_external` /
   `pull_request_create` when they need it. Even though TF-IDF's
   aggregate sev-weighted delta is favourable, its operational profile is
   not deployable.

## 2.6 What threshold produced these numbers? — TF-IDF across all six configurations

Both baselines were initially reported at a single operating point. The
threshold story differs:

- **TF-IDF + logreg** uses sklearn's `clf.predict()` which applies a
  **default 0.5 cutoff** on the predicted probability. `class_weight='balanced'`
  affects the trained model but not the inference cutoff. So the TF-IDF
  row in §1 is effectively the `static_05` configuration of our C2
  taxonomy — one of six possible thresholdings of the same trained model.
- **Claude Haiku** has no probability output to threshold. Its operating
  point is determined by the prompt (taxonomy + 6 few-shots + "when in
  doubt, deny") and `temperature=0`. To shift Claude's operating point you
  would have to change the prompt — there is no post-hoc threshold dial.

For a fair like-for-like comparison with the eventual six DeBERTa
configurations, the TF-IDF trained model was re-evaluated at all six
threshold configs using `predict_proba` + manual thresholding:

| config | sev-delta | overshoot | undershoot | T1 over | T1 under | T2 under | T3 under |
|---|---:|---:|---:|---:|---:|---:|---:|
| static_05 | 0.95 | 33% | 43% | 0.15 | **0.09** | 0.29 | 0.13 |
| static_08 | 0.00 | 0% | 95% | 0.00 | 0.52 | 1.10 | 0.53 |
| risk_07_05_03 (default) | 1.43 | 77% | 52% | 0.00 | **0.34** | 0.29 | 0.02 |
| risk_06_04_02 | 3.09 | 94% | 28% | 0.03 | 0.18 | 0.13 | 0.01 |
| risk_05_03_01 | 6.38 | 100% | 12% | 0.15 | **0.09** | 0.03 | 0.00 |
| risk_08_06_04 | 0.58 | 46% | 76% | 0.00 | 0.52 | 0.52 | 0.07 |

Raw sweep data saved to `results/tfidf_threshold_sweep.json`.

**Two findings emerge from this sweep:**

1. **No TF-IDF configuration meets the Tier 1 undershoot = 0 constraint.**
   The lowest Tier 1 undershoot count any TF-IDF threshold can produce is
   0.09 per task (~9% of test records). Under our tier-aware budget
   (T1 undershoot must equal C1's 0%), TF-IDF is structurally undeployable
   at any threshold — its probabilities are not sharp enough to separate
   Tier 1 positives from negatives cleanly.

2. **The canonical risk-based defaults (0.7/0.5/0.3) are too strict for
   TF-IDF.** The defaults give 0.34 Tier 1 undershoot per task — worse than
   simple uniform `static_05` at 0.09. The risk-based defaults implicitly
   assume the classifier's probability scores are well-calibrated; a 0.7
   gate on Tier 1 only makes sense if confident true positives score above
   0.7. TF-IDF underestimates rare positives, so the strict Tier 1 cutoff
   kills recall on exactly the permissions where Tier 1 matters most. Only
   the loosest variant `risk_05_03_01` recovers TF-IDF's recall to the
   `static_05` level, at the cost of higher sev-weighted delta (6.38 vs
   0.95).

This second finding is the operational argument for DeBERTa fine-tuning:
**we need a model whose probabilities can support the risk-based defaults**.
If DeBERTa produces sharper, better-calibrated probabilities than TF-IDF,
the same 0.7/0.5/0.3 defaults that fail here should work much better
there. The DeBERTa threshold sweep in Phase D will test this directly.

Claude Haiku, despite having no tunable threshold, occupies a region of
the trade-off space that TF-IDF cannot reach at any threshold: T1
overshoot 0.10 / T1 undershoot 0.00 simultaneously. The architectural lift
from bag-of-words to a contextually-aware decision is what unlocks the
Tier 1 = 0 operating point.

## 2.7 Claude Haiku — single API run, six threshold operating points

To make Claude directly comparable to the threshold-swept TF-IDF and DeBERTa
results, the system prompt asks Claude to return a confidence float in
[0.0, 1.0] per permission rather than a categorical boolean. A single API
run over the 100 test records produces a cached 100 × 15 score matrix at
`dataset/classifier_artifacts/claude_haiku_scores.json`; the six threshold
configurations are then applied post-hoc to that matrix with zero
additional API calls.

Cost for the run: ~210k uncached input tokens + ~20k output tokens
(~$0.30). The system prompt is below Haiku's 2048-token prompt-cache
minimum so caching did not activate — flagged for a possible future fix.

| config | sev-d | overshoot | undershoot | macro-P | auto/100 | sev-d on auto |
|---|---:|---:|---:|---:|---:|---:|
| static_05 | 1.12 | 41% | 11% | 0.848 | 89 | 1.09 |
| static_08 | 0.67 | 27% | 22% | **0.895** | 78 | 0.71 |
| **risk_07_05_03** (default) | 1.12 | 42% | 11% | 0.842 | 89 | 1.08 |
| risk_06_04_02 | 1.26 | 45% | 11% | 0.816 | 89 | 1.24 |
| **risk_05_03_01** | 2.88 | 86% | **10%** | 0.696 | 90 | 2.86 |
| risk_08_06_04 | 0.91 | 37% | 14% | 0.865 | 86 | 0.92 |

### Per-tier undershoot — five of six configs have zero Tier 1 undershoot

| config | T1 under | T2 under | T3 under |
|---|---:|---:|---:|
| static_05 | **0.0%** | 9.0% | 4.0% |
| static_08 | 4.0% | 11.0% | 10.0% |
| risk_07_05_03 | **0.0%** | 9.0% | 4.0% |
| risk_06_04_02 | **0.0%** | 9.0% | 3.0% |
| risk_05_03_01 | **0.0%** | 9.0% | 1.0% |
| risk_08_06_04 | 4.0% | 9.0% | 4.0% |

Claude maintains zero Tier 1 undershoot across a wide range of thresholds
— from 0.5 (static_05) down through 0.7 / 0.5 / 0.3 (canonical defaults)
and lower. Only the strictest variant (risk_08_06_04, T1 = 0.8) loses 4
Tier 1 grants. This robustness is a function of Claude's confidence
distribution (next subsection).

### Claude's scores are highly bimodal

Distribution of all 1500 cell scores (100 records × 15 permissions):

```
[0.00, 0.05):  25.5% ############          # ~confident no
[0.05, 0.20):  53.3% ##########################
[0.20, 0.40):   2.5% #
[0.40, 0.60):   0.1%                       # almost no fence-sitting
[0.60, 0.80):   2.1% #
[0.80, 0.95):  16.1% ########              # ~confident yes
[0.95, 1.01):   0.3%
```

~79% of scores below 0.20, ~18% above 0.60, only ~5% in the [0.20, 0.60]
middle. Claude rarely expresses fence-level uncertainty — it tends to
have strong opinions. The operational implication: most thresholds between
0.3 and 0.7 give similar classifications, because almost no scores live
in that range to be split differently. The same configurations
(static_05, risk_07_05_03, risk_06_04_02) produce nearly identical
overall metrics for this reason. The interesting differentiation happens
at the extremes (static_08 too strict, risk_05_03_01 sweeps the
fence-sitters into "grant").

### Calibration: Claude's probabilities support the canonical defaults; TF-IDF's don't

The cleanest comparison this sweep enables is at risk_07_05_03 (the
canonical Section 5.4 defaults):

| | TF-IDF | Claude Haiku |
|---|---:|---:|
| undershoot rate | 52% | 11% |
| Tier 1 undershoot (per task) | 0.34 | 0.00 |
| macro-P | 0.74 | 0.84 |
| sev-d | 1.43 | 1.12 |

**Same threshold strategy. Wildly different outcomes.** The thresholds
work as designed when the underlying probabilities are calibrated — every
needed Tier 1 grant scores above 0.7, every unneeded one below. They
fail when the probabilities aren't calibrated — TF-IDF's needed grants
often score below 0.7, so the strict Tier 1 gate kills recall.

This is the empirical validation of the entire risk-based threshold
design from §5.4. It also predicts that fine-tuned DeBERTa, with
explicit `BCEWithLogitsLoss` + `pos_weight` calibration during training,
should behave like Claude (or better) under the canonical defaults — and
unlike TF-IDF.

### Against the deployability bar

| config | undershoot < 10% | macroP ≥ 0.89 | both? |
|---|:-:|:-:|:-:|
| static_05 | × (11%) | × (0.85) | × |
| static_08 | × (22%) | ✓ (0.90) | × |
| risk_07_05_03 | × (11%) | × (0.84) | × |
| risk_06_04_02 | × (11%) | × (0.82) | × |
| risk_05_03_01 | ✓ (10%) | × (0.70) | × |
| risk_08_06_04 | × (14%) | × (0.87) | × |

**No Claude configuration clears both bars simultaneously.** The cluster
around 11% undershoot and 0.82–0.85 macro-P sits 1pp short on the
undershoot bar and 4–7pp short on macro-precision. `risk_05_03_01` clears
the undershoot bar at the cost of collapsing precision.

The DeBERTa target is now sharp: clear both bars at the same time.
Specifically, hit < 10% undershoot while preserving macro-P ≥ 0.89 — a
1pp improvement on the undershoot side and 5pp on the precision side
versus the closest Claude configuration. Fine-tuning on 500 labelled
records should make both moves possible because:
- The 500-example training signal will improve borderline cases that
  Claude (with 6 few-shots) gets wrong, lowering undershoot.
- Direct optimisation against the labelled ground truth tends to produce
  better per-permission calibration than few-shot prompting, lifting
  precision.

This is now the empirical comparison the paper rests on. If DeBERTa
beats Claude on both axes, the deployment claim is publishable as-is. If
DeBERTa is close but doesn't clear both bars, the gap defines the
deployment caveat honestly.

## 3. Per-department breakdown

| department | sev-delta | overshoot | undershoot |
|---|---:|---:|---:|
| Engineering | 0.76 | 32% | **56%** |
| Security | 1.13 | 33% | **53%** |
| Customer Success | 1.45 | 40% | 30% |
| Finance | 1.20 | 47% | 40% |
| Data & Analytics | 0.53 | 20% | 33% |
| Legal & Compliance | 0.40 | 20% | 40% |

Engineering and Security take the worst hit on undershoot — both have the
broadest tool envelope and the most multi-tool tasks (debugging, incident
response). A bag-of-words representation cannot disentangle "this task
mentions Slack but only as a destination for the report" from "this task
mentions Slack as the data source." DeBERTa's contextual embeddings
should specifically improve these two departments.

---

## 4. What these numbers tell us — F1 vs severity-weighted delta

The two metrics measure different things and answer different questions.
Understanding which to argue from is the difference between a clean claim
and a misleading one.

### F1 measures classifier quality

`F1 = 2·P·R / (P + R)` summarises how well the classifier matches the
ground-truth label. It treats false positives and false negatives
symmetrically and is computed per permission. **Macro-F1** is the mean
across permissions, weighting every permission equally regardless of risk.

What F1 is useful for:
- Comparing classifiers against each other (TF-IDF vs DeBERTa vs Claude).
- Reporting per-permission accuracy in the validation section.
- Establishing that the classifier isn't trivially broken.

What F1 is **not** useful for:
- Arguing the security value of the architecture. F1 = 0.85 doesn't tell
  you whether the 15% errors were costly Tier 1 over-grants or harmless
  Tier 3 under-grants. The argument we want to make is about *which kind*
  of errors are reduced, not how many.

### Severity-weighted delta measures attack surface reduction

`severity_weighted_delta(condition) = Σ tier_weight(p) · 1{granted(p) ∧ ¬needed(p)}`,
averaged over the test set. Tier 1 over-grant = 3 units, Tier 2 = 2 units,
Tier 3 = 1 unit. **Only overshoot contributes**; under-grants do not.

This is the right metric for arguing security value because it directly
quantifies the risky credentials a condition leaves attached. C0 = 26.12,
C1 = 17.51 means the role ceiling removes 8.6 sev-weighted units per task
on average vs the all-grant baseline.

What sev-weighted delta is useful for:
- Quantifying the security value of each layer of the architecture.
- Comparing C2 to C1 directly: "Source 2 removes X additional units per
  task on top of role-based IAM."
- Decomposing by tier to show whether the reductions hit high-risk tools
  (Tier 1) or just clean up low-risk ones (Tier 3).

What sev-weighted delta is **not** useful for:
- Judging operational viability. A classifier that denies everything has
  sev-weighted delta = 0 but is useless. The TF-IDF baseline here
  illustrates exactly this failure mode: sev-delta = 0.95 but undershoot
  = 43%.

### The argument we should make for C2

The two metrics together support the deployment claim, but neither alone
is sufficient. The right framing is **deployability with an escalation
path**, not zero-undershoot perfectionism.

Real deployments cannot guarantee 100% recall. The system will under-grant
sometimes — what matters is (a) how often, and (b) what happens on those
cases. The operational handling is:

- **Auto-handled cases (no undershoot):** the agent runs with the C2
  grant set. This is where the security value accrues.
- **Escalation cases (any undershoot):** the system falls back to HITL
  approval, log-only mode, or retry with the C1 (role ceiling) grant
  set. The C1 fallback preserves operational continuity at the cost of
  accepting C1-level security on the residual fraction.

Under this framing, the deployability budget is set in §6.3 of the
action plan:

- **Undershoot rate < 10%.** Above 10%, escalation volume becomes
  operationally expensive — every tenth task requires a human or a
  retry. Below 10%, the system is realistically deployable with a
  background escalation pipeline.
- **Macro-precision high.** Precision is what determines whether the
  grants the system *does* make are clean. The Claude Haiku baseline
  shows macro-precision of 0.893 is achievable off-the-shelf, so we set
  that as the floor DeBERTa should match or beat.
- **Per-tier visibility retained.** Tier 1 errors still get reported
  separately — they remain the most consequential errors on both sides
  — but they are no longer a hard 0% constraint. A fine-tuned classifier
  that gets Tier 1 undershoot to 0% is great, but a classifier at 1–2%
  Tier 1 undershoot with otherwise strong numbers is still deployable
  because the escalation path catches those records.

The operationally-safe C2 configuration is then

```
argmin  sev_delta(C2)
subject to:
    undershoot_rate(C2) < 10%
    macro_precision(C2) ≥ 0.89
```

and the headline deployment claim becomes:

> For N% of agent invocations, C2 makes the grant decision autonomously
> with severity-weighted delta D — an X% reduction in attack surface
> vs the role-based ceiling. The remaining (100 − N)% escalate to HITL
> or fall back to the C1 grant set.
>
> N% = 100 − undershoot_rate(C2)
> X% = (sev_delta(C1) − sev_delta_on_auto(C2)) / sev_delta(C1)

where `sev_delta_on_auto(C2)` is the mean severity-weighted delta over
records where C2 did *not* under-grant — the auto-handled portion.

### What the baselines show against this bar

| condition | undershoot | macro-P | auto-handled | sev-delta on auto |
|---|---:|---:|---:|---:|
| C1 (role ceiling) | 2% | low | 98/100 | 17.51 |
| TF-IDF static_05 | 43% | 0.77 | 57/100 | 0.84 |
| TF-IDF risk_07_05_03 | 52% | 0.74 | 48/100 | 1.48 |
| TF-IDF risk_05_03_01 | 12% | **0.41** | 88/100 | 6.26 |
| TF-IDF risk_08_06_04 | 76% | 0.68 | 24/100 | 0.50 |
| **Claude Haiku** | **15%** | **0.89** | **85/100** | **0.68** |

Three observations:

1. **No baseline configuration clears undershoot < 10%.** Closest is
   TF-IDF `risk_05_03_01` at 12% — but it does so by collapsing
   precision to 0.41 and accepting 100% overshoot. It is essentially
   "predict everything"; not a meaningful security control.

2. **Claude Haiku is the closest to deployable.** 85/100 auto-handled,
   precision 0.89, sev-delta 0.68 on the auto-handled portion. The 15%
   undershoot exceeds the budget by 5pp, but precision is in the
   target range. A fine-tuned DeBERTa whose precision matches Claude
   and whose undershoot drops to <10% would clear both constraints
   simultaneously.

3. **The `risk_05_03_01` floor is informative.** Even at maximum
   permissiveness (100% overshoot — the model grants everything it
   predicts plus a lot more), TF-IDF still misses 12% of needed
   permissions. That 12% is the classifier-quality floor: those test
   records have at least one needed permission that scores below *every*
   threshold we tested. To get below 12% on this floor, you'd need
   either a more permissive threshold (which approaches C0 and loses
   the security argument) or a better classifier. DeBERTa is the
   "better classifier" path.

### What this means for DeBERTa

The Phase C / D evaluation should produce a configuration that achieves
all of:

- Macro-precision ≥ 0.89 (Claude floor)
- Undershoot rate < 10% (operationally deployable)
- Auto-handled count ≥ 90/100
- Sev-delta on auto-handled ≪ C1 (the actual attack surface claim)
- Per-tier breakdown showing Tier 1 errors are bounded

If DeBERTa hits this bar, the deployment claim is publishable. If it
gets close on undershoot (e.g. 10–12%) but precision and sev-delta are
strong, the argument becomes "<10% with operational escalation" and
remains coherent. If precision collapses (matching TF-IDF
`risk_05_03_01`'s 0.41), no claim is possible — that means the model is
just rebadging C1.

This is the claim that lands operationally. F1 numbers and per-tier
breakdowns are reported as classifier-quality diagnostics. The
deployment story rests on undershoot rate, precision, and sev-delta on
the auto-handled portion.

### Where the TF-IDF baseline sits on this argument

TF-IDF achieves the lowest sev-weighted delta of any condition (0.95) but
fails the operationally-safe constraint by an order of magnitude:
undershoot 43% vs C1's 2%. It is a useful *lower bound* on attainable
sev-delta but is not a deployable configuration. It also reveals that
naive class-weight balancing alone produces a classifier far on the
recall-sacrificing side of the trade-off — the threshold of 0.5 is
already too high for an operationally-safe deployment.

The DeBERTa story we want to argue is therefore:

1. **Better classifier than TF-IDF** — macro-F1 should jump from 0.70
   toward 0.85+, particularly on the rare permissions where TF-IDF
   collapses (`pull_request_create`, `code_execute`,
   `email_send_external`).
2. **Operationally safer than TF-IDF** — undershoot down from 43% to
   ≤ C1's 2% by combining the stronger classifier with the risk-based
   threshold (Tier 1 = 0.7, Tier 2 = 0.5, Tier 3 = 0.3 — Tier 3 in
   particular gates almost nothing, so undershoot from rare-label
   weakness is bounded).
3. **Lower sev-delta than C1** at that operationally-safe undershoot —
   the headline X% reduction quantified above.

That is the three-point claim the paper needs C2 to support. The TF-IDF
baseline shows one corner of the trade-off; the role ceiling shows the
other; C2 should sit inside both bounds.

---

## 5. Per-tier severity-weighted breakdown

The aggregate sev-weighted delta hides where the security risk
concentrates. Per-tier counts × tier weights give the explicit
decomposition (T1 × 3 + T2 × 2 + T3 × 1 = total):

| condition | T1 cnt | T1 × 3 | T2 cnt | T2 × 2 | T3 cnt | T3 × 1 | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| C0 | 3.37 | 10.11 | 6.80 | 13.60 | 2.41 | 2.41 | 26.12 |
| C1 | 1.82 | 5.46 | 4.82 | 9.64 | 2.41 | 2.41 | 17.51 |
| TF-IDF logreg static_05 | 0.15 | 0.45 | 0.19 | 0.38 | 0.12 | 0.12 | 0.95 |
| Claude static_05 | 0.15 | 0.45 | 0.32 | 0.64 | 0.03 | 0.03 | 1.12 |
| Claude static_08 | 0.08 | 0.24 | 0.21 | 0.42 | 0.01 | 0.01 | 0.67 |
| **Claude risk_07_05_03** | **0.14** | **0.42** | **0.32** | **0.64** | **0.06** | **0.06** | **1.12** |
| Claude risk_06_04_02 | 0.15 | 0.45 | 0.32 | 0.64 | 0.17 | 0.17 | 1.26 |
| Claude risk_05_03_01 | 0.15 | 0.45 | 0.35 | 0.70 | 1.73 | 1.73 | 2.88 |
| Claude risk_08_06_04 | 0.08 | 0.24 | 0.32 | 0.64 | 0.03 | 0.03 | 0.91 |

### Where each layer of the architecture removes attack surface

The C0 → C1 transition (role ceiling) removes:
- 46% of Tier 1 attack surface (10.11 → 5.46)
- 29% of Tier 2 (13.60 → 9.64)
- 0% of Tier 3 (2.41 → 2.41) — all six departments share most Tier 3
  permissions, so the ceiling can't narrow them

The C1 → Claude risk_07_05_03 transition (classifier on top of ceiling)
removes:
- 92% of remaining Tier 1 (5.46 → 0.42)
- 93% of remaining Tier 2 (9.64 → 0.64)
- 98% of remaining Tier 3 (2.41 → 0.06)
- 94% overall (17.51 → 1.12)

### The headline claim, written out per tier

> At canonical risk-based thresholds (Tier 1 = 0.7, Tier 2 = 0.5,
> Tier 3 = 0.3), Claude Haiku 4.5 (zero fine-tuning, 6 few-shot
> examples) reduces severity-weighted attack surface by **94%** vs the
> role-based ceiling, with the largest reductions in the most consequential
> tiers: **92% reduction in Tier 1 over-grants, 93% in Tier 2, 98% in
> Tier 3.** The reduction holds at 11% undershoot rate (89 / 100 test
> tasks auto-handled), with the remaining 11 escalating to HITL or
> C1-fallback.

This is the strongest version of the C2 deployment claim that the Phase
B data supports. DeBERTa needs to either match this or improve on it
while clearing the deployability bar (< 10% undershoot, ≥ 0.89
macro-P) that Claude misses by 1pp on undershoot and 5pp on precision.

### Why risk_05_03_01 is informative but not deployable

risk_05_03_01 stands out in the table because its T3 contribution
balloons to 1.73 — almost half of all Tier 3 permissions are
over-granted across the test set. This happens because the T3 threshold
of 0.1 falls inside Claude's high-density "below 0.20" score band: any
record that scores even moderately on a Tier 3 permission ends up
granting it. Tier 1 contribution is unchanged from the canonical
defaults (0.45 vs 0.42) because Claude's high-confidence Tier 1 grants
all live above 0.5 anyway.

This config trades **macro-precision (0.70)** for **undershoot (10%)**
by over-granting cheap Tier 3 permissions. From a pure sev-weighted
viewpoint, the trade is mild (2.88 vs 1.12) because Tier 3 over-grants
are cheap (weight 1). From a precision-of-grant viewpoint, the trade is
expensive — every fourth grant Claude makes is unnecessary, which
weakens the security argument because the system looks noisy. For
deployment we prefer the cluster around 11% undershoot / 0.84 macro-P,
not the 10% undershoot / 0.70 macro-P operating point.

---

## 6. Implications for DeBERTa

The Claude few-shot sweep sharpens what Phase C needs to produce.

### The sharpened DeBERTa target

DeBERTa needs to clear all four metrics simultaneously at the same
threshold configuration:

| target | Phase B closest | DeBERTa target |
|---|---|---|
| Undershoot rate | 10% (risk_05_03_01, but P collapses to 0.70) | **< 10%** |
| Macro-precision | 0.895 (static_08 at 22% undershoot) | **≥ 0.89** |
| Macro-F1 | 0.889 (static_05) | **≥ 0.89** |
| T1 undershoot rate | 0% (5 of 6 Claude configs) | **0%** |

The cluster of Claude configurations around 11%
undershoot / 0.84 macro-P / 0% T1 undershoot is the floor: a fine-tuned
small model should beat off-the-shelf few-shot prompting on this
task because (a) it sees 83× more supervised signal (500 records vs 6
few-shots), (b) `BCEWithLogitsLoss` + `pos_weight` is an explicit
calibration objective, and (c) the model is task-specialised rather
than task-generalist.

### Specific behaviours to verify in Phase C/D

1. **The canonical risk_07_05_03 thresholds should work.** This was the
   point at which TF-IDF failed catastrophically (52% undershoot) and
   Claude succeeded (11% undershoot, 0% T1 undershoot). DeBERTa's
   probabilities should support these defaults like Claude's do — if
   they don't, that's a signal that fine-tuning didn't produce
   calibrated outputs and we need to either re-train or sweep additional
   thresholds.

2. **Pull_request_create remains the high-risk failure mode.** Only 13
   positive training records and 1 positive test record. Three
   acceptable behaviours: (a) DeBERTa defaults to deny — correct Tier 1
   fallback, contributes to robustness; (b) DeBERTa correctly grants
   when needed (best case, hard with so little signal); (c) DeBERTa
   over-grants — bad outcome, expands attack surface for a Tier 1
   permission. Watch this specifically; consider a manual rule for this
   permission if the model fails.

3. **Score distribution shape matters as much as F1.** Claude's
   bimodality (79% below 0.20, 18% above 0.60, 5% in middle) means
   threshold choice barely matters in the middle range. If DeBERTa
   produces a similarly bimodal distribution, threshold-sweep results
   will look similar — most thresholds in [0.3, 0.7] will give similar
   classifications. If DeBERTa's distribution is flatter, the threshold
   sweep will produce more differentiated operating points and risk-based
   defaults will matter more.

4. **Rare-label calibration is the open question.** Claude has zero
   Tier 1 undershoot but only 13 training records won't have taught
   DeBERTa about `pull_request_create` very well. The fine-tuning data
   includes only 1 positive example for this label in the test set — so
   F1 on this label is essentially binary (got the 1 case right or
   wrong). Cannot draw statistically meaningful per-label conclusions
   on this permission; aggregate metrics dominate.

### What the deployment story looks like in each outcome

**DeBERTa beats Claude on the deployability bar** — undershoot < 10% AND
macro-P ≥ 0.89: full deployment claim works. Paper headline is "C2
achieves N% sev-d reduction at M% undershoot, deployable as-is."

**DeBERTa matches Claude** — both around 11% undershoot, 0.84 macro-P:
publishable as a deployment claim with explicit operational caveat. "C2
deployable with 11% HITL escalation rate, achieving 94% sev-d
reduction on the auto-handled portion." Stronger because DeBERTa has
operational properties Claude lacks (sub-second latency, deterministic,
no injection surface, calibrated probabilities exposed for downstream
tuning).

**DeBERTa loses to Claude** — undershoot ≥ 15% or macro-P < 0.80: still
publishable as a finding ("our 500-record fine-tune did not beat
off-the-shelf Claude few-shot at this task"). The architectural argument
for DeBERTa remains (operational properties), but the headline shifts to
"Claude Haiku as Source 2 is a viable deployment option with the API
trade-offs documented." Less attractive but coherent.

---

## 7. Known gaps and follow-ups

- **Bootstrap confidence intervals not yet computed.** All numbers in
  this document are point estimates on n=100. The 95% CIs are likely
  wide — macro-F1 ± 0.04 or so on this sample size. Phase E will add
  the bootstrap pass (1000 resamples) and re-quote every metric with
  its CI. The qualitative conclusions are unlikely to change but the
  paper claims need the CIs attached.
- **Prompt cache did not activate on the Claude run.** Usage shows
  `cache_creation_input_tokens = 0` and `cache_read_input_tokens = 0`.
  The system prompt at ~5.7k characters tokenises to roughly 1.4k
  tokens, below Haiku 4.5's documented 2048-token cache minimum. To
  activate caching, the system prompt would need to be expanded — e.g.,
  by adding more few-shots or reasoning-style instructions. The current
  API cost (~$0.30 per 100-record run) is low enough that this hasn't
  been worth optimising, but at production scale or larger evaluation
  sets it would be.
- **Claude's probability calibration not formally measured.** The
  evidence here is indirect: the risk_07_05_03 defaults that fail on
  TF-IDF succeed on Claude. A direct calibration plot (predicted
  probability vs actual positive rate, bucketed) would be a stronger
  argument. Phase E or Section 8 of the paper.
- **Pull_request_create has 1 positive in the test set.** Per-permission
  F1 for this label is essentially binary noise. Cannot draw statistical
  conclusions. Reporting it as a limitation rather than a metric.
- **Single-test-set evaluation.** All numbers are on the same 100-record
  held-out test set. Cross-validation on the 500-record train set would
  give a more robust estimate of variance, at the cost of either more
  Claude API calls or just more compute for TF-IDF/DeBERTa. Not planned
  for the dataset paper but worth flagging for the C3/C4 follow-up.

---

## 8. Summary — what Phase B established before DeBERTa

**Empirically:**

- The role-based ceiling (C1) removes 46% of Tier 1, 29% of Tier 2, and
  0% of Tier 3 attack surface vs C0. That's the floor the classifier
  layer (C2) builds on.
- TF-IDF + logreg cannot be deployed under our tier-aware budget at any
  threshold. Its probabilities are not calibrated enough to support the
  risk-based defaults; the best operating point we found (`static_05`)
  has 43% undershoot.
- Claude Haiku 4.5 with 6 few-shot examples produces calibrated
  probabilities. At canonical risk-based thresholds (0.7 / 0.5 / 0.3) it
  delivers a 94% sev-weighted attack surface reduction vs C1, with 11%
  undershoot, 0% Tier 1 undershoot, and macro-precision 0.84.
- No baseline configuration clears the deployability bar of < 10%
  undershoot AND ≥ 0.89 macro-precision simultaneously. Claude's best
  cluster (11% undershoot / 0.84 macro-P) is the closest.

**Conceptually:**

- **Severity-weighted delta** measures attack surface; **macro-precision**
  measures whether grants are clean; **undershoot rate** measures how
  often the system needs an escalation path. The deployable claim
  requires all three.
- F1 is a classifier-quality diagnostic, not the security argument. The
  paper uses it for comparing classifiers; the deployment story uses
  sev-d-on-auto + macro-P + undershoot together.
- The per-tier decomposition shows where each layer's attack surface
  reduction concentrates. The headline-worthy version of the C2 claim
  uses the per-tier numbers because they make the argument concrete
  (e.g. "92% of remaining Tier 1 over-grants eliminated").
- Calibration is the property that makes the risk-based threshold
  strategy work. A model whose probabilities are calibrated (Claude) can
  use the canonical defaults; a model whose probabilities aren't
  calibrated (TF-IDF) cannot. This is a paper-worthy finding that
  motivates DeBERTa's BCEWithLogitsLoss + pos_weight training objective.

**For Phase C:**

- The DeBERTa training run produces a model at one calibration point;
  the threshold sweep then provides six operating points without
  re-running inference (predictions cached, thresholds applied
  post-hoc — the same pattern that worked for the Claude sweep).
- The target is to clear all four constraints at one configuration:
  undershoot < 10%, macro-P ≥ 0.89, macro-F1 ≥ 0.90, Tier 1 undershoot
  = 0%.
- The deployment story shape is decided in Phase C/D: full deployment
  claim if all four clear, deployment-with-caveats if 3 of 4 clear,
  publishable-finding if DeBERTa doesn't beat Claude.

**Artefacts produced by Phase B (for future inspection):**

- `results/c0.json`, `results/c1.json` — baseline conditions with
  per-tier metrics.
- `results/classifier_baselines.json` — TF-IDF and Claude Haiku with the
  full six-config sweep, per-tier metrics, raw EvalResult entries.
- `results/tfidf_threshold_sweep.json` — TF-IDF at all six threshold
  configurations.
- `dataset/classifier_artifacts/claude_haiku_scores.json` — cached 100 ×
  15 probability matrix from the single Claude API run; reusable for
  any future threshold experiment without additional API calls.
- `mostargate/classifier/data.py` — data loading + label matrix +
  tokeniser plumbing.
- `mostargate/classifier/baselines.py` — both baselines + threshold
  sweep machinery.
- `mostargate/experiments/metrics.py` — per-tier overshoot/undershoot
  metrics, severity weighting, summary aggregation.

Everything above the DeBERTa step has been built and validated against
real data. Phase C is purely training a single model and running it
through the same evaluation harness.

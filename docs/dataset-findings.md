# Paper Update Brief — MostarGate

This document is a briefing for an LLM that will edit `mostargate-paper.md`.
It describes what empirical work has been done since the paper was drafted, what the
results were, and exactly what to change in the paper — including the original text to
find, what to replace it with, and the reasoning behind each change.

Read this document fully before touching the paper. Each section below targets a
specific location in the paper, quotes the current text, and states the replacement.

---

## Context: what has been done

The paper was drafted as a research proposal with planned methodology. Since drafting,
the dataset has been generated (600 records) and a 60-record human validation sample
has been completed by the primary researcher (Burak Noyan). The human labels were then
compared against the LLM labels from the dataset using an automated metrics pipeline.

**Key facts about what was actually done vs. what the paper planned:**

| Item | Paper planned | What actually happened |
|---|---|---|
| Dataset size | 500 records | 600 records generated |
| Human validation sample | 10% = 50 records | 60 records (10% of 600) |
| Number of human labellers | Two independent experts | One (the primary researcher) |
| Validation timing | Random 10% of training set | Random sample from training set |
| Review of disagreements | Not described | Interactive per-permission review with recorded resolutions |

---

## Empirical results from the human validation

Both pre-review and post-review metrics are complete. The pre-review metrics treat
human labels as ground truth. The post-review metrics use adjudicated labels — each
of the 20 permission disagreements was resolved by the primary researcher as
llm_correct, human_correct, or ambiguous. The post-review metrics are the paper's
primary claim; pre-review is retained as the conservative baseline.

### Permission agreement — pre-review (human as reference)

Computed within department capability ceilings only. Tools structurally unavailable to
a department are excluded from all calculations.

| Metric | Value |
|---|---|
| Records evaluated | 60 |
| Exact match rate | 68.3% (41/60) |
| Hamming accuracy | 97.1% |
| Macro F1 | 0.920 |
| Cohen's kappa | 0.917 |
| Overshoot rate | 1.3% (LLM grants, human denied) |
| Undershoot rate | 8.1% (LLM denies, human granted) |
| Severity-weighted overshoot | 15.00 |

### Permission agreement — post-review (adjudicated ground truth)

| Metric | Value |
|---|---|
| Exact match rate | 85.0% (51/60) |
| Hamming accuracy | 98.8% |
| Macro F1 | 0.966 |
| Cohen's kappa | 0.967 |
| Overshoot rate | 0.2% |
| Undershoot rate | 4.4% |
| Severity-weighted overshoot | 2.00 |

### Disagreement resolution breakdown

| | Count | Share of 20 |
|---|---|---|
| LLM correct (human made a labelling error) | 10 | 50% |
| Human correct (LLM made a prediction error) | 8 | 40% |
| Ambiguous (genuinely unclear) | 2 | 10% |

### Sensitivity resolution breakdown (for reference only — excluded from all metrics)

| | Count | Share of 24 |
|---|---|---|
| Human correct | 17 | 70.8% |
| LLM correct | 6 | 25.0% |
| Ambiguous | 1 | 4.2% |

### Sensitivity confusion matrix (human vs LLM, rows = human, cols = LLM)

```
              LLM_LOW  LLM_MED  LLM_HIGH
Human_LOW          1        2        1
Human_MEDIUM       4       11        7
Human_HIGH         1        9       24
```

Agreement rate: 60.0% (36/60). Excluded from all metric computations per the
sensitivity finding below.

---

## Key findings and their interpretation

### Finding 1: The LLM's true accuracy is higher than the naive pre-review numbers suggest

The pre-review kappa of 0.917 already clears the 0.8 threshold, but it is deflated by
human labelling errors. Once disagreements are adjudicated, kappa rises to **0.967** —
near-perfect agreement. The gap between 0.917 and 0.967 quantifies the impact of
human labelling errors on the naive estimate.

The 50/40/10 split (LLM correct / human correct / ambiguous) is the key figure: when
the human and LLM disagreed on a permission, they were wrong at roughly equal rates.
This means the human labels are not a clean ground truth — they contain systematic
errors. The adjudicated post-review metrics are a substantially more accurate measure
of classifier performance.

### Finding 2: The LLM almost never over-grants high-risk tools

Severity-weighted overshoot collapses from **15.00 pre-review to 2.00 post-review**
— an 86.7% reduction. The 15.00 figure was almost entirely human labelling errors:
cases where the human denied a high-tier tool but the LLM correctly granted it. The
true over-granting of high-risk tools is near-zero (severity-weighted overshoot: 2.00,
raw overshoot rate: 0.2%).

This is the most important finding for the paper's security claim. The classifier
essentially never grants a Tier 1 tool (database_read, email_send_external,
http_request, pull_request_create) incorrectly.

### Finding 3: The remaining genuine error is conservative undershoot

Post-review undershoot is **4.4%**: the LLM denies 4.4% of permissions that should
have been granted. This is the classifier's actual failure mode. For a security control,
this is the preferred direction — a missed grant causes task inconvenience; an incorrect
grant expands the attack surface.

### Finding 4: Exact match rate improves substantially once human errors are removed

Pre-review exact match: 68.3% (41/60). Post-review: 85.0% (51/60). The 16.7
percentage point gap represents the 10 records where the human made at least one
labelling error. At the individual permission level, the improvement is from 97.1% to
98.8% hamming accuracy.

### Finding 5: Sensitivity is too subjective to use — and the resolution data confirms it

Of 24 sensitivity disagreements, the human was correct 17 times (70.8%) and the LLM
6 times (25%). The LLM has a genuine weakness in sensitivity classification, in
addition to the definitional divergence with the human. Both reasons independently
support the decision to exclude sensitivity from all calculations. Sensitivity labels
are retained as descriptive metadata only.

---

## Paper changes — section by section

### CHANGE 1 — §6.2 Step 4: Human validation description (line ~731)

**Current text in paper:**
> Two independent expert labellers validate a random 10% sample (50 records).
> Cohen's kappa is computed. Where agreement is below 0.8, the ambiguous prompts
> are reviewed and the disagreement is documented as a genuine labelling difficulty
> — which is itself a finding about where the boundary between sensitivity classes
> is unclear.
>
> A 10% sample is sufficient at this dataset scale (500 records) to detect systematic
> labelling errors and compute a reliable kappa estimate. The reduction from 20% is a
> practical tradeoff that does not meaningfully weaken the validity argument.

**Replace with:**
> A single expert labeller (the primary researcher) validated a random 10% sample
> (60 records from the 600-record dataset). Using a single labeller rather than two
> is a limitation noted in §9 Blind Spot 1 — self-review bias applies because the
> same researcher who produced the dataset labels also reviewed disagreements between
> those labels and the LLM's predictions.
>
> Cohen's kappa between human and LLM labels was **0.917** (almost perfect agreement).
> The 0.8 threshold was comfortably met; no profiles required regeneration.
>
> Sensitivity agreement was measured separately and was substantially lower at **60.0%**,
> primarily at the MEDIUM/HIGH boundary. This is treated as a finding about definitional
> divergence rather than a labelling failure — see §8 Results.

---

### CHANGE 2 — §6.4 Running the pipeline at scale (line ~816)

**Current text:**
> Run each profile 5 times at temperature 0.9 → 600 total prompts. Split: 500 training
> / 100 test (held out, never seen during training). Human-validate 10% of the training
> set (50 records). Compute Cohen's kappa. If below 0.8 for any profile, regenerate.

**Replace with:**
> Run each profile 5 times at temperature 0.9 → 600 total prompts. Split: 500 training
> / 100 test (held out, never seen during training). Human-validate 10% of the full
> dataset (60 records). Compute Cohen's kappa between human and LLM labels on
> permission decisions. If below 0.8 for any permission tier, regenerate.
> Sensitivity agreement is tracked separately (see §8).

---

### CHANGE 3 — §7.2 Synthetic Dataset Generation: Two-Pass Pipeline (line ~848)

**Current text:**
> **Human validation:** 20% random sample validated by two expert labellers.
> Cohen's kappa reported. Disagreements documented as labelling difficulty findings.

**Replace with:**
> **Human validation:** 10% random sample (60 records) validated by one expert
> labeller. Cohen's kappa reported for permission decisions (κ = 0.917).
> Sensitivity agreement reported separately (60.0%). Per-permission disagreements
> resolved through an interactive review pass; resolution decisions (llm_correct /
> human_correct / ambiguous) are recorded in `disagreements.json` and released with
> the dataset.

---

### CHANGE 4 — §9 Blind Spot 1: Ground truth subjectivity (line ~971)

**Current text:**
> **Problem:** Human labellers may disagree on edge cases.
>
> **Mitigation:** Document Cohen's kappa. Exclude tasks with irresolvable disagreement.
> Report kappa alongside results.

**Replace with:**
> **Problem:** Human labels are produced by a single labeller (the primary researcher),
> not two independent experts as originally planned. This creates two compounding risks:
> (a) systematic blind spots that a second independent labeller would have caught, and
> (b) self-review bias, since the same researcher who produced the labels also
> adjudicated disagreements between those labels and the LLM's predictions. A researcher
> resolving their own prior decisions may unconsciously favour confirmation of the
> original label.
>
> **Mitigation:** Cohen's kappa (κ = 0.917) indicates that even under self-review
> conditions, permission agreement is high enough to proceed. All disagreement
> resolutions and their notes are released in `disagreements.json` so external reviewers
> can audit the adjudication decisions. Sensitivity disagreements are reported separately
> and not collapsed into the permission kappa — the 60.0% sensitivity agreement is
> disclosed as a finding about definitional divergence, not treated as noise.
>
> The most significant limitation is the absence of a second human labeller. This is
> noted as future work: validating the dataset with an independent expert and computing
> true inter-rater kappa would substantially strengthen the labelling validity claim.

---

### CHANGE 5 — §8 Results: add human validation results sub-section

The paper does not yet have a §8 Results section. When written, it must include the
following sub-section. Use the post-review metrics as the primary figures; show
pre-review in a comparison table as the conservative baseline.

**Add this sub-section to §8:**

> ### 8.X Human Validation Results
>
> A 60-record sample was validated by the primary researcher and compared against the
> LLM's permission labels. Each of the 20 permission disagreements was then adjudicated
> (llm_correct / human_correct / ambiguous) to produce a resolved ground truth.
> Two metric sets are reported: pre-review (human labels as reference) and post-review
> (adjudicated labels as ground truth, ambiguous cases excluded).
>
> #### Permission Metrics
>
> | Metric | Pre-review | Post-review |
> |---|---|---|
> | Exact match rate | 68.3% (41/60) | 85.0% (51/60) |
> | Hamming accuracy | 97.1% | 98.8% |
> | Macro F1 | 0.920 | 0.966 |
> | Cohen's kappa | 0.917 | 0.967 |
> | Overshoot rate | 1.3% | 0.2% |
> | Undershoot rate | 8.1% | 4.4% |
> | Severity-weighted overshoot | 15.00 | 2.00 |
>
> **Primary finding:** Post-review kappa of **0.967** (near-perfect agreement) is the
> paper's headline accuracy figure. The pre-review kappa of 0.917 is retained as the
> conservative baseline — it represents accuracy assuming human labels are always
> correct, which is a stricter standard than the true ground truth.
>
> The severity-weighted overshoot drop from 15.00 to 2.00 (86.7% reduction) is the
> most security-relevant finding. The pre-review figure of 15.00 was almost entirely
> human labelling errors — cases where the human incorrectly denied a high-tier tool
> that the LLM correctly granted. The LLM's true over-granting of high-risk tools is
> near-zero.
>
> The remaining genuine error is conservative undershoot at 4.4%: the LLM denies
> permissions that should have been granted. For a security control, this is the
> preferred failure mode — a missed grant causes task inconvenience, while an incorrect
> grant expands the attack surface.
>
> #### Disagreement Resolution
>
> Of the 20 permission disagreements:
>
> | Resolution | Count | Share |
> |---|---|---|
> | LLM correct (human labelling error) | 10 | 50% |
> | Human correct (LLM prediction error) | 8 | 40% |
> | Ambiguous | 2 | 10% |
>
> The 50/40/10 split shows that when disagreements occurred, the human and LLM were
> wrong at roughly equal rates. Human labels are not a clean ground truth: they contain
> systematic labelling errors at a rate comparable to the LLM's prediction errors.
> This is why the adjudicated post-review metrics are the primary claim.
>
> #### Sensitivity (for context only — excluded from all calculations)
>
> Sensitivity agreement rate was 60.0%. Of 24 sensitivity disagreements, the human was
> correct in 70.8% of cases and the LLM in 25%. Both the low agreement rate and the
> LLM's weaker performance on sensitivity (vs. permissions) independently support the
> decision to exclude sensitivity tier from all metric computations. Sensitivity labels
> are retained as descriptive metadata only.

---

### CHANGE 6 — §6.2 Pilot reference: update record counts (line ~579)

**Current text:**
> Before settling on the final dataset design, a pilot experiment was conducted:
> 600 prompts were generated using an initial grouped-permission taxonomy ... and a
> single-pass generation approach. A 10% human validation sample (60 records) was
> analysed independently.

**No change needed here.** The paper already correctly states 60 records in this
section. The inconsistency is in §6.2 Step 4 and §6.4 which say 50 records — those
are fixed by Changes 1 and 2 above.

---

### CHANGE 7 — §10 Implementation Plan timeline (line ~1035)

**Current text:**
> | **Phase 1 — Dataset generation** | Generate 600 prompts, LLM-label, human-validate
> 10% (50 records), build injection stress tests | Weeks 1–4 |

**Replace "50 records" with "60 records":**
> | **Phase 1 — Dataset generation** | Generate 600 prompts, LLM-label, human-validate
> 10% (60 records), build injection stress tests | Weeks 1–4 |

---

### CHANGE 8 — Add methodological note on reasoning field naming

In §6 or in the dataset documentation section, add the following note. Find the most
natural location near the description of the LLM labelling output format.

**Add:**
> **Reasoning fields:** Each labelled record includes a `reasoning` object with two
> sub-fields: `granted` (one sentence per permission that was granted, explaining why
> it is required) and `denied` (one sentence per permission that was denied, explaining
> why it is not required). The `denied` field covers all denied tools and is not
> restricted to high-risk permissions — the LLM provides justification for every denial.
> These reasoning fields are used during the human review pass to allow the reviewer to
> evaluate the LLM's logic for each disagreeing permission decision.

---

### CHANGE 9 — Add methodological note on permission metric scope

Near the description of Cohen's kappa computation in §6.2 or §7, add the following
clarification. This is important for reproducibility.

**Add:**
> **Ceiling-filtered computation:** All permission agreement metrics (kappa, precision,
> recall, F1, overshoot/undershoot rates) are computed within the department capability
> ceiling. A tool that is structurally unavailable to a department — for example,
> `github_read` for Finance — is excluded from all confusion matrix calculations for
> records in that department. Including out-of-ceiling tools would produce trivial true
> negatives (both human and LLM correctly deny them) that inflate agreement metrics
> without reflecting classifier performance on the tools that actually matter.

---

## Findings to preserve exactly as stated

The following findings from the paper's pilot section (lines ~459–473) are empirically
supported and should be kept intact. They describe the taxonomy redesign rationale and
are not contradicted by the validation results.

- "`file_read_standard` was triggered in 7/60 records, but 6 of those 7 also had
  `internal_search`" — keep as-is
- "18/60 records (30%) contained explanatory phrases like 'I'm trying to figure out
  why'" — keep as-is
- "content sensitivity is a property of the data, not the storage location" — keep
  as-is

These were from the pilot that motivated the taxonomy redesign and are already correctly
described in the paper.

---

## Finding: sensitivity estimates are too subjective to use in calculations

**Finding:** The 60% sensitivity agreement rate (compared to 91.7% kappa on permissions)
demonstrates that sensitivity tier assignment (LOW / MEDIUM / HIGH) is highly subjective
and inconsistent between human and LLM labellers. The confusion matrix shows no clean
boundary — disagreements are distributed across all tier combinations, with the MEDIUM
tier being particularly unstable (50% agreement, errors in both directions).

**Decision:** Sensitivity estimates will not be used in any permission classifier
metrics, delta calculations, or experimental results. They are excluded from Cohen's
kappa, F1, overshoot/undershoot rates, and severity-weighted delta computations.

**What sensitivity is used for:** Sensitivity labels are retained in the dataset as
descriptive metadata for qualitative analysis only — for example, observing whether
high-sensitivity prompts tend to cluster in certain departments. They are not treated
as ground truth for any quantitative claim in the paper.

**Paper instruction:** Anywhere the paper implies sensitivity tier is a validated or
reliable label, soften the claim. Remove any methodology that treats sensitivity as
an input to metrics. Add the following note in §8 Results and in §6.2 Step 4:

> "Sensitivity tier labels (LOW / MEDIUM / HIGH) were found to be highly subjective,
> with only 60% agreement between the human validator and the LLM labeller — compared
> to κ = 0.917 on permission decisions. The MEDIUM tier was particularly unstable,
> with agreement of only 50% and errors distributed in both directions. Sensitivity
> labels are therefore excluded from all quantitative metrics and classifier evaluations.
> They are retained in the dataset as descriptive metadata only."

---

## Post-review data — complete

All items are resolved. Summary of final figures for the paper:

| Figure | Value | Where to use |
|---|---|---|
| Pre-review kappa | 0.917 | Conservative baseline in results table |
| Post-review kappa | 0.967 | Primary headline accuracy claim |
| Pre-review overshoot | 1.3% | Results table |
| Post-review overshoot | 0.2% | Results table (primary) |
| Pre-review sev-weighted overshoot | 15.00 | Results table |
| Post-review sev-weighted overshoot | 2.00 | Results table (primary) |
| Undershoot (post-review) | 4.4% | Primary failure mode claim |
| LLM correct / human correct / ambiguous | 10 / 8 / 2 | Resolution breakdown |
| Sensitivity agreement | 60.0% | Noted as context, not used in metrics |

**Kappa confidence intervals still to compute.** At n=60 the 95% CI for kappa is
approximately ±0.05–0.10. For κ = 0.967 this is unlikely to drop below 0.90, which
still represents almost-perfect agreement. Compute and report the exact CI before
final submission using the Fleiss formula: SE(κ) ≈ √(po(1−po) / (n(1−pe)²)).

---

## Charts — placeholders and specifications

Five charts should be added to the paper. Each entry below gives: the section where
the placeholder should appear, what the chart shows, what data to use, and why it
earns its place over a table.

When editing the paper, insert a placeholder at the indicated location in this form:

```
[FIGURE X — placeholder: <chart name>]
Caption: <caption text below>
Data source: <file>
```

---

### Figure 1 — Dataset composition (§6 — Dataset Construction)

**Place after:** the paragraph describing the department allocation and batch structure.

**Chart type:** Two side-by-side horizontal bar charts.
- Left: record count per department, bars sorted by count, coloured by department.
- Right: LLM grant rate per tool (%), bars sorted by tier and then rate within tier,
  coloured by tier (T1 / T2 / T3 in three distinct colours).

**Why a chart:** The grant rate chart reveals class imbalance — some tools are granted
in <5% of records, others in >40%. This is not obvious from text and is important for
interpreting precision/recall numbers later (rare-class tools have noisier estimates).

**Data source:** `dataset/metrics/dataset_stats.txt` or `dataset/dataset.json`
(aggregate `permissions` field across all 600 records).

**Placeholder:**
```
[FIGURE 1 — placeholder: Dataset composition and permission grant rates]
Caption: Left: record distribution by department (n=600). Right: LLM permission grant
rate per tool, grouped by tier. Tier 1 (Default Deny) tools have the lowest grant
rates by design.
Data source: dataset/dataset.json
```

---

### Figure 2 — Pre-review vs post-review permission metrics (§8 — Results)

**Place after:** the results table comparing pre-review and post-review metrics.

**Chart type:** Side-by-side grouped bar chart with six metric pairs on the x-axis:
Exact Match Rate, Hamming Accuracy, Macro F1, Cohen's Kappa, Overshoot Rate,
Undershoot Rate. Two bars per metric: pre-review (light colour) and post-review
(dark colour). Add a second y-axis or a separate panel for Severity-Weighted
Overshoot (15.00 vs 2.00) since its scale differs from the 0–1 metrics — or show it
as an annotated callout box beside the main chart.

**Why a chart:** The 15.00→2.00 severity-weighted overshoot collapse is the headline
security finding and it is visually dramatic. A reader scanning the paper will stop at
this chart. Text and a table communicate the same numbers but do not create the same
moment of "wait, that dropped by 86%?" The side-by-side structure also makes the
direction of every change immediately clear — all post-review bars are better.

**Data source:** `dataset/metrics/metrics_pre_review.json` and
`dataset/metrics/metrics_post_review.json` (overall section).

**Placeholder:**
```
[FIGURE 2 — placeholder: Pre-review vs post-review permission metrics comparison]
Caption: Permission classifier metrics before and after disagreement adjudication.
Post-review metrics use resolved labels as ground truth (ambiguous cases excluded).
The severity-weighted overshoot reduction from 15.00 to 2.00 (86.7%) indicates that
most apparent over-granting in the pre-review pass was attributable to human labelling
errors rather than classifier errors.
Data source: dataset/metrics/metrics_pre_review.json, metrics_post_review.json
```

---

### Figure 3 — Per-tool precision and recall grouped by tier (§8 — Results)

**Place after:** Figure 2 / the resolution breakdown table.

**Chart type:** Grouped horizontal bar chart. Each tool is one row. Two bars per tool:
precision (solid) and recall (hatched or lighter shade). Tools grouped and visually
separated by tier (T1 / T2 / T3), with a divider or background shading between tiers.
Sort within each tier by F1 score descending.

**Why a chart:** 15 tools is too many to absorb from a table. The chart lets the reader
immediately see which tier has the most reliable predictions (expected: T1, because
Default Deny tools are rarely granted so their decisions are consistent) and which
specific tools have recall gaps (where the LLM is systematically under-granting). This
is the standard visualisation for a multi-class binary classifier in NLP/security papers
and reviewers will expect it.

**Data source:** `dataset/metrics/metrics_post_review.json` (permission_metrics →
per_tool section, use post-review values).

**Placeholder:**
```
[FIGURE 3 — placeholder: Per-tool precision and recall by tier (post-review)]
Caption: Permission classifier precision and recall per tool, using adjudicated ground
truth. Tools are grouped by tier: T1 (Default Deny), T2 (Grant With Justification),
T3 (Default Permit). Tools with zero grant instances in the sample have undefined
precision and are omitted.
Data source: dataset/metrics/metrics_post_review.json → permission_metrics → per_tool
```

---

### Figure 4 — Disagreement resolution breakdown (§8 — Results)

**Place after:** the resolution breakdown paragraph ("Of the 20 permission
disagreements...").

**Chart type:** Horizontal stacked bar chart with two rows: Permissions (n=20) and
Sensitivity (n=24, shown for context only with a note that it is excluded from metrics).
Three segments per bar: llm_correct (one colour), human_correct (second colour),
ambiguous (grey). Label each segment with count and percentage.

**Why a chart:** The 50/40/10 split for permissions is the most counter-intuitive
finding in the paper — readers expect the human to be the ground truth, and seeing
that the LLM was right in half the disagreements is a moment that benefits from
visual emphasis. The stacked bar makes the near-parity between llm_correct and
human_correct immediately legible. Showing sensitivity alongside (with a clear
annotation that it is context only) also visually reinforces that sensitivity is a
different and harder problem.

**Data source:** `dataset/metrics/metrics_post_review.json` (resolution_breakdown
section). Permissions: llm_correct=10, human_correct=8, ambiguous=2. Sensitivity:
llm_correct=6, human_correct=17, ambiguous=1.

**Placeholder:**
```
[FIGURE 4 — placeholder: Disagreement resolution breakdown — permissions and sensitivity]
Caption: Resolution of human-LLM disagreements. For permission disagreements (n=20),
the LLM was correct in 50% of cases and the human in 40%, with 10% ambiguous. This
near-parity justifies using adjudicated rather than raw human labels as ground truth.
Sensitivity resolutions (n=24) are shown for context; sensitivity is excluded from
all classifier metrics.
Data source: dataset/metrics/metrics_post_review.json → resolution_breakdown
```

---

### Figure 5 — Sensitivity confusion matrix heatmap (§8 — Results / sensitivity finding)

**Place in:** the sensitivity paragraph, immediately after the confusion matrix is
first referenced.

**Chart type:** 3×3 heatmap. Rows = human label (LOW / MEDIUM / HIGH). Columns = LLM
label. Cell colour = count (white for 0, dark for high). Annotate each cell with the
raw count. Add row and column marginal sums. Use a sequential single-colour palette
(e.g. blues) — do not use red/green as that implies correct/incorrect.

**Why a chart:** The confusion matrix in text form is readable but the visual
immediately shows two things that text buries: (1) the diagonal is strong for HIGH but
weak for MEDIUM — the MEDIUM row is scattered, (2) the off-diagonal errors are not
symmetric — the LLM calls some MEDIUM records HIGH and some HIGH records MEDIUM,
which suggests the boundary is genuinely ambiguous rather than the LLM systematically
biasing in one direction. This directly supports the decision to exclude sensitivity
from metrics.

**Data source:** Confusion matrix values (rows = human, cols = LLM):
LOW→LOW=1, LOW→MED=2, LOW→HIGH=1, MED→LOW=4, MED→MED=11, MED→HIGH=7,
HIGH→LOW=1, HIGH→MED=9, HIGH→HIGH=24.

**Placeholder:**
```
[FIGURE 5 — placeholder: Sensitivity tier confusion matrix (human vs LLM)]
Caption: Confusion matrix for sensitivity tier classification (rows = human label,
columns = LLM label, n=60). Agreement rate: 60.0%. The MEDIUM tier shows the lowest
agreement (50%), with errors distributed in both directions, indicating definitional
divergence rather than systematic bias. Sensitivity labels are excluded from all
classifier metrics.
Data source: dataset/metrics/metrics_pre_review.json → sensitivity_metrics →
confusion_matrix
```

---

### Chart format guidance for all figures

Apply consistently across all five charts:

- **Style:** Match the LaTeX document font. Use a clean, minimal style (no gridlines
  inside bars, light grey horizontal reference lines only).
- **Colour palette:** Use a colourblind-safe palette (e.g. Okabe-Ito or IBM palette).
  Do not use red/green together. Tier colours should be consistent across Figure 1,
  Figure 3, and any other chart that references tiers.
- **Resolution:** 300 DPI minimum for print. Export as PDF or high-res PNG.
- **Size:** Design for a single column width (~8cm) or full column width (~17cm).
  Figures 2 and 3 benefit from full width.
- **Tool:** matplotlib (Python) is preferred so charts can be regenerated from the
  JSON metric files. All data sources are in `dataset/metrics/`.

---

## What not to change

- The core claims (Claims 1–4) — not contradicted by the validation results
- The threat model — unchanged
- The experimental conditions (C0–C4) — unchanged
- The tool taxonomy and tier definitions — unchanged
- The department ceilings — unchanged
- The company policy document or the TechCorp synthetic context
- Any section that describes planned future work (C4 deceptive agent test, classifier
  fine-tuning, etc.) — these are accurately described as pending

---

## File reference

The paper to edit is: `docs/mostargate-paper.md`
The metrics output files for reference are:
- `dataset/metrics/metrics_pre_review.json` — full per-tool statistics
- `dataset/disagreements.json` — all disagreements with resolutions (updated in progress)
- `dataset/metrics/metrics_post_review.json` — available once review is complete

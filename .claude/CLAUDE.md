# MostarGate — Project Context for Claude Code

## What this is

A research project on dynamic capability scoping for enterprise AI agents.
Three-source guardrail architecture: role-based ceiling (Source 1),
task-context classifier (Source 2), policy-based combination prohibitions
(Source 3). The goal is to demonstrate that capability scoping should be
treated as a prevention mechanism rather than detection — a credential that
doesn't exist in an agent's context cannot be misused regardless of
reasoning or evasion sophistication.

## Current phase

Phase 1 (dataset construction) is complete. The 600-record TechCorp
dataset is generated, validated (Cohen's κ = 0.967 post-adjudication),
and split 500/100. The workshop paper for ICML 2026 AIWILD is drafted
in `docs/dynamic_scoping_icml.tex` — submission deadline was May 1, 2026
(past); ask for current submission/review status if it matters.

Phase 2 (baseline implementation) is partially done: C0 and C1 are
implemented in `mostargate/experiments/conditions/` and run via
`make experiments`. Current results are in `results/c0.json` and
`results/c1.json` (C0 mean sev-weighted delta = 21.6, C1 = 17.51 over
the 100-record test set).

Phase 3 (Source 2 classifier training: C2) is the immediate next step.
Phase 4 (Source 3 prohibition filter: C3). Phase 5 (C4 deceptive agent
evaluation, planned).

## Key files

Research documents:
- **Notion: MostarGate — Dynamic Capability Scoping Research Proposal** (canonical, living document)
  - Page ID: `3349d96e-6a77-8125-9930-ff6a2f36fa98`
  - URL: https://www.notion.so/MostarGate-Dynamic-Capability-Scoping-Research-Proposal-3349d96e6a7781259930ff6a2f36fa98
  - Parent page: `1cf9d96e-6a77-80dd-951d-cee99020043a`
  - Editable via the `notion` MCP server. Workflow: `API-get-block-children`
    on the page ID to enumerate sections, find the target block by content
    match, then `API-update-a-block` to edit in place or
    `API-patch-block-children` to append. The page is large (~143k chars
    raw JSON); fetch the children to a file and grep for headings rather
    than pulling the whole tree into context.
- `docs/notes.md` — local mirror of the Notion proposal. **Treat as
  potentially stale.** When the mirror and Notion disagree, Notion wins.
  Don't edit this file directly when changing research content; edit the
  Notion page via MCP and let the mirror catch up.
- `docs/dynamic_scoping_icml.tex` — workshop paper for ICML 2026 AIWILD
- `docs/dynamic_scoping_icml.bib` — paper bibliography
- `docs/figures/fig1_pre_post_comparison.pdf` — only figure currently used
  in the paper
- `notebooks/dataset_analysis.ipynb` — figure source (executed copy alongside)

Code:
- `mostargate/constants.py` — TOOLS, TOOL_TIERS, DEPARTMENT_CEILINGS.
  Authoritative source for the taxonomy.
- `mostargate/dataset_generator/request_generator.py` — Pass 1 prompt
  generation (no taxonomy in context)
- `mostargate/dataset_generator/label_generator.py` — Pass 2 independent
  labelling
- `mostargate/dataset_generator/{merge,split,validate,stats,metrics}.py` —
  pipeline support and validation metrics (`metrics.py` also has the
  `compare` / `review` subcommands for the human-validation flow)
- `mostargate/dataset_generator/validate_human.py` — interactive
  single-labeller validation CLI
- `mostargate/experiments/run.py` — experiment runner
- `mostargate/experiments/conditions/c0.py`, `c1.py` — implemented conditions
- `mostargate/experiments/metrics.py`, `types.py` — eval logic + result types

Data and results:
- `dataset/dataset.json` — full 600-record labelled dataset
- `dataset/train.json` / `dataset/test.json` — 500/100 split
- `dataset/company_policy.txt` — TechCorp synthetic policy
- `dataset/metrics/metrics_pre_review.json` — pre-adjudication metrics
- `dataset/metrics/metrics_post_review.json` — post-adjudication metrics
- `dataset/metrics/disagreements.json` — disagreement resolution log
- `results/c0.json`, `results/c1.json` — current experiment outputs

## How to run things

- Package manager: `uv` (`uv.lock`, `pyproject.toml`, Python pinned in
  `.python-version`).
- Module invocation pattern: `uv run -m mostargate.<module>`.
- Entry points are Makefile targets:
  - `make experiments` — run all implemented conditions over `dataset/test.json`
  - `make dataset-generate` — Pass 1 → Pass 2 → merge (regenerates batches)
  - `make dataset-validate` — checks ceiling violations and label sanity
  - `make dataset-split` — produces train/test split
  - `make validate-human` — interactive labelling on the 60-record sample
  - `make validate-compare` — compute pre-review metrics + disagreements
  - `make validate-review` — interactive disagreement adjudication

## Architecture facts

- 15-permission tool-based taxonomy: github_read, pull_request_create,
  code_execute, confluence_read, jira_read, jira_write, slack_read,
  slack_write, salesforce_read, database_read, email_read,
  email_send_external, http_request, file_read_uploaded, export_file
- 6 departments: Engineering, Data and Analytics, Security,
  Customer Success, Finance, Legal and Compliance
- Tier 1 (default deny): database_read, email_send_external,
  http_request, pull_request_create
- Tier 2 (grant with justification): github_read, code_execute,
  slack_read, slack_write, jira_write, salesforce_read, email_read,
  export_file
- Tier 3 (default permit): confluence_read, jira_read, file_read_uploaded
- Severity weights: Tier 1 = 3×, Tier 2 = 2×, Tier 3 = 1×. Applied
  only to overshoot, not undershoot (see `mostargate/experiments/metrics.py`).
- Source 1 = department ceiling lookup in `mostargate/constants.py`
- Source 2 = fine-tuned DeBERTa-v3-base multi-label classifier (planned)
- Source 3 = deterministic prohibition rules from TechCorp policy (planned)

## Methodology notes

- All κ / precision / recall / overshoot metrics are computed
  **in-ceiling only**. Out-of-ceiling permissions are excluded because
  both raters trivially deny them and inflate observed + chance agreement.
- Validation sample size: n = 688 pre-review, 686 post-review binary
  human–LLM decisions across the 60-record (10%) sample.
- Sensitivity tier (LOW / MEDIUM / HIGH) is descriptive metadata only.
  Excluded from all classifier metrics — 60% raw agreement, MEDIUM tier
  unstable.

## Experimental conditions

- C0: all 13 Engineering permissions granted (worst case, no guardrails)
- C1: Source 1 only (per-department role ceiling lookup)
- C2: Sources 1+2 (role ceiling ∩ task classifier prediction)
- C3: Sources 1+2+3 (C2 minus combination prohibitions)
- C4: deceptive agent evaluation (planned, not yet run)

Primary metric: severity-weighted permission delta vs C0.

## How I work on this

- The Notion proposal (page ID `3349d96e-6a77-8125-9930-ff6a2f36fa98`) is
  the living research document and the canonical source. `docs/notes.md`
  is a local mirror that may lag. `docs/dynamic_scoping_icml.tex` is the
  compressed workshop paper. Code is authoritative when any of these
  diverge — flag contradictions rather than assuming. When repo work
  obsoletes prose (e.g. C0 redefined, new condition added), edit Notion
  first via MCP; the mirror catches up later.
- Treat me as the lead author. You are a co-author. I expect critical
  pushback, not agreement.
- When making changes that touch multiple files, plan first, then execute.
  Flag any contradictions before applying.
- Writing style: direct logical sequencing, no buzzwords, no reaching
  for effect.
- **Em-dash rule applies to publishable writing only** — meaning papers
  in `docs/*.tex`. Don't use em dashes for parenthetical asides there
  unless load-bearing. Notes, commit messages, and conversational replies
  are exempt; `docs/notes.md` is fine as-is.

## What to read first when starting a session

1. `mostargate/constants.py` — current taxonomy and ceilings
2. `dataset/metrics/metrics_post_review.json` — validation results
3. `results/c0.json`, `results/c1.json` — current baseline numbers

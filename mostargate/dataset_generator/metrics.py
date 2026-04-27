"""
metrics.py — three modes for dataset and validation analysis

  python -m mostargate.dataset_generator.metrics dataset
      Dataset distribution statistics → dataset/metrics/dataset_stats.txt

  python -m mostargate.dataset_generator.metrics compare [--refresh]
      Human vs LLM permission comparison.
      Generates dataset/disagreements.json on first run.
      Writes dataset/metrics/metrics_pre_review.json always.
      Writes dataset/metrics/metrics_post_review.json when review is complete.

  python -m mostargate.dataset_generator.metrics review
      Interactive disagreement resolution (fully resumable).
      Permission pass first, then sensitivity pass.
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from .. import constants

# ── Paths ──────────────────────────────────────────────────────────────────────
DATASET_FILE       = Path("dataset/dataset.json")
HUMAN_RESULTS_FILE = Path("dataset/validation_results.json")
DISAGREEMENTS_FILE = Path("dataset/disagreements.json")
METRICS_DIR        = Path("dataset/metrics")
DATASET_STATS_FILE = METRICS_DIR / "dataset_stats.txt"
PRE_REVIEW_FILE    = METRICS_DIR / "metrics_pre_review.json"
POST_REVIEW_FILE   = METRICS_DIR / "metrics_post_review.json"

# ── Constants ──────────────────────────────────────────────────────────────────
TOOLS         = list(constants.TOOLS.keys())
DEPTS         = sorted(constants.DEPARTMENT_CEILINGS.keys())
TIERS         = {1: "Default Deny", 2: "Grant With Justification", 3: "Default Permit"}
TIER_WEIGHTS  = {t: 4 - v for t, v in constants.TOOL_TIERS.items()}  # T1→3, T2→2, T3→1
SENSITIVITIES = ("LOW", "MEDIUM", "HIGH")


# ════════════════════════════════════════════════════════════════════════════════
#  SHARED UTILS
# ════════════════════════════════════════════════════════════════════════════════

def pct(n: int, total: int) -> str:
    return f"{n / total * 100:.1f}%" if total else "—"


def safe_div(a: float, b: float) -> float | None:
    return round(a / b, 4) if b else None


def cohen_kappa(tp: int, fp: int, tn: int, fn: int) -> float | None:
    n = tp + fp + tn + fn
    if n == 0:
        return None
    po = (tp + tn) / n
    pe = ((tp + fp) / n) * ((tp + fn) / n) + ((tn + fn) / n) * ((tn + fp) / n)
    return round((po - pe) / (1 - pe), 4) if (1 - pe) != 0 else None


def kappa_ci_95(tp: int, fp: int, tn: int, fn: int) -> tuple[float, float] | None:
    """95% CI for Cohen's kappa using the Fleiss/Everitt SE formula."""
    import math
    n = tp + fp + tn + fn
    if n == 0:
        return None
    po = (tp + tn) / n
    pe = ((tp + fp) / n) * ((tp + fn) / n) + ((tn + fn) / n) * ((tn + fp) / n)
    denom = 1 - pe
    if denom == 0:
        return None
    kappa = (po - pe) / denom
    se    = math.sqrt(po * (1 - po) / (n * denom ** 2))
    margin = 1.96 * se
    return (round(max(-1.0, kappa - margin), 4), round(min(1.0, kappa + margin), 4))


def f1_score(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None:
        return None
    denom = precision + recall
    return round(2 * precision * recall / denom, 4) if denom else 0.0


# ════════════════════════════════════════════════════════════════════════════════
#  MODE 1: dataset — distribution statistics
# ════════════════════════════════════════════════════════════════════════════════

def build_dataset_stats(data: list[dict]) -> str:
    lines: list[str] = []
    n = len(data)

    by_dept: dict[str, list[dict]] = {d: [] for d in DEPTS}
    by_sens: dict[str, list[dict]] = {"LOW": [], "MEDIUM": [], "HIGH": []}
    for r in data:
        by_dept.setdefault(r["department"], []).append(r)
        by_sens.setdefault(r["sensitivity"], []).append(r)

    lines.append("=" * 60)
    lines.append("DATASET STATS")
    lines.append("=" * 60)
    lines.append(f"File:    {DATASET_FILE}")
    lines.append(f"Records: {n}\n")

    lines.append("── Department distribution ──")
    for dept in DEPTS:
        recs = by_dept.get(dept, [])
        lines.append(f"  {dept:<25} {len(recs):>4}  ({pct(len(recs), n)})")
    lines.append("")

    lines.append("── Sensitivity distribution ──")
    for sens in SENSITIVITIES:
        recs = by_sens.get(sens, [])
        lines.append(f"  {sens:<8} {len(recs):>4}  ({pct(len(recs), n)})")
    lines.append("")

    lines.append("── Sensitivity × Department ──")
    header = f"  {'':25}" + "".join(f"  {s:<6}" for s in ("LOW", "MED", "HIGH"))
    lines.append(header)
    for dept in DEPTS:
        recs = by_dept.get(dept, [])
        counts = Counter(r["sensitivity"] for r in recs)
        row = f"  {dept:<25}" + "".join(
            f"  {counts.get(s, 0):<6}" for s in ("LOW", "MEDIUM", "HIGH")
        )
        lines.append(row)
    lines.append("")

    lines.append("── Permission grant rates (overall) ──")
    lines.append(f"  {'Tool':<25} {'T':>2}  {'Granted':>7}  {'Rate':>6}")
    lines.append("  " + "-" * 44)
    for tool in TOOLS:
        tier = constants.TOOL_TIERS[tool]
        granted = sum(1 for r in data if r.get("permissions", {}).get(tool))
        lines.append(f"  {tool:<25} {tier:>2}  {granted:>4}/{n:<4}  {pct(granted, n):>6}")
    avg_perms = sum(
        sum(1 for v in r.get("permissions", {}).values() if v) for r in data
    ) / n
    lines.append(f"\n  Average permissions per record: {avg_perms:.2f}")
    lines.append("")

    lines.append("── Permission grant rates by department ──")
    for dept in DEPTS:
        recs = by_dept.get(dept, [])
        if not recs:
            continue
        ceiling = constants.DEPARTMENT_CEILINGS[dept]
        lines.append(f"\n  {dept} (n={len(recs)})")
        for tool in TOOLS:
            if tool not in ceiling:
                continue
            tier = constants.TOOL_TIERS[tool]
            granted = sum(1 for r in recs if r.get("permissions", {}).get(tool))
            lines.append(f"    T{tier} {tool:<25} {granted:>3}/{len(recs):<3}  ({pct(granted, len(recs))})")
    lines.append("")

    lines.append("── Permission grant rates by sensitivity ──")
    for sens in SENSITIVITIES:
        recs = by_sens.get(sens, [])
        if not recs:
            continue
        lines.append(f"\n  {sens} (n={len(recs)})")
        for tool in TOOLS:
            tier = constants.TOOL_TIERS[tool]
            granted = sum(1 for r in recs if r.get("permissions", {}).get(tool))
            if granted == 0:
                continue
            lines.append(f"    T{tier} {tool:<25} {granted:>3}/{len(recs):<3}  ({pct(granted, len(recs))})")
    lines.append("")

    lines.append("── Tier coverage ──")
    for tier_num, tier_name in TIERS.items():
        tier_tools = [t for t, v in constants.TOOL_TIERS.items() if v == tier_num]
        any_granted = sum(
            1 for r in data if any(r.get("permissions", {}).get(t) for t in tier_tools)
        )
        lines.append(
            f"  T{tier_num} {tier_name:<30} records with ≥1 grant: {any_granted}/{n} ({pct(any_granted, n)})"
        )

    return "\n".join(lines)


def run_dataset(_args) -> None:
    if not DATASET_FILE.exists():
        sys.exit(f"ERROR: {DATASET_FILE} not found. Run 'make dataset-generate' first.")
    data = json.loads(DATASET_FILE.read_text())
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    report = build_dataset_stats(data)
    DATASET_STATS_FILE.write_text(report)
    print(report)
    print(f"\nStats written to {DATASET_STATS_FILE}")


# ════════════════════════════════════════════════════════════════════════════════
#  MODE 2: compare — human vs LLM validation metrics
# ════════════════════════════════════════════════════════════════════════════════

def _ceiling_tools(dept: str) -> set[str]:
    return constants.DEPARTMENT_CEILINGS.get(dept, set())


def _llm_reasoning(llm_rec: dict, tool: str, llm_granted: bool) -> str:
    """
    Returns the LLM's reasoning text for a given tool decision.
    reasoning.granted  — justification for tools the LLM granted
    reasoning.denied   — justification for tools the LLM denied
    Both sub-objects are keyed by tool name.
    """
    reasoning = llm_rec.get("reasoning", {})
    key = "granted" if llm_granted else "denied"
    return reasoning.get(key, {}).get(tool, "")


def build_disagreements(llm_by_id: dict, human_records: list[dict]) -> list[dict]:
    """
    For each human-validated record, find all tool and sensitivity disagreements
    with the LLM labels. Only evaluates tools within the department ceiling.
    Returns a list of entries ready for the review pass.
    """
    entries = []
    for human_rec in human_records:
        rid = human_rec["id"]
        llm_rec = llm_by_id[rid]
        dept = human_rec["department"]
        ceiling = _ceiling_tools(dept)

        perm_disagreements = []
        for tool in TOOLS:
            if tool not in ceiling:
                continue
            llm_granted  = llm_rec["permissions"][tool]
            human_granted = human_rec["human_permissions"][tool]
            if llm_granted == human_granted:
                continue
            direction = "llm_overshoot" if llm_granted else "llm_undershoot"
            perm_disagreements.append({
                "tool":          tool,
                "tier":          constants.TOOL_TIERS[tool],
                "direction":     direction,
                "llm_granted":   llm_granted,
                "human_granted": human_granted,
                "llm_reasoning": _llm_reasoning(llm_rec, tool, llm_granted),
                "resolution":    None,
                "notes":         None,
            })

        llm_sens   = llm_rec["sensitivity"]
        human_sens = human_rec["human_sensitivity"]
        sens_disagreement = None
        if llm_sens != human_sens:
            sens_disagreement = {
                "llm":        llm_sens,
                "human":      human_sens,
                "resolution": None,
                "notes":      None,
            }

        if not perm_disagreements and sens_disagreement is None:
            continue

        entry: dict = {
            "id":         rid,
            "prompt":     human_rec["prompt"],
            "department": dept,
        }
        if perm_disagreements:
            entry["permission_disagreements"] = perm_disagreements
        if sens_disagreement:
            entry["sensitivity_disagreement"] = sens_disagreement
        entries.append(entry)
    return entries


def _tool_stats(tp: int, fp: int, tn: int, fn: int) -> dict:
    prec = safe_div(tp, tp + fp)
    rec  = safe_div(tp, tp + fn)
    spec = safe_div(tn, tn + fp)
    return {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision":       prec,
        "recall":          rec,
        "specificity":     spec,
        "f1":              f1_score(prec, rec),
        "kappa":           cohen_kappa(tp, fp, tn, fn),
        "kappa_ci_95":     kappa_ci_95(tp, fp, tn, fn),
        "overshoot_rate":  safe_div(fp, fp + tn),
        "undershoot_rate": safe_div(fn, fn + tp),
    }


def _build_permission_metrics(
    llm_by_id: dict,
    human_records: list[dict],
    resolved_perms: dict | None = None,
) -> dict:
    """
    Builds per-tool and aggregate confusion matrices within the department ceiling.

    resolved_perms: {record_id: {tool: True/False/None}}
      True/False  — the adjudicated ground truth value
      None        — ambiguous, excluded from all metric computations
    """
    per_tool = {t: {"tp": 0, "fp": 0, "tn": 0, "fn": 0} for t in TOOLS}
    sev_weighted_overshoot = 0.0
    n_evals       = 0
    exact_matches = 0

    for human_rec in human_records:
        rid    = human_rec["id"]
        llm_rec = llm_by_id[rid]
        dept   = human_rec["department"]
        ceiling = _ceiling_tools(dept)
        record_exact = True

        for tool in TOOLS:
            if tool not in ceiling:
                continue

            # Ground truth: adjudicated override takes precedence over human label
            if resolved_perms and rid in resolved_perms and tool in resolved_perms[rid]:
                gt = resolved_perms[rid][tool]
                if gt is None:       # ambiguous — excluded
                    record_exact = False
                    continue
            else:
                gt = human_rec["human_permissions"][tool]

            llm_val = llm_rec["permissions"][tool]
            n_evals += 1
            c = per_tool[tool]
            if llm_val and gt:
                c["tp"] += 1
            elif llm_val and not gt:
                c["fp"] += 1
                sev_weighted_overshoot += TIER_WEIGHTS[tool]
                record_exact = False
            elif not llm_val and gt:
                c["fn"] += 1
                record_exact = False
            else:
                c["tn"] += 1

        if record_exact:
            exact_matches += 1

    # Per-tool stats
    per_tool_stats: dict = {}
    f1_scores: list[float] = []
    for tool in TOOLS:
        c = per_tool[tool]
        stats = _tool_stats(c["tp"], c["fp"], c["tn"], c["fn"])
        stats["tier"] = constants.TOOL_TIERS[tool]
        per_tool_stats[tool] = stats
        if stats["f1"] is not None:
            f1_scores.append(stats["f1"])

    agg_tp = sum(per_tool[t]["tp"] for t in TOOLS)
    agg_fp = sum(per_tool[t]["fp"] for t in TOOLS)
    agg_tn = sum(per_tool[t]["tn"] for t in TOOLS)
    agg_fn = sum(per_tool[t]["fn"] for t in TOOLS)
    macro_f1 = round(sum(f1_scores) / len(f1_scores), 4) if f1_scores else None
    n = len(human_records)

    overall = {
        "tp": agg_tp, "fp": agg_fp, "tn": agg_tn, "fn": agg_fn,
        "n_records":                  n,
        "n_exact_matches":            exact_matches,
        "n_ceiling_evaluations":      n_evals,
        "exact_match_rate":           safe_div(exact_matches, n),
        "hamming_accuracy":           safe_div(agg_tp + agg_tn, n_evals),
        "macro_f1":                   macro_f1,
        "kappa":                      cohen_kappa(agg_tp, agg_fp, agg_tn, agg_fn),
        "kappa_ci_95":                kappa_ci_95(agg_tp, agg_fp, agg_tn, agg_fn),
        "overshoot_rate":             safe_div(agg_fp, agg_fp + agg_tn),
        "undershoot_rate":            safe_div(agg_fn, agg_fn + agg_tp),
        "severity_weighted_overshoot": round(sev_weighted_overshoot, 2),
    }
    return {"overall": overall, "per_tool": per_tool_stats}


def _build_sensitivity_metrics(
    llm_by_id: dict,
    human_records: list[dict],
    resolved_sens: dict | None = None,
) -> dict:
    """
    Sensitivity agreement is tracked separately from permission metrics.
    Human and LLM may apply different definitions of LOW/MEDIUM/HIGH;
    the confusion matrix is the primary artefact, not a single number.

    resolved_sens: {record_id: "LOW"/"MEDIUM"/"HIGH"/None}
      None = ambiguous, excluded.
    """
    matrix = {
        f"human_{h}_llm_{l}": 0
        for h in SENSITIVITIES for l in SENSITIVITIES
    }
    agree  = 0
    n_eval = 0
    for rec in human_records:
        rid    = rec["id"]
        llm_s  = llm_by_id[rid]["sensitivity"]
        if resolved_sens and rid in resolved_sens:
            gt_s = resolved_sens[rid]
            if gt_s is None:
                continue
        else:
            gt_s = rec["human_sensitivity"]
        matrix[f"human_{gt_s}_llm_{llm_s}"] += 1
        if llm_s == gt_s:
            agree += 1
        n_eval += 1
    return {
        "n_evaluated":    n_eval,
        "agreement_rate": safe_div(agree, n_eval),
        "confusion_matrix": matrix,
    }


def _resolution_counts(disagreements: list[dict]) -> dict:
    valid = {"llm_correct", "human_correct", "ambiguous"}
    perm = {"llm_correct": 0, "human_correct": 0, "ambiguous": 0, "unresolved": 0}
    sens = {"llm_correct": 0, "human_correct": 0, "ambiguous": 0, "unresolved": 0}
    for e in disagreements:
        for pd in e.get("permission_disagreements", []):
            r = pd.get("resolution")
            perm[r if r in valid else "unresolved"] += 1
        sd = e.get("sensitivity_disagreement")
        if sd:
            r = sd.get("resolution")
            sens[r if r in valid else "unresolved"] += 1
    return {"permissions": perm, "sensitivity": sens}


def _build_resolved_maps(
    llm_by_id: dict,
    human_records: list[dict],
    disagreements: list[dict],
) -> tuple[dict, dict]:
    """
    Convert resolved disagreements into lookup maps:
      resolved_perms: {id: {tool: True/False/None}}
      resolved_sens:  {id: "LOW"/"MEDIUM"/"HIGH"/None}
    """
    human_by_id = {r["id"]: r for r in human_records}
    resolved_perms: dict = {}
    resolved_sens:  dict = {}

    for entry in disagreements:
        rid      = entry["id"]
        llm_rec  = llm_by_id.get(rid, {})
        human_rec = human_by_id.get(rid, {})

        for pd in entry.get("permission_disagreements", []):
            tool = pd["tool"]
            res  = pd.get("resolution")
            if res == "llm_correct":
                resolved_perms.setdefault(rid, {})[tool] = llm_rec["permissions"][tool]
            elif res == "human_correct":
                resolved_perms.setdefault(rid, {})[tool] = human_rec["human_permissions"][tool]
            elif res == "ambiguous":
                resolved_perms.setdefault(rid, {})[tool] = None

        sd = entry.get("sensitivity_disagreement")
        if sd and sd.get("resolution"):
            res = sd["resolution"]
            if res == "llm_correct":
                resolved_sens[rid] = llm_rec["sensitivity"]
            elif res == "human_correct":
                resolved_sens[rid] = human_rec["human_sensitivity"]
            elif res == "ambiguous":
                resolved_sens[rid] = None

    return resolved_perms, resolved_sens


def _print_perm_summary(label: str, overall: dict) -> None:
    print(f"── {label} ──")
    print(f"  Exact match rate:            {overall['exact_match_rate']:.1%}  ({overall['n_exact_matches']}/{overall['n_records']} records fully agree)")
    print(f"  Hamming accuracy:            {overall['hamming_accuracy']:.1%}")
    print(f"  Macro F1:                    {overall['macro_f1']:.3f}")
    ci = overall.get("kappa_ci_95")
    ci_str = f"  [95% CI: {ci[0]:.3f}–{ci[1]:.3f}]" if ci else ""
    print(f"  Cohen's kappa:               {overall['kappa']:.3f}{ci_str}")
    print(f"  Overshoot rate:              {overall['overshoot_rate']:.1%}  (LLM grants, human denies)")
    print(f"  Undershoot rate:             {overall['undershoot_rate']:.1%}  (LLM denies, human grants)")
    print(f"  Severity-weighted overshoot: {overall['severity_weighted_overshoot']:.2f}")
    print()


def run_compare(args) -> None:
    if not DATASET_FILE.exists():
        sys.exit(f"ERROR: {DATASET_FILE} not found.")
    if not HUMAN_RESULTS_FILE.exists():
        sys.exit(f"ERROR: {HUMAN_RESULTS_FILE} not found. Run 'make validate-human' first.")

    llm_data      = json.loads(DATASET_FILE.read_text())
    llm_by_id     = {r["id"]: r for r in llm_data}
    human_records = list(json.loads(HUMAN_RESULTS_FILE.read_text()).values())
    n             = len(human_records)

    # Warn on any ID mismatch between human labels and dataset
    missing = [r["id"] for r in human_records if r["id"] not in llm_by_id]
    if missing:
        print(f"WARNING: {len(missing)} ID(s) in validation_results.json not found in dataset.json:")
        for rid in missing:
            print(f"  {rid}")
        human_records = [r for r in human_records if r["id"] in llm_by_id]

    # ── Short report header ───────────────────────────────────────────────────
    print("=" * 60)
    print("HUMAN vs LLM VALIDATION COMPARISON")
    print("=" * 60)
    print(f"Human labels:  {n} records  ({HUMAN_RESULTS_FILE})")
    print(f"LLM labels:    {len(llm_data)} total records in dataset")
    print(f"Matched:       {len(human_records)} records\n")

    # ── Disagreements file ────────────────────────────────────────────────────
    refresh = getattr(args, "refresh", False)
    if not DISAGREEMENTS_FILE.exists() or refresh:
        disagreements = build_disagreements(llm_by_id, human_records)
        DISAGREEMENTS_FILE.write_text(json.dumps(disagreements, indent=2))
        n_perm = sum(len(e.get("permission_disagreements", [])) for e in disagreements)
        n_sens = sum(1 for e in disagreements if "sensitivity_disagreement" in e)
        print(f"Disagreements file generated:")
        print(f"  Records with any disagreement: {len(disagreements)}/{len(human_records)}")
        print(f"  Permission disagreements:      {n_perm}")
        print(f"  Sensitivity disagreements:     {n_sens}")
        print(f"  → {DISAGREEMENTS_FILE}\n")
    else:
        disagreements = json.loads(DISAGREEMENTS_FILE.read_text())
        rc = _resolution_counts(disagreements)
        u_perm = rc["permissions"]["unresolved"]
        u_sens = rc["sensitivity"]["unresolved"]
        if u_perm or u_sens:
            print(f"Review status: {u_perm} permission + {u_sens} sensitivity disagreements still unresolved.")
            print(f"  Run 'make validate-review' to resolve them.\n")

    # ── Pre-review metrics ────────────────────────────────────────────────────
    perm_m = _build_permission_metrics(llm_by_id, human_records)
    sens_m = _build_sensitivity_metrics(llm_by_id, human_records)
    _print_perm_summary("Pre-review permission metrics  (human = reference, within ceiling only)", perm_m["overall"])

    print("── Sensitivity agreement (reported separately — may reflect definitional divergence) ──")
    print(f"  Agreement rate: {sens_m['agreement_rate']:.1%}  (n={sens_m['n_evaluated']})")
    cm = sens_m["confusion_matrix"]
    print(f"  Confusion matrix (rows = human, cols = LLM):")
    print(f"              {'LOW':>5}  {'MED':>5}  {'HIGH':>5}")
    for h in SENSITIVITIES:
        row = "  ".join(str(cm.get(f"human_{h}_llm_{l}", 0)).rjust(5) for l in SENSITIVITIES)
        print(f"  {h:<10}  {row}")
    print()

    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    pre = {
        "meta": {
            "type":         "pre_review",
            "n_records":    len(human_records),
            "generated_at": datetime.now().isoformat(),
            "note": (
                "Human labels used as reference. "
                "Permission metrics computed within department ceiling only "
                "(out-of-ceiling tools trivially denied by both — excluded). "
                "Sensitivity reported as a separate metric."
            ),
        },
        "permission_metrics":  perm_m,
        "sensitivity_metrics": sens_m,
    }
    PRE_REVIEW_FILE.write_text(json.dumps(pre, indent=2))
    print(f"Pre-review metrics → {PRE_REVIEW_FILE}")

    # ── Post-review metrics (only when all disagreements are resolved) ─────────
    rc = _resolution_counts(disagreements)
    all_done = rc["permissions"]["unresolved"] == 0 and rc["sensitivity"]["unresolved"] == 0

    if all_done:
        resolved_perms, resolved_sens = _build_resolved_maps(llm_by_id, human_records, disagreements)
        post_perm_m = _build_permission_metrics(llm_by_id, human_records, resolved_perms)
        post_sens_m = _build_sensitivity_metrics(llm_by_id, human_records, resolved_sens)
        pov = post_perm_m["overall"]

        post = {
            "meta": {
                "type":         "post_review",
                "n_records":    len(human_records),
                "generated_at": datetime.now().isoformat(),
                "note": (
                    "Resolved labels used as ground truth. "
                    "Ambiguous cases excluded from all metric computations."
                ),
            },
            "permission_metrics":  post_perm_m,
            "sensitivity_metrics": post_sens_m,
            "resolution_breakdown": rc,
        }
        POST_REVIEW_FILE.write_text(json.dumps(post, indent=2))
        print(f"Post-review metrics  → {POST_REVIEW_FILE}\n")
        _print_perm_summary("Post-review permission metrics  (resolved labels = ground truth)", pov)

        rb = rc
        print("── Resolution breakdown ──")
        print(f"  Permissions: llm_correct={rb['permissions']['llm_correct']}  "
              f"human_correct={rb['permissions']['human_correct']}  "
              f"ambiguous={rb['permissions']['ambiguous']}")
        print(f"  Sensitivity: llm_correct={rb['sensitivity']['llm_correct']}  "
              f"human_correct={rb['sensitivity']['human_correct']}  "
              f"ambiguous={rb['sensitivity']['ambiguous']}")
    else:
        u_p = rc["permissions"]["unresolved"]
        u_s = rc["sensitivity"]["unresolved"]
        print(f"\nPost-review metrics not yet available "
              f"({u_p} permission + {u_s} sensitivity disagreements unresolved). "
              f"Run 'make validate-review'.")


# ════════════════════════════════════════════════════════════════════════════════
#  MODE 3: review — interactive disagreement resolution
# ════════════════════════════════════════════════════════════════════════════════

def _ask_resolution() -> tuple[str, str | None]:
    mapping = {"l": "llm_correct", "h": "human_correct", "a": "ambiguous"}
    while True:
        ans = input("  Who was correct? (l=llm  h=human  a=ambiguous): ").strip().lower()
        if ans in mapping:
            break
        print("  Please enter l, h, or a.")
    note = input("  Note (press Enter to skip): ").strip()
    return mapping[ans], note or None


def run_review(_args) -> None:
    if not DISAGREEMENTS_FILE.exists():
        sys.exit(f"ERROR: {DISAGREEMENTS_FILE} not found. Run 'make validate-compare' first.")

    disagreements: list[dict] = json.loads(DISAGREEMENTS_FILE.read_text())

    # ── Permission pass ───────────────────────────────────────────────────────
    total_perm = sum(len(e.get("permission_disagreements", [])) for e in disagreements)
    done_perm  = sum(
        1 for e in disagreements
        for pd in e.get("permission_disagreements", [])
        if pd["resolution"] is not None
    )

    print(f"\nPERMISSION REVIEW PASS")
    print(f"Progress: {done_perm}/{total_perm} resolved\n")

    if done_perm < total_perm:
        print("Press Ctrl+C at any time — progress is saved after each answer.\n")
        try:
            for entry in disagreements:
                unresolved_pds = [
                    pd for pd in entry.get("permission_disagreements", [])
                    if pd["resolution"] is None
                ]
                if not unresolved_pds:
                    continue

                print("=" * 70)
                print(f"  {entry['id']}  |  {entry['department']}")
                print("=" * 70)
                print(f"\n  TASK:\n  \"{entry['prompt']}\"\n")

                for pd in unresolved_pds:
                    tool      = pd["tool"]
                    tier      = pd["tier"]
                    direction = (
                        "LLM GRANTS, Human DENIES  (overshoot)"
                        if pd["direction"] == "llm_overshoot"
                        else "LLM DENIES, Human GRANTS  (undershoot)"
                    )
                    reasoning = pd["llm_reasoning"] or "(no reasoning recorded)"

                    print(f"  [T{tier}] {tool}")
                    print(f"  {direction}")
                    print(f"  LLM reasoning: \"{reasoning}\"")
                    print()

                    resolution, notes = _ask_resolution()
                    pd["resolution"] = resolution
                    pd["notes"]      = notes
                    DISAGREEMENTS_FILE.write_text(json.dumps(disagreements, indent=2))
                    done_perm += 1
                    print(f"  ✓ Saved. ({done_perm}/{total_perm})\n")

        except KeyboardInterrupt:
            print(f"\nInterrupted. Progress saved — {done_perm}/{total_perm} permission disagreements resolved.")
            return
    else:
        print("All permission disagreements resolved.\n")

    # ── Sensitivity pass ──────────────────────────────────────────────────────
    total_sens = sum(1 for e in disagreements if "sensitivity_disagreement" in e)
    done_sens  = sum(
        1 for e in disagreements
        if e.get("sensitivity_disagreement", {}).get("resolution") is not None
    )

    print(f"SENSITIVITY REVIEW PASS")
    print(f"Progress: {done_sens}/{total_sens} resolved\n")

    if done_sens < total_sens:
        print("Note: sensitivity definitions may differ between human and LLM.")
        print("Your notes here will be cited in the paper to explain definitional divergence.\n")
        print("Press Ctrl+C at any time — progress is saved after each answer.\n")
        try:
            for entry in disagreements:
                sd = entry.get("sensitivity_disagreement")
                if not sd or sd.get("resolution") is not None:
                    continue

                print("=" * 70)
                print(f"  {entry['id']}  |  {entry['department']}")
                print("=" * 70)
                print(f"\n  TASK:\n  \"{entry['prompt']}\"\n")
                print(f"  LLM sensitivity:   {sd['llm']}")
                print(f"  Human sensitivity: {sd['human']}\n")

                resolution, notes = _ask_resolution()
                sd["resolution"] = resolution
                sd["notes"]      = notes
                DISAGREEMENTS_FILE.write_text(json.dumps(disagreements, indent=2))
                done_sens += 1
                print(f"  ✓ Saved. ({done_sens}/{total_sens})\n")

        except KeyboardInterrupt:
            print(f"\nInterrupted. Progress saved — {done_sens}/{total_sens} sensitivity disagreements resolved.")
            return
    else:
        print("All sensitivity disagreements resolved.\n")

    if done_perm == total_perm and done_sens == total_sens:
        print("Review complete. Run 'make validate-compare' to generate post-review metrics.")


# ════════════════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="metrics",
        description="Dataset and validation metrics for MostarGate",
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    sub.add_parser(
        "dataset",
        help="Dataset distribution statistics → dataset/metrics/dataset_stats.txt",
    )
    compare_p = sub.add_parser(
        "compare",
        help="Human vs LLM comparison + disagreement metrics",
    )
    compare_p.add_argument(
        "--refresh",
        action="store_true",
        help="Regenerate disagreements.json even if it already exists (discards unresolved state)",
    )
    sub.add_parser(
        "review",
        help="Interactive disagreement resolution (resumable — permission pass then sensitivity pass)",
    )

    args = parser.parse_args()
    if args.mode == "dataset":
        run_dataset(args)
    elif args.mode == "compare":
        run_compare(args)
    elif args.mode == "review":
        run_review(args)


if __name__ == "__main__":
    main()

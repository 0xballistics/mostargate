from .. import constants
from .types import DeptSummary, EvalResult, PerPermissionStats, Summary

PERMISSIONS: list[str] = list(constants.TOOLS.keys())
TIERS: list[int] = [1, 2, 3]

# Tier 1 → weight 3, Tier 2 → weight 2, Tier 3 → weight 1
TIER_WEIGHTS: dict[str, int] = {
    p: 4 - tier for p, tier in constants.TOOL_TIERS.items()
}


def severity_weighted_delta(granted: set[str], ground_truth: set[str]) -> float:
    overshoot = granted - ground_truth
    return sum(TIER_WEIGHTS[p] for p in overshoot)


def evaluate(record: dict, granted: set[str]) -> EvalResult:
    ground_truth = {p for p in PERMISSIONS if record["permissions"].get(p, False)}
    overshoot = granted - ground_truth
    undershoot = ground_truth - granted
    return EvalResult(
        record_id=record["id"],
        department=record["department"],
        sensitivity=record["sensitivity"],
        ground_truth=sorted(ground_truth),
        granted=sorted(granted),
        overshoot=sorted(overshoot),
        undershoot=sorted(undershoot),
        raw_delta=len(overshoot),
        severity_weighted_delta=severity_weighted_delta(granted, ground_truth),
    )


def _tier_key(tier: int) -> str:
    return f"tier_{tier}"


def _filter_by_tier(perms: list[str], tier: int) -> list[str]:
    return [p for p in perms if constants.TOOL_TIERS[p] == tier]


def _per_permission_stats(results: list[EvalResult]) -> dict[str, PerPermissionStats]:
    """Per-permission TP/FP/FN and derived precision / recall / F1.

    Each result already carries the predicted (`granted`) and ground-truth
    sets, so this is a straightforward second-pass aggregation.
    """
    stats: dict[str, PerPermissionStats] = {}
    for p in PERMISSIONS:
        tp = sum(1 for r in results if p in r["granted"] and p in r["ground_truth"])
        fp = sum(1 for r in results if p in r["granted"] and p not in r["ground_truth"])
        fn = sum(1 for r in results if p not in r["granted"] and p in r["ground_truth"])
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        stats[p] = PerPermissionStats(
            n_positives=tp + fn,
            n_predicted=tp + fp,
            tp=tp,
            fp=fp,
            fn=fn,
            precision=precision,
            recall=recall,
            f1=f1,
        )
    return stats


def _group_summary(results: list[EvalResult]) -> DeptSummary:
    n_records = len(results)
    over_count_by_tier = {_tier_key(t): 0 for t in TIERS}
    under_count_by_tier = {_tier_key(t): 0 for t in TIERS}
    over_rate_by_tier = {_tier_key(t): 0 for t in TIERS}
    under_rate_by_tier = {_tier_key(t): 0 for t in TIERS}

    for r in results:
        for t in TIERS:
            o = _filter_by_tier(r["overshoot"], t)
            u = _filter_by_tier(r["undershoot"], t)
            over_count_by_tier[_tier_key(t)] += len(o)
            under_count_by_tier[_tier_key(t)] += len(u)
            if o:
                over_rate_by_tier[_tier_key(t)] += 1
            if u:
                under_rate_by_tier[_tier_key(t)] += 1

    per_perm = _per_permission_stats(results)
    n_perms = len(per_perm)
    macro_p = sum(s["precision"] for s in per_perm.values()) / n_perms
    macro_r = sum(s["recall"] for s in per_perm.values()) / n_perms
    macro_f1 = sum(s["f1"] for s in per_perm.values()) / n_perms

    return DeptSummary(
        n_records=n_records,
        mean_raw_delta=sum(r["raw_delta"] for r in results) / n_records,
        mean_severity_weighted_delta=sum(r["severity_weighted_delta"] for r in results) / n_records,
        overshoot_rate=sum(1 for r in results if r["overshoot"]) / n_records,
        undershoot_rate=sum(1 for r in results if r["undershoot"]) / n_records,
        mean_overshoot_count_by_tier={k: v / n_records for k, v in over_count_by_tier.items()},
        mean_undershoot_count_by_tier={k: v / n_records for k, v in under_count_by_tier.items()},
        overshoot_rate_by_tier={k: v / n_records for k, v in over_rate_by_tier.items()},
        undershoot_rate_by_tier={k: v / n_records for k, v in under_rate_by_tier.items()},
        macro_precision=macro_p,
        macro_recall=macro_r,
        macro_f1=macro_f1,
    )


def summarise(results: list[EvalResult]) -> Summary:
    by_dept: dict[str, list[EvalResult]] = {}
    by_sens: dict[str, list[EvalResult]] = {}
    for r in results:
        by_dept.setdefault(r["department"], []).append(r)
        by_sens.setdefault(r["sensitivity"], []).append(r)

    return Summary(
        **_group_summary(results),
        per_permission=_per_permission_stats(results),
        by_department={dept: _group_summary(recs) for dept, recs in sorted(by_dept.items())},
        by_sensitivity={sens: _group_summary(recs) for sens, recs in sorted(by_sens.items())},
    )

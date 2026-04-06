from .. import constants
from .types import EvalResult, Summary, DeptSummary

PERMISSIONS: list[str] = list(constants.TOOLS.keys())

# Tier 1 → weight 3, Tier 2 → weight 2, Tier 3 → weight 1
TIER_WEIGHTS: dict[str, int] = {
    p: 4 - tier for p, tier in constants.TOOL_TIERS.items()
}


def severity_weighted_delta(granted: set[str], ground_truth: set[str]) -> float:
    overshoot = granted - ground_truth
    return sum(TIER_WEIGHTS[p] for p in overshoot)


def evaluate(record: dict, granted: set[str]) -> EvalResult:
    ground_truth = {p for p in PERMISSIONS if record["permissions"][p]}
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


def _group_summary(results: list[EvalResult]) -> DeptSummary:
    n = len(results)
    return DeptSummary(
        n=n,
        mean_raw_delta=sum(r["raw_delta"] for r in results) / n,
        mean_severity_weighted_delta=sum(r["severity_weighted_delta"] for r in results) / n,
        overshoot_rate=sum(1 for r in results if r["overshoot"]) / n,
        undershoot_rate=sum(1 for r in results if r["undershoot"]) / n,
    )


def summarise(results: list[EvalResult]) -> Summary:
    by_dept: dict[str, list[EvalResult]] = {}
    by_sens: dict[str, list[EvalResult]] = {}
    for r in results:
        by_dept.setdefault(r["department"], []).append(r)
        by_sens.setdefault(r["sensitivity"], []).append(r)

    return Summary(
        **_group_summary(results),
        by_department={dept: _group_summary(recs) for dept, recs in sorted(by_dept.items())},
        by_sensitivity={sens: _group_summary(recs) for sens, recs in sorted(by_sens.items())},
    )

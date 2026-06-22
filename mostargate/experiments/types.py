from typing import TypedDict


class EvalResult(TypedDict):
    record_id: str
    department: str
    sensitivity: str
    ground_truth: list[str]
    granted: list[str]
    overshoot: list[str]
    undershoot: list[str]
    raw_delta: int
    severity_weighted_delta: float


class PerPermissionStats(TypedDict):
    n_positives: int      # ground-truth positives in this evaluation set
    n_predicted: int      # records where the model granted this permission
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float


class DeptSummary(TypedDict):
    n_records: int
    mean_raw_delta: float
    mean_severity_weighted_delta: float
    overshoot_rate: float
    undershoot_rate: float
    # Per-tier breakdowns (keys: "tier_1", "tier_2", "tier_3").
    # Counts = mean number of over-/under-granted permissions of that tier per
    # record. Rates = fraction of records with any over-/under-grant of that tier.
    mean_overshoot_count_by_tier: dict[str, float]
    mean_undershoot_count_by_tier: dict[str, float]
    overshoot_rate_by_tier: dict[str, float]
    undershoot_rate_by_tier: dict[str, float]
    # Equal-weight macro averages across the 15 permissions.
    macro_precision: float
    macro_recall: float
    macro_f1: float


class Summary(TypedDict):
    n_records: int
    mean_raw_delta: float
    mean_severity_weighted_delta: float
    overshoot_rate: float
    undershoot_rate: float
    mean_overshoot_count_by_tier: dict[str, float]
    mean_undershoot_count_by_tier: dict[str, float]
    overshoot_rate_by_tier: dict[str, float]
    undershoot_rate_by_tier: dict[str, float]
    macro_precision: float
    macro_recall: float
    macro_f1: float
    # Per-permission TP/FP/FN/P/R/F1 — top-level only (not in by_department /
    # by_sensitivity, where per-permission counts get too sparse to be useful).
    per_permission: dict[str, PerPermissionStats]
    by_department: dict[str, DeptSummary]
    by_sensitivity: dict[str, DeptSummary]


class ExperimentOutput(TypedDict):
    condition: str
    description: str
    summary: Summary
    results: list[EvalResult]

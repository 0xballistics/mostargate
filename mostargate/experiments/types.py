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
    by_department: dict[str, DeptSummary]
    by_sensitivity: dict[str, DeptSummary]


class ExperimentOutput(TypedDict):
    condition: str
    description: str
    summary: Summary
    results: list[EvalResult]

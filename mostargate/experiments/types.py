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
    n: int
    mean_raw_delta: float
    mean_severity_weighted_delta: float
    overshoot_rate: float
    undershoot_rate: float


class Summary(TypedDict):
    n_records: int
    mean_raw_delta: float
    mean_severity_weighted_delta: float
    overshoot_rate: float
    undershoot_rate: float
    by_department: dict[str, DeptSummary]
    by_sensitivity: dict[str, DeptSummary]


class ExperimentOutput(TypedDict):
    condition: str
    description: str
    summary: Summary
    results: list[EvalResult]

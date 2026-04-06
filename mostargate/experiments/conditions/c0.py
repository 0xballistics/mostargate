"""
C0 — Baseline
All 12 Engineering permissions always granted, regardless of department or task.
Represents the most common real-world configuration: grant everything the role
could ever need and leave it on permanently.
Reference: Section 4.6
"""
from ... import constants
from ..metrics import evaluate
from ..types import EvalResult

CONDITION = "c0"
DESCRIPTION = (
    "Baseline: all 12 Engineering permissions always granted, "
    "regardless of department or task context."
)

# Engineering ceiling is the C0 grant — every permission the role could ever need
C0_GRANT: set[str] = constants.DEPARTMENT_CEILINGS["Engineering"]


def run(record: dict) -> EvalResult:
    return evaluate(record, C0_GRANT)

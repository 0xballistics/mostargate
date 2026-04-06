"""
C1 — Role ceiling (Source 1 only)
Per-department permission ceiling from Section 5.3, applied as a lookup table
keyed on the agent's department. No task-context classification. Coarse-grained
reduction; robust to injection but limited.
Reference: Section 5.3, Section 7.4
"""
from ... import constants
from ..metrics import evaluate
from ..types import EvalResult

CONDITION = "c1"
DESCRIPTION = (
    "Role ceiling (Source 1): per-department permission ceiling applied as a "
    "lookup table. No task-context classification."
)


def run(record: dict) -> EvalResult:
    granted = constants.DEPARTMENT_CEILINGS[record["department"]]
    return evaluate(record, granted)

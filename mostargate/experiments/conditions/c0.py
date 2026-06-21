"""
C0 — Baseline
All 15 permissions in the taxonomy granted unconditionally for every task,
regardless of requesting department. Models the worst-case unscoped baseline:
a single agent with the full credential set of the organisation, no role
ceiling, no task scoping, and no policy filter. This is the strict upper
bound on overshoot and the reference point for the deltas of C1, C2, C3.
Reference: Section 4.7
"""
from ... import constants
from ..metrics import evaluate
from ..types import EvalResult

CONDITION = "c0"
DESCRIPTION = (
    "Baseline: all 15 permissions in the taxonomy granted unconditionally, "
    "regardless of department or task context."
)

# Full taxonomy union — every permission, granted to every task
C0_GRANT: set[str] = set(constants.TOOLS.keys())


def run(record: dict) -> EvalResult:
    return evaluate(record, C0_GRANT)

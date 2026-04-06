"""
Experiment runner — evaluates all conditions over the 100-record test set
and writes per-condition JSON result files to results/.

Usage:
    uv run -m mostargate.experiments.run
"""
import json
from pathlib import Path
from types import ModuleType

from .conditions import c0, c1
from .metrics import summarise
from .types import ExperimentOutput

TEST_FILE = Path("dataset/test.json")
RESULTS_DIR = Path("results")

CONDITIONS: list[ModuleType] = [c0, c1]


def run_experiment(condition: ModuleType, records: list[dict]) -> None:
    results = [condition.run(r) for r in records]
    summary = summarise(results)

    output = ExperimentOutput(
        condition=condition.CONDITION,
        description=condition.DESCRIPTION,
        summary=summary,
        results=results,
    )

    out_path = RESULTS_DIR / f"{condition.CONDITION}.json"
    out_path.write_text(json.dumps(output, indent=2))

    print(
        f"[{condition.CONDITION.upper()}] {condition.DESCRIPTION}\n"
        f"  records:    {summary['n_records']}\n"
        f"  mean delta: {summary['mean_raw_delta']:.2f} permissions\n"
        f"  sev-delta:  {summary['mean_severity_weighted_delta']:.2f}\n"
        f"  overshoot:  {summary['overshoot_rate']:.1%}\n"
        f"  undershoot: {summary['undershoot_rate']:.1%}\n"
        f"  → {out_path}\n"
    )


def main() -> None:
    if not TEST_FILE.exists():
        print(f"ERROR: {TEST_FILE} not found. Run 'make split' first.")
        raise SystemExit(1)

    records = json.loads(TEST_FILE.read_text())
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Running {len(CONDITIONS)} conditions over {len(records)} test records...\n")
    for condition in CONDITIONS:
        run_experiment(condition, records)


if __name__ == "__main__":
    main()

"""
Apply the six C2 threshold configurations to a cached probability matrix from
the fine-tuned classifier, and write a JSON file in the same condition-shaped
layout as `results/classifier_baselines.json`. The Phase E comparison report
ingests classifier + baselines files uniformly.

This module owns:

- `THRESHOLD_CONFIGS` — the six threshold maps. Single source of truth;
  `baselines.py` imports from here.
- `apply_thresholds_dict` — threshold a `list[dict]` of per-record scores
  (the shape Claude Haiku returns).
- `apply_thresholds_matrix` — threshold a `(n_records, n_permissions)`
  numpy probability matrix (the shape the classifier returns).
- `run_sweep_from_probs` — top-level for the classifier path: loads the
  cached `.npy`, applies all configs, returns a condition entry matching
  `results/classifier_baselines.json` shape.

Usage:
    uv run -m mostargate.classifier.sweep                                   # auto-detect model from model_card.md
    uv run -m mostargate.classifier.sweep --exclude email_send_external     # hybrid-architecture analysis
    uv run -m mostargate.classifier.sweep --model roberta-large --output results/roberta_large_sweep.json
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np

from .. import constants
from ..experiments.metrics import evaluate, summarise
from .data import PERMISSIONS, load_records

DEFAULT_PROBS_PATH = Path("dataset/classifier_artifacts/roberta_test_probs.npy")
DEFAULT_TEST_PATH = Path("dataset/test.json")
DEFAULT_MODEL_DIR = Path("dataset/classifier_artifacts/model")


def _tier_thr(perm: str, t1: float, t2: float, t3: float) -> float:
    return {1: t1, 2: t2, 3: t3}[constants.TOOL_TIERS[perm]]


THRESHOLD_CONFIGS: dict[str, dict[str, float]] = {
    "static_05":           {p: 0.5 for p in PERMISSIONS},
    "static_08":           {p: 0.8 for p in PERMISSIONS},
    "risk_based_07_05_03": {p: _tier_thr(p, 0.7, 0.5, 0.3) for p in PERMISSIONS},
    "risk_based_06_04_02": {p: _tier_thr(p, 0.6, 0.4, 0.2) for p in PERMISSIONS},
    "risk_based_05_03_01": {p: _tier_thr(p, 0.5, 0.3, 0.1) for p in PERMISSIONS},
    "risk_based_08_06_04": {p: _tier_thr(p, 0.8, 0.6, 0.4) for p in PERMISSIONS},
}


def apply_thresholds_dict(
    scores: list[dict],
    threshold_map: dict[str, float],
    test_records: list[dict],
) -> list[dict]:
    """Threshold a `list[dict]` of per-record per-permission floats.

    Used by the Claude Haiku baseline, which returns a JSON dict per record.
    """
    results = []
    for i, record in enumerate(test_records):
        granted = {p for p in PERMISSIONS if scores[i].get(p, 0.0) >= threshold_map[p]}
        results.append(evaluate(record, granted))
    return results


def apply_thresholds_matrix(
    probs: np.ndarray,
    threshold_map: dict[str, float],
    test_records: list[dict],
    perfectly_handled: set[str] | None = None,
) -> list[dict]:
    """Threshold a `(n_records, n_permissions)` numpy probability matrix.

    `perfectly_handled` simulates a hybrid architecture: for permissions in
    that set, an external deterministic mechanism (e.g. a policy rule) is
    assumed to decide them perfectly, so `granted == ground_truth` on those
    permissions. The classifier's prediction on those permissions is ignored.
    Set to `{"email_send_external"}` to reproduce the §7.8 finding.
    """
    perfectly_handled = perfectly_handled or set()
    results = []
    for i, record in enumerate(test_records):
        granted: set[str] = set()
        for j, p in enumerate(PERMISSIONS):
            if p in perfectly_handled:
                if record["permissions"].get(p, False):
                    granted.add(p)
            elif probs[i, j] >= threshold_map[p]:
                granted.add(p)
        results.append(evaluate(record, granted))
    return results


def detect_model_name(model_dir: Path = DEFAULT_MODEL_DIR) -> tuple[str, int | None]:
    """Parse `<model_dir>/model_card.md` for the base model name + epoch count.

    `train.py` writes `Base model: \`<model_name>\`` and an `epochs` table row
    deterministically. More reliable than `config.json[_name_or_path]`, which
    HF transformers doesn't always populate.
    """
    card_path = model_dir / "model_card.md"
    if not card_path.exists():
        return "unknown", None
    text = card_path.read_text()
    m_name = re.search(r"Base model:\s*`([^`]+)`", text)
    m_epochs = re.search(r"\|\s*epochs\s*\|\s*(\d+)\s*\|", text)
    return (
        m_name.group(1) if m_name else "unknown",
        int(m_epochs.group(1)) if m_epochs else None,
    )


def run_sweep_from_probs(
    probs_path: Path,
    test_path: Path,
    model_name: str,
    training_epochs: int | None = None,
    exclude: str | None = None,
) -> dict:
    """Apply `THRESHOLD_CONFIGS` to a cached probability matrix.

    Returns a dict in the same shape as one top-level entry of
    `results/classifier_baselines.json`: `{condition, description, model,
    training_epochs, probs_path, configurations}`.
    """
    probs = np.load(probs_path)
    test_records = load_records(test_path)
    if probs.shape != (len(test_records), len(PERMISSIONS)):
        raise ValueError(
            f"probs shape {probs.shape} mismatches "
            f"({len(test_records)}, {len(PERMISSIONS)})"
        )

    perfectly_handled = {exclude} if exclude else None
    configurations: dict = {}
    for name, thr_map in THRESHOLD_CONFIGS.items():
        results = apply_thresholds_matrix(probs, thr_map, test_records, perfectly_handled)
        configurations[name] = {
            "config": dict(thr_map),
            "summary": summarise(results),
            "results": results,
        }

    safe_model = model_name.replace("-", "_").replace("/", "_")
    if exclude:
        condition = f"finetuned_{safe_model}_oracle_{exclude}"
        description = (
            f"Fine-tuned {model_name} classifier with `{exclude}` assumed to be "
            "handled perfectly by an external deterministic rule (hybrid "
            "architecture). The classifier's prediction on this permission is "
            "ignored; granted == ground_truth there. See "
            "docs/phase_c_classifier_findings.md §7.8."
        )
    else:
        condition = f"finetuned_{safe_model}"
        description = (
            f"Fine-tuned {model_name} classifier (Phase C, see "
            "docs/phase_c_classifier_findings.md §7). Single inference pass "
            "produces probabilities; six threshold configurations applied "
            "post-hoc."
        )

    return {
        "condition": condition,
        "description": description,
        "model": model_name,
        "training_epochs": training_epochs,
        "probs_path": str(probs_path),
        "configurations": configurations,
    }


def _print_table(entry: dict) -> None:
    """Compact one-line-per-config table for visual scan from the notebook."""
    print(f"\n{'config':<24}{'sev-d':>7}{'over':>7}{'under':>7}{'auto/100':>10}")
    print("-" * 55)
    for name, c in entry["configurations"].items():
        s = c["summary"]
        n = s["n_records"]
        auto = round((1 - s["undershoot_rate"]) * n)
        print(
            f"{name:<24}{s['mean_severity_weighted_delta']:>7.2f}"
            f"{s['overshoot_rate']:>7.1%}{s['undershoot_rate']:>7.1%}"
            f"{auto:>10}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply the six C2 threshold configurations to a cached "
                    "probability matrix from the fine-tuned classifier."
    )
    parser.add_argument("--probs", type=Path, default=DEFAULT_PROBS_PATH)
    parser.add_argument("--test", type=Path, default=DEFAULT_TEST_PATH)
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=f"Base model name. Auto-detected from {DEFAULT_MODEL_DIR}/model_card.md if not set.",
    )
    parser.add_argument(
        "--exclude",
        type=str,
        default=None,
        choices=PERMISSIONS,
        help="Assume an external deterministic rule handles this permission "
             "perfectly (hybrid-architecture analysis). The classifier's "
             "prediction on this permission is replaced with ground_truth.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path. Default: results/<short_model>_sweep.json. "
             "If the file exists, the run is merged in under its condition key.",
    )
    args = parser.parse_args()

    if args.model:
        model_name, training_epochs = args.model, None
    else:
        model_name, training_epochs = detect_model_name()
    short_model = model_name.split("/")[-1].replace("-", "_")

    output_path = args.output or Path(f"results/{short_model}_sweep.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    entry = run_sweep_from_probs(
        args.probs,
        args.test,
        model_name=model_name,
        training_epochs=training_epochs,
        exclude=args.exclude,
    )

    existing = json.loads(output_path.read_text()) if output_path.exists() else {}
    existing[entry["condition"]] = entry
    output_path.write_text(json.dumps(existing, indent=2))

    label = f"Model: {model_name}"
    if training_epochs:
        label += f" ({training_epochs} epochs)"
    if args.exclude:
        label += f"; oracle on {args.exclude}"
    print(label)
    _print_table(entry)
    print(f"\nWrote → {output_path}  "
          f"({output_path.stat().st_size:,} bytes)  "
          f"under key {entry['condition']!r}")


if __name__ == "__main__":
    main()

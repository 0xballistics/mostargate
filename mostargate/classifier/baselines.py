"""
Baselines for C2 — to verify that DeBERTa fine-tuning is load-bearing.

Two baselines, both evaluated on dataset/test.json:

1. TF-IDF + one-vs-rest logistic regression (sklearn) — the simplest
   text-classification baseline. Trained on dataset/train.json.
2. Few-shot Claude Haiku 4.5 — asks for confidence floats per permission,
   caches a single 100×15 score matrix, and applies the six C2 threshold
   configurations post-hoc. One API run, six operating points.

Results are written to results/classifier_baselines.json in the same
per-condition shape as results/c0.json / c1.json so the Phase E comparison
report ingests them uniformly. The Claude scores are cached at
dataset/classifier_artifacts/claude_haiku_scores.json so threshold sweeps
and re-runs do not re-call the API.

Usage:
    uv run -m mostargate.classifier.baselines                          # both baselines
    uv run -m mostargate.classifier.baselines --baseline tfidf         # fast, no API
    uv run -m mostargate.classifier.baselines --baseline claude        # uses cached scores if present
    uv run -m mostargate.classifier.baselines --baseline claude --refresh-claude-cache
"""
import argparse
import json
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multioutput import MultiOutputClassifier

from ..experiments.metrics import evaluate, summarise
from .data import PERMISSIONS, build_label_matrix, load_records
from .sweep import THRESHOLD_CONFIGS, apply_thresholds_dict

load_dotenv()

HAIKU_MODEL = "claude-haiku-4-5-20251001"

BASELINES_RESULTS_PATH = Path("results/classifier_baselines.json")
CLAUDE_SCORES_CACHE_PATH = Path("dataset/classifier_artifacts/claude_haiku_scores.json")


def _update_baselines_file(key: str, entry: dict) -> None:
    """Merge a single entry into results/classifier_baselines.json."""
    BASELINES_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if BASELINES_RESULTS_PATH.exists():
        data = json.loads(BASELINES_RESULTS_PATH.read_text())
    data[key] = entry
    BASELINES_RESULTS_PATH.write_text(json.dumps(data, indent=2))


# ────────────────────────────────────────────────────────────────────────────
# TF-IDF + logreg
# ────────────────────────────────────────────────────────────────────────────

def run_tfidf_logreg(train_records: list[dict], test_records: list[dict]) -> list[dict]:
    """Fit TF-IDF + per-label logreg on train, predict on test."""
    train_prompts = [r["prompt"] for r in train_records]
    train_labels = build_label_matrix(train_records)

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=10000)
    X_train = vectorizer.fit_transform(train_prompts)

    clf = MultiOutputClassifier(
        LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)
    )
    clf.fit(X_train, train_labels)

    test_prompts = [r["prompt"] for r in test_records]
    X_test = vectorizer.transform(test_prompts)
    predictions = clf.predict(X_test)

    results = []
    for i, record in enumerate(test_records):
        granted = {p for j, p in enumerate(PERMISSIONS) if predictions[i, j] > 0.5}
        results.append(evaluate(record, granted))
    return results


# ────────────────────────────────────────────────────────────────────────────
# Few-shot Claude Haiku
# ────────────────────────────────────────────────────────────────────────────

# Picked from dataset/train.json to span departments and permission combinations
FEWSHOT_EXAMPLES = [
    {
        "department": "Engineering",
        "prompt": (
            "Find the Stripe webhook handling code in the repo and check whether we're "
            "doing signature validation correctly. Loop in the payments squad on Slack "
            "with a quick assessment."
        ),
        "permissions": ["github_read", "slack_write"],
    },
    {
        "department": "Customer Success",
        "prompt": (
            "Draft a renewal proposal for the Acme account using their current contract "
            "terms and send it to their procurement contact at procurement@acme.com."
        ),
        "permissions": ["salesforce_read", "email_send_external"],
    },
    {
        "department": "Data and Analytics",
        "prompt": (
            "Pull Q3 revenue by region from the warehouse, enrich with current FX rates "
            "from the ECB API, and export the result as a CSV for the board pack."
        ),
        "permissions": ["database_read", "http_request", "export_file"],
    },
    {
        "department": "Legal and Compliance",
        "prompt": (
            "Review the attached vendor NDA for non-standard risk clauses and cross-check "
            "against our standard NDA template in Confluence."
        ),
        "permissions": ["file_read_uploaded", "confluence_read"],
    },
    {
        "department": "Finance",
        "prompt": (
            "Reconcile this month's payroll figures against the database, then email a "
            "summary to the audit firm at audit@bigfour.com."
        ),
        "permissions": ["database_read", "email_send_external"],
    },
    {
        "department": "Engineering",
        "prompt": "What's our company policy on open-sourcing internal tooling?",
        "permissions": ["confluence_read"],
    },
]


# ────────────────────────────────────────────────────────────────────────────
# Claude few-shot — returns confidence floats; threshold-swept downstream
# ────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """\
You score enterprise AI task prompts for permission requirements.

Given a task description, output ONLY a JSON object with exactly 15 numeric fields, one per permission. Each value is a confidence score between 0.0 and 1.0, where:
  - 0.0  = the task definitely does NOT require this permission
  - 1.0  = the task definitely requires this permission
  - 0.5  = genuinely uncertain
Use intermediate values to reflect your actual confidence. No preamble, no markdown fences, no commentary — just the JSON object.

The 15 permissions are:
{perms_list}

Scoring rules:
1. Score a permission high (>0.5) only if the task genuinely cannot be completed without it.
2. When in doubt, score below 0.5.
3. Score based on what the task explicitly requires — not on what the agent might find useful.
4. Express genuine uncertainty with values near 0.5 rather than always returning 0.1 or 0.9.

Examples:
{fewshot_block}
Output schema (every field required, all floats in [0.0, 1.0]):
{schema}

Now score the task in the next user message. Output ONLY the JSON object."""


def build_system_prompt() -> str:
    """System prompt asking for per-permission confidence floats in [0.0, 1.0].

    Cached across the 100 test calls. Each call returns a 15-dim vector of
    floats; downstream code thresholds it six different ways to produce six
    Claude operating points (the same six configs we'll apply to DeBERTa).
    """
    perms_list = "\n".join(f"- {p}: {desc}" for p, desc in constants.TOOLS.items())

    fewshot_block = ""
    for i, ex in enumerate(FEWSHOT_EXAMPLES, 1):
        # Map "granted" examples to 0.90 confidence, "denied" to 0.10 — encourages
        # the model to interpolate between extremes rather than always 0/1.
        conf_dict = {p: (0.90 if p in ex["permissions"] else 0.10) for p in PERMISSIONS}
        fewshot_block += (
            f"\nExample {i} (department: {ex['department']}):\n"
            f"Task: {ex['prompt']}\n"
            f"Output: {json.dumps(conf_dict)}\n"
        )

    schema = json.dumps({p: 0.0 for p in PERMISSIONS}, indent=2)
    return SYSTEM_PROMPT_TEMPLATE.format(
        perms_list=perms_list,
        fewshot_block=fewshot_block,
        schema=schema,
    )


def claude_score_one(client, system_prompt: str, task: str) -> tuple[dict, object]:
    """Single Claude call returning a dict[permission, float in [0,1]]."""
    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=600,
        temperature=0,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": task}],
    )
    raw = next(b.text for b in response.content if b.type == "text")
    try:
        parsed = parse_response(raw)
        scores: dict[str, float] = {}
        for p in PERMISSIONS:
            v = parsed.get(p, 0.0)
            # Tolerate bool fallback in case Claude reverts to boolean output
            if isinstance(v, bool):
                v = 1.0 if v else 0.0
            v = float(v)
            scores[p] = max(0.0, min(1.0, v))  # clip into [0,1]
    except (ValueError, json.JSONDecodeError, TypeError) as e:
        print(f"  WARN: parse failure ({e}); defaulting to all-zero. Raw: {raw[:200]!r}")
        scores = {p: 0.0 for p in PERMISSIONS}
    return scores, response.usage


def run_claude_haiku(test_records: list[dict]) -> tuple[list[dict], dict]:
    """Run Claude once per test record, return raw confidence scores + usage."""
    client = anthropic.Anthropic()
    system_prompt = build_system_prompt()
    print(f"  system prompt length (chars): {len(system_prompt)}")

    all_scores: list[dict] = []
    cache_creation = 0
    cache_read = 0
    output_tokens = 0
    input_tokens_uncached = 0

    for i, record in enumerate(test_records):
        if i % 10 == 0:
            print(f"  Claude Haiku (probabilistic): {i}/{len(test_records)}")
        scores, usage = claude_score_one(client, system_prompt, record["prompt"])
        all_scores.append(scores)
        cache_creation += getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0
        output_tokens += usage.output_tokens
        input_tokens_uncached += getattr(usage, "input_tokens", 0) or 0
        time.sleep(0.05)

    return all_scores, {
        "cache_creation_input_tokens": cache_creation,
        "cache_read_input_tokens": cache_read,
        "input_tokens_uncached": input_tokens_uncached,
        "output_tokens": output_tokens,
    }


def parse_response(text: str) -> dict:
    """Robust parse: strip fences, find outermost JSON object."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object found in response: {text[:200]!r}")
    return json.loads(text[start : end + 1])


# ────────────────────────────────────────────────────────────────────────────
# Top-level baseline runners — each writes its entry into the merged JSON
# ────────────────────────────────────────────────────────────────────────────

def run_baseline_tfidf(train_records: list[dict], test_records: list[dict]) -> dict:
    results = run_tfidf_logreg(train_records, test_records)
    return {
        "condition": "tfidf_logreg",
        "description": (
            "Baseline: TF-IDF (n-grams 1-2, 10k features) + one-vs-rest "
            "logistic regression with class_weight=balanced, trained on the "
            "500-record training split. Decision threshold = 0.5 (sklearn predict default)."
        ),
        "summary": summarise(results),
        "results": results,
    }


def run_baseline_claude(
    test_records: list[dict], refresh_cache: bool = False
) -> dict:
    """Claude few-shot + 6-config threshold sweep.

    Uses the cached score matrix at CLAUDE_SCORES_CACHE_PATH when present
    (and refresh_cache is False); otherwise calls the API and writes the
    cache. The six threshold configs from THRESHOLD_CONFIGS are then
    applied post-hoc with no further API calls.
    """
    if not refresh_cache and CLAUDE_SCORES_CACHE_PATH.exists():
        print(f"  Loading cached Claude scores from {CLAUDE_SCORES_CACHE_PATH}")
        cache = json.loads(CLAUDE_SCORES_CACHE_PATH.read_text())
        scores = cache["scores"]
        usage = cache.get("usage", {})
    else:
        if refresh_cache:
            print("  --refresh-claude-cache set; calling Claude API...")
        else:
            print(f"  No cache at {CLAUDE_SCORES_CACHE_PATH}; calling Claude API...")
        scores, usage = run_claude_haiku(test_records)
        CLAUDE_SCORES_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CLAUDE_SCORES_CACHE_PATH.write_text(json.dumps({
            "records": [r["id"] for r in test_records],
            "scores": scores,
            "usage": usage,
        }, indent=2))
        print(f"  Cached scores → {CLAUDE_SCORES_CACHE_PATH}")

    configurations: dict = {}
    for name, thr_map in THRESHOLD_CONFIGS.items():
        results = apply_thresholds_dict(scores, thr_map, test_records)
        configurations[name] = {
            "config": thr_map,
            "summary": summarise(results),
            "results": results,
        }

    return {
        "condition": "claude_haiku_fewshot",
        "description": (
            f"Few-shot Claude Haiku ({HAIKU_MODEL}, 6 examples): single API "
            "run returns per-permission confidence scores; 6 threshold "
            "configurations applied post-hoc."
        ),
        "usage": usage,
        "configurations": configurations,
    }


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────

def _print_summary_line(s: dict) -> None:
    print(
        f"  sev-d: {s['mean_severity_weighted_delta']:.2f}  "
        f"overshoot: {s['overshoot_rate']:.1%}  "
        f"undershoot: {s['undershoot_rate']:.1%}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run classifier baselines.")
    parser.add_argument(
        "--baseline",
        choices=["tfidf", "claude", "all"],
        default="all",
        help="Which baseline(s) to run (default: all)",
    )
    parser.add_argument(
        "--refresh-claude-cache",
        action="store_true",
        help="For --baseline claude, force a fresh API call instead of "
             "loading cached scores from dataset/classifier_artifacts/claude_haiku_scores.json",
    )
    args = parser.parse_args()

    train_records = load_records("dataset/train.json")
    test_records = load_records("dataset/test.json")
    print(f"Loaded {len(train_records)} train, {len(test_records)} test records.\n")

    if args.baseline in ("tfidf", "all"):
        print("─── TF-IDF + logreg baseline ───")
        entry = run_baseline_tfidf(train_records, test_records)
        _update_baselines_file("tfidf_logreg", entry)
        _print_summary_line(entry["summary"])
        print()

    if args.baseline in ("claude", "all"):
        print("─── Claude Haiku few-shot + 6-config threshold sweep ───")
        entry = run_baseline_claude(
            test_records, refresh_cache=args.refresh_claude_cache
        )
        _update_baselines_file("claude_haiku_fewshot", entry)
        for name, c in entry["configurations"].items():
            s = c["summary"]
            print(
                f"  {name:<24} "
                f"sev-d={s['mean_severity_weighted_delta']:>5.2f}  "
                f"o={s['overshoot_rate']:>5.1%}  "
                f"u={s['undershoot_rate']:>5.1%}"
            )
        print()

    print(f"Results in {BASELINES_RESULTS_PATH}")


if __name__ == "__main__":
    main()

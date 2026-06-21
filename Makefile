.PHONY: all init \
        dataset-generate dataset-requests dataset-labels dataset-merge \
        dataset-validate dataset-stats dataset-split \
        validate-human validate-compare validate-review \
        experiments \
        baselines baseline-tfidf baseline-claude baseline-claude-refresh \
        clean

# ── Full pipeline ──────────────────────────────────────────────────────────────
all: dataset-generate dataset-validate dataset-split

init:
	uv venv
	uv sync

# ── Dataset generation ─────────────────────────────────────────────────────────
dataset-generate: dataset-requests dataset-labels dataset-merge

dataset-requests:
	uv run -m mostargate.dataset_generator.request_generator

dataset-labels:
	uv run -m mostargate.dataset_generator.label_generator

dataset-merge:
	uv run -m mostargate.dataset_generator.merge

# ── Dataset quality ────────────────────────────────────────────────────────────
dataset-validate:
	uv run -m mostargate.dataset_generator.validate

dataset-stats:
	uv run -m mostargate.dataset_generator.metrics dataset

dataset-split:
	uv run -m mostargate.dataset_generator.split

# ── Human validation pipeline ─────────────────────────────────────────────────
# Step 1: label 60 sampled records interactively
validate-human:
	uv run -m mostargate.dataset_generator.validate_human

# Step 2: compare human labels vs LLM, generate disagreements.json + pre-review metrics
#         add --refresh to regenerate disagreements.json from scratch
validate-compare:
	uv run -m mostargate.dataset_generator.metrics compare

# Step 3: resolve disagreements interactively (resumable)
validate-review:
	uv run -m mostargate.dataset_generator.metrics review

# ── Experiments ────────────────────────────────────────────────────────────────
experiments:
	uv run -m mostargate.experiments.run

# ── Classifier baselines ───────────────────────────────────────────────────────
# Both baselines: TF-IDF + Claude few-shot with 6-config threshold sweep.
# First Claude run costs ~$0.30 in API; subsequent runs use the cached score matrix.
baselines:
	uv run -m mostargate.classifier.baselines --baseline all

# Fast, no API. TF-IDF + logreg at threshold 0.5 only.
baseline-tfidf:
	uv run -m mostargate.classifier.baselines --baseline tfidf

# Claude Haiku 4.5 few-shot + 6-config threshold sweep. Uses cached scores if
# present; only calls the API on first run or when the cache is missing.
baseline-claude:
	uv run -m mostargate.classifier.baselines --baseline claude

# Force a fresh Claude API call (re-generates the score cache).
baseline-claude-refresh:
	uv run -m mostargate.classifier.baselines --baseline claude --refresh-claude-cache

# ── Cleanup ────────────────────────────────────────────────────────────────────
clean:
	zip -r dataset/batches.zip dataset/pass*
	rm -f dataset/pass1_batch_*.json dataset/pass2_batch_*.json

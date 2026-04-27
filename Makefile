.PHONY: all init \
        dataset-generate dataset-requests dataset-labels dataset-merge \
        dataset-validate dataset-stats dataset-split \
        validate-human validate-compare validate-review \
        experiment-run clean

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
experiment-run:
	uv run -m mostargate.experiments.run

# ── Cleanup ────────────────────────────────────────────────────────────────────
clean:
	zip -r dataset/batches.zip dataset/pass*
	rm -f dataset/pass1_batch_*.json dataset/pass2_batch_*.json

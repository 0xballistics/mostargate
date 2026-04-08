.PHONY: all init generate requests labels merge validate stats split validate_human experiment clean

# Full pipeline
all: generate validate split

init:
	uv venv
	uv sync

generate: requests labels merge

requests:
	uv run -m mostargate.dataset_generator.request_generator

labels:
	uv run -m mostargate.dataset_generator.label_generator

merge:
	uv run -m mostargate.dataset_generator.merge

validate:
	uv run -m mostargate.dataset_generator.validate

stats:
	uv run -m mostargate.dataset_generator.stats

split:
	uv run -m mostargate.dataset_generator.split

experiment:
	uv run -m mostargate.experiments.run

validate_human:
	uv run -m mostargate.dataset_generator.validate_human

clean:
	zip -r dataset/batches.zip dataset/pass*
	rm -f dataset/pass1_batch_*.json dataset/pass2_batch_*.json
		

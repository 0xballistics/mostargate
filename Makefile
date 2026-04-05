.PHONY: all generate generate_requests generate_labels merge validate validate_human clean

# Full pipeline
all: generate validate

generate: generate_requests generate_labels merge

generate_requests:
	uv run -m mostargate.dataset_generator.request_generator

generate_labels:
	uv run -m mostargate.dataset_generator.label_generator

merge:
	uv run -m mostargate.dataset_generator.merge

validate:
	uv run -m mostargate.dataset_generator.validate

validate_human:
	uv run -m mostargate.dataset_generator.validate_human

clean:

	rm -f dataset/pass1_batch_*.json dataset/pass2_batch_*.json
		

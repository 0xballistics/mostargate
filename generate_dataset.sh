#!/bin/bash
uv run -m mostargate.dataset_generator.request_generator
uv run -m mostargate.dataset_generator.label_generator
uv run -m mostargate.dataset_generator.merge
uv run -m mostargate.dataset_generator.validate
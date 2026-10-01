SHELL := /bin/bash

.PHONY: setup dev lint format test check fix precommit clean clear

setup:
	./setup.sh

dev:
	./scripts/dev.sh

lint:
	./scripts/lint.sh

format:
	./scripts/format.sh

test:
	./scripts/test.sh

check: lint test

fix: format test

precommit:
	.venv/bin/pre-commit run --all-files

# Remove runtime outputs and local caches (keeps .venv, source, and data/review.db).
clean:
	rm -rf out/ data/runs data/raw data/drafts data/artifacts data/form_*.json
	rm -rf __pycache__/ .pytest_cache/ .mypy_cache/ .ruff_cache/ .coverage htmlcov/
	find . -type d -name '__pycache__' -not -path './.venv/*' -prune -exec rm -rf {} +
	@echo "Cleaned out/, data pipeline scratch, caches. .venv and review.db kept. For a blank terminal use shell: clear"

# Alias — people often type `make clear` after shell `clear`.
clear: clean

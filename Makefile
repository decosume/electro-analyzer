PYTHON ?= python3
VENV ?= .venv
ACTIVATE = . $(VENV)/bin/activate

.PHONY: setup lint test run clean format typecheck

setup:
	$(PYTHON) -m venv $(VENV)
	$(ACTIVATE) && pip install --upgrade pip
	$(ACTIVATE) && pip install -e ".[dev]"

lint:
	$(ACTIVATE) && ruff check src tests
	$(ACTIVATE) && black --check src tests

format:
	$(ACTIVATE) && ruff check src tests --fix
	$(ACTIVATE) && black src tests

test:
	$(ACTIVATE) && pytest

typecheck:
	$(ACTIVATE) && mypy src

run:
	$(ACTIVATE) && python -m electro_analyzer.cli $(ARGS)

clean:
	rm -rf $(VENV)
	rm -rf build dist .mypy_cache .pytest_cache .ruff_cache
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
	rm -f outputs/*.png

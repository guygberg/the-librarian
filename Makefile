VENV := .venv
BIN := $(VENV)/bin

.PHONY: install check

install:
	python3 -m venv $(VENV)
	$(BIN)/pip install -r requirements.lock
	$(BIN)/pip install --no-deps -e .
	$(BIN)/librarian migrate --existing-only

check:
	$(BIN)/ruff check src tests
	$(BIN)/pytest -q

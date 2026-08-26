# Water Mill's own gate.
#
# The factory holds its targets to a gate, so it holds itself to one. Two rules
# are inherited deliberately from the first project it drives, and both exist
# because breaking them produces a green result that means nothing:
#
#   A step that cannot fail must not be part of a green result. No `|| true`,
#   no `-` prefixes, no `continue-on-error`. `typecheck` prints why there is no
#   type checker and exits non-zero, so it can never contribute to a pass.
#
#   Without `pipefail`, `cmd | tail` reports tail's status. A broken install
#   measured while building the first version of this gate was recorded as a
#   success for exactly that reason.

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

PYTHON ?= python3
VENV := .venv
VENV_PY := $(VENV)/bin/python

.PHONY: help
help:  ## List every target
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

.PHONY: install
install:  ## Create .venv and install dependencies
	$(PYTHON) -m venv $(VENV)
	$(VENV_PY) -m pip install --upgrade pip
	$(VENV_PY) -m pip install -r requirements.txt
	@echo "Installed. Next:  make verify"

.PHONY: verify
verify: guard lint test  ## THE MERGE GATE. Everything below, in order
	@echo
	@echo "verify: passed"

.PHONY: guard
guard:  ## Refuse to run the suite anywhere near a real run's artifacts
	@# The suite drives real git repositories in temp directories. This proves
	@# it is not about to do that inside this checkout, where `runs/` holds the
	@# only record of every night the factory has worked.
	@test -d tests || { echo "guard: no tests/ directory"; exit 1; }
	@if [ -n "$${WATERMILL_ROOT:-}" ]; then \
		echo "guard: WATERMILL_ROOT is set to '$$WATERMILL_ROOT'."; \
		echo "guard: the suite must not be pointed at a real factory root."; \
		exit 1; \
	fi
	@echo "guard: ok"

.PHONY: lint
lint:  ## ruff over the package and the suite
	$(PYTHON) -m ruff check .

.PHONY: format
format:  ## Apply the fixes ruff can make itself
	$(PYTHON) -m ruff check --fix .

.PHONY: test
test:  ## The full suite
	$(PYTHON) -m pytest tests/ -q

.PHONY: test-fast
test-fast:  ## Everything except the tests that drive real subprocesses
	$(PYTHON) -m pytest tests/ -q --ignore=tests/test_engine.py

.PHONY: typecheck
typecheck:  ## Explains that there is no type checker, and fails
	@echo "No type checker is configured for this project."
	@echo
	@echo "This target exists so that absence is stated rather than assumed, and"
	@echo "it exits non-zero so it can never contribute to a green result. A"
	@echo "no-op that succeeds is indistinguishable from a check that ran."
	@exit 1

.PHONY: doctor
doctor:  ## Preflight every registered project, without running its gate
	$(PYTHON) bin/watermill doctor

.PHONY: clean
clean:  ## Remove build artifacts and .venv (never runs/)
	rm -rf $(VENV) .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	@echo "clean: runs/ was left alone -- it is the only record of past nights"

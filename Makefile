# ==============================================================================
# Ledger API Makefile
# ==============================================================================

.DEFAULT_GOAL := help
.ONESHELL:
SHELL := /bin/bash

# Configuration
APP           ?= app.main:app
HOST          ?= 127.0.0.1
PORT          ?= 8000
UVICORN_FLAGS ?= --reload

# Tool wrappers (uses uv run if uv is in PATH, otherwise falls back to .venv/bin/)
VENV          := .venv
VENV_BIN      := $(VENV)/bin
USE_UV        := $(shell which uv 2>/dev/null)

ifeq ($(USE_UV),)
    PYTHON       := $(VENV_BIN)/python
    UVICORN      := $(VENV_BIN)/uvicorn
    ALEMBIC      := $(VENV_BIN)/alembic
    RUFF         := $(VENV_BIN)/ruff
    BASEDPYRIGHT := $(VENV_BIN)/basedpyright
    PYTEST       := $(VENV_BIN)/pytest
else
    PYTHON       := uv run python
    UVICORN      := uv run uvicorn
    ALEMBIC      := uv run alembic
    RUFF         := uv run ruff
    BASEDPYRIGHT := uv run basedpyright
    PYTEST       := uv run pytest
endif

RUFF_CHECK    := $(RUFF) check
RUFF_FORMAT   := $(RUFF) format

.PHONY: help dev run format format-check lint lintfix lint-fix typecheck test check \
        migrate makemigrations downgrade current history clean

# ==============================================================================
# HELP
# ==============================================================================

## help: Display available make targets
help:
	@echo "Ledger API Makefile"
	@echo "==================="
	@echo "Usage: make [target]"
	@echo ""
	@echo "Development:"
	@echo "  dev            Start FastAPI dev server with auto-reload"
	@echo "  run            Alias for dev"
	@echo ""
	@echo "Code Quality:"
	@echo "  format         Format all Python files using Ruff"
	@echo "  format-check   Check formatting without applying changes"
	@echo "  lint           Run Ruff code linter"
	@echo "  lintfix        Automatically fix lint issues with Ruff"
	@echo "  lint-fix       Alias for lintfix"
	@echo "  typecheck      Run static type checking with BasedPyright"
	@echo "  test           Run test suite with pytest"
	@echo "  check          Run format-check, lint, and typecheck"
	@echo ""
	@echo "Database Migrations:"
	@echo "  makemigrations Generate migration revision (requires m=\"message\")"
	@echo "  migrate        Apply all pending migrations"
	@echo "  downgrade      Rollback the last migration"
	@echo "  current        Show current migration revision"
	@echo "  history        Show migration history"
	@echo ""
	@echo "Cleanup:"
	@echo "  clean          Remove python cache and tool artifacts"

# ==============================================================================
# DEVELOPMENT
# ==============================================================================

## dev: Start FastAPI development server with auto-reload
dev:
	$(UVICORN) $(APP) $(UVICORN_FLAGS) --host $(HOST) --port $(PORT)

## run: Alias for dev target
run: dev

# ==============================================================================
# CODE QUALITY & TESTING
# ==============================================================================

## format: Format all Python files in the repository using Ruff
format:
	$(RUFF_FORMAT) .

## format-check: Verify that all Python files adhere to formatting rules
format-check:
	$(RUFF_FORMAT) --check .

## lint: Check codebase for code quality and style issues with Ruff
lint:
	$(RUFF_CHECK) .

## lintfix: Automatically fix auto-fixable linting issues with Ruff
lintfix:
	$(RUFF_CHECK) --fix .

## lint-fix: Alias for lintfix
lint-fix: lintfix

## typecheck: Run static type checks using BasedPyright
typecheck:
	$(BASEDPYRIGHT)

## test: Run test suite with pytest
test:
	$(PYTEST)

## check: Run formatting checks, linter verification, and type checking
check: format-check lint typecheck

# ==============================================================================
# DATABASE MIGRATIONS (ALEMBIC)
# ==============================================================================

## makemigrations: Generate migration revision (requires m="description")
makemigrations:
	@if [ -z "$(m)" ]; then \
		echo "Error: Migration message required. Usage: make makemigrations m=\"your description\""; \
		exit 1; \
	fi
	$(ALEMBIC) revision --autogenerate -m "$(m)"

## migrate: Apply all pending migrations (alembic upgrade head)
migrate:
	$(ALEMBIC) upgrade head

## downgrade: Rollback last migration step (alembic downgrade -1)
downgrade:
	$(ALEMBIC) downgrade -1

## current: Display current migration revision
current:
	$(ALEMBIC) current

## history: Display migration history
history:
	$(ALEMBIC) history

# ==============================================================================
# CLEANUP
# ==============================================================================

## clean: Clean python bytecode and tool cache directories
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .ruff_cache .pytest_cache

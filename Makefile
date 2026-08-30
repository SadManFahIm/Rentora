# Rentora — monorepo command aliases
#
# Windows local dev: Python venv at backend/venv (Scripts), Node deps in frontend.
# Commands:
#   make help          list targets
#   make setup         install Python + Node dependencies
#   make dev           run backend (:8000) + frontend (:3001) together
#   make run-backend   Django dev server only
#   make run-frontend  Vite dev server only
#   make migrate       apply Django migrations
#   make seed          (re)seed demo data used by screenshots
#   make test          run backend + frontend unit suites
#   make check         full local pre-PR gate (lint + format + types + tests)

VENV    := backend/venv/Scripts/python.exe
PY      := $(if $(shell test -f $(VENV) && echo y),$(VENV),python)
MANAGE  := $(PY) manage.py

.PHONY: help setup install dev run-backend run-frontend migrate seed test test-backend test-frontend lint format format-check types build check clean screenshots

help: ## List all commands
	@printf 'Rentora monorepo commands:\n\n'
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## Install everything (Python deps + Node deps) — first time only
	python -m venv backend/venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r backend/requirements.txt
	cd frontend && npm ci

install: setup ## Alias for setup

dev: ## Run backend (:8000) + frontend (:3001) together
	@echo "Starting backend :8000 and frontend :3001…"
	$(MAKE) run-backend &
	$(MAKE) run-frontend &
	wait

run-backend: ## Django dev server on :8000
	cd backend && $(PY) manage.py runserver 0.0.0.0:8000

run-frontend: ## Vite dev server on :3001
	cd frontend && npm run dev

migrate: ## Apply migrations
	cd backend && $(MANAGE) migrate

seed: ## Seed demo data used by the screenshot galleries
	cd backend && $(MANAGE) register_rental_agent

test: test-backend test-frontend ## Backend + frontend unit tests

test-backend: ## Django test suite
	cd backend && $(MANAGE) test

test-frontend: ## Vitest suite
	cd frontend && npm run test:coverage

lint: ## ESLint + ruff + tsc typecheck
	cd frontend && npm run lint
	cd backend && $(PY) -m ruff check .
	cd frontend && npx tsc --noEmit

format: ## Prettier (TS), ruff (Python)
	cd frontend && npm run format
	cd backend && $(PY) -m ruff check --fix .

format-check: ## Prettier + ruff dry-run (same as CI)
	cd frontend && npm run format:check
	cd backend && $(PY) -m ruff check .

types: ## TypeScript strict typecheck
	cd frontend && npx tsc --noEmit

build: ## Production build
	cd frontend && npm run build

check: lint format-check test build ## Full pre-PR gate (mirrors CI)

clean: ## Remove generated/cached artifacts
	rm -rf frontend/build frontend/coverage backend/htmlcov .ruff_cache
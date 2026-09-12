SHELL := /bin/sh

.DEFAULT_GOAL := help

BACKEND_HOST ?= 127.0.0.1
BACKEND_PORT ?= 8000
FRONTEND_HOST ?= localhost
FRONTEND_PORT ?= 5173
API_BASE_URL ?= http://$(BACKEND_HOST):$(BACKEND_PORT)

.PHONY: help setup install run backend frontend migrate test lint build check

help: ## Show the available commands
	@awk 'BEGIN { FS = ":.*## " } /^[a-zA-Z_-]+:.*## / { printf "  %-10s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

setup: ## Install backend and frontend dependencies
	uv sync
	npm --prefix frontend install

install: setup ## Alias for setup

run: ## Run the backend and frontend development servers
	@set -eu; \
	$(MAKE) --no-print-directory backend & backend_pid=$$!; \
	$(MAKE) --no-print-directory frontend & frontend_pid=$$!; \
	trap 'kill "$$backend_pid" "$$frontend_pid" 2>/dev/null || true' INT TERM EXIT; \
	wait "$$backend_pid" "$$frontend_pid"

backend: ## Run the backend development server
	uv run uvicorn backend.main:app --reload --host $(BACKEND_HOST) --port $(BACKEND_PORT)

frontend: ## Run the frontend development server
	VITE_API_BASE_URL=$(API_BASE_URL) npm --prefix frontend run dev -- --host $(FRONTEND_HOST) --port $(FRONTEND_PORT)

migrate: ## Upgrade the database to the latest migration
	uv run alembic -c backend/alembic.ini upgrade head

test: ## Run the backend test suite
	uv run pytest

lint: ## Lint the frontend
	npm --prefix frontend run lint

build: ## Build the frontend for production
	npm --prefix frontend run build

check: test lint build ## Run all automated checks

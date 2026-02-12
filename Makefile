.PHONY: help setup run dev test dev-mode docker clean

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PORT := 8000

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Create virtual environment and install dependencies
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env from .env.example — edit it to add your API key"; fi

run: ## Start the application (port 8000)
	$(PYTHON) -m uvicorn app.main:app --host 0.0.0.0 --port $(PORT)

dev: ## Start with hot reload for development
	$(PYTHON) -m uvicorn app.main:app --host 0.0.0.0 --port $(PORT) --reload

test: ## Run the test suite
	$(PYTHON) -m pytest -v

dev-mode: ## Start in dev mode (mock responses, no API key needed)
	DEV_MODE=true $(PYTHON) -m uvicorn app.main:app --host 0.0.0.0 --port $(PORT) --reload

docker: ## Build and run with Docker Compose
	docker compose up --build

clean: ## Remove venv, caches, and generated files
	rm -rf $(VENV) __pycache__ .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true

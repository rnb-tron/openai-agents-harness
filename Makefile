# Agent Harness Makefile

PYTHON ?= venv/bin/python
PIP ?= venv/bin/pip

.PHONY: help install dev run test test-integration test-e2e test-all clean format lint

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	$(PIP) install -r requirements.txt
	$(PIP) install -e .

dev: ## Install development dependencies
	$(PIP) install -e ".[dev]"

run: ## Run the application
	ENVTYPE=test $(PYTHON) -m uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload

test: ## Run unit tests
	$(PYTHON) -m pytest tests/unit -v

test-integration: ## Run local integration tests
	$(PYTHON) -m pytest tests/integration -v

test-e2e: ## Run e2e tests; external checks are skipped unless RUN_EXTERNAL_TESTS=true
	$(PYTHON) -m pytest tests/e2e -v

test-all: ## Run unit, integration, and e2e tests
	$(PYTHON) -m pytest tests/unit tests/integration tests/e2e -v

test-cov: ## Run tests with coverage
	$(PYTHON) -m pytest tests/unit -v --cov=src --cov-report=html

format: ## Format code
	black src/ tests/
	ruff check --fix src/ tests/

lint: ## Lint code
	ruff check src/ tests/
	mypy src/

clean: ## Clean up
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/ dist/ .pytest_cache/ .mypy_cache/ htmlcov/

migrate: ## Run database migrations
	# Add migration commands here

seed: ## Seed database with initial data
	# Add seed commands here

docker-build: ## Build Docker image
	docker build -t openai-agent-sdk:latest -f docker/Dockerfile .

docker-run: ## Run Docker container
	docker-compose up -d

docker-stop: ## Stop Docker containers
	docker-compose down

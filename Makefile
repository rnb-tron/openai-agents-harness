# Agent Harness Makefile

.PHONY: help install dev run test clean format lint

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	pip install -r requirements.txt
	pip install -e .

dev: ## Install development dependencies
	pip install -e ".[dev]"

run: ## Run the application
	ENVTYPE=test python -m uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload

test: ## Run tests
	python -m pytest tests/ -v

test-cov: ## Run tests with coverage
	python -m pytest tests/ -v --cov=src --cov-report=html

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

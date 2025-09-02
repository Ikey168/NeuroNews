.PHONY: help install test lint format clean build deploy

help:
	@echo "Available commands:"
	@echo "  install    Install dependencies"
	@echo "  test       Run tests"
	@echo "  lint       Run linting"
	@echo "  format     Format code"
	@echo "  clean      Clean artifacts"
	@echo "  build      Build application"
	@echo "  deploy     Deploy application"

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v --cov=src/neuronews --cov-report=html

lint:
	flake8 src/ tests/
	mypy src/

format:
	black src/ tests/
	isort src/ tests/

clean:
	rm -rf .artifacts/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build:
	docker build -t neuronews -f deploy/docker/Dockerfile .

deploy:
	docker-compose -f deploy/docker/docker-compose.yml up -d

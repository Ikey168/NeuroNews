# Multi-stage Dockerfile for NeuroNews
FROM python:3.12-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash neuronews
USER neuronews
WORKDIR /home/neuronews/app

# Install Python dependencies
COPY --chown=neuronews:neuronews requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Development stage with additional tools
FROM base as development
USER root
RUN apt-get update && apt-get install -y \
    git \
    vim \
    && rm -rf /var/lib/apt/lists/*
USER neuronews

# Copy application code
COPY --chown=neuronews:neuronews . .

# Set Python path
ENV PYTHONPATH=/home/neuronews/app

# Default command for development
CMD ["python", "-m", "pytest", "-v"]

# Production stage
FROM base as production
# Copy only necessary files for production
COPY --chown=neuronews:neuronews src/ ./src/
COPY --chown=neuronews:neuronews config/ ./config/
COPY --chown=neuronews:neuronews *.py ./

ENV PYTHONPATH=/home/neuronews/app
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Test-minimal stage for basic connectivity testing
FROM base as test-minimal

USER neuronews
WORKDIR /home/neuronews/app

# Copy minimal test requirements
COPY --chown=neuronews:neuronews requirements-test-minimal.txt .

# Install minimal test dependencies
RUN pip install --user --no-cache-dir -r requirements-test-minimal.txt

# Copy test connectivity script
COPY --chown=neuronews:neuronews tests/test_connectivity.py .

# Health check for test environment
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import psycopg2; print('Test environment ready')" || exit 1

# Default command for running connectivity tests
CMD ["python", "test_connectivity.py"]

# Test stage
FROM development as test
# Copy test files
COPY --chown=neuronews:neuronews tests/ ./tests/

# Install test dependencies
RUN pip install --user pytest-cov pytest-asyncio pytest-mock

# Run tests by default
CMD ["python", "-m", "pytest", "--cov=src", "--cov-report=html", "--cov-report=term-missing", "-v"]

# NeuroNews FastAPI Application Docker Image
FROM python:3.11-slim as base

LABEL maintainer="NeuroNews Team"
LABEL description="NeuroNews FastAPI Application"
LABEL version="1.0.0"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN groupadd --gid 1001 neuronews && \
    useradd --uid 1001 --gid neuronews --shell /bin/bash --create-home neuronews

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies as root
RUN pip install --no-cache-dir -r requirements.txt

# Development stage
FROM base as development

# Install additional development tools
RUN apt-get update && apt-get install -y \
    git \
    vim \
    htop \
    && rm -rf /var/lib/apt/lists/*

# Switch to non-root user
USER neuronews

# Copy application code
COPY --chown=neuronews:neuronews . .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command for development
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Production stage
FROM base as production

# Switch to non-root user
USER neuronews

# Copy only necessary files for production
COPY --chown=neuronews:neuronews src/ ./src/
COPY --chown=neuronews:neuronews config/ ./config/
COPY --chown=neuronews:neuronews requirements.txt ./

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Command for production
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

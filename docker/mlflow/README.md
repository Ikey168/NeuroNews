# MLflow Tracking Server

This directory contains the MLflow tracking server setup with PostgreSQL backend for the NeuroNews project.

## Quick Start

```bash
# Start MLflow tracking server
make mlflow-up

# Open MLflow UI
make mlflow-ui

# Stop MLflow tracking server
make mlflow-down
```

## Services

- **MLflow Server**: Runs on `http://localhost:5001`
- **PostgreSQL Database**: Runs on port `5433` (to avoid conflicts)
- **Artifact Storage**: Local filesystem at `./mlruns`

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   MLflow UI     │────│ MLflow Server   │────│   PostgreSQL    │
│ localhost:5001  │    │                 │    │   Backend       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                                │
                        ┌─────────────────┐
                        │  File System    │
                        │   Artifacts     │
                        │   ./mlruns      │
                        └─────────────────┘
```

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and modify as needed:

```bash
cp .env.example .env
```

Key configurations:
- `MLFLOW_PORT=5001` - MLflow server port
- `POSTGRES_PORT=5433` - PostgreSQL port (avoid conflicts)
- `MLFLOW_ARTIFACTS_DIR=./mlruns` - Local artifact storage

### Backend Store URI

```
postgresql+psycopg2://mlflow:mlflow@mlflow-db:5432/mlflow
```

### Artifact Root

```
/mlflow/artifacts
```

## Usage

### Creating Experiments

```python
import mlflow

# Set tracking URI
mlflow.set_tracking_uri("http://localhost:5001")

# Create experiment
experiment_id = mlflow.create_experiment("news_sentiment_analysis")

# Start a run
with mlflow.start_run(experiment_id=experiment_id):
    # Log parameters
    mlflow.log_param("model_type", "bert")
    mlflow.log_param("learning_rate", 0.001)
    
    # Log metrics
    mlflow.log_metric("accuracy", 0.95)
    mlflow.log_metric("f1_score", 0.93)
    
    # Log artifacts
    mlflow.log_artifact("model.pkl")
```

## Health Checks

The services include health checks:

- **MLflow Server**: `curl -f http://localhost:5001/health`
- **PostgreSQL**: `pg_isready -U mlflow -d mlflow`

## Troubleshooting

### Port Conflicts

If you have PostgreSQL running locally on port 5432, the MLflow database uses port 5433 to avoid conflicts.

### Permissions

Ensure the `./mlruns` and `./logs` directories are writable:

```bash
chmod 755 ./mlruns ./logs
```

### Database Connection

If you see connection errors, ensure PostgreSQL is healthy:

```bash
docker-compose -f docker-compose.mlflow.yml ps
docker-compose -f docker-compose.mlflow.yml logs mlflow-db
```

## Integration with NeuroNews

This MLflow setup is designed to track experiments for:

- Sentiment analysis models
- NLP pipeline optimization
- Model performance monitoring
- A/B testing results

See the main project documentation for specific integration examples.

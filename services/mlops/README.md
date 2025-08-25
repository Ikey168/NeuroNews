# MLflow Python Tracking Helper

A standardized MLflow tracking helper for NeuroNews ML experiments that automatically sets common tags, parameters, and metadata.

## Features

- 🏷️ **Automatic Standard Tags**: git SHA, branch, environment, hostname, code version
- 🌍 **Environment Detection**: Automatically detects dev/ci/prod environments
- 📊 **Context Manager**: Simple `mlrun()` context manager for experiment tracking
- ⚙️ **Configurable**: Environment variables for tracking URI and experiment names
- 🧪 **Well Tested**: Comprehensive unit and integration tests

## Quick Start

```python
from services.mlops.tracking import mlrun
import mlflow

# Basic usage
with mlrun("my-experiment") as run:
    mlflow.log_param("learning_rate", 0.01)
    mlflow.log_metric("accuracy", 0.95)
    mlflow.log_artifact("model.pkl")
```

## Standard Tags Applied

The `mlrun` context manager automatically applies these standard tags:

| Tag | Description | Example |
|-----|-------------|---------|
| `git.sha` | Current git commit SHA | `abc123def456` |
| `git.branch` | Current git branch | `feature/sentiment` |
| `env` | Environment (dev/ci/prod) | `dev` |
| `hostname` | Machine hostname | `ml-server-01` |
| `code_version` | Short git SHA or timestamp | `abc123de` |
| `pipeline` | Pipeline name (if set) | `sentiment-analyzer` |

## Environment Configuration

Configure MLflow through environment variables:

```bash
# MLflow server URL
export MLFLOW_TRACKING_URI="http://localhost:5001"

# Default experiment name
export MLFLOW_EXPERIMENT="news-sentiment"

# Pipeline identifier (optional)
export NEURONEWS_PIPELINE="data-preprocessing"
```

Or use the helper function:

```python
from services.mlops.tracking import setup_mlflow_env

setup_mlflow_env("http://localhost:5001", "my-experiment")
```

## Usage Examples

### Basic Experiment Tracking

```python
from services.mlops.tracking import mlrun
import mlflow

with mlrun("sentiment-training", experiment="news-nlp") as run:
    # Log hyperparameters
    mlflow.log_param("model_type", "bert-base-uncased")
    mlflow.log_param("learning_rate", 2e-5)
    mlflow.log_param("batch_size", 32)
    
    # Log metrics during training
    for epoch in range(3):
        accuracy = train_epoch()  # Your training code
        mlflow.log_metric("accuracy", accuracy, step=epoch)
    
    # Log final model
    mlflow.log_artifact("model.pkl")
```

### Custom Tags

```python
custom_tags = {
    "model_version": "v2.1.0",
    "data_source": "twitter",
    "experiment_type": "hyperparameter_tuning"
}

with mlrun("bert-tuning", tags=custom_tags) as run:
    mlflow.log_param("learning_rate", 1e-4)
    mlflow.log_metric("f1_score", 0.89)
```

### Pipeline Context

```python
import os

# Set pipeline context
os.environ["NEURONEWS_PIPELINE"] = "data-preprocessing"

with mlrun("data-cleaning") as run:
    mlflow.log_param("input_format", "json")
    mlflow.log_param("output_format", "parquet")
    mlflow.log_metric("records_processed", 10000)
    
# Pipeline tag will be automatically added
```

## Environment Detection

The helper automatically detects the environment:

- **CI**: Detected when `CI`, `GITHUB_ACTIONS`, `GITLAB_CI`, `JENKINS_URL`, or `TRAVIS` environment variables are present
- **Production**: Detected when `ENV=production` or `ENVIRONMENT=prod`
- **Development**: Default fallback for local development

## Testing

Run the tests:

```bash
# Unit tests only
pytest tests/mlops -m "not integration"

# All tests (requires MLflow server)
make mlflow-up  # Start MLflow server
pytest tests/mlops

# Quick test
pytest -q tests/mlops
```

## Integration with NeuroNews Pipelines

The tracking helper integrates seamlessly with NeuroNews ML pipelines:

### Sentiment Analysis Pipeline

```python
from services.mlops.tracking import mlrun
import mlflow

def train_sentiment_model(data_path, model_config):
    with mlrun("sentiment-bert-training", experiment="news-sentiment") as run:
        # Log data and model configuration
        mlflow.log_param("data_path", data_path)
        mlflow.log_params(model_config)
        
        # Training code here...
        model = train_model(data_path, model_config)
        
        # Log results
        mlflow.log_metric("final_accuracy", model.accuracy)
        mlflow.log_artifact(model.save_path)
        
        return model
```

### Data Processing Pipeline

```python
import os
from services.mlops.tracking import mlrun
import mlflow

def process_news_data(input_path, output_path):
    os.environ["NEURONEWS_PIPELINE"] = "data-preprocessing"
    
    with mlrun("news-data-processing") as run:
        mlflow.log_param("input_path", input_path)
        mlflow.log_param("output_path", output_path)
        
        # Processing logic...
        result = process_data(input_path, output_path)
        
        mlflow.log_metric("records_processed", result.record_count)
        mlflow.log_metric("processing_time_seconds", result.duration)
        
        return result
```

## API Reference

### `mlrun(name, experiment=None, tags=None)`

Context manager for MLflow runs with standardized tagging.

**Parameters:**
- `name` (str): Name for the MLflow run
- `experiment` (str, optional): Experiment name (overrides environment)
- `tags` (dict, optional): Additional custom tags

**Returns:**
- MLflow active run object

### `setup_mlflow_env(tracking_uri, experiment)`

Helper to setup MLflow environment variables.

**Parameters:**
- `tracking_uri` (str): MLflow tracking server URI
- `experiment` (str): Default experiment name

### `get_current_run_info()`

Get information about the current MLflow run context.

**Returns:**
- Dictionary with current run information

## Error Handling

The tracking helper is designed to be robust:

- **Offline Development**: Works without MLflow server (logs warnings)
- **Git Unavailable**: Falls back to timestamp-based versioning
- **Network Issues**: Gracefully handles MLflow server connectivity issues

## Requirements

- `mlflow >= 2.0.0`
- `python >= 3.8`

## Contributing

When adding new features:

1. Add unit tests to `tests/mlops/test_tracking.py`
2. Update this documentation
3. Ensure all tests pass: `pytest tests/mlops`

## Troubleshooting

### MLflow Server Not Available

```
Warning: Could not setup MLflow experiment 'test': Connection refused
```

**Solution**: Start the MLflow server:
```bash
make mlflow-up
```

### Permission Denied for Artifacts

```
Warning: MLflow run failed: [Errno 13] Permission denied: '/mlflow'
```

**Solution**: Check MLflow server artifact storage configuration in `docker/mlflow/docker-compose.mlflow.yml`.

### Git Information Not Available

```
git.sha: unknown
git.branch: unknown
```

**Solution**: Ensure you're running in a git repository, or the warnings can be ignored for non-git environments.

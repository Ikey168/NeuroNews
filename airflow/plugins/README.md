# Airflow ↔ MLflow Integration (Issue #225)

This directory contains the MLflow integration for Airflow DAGs, providing automatic experiment tracking for pipeline runs.

## Features

- **DAG-level tracking**: Each DAG run creates a parent MLflow run with metadata
- **Task-level tracking**: Individual tasks create nested runs under the DAG parent
- **Environment control**: Use `MLFLOW_DISABLED=true` to disable in CI/testing
- **NeuroNews integration**: Follows NeuroNews MLflow conventions and experiments

## Files

- `mlflow_callbacks.py` - Core integration callbacks and utilities
- Example usage in `../dags/news_pipeline.py`

## Usage

### Basic DAG Integration

```python
from mlflow_callbacks import configure_dag_for_mlflow

@dag(
    dag_id='my_pipeline',
    tags=['mlflow:experiment_name'],  # Specify MLflow experiment
    # ... other DAG config
)
def my_pipeline():
    # DAG tasks here
    pass

# Configure MLflow integration
my_dag = my_pipeline()
my_dag = configure_dag_for_mlflow(my_dag)
```

### Environment Configuration

```bash
# Enable MLflow tracking (default)
export MLFLOW_TRACKING_URI="file:./mlruns"
export AIRFLOW_ENV="dev"

# Disable MLflow tracking (e.g., in CI)
export MLFLOW_DISABLED="true"
```

## MLflow Experiment Mapping

DAGs can specify their MLflow experiment using tags:

- `mlflow:neuro_news_indexing` → Uses `neuro_news_indexing` experiment
- `mlflow:neuro_news_ask` → Uses `neuro_news_ask` experiment  
- `mlflow:research_prototypes` → Uses `research_prototypes` experiment
- No tag → Creates experiment named `airflow_{dag_id}`

## Run Metadata

### DAG Runs
- **Tags**: `dag_id`, `run_id`, `execution_date`, `environment`, `pipeline`
- **Parameters**: `schedule_interval`, `max_active_runs`, `catchup`, `task_count`
- **Metrics**: `duration_seconds`, `task_count`, `end_time`

### Task Runs (Nested)
- **Tags**: `task_id`, `try_number`, `operator`, `parent_run_id`
- **Parameters**: `max_tries`, `pool`, `queue`
- **Metrics**: `duration_seconds`

## Testing

Run the test script to validate the integration:

```bash
python /workspaces/NeuroNews/test_mlflow_callbacks.py
```

## Integration with news_pipeline

The `news_pipeline` DAG is configured to use MLflow tracking:

1. **Experiment**: Uses `neuro_news_indexing` (via `mlflow:neuro_news_indexing` tag)
2. **Parent run**: Created for each DAG execution with pipeline metadata
3. **Child runs**: Created for each task (scrape, clean, nlp, publish)
4. **Metrics**: Duration, success/failure status, error details

## Monitoring

When MLflow tracking is enabled, you can monitor pipeline runs via:

1. **MLflow UI**: `mlflow ui --backend-store-uri file:./mlruns`
2. **File system**: Browse `./mlruns` directory structure
3. **Programmatic**: Use MLflow Python API to query runs

## Troubleshooting

### MLflow not working
- Check `MLFLOW_DISABLED` environment variable
- Verify MLflow is installed: `pip install mlflow==2.10.0`
- Check tracking URI: `echo $MLFLOW_TRACKING_URI`

### Missing runs
- Ensure DAG is configured with `configure_dag_for_mlflow()`
- Check Airflow logs for MLflow errors
- Verify experiment exists in MLflow

### Nested runs not appearing
- Check task callbacks are properly configured
- Verify XCom functionality is working
- Look for task-level MLflow errors in logs

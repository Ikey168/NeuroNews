"""
MLflow Tracking Helper for NeuroNews.

This module provides a standardized way to track ML experiments with MLflow,
automatically setting common tags, parameters, and metadata.
"""

import os
import socket
import subprocess
from contextlib import contextmanager
from typing import Dict, Optional, Any
import mlflow
import mlflow.tracking


def _get_git_info() -> Dict[str, str]:
    """Get current git information."""
    git_info = {}
    
    try:
        # Get git commit SHA
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        )
        git_info["sha"] = result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        git_info["sha"] = "unknown"
    
    try:
        # Get git branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        )
        git_info["branch"] = result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        git_info["branch"] = "unknown"
    
    return git_info


def _get_environment() -> str:
    """Determine the current environment (dev/ci/prod)."""
    # Check common CI environment variables
    if any(env_var in os.environ for env_var in [
        "CI", "CONTINUOUS_INTEGRATION", "GITHUB_ACTIONS", 
        "GITLAB_CI", "JENKINS_URL", "TRAVIS"
    ]):
        return "ci"
    
    # Check for production indicators
    if os.environ.get("ENV") == "production" or os.environ.get("ENVIRONMENT") == "prod":
        return "prod"
    
    # Default to development
    return "dev"


def _get_code_version() -> str:
    """Get a code version identifier."""
    git_info = _get_git_info()
    if git_info["sha"] != "unknown":
        return git_info["sha"][:8]  # Short SHA
    
    # Fallback to timestamp if no git
    import time
    return f"local-{int(time.time())}"


def _setup_mlflow_tracking():
    """Setup MLflow tracking URI and experiment from environment variables."""
    # Set tracking URI from environment or default to local
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5001")
    mlflow.set_tracking_uri(tracking_uri)
    
    # Set experiment from environment or create default
    experiment_name = os.environ.get("MLFLOW_EXPERIMENT", "neuronews-default")
    
    try:
        # Try to get existing experiment
        experiment = mlflow.get_experiment_by_name(experiment_name)
        if experiment is None:
            # Create experiment if it doesn't exist
            experiment_id = mlflow.create_experiment(experiment_name)
        else:
            experiment_id = experiment.experiment_id
        
        mlflow.set_experiment(experiment_name)
        return experiment_id
    except Exception as e:
        # If MLflow server is not available, log warning but continue
        print(f"Warning: Could not setup MLflow experiment '{experiment_name}': {e}")
        return None


@contextmanager
def mlrun(name: str, experiment: Optional[str] = None, tags: Optional[Dict[str, Any]] = None):
    """
    Context manager for MLflow runs with standardized tagging.
    
    Args:
        name: Name for the MLflow run
        experiment: Optional experiment name (overrides environment)
        tags: Additional custom tags to add
    
    Yields:
        MLflow active run object
    
    Example:
        with mlrun("sentiment-training", experiment="news-nlp") as run:
            mlflow.log_param("model_type", "bert")
            mlflow.log_metric("accuracy", 0.95)
            mlflow.log_artifact("model.pkl")
    """
    # Setup MLflow tracking
    _setup_mlflow_tracking()
    
    # Override experiment if specified
    if experiment:
        try:
            mlflow.set_experiment(experiment)
        except Exception as e:
            print(f"Warning: Could not set experiment '{experiment}': {e}")
    
    # Gather standard tags and metadata
    git_info = _get_git_info()
    standard_tags = {
        "git.sha": git_info["sha"],
        "git.branch": git_info["branch"],
        "env": _get_environment(),
        "hostname": socket.gethostname(),
        "code_version": _get_code_version(),
    }
    
    # Add pipeline tag if specified in environment
    pipeline = os.environ.get("NEURONEWS_PIPELINE")
    if pipeline:
        standard_tags["pipeline"] = pipeline
    
    # Merge with custom tags
    if tags:
        standard_tags.update(tags)
    
    # Start MLflow run
    try:
        with mlflow.start_run(run_name=name, tags=standard_tags) as run:
            # Log standard parameters
            mlflow.log_param("run_name", name)
            mlflow.log_param("git_sha", git_info["sha"])
            mlflow.log_param("git_branch", git_info["branch"])
            mlflow.log_param("environment", _get_environment())
            mlflow.log_param("hostname", socket.gethostname())
            
            yield run
            
    except Exception as e:
        print(f"Warning: MLflow run failed: {e}")
        # Create a mock run object for offline development
        class MockRun:
            def __init__(self):
                self.info = type('RunInfo', (), {
                    'run_id': 'mock-run-id',
                    'experiment_id': 'mock-experiment-id',
                    'status': 'RUNNING'
                })()
        
        yield MockRun()


def setup_mlflow_env(tracking_uri: str = "http://localhost:5001", experiment: str = "neuronews-default"):
    """
    Helper function to setup MLflow environment variables.
    
    Args:
        tracking_uri: MLflow tracking server URI
        experiment: Default experiment name
    """
    os.environ["MLFLOW_TRACKING_URI"] = tracking_uri
    os.environ["MLFLOW_EXPERIMENT"] = experiment
    
    print(f"MLflow environment setup:")
    print(f"  Tracking URI: {tracking_uri}")
    print(f"  Default Experiment: {experiment}")


def get_current_run_info() -> Dict[str, Any]:
    """
    Get information about the current MLflow run context.
    
    Returns:
        Dictionary with current run information
    """
    try:
        active_run = mlflow.active_run()
        if active_run:
            return {
                "run_id": active_run.info.run_id,
                "experiment_id": active_run.info.experiment_id,
                "status": active_run.info.status,
                "tracking_uri": mlflow.get_tracking_uri(),
            }
        else:
            return {"status": "no_active_run"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

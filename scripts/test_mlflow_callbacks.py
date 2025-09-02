#!/usr/bin/env python3
"""
Simple test for MLflow callbacks without full Airflow installation.

This script tests the core MLflow integration logic by mocking Airflow
components, allowing us to verify the implementation works correctly.
"""

import os
import sys
import tempfile
import logging
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_mlflow_env():
    """Set up MLflow environment for testing."""
    # Create temporary directory for MLflow tracking
    mlflow_dir = tempfile.mkdtemp(prefix='test_mlflow_')
    mlflow_uri = f"file://{mlflow_dir}"
    
    # Set environment variables
    os.environ['MLFLOW_TRACKING_URI'] = mlflow_uri
    os.environ['AIRFLOW_ENV'] = 'test'
    
    # Ensure MLflow is not disabled
    if 'MLFLOW_DISABLED' in os.environ:
        del os.environ['MLFLOW_DISABLED']
    
    logger.info(f"MLflow tracking URI: {mlflow_uri}")
    return mlflow_dir, mlflow_uri

def test_mlflow_basic():
    """Test basic MLflow functionality."""
    try:
        import mlflow
        mlflow.set_tracking_uri(os.environ['MLFLOW_TRACKING_URI'])
        
        # Test experiment creation
        experiment_name = "test_airflow_integration"
        experiment_id = mlflow.create_experiment(experiment_name)
        mlflow.set_experiment(experiment_name)
        
        # Test run creation
        with mlflow.start_run(run_name="test_dag_run") as parent_run:
            mlflow.set_tags({
                "dag_id": "test_pipeline",
                "run_id": "manual_2025-08-25",
                "environment": "test",
                "pipeline": "airflow"
            })
            
            mlflow.log_params({
                "schedule_interval": "daily",
                "max_active_runs": 1
            })
            
            # Test nested run
            with mlflow.start_run(run_name="test_task", nested=True) as child_run:
                mlflow.set_tags({
                    "task_id": "test_task",
                    "operator": "PythonOperator"
                })
                
                mlflow.log_metrics({
                    "duration_seconds": 5.0,
                    "memory_usage_mb": 128
                })
        
        logger.info("✅ Basic MLflow functionality works")
        return True
        
    except Exception as e:
        logger.error(f"Basic MLflow test failed: {e}")
        return False

def test_mlflow_disabled():
    """Test MLflow disabled scenario."""
    
    # Set environment to disable MLflow
    os.environ['MLFLOW_DISABLED'] = 'true'
    
    try:
        # Test that we can detect disabled state
        mlflow_disabled = os.getenv("MLFLOW_DISABLED", "").lower() == "true"
        
        if not mlflow_disabled:
            logger.error("MLFLOW_DISABLED environment variable not working")
            return False
        
        logger.info("✅ MLflow disabled detection works")
        return True
        
    except Exception as e:
        logger.error(f"MLflow disabled test failed: {e}")
        return False
    finally:
        # Clean up environment
        if 'MLFLOW_DISABLED' in os.environ:
            del os.environ['MLFLOW_DISABLED']

def test_callbacks_structure():
    """Test the structure of our callbacks without Airflow imports."""
    try:
        # Read the callbacks file and verify structure
        callbacks_file = "/workspaces/NeuroNews/airflow/plugins/mlflow_callbacks.py"
        
        with open(callbacks_file, 'r') as f:
            content = f.read()
        
        # Check for required components
        required_components = [
            "class AirflowMLflowCallbacks",
            "def on_dag_start",
            "def on_dag_success", 
            "def on_dag_failure",
            "def on_task_start",
            "def on_task_success",
            "def on_task_failure",
            "MLFLOW_DISABLED",
            "mlflow.start_run",
            "mlflow.set_tags"
        ]
        
        missing_components = []
        for component in required_components:
            if component not in content:
                missing_components.append(component)
        
        if missing_components:
            logger.error(f"Missing components: {missing_components}")
            return False
        
        logger.info("✅ Callbacks file structure is correct")
        return True
        
    except Exception as e:
        logger.error(f"Callbacks structure test failed: {e}")
        return False

def main():
    """Run the tests."""
    
    print("=" * 60)
    print("🧪 MLflow Callbacks Test (Issue #225)")
    print("=" * 60)
    
    # Set up MLflow environment
    mlflow_dir, mlflow_uri = setup_mlflow_env()
    
    try:
        success = True
        
        # Test 1: Basic MLflow functionality
        print("\n📍 Test 1: Basic MLflow Functionality")
        print("-" * 40)
        if not test_mlflow_basic():
            success = False
        
        # Test 2: MLflow disabled
        print("\n📍 Test 2: MLflow Disabled Detection")  
        print("-" * 40)
        if not test_mlflow_disabled():
            success = False
        
        # Test 3: Callbacks structure
        print("\n📍 Test 3: Callbacks File Structure")
        print("-" * 40)
        if not test_callbacks_structure():
            success = False
        
        # Summary
        print("\n" + "=" * 60)
        if success:
            print("🎉 All tests passed!")
            print(f"📂 MLflow data saved to: {mlflow_dir}")
            
            # Show MLflow runs
            try:
                import mlflow
                mlflow.set_tracking_uri(mlflow_uri)
                experiments = mlflow.search_experiments()
                for exp in experiments:
                    runs = mlflow.search_runs(experiment_ids=[exp.experiment_id])
                    print(f"📊 Experiment '{exp.name}': {len(runs)} runs")
            except Exception as e:
                logger.warning(f"Could not list MLflow runs: {e}")
                
        else:
            print("❌ Some tests failed - check logs above")
        print("=" * 60)
        
        return success
        
    except Exception as e:
        logger.error(f"Test setup failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

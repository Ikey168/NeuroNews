#!/usr/bin/env python3
"""
Demo: Airflow ↔ MLflow Integration (Issue #225)

This script demonstrates the MLflow callbacks functionality for Airflow,
showing how DAG and task execution is tracked in MLflow with proper
parent-child run relationships.

Features demonstrated:
- DAG-level MLflow run creation with metadata
- Task-level nested runs with detailed tracking
- Environment-based enabling/disabling
- Integration with NeuroNews MLflow conventions
"""

import os
import sys
import tempfile
import logging
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock

# Add project paths to sys.path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
airflow_plugins_path = os.path.join(current_dir, 'airflow', 'plugins')
sys.path.insert(0, project_root)
sys.path.insert(0, current_dir)
sys.path.insert(0, airflow_plugins_path)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_mlflow_env():
    """Set up MLflow environment for demo."""
    # Create temporary directory for MLflow tracking
    mlflow_dir = tempfile.mkdtemp(prefix='demo_mlflow_')
    mlflow_uri = f"file://{mlflow_dir}"
    
    # Set environment variables
    os.environ['MLFLOW_TRACKING_URI'] = mlflow_uri
    os.environ['AIRFLOW_ENV'] = 'demo'
    
    # Ensure MLflow is not disabled
    if 'MLFLOW_DISABLED' in os.environ:
        del os.environ['MLFLOW_DISABLED']
    
    logger.info(f"MLflow tracking URI: {mlflow_uri}")
    return mlflow_dir, mlflow_uri

def create_mock_context(dag_id='news_pipeline', task_id='demo_task'):
    """Create mock Airflow context for testing."""
    
    # Mock DAG
    mock_dag = Mock()
    mock_dag.dag_id = dag_id
    mock_dag.description = "Demo NeuroNews data pipeline"
    mock_dag.tags = ['neuronews', 'data-pipeline', 'mlflow:neuro_news_indexing']
    mock_dag.schedule_interval = timedelta(days=1)
    mock_dag.max_active_runs = 1
    mock_dag.catchup = False
    mock_dag.is_paused = False
    mock_dag.task_ids = ['scrape', 'clean', 'nlp', 'publish']
    
    # Mock DAG run
    mock_dag_run = Mock()
    mock_dag_run.dag_id = dag_id
    mock_dag_run.run_id = f"manual__{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}"
    mock_dag_run.execution_date = datetime.now()
    mock_dag_run.start_date = datetime.now()
    mock_dag_run.get_task_instances = Mock(return_value=[])
    
    # Mock task instance
    mock_task_instance = Mock()
    mock_task_instance.task_id = task_id
    mock_task_instance.try_number = 1
    mock_task_instance.max_tries = 3
    mock_task_instance.pool = 'default_pool'
    mock_task_instance.queue = None
    mock_task_instance.start_date = datetime.now()
    
    # Mock task
    mock_task = Mock()
    mock_task.__class__.__name__ = 'PythonOperator'
    mock_task_instance.task = mock_task
    
    # Mock XCom functionality
    xcom_data = {}
    def xcom_push(key, value):
        xcom_data[key] = value
    def xcom_pull(key):
        return xcom_data.get(key)
    
    mock_task_instance.xcom_push = xcom_push
    mock_task_instance.xcom_pull = xcom_pull
    
    # Create context
    context = {
        'dag': mock_dag,
        'dag_run': mock_dag_run,
        'task_instance': mock_task_instance,
        'airflow': {'version': '2.8.1'}
    }
    
    return context

def demo_dag_lifecycle():
    """Demonstrate complete DAG lifecycle with MLflow tracking."""
    
    try:
        # Import MLflow callbacks
        from mlflow_callbacks import AirflowMLflowCallbacks
        
        # Create callbacks instance
        callbacks = AirflowMLflowCallbacks()
        
        if not callbacks.mlflow_enabled:
            logger.error("MLflow is not enabled - cannot run demo")
            return False
        
        # Create mock context
        context = create_mock_context()
        
        logger.info("🚀 Starting DAG lifecycle demo...")
        
        # 1. DAG Start
        logger.info("📋 DAG Start - Creating parent MLflow run")
        callbacks.on_dag_start(context)
        
        # 2. Task lifecycle for multiple tasks
        tasks = ['scrape', 'clean', 'nlp', 'publish']
        
        for task_id in tasks:
            logger.info(f"⚙️  Task '{task_id}' - Creating nested MLflow run")
            
            # Update context for this task
            task_context = context.copy()
            task_context['task_instance'].task_id = task_id
            
            # Task start
            callbacks.on_task_start(task_context)
            
            # Simulate task execution time
            import time
            time.sleep(0.1)
            
            # Task success (most tasks succeed)
            if task_id != 'nlp':  # Let nlp task "fail" for demo
                callbacks.on_task_success(task_context)
                logger.info(f"✅ Task '{task_id}' completed successfully")
            else:
                # Simulate task failure
                task_context['exception'] = Exception(f"Demo failure in {task_id} task")
                callbacks.on_task_failure(task_context)
                logger.info(f"❌ Task '{task_id}' failed (demo)")
        
        # 3. DAG completion (success despite one task failure)
        logger.info("🏁 DAG Success - Finalizing parent MLflow run")
        callbacks.on_dag_success(context)
        
        logger.info("✅ Demo completed successfully!")
        
        # 4. Display MLflow information
        try:
            import mlflow
            tracking_uri = mlflow.get_tracking_uri()
            logger.info(f"📊 MLflow tracking URI: {tracking_uri}")
            logger.info("💡 You can view the runs in MLflow UI or by browsing the tracking directory")
        except Exception as e:
            logger.warning(f"Could not get MLflow info: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"Demo failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def demo_mlflow_disabled():
    """Demonstrate behavior when MLflow is disabled."""
    
    logger.info("🚫 Testing MLflow disabled scenario...")
    
    # Set environment to disable MLflow
    os.environ['MLFLOW_DISABLED'] = 'true'
    
    try:
        # Import fresh instance
        from mlflow_callbacks import AirflowMLflowCallbacks
        
        # Create callbacks instance
        callbacks = AirflowMLflowCallbacks()
        
        if callbacks.mlflow_enabled:
            logger.error("MLflow should be disabled but it's still enabled")
            return False
        
        # Create mock context
        context = create_mock_context()
        
        logger.info("📋 Testing callbacks with MLflow disabled...")
        
        # These should all be no-ops
        callbacks.on_dag_start(context)
        callbacks.on_task_start(context)
        callbacks.on_task_success(context)
        callbacks.on_dag_success(context)
        
        logger.info("✅ MLflow disabled scenario works correctly")
        return True
        
    except Exception as e:
        logger.error(f"MLflow disabled demo failed: {e}")
        return False
    finally:
        # Clean up environment
        if 'MLFLOW_DISABLED' in os.environ:
            del os.environ['MLFLOW_DISABLED']

def main():
    """Run the complete demo."""
    
    print("=" * 60)
    print("🧪 Airflow ↔ MLflow Integration Demo (Issue #225)")
    print("=" * 60)
    
    # Set up MLflow environment
    mlflow_dir, mlflow_uri = setup_mlflow_env()
    
    try:
        success = True
        
        # Demo 1: Normal MLflow tracking
        print("\n📍 Demo 1: Normal MLflow Tracking")
        print("-" * 40)
        if not demo_dag_lifecycle():
            success = False
        
        # Demo 2: MLflow disabled
        print("\n📍 Demo 2: MLflow Disabled")  
        print("-" * 40)
        if not demo_mlflow_disabled():
            success = False
        
        # Summary
        print("\n" + "=" * 60)
        if success:
            print("🎉 All demos completed successfully!")
            print(f"📂 MLflow data saved to: {mlflow_dir}")
            print("💡 Check the MLflow directory for run artifacts")
        else:
            print("❌ Some demos failed - check logs above")
        print("=" * 60)
        
        return success
        
    except Exception as e:
        logger.error(f"Demo setup failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

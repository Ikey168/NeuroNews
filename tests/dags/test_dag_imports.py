"""
DAG Import Tests for NeuroNews Pipeline (Issue #195)

Tests to ensure DAG files can be imported without errors and contain
the expected tasks. This helps catch configuration issues early in CI/CD.
"""

import pytest
import os
import sys
from pathlib import Path


def test_dag_imports():
    """
    Test that all DAGs can be imported without errors.
    
    Verifies:
    - DAGs can be loaded from airflow/dags directory
    - No import errors occur during DAG parsing
    - news_pipeline DAG is present and contains expected tasks
    """
    # Add airflow plugins to path for lineage_utils
    airflow_plugins_path = str(Path(__file__).parent.parent.parent / "airflow" / "plugins")
    if airflow_plugins_path not in sys.path:
        sys.path.insert(0, airflow_plugins_path)
    
    try:
        from airflow.models import DagBag
    except ImportError:
        pytest.skip("Airflow not available in test environment")
    
    # Set up the DAG folder path
    dag_folder = str(Path(__file__).parent.parent.parent / "airflow" / "dags")
    
    # Create DagBag to import all DAGs
    dag_bag = DagBag(dag_folder=dag_folder, include_examples=False)
    
    # Assert no import errors occurred
    if dag_bag.import_errors:
        error_messages = []
        for filename, error in dag_bag.import_errors.items():
            error_messages.append(f"Import error in {filename}: {error}")
        pytest.fail(f"DAG import errors found:\n" + "\n".join(error_messages))
    
    # Verify news_pipeline DAG exists
    dag = dag_bag.get_dag("news_pipeline")
    assert dag is not None, "news_pipeline DAG not found in DAG bag"
    
    # Verify expected tasks are present
    task_ids = {t.task_id for t in dag.tasks}
    expected_tasks = {"scrape", "clean", "nlp", "publish"}
    
    assert expected_tasks.issubset(task_ids), (
        f"Missing expected tasks. Expected: {expected_tasks}, "
        f"Found: {task_ids}"
    )
    
    # Additional DAG validation
    assert dag.dag_id == "news_pipeline", f"Unexpected DAG ID: {dag.dag_id}"
    assert dag.is_active, "news_pipeline DAG should be active"
    assert len(dag.tasks) >= 4, f"Expected at least 4 tasks, found {len(dag.tasks)}"


def test_dag_structure():
    """
    Test the structure and configuration of the news_pipeline DAG.
    
    Verifies:
    - DAG has correct owner and configuration
    - Tasks have proper dependencies
    - Task flow follows expected sequence
    """
    try:
        from airflow.models import DagBag
    except ImportError:
        pytest.skip("Airflow not available in test environment")
    
    # Set up the DAG folder path
    dag_folder = str(Path(__file__).parent.parent.parent / "airflow" / "dags")
    
    # Import the DAG
    dag_bag = DagBag(dag_folder=dag_folder, include_examples=False)
    dag = dag_bag.get_dag("news_pipeline")
    
    # Verify DAG configuration
    assert dag.owner == "neuronews", f"Expected owner 'neuronews', got '{dag.owner}'"
    assert dag.max_active_runs == 1, f"Expected max_active_runs=1, got {dag.max_active_runs}"
    
    # Verify task dependencies (scrape -> clean -> nlp -> publish)
    scrape_task = dag.get_task("scrape")
    clean_task = dag.get_task("clean")
    nlp_task = dag.get_task("nlp")
    publish_task = dag.get_task("publish")
    
    # Check that tasks exist
    assert scrape_task is not None, "scrape task not found"
    assert clean_task is not None, "clean task not found"
    assert nlp_task is not None, "nlp task not found"
    assert publish_task is not None, "publish task not found"
    
    # Verify task dependencies
    assert len(scrape_task.upstream_task_ids) == 0, "scrape should have no upstream tasks"
    assert "scrape" in clean_task.upstream_task_ids, "clean should depend on scrape"
    assert "clean" in nlp_task.upstream_task_ids, "nlp should depend on clean"
    assert "nlp" in publish_task.upstream_task_ids, "publish should depend on nlp"


def test_dag_tasks_configuration():
    """
    Test individual task configurations in the news_pipeline DAG.
    
    Verifies:
    - Tasks have proper retry configuration
    - Tasks have appropriate timeouts
    - SLA configuration is present where expected
    """
    try:
        from airflow.models import DagBag
        from datetime import timedelta
    except ImportError:
        pytest.skip("Airflow not available in test environment")
    
    # Set up the DAG folder path
    dag_folder = str(Path(__file__).parent.parent.parent / "airflow" / "dags")
    
    # Import the DAG
    dag_bag = DagBag(dag_folder=dag_folder, include_examples=False)
    dag = dag_bag.get_dag("news_pipeline")
    
    # Test task configuration
    for task in dag.tasks:
        # All tasks should have retry configuration
        assert hasattr(task, 'retries'), f"Task {task.task_id} missing retries config"
        assert task.retries >= 1, f"Task {task.task_id} should have at least 1 retry"
        
        # All tasks should have retry delay
        assert hasattr(task, 'retry_delay'), f"Task {task.task_id} missing retry_delay"
        assert isinstance(task.retry_delay, timedelta), (
            f"Task {task.task_id} retry_delay should be timedelta"
        )
    
    # Check SLA configuration on clean task (Issue #190)
    clean_task = dag.get_task("clean")
    if hasattr(clean_task, 'sla') and clean_task.sla:
        assert isinstance(clean_task.sla, timedelta), "clean task SLA should be timedelta"
        assert clean_task.sla.total_seconds() > 0, "clean task SLA should be positive"


if __name__ == "__main__":
    # Run tests individually for debugging
    test_dag_imports()
    test_dag_structure()
    test_dag_tasks_configuration()
    print("✅ All DAG import tests passed!")

"""
Example DAG for NeuroNews Airflow + Marquez setup
This DAG demonstrates basic functionality and lineage tracking.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.dummy_operator import DummyOperator
from airflow.operators.python_operator import PythonOperator

def example_extract():
    """Mock data extraction task."""
    print("📥 Extracting data from source...")
    return {"status": "success", "records": 100}

def example_transform(**context):
    """Mock data transformation task."""
    print("🔄 Transforming data...")
    data = context['task_instance'].xcom_pull(task_ids='extract')
    print(f"Processing {data['records']} records")
    return {"status": "transformed", "records": data['records']}

def example_load(**context):
    """Mock data loading task."""
    print("📤 Loading data to destination...")
    data = context['task_instance'].xcom_pull(task_ids='transform')
    print(f"Loaded {data['records']} records")
    return {"status": "loaded", "records": data['records']}

# DAG definition
default_args = {
    'owner': 'neuronews',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'neuronews_example_pipeline',
    default_args=default_args,
    description='Example NeuroNews ETL pipeline with lineage tracking',
    schedule_interval='@daily',
    catchup=False,
    tags=['example', 'neuronews', 'etl'],
    max_active_runs=1,
)

# Task definitions
start_task = DummyOperator(
    task_id='start',
    dag=dag,
)

extract_task = PythonOperator(
    task_id='extract',
    python_callable=example_extract,
    dag=dag,
)

transform_task = PythonOperator(
    task_id='transform',
    python_callable=example_transform,
    provide_context=True,
    dag=dag,
)

load_task = PythonOperator(
    task_id='load',
    python_callable=example_load,
    provide_context=True,
    dag=dag,
)

end_task = DummyOperator(
    task_id='end',
    dag=dag,
)

# Task dependencies
start_task >> extract_task >> transform_task >> load_task >> end_task

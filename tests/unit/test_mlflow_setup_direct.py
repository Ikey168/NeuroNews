#!/usr/bin/env python3
"""
Direct MLflow testing by executing commands inside the container.
This bypasses networking issues and tests MLflow functionality directly.
"""

import subprocess
import sys

def run_container_command(cmd):
    """Run a command inside the MLflow container."""
    full_cmd = f"docker exec mlflow-server python -c \"{cmd}\""
    try:
        result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)

def test_mlflow_container_functionality():
    """Test MLflow functionality directly in the container."""
    print("🧪 Testing MLflow functionality inside container...")
    print("=" * 60)
    
    # Test 1: Basic connectivity
    print("1️⃣ Testing basic MLflow connectivity...")
    cmd = """
import mlflow
mlflow.set_tracking_uri('http://localhost:5000')
try:
    client = mlflow.tracking.MlflowClient()
    experiments = client.search_experiments()
    print(f'✅ Connected! Found {len(experiments)} experiments')
except Exception as e:
    print(f'❌ Connection failed: {e}')
    raise
"""
    success, stdout, stderr = run_container_command(cmd)
    if success and "✅ Connected!" in stdout:
        print("✅ Basic connectivity test passed")
    else:
        print(f"❌ Basic connectivity test failed")
        print(f"stdout: {stdout}")
        print(f"stderr: {stderr}")
        return False
    
    # Test 2: Create experiment and log data
    print("\n2️⃣ Testing experiment creation and logging...")
    cmd = """
import mlflow
import time
mlflow.set_tracking_uri('http://localhost:5000')

try:
    # Create a unique experiment name
    experiment_name = f'neuronews_test_{int(time.time())}'
    experiment_id = mlflow.create_experiment(experiment_name)
    print(f'✅ Created experiment: {experiment_name} (ID: {experiment_id})')
    
    # Start a run and log data
    with mlflow.start_run(experiment_id=experiment_id):
        mlflow.log_param('model_type', 'neural_network')
        mlflow.log_param('learning_rate', 0.001)
        mlflow.log_param('batch_size', 32)
        
        mlflow.log_metric('accuracy', 0.95)
        mlflow.log_metric('precision', 0.92)
        mlflow.log_metric('recall', 0.89)
        mlflow.log_metric('f1_score', 0.90)
        
        print('✅ Successfully logged parameters and metrics')
    
    print('✅ Experiment and run creation test passed')
    
except Exception as e:
    print(f'❌ Test failed: {e}')
    raise
"""
    success, stdout, stderr = run_container_command(cmd)
    if success and "✅ Experiment and run creation test passed" in stdout:
        print("✅ Experiment creation and logging test passed")
    else:
        print(f"❌ Experiment creation test failed")
        print(f"stdout: {stdout}")
        print(f"stderr: {stderr}")
        return False
    
    # Test 3: Query experiments and runs
    print("\n3️⃣ Testing experiment and run querying...")
    cmd = """
import mlflow
mlflow.set_tracking_uri('http://localhost:5000')

try:
    client = mlflow.tracking.MlflowClient()
    
    # Get all experiments
    experiments = client.search_experiments()
    print(f'✅ Found {len(experiments)} experiments')
    
    # Get runs from the default experiment
    runs = client.search_runs(experiment_ids=['0'])
    print(f'✅ Found {len(runs)} runs in default experiment')
    
    if runs:
        latest_run = runs[0]
        print(f'✅ Latest run ID: {latest_run.info.run_id}')
        print(f'✅ Run status: {latest_run.info.status}')
        
        # Print some metrics
        for metric_key, metric_value in latest_run.data.metrics.items():
            print(f'  📊 {metric_key}: {metric_value}')
    
    print('✅ Query test passed')
    
except Exception as e:
    print(f'❌ Query test failed: {e}')
    raise
"""
    success, stdout, stderr = run_container_command(cmd)
    if success and "✅ Query test passed" in stdout:
        print("✅ Experiment and run querying test passed")
    else:
        print(f"❌ Querying test failed")
        print(f"stdout: {stdout}")
        print(f"stderr: {stderr}")
        return False
    
    return True

def test_database_connectivity():
    """Test PostgreSQL database connectivity."""
    print("\n🗄️ Testing PostgreSQL database connectivity...")
    cmd = """
import psycopg2
import os

try:
    # Connect to the MLflow database
    conn = psycopg2.connect(
        host='mlflow-db',
        port=5432,
        database='mlflow',
        user='mlflow',
        password='mlflow'
    )
    
    cursor = conn.cursor()
    cursor.execute('SELECT version();')
    version = cursor.fetchone()[0]
    print(f'✅ Connected to PostgreSQL: {version}')
    
    # Check MLflow tables
    cursor.execute(\"\"\"
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name LIKE '%experiment%' OR table_name LIKE '%run%'
        ORDER BY table_name;
    \"\"\")
    
    tables = cursor.fetchall()
    print(f'✅ Found {len(tables)} MLflow tables in database')
    for table in tables:
        print(f'  📋 {table[0]}')
    
    cursor.close()
    conn.close()
    print('✅ Database connectivity test passed')
    
except Exception as e:
    print(f'❌ Database test failed: {e}')
    raise
"""
    success, stdout, stderr = run_container_command(cmd)
    if success and "✅ Database connectivity test passed" in stdout:
        print("✅ Database connectivity test passed")
        return True
    else:
        print(f"❌ Database connectivity test failed")
        print(f"stdout: {stdout}")
        print(f"stderr: {stderr}")
        return False

def main():
    """Main test function."""
    print("🚀 MLflow Container Testing Suite")
    print("=" * 60)
    print("This test bypasses network issues by running commands directly")
    print("inside the MLflow container.")
    print("=" * 60)
    
    # Check if container is running
    try:
        result = subprocess.run(
            "docker ps | grep mlflow-server", 
            shell=True, capture_output=True, text=True
        )
        if result.returncode != 0:
            print("❌ MLflow container is not running!")
            print("   Run 'make mlflow-up' first.")
            sys.exit(1)
        print("✅ MLflow container is running")
    except Exception as e:
        print(f"❌ Failed to check container status: {e}")
        sys.exit(1)
    
    # Run tests
    try:
        mlflow_test = test_mlflow_container_functionality()
        db_test = test_database_connectivity()
        
        print("\n" + "=" * 60)
        print("📊 TEST RESULTS SUMMARY")
        print("=" * 60)
        
        if mlflow_test and db_test:
            print("🎉 ALL TESTS PASSED!")
            print("✅ MLflow tracking server is working correctly")
            print("✅ PostgreSQL database is accessible")
            print("✅ Experiment creation and logging works")
            print("✅ Data querying works")
            print("\n🌐 MLflow UI should be accessible at: http://localhost:5001")
            print("   (Note: Direct external access may have network configuration issues)")
            sys.exit(0)
        else:
            print("❌ SOME TESTS FAILED")
            print("   Check the error messages above for details")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Test suite failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

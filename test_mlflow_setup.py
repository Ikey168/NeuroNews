#!/usr/bin/env python3
"""
Test MLflow tracking server functionality.
This script verifies that:
1. MLflow UI loads on http://localhost:5001
2. Experiments can be created

Usage: python test_mlflow_setup.py
"""

import mlflow
import requests
import sys

def test_mlflow_connectivity():
    """Test if MLflow server is accessible."""
    try:
        response = requests.get("http://localhost:5001", timeout=10)
        if response.status_code == 200 and "MLflow" in response.text:
            print("✅ MLflow UI accessible at http://localhost:5001")
            return True
        else:
            print(f"❌ MLflow UI returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Failed to connect to MLflow UI: {e}")
        return False

def test_experiment_creation():
    """Test creating an MLflow experiment."""
    try:
        # Set tracking URI
        mlflow.set_tracking_uri("http://localhost:5001")
        
        # Create a test experiment
        experiment_name = "test_neuronews_experiment"
        experiment_id = mlflow.create_experiment(experiment_name)
        print(f"✅ Created experiment '{experiment_name}' with ID: {experiment_id}")
        
        # Start a test run
        with mlflow.start_run(experiment_id=experiment_id):
            # Log some test parameters and metrics
            mlflow.log_param("model_type", "test")
            mlflow.log_param("framework", "mlflow")
            mlflow.log_metric("accuracy", 0.95)
            mlflow.log_metric("loss", 0.05)
            
            print("✅ Successfully logged parameters and metrics")
        
        print("✅ Test run completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Failed to create experiment or log data: {e}")
        return False

def main():
    """Main test function."""
    print("🧪 Testing MLflow setup...")
    print("=" * 50)
    
    # Test 1: UI accessibility
    ui_test = test_mlflow_connectivity()
    
    # Test 2: Experiment creation
    experiment_test = test_experiment_creation()
    
    print("=" * 50)
    if ui_test and experiment_test:
        print("🎉 All tests passed! MLflow setup is working correctly.")
        print("📊 Open http://localhost:5001 to view the MLflow UI")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Check the setup.")
        sys.exit(1)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Simple test to verify DoD requirements for the tracking helper.

This script tests that:
1. mlrun context manager works
2. Standard tags are applied
3. Run is visible in MLflow UI
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from services.mlops.tracking import mlrun, setup_mlflow_env
import mlflow


def test_dod_requirements():
    """Test DoD requirements."""
    print("🧪 Testing DoD requirements...")
    
    # Setup MLflow environment
    setup_mlflow_env("http://localhost:5001", "dod-test")
    
    try:
        # Test mlrun context manager with standard tags
        with mlrun("dod-test-run", tags={"test": "dod"}) as run:
            # Log a parameter and metric
            mlflow.log_param("test_param", "dod_value")
            mlflow.log_metric("test_metric", 0.95)
            
            print(f"✅ Run created with ID: {run.info.run_id}")
            
            # Verify standard tags are set
            from mlflow.tracking import MlflowClient
            client = MlflowClient()
            run_data = client.get_run(run.info.run_id)
            
            expected_tags = ["git.sha", "git.branch", "env", "hostname", "code_version"]
            missing_tags = []
            
            for tag in expected_tags:
                if tag not in run_data.data.tags:
                    missing_tags.append(tag)
            
            if missing_tags:
                print(f"❌ Missing standard tags: {missing_tags}")
                return False
            else:
                print("✅ All standard tags present")
            
            # Verify custom tag
            if "test" not in run_data.data.tags or run_data.data.tags["test"] != "dod":
                print("❌ Custom tag not set correctly")
                return False
            else:
                print("✅ Custom tag set correctly")
            
            # Verify parameters and metrics
            if "test_param" not in run_data.data.params:
                print("❌ Parameter not logged")
                return False
            else:
                print("✅ Parameter logged correctly")
            
            if "test_metric" not in run_data.data.metrics:
                print("❌ Metric not logged")
                return False
            else:
                print("✅ Metric logged correctly")
            
            print("\n📊 Run details:")
            print(f"  Experiment: {run_data.info.experiment_id}")
            print(f"  Run ID: {run_data.info.run_id}")
            print(f"  Status: {run_data.info.status}")
            print(f"  Standard tags: {[tag for tag in expected_tags if tag in run_data.data.tags]}")
            print(f"  MLflow UI: http://localhost:5001/#/experiments/{run_data.info.experiment_id}/runs/{run_data.info.run_id}")
            
            return True
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def main():
    """Main test function."""
    print("🎯 DoD Requirements Test")
    print("=" * 40)
    
    success = test_dod_requirements()
    
    print("\n" + "=" * 40)
    if success:
        print("🎉 All DoD requirements satisfied!")
        print("📊 Check MLflow UI: http://localhost:5001")
        sys.exit(0)
    else:
        print("❌ DoD requirements not satisfied")
        sys.exit(1)


if __name__ == "__main__":
    main()

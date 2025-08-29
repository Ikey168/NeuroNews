#!/usr/bin/env python3
"""
Custom MLflow server starter using gunicorn with proper host binding
"""
import os
import sys
import subprocess

def main():
    # Set environment variables for MLflow
    os.environ['MLFLOW_BACKEND_STORE_URI'] = 'postgresql+psycopg2://mlflow:mlflow@mlflow-db:5432/mlflow'
    os.environ['MLFLOW_DEFAULT_ARTIFACT_ROOT'] = '/mlflow/artifacts'
    
    # Use gunicorn to run MLflow with explicit host binding
    cmd = [
        'gunicorn', 
        'mlflow.server:app',
        '--bind', '0.0.0.0:5000',
        '--workers', '1',
        '--timeout', '60',
        '--keep-alive', '2',
        '--max-requests', '1000'
    ]
    
    print(f"Starting MLflow server with command: {' '.join(cmd)}")
    print(f"Backend store: {os.environ['MLFLOW_BACKEND_STORE_URI']}")
    print(f"Artifact root: {os.environ['MLFLOW_DEFAULT_ARTIFACT_ROOT']}")
    
    # Run the command
    subprocess.run(cmd, check=True)

if __name__ == "__main__":
    main()

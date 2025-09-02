#!/usr/bin/env python3
"""
Test script for the NeuroNews Metrics API
"""

import requests
import json
import time
import subprocess
import os
import sys

def test_api_endpoints():
    """Test the metrics API endpoints"""
    base_url = "http://localhost:8000"
    
    print("🚀 Testing NeuroNews Metrics API")
    print("=" * 50)
    
    # Test health endpoint
    print("\n1. Testing Health Endpoint")
    try:
        response = requests.get(f"{base_url}/health")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except requests.exceptions.ConnectionError:
        print("❌ Server not running. Start with: uvicorn app:app --reload")
        return
    
    # Test root endpoint
    print("\n2. Testing Root Endpoint")
    response = requests.get(f"{base_url}/")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    # Test available metrics
    print("\n3. Testing Available Metrics")
    response = requests.get(f"{base_url}/metrics/available")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    else:
        print(f"Error: {response.text}")
    
    # Test dimensions
    print("\n4. Testing Available Dimensions")
    response = requests.get(f"{base_url}/dimensions")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    else:
        print(f"Error: {response.text}")
    
    # Test metrics query
    print("\n5. Testing Metrics Query")
    params = {
        "name": "articles_ingested",
        "group_by": "metric_time__day", 
        "limit": 5
    }
    response = requests.get(f"{base_url}/metrics", params=params)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    else:
        print(f"Error: {response.text}")
    
    print("\n✅ API testing complete!")

def start_server():
    """Start the FastAPI server"""
    print("🚀 Starting NeuroNews Metrics API server...")
    
    # Set environment variables
    os.environ["DBT_PROJECT_DIR"] = "/workspaces/NeuroNews/dbt"
    os.environ["DBT_PROFILES_DIR"] = "/workspaces/NeuroNews/dbt"
    
    # Start uvicorn server
    try:
        subprocess.run([
            "uvicorn", "app:app", 
            "--host", "0.0.0.0", 
            "--port", "8000", 
            "--reload"
        ], check=True)
    except KeyboardInterrupt:
        print("\n🛑 Server stopped")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to start server: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_api_endpoints()
    else:
        start_server()

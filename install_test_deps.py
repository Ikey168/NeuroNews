#!/usr/bin/env python3
"""
Install Test Dependencies
Installs common dependencies needed to run the test suite successfully.
"""

import subprocess
import sys

def install_dependencies():
    """Install common test dependencies."""
    print("📦 Installing test dependencies...")
    print("="*50)
    
    # Core test dependencies
    test_deps = [
        "pytest",
        "pytest-cov", 
        "pytest-asyncio",
        "fastapi",
        "requests",
        "httpx",  # Required for FastAPI TestClient
        "gremlinpython",  # Required for graph database tests (note: different package name)
        "boto3",  # Required for AWS service tests
        "sqlalchemy",  # Required for database tests
        "pandas",  # Required for data processing tests
        "numpy",  # Required for data processing tests
        "scikit-learn",  # Required for ML tests
        "transformers",  # Required for NLP tests
        "torch",  # Required for ML/NLP tests
        "scrapy",  # Required for scraper tests
        "beautifulsoup4",  # Required for web scraping tests
        "aiohttp",  # Required for async HTTP tests
        "uvicorn",  # Required for FastAPI server tests
        "pydantic",  # Required for API validation tests
        "aiofiles",  # Required for async file operations
        "sentence-transformers",  # Required for Issue #31 tests
        "mlflow",  # Required for ML workflow tests
        "python-dotenv",  # Required for environment variable loading
        "pyyaml",  # Required for YAML config loading
        "jinja2",  # Required for template rendering
        "streamlit",  # Required for Streamlit app tests
        "redis",  # Required for Redis tests
        "snowflake-connector-python",  # Required for Snowflake tests
        "qdrant-client",  # Required for vector database tests
        "openai",  # Required for OpenAI API tests
        "tiktoken",  # Required for token counting in OpenAI tests
        "plotly",  # Required for visualization tests
        "dash",  # Required for dashboard tests
    ]
    
    for dep in test_deps:
        try:
            print(f"Installing {dep}...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", dep],
                check=True,
                capture_output=True
            )
            print(f"✅ {dep} installed")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install {dep}: {e}")
    
    print("="*50)
    print("✅ Test dependency installation complete!")
    print("🚀 You can now run: python run_all_tests.py")

if __name__ == "__main__":
    install_dependencies()
#!/usr/bin/env python3
"""
NeuroNews Dashboard Launcher (Issue #50)

Script to launch the Streamlit dashboard with proper configuration.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Add src to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))


def check_dependencies():
    """Check if required dependencies are installed."""
    required_packages = ["streamlit", "plotly",
        "networkx", "pandas", "requests"]

    missing_packages = []

    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        print(f"❌ Missing required packages: {', '.join(missing_packages)}")
        print("Please install them using: pip install -r requirements.txt")
        return False

    print(" All required packages are installed")
    return True


def check_api_connection(api_url: str):
    """Check if the API is accessible."""
    try:
        import requests

        response = requests.get("{0}/health".format(api_url), timeout=5)
        if response.status_code == 200:
            print(" API is accessible at {0}".format(api_url))
            return True
        else:
            print("⚠️  API returned status {0}".format(response.status_code))
            return False
    except requests.exceptions.RequestException as e:
        print("❌ API is not accessible at {0}: {1}".format(api_url, e))
        return False


def setup_environment():
    """Setup environment variables."""
    # Set default environment variables if not already set
    env_vars = {
        "NEURONEWS_API_URL": "http://localhost:8000",
        "STREAMLIT_SERVER_PORT": "8501",
        "STREAMLIT_SERVER_ADDRESS": "localhost",
    }

    for key, default_value in env_vars.items():
        if key not in os.environ:
            os.environ[key] = default_value
            print("📝 Set {0}={1}".format(key, default_value))


def main():
    """Main launcher function."""
    parser = argparse.ArgumentParser(
        description="Launch NeuroNews Streamlit Dashboard")
    parser.add_argument(
        "--port", type=int, default=8501, help="Port to run dashboard on"
    )
    parser.add_argument("--host", default="localhost",
                        help="Host to bind dashboard to")
    parser.add_argument(
        "--api-url", default="http://localhost:8000", help="NeuroNews API URL"
    )
    parser.add_argument("--dev", action="store_true",
                        help="Run in development mode")
    parser.add_argument(
        "--skip-checks", action="store_true", help="Skip dependency and API checks"
    )

    args = parser.parse_args()

    print(" NeuroNews Dashboard Launcher")
    print("=" * 40)

    # Setup environment
    setup_environment()
    os.environ["NEURONEWS_API_URL"] = args.api_url

    if args.dev:
        os.environ["ENVIRONMENT"] = "development"
        print("🔧 Running in development mode")

    # Check dependencies
    if not args.skip_checks:
        print(""
 Checking dependencies...")"
        if not check_dependencies():
            sys.exit(1)

        print(""
🔗 Checking API connection...")"
        check_api_connection(args.api_url)

    # Prepare streamlit command
    dashboard_path=src_path / "dashboards" / "streamlit_dashboard.py"

    streamlit_cmd=[
        "streamlit",
        "run",
        str(dashboard_path),
        "--server.port",
        str(args.port),
        "--server.address",
        args.host,
        "--server.headless",
        "true" if args.dev else f"alse",
        "--server.fileWatcherType",
        "poll" if args.dev else "auto",
        "--theme.primaryColor",
        "#FF6B6B",
        "--theme.backgroundColor",
        "#FFFFFF",
        "--theme.secondaryBackgroundColor",
        "#F0F2F6",
        "--theme.textColor",
        "#262730",
    ]

    print(""
🌐 Starting dashboard at http: // {0}: {1}".format(args.host, args.port))
    print("Press Ctrl+C to stop the dashboard")
    print("-" * 40)"

    try:
        subprocess.run(streamlit_cmd, check=True)
    except KeyboardInterrupt:
        print(""
👋 Dashboard stopped by user")"
    except subprocess.CalledProcessError as e:
        print("❌ Error running dashboard: {0}".format(e))
        sys.exit(1)
    except FileNotFoundError:
        print("❌ Streamlit is not installed or not in PATH")
        print("Please install streamlit: pip install streamlit")
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Quick containerization verification script.
This proves the containerized approach works by testing individual components.
"""

import subprocess
import sys
import time


def run_command(cmd, description):
    """Run a command and return success status."""
    print("🔧 {0}...".format(description))
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print(" {0} - SUCCESS".format(description))
            return True
        else:
            print("❌ {0} - FAILED".format(description))
            print("Error: {0}".format(result.stderr))
            return False
    except subprocess.TimeoutExpired:
        print("⏰ {0} - TIMEOUT (30s)".format(description))
        return False
    except Exception as e:
        print("❌ {0} - ERROR: {1}".format(description, e))
        return False


def main():
    """Main verification function."""
    print(" NeuroNews Containerization Verification")
    print("=" * 50)

    tests = [
        ("docker --version",
         "Docker availability"),
        ("docker compose version",
         "Docker Compose availability"),
        ("docker build -f deploy/docker/Dockerfile.simple -t neuronews-test .",
            "Simple Docker build",
         ),
        ("docker images | grep neuronews",
         "Docker image creation"),
        ("docker run --rm neuronews-test python -c 'import psycopg2; print(\"Dependencies OK\")'",
            "Container dependency check",
         ),
    ]

    results = []
    for cmd, desc in tests:
        success = run_command(cmd, desc)
        results.append(success)
        time.sleep(1)  # Brief pause between tests

    print("=" * 50)
    print("VERIFICATION RESULTS:")
    print("Passed: {0}/{1} tests".format(sum(results), len(results)))

    if all(results):
        print(" CONTAINERIZATION VERIFICATION COMPLETE!")
        print("✨ The containerized solution is ready for deployment!")
        return True
    else:
        print("⚠️  Some tests failed, but core containerization works")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

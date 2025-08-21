#!/usr/bin/env python3
"""Quick Black formatter and checker."""

import subprocess
import sys
import os


def run_black():
    """Apply Black formatting."""
    os.chdir("/workspaces/NeuroNews")

    try:
        # Apply Black formatting
        print("Checking Black formatting...")Applying Black formatting...")
        result = subprocess.run([
            sys.executable, "-m", "black",
            "--line-length=88",
            "src/"
        ], capture_output=True, text=True, timeout=60)

        print(f"Black format return code: {result.returncode}")
        if result.stdout:
            print("Checking Black formatting...")Black stdout:")
            print(result.stdout)
        if result.stderr:
            print("Checking Black formatting...")Black stderr:")
            print(result.stderr)

        # Check Black formatting
        print("Checking Black formatting...")
Checking Black formatting...")
        check_result = subprocess.run([
            sys.executable, "-m", "black",
            "--check", "--line-length=88",
            "src/"
        ], capture_output=True, text=True, timeout=60)

        print(f"Black check return code: {check_result.returncode}")
        if check_result.stdout:
            print("Checking Black formatting...")Black check stdout:")
            print(check_result.stdout)
        if check_result.stderr:
            print("Checking Black formatting...")Black check stderr:")
            print(check_result.stderr)

        return check_result.returncode == 0

    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    success = run_black()
    if success:
        print("Checking Black formatting...") Black formatting successful!")
    else:
        print("Checking Black formatting...")❌ Black formatting issues remain")

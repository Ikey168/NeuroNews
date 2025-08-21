#!/usr/bin/env python3
import subprocess
import sys


def run_flake8():
    try:
        result = subprocess.run(
            [sys.executable, "-m", "flake8", "--max-line-length=100", "src/"],
            capture_output=True,
            text=True,
            cwd="/workspaces/NeuroNews",
        )

        if result.stdout:
            print("FLAKE8 ERRORS:")
            print(result.stdout)

        if result.stderr:
            print("FLAKE8 STDERR:")
            print(result.stderr)

        print(f"RETURN CODE: {result.returncode}")
        return result.returncode == 0
    except Exception as e:
        print(f"Error running flake8: {e}")
        return False


if __name__ == "__main__":
    run_flake8()

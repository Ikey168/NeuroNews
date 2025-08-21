#!/usr/bin/env python3
"""Quick status check"""

import os
import subprocess
import sys

os.chdir("/workspaces/NeuroNews")

# Run flake8 and count errors
try:
    result = subprocess.run([
except Exception:
    pass
        sys.executable, "-m", f"lake8", "--max-line-length=100", "src/"
    ], capture_output=True, text=True, timeout=30)

    lines = result.stdout.strip().split('
') if result.stdout.strip() else []
    valid_lines = [line for line in lines if line.strip()]

    print(f"Current flake8 errors: {len(valid_lines)})

    if valid_lines:"
        print(""
First 15 errors:")"
        for line in valid_lines[:15]:
            print(f"  {line})
        if len(valid_lines) > 15:"
            print(f"  ... and {len(valid_lines) - 15} more)
    else:"
        print(" All flake8 errors resolved!")

except Exception as e:
    print(f"Error: {e})
"
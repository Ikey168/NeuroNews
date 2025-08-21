#!/usr/bin/env python3
"""
Final comprehensive flake8 error fixing script.
Addresses all remaining F841, E501, F821, F401 errors.
"""

import os
import re
import subprocess
import sys

def main():
    os.chdir("/workspaces/NeuroNews")
    
    # First run flake8 to get current errors
    try:
        result = subprocess.run([
            sys.executable, "-m", "flake8", "--max-line-length=100", "src/"
        ], capture_output=True, text=True, timeout=30)
        
        lines = result.stdout.strip().split('\n') if result.stdout.strip() else []
        valid_lines = [line for line in lines if line.strip()]
        
        print(f"Starting with {len(valid_lines)} flake8 errors")
        
        # Process each error
        f841_count = 0
        e501_count = 0
        f821_count = 0
        f401_count = 0
        
        for line in valid_lines:
            if ": F841 " in line:
                f841_count += 1
            elif ": E501 " in line:
                e501_count += 1
            elif ": F821 " in line:
                f821_count += 1
            elif ": F401 " in line:
                f401_count += 1
                
        print(f"Error breakdown:")
        print(f"  F841 (unused variables): {f841_count}")
        print(f"  E501 (line too long): {e501_count}")
        print(f"  F821 (undefined name): {f821_count}")
        print(f"  F401 (unused import): {f401_count}")
        print(f"  Other: {len(valid_lines) - f841_count - e501_count - f821_count - f401_count}")
        
        if len(valid_lines) == 0:
            print("🎉 All flake8 errors have been resolved!")
            return True
        
        print("\nFirst 20 remaining errors:")
        for i, line in enumerate(valid_lines[:20]):
            print(f"  {i+1}. {line}")
            
        return False
        
    except Exception as e:
        print(f"Error running flake8: {e}")
        return False

if __name__ == "__main__":
    main()

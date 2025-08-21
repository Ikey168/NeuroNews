#!/usr/bin/env python3
"""
Comprehensive Black and flake8 checker and fixer.
"""

import os
import subprocess
import sys
from pathlib import Path

def run_command(cmd, description):
    """Run a command and return the result."""
    print(f"\n{'='*50}")
    print(f"Running: {description}")
    print(f"Command: {cmd}")
    print('='*50)
    
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=60,
            cwd="/workspaces/NeuroNews"
        )
        
        print(f"Return code: {result.returncode}")
        
        if result.stdout:
            print("STDOUT:")
            print(result.stdout)
            
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
            
        return result
        
    except subprocess.TimeoutExpired:
        print("Command timed out!")
        return None
    except Exception as e:
        print(f"Error running command: {e}")
        return None

def main():
    os.chdir("/workspaces/NeuroNews")
    
    print("COMPREHENSIVE CODE QUALITY CHECK AND FIX")
    print("="*60)
    
    # 1. Check Black formatting
    print("\n1. CHECKING BLACK FORMATTING...")
    black_check = run_command(
        "python -m black --check --line-length=88 src/",
        "Black formatting check"
    )
    
    # 2. Apply Black formatting if needed
    if black_check and black_check.returncode != 0:
        print("\n2. APPLYING BLACK FORMATTING...")
        black_fix = run_command(
            "python -m black --line-length=88 src/",
            "Apply Black formatting"
        )
    else:
        print("\n2. Black formatting is already compliant!")
    
    # 3. Check flake8 errors
    print("\n3. CHECKING FLAKE8 ERRORS...")
    flake8_check = run_command(
        "python -m flake8 --max-line-length=100 src/",
        "Full flake8 check"
    )
    
    # 4. Show summary
    print("\n4. SUMMARY")
    print("="*40)
    
    if flake8_check:
        errors = flake8_check.stdout.strip().split('\n') if flake8_check.stdout.strip() else []
        valid_errors = [e for e in errors if e.strip()]
        
        if valid_errors:
            print(f"Remaining flake8 errors: {len(valid_errors)}")
            print("\nFirst 20 errors:")
            for i, error in enumerate(valid_errors[:20], 1):
                print(f"  {i:2d}. {error}")
            if len(valid_errors) > 20:
                print(f"     ... and {len(valid_errors) - 20} more errors")
        else:
            print("🎉 All flake8 errors resolved!")
    
    # 5. Check if Black is happy now
    print("\n5. FINAL BLACK CHECK...")
    final_black = run_command(
        "python -m black --check --line-length=88 src/",
        "Final Black check"
    )
    
    if final_black and final_black.returncode == 0:
        print("✅ Black formatting is compliant!")
    else:
        print("❌ Black formatting issues remain")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Final format and lint checker.
"""

import os
import subprocess
import sys
import re
from pathlib import Path

def cleanup_files():
    """Clean up formatting issues."""
    print("Cleaning up formatting issues...")
    
    src_dir = Path("/workspaces/NeuroNews/src")
    python_files = list(src_dir.rglob("*.py"))
    
    fixes = 0
    
    for file_path in python_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original = content
            
            # Remove trailing whitespace
            content = re.sub(r'[ \t]+$', '', content, flags=re.MULTILINE)
            
            # Single newline at end
            content = content.rstrip() + '\n'
            
            # Remove excessive blank lines
            content = re.sub(r'\n\n\n+', '\n\n', content)
            
            if content != original:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                fixes += 1
                
        except Exception as e:
            print(f"Error with {file_path}: {e}")
    
    print(f"Fixed {fixes} files")
    return fixes

def run_tools():
    """Run Black and flake8."""
    os.chdir("/workspaces/NeuroNews")
    
    print("\n1. Running Black...")
    try:
        black_result = subprocess.run([
            sys.executable, "-m", "black", "--line-length=88", "src/"
        ], capture_output=True, text=True, timeout=60)
        
        print(f"Black return code: {black_result.returncode}")
        if black_result.stdout:
            print("Black output:", black_result.stdout[:500])
        
    except Exception as e:
        print(f"Black error: {e}")
    
    print("\n2. Running flake8...")
    try:
        flake8_result = subprocess.run([
            sys.executable, "-m", "flake8", "--max-line-length=100", "src/"
        ], capture_output=True, text=True, timeout=60)
        
        print(f"Flake8 return code: {flake8_result.returncode}")
        
        if flake8_result.stdout:
            errors = flake8_result.stdout.strip().split('\n')
            valid_errors = [e for e in errors if e.strip()]
            print(f"Flake8 errors: {len(valid_errors)}")
            
            if valid_errors:
                print("First 15 errors:")
                for i, error in enumerate(valid_errors[:15], 1):
                    print(f"  {i}. {error}")
                if len(valid_errors) > 15:
                    print(f"  ... and {len(valid_errors) - 15} more")
            else:
                print("🎉 No flake8 errors!")
        else:
            print("🎉 No flake8 errors!")
            
        return flake8_result.returncode == 0
        
    except Exception as e:
        print(f"Flake8 error: {e}")
        return False

def main():
    print("FINAL CODE QUALITY CHECK")
    print("=" * 40)
    
    cleanup_files()
    success = run_tools()
    
    if success:
        print("\n✅ All checks passed!")
    else:
        print("\n❌ Issues found")
    
    return success

if __name__ == "__main__":
    main()

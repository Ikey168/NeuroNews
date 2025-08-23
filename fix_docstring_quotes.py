#!/usr/bin/env python3
"""
Docstring Quote Fixer
Fixes incorrect docstring quotes that cause E999 errors.
"""

import os
import re
import subprocess


def fix_docstring_quotes(filepath):
    """Fix malformed docstring quotes."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        original_content = content

        # Fix common docstring quote patterns
        # Fix """...""" -> """..."""
        content = re.sub(r'"""(".*?")"""', r'"""\1"""', content, flags=re.DOTALL)

        # Fix """"
....""" -> """
..."""
        content = re.sub(r'""""([^"] * ?)""""', r'"""\1"""', content, flags=re.DOTALL)
        
        # Fix """" at start of line -> """
        content = re.sub(r'^""""', '"""', content, flags=re.MULTILINE)
        
        # Fix """" at end with newline -> """
        content = re.sub(r'""""$', '"""', content, flags=re.MULTILINE)
        content = re.sub(r'""""
', '"""
', content)
        
        # Fix specific pattern: 
"""
        content = re.sub(r'\
"""', '\
"""', content)
        
        # Write back if changed
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        
        return False
        
    except Exception as e:
        print(f"Error fixing {filepath}: {e}")
        return False


def get_all_python_files():
    """Get all Python files in the workspace."""
    python_files = []
    for root, dirs, files in os.walk('.'):
        # Skip hidden directories and __pycache__
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
        
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    
    return python_files


def main():
    """Fix docstring quotes in all Python files."""
    print("🔧 Fixing docstring quotes...")
    
    python_files = get_all_python_files()
    print(f"Found {len(python_files)} Python files")
    
    fixed_count = 0
    for filepath in python_files:
        if fix_docstring_quotes(filepath):
            print(f" Fixed {filepath}")
            fixed_count += 1
    
    print(f" Fixed {fixed_count} files")
    
    # Check remaining E999 errors
    try:
        result = subprocess.run(
            ["python", "-m", "flake8", "--select=E999", "--count"],
            capture_output=True, text=True
        )
        if result.stdout.strip().isdigit():
            remaining_count = int(result.stdout.strip())
            print(f" Remaining E999 errors: {remaining_count}")
    except Exception as e:
        print(f"Could not check remaining errors: {e}")


if __name__ == "__main__":
    main()

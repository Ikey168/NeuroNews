#!/usr/bin/env python3
"""
Fix unterminated string literals and other syntax errors.
"""

import re


def fix_unterminated_strings():
    """Fix files with unterminated string literals."""

    # Read the problematic file
    with open("./apply_black.py", "r") as f:
        content = f.read()

    # Fix the specific issue
    content = content.replace('print("', 'print("Checking Black formatting...")')
    content = re.sub(r'print\("\s*\n\s*Checking', 'print("Checking', content)

    with open("./apply_black.py", "w") as f:
        f.write(content)

    print("Fixed apply_black.py")


if __name__ == "__main__":
    fix_unterminated_strings()

#!/usr/bin/env python3
"""
Comprehensive Flake8 Error Fix Script
Fixes all E999 syntax errors and other flake8 issues systematically.
"""

import re
import subprocess


def run_command(cmd):
    """Run shell command and return success, stdout, stderr."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)


def fix_unterminated_strings():
    """Fix E999 unterminated string literal errors."""
    print("🔧 Fixing unterminated string literals (E999)...")

    # Get all E999 errors
    success, output, _ = run_command("python -m flake8 --select=E999")
    if not success:
        print("❌ Could not get E999 errors")
        return

    fixed_count = 0
    for line in output.strip().split('
'):
        if not line or 'E999' not in line:
            continue

        # Parse error line: ./file.py:line:col: E999 message
        parts = line.split(':')
        if len(parts) < 4:
            continue

        filepath = parts[0].lstrip('./')
        line_num = int(parts[1])

        try:
            # Read file
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if line_num > len(lines):
                continue

            # Get the problematic line
            problem_line = lines[line_num - 1]

            # Common fixes for unterminated strings
            fixed_line = problem_line

            # Fix split with broken newline
            if "split('" in problem_line and not problem_line.count("'") % 2 == 0:
                fixed_line = re.sub(r"split\('([^']*)
([^']*)\)", r"split('
')", fixed_line)

            # Fix broken f-strings
            if 'f"' in problem_line or "f'" in problem_line:
                # Count quotes to see if unmatched
                single_quotes = problem_line.count("'")
                double_quotes = problem_line.count('"')

                if single_quotes % 2 != 0:
                    # Add missing single quote at end
                    fixed_line = problem_line.rstrip() + "'
"
                elif double_quotes % 2 != 0:
                    # Add missing double quote at end
                    fixed_line = problem_line.rstrip() + '"
'

            # Fix regular strings with missing quotes
            elif '"' in problem_line or "'" in problem_line:
                single_quotes = problem_line.count("'")
                double_quotes = problem_line.count('"')

                if single_quotes % 2 != 0:
                    fixed_line = problem_line.rstrip() + "'
"
                elif double_quotes % 2 != 0:
                    fixed_line = problem_line.rstrip() + '"
'

            # Apply fix if changed
            if fixed_line != problem_line:
                lines[line_num - 1] = fixed_line

                # Write back to file
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.writelines(lines)

                print(f" Fixed {filepath}:{line_num}")
                fixed_count += 1

        except Exception as e:
            print(f"❌ Error fixing {filepath}: {e}")
            continue

    print(f" Fixed {fixed_count} unterminated string errors")


def fix_undefined_names():
    """Fix F821 undefined name errors."""
    print("🔧 Fixing undefined names (F821)...")

    success, output, _ = run_command("python -m flake8 --select=F821")
    if not success:
        print("❌ Could not get F821 errors")
        return

    fixed_count = 0
    for line in output.strip().split('
'):
        if not line or 'F821' not in line:
            continue

        parts = line.split(':')
        if len(parts) < 4:
            continue

        filepath = parts[0].lstrip('./')
        line_num = int(parts[1])

        # Extract undefined variable name
        if 'undefined name' in line:
            var_name = line.split("'")[1] if "'" in line else ""

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Add common imports at top
                imports_to_add = []
                if var_name in ['json', 'os', 'sys', 'time', 'asyncio', 'logging']:
                    imports_to_add.append(f"import {var_name}")
                elif var_name == 'datetime':
                    imports_to_add.append("from datetime import datetime")
                elif var_name == '__':
                    imports_to_add.append("from __future__ import annotations")

                if imports_to_add:
                    # Add imports after existing imports
                    lines = content.split('
')
                    import_insert_pos = 0

                    # Find where to insert imports
                    for i, line in enumerate(lines):
                        if line.startswith('import ') or line.startswith('from '):
                            import_insert_pos = i + 1

                    # Insert imports
                    for imp in imports_to_add:
                        if imp not in content:
                            lines.insert(import_insert_pos, imp)
                            import_insert_pos += 1

                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write('
'.join(lines))

                    print(f" Added imports to {filepath}")
                    fixed_count += 1

            except Exception as e:
                print(f"❌ Error fixing {filepath}: {e}")
                continue

    print(f" Fixed {fixed_count} undefined name errors")


def fix_unused_variables():
    """Fix F841 unused variable errors by commenting them out."""
    print("🔧 Fixing unused variables (F841)...")

    success, output, _ = run_command("python -m flake8 --select=F841")
    if not success:
        print("❌ Could not get F841 errors")
        return

    fixed_count = 0
    for line in output.strip().split('
'):
        if not line or 'F841' not in line:
            continue

        parts = line.split(':')
        if len(parts) < 4:
            continue

        filepath = parts[0].lstrip('./')
        line_num = int(parts[1])

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if line_num > len(lines):
                continue

            # Comment out the unused variable assignment
            problem_line = lines[line_num - 1]
            if '=' in problem_line and not problem_line.strip().startswith('#'):
                # Add comment prefix while preserving indentation
                indent = len(problem_line) - len(problem_line.lstrip())
                comment_line = ' ' * indent + '# ' + problem_line.lstrip()
                lines[line_num - 1] = comment_line

                with open(filepath, 'w', encoding='utf-8') as f:
                    f.writelines(lines)

                print(f" Commented unused variable in {filepath}:{line_num}")
                fixed_count += 1

        except Exception as e:
            print(f"❌ Error fixing {filepath}: {e}")
            continue

    print(f" Fixed {fixed_count} unused variable errors")


def fix_line_length_issues():
    """Fix E501 line too long errors using autopep8."""
    print("🔧 Fixing line length issues (E501)...")

    success, _, _ = run_command(
        "autopep8 --in-place --aggressive --max-line-length=100 --recursive .")
    if success:
        print(" Applied autopep8 line length fixes")
    else:
        print("❌ Failed to apply autopep8 fixes")


def fix_continuation_lines():
    """Fix E127, E128, E131 continuation line errors."""
    print("🔧 Fixing continuation line issues...")

    success, output, _ = run_command("python -m flake8 --select=E127,E128,E131")
    if not success:
        print("❌ Could not get continuation errors")
        return

    fixed_count = 0
    for line in output.strip().split('
'):
        if not line or not any(code in line for code in ['E127', 'E128', 'E131']):
            continue

        parts = line.split(':')
        if len(parts) < 4:
            continue

        filepath = parts[0].lstrip('./')
        line_num = int(parts[1])

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if line_num > len(lines):
                continue

            # Remove problematic backslashes and fix indentation
            problem_line = lines[line_num - 1]

            # Remove redundant backslashes inside brackets
            if '\\' in problem_line and any(char in problem_line for char in ['(', '[', '{']):
                fixed_line = problem_line.replace('\\', '')
                lines[line_num - 1] = fixed_line

                with open(filepath, 'w', encoding='utf-8') as f:
                    f.writelines(lines)

                print(f" Fixed continuation in {filepath}:{line_num}")
                fixed_count += 1

        except Exception as e:
            print(f"❌ Error fixing {filepath}: {e}")
            continue

    print(f" Fixed {fixed_count} continuation line errors")


def remove_unused_imports():
    """Remove F401 unused imports using autoflake."""
    print("🔧 Removing unused imports (F401)...")

    success, _, _ = run_command("autoflake --in-place --remove-all-unused-imports --recursive .")
    if success:
        print(" Removed unused imports with autoflake")
    else:
        print("❌ Failed to remove unused imports")


def fix_whitespace_issues():
    """Fix whitespace issues."""
    print("🔧 Fixing whitespace issues...")

    # Fix E203 whitespace before ':'
    success, output, _ = run_command("python -m flake8 --select=E203")
    if success:
        fixed_count = 0
        for line in output.strip().split('
'):
            if not line or 'E203' not in line:
                continue

            parts = line.split(':')
            if len(parts) < 4:
                continue

            filepath = parts[0].lstrip('./')
            line_num = int(parts[1])

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                if line_num > len(lines):
                    continue

                # Remove whitespace before colons
                problem_line = lines[line_num - 1]
                fixed_line = re.sub(r'\s+:', ':', problem_line)

                if fixed_line != problem_line:
                    lines[line_num - 1] = fixed_line

                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.writelines(lines)

                    print(f" Fixed whitespace in {filepath}:{line_num}")
                    fixed_count += 1

            except Exception as e:
                print(f"❌ Error fixing {filepath}: {e}")
                continue

        print(f" Fixed {fixed_count} whitespace errors")


def main():
    """Run all fixes in order."""
    print(" Starting comprehensive flake8 error fixes...")

    # Get initial error count
    success, output, _ = run_command("python -m flake8 --count")
    initial_count = 0
    if success and output.strip().isdigit():
        initial_count = int(output.strip())

    print(f" Initial error count: {initial_count}")

    # Run fixes in order of importance
    fix_unterminated_strings()      # E999 - blocks everything else
    fix_undefined_names()           # F821 - import issues
    fix_unused_variables()          # F841 - comment out unused vars
    fix_continuation_lines()        # E127, E128, E131 - formatting
    fix_whitespace_issues()         # E203 - whitespace
    remove_unused_imports()         # F401 - unused imports
    fix_line_length_issues()        # E501 - line length

    # Get final error count
    success, output, _ = run_command("python -m flake8 --count")
    final_count = 0
    if success and output.strip().isdigit():
        final_count = int(output.strip())

    print(f" Final error count: {final_count}")
    print(f" Reduced errors by: {initial_count - final_count}")

    if final_count < initial_count:
        print(" Successfully reduced flake8 errors!")
    else:
        print("⚠️  Some errors may require manual intervention")


if __name__ == "__main__":
    main()

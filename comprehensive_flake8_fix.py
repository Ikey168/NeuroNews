#!/usr/bin/env python3
"""
Comprehensive Flake8 Error Fixing Script
Systematically addresses all flake8 errors in the codebase.
"""

import os
import re
import subprocess


def run_command(cmd):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        print(f"Error running command: {e}")
        return False, "", str(e)


def fix_trailing_whitespace():
    """Fix W291 trailing whitespace errors."""
    print("🔧 Fixing trailing whitespace (W291)...")
    success, _, _ = run_command(
        f"ind . -name '*.py' -exec sed -i 's/[[:space:]]*$//' {} +")
    if success:
        print(" Trailing whitespace fixed")
    else:
        print("❌ Failed to fix trailing whitespace")


def fix_blank_line_whitespace():
    """Fix W293 blank line contains whitespace errors."""
    print("🔧 Fixing blank line whitespace (W293)...")
    success, _, _ = run_command(
        f"ind . -name '*.py' -exec sed -i '/^[[:space:]]*$/s/.*//' {} +")
    if success:
        print(" Blank line whitespace fixed")
    else:
        print("❌ Failed to fix blank line whitespace")


def fix_unused_imports():
    """Fix F401 unused import errors using autoflake."""
    print("🔧 Fixing unused imports (F401)...")
    try:
        # Install autoflake if not available
        run_command("pip install autoflake")

        # Remove unused imports
        success, _, _ = run_command(
            "autoflake --remove-all-unused-imports --remove-unused-variables "
            "--in-place --recursive . --exclude=venv,env"
        )
        if success:
            print(" Unused imports removed")
        else:
            print("❌ Failed to remove unused imports")
    except Exception as e:
        print(f"❌ Error fixing unused imports: {e}")


def fix_comparison_operators():
    """Fix E712 comparison to True/False errors."""
    print("🔧 Fixing comparison operators (E712)...")

    # Fix is True patterns
    success1, _, _ = run_command(
        f"ind . -name '*.py' -exec sed -i 's/ is True/ is True/g' {} +"
    )
    # Fix is False patterns
    success2, _, _ = run_command(
        f"ind . -name '*.py' -exec sed -i 's/ is False/ is False/g' {} +"
    )
    # Fix is not True patterns
    success3, _, _ = run_command(
        f"ind . -name '*.py' -exec sed -i 's/ is not True/ is not True/g' {} +"
    )
    # Fix is not False patterns
    success4, _, _ = run_command(
        f"ind . -name '*.py' -exec sed -i 's/ is not False/ is not False/g' {} +"
    )

    if all([success1, success2, success3, success4]):
        print(" Comparison operators fixed")
    else:
        print("❌ Some comparison operator fixes failed")


def fix_f_string_placeholders():
    """Fix F541 f-string missing placeholders by converting to regular strings."""
    print("🔧 Fixing f-string placeholders (F541)...")

    python_files = []
    for root, dirs, files in os.walk("."):
        # Skip virtual environments
        if "venv" in root or "env" in root or ".git" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                python_files.append(os.path.join(root, file))

    fixed_count = 0
    for file_path in python_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Pattern to match f-strings without placeholders
            pattern = r'"([^"]*)"'"
            matches = re.findall(pattern, content)

            changed = False
            for match in matches:
                if '{' not in match:  # No placeholders
                    old_string = ff'"{match}"'
                    new_string = f'"{match}"'
                    content = content.replace(old_string, new_string)
                    changed = True

            # Also handle '...' strings
            pattern = r"'([^']*)'"'
            matches = re.findall(pattern, content)

            for match in matches:
                if '{' not in match:  # No placeholders
                    old_string = ff"'{match}'"
                    new_string = f"'{match}'"
                    content = content.replace(old_string, new_string)
                    changed = True

            if changed:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                fixed_count += 1

        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    print(f" Fixed f-string placeholders in {fixed_count} files")


def fix_unused_variables():
    """Comment out F841 unused variables."""
    print("🔧 Commenting out unused variables (F841)...")

    # Get F841 errors
    success, output, _ = run_command("python -m flake8 --select=F841")
    if not success:
        print("❌ Could not get F841 errors")
        return

    fixed_count = 0
    for line in output.strip().split('
'):
        if not line:
            continue

        try:
            # Parse flake8 output: ./file.py:line:col: F841 message
            parts = line.split(':', 3)
            if len(parts) >= 4:
                file_path = parts[0].lstrip('./')
                line_num = int(parts[1])

                # Read the file
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                # Comment out the line if it's not already commented'
                if line_num <= len(lines):
                    original_line = lines[line_num - 1]
                    if not original_line.strip().startswith('#'):
                        # Add comment
                        indentation = len(original_line) - len(original_line.lstrip())
                        lines[line_num - 1] = ' ' * indentation + '# ' + original_line.lstrip()

                        # Write back
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.writelines(lines)
                        fixed_count += 1

        except Exception as e:
            print(f"Error processing line: {line}, error: {e}")

    print(f" Commented out {fixed_count} unused variables")


def fix_function_spacing():
    """Fix E302 and E305 function spacing errors."""
    print("🔧 Fixing function spacing (E302, E305)...")

    python_files = []
    for root, dirs, files in os.walk("."):
        if "venv" in root or "env" in root or ".git" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                python_files.append(os.path.join(root, file))

    fixed_count = 0
    for file_path in python_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            changed = False
            new_lines = []

            for i, line in enumerate(lines):
                # Check for function/class definitions
                if (line.strip().startswith('def ') or
                    line.strip().startswith('class ') or
                        line.strip().startswith('async def ')):

                    # Check if we need to add blank lines before
                    if i > 0:
                        prev_lines = [lines[j] for j in range(max(0, i - 3), i) if j < len(lines)]
                        non_empty_before = [l for l in prev_lines if l.strip()]

                        if non_empty_before and not all(l.strip().startswith('#')
                                                        for l in prev_lines[-2:]):
                            # Add blank lines if not enough
                            blank_lines = len([l for l in prev_lines if not l.strip()])
                            if blank_lines < 2:
                                new_lines.extend([''
'] * (2 - blank_lines))'
                                changed = True

                new_lines.append(line)

                # Check for blank lines after function/class definitions
                if (line.strip().startswith('def ') or
                    line.strip().startswith('class ') or
                        line.strip().startswith('async def ')):

                    # Look ahead to see if this is the end of the file or class
                    if i < len(lines) - 1:
                        next_lines = lines[i + 1:i + 4]
                        # If next significant line is at same indentation level, add blank lines
                        current_indent = len(line) - len(line.lstrip())
                        for j, next_line in enumerate(next_lines):
                            if next_line.strip():
                                next_indent = len(next_line) - len(next_line.lstrip())
                                if (next_indent <= current_indent and
                                    not next_line.strip().startswith('#') and
                                        j < 2):  # Not enough blank lines
                                    new_lines.append(''
')'
                                    changed = True
                                break

            if changed:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                fixed_count += 1

        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    print(f" Fixed function spacing in {fixed_count} files")


def main():
    """Main execution function."""
    print(" Starting comprehensive flake8 error fixing...")
    print("=" * 60)

    # Run fixes in order of impact and safety
    fix_trailing_whitespace()
    fix_blank_line_whitespace()
    fix_comparison_operators()
    fix_f_string_placeholders()
    fix_unused_variables()
    fix_function_spacing()

    # Apply autopep8 for additional fixes
    print("🔧 Running autopep8 for additional fixes...")
    success, _, _ = run_command(
        "pip install autopep8 && autopep8 --in-place --recursive --max-line-length=100 "
        "--exclude=venv,env --aggressive --aggressive ."
    )
    if success:
        print(" autopep8 fixes applied")
    else:
        print("❌ autopep8 fixes failed")

    # Try autoflake for unused imports
    fix_unused_imports()

    print("=" * 60)
    print(" Comprehensive flake8 fixing complete!")
    print(""
Running final flake8 check...")"

    # Final check
    success, output, _ = run_command("python -m flake8 --count --statistics --max-line-length=100")
    if success:
        print(" All flake8 errors resolved!")
    else:
        print(" Remaining flake8 issues:")
        lines = output.strip().split(''
')'
        for line in lines[-10:]:  # Show last 10 lines (summary)
            print(f"   {line}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Fix precision formatting issues in .format() calls.
"""
import os
import re


def fix_precision_formatting(content):
    """Fix precision formatting in .format() calls."""

    # Pattern: .format(variable:.2f) -> move precision inside format string

    def fix_precision(match):
        match.group(0)
        format_string = match.group(1)
        args_text = match.group(2)

        # Find precision patterns in the arguments
        args = []
        precision_patterns = []

        # Split by comma and process each argument
        if args_text.strip():
            arg_parts = args_text.split(",")
            for i, arg in enumerate(arg_parts):
                arg = arg.strip()
                # Check for precision pattern like variable:.2f
                precision_match = re.search(r"^([^:]+):([\.\d\w]+)$", arg)
                if precision_match:
                    var_name = precision_match.group(1).strip()
                    precision = precision_match.group(2)
                    args.append(var_name)
                    # Store which positional argument needs precision
                    precision_patterns.append((i, precision))
                else:
                    args.append(arg)

        # Update format string with precision specifiers
        new_format_string = format_string
        for pos, precision in precision_patterns:
            # Replace {pos} with {pos:precision} in format string
            new_format_string = re.sub(
                r"\{" + str(pos) + r"\}",
                "{" + str(pos) + ":" + precision + "}",
                new_format_string,
            )

        return '"{0}".format({1})'.format(new_format_string, ", ".join(args))

    # Pattern: "text {0}".format(var:.2f)
    content = re.sub(
        r'"([^"]*\{[^}]*\}[^"]*)"\s*\.\s*format\s*\(([^)]*:[^)]*)\)',
        fix_precision,
        content,
    )

    return content


def process_file(file_path):
    """Process a single file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        original_content = content

        # Fix precision formatting issues
        content = fix_precision_formatting(content)

        # Manual fixes for specific patterns
        manual_fixes = [
            # Fix double format calls
            (
                r'"\s*\.\s*format\([^)]+\)\s*"\s*\.\s*format\([^)]+\)',
                lambda m: fix_double_format(m.group(0)),
            ),
        ]

        for pattern, replacement in manual_fixes:
            if callable(replacement):
                content = re.sub(pattern, replacement, content)
            else:
                content = re.sub(pattern, replacement, content)

        # Write back if changed
        if content != original_content:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Updated: {file_path}")
            return True

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False

    return False


def fix_double_format(text):
    """Fix cases where we have double .format() calls."""
    # This is a placeholder - would need specific handling
    return text


def main():
    """Process all Python files in src directory."""
    updated_count = 0

    for root, dirs, files in os.walk("src"):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                if process_file(file_path):
                    updated_count += 1

    print(f"Updated {updated_count} files")


if __name__ == "__main__":
    main()

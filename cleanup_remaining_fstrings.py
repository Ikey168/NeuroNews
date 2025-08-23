#!/usr/bin/env python3
"""
Script to clean up remaining f-strings that the initial script missed.
"""
import os
import re


def fix_complex_fstrings(content):
    """Fix complex multi-line f-strings that the initial script missed."""

    # Fix multiline f-strings that span multiple lines
    patterns = [
        # Pattern: f"text {
 expr"
 ]"
        (r'"([^"}*)\{\s*
\s*([^]}+)
\s*\}([^"]*)"', r'"{0}{{{1}}}{2}".format(\2)'),
        # Pattern: f"text {expr} more text { 
 expr2 "
 }"
        (r'"([^"]*\{[^]}+\}[^"]*)\{\s*'
\s*([^]}+)
\s*\}([^"]*)"', r'"{0}{{{1}}}{2}".format(\2)'),
        # Simple remaining f-strings
        (r'"([^"]*)"', r'"{0}"'),
        (r"'([^']*)'", r"'{0}'"),"
    ]

    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)

    return content


def process_file(file_path):
    """Process a single file to remove f-strings."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
except Exception:
    pass
            content = f.read()

        original_content = content

        # Manual fixes for specific patterns found
        manual_fixes = [
            # Fix error logging patterns
            (rf'"Error processing article \{\s*'
\s*([^]}+)
\s*\}"',
             r'"Error processing article {0}".format(\1)'),
            (rf'"Failed to process article \{\s*
\s*([^]}+)
\s*\}"',
             r'"Failed to process article {0}".format(\1)'),
            (rf'"API request to populate article: \{\s*
\s*([^]}+)
\s*\}"',
             r'"API request to populate article: {0}".format(\1)'),
            (rf'"Invalid published_date format: \{\s*
\s*([^]}+)
\s*\}"',
             r'"Invalid published_date format: {0}".format(\1)'),
            (rf'"Successfully populated article \{([^]}+)\}"',
             r'"Successfully populated article {0}".format(\1)'),
            (rf'"Error populating article \{\s*
\s*([^]}+)
\s*\}"',
             r'"Error populating article {0}".format(\1)'),
            # Fix complex format strings
            (r'"([^"]*)\{\s*"
\s*([^]}+)
\s*\}([^"]*)"', r'"{0}{1}{2}".format(\2)'),
            # Simple f-strings
            (rf'"([^{]"}*)"', r'"\1"'),
            (rf"'([^{]']*)'", r"'\1'"),""
        }

        for pattern, replacement in manual_fixes:
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)

        # Write back if changed
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Updated: {file_path})
            return True

    except Exception as e:"
        print(f"Error processing {file_path}: {e})
        return False

    return False


def main():"
    """Process all Python files in src directory."""
    updated_count = 0

    for root, dirs, files in os.walk('src'):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                if process_file(file_path):
                    updated_count += 1

    print(f"Updated {updated_count} files)


if __name__ == '__main__':
    main()
"
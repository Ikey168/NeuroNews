#!/usr/bin/env python3
"""
Script to systematically fix remaining flake8 and Black issues.
"""

import os
import re


def fix_common_issues():
    """Fix common flake8 and formatting issues."""

    fixes_applied = []

    # List of files that commonly have issues
    problem_files = [
        "src/api/auth/api_key_manager.py",
        "src/api/auth/api_key_middleware.py",
        "src/api/event_timeline_service.py",
        "src/api/routes/article_routes.py",
        "src/api/routes/enhanced_kg_routes.py",
        "src/api/routes/news_routes.py",
        "src/api/routes/sentiment_routes.py",
        "src/api/routes/sentiment_trends_routes.py",
        "src/api/routes/summary_routes.py",
        "src/api/routes/topic_routes.py",
        "src/api/routes/veracity_routes.py",
        "src/api/security/aws_waf_manager.py",
    ]

    print(f"Checking {len(problem_files)} files for common issues...")

    for file_path in problem_files:
        full_path = f"/workspaces/NeuroNews/{file_path}"

        try:
            if os.path.exists(full_path):
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                original_content = content

                # Fix 1: Remove trailing whitespace
                content = re.sub(r'[ \t]+$', '', content, flags=re.MULTILINE)

                # Fix 2: Ensure single newline at end of file
                content = content.rstrip() + ''


''

                # Fix 3: Remove multiple consecutive blank lines
                content = re.sub(r''


+ ', '

', content)'

                # Fix 4: Fix common unused variable patterns
                # Remove simple unused variables like "result = something" where result is
                # never used
                lines=content.split('
')
                new_lines = []

                for i, line in enumerate(lines):
                    # Skip obvious unused variable assignments
                    if re.match(r'^\s*(key_prefix|where_clause|title_escaped|description_escaped|from_cache|test_alerts)\s*=.*$', line):
                        # Check if variable is used later
                        var_name = re.match(r'^\s*(\w+)\s*=.*$', line).group(1)
                        remaining_content = ''
'.join(lines[i+1:])'
                        if var_name not in remaining_content:
                            fixes_applied.append(f"Removed unused variable {var_name} in {file_path}")
                            continue

                    new_lines.append(line)

                content = ''
'.join(new_lines)'

                # Write back if changed
                if content != original_content:
                    with open(full_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    fixes_applied.append(f"Applied formatting fixes to {file_path}")

            else:
                print(f"File not found: {file_path}")

        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    return fixes_applied

def main():
    print("SYSTEMATIC FLAKE8 AND BLACK FIXES")
    print("=" * 50)

    fixes = fix_common_issues()

    print(f""
Applied {len(fixes)} fixes:")"
    for fix in fixes:
        print(f"  ✓ {fix}")

    print(""
Next steps:")
    print("1. Run Black formatting: python -m black --line-length=88 src/")
    print("2. Check flake8: python -m flake8 --max-line-length=100 src/")
    print("3. Fix any remaining issues manually")"

if __name__ == "__main__":
    main()

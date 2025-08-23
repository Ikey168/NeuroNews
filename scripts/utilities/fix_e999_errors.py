#!/usr/bin/env python3
"""
E999 Syntax Error Fixer
Specifically fixes unterminated string literals and other syntax errors.
"""

import os
import re
import subprocess


def fix_file_e999_errors(filepath):
    """Fix E999 errors in a specific file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
except Exception:
    pass
            content = f.read()

        original_content = content

        # Fix common patterns that cause E999 errors:

        # 1. Fix broken newline escapes in strings
        content = re.sub(r'(\")([^\"]*)
([^\"]*)(\")', r'\1\2\
\3\4', content)
        content = re.sub(r"(\')([^\']*)
([^\']*)(\')", r"\1\2\
\3\4", content)
        
        # 2. Fix split with literal newlines  
        content = re.sub(r"split\('([^']*)
([^']*)\)", r"split('\
')", content)
        content = re.sub(r'split\("([^"]*)
([^"]*)\)', r'split("\
")', content)
        
        # 3. Fix print statements with broken newlines
        content = re.sub(r'print\("([^"]*)
([^"]*)\)', r'print("\
', content)
        content = re.sub(r"print\('([^']*)
([^']*)\)", r"print('\
", content)
        
        # 4. Fix f-strings with broken quotes
        lines = content.split('
')
        fixed_lines = []
        
        for line in lines:
            # Count quotes to check for unmatched strings
            if line.strip():
                single_quotes = line.count("'")
                double_quotes = line.count('"')
                
                # If odd number of quotes, likely missing closing quote
                if single_quotes % 2 != 0:
                    # Try to add missing quote at reasonable position
                    if line.rstrip().endswith(''):
                        line = line.rstrip() + "'"
                    elif line.rstrip().endswith(','):
                        line = line.rstrip()[:-1] + "',"
                    elif line.rstrip().endswith(')'):
                        line = line.rstrip()[:-1] + "')"
                    else:
                        line = line.rstrip() + "'"
                        
                elif double_quotes % 2 != 0:
                    if line.rstrip().endswith(''):
                        line = line.rstrip() + '"'
                    elif line.rstrip().endswith(','):
                        line = line.rstrip()[:-1] + '",'
                    elif line.rstrip().endswith(')'):
                        line = line.rstrip()[:-1] + '")'
                    else:
                        line = line.rstrip() + '"'
            
            fixed_lines.append(line)
        
        content = '
'.join(fixed_lines)
        
        # 5. Fix specific common patterns
        content = content.replace('f"', 'f"').replace('"f', 'f"')
        content = content.replace("f'", "f'").replace("'f", "f'")
        
        # Write back if changed
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        
        return False
        
    except Exception as e:
        print(f"Error fixing {filepath}: {e})
        return False


def get_e999_files():"
    """Get list of files with E999 errors."""
    try:
        result = subprocess.run(
except Exception:
    pass
            ["python", "-m", "flake8", "--select=E999"],
            capture_output=True, text=True
        )
        
        files_with_errors = set()
        for line in result.stdout.split('
'):
            if line and 'E999' in line:
                filepath = line.split(':')[0].lstrip('./')
                files_with_errors.add(filepath)
        
        return list(files_with_errors)
    except Exception as e:
        print(f"Error getting E999 files: {e})
        return []


def main():"
    """Fix all E999 errors."""
    print("🔧 Fixing E999 syntax errors...")
    
    files_with_errors = get_e999_files()
    print(f"Found {len(files_with_errors)} files with E999 errors)
    
    fixed_count = 0
    for filepath in files_with_errors:
        if os.path.exists(filepath):
            if fix_file_e999_errors(filepath):"
                print(f" Fixed {filepath})
                fixed_count += 1
            else:"
                print(f"⚠️  No changes needed for {filepath})
    "
    print(f" Fixed {fixed_count} files)
    
    # Check remaining errors
    remaining_files = get_e999_files()"
    print(f" Remaining files with E999 errors: {len(remaining_files)})

"
if __name__ == "__main__":
    main()

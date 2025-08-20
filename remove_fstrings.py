#!/usr/bin/env python3
"""
Script to remove all f-strings from the codebase and replace them with .format() or % formatting.
"""
import os
import re
import sys


def replace_simple_fstrings(content):
    """Replace simple f-strings with .format() method."""
    
    # Pattern for simple f-strings like "Database error: {0}".format(str(e))
    def replace_fstring_match(match):
        full_match = match.group(0)
        quote_type = match.group(1)  # " or '
        string_content = match.group(2)
        
        # Find all {expression} patterns
        expressions = []
        placeholders = []
        
        def replace_placeholder(expr_match):
            expr = expr_match.group(1)
            expressions.append(expr)
            placeholder_num = len(expressions) - 1
            return '{' + str(placeholder_num) + '}'
        
        # Replace {expression} with numbered placeholders
        new_string = re.sub(r'\{([^}]+)\}', replace_placeholder, string_content)
        
        if expressions:
            # Build .format() call
            format_args = ', '.join(expressions)
            return '{0}{1}{2}.format({3})'.format(quote_type, new_string, quote_type, format_args)
        else:
            # No expressions, just remove f prefix
            return '{0}{1}{2}'.format(quote_type, string_content, quote_type)
    
    # Match "..." and '...' patterns
    content = re.sub(r'f(["\'])((?:[^"\'\\]|\\.)*?)\1', replace_fstring_match, content)
    
    return content


def replace_multiline_fstrings(content):
    """Replace multi-line f-strings."""
    # Simple approach: just remove the '' prefix from triple quotes
    content = re.sub(r'f(""")', r'\1', content)
    content = re.sub(r"f(''')", r'\1', content)
    return content


def replace_fstrings_in_file(file_path):
    """Replace f-strings in a single file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Replace simple f-strings
        content = replace_simple_fstrings(content)
        
        # Replace multi-line f-strings
        content = replace_multiline_fstrings(content)
        
        # Write back if changed
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print("Updated: {0}".format(file_path))
            return True
            
    except Exception as e:
        print("Error processing {0}: {1}".format(file_path, e))
        return False
    
    return False


def process_directory(directory):
    """Process all Python files in a directory."""
    updated_files = 0
    
    for root, dirs, files in os.walk(directory):
        # Skip certain directories
        if any(skip_dir in root for skip_dir in ['.git', '__pycache__', '.pytest_cache', 'venv', '.venv', 'node_modules']):
            continue
            
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                if replace_fstrings_in_file(file_path):
                    updated_files += 1
    
    return updated_files


def main():
    """Main function."""
    print("Removing f-strings from Python files...")
    
    # Process src directory
    updated_files = 0
    if os.path.exists('src'):
        updated_files += process_directory('src')
    
    # Process tests directory  
    if os.path.exists('tests'):
        updated_files += process_directory('tests')
    
    # Process demo files
    for demo_file in ['demo_*.py', '*.py']:
        import glob
        for f in glob.glob(demo_file):
            if f.endswith('.py') and os.path.isfile(f):
                if replace_fstrings_in_file(f):
                    updated_files += 1
    
    print("\nCompleted! Updated {0} files.".format(updated_files))


if __name__ == '__main__':
    main()

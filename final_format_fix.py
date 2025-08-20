#!/usr/bin/env python3
"""
Final cleanup script to fix all remaining formatting issues.
"""
import os
import re


def fix_all_format_issues(content):
    """Fix all format-related issues."""
    
    # Fix precision formatting: .format(var:.2f) -> move precision to format string
    def fix_precision_in_format(match):
        before_format = match.group(1)
        args_part = match.group(2)
        
        # Parse arguments to find precision patterns
        if not args_part.strip():
            return before_format + '.format()'
            
        args = []
        new_format_positions = {}
        arg_list = re.split(r',(?![^()]*\))', args_part)  # Split by comma not inside parentheses
        
        for i, arg in enumerate(arg_list):
            arg = arg.strip()
            # Check for precision pattern like variable:.2f
            precision_match = re.match(r'^([^:]+):([\.\d\w%]+)$', arg)
            if precision_match:
                var_name = precision_match.group(1).strip()
                precision = precision_match.group(2)
                args.append(var_name)
                new_format_positions[i] = precision
            else:
                args.append(arg)
        
        # Update format string with precision
        new_format_string = before_format
        for pos, precision in new_format_positions.items():
            # Replace {pos} with {pos:precision} in format string
            pattern = r'\{' + str(pos) + r'\}'
            replacement = '{' + str(pos) + ':' + precision + '}'
            new_format_string = re.sub(pattern, replacement, new_format_string)
        
        return new_format_string + '.format(' + ', '.join(args) + ')'
    
    # Apply the precision fix
    content = re.sub(
        r'("[^"]*(?:\{[^}]*\}[^"]*)*")\s*\.\s*format\s*\(\s*([^)]*:[^)]*)\s*\)',
        fix_precision_in_format,
        content
    )
    
    # Fix incomplete format strings
    fixes = [
        # Fix incomplete array slicing
        (r'\.format\(([^)]*)\[\)', r'.format(\1[:100])'),
        (r'\.format\(([^)]*)\[([^)]*)\)', r'.format(\1[\2])'),
        
        # Fix standalone precision formatting
        (r'([a-zA-Z_][a-zA-Z0-9_]*):(\.[\d]+[fd])', r'\1'),
        
        # Fix broken parentheses in format strings
        (r'\.format\(([^)]*)\[\s*$', r'.format(\1[:100])'),
    ]
    
    for pattern, replacement in fixes:
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    
    return content


def process_file(file_path):
    """Process a single file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        content = fix_all_format_issues(content)
        
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Fixed: {file_path}")
            return True
            
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False
    
    return False


def main():
    """Process all Python files in src directory."""
    updated_count = 0
    
    for root, dirs, files in os.walk('src'):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                if process_file(file_path):
                    updated_count += 1
    
    print(f"Fixed {updated_count} files")


if __name__ == '__main__':
    main()

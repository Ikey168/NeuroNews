#!/usr/bin/env python3
"""
Script to automatically fix common flake8 errors across the codebase.
"""

import re
import os
import subprocess
from pathlib import Path


def fix_f841_errors(file_path, line_number, variable_name):
    """Remove or fix F841 unused variable errors"""
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    # Check if it's a simple assignment we can remove
    line = lines[line_number - 1]
    if f"{variable_name} = " in line and line.strip().startswith(variable_name):
        # Remove the line entirely if it's just an unused assignment
        lines.pop(line_number - 1)
        
        with open(file_path, 'w') as f:
            f.writelines(lines)
        print(f"Fixed F841 in {file_path}:{line_number} - removed unused variable {variable_name}")
        return True
    
    return False


def fix_e501_errors(file_path, line_number):
    """Fix E501 line too long errors by breaking lines"""
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    line = lines[line_number - 1].rstrip()
    
    # Handle long strings
    if '= "' in line and len(line) > 100:
        # Try to break long string assignments
        parts = line.split('= "', 1)
        if len(parts) == 2:
            indent = len(parts[0]) - len(parts[0].lstrip())
            base_indent = ' ' * indent
            string_content = parts[1][:-1]  # Remove closing quote
            
            if len(string_content) > 80:
                # Break into multiple lines
                words = string_content.split(' ')
                lines_list = []
                current_line = ""
                
                for word in words:
                    if len(current_line + word + ' ') > 80:
                        if current_line:
                            lines_list.append(current_line.strip())
                            current_line = word + ' '
                        else:
                            lines_list.append(word + ' ')
                    else:
                        current_line += word + ' '
                
                if current_line:
                    lines_list.append(current_line.strip())
                
                if len(lines_list) > 1:
                    new_lines = []
                    new_lines.append(f"{parts[0]}= (\n")
                    for i, line_part in enumerate(lines_list):
                        if i == len(lines_list) - 1:
                            new_lines.append(f'{base_indent}    "{line_part}"\n')
                        else:
                            new_lines.append(f'{base_indent}    "{line_part} "\n')
                    new_lines.append(f'{base_indent})\n')
                    
                    lines[line_number - 1:line_number] = new_lines
                    
                    with open(file_path, 'w') as f:
                        f.writelines(lines)
                    print(f"Fixed E501 in {file_path}:{line_number} - broke long string")
                    return True
    
    return False


def main():
    """Main function to fix all flake8 errors"""
    
    # Get flake8 errors
    result = subprocess.run(['flake8', '--max-line-length=100', 'src/', 'tests/'], 
                          capture_output=True, text=True)
    
    if result.returncode == 0:
        print("No flake8 errors found!")
        return
    
    errors = result.stdout.strip().split('\n')
    
    # Group errors by type
    f841_errors = []
    e501_errors = []
    f821_errors = []
    
    for error in errors:
        if not error.strip():
            continue
            
        parts = error.split(':')
        if len(parts) >= 4:
            file_path = parts[0]
            line_number = int(parts[1])
            error_code = parts[3].strip().split()[0]
            
            if error_code == 'F841':
                # Extract variable name
                match = re.search(r"local variable '(\w+)' is assigned to but never used", error)
                if match:
                    var_name = match.group(1)
                    f841_errors.append((file_path, line_number, var_name))
            
            elif error_code == 'E501':
                e501_errors.append((file_path, line_number))
            
            elif error_code == 'F821':
                f821_errors.append((file_path, line_number, error))
    
    print(f"Found {len(f841_errors)} F841 errors, {len(e501_errors)} E501 errors, {len(f821_errors)} F821 errors")
    
    # Fix F841 errors first (unused variables)
    for file_path, line_number, var_name in f841_errors:
        try:
            fix_f841_errors(file_path, line_number, var_name)
        except Exception as e:
            print(f"Error fixing F841 in {file_path}:{line_number}: {e}")
    
    # Fix E501 errors (line too long)
    for file_path, line_number in e501_errors:
        try:
            fix_e501_errors(file_path, line_number)
        except Exception as e:
            print(f"Error fixing E501 in {file_path}:{line_number}: {e}")
    
    print("Automatic fixes completed. Some errors may need manual attention.")


if __name__ == "__main__":
    main()

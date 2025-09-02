#!/usr/bin/env python3
"""Fix test functions with incorrect self parameter."""
import re
import os

def fix_test_functions(file_path):
    """Fix test functions that have self parameter but aren't in a class."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Pattern to match function definitions with self parameter that aren't in classes
        # Look for 'def test_...(self):' that are not indented (not in a class)
        pattern = r'^def (test_[^(]+)\(self\):'
        
        # Replace with just the function name without self
        new_content = re.sub(pattern, r'def \1():', content, flags=re.MULTILINE)
        
        if new_content != content:
            with open(file_path, 'w') as f:
                f.write(new_content)
            print(f"Fixed {file_path}")
            return True
        return False
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False

# Find all test files and fix them
test_files = [
    "/workspaces/NeuroNews/tests/unit/auth/test_jwt_auth.py",
    "/workspaces/NeuroNews/tests/unit/routes/test_veracity_routes.py", 
    "/workspaces/NeuroNews/tests/unit/routes/test_topic_routes.py",
    "/workspaces/NeuroNews/tests/unit/routes/test_influence_routes.py",
    "/workspaces/NeuroNews/tests/unit/routes/test_knowledge_graph_routes.py",
    "/workspaces/NeuroNews/tests/unit/rbac/test_rbac_system.py",
    "/workspaces/NeuroNews/tests/unit/handlers/test_error_handlers.py",
    "/workspaces/NeuroNews/tests/unit/routes/test_multiple_routes.py",
    "/workspaces/NeuroNews/tests/unit/middleware/test_multiple_middleware.py"
]

for file_path in test_files:
    if os.path.exists(file_path):
        fix_test_functions(file_path)
    else:
        print(f"File not found: {file_path}")

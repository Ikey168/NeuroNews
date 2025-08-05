#!/usr/bin/env python3
"""
Script to create GitHub issues for BDU Milestone 3
This script generates the GitHub CLI commands needed to create all issues for milestone 3.
"""

import json
import subprocess
import sys
from typing import List, Dict

# Issue data for BDU Milestone 3
MILESTONE_3_ISSUES = [
    {
        "title": "Define D1 schema & write migrations",
        "body": """## Description

- [ ] Create Wrangler migration files for `users`, `events`, and `registrations` tables (per schema in README)
- [ ] Verify migrations run successfully against a fresh D1 instance

## Acceptance Criteria

- [ ] Migration files are created in the correct format
- [ ] All table schemas match the specifications in README
- [ ] Migrations execute without errors on fresh D1 instance
- [ ] Rollback migrations work correctly""",
        "labels": ["infra", "cloudflare-workers", "d1"],
        "milestone": "3"
    },
    {
        "title": "Implement `GET /api/users` & `POST /api/users`",
        "body": """## Description

- [ ] Worker endpoint to list users and to register new users
- [ ] Enforce unique email/username constraints

## Acceptance Criteria

- [ ] GET /api/users returns list of all users
- [ ] POST /api/users creates new user with validation
- [ ] Unique email constraint is enforced
- [ ] Unique username constraint is enforced
- [ ] Proper error handling for constraint violations""",
        "labels": ["backend", "api", "cloudflare-workers"],
        "milestone": "3"
    },
    {
        "title": "Implement `GET /api/events` & `POST /api/events`",
        "body": """## Description

- [ ] Worker endpoint to list all events (with optional `type` filter) and to create new events
- [ ] Validate `start_time < end_time`

## Acceptance Criteria

- [ ] GET /api/events returns list of all events
- [ ] GET /api/events supports optional type filter parameter
- [ ] POST /api/events creates new event with validation
- [ ] start_time < end_time validation is enforced
- [ ] Proper error responses for validation failures""",
        "labels": ["backend", "api", "cloudflare-workers"],
        "milestone": "3"
    },
    {
        "title": "Implement `POST /api/registrations` & `GET /api/registrations`",
        "body": """## Description

- [ ] Endpoint for users to register for an event; enforce one registration per user/event
- [ ] Admin endpoint to list registrations by event

## Acceptance Criteria

- [ ] POST /api/registrations allows users to register for events
- [ ] One registration per user/event constraint is enforced
- [ ] GET /api/registrations lists registrations by event (admin only)
- [ ] Proper error handling for duplicate registrations
- [ ] Admin-only access control for listing endpoint""",
        "labels": ["backend", "api", "cloudflare-workers"],
        "milestone": "3"
    },
    {
        "title": "Add authentication via Pages Members",
        "body": """## Description

- [ ] Protect write endpoints (`POST /*`), only callable by authenticated members
- [ ] Expose current user info at `GET /api/auth/session`

## Acceptance Criteria

- [ ] All POST endpoints require authentication
- [ ] Authentication is implemented via Pages Members
- [ ] GET /api/auth/session returns current user information
- [ ] Unauthenticated requests to protected endpoints return 401
- [ ] Authentication middleware is reusable across endpoints""",
        "labels": ["backend", "auth", "cloudflare-workers"],
        "milestone": "3"
    },
    {
        "title": "Input validation middleware",
        "body": """## Description

- [ ] Create a reusable Hono/Vite middleware for request body validation (e.g. using Zod)
- [ ] Apply to all write endpoints

## Acceptance Criteria

- [ ] Reusable validation middleware is created
- [ ] Middleware uses Zod for schema validation
- [ ] All write endpoints use the validation middleware
- [ ] Validation errors return consistent error format
- [ ] Middleware is well-documented and easy to use""",
        "labels": ["backend", "validation", "cloudflare-workers"],
        "milestone": "3"
    },
    {
        "title": "Error-handling & logging",
        "body": """## Description

- [ ] Standardize error responses (status codes + JSON `{error: message}`)
- [ ] Integrate Cloudflare Workers' logging (e.g. `console.error`, Workers KV) for failed requests

## Acceptance Criteria

- [ ] All endpoints return standardized error format
- [ ] Consistent HTTP status codes are used
- [ ] Failed requests are logged appropriately
- [ ] Cloudflare Workers logging is integrated
- [ ] Error handling middleware is implemented""",
        "labels": ["backend", "observability", "cloudflare-workers"],
        "milestone": "3"
    },
    {
        "title": "Unit tests for each endpoint",
        "body": """## Description

- [ ] Write Jest or Vitest tests for success and failure cases of each API route
- [ ] Mock D1 bindings via `wrangler dev` or Miniflare

## Acceptance Criteria

- [ ] Unit tests cover all API endpoints
- [ ] Both success and failure cases are tested
- [ ] D1 bindings are properly mocked
- [ ] Tests use Jest or Vitest framework
- [ ] Test coverage is comprehensive
- [ ] Tests can be run in CI environment""",
        "labels": ["test", "unit-tests", "cloudflare-workers"],
        "milestone": "3"
    },
    {
        "title": "Integration tests with real D1",
        "body": """## Description

- [ ] CI job that runs against a preview D1 instance to verify migrations and CRUD end-to-end
- [ ] Clean up test data after each run

## Acceptance Criteria

- [ ] Integration tests run against real D1 instance
- [ ] Tests verify migrations work correctly
- [ ] End-to-end CRUD operations are tested
- [ ] Test data is cleaned up after each run
- [ ] CI job is properly configured
- [ ] Tests use preview D1 environment""",
        "labels": ["test", "integration-tests", "ci"],
        "milestone": "3"
    },
    {
        "title": "Update API documentation",
        "body": """## Description

- [ ] Document all routes, request/response schemas, example cURL calls in `/docs/api.md`
- [ ] Ensure README links to this file

## Acceptance Criteria

- [ ] All API routes are documented in /docs/api.md
- [ ] Request/response schemas are clearly defined
- [ ] Example cURL calls are provided for each endpoint
- [ ] README.md links to the API documentation
- [ ] Documentation is kept up-to-date with implementation""",
        "labels": ["documentation", "api"],
        "milestone": "3"
    }
]

def generate_gh_commands(repo: str = "Ikey168/BDU") -> List[str]:
    """Generate GitHub CLI commands to create issues."""
    commands = []
    
    for issue in MILESTONE_3_ISSUES:
        # Prepare labels as comma-separated string
        labels_str = ",".join(issue["labels"])
        
        # Create the gh command
        cmd = f"""gh issue create \\
  --repo {repo} \\
  --title "{issue['title']}" \\
  --body "{issue['body'].replace(chr(10), '\\n')}" \\
  --label "{labels_str}" \\
  --milestone "{issue['milestone']}" """
        
        commands.append(cmd)
    
    return commands

def create_script_file(output_file: str = "create_issues.sh"):
    """Create a shell script with all the commands."""
    commands = generate_gh_commands()
    
    script_content = f"""#!/bin/bash
# Script to create all BDU Milestone 3 issues
# Make sure you have gh CLI installed and authenticated
# Run: chmod +x {output_file} && ./{output_file}

set -e

echo "Creating BDU Milestone 3 issues..."
echo "Make sure you have access to the Ikey168/BDU repository"
echo ""

"""
    
    for i, cmd in enumerate(commands, 1):
        script_content += f"""echo "Creating issue {i}/10..."
{cmd}
echo "Issue {i} created successfully"
echo ""

"""
    
    script_content += """echo "All issues created successfully!"
echo "Check https://github.com/Ikey168/BDU/issues to verify"
"""
    
    with open(output_file, 'w') as f:
        f.write(script_content)
    
    print(f"Script created: {output_file}")
    print(f"Make it executable with: chmod +x {output_file}")
    print(f"Run with: ./{output_file}")

def print_manual_instructions():
    """Print manual instructions for creating issues."""
    print("MANUAL INSTRUCTIONS FOR CREATING BDU MILESTONE 3 ISSUES")
    print("=" * 60)
    print()
    print("If you prefer to create issues manually, use these commands:")
    print()
    
    commands = generate_gh_commands()
    for i, cmd in enumerate(commands, 1):
        print(f"# Issue {i}/10")
        print(cmd)
        print()

def create_json_export():
    """Create a JSON file with all issue data."""
    with open("bdu_milestone3_issues.json", 'w') as f:
        json.dump(MILESTONE_3_ISSUES, f, indent=2)
    
    print("JSON export created: bdu_milestone3_issues.json")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--manual":
            print_manual_instructions()
        elif sys.argv[1] == "--json":
            create_json_export()
        elif sys.argv[1] == "--script":
            create_script_file()
        else:
            print("Usage: python create_bdu_milestone3_issues.py [--manual|--json|--script]")
    else:
        # Default behavior: create script file
        create_script_file()
        print()
        print("Also creating JSON export and showing manual instructions...")
        print()
        create_json_export()
        print()
        print_manual_instructions()
#!/bin/bash
# Script to create all BDU Milestone 3 issues
# Make sure you have gh CLI installed and authenticated
# Run: chmod +x create_issues.sh && ./create_issues.sh

set -e

echo "Creating BDU Milestone 3 issues..."
echo "Make sure you have access to the Ikey168/BDU repository"
echo ""

echo "Creating issue 1/10..."
gh issue create \
  --repo Ikey168/BDU \
  --title "Define D1 schema & write migrations" \
  --body "## Description\n\n- [ ] Create Wrangler migration files for `users`, `events`, and `registrations` tables (per schema in README)\n- [ ] Verify migrations run successfully against a fresh D1 instance\n\n## Acceptance Criteria\n\n- [ ] Migration files are created in the correct format\n- [ ] All table schemas match the specifications in README\n- [ ] Migrations execute without errors on fresh D1 instance\n- [ ] Rollback migrations work correctly" \
  --label "infra,cloudflare-workers,d1" \
  --milestone "3" 
echo "Issue 1 created successfully"
echo ""

echo "Creating issue 2/10..."
gh issue create \
  --repo Ikey168/BDU \
  --title "Implement `GET /api/users` & `POST /api/users`" \
  --body "## Description\n\n- [ ] Worker endpoint to list users and to register new users\n- [ ] Enforce unique email/username constraints\n\n## Acceptance Criteria\n\n- [ ] GET /api/users returns list of all users\n- [ ] POST /api/users creates new user with validation\n- [ ] Unique email constraint is enforced\n- [ ] Unique username constraint is enforced\n- [ ] Proper error handling for constraint violations" \
  --label "backend,api,cloudflare-workers" \
  --milestone "3" 
echo "Issue 2 created successfully"
echo ""

echo "Creating issue 3/10..."
gh issue create \
  --repo Ikey168/BDU \
  --title "Implement `GET /api/events` & `POST /api/events`" \
  --body "## Description\n\n- [ ] Worker endpoint to list all events (with optional `type` filter) and to create new events\n- [ ] Validate `start_time < end_time`\n\n## Acceptance Criteria\n\n- [ ] GET /api/events returns list of all events\n- [ ] GET /api/events supports optional type filter parameter\n- [ ] POST /api/events creates new event with validation\n- [ ] start_time < end_time validation is enforced\n- [ ] Proper error responses for validation failures" \
  --label "backend,api,cloudflare-workers" \
  --milestone "3" 
echo "Issue 3 created successfully"
echo ""

echo "Creating issue 4/10..."
gh issue create \
  --repo Ikey168/BDU \
  --title "Implement `POST /api/registrations` & `GET /api/registrations`" \
  --body "## Description\n\n- [ ] Endpoint for users to register for an event; enforce one registration per user/event\n- [ ] Admin endpoint to list registrations by event\n\n## Acceptance Criteria\n\n- [ ] POST /api/registrations allows users to register for events\n- [ ] One registration per user/event constraint is enforced\n- [ ] GET /api/registrations lists registrations by event (admin only)\n- [ ] Proper error handling for duplicate registrations\n- [ ] Admin-only access control for listing endpoint" \
  --label "backend,api,cloudflare-workers" \
  --milestone "3" 
echo "Issue 4 created successfully"
echo ""

echo "Creating issue 5/10..."
gh issue create \
  --repo Ikey168/BDU \
  --title "Add authentication via Pages Members" \
  --body "## Description\n\n- [ ] Protect write endpoints (`POST /*`), only callable by authenticated members\n- [ ] Expose current user info at `GET /api/auth/session`\n\n## Acceptance Criteria\n\n- [ ] All POST endpoints require authentication\n- [ ] Authentication is implemented via Pages Members\n- [ ] GET /api/auth/session returns current user information\n- [ ] Unauthenticated requests to protected endpoints return 401\n- [ ] Authentication middleware is reusable across endpoints" \
  --label "backend,auth,cloudflare-workers" \
  --milestone "3" 
echo "Issue 5 created successfully"
echo ""

echo "Creating issue 6/10..."
gh issue create \
  --repo Ikey168/BDU \
  --title "Input validation middleware" \
  --body "## Description\n\n- [ ] Create a reusable Hono/Vite middleware for request body validation (e.g. using Zod)\n- [ ] Apply to all write endpoints\n\n## Acceptance Criteria\n\n- [ ] Reusable validation middleware is created\n- [ ] Middleware uses Zod for schema validation\n- [ ] All write endpoints use the validation middleware\n- [ ] Validation errors return consistent error format\n- [ ] Middleware is well-documented and easy to use" \
  --label "backend,validation,cloudflare-workers" \
  --milestone "3" 
echo "Issue 6 created successfully"
echo ""

echo "Creating issue 7/10..."
gh issue create \
  --repo Ikey168/BDU \
  --title "Error-handling & logging" \
  --body "## Description\n\n- [ ] Standardize error responses (status codes + JSON `{error: message}`)\n- [ ] Integrate Cloudflare Workers' logging (e.g. `console.error`, Workers KV) for failed requests\n\n## Acceptance Criteria\n\n- [ ] All endpoints return standardized error format\n- [ ] Consistent HTTP status codes are used\n- [ ] Failed requests are logged appropriately\n- [ ] Cloudflare Workers logging is integrated\n- [ ] Error handling middleware is implemented" \
  --label "backend,observability,cloudflare-workers" \
  --milestone "3" 
echo "Issue 7 created successfully"
echo ""

echo "Creating issue 8/10..."
gh issue create \
  --repo Ikey168/BDU \
  --title "Unit tests for each endpoint" \
  --body "## Description\n\n- [ ] Write Jest or Vitest tests for success and failure cases of each API route\n- [ ] Mock D1 bindings via `wrangler dev` or Miniflare\n\n## Acceptance Criteria\n\n- [ ] Unit tests cover all API endpoints\n- [ ] Both success and failure cases are tested\n- [ ] D1 bindings are properly mocked\n- [ ] Tests use Jest or Vitest framework\n- [ ] Test coverage is comprehensive\n- [ ] Tests can be run in CI environment" \
  --label "test,unit-tests,cloudflare-workers" \
  --milestone "3" 
echo "Issue 8 created successfully"
echo ""

echo "Creating issue 9/10..."
gh issue create \
  --repo Ikey168/BDU \
  --title "Integration tests with real D1" \
  --body "## Description\n\n- [ ] CI job that runs against a preview D1 instance to verify migrations and CRUD end-to-end\n- [ ] Clean up test data after each run\n\n## Acceptance Criteria\n\n- [ ] Integration tests run against real D1 instance\n- [ ] Tests verify migrations work correctly\n- [ ] End-to-end CRUD operations are tested\n- [ ] Test data is cleaned up after each run\n- [ ] CI job is properly configured\n- [ ] Tests use preview D1 environment" \
  --label "test,integration-tests,ci" \
  --milestone "3" 
echo "Issue 9 created successfully"
echo ""

echo "Creating issue 10/10..."
gh issue create \
  --repo Ikey168/BDU \
  --title "Update API documentation" \
  --body "## Description\n\n- [ ] Document all routes, request/response schemas, example cURL calls in `/docs/api.md`\n- [ ] Ensure README links to this file\n\n## Acceptance Criteria\n\n- [ ] All API routes are documented in /docs/api.md\n- [ ] Request/response schemas are clearly defined\n- [ ] Example cURL calls are provided for each endpoint\n- [ ] README.md links to the API documentation\n- [ ] Documentation is kept up-to-date with implementation" \
  --label "documentation,api" \
  --milestone "3" 
echo "Issue 10 created successfully"
echo ""

echo "All issues created successfully!"
echo "Check https://github.com/Ikey168/BDU/issues to verify"

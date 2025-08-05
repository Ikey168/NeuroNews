# BDU Milestone 3 Issue Creator

This directory contains tools to create all the GitHub issues for **BDU Milestone 3** in the `Ikey168/BDU` repository.

## 📋 Issues Overview

The script creates **10 issues** for milestone 3, covering:

1. **Define D1 schema & write migrations** - Database setup and migrations
2. **Implement `GET /api/users` & `POST /api/users`** - User management endpoints
3. **Implement `GET /api/events` & `POST /api/events`** - Event management endpoints  
4. **Implement `POST /api/registrations` & `GET /api/registrations`** - Registration endpoints
5. **Add authentication via Pages Members** - Authentication implementation
6. **Input validation middleware** - Request validation using Zod
7. **Error-handling & logging** - Standardized error responses and logging
8. **Unit tests for each endpoint** - Comprehensive unit testing
9. **Integration tests with real D1** - End-to-end testing with real database
10. **Update API documentation** - Complete API documentation

Each issue includes:
- ✅ Checkboxes for each task (as requested)
- 🏷️ Appropriate labels (`infra`, `cloudflare-workers`, `d1`, `backend`, `api`, `auth`, `validation`, `observability`, `test`, `unit-tests`, `integration-tests`, `ci`, `documentation`)
- 📝 Detailed acceptance criteria
- 🎯 Milestone 3 assignment

## 🚀 Quick Start

### Option 1: Run the Shell Script (Recommended)

```bash
# Make the script executable
chmod +x create_issues.sh

# Run the script (requires gh CLI authentication)
./create_issues.sh
```

### Option 2: Use the Python Script

```bash
# Generate files
python3 scripts/create_bdu_milestone3_issues.py

# Or generate specific outputs:
python3 scripts/create_bdu_milestone3_issues.py --script   # Generate shell script
python3 scripts/create_bdu_milestone3_issues.py --json    # Generate JSON export
python3 scripts/create_bdu_milestone3_issues.py --manual  # Show manual commands
```

### Option 3: Manual Creation

Use the commands shown in the script output or copy them from the generated files.

## 📋 Prerequisites

1. **GitHub CLI**: Install and authenticate with `gh auth login`
2. **Repository Access**: Ensure you have access to `Ikey168/BDU`
3. **Milestone 3**: Make sure milestone "3" exists in the BDU repository

### Installing GitHub CLI

```bash
# On Ubuntu/Debian
sudo apt update && sudo apt install gh

# On macOS
brew install gh

# On Windows
winget install --id GitHub.cli
```

### Authenticate GitHub CLI

```bash
gh auth login
# Follow the prompts to authenticate
```

## 📁 Generated Files

- `create_issues.sh` - Executable shell script to create all issues
- `bdu_milestone3_issues.json` - JSON export of all issue data
- `scripts/create_bdu_milestone3_issues.py` - Python script generator

## 🔧 Customization

To modify the issues, edit the `MILESTONE_3_ISSUES` list in `scripts/create_bdu_milestone3_issues.py`:

```python
MILESTONE_3_ISSUES = [
    {
        "title": "Your Issue Title",
        "body": """## Description
        
- [ ] Your task with checkbox
- [ ] Another task

## Acceptance Criteria

- [ ] Criteria 1
- [ ] Criteria 2""",
        "labels": ["label1", "label2"],
        "milestone": "3"
    }
]
```

Then regenerate the files:

```bash
python3 scripts/create_bdu_milestone3_issues.py
```

## 🎯 Labels Used

- `infra` - Infrastructure and setup tasks
- `cloudflare-workers` - Cloudflare Workers specific work
- `d1` - D1 database related tasks  
- `backend` - Backend API development
- `api` - API endpoint implementation
- `auth` - Authentication and authorization
- `validation` - Input validation and middleware
- `observability` - Logging and error handling
- `test` - Testing related tasks
- `unit-tests` - Unit testing specifically
- `integration-tests` - Integration testing
- `ci` - Continuous integration
- `documentation` - Documentation updates

## ✅ Verification

After running the script, verify the issues were created:

1. Visit https://github.com/Ikey168/BDU/issues
2. Filter by milestone "3" 
3. Check that all 10 issues are present with correct labels

## 🐛 Troubleshooting

**Authentication Error**: Run `gh auth status` to check authentication
**Repository Access**: Ensure you have access to `Ikey168/BDU`
**Milestone Missing**: Create milestone "3" in the repository first
**Existing Issues**: The script will create duplicate issues if run multiple times

## 📝 Notes

- Each issue includes checkboxes (- [ ]) for task tracking as requested
- All labels specified in the problem statement are included
- Issues are automatically assigned to milestone "3"
- The script handles proper escaping for GitHub CLI commands
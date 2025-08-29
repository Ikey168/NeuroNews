#!/usr/bin/env python3
"""
GitHub Issue Creator for API Coverage Sub-Issues
Creates GitHub issues for each low-coverage module identified.
"""
import json
import subprocess
import sys
from typing import Dict, List, Tuple

# Coverage data from our analysis
COVERAGE_DATA = {
    "src/api/handler.py": {"current": 33, "target": 80, "priority": "CRITICAL", "lines": "3-5"},
    "src/api/graph/optimized_api.py": {"current": 3, "target": 60, "priority": "CRITICAL", "lines": "19-846"},
    "src/api/middleware/rate_limit_middleware.py": {"current": 4, "target": 60, "priority": "CRITICAL", "lines": "19-639"},
    "src/api/aws_rate_limiting.py": {"current": 19, "target": 70, "priority": "HIGH", "lines": "72-87, 91-129, 133-178, 184-208, 212-227, 233-268, 274-308, 312-331, 338-345, 351-384, 388-417, 423, 428, 433-450"},
    "src/api/security/waf_middleware.py": {"current": 18, "target": 65, "priority": "HIGH", "lines": "38-70, 84-135, 139-142, 147-157, 165-223, 227-259, 267-292, 296-327, 331-368, 373-402, 414-432, 436-450, 456-469, 473-490, 494-505, 524-552, 556-562"},
    "src/api/error_handlers.py": {"current": 43, "target": 75, "priority": "MEDIUM", "lines": "35-50, 60-89, 104-127, 141-162, 175-200, 214-225, 238-247, 255-264, 277-286, 295-308, 334-337, 342, 350, 355, 360, 368-371, 378, 385, 392"},
    "src/api/routes/graph_search_routes.py": {"current": 20, "target": 60, "priority": "MEDIUM", "lines": "32-56, 63-69, 115-159, 213-250, 285-329, 373-399, 410-422, 433-470"},
    "src/api/routes/influence_routes.py": {"current": 22, "target": 60, "priority": "MEDIUM", "lines": "27-40, 47, 77-106, 129-149, 172-192, 216-244, 265-319, 332-377, 388"},
    "src/api/routes/news_routes.py": {"current": 19, "target": 60, "priority": "MEDIUM", "lines": "18-35, 62-96, 117-172, 185-222"},
    "src/api/routes/knowledge_graph_routes.py": {"current": 20, "target": 60, "priority": "MEDIUM", "lines": "39, 79-140, 166-212, 234-288, 308-342, 355-382, 405-445"},
    "src/api/routes/quicksight_routes_broken.py": {"current": 0, "target": 50, "priority": "LOW", "lines": "16-459"},
    "src/api/routes/veracity_routes_fixed.py": {"current": 0, "target": 50, "priority": "LOW", "lines": "7-328"},
    "src/api/routes/enhanced_graph_routes.py": {"current": 4, "target": 50, "priority": "LOW", "lines": "21-667"},
}

FOCUS_AREAS = {
    "src/api/handler.py": [
        "Lambda event processing for different HTTP methods",
        "Context handling and timeout scenarios", 
        "Error handling for malformed events",
        "Response formatting and status codes",
        "Integration with FastAPI app"
    ],
    "src/api/graph/optimized_api.py": [
        "Neo4j connection handling",
        "Graph query optimization",
        "Caching mechanisms", 
        "Error handling for database operations",
        "Query result processing"
    ],
    "src/api/middleware/rate_limit_middleware.py": [
        "Rate limit enforcement logic",
        "IP tracking and identification",
        "Redis/memory caching integration",
        "Middleware chain processing",
        "Rate limit exceeded handling"
    ],
    "src/api/aws_rate_limiting.py": [
        "DynamoDB operations (get_item, put_item, update_item)",
        "Rate limit calculations and time windows",
        "AWS error handling and retries",
        "Configuration management",
        "Cleanup operations"
    ],
    "src/api/security/waf_middleware.py": [
        "Request filtering and threat detection",
        "Geofencing and IP validation", 
        "Security event logging",
        "Middleware chain integration",
        "Bot detection and blocking"
    ],
    "src/api/error_handlers.py": [
        "HTTP exception handling",
        "Validation error formatting",
        "Custom error responses",
        "Error logging integration"
    ],
    "src/api/routes/graph_search_routes.py": [
        "Entity search endpoints",
        "Relationship traversal APIs",
        "Graph query parameter validation",
        "Search result formatting",
        "Error handling for invalid queries"
    ],
    "src/api/routes/influence_routes.py": [
        "Influence scoring algorithms",
        "Network analysis endpoints",
        "Propagation tracking",
        "Influence metrics calculation"
    ],
    "src/api/routes/news_routes.py": [
        "Article processing endpoints",
        "News categorization",
        "Sentiment analysis integration",
        "Article search and filtering"
    ],
    "src/api/routes/knowledge_graph_routes.py": [
        "Entity management CRUD",
        "Relationship operations",
        "Graph query endpoints",
        "Knowledge graph updates"
    ],
    "src/api/routes/quicksight_routes_broken.py": [
        "Fix broken imports",
        "QuickSight dashboard integration",
        "Data visualization endpoints",
        "Embed URL generation"
    ],
    "src/api/routes/veracity_routes_fixed.py": [
        "Fact-checking endpoints",
        "Veracity scoring",
        "Source credibility analysis",
        "Bias detection"
    ],
    "src/api/routes/enhanced_graph_routes.py": [
        "Advanced graph operations",
        "Enhanced query capabilities", 
        "Graph analytics endpoints",
        "Performance optimization"
    ]
}

def create_issue_body(module_path: str, data: Dict) -> str:
    """Create GitHub issue body for a coverage module."""
    focus_areas = FOCUS_AREAS.get(module_path, ["General functionality testing"])
    focus_list = "\n".join(f"- {area}" for area in focus_areas)
    
    # Generate test file name
    module_name = module_path.split('/')[-1].replace('.py', '')
    test_file = f"test_{module_name}_coverage.py"
    
    body = f"""## 📊 Coverage Target

- **Module**: `{module_path}`
- **Current Coverage**: {data['current']}%
- **Target Coverage**: {data['target']}%
- **Priority**: {data['priority']}
- **Impact**: High (core functionality)

## 🔍 Missing Coverage Lines

```
{data['lines']}
```

## 🎯 Focus Areas

{focus_list}

## ✅ Acceptance Criteria

- [ ] Module coverage increased to {data['target']}%
- [ ] All critical paths tested
- [ ] Error scenarios covered
- [ ] Tests run without heavy dependencies
- [ ] Test execution time < 5 seconds
- [ ] No test failures or flaky tests

## 🛠️ Implementation Plan

### 1. Setup Test File
```bash
# Create test file
touch tests/api/routes/{test_file}

# Run baseline coverage
pytest tests/api/routes/{test_file} --cov={module_path} --cov-report=term-missing
```

### 2. Test Structure
```python
import pytest
from unittest.mock import Mock, patch

class Test{module_name.title().replace('_', '')}Coverage:
    def test_core_functionality(self):
        # Test implementation
        pass
    
    def test_error_handling(self):
        # Test implementation  
        pass
        
    def test_edge_cases(self):
        # Test implementation
        pass
```

### 3. Target Specific Lines
Focus on testing these specific line ranges:
```
{data['lines']}
```

## 📋 Testing Checklist

- [ ] Unit tests for core functionality
- [ ] Error handling tests
- [ ] Edge case scenarios
- [ ] Mock external dependencies
- [ ] Integration with existing test suite
- [ ] Performance validation

## 🚀 Definition of Done

- Coverage target achieved ({data['target']}%)
- All tests pass consistently
- Code review completed
- Documentation updated if needed
- Integrated with CI/CD pipeline

## 🔗 Related Issues

Part of the [API Coverage 80% Initiative](https://github.com/Ikey168/NeuroNews/issues) to improve overall API test coverage from 30% to 80%.
"""
    
    return body

def create_github_issue(module_path: str, data: Dict) -> bool:
    """Create a GitHub issue using gh CLI."""
    module_name = module_path.split('/')[-1].replace('.py', '')
    title = f"[COVERAGE] {module_path} - {data['current']}% → {data['target']}%"
    body = create_issue_body(module_path, data)
    
    # Create labels based on priority
    labels = ["coverage", "testing", "api"]
    if data['priority'] == "CRITICAL":
        labels.append("priority:critical")
    elif data['priority'] == "HIGH":
        labels.append("priority:high")
    elif data['priority'] == "MEDIUM":
        labels.append("priority:medium")
    else:
        labels.append("priority:low")
    
    # Add module type labels
    if "routes/" in module_path:
        labels.append("routes")
    elif "middleware/" in module_path:
        labels.append("middleware")
    elif "security/" in module_path:
        labels.append("security")
    elif "auth/" in module_path:
        labels.append("auth")
    
    try:
        # Use gh CLI to create issue
        cmd = [
            "gh", "issue", "create",
            "--title", title,
            "--body", body,
            "--label", ",".join(labels)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            issue_url = result.stdout.strip()
            print(f"✅ Created issue for {module_path}: {issue_url}")
            return True
        else:
            print(f"❌ Failed to create issue for {module_path}: {result.stderr}")
            return False
            
    except FileNotFoundError:
        print("❌ GitHub CLI (gh) not found. Please install it first.")
        return False
    except Exception as e:
        print(f"❌ Error creating issue for {module_path}: {e}")
        return False

def create_master_tracking_issue() -> bool:
    """Create a master tracking issue for the coverage initiative."""
    title = "[EPIC] API Coverage 80% Initiative - Test Coverage Improvement"
    
    # Create checklist of all sub-issues
    checklist_items = []
    for module_path, data in COVERAGE_DATA.items():
        module_name = module_path.split('/')[-1].replace('.py', '')
        item = f"- [ ] {module_path} ({data['current']}% → {data['target']}%)"
        checklist_items.append(item)
    
    checklist = "\n".join(checklist_items)
    
    body = f"""## 🎯 Objective

Improve API test coverage from current **30%** to **80%** through systematic testing of low-coverage modules.

## 📊 Current Status

- **Current Coverage**: 30%
- **Target Coverage**: 80%
- **Modules to Improve**: {len(COVERAGE_DATA)}
- **Test Infrastructure**: ✅ Established

## 📋 Module Coverage Checklist

{checklist}

## 🏗️ Implementation Phases

### Phase 1: Critical Infrastructure (Target: 40%)
- Handler, OptimizedAPI, RateLimitMiddleware
- **Timeline**: 3-4 days

### Phase 2: Security & Authentication (Target: 55%)
- AWS integration, auth middleware, security
- **Timeline**: 3-4 days

### Phase 3: Route Optimization (Target: 70%)
- Route-specific improvements
- **Timeline**: 4-5 days

### Phase 4: Zero Coverage Cleanup (Target: 80%)
- Fix broken modules, implement missing tests
- **Timeline**: 2-3 days

## 🛠️ Technical Standards

Each sub-issue must achieve:
- [ ] Module coverage increase of 20-40%
- [ ] All tests pass consistently
- [ ] No dependency on heavy ML imports
- [ ] Test execution time < 5 seconds per module
- [ ] Integration with existing test infrastructure

## 📈 Progress Tracking

```bash
# Track overall progress
PYTHONPATH=/workspaces/NeuroNews python -m pytest tests/api/ --cov=src/api --cov-report=term-missing --cov-report=html

# Track specific module
PYTHONPATH=/workspaces/NeuroNews python -m pytest tests/api/routes/test_{{module}}_coverage.py --cov=src/api/{{module_path}} --cov-report=term-missing
```

## 🎉 Success Criteria

- [ ] **80% API coverage achieved**
- [ ] All sub-issues completed
- [ ] Test suite runs reliably
- [ ] CI/CD integration maintained
- [ ] Documentation updated

## 🔗 Resources

- [Coverage Sub-Issues Breakdown](./COVERAGE_SUB_ISSUES.md)
- [GitHub Issues List](./GITHUB_COVERAGE_ISSUES.md)
- [Test Infrastructure Guide](./tests/api/README.md)

---

**Note**: This epic tracks the systematic improvement of API test coverage. Each module has its own dedicated issue for focused development.
"""
    
    try:
        cmd = [
            "gh", "issue", "create",
            "--title", title,
            "--body", body,
            "--label", "epic,coverage,testing,api,priority:high"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            issue_url = result.stdout.strip()
            print(f"✅ Created master tracking issue: {issue_url}")
            return True
        else:
            print(f"❌ Failed to create master tracking issue: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error creating master tracking issue: {e}")
        return False

def main():
    """Main function to create all GitHub issues."""
    print("🚀 Creating GitHub issues for API coverage improvement...")
    
    # Check if gh CLI is available
    try:
        result = subprocess.run(["gh", "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            print("❌ GitHub CLI not available. Please install 'gh' first.")
            sys.exit(1)
    except FileNotFoundError:
        print("❌ GitHub CLI not found. Please install 'gh' first.")
        sys.exit(1)
    
    success_count = 0
    
    # Create master tracking issue first
    if create_master_tracking_issue():
        success_count += 1
    
    # Create individual sub-issues
    for module_path, data in COVERAGE_DATA.items():
        if create_github_issue(module_path, data):
            success_count += 1
    
    total_issues = len(COVERAGE_DATA) + 1  # +1 for master issue
    print(f"\n📊 Summary:")
    print(f"✅ Successfully created: {success_count}/{total_issues} issues")
    print(f"❌ Failed: {total_issues - success_count} issues")
    
    if success_count == total_issues:
        print("\n🎉 All GitHub issues created successfully!")
        print("🔗 View issues: gh issue list --label coverage")
    else:
        print("\n⚠️  Some issues failed to create. Check the error messages above.")

if __name__ == "__main__":
    main()

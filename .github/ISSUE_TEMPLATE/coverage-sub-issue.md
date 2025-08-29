---
name: Coverage Issue Template
about: Template for API coverage improvement sub-issues
title: '[COVERAGE] {Module Name} - {Current}% → {Target}%'
labels: ['coverage', 'testing', 'api']
---

## 📊 Coverage Target

- **Module**: `{module_path}`
- **Current Coverage**: {current}%
- **Target Coverage**: {target}%
- **Priority**: {priority}
- **Impact**: {impact}

## 🔍 Missing Coverage Lines

```
{missing_lines}
```

## 🎯 Focus Areas

{focus_areas}

## ✅ Acceptance Criteria

- [ ] Module coverage increased to {target}%
- [ ] All critical paths tested
- [ ] Error scenarios covered
- [ ] Tests run without heavy dependencies
- [ ] Test execution time < 5 seconds
- [ ] No test failures or flaky tests

## 🛠️ Implementation Plan

### 1. Setup Test File
```bash
# Create test file
touch tests/api/{test_file_name}

# Run baseline coverage
pytest tests/api/{test_file_name} --cov=src/api/{module_path} --cov-report=term-missing
```

### 2. Test Structure
```python
import pytest
from unittest.mock import Mock, patch
# Add specific imports for the module

class Test{ModuleName}Coverage:
    def test_{focus_area_1}(self):
        # Test implementation
        pass
    
    def test_{focus_area_2}(self):
        # Test implementation  
        pass
```

### 3. Target Specific Lines
Focus on testing these specific line ranges:
{specific_line_targets}

## 🔗 Dependencies

{dependencies}

## 📋 Testing Checklist

- [ ] Unit tests for core functionality
- [ ] Error handling tests
- [ ] Edge case scenarios
- [ ] Mock external dependencies
- [ ] Integration with existing test suite
- [ ] Performance validation

## 🚀 Definition of Done

- Coverage target achieved ({target}%)
- All tests pass consistently
- Code review completed
- Documentation updated if needed
- Integrated with CI/CD pipeline

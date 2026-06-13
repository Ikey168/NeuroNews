#!/usr/bin/env python3
"""
GitHub Issue Creation Script for Phase-Based Coverage Implementation

This script creates GitHub issues for each phase of the API coverage 80% initiative.
Run this script to automatically create all phase-based sub-issues.

Usage:
    python scripts/create_phase_issues.py
    
Requirements:
    - GitHub CLI (gh) installed and authenticated
    - Repository access permissions
"""

import subprocess
import json
import time
from typing import Dict, List

# Phase-based issue data
PHASE_ISSUES = {
    # PHASE 1: CRITICAL INFRASTRUCTURE
    "phase-1.1": {
        "title": "[PHASE-1.1] Lambda Handler Core Functionality - 33% → 80%",
        "labels": ["phase-1", "critical", "aws-lambda", "coverage"],
        "milestone": "Phase 1: Critical Infrastructure",
        "body": """## 🎯 Objective
Improve Lambda handler test coverage from 33% to 80% by implementing comprehensive testing for AWS Lambda integration.

## 📊 Current Status
- **Current Coverage**: 33%
- **Target Coverage**: 80%
- **Missing Lines**: 3-5 (almost entire functionality)
- **File**: `src/api/handler.py`

## 🔍 Implementation Tasks
- [ ] HTTP method processing (GET, POST, PUT, DELETE, PATCH)
- [ ] Event validation and parsing
- [ ] Context handling and timeout scenarios
- [ ] Response formatting and status codes
- [ ] Error handling for malformed events
- [ ] Integration testing with FastAPI app

## 🧪 Test Implementation
```python
# tests/api/test_phase_1_1_handler.py
class TestPhase1HandlerCore:
    def test_http_method_processing(self):
        \"\"\"Test all HTTP methods through Lambda handler\"\"\"
        
    def test_event_validation(self):
        \"\"\"Test event structure validation\"\"\"
        
    def test_context_handling(self):
        \"\"\"Test AWS context processing\"\"\"
        
    def test_response_formatting(self):
        \"\"\"Test response structure compliance\"\"\"
        
    def test_error_scenarios(self):
        \"\"\"Test malformed events and timeouts\"\"\"
```

## ✅ Success Criteria
- [ ] Handler module reaches 80% coverage
- [ ] All HTTP methods properly tested
- [ ] Error scenarios comprehensively covered
- [ ] Integration with FastAPI validated
- [ ] CI/CD pipeline passes all tests

## 🔗 Related Issues
- Part of Phase 1: Critical Infrastructure
- Blocks: AWS deployment testing
- Dependencies: FastAPI app core functionality

## 📝 Notes
This is a critical foundation component for AWS Lambda deployment. Success here unblocks cloud deployment testing."""
    },
    
    "phase-1.2": {
        "title": "[PHASE-1.2] Optimized Graph API Foundation - 3% → 60%",
        "labels": ["phase-1", "critical", "neo4j", "graph-api", "coverage"],
        "milestone": "Phase 1: Critical Infrastructure",
        "body": """## 🎯 Objective
Improve OptimizedGraphAPI test coverage from 3% to 60% by implementing comprehensive graph database testing.

## 📊 Current Status
- **Current Coverage**: 3%
- **Target Coverage**: 60%
- **Missing Lines**: 19-846 (entire functionality)
- **File**: `src/api/optimized_api.py`

## 🔍 Implementation Tasks
- [ ] Neo4j connection establishment and management
- [ ] Basic graph query operations
- [ ] Query optimization mechanisms
- [ ] Caching layer implementation
- [ ] Error handling for database operations
- [ ] Connection pooling and cleanup

## 🧪 Test Implementation
```python
# tests/api/test_phase_1_2_optimized_api.py
@patch('neo4j.GraphDatabase')
class TestPhase1OptimizedApiCore:
    def test_connection_management(self, mock_neo4j):
        \"\"\"Test database connection handling\"\"\"
        
    def test_basic_queries(self, mock_neo4j):
        \"\"\"Test query execution and results\"\"\"
        
    def test_optimization_layer(self, mock_neo4j):
        \"\"\"Test query optimization mechanisms\"\"\"
        
    def test_caching_mechanism(self, mock_neo4j):
        \"\"\"Test caching layer functionality\"\"\"
```

## ✅ Success Criteria
- [ ] OptimizedGraphAPI reaches 60% coverage
- [ ] Database connection handling tested
- [ ] Query optimization paths covered
- [ ] Caching mechanisms validated
- [ ] Error handling comprehensive

## 🔗 Related Issues
- Part of Phase 1: Critical Infrastructure
- Blocks: Graph routes testing
- Dependencies: Neo4j mock setup

## 📝 Notes
Core graph functionality that enables all graph-based features. Essential for knowledge graph operations."""
    },
    
    "phase-1.3": {
        "title": "[PHASE-1.3] Rate Limiting Middleware Foundation - 4% → 60%",
        "labels": ["phase-1", "critical", "middleware", "rate-limiting", "security", "coverage"],
        "milestone": "Phase 1: Critical Infrastructure",
        "body": """## 🎯 Objective
Improve rate limiting middleware test coverage from 4% to 60% for API security foundation.

## 📊 Current Status
- **Current Coverage**: 4%
- **Target Coverage**: 60%
- **Missing Lines**: 19-639 (core security functionality)
- **File**: `src/api/middleware/rate_limit_middleware.py`

## 🔍 Implementation Tasks
- [ ] Request rate tracking and enforcement
- [ ] IP identification and client tracking
- [ ] Memory/Redis caching integration
- [ ] Middleware chain integration
- [ ] Rate limit exceeded handling
- [ ] Configuration and rule management

## 🧪 Test Implementation
```python
# tests/api/test_phase_1_3_rate_limit_middleware.py
class TestPhase1RateLimitCore:
    @pytest.mark.asyncio
    async def test_rate_enforcement(self):
        \"\"\"Test rate limit checking and enforcement\"\"\"
        
    @pytest.mark.asyncio
    async def test_client_tracking(self):
        \"\"\"Test IP/client identification\"\"\"
        
    @pytest.mark.asyncio
    async def test_middleware_integration(self):
        \"\"\"Test ASGI middleware chain integration\"\"\"
```

## ✅ Success Criteria
- [ ] Rate limiting middleware reaches 60% coverage
- [ ] Rate enforcement logic tested
- [ ] Client tracking mechanisms validated
- [ ] Middleware integration confirmed
- [ ] Security scenarios covered

## 🔗 Related Issues
- Part of Phase 1: Critical Infrastructure
- Blocks: Security middleware testing
- Dependencies: FastAPI middleware system

## 📝 Notes
Critical security component that protects API from abuse. Foundation for all security middleware."""
    },
    
    "phase-1.4": {
        "title": "[PHASE-1.4] FastAPI App Core Enhancement - 75% → 85%",
        "labels": ["phase-1", "critical", "fastapi", "app-core", "coverage"],
        "milestone": "Phase 1: Critical Infrastructure",
        "body": """## 🎯 Objective
Enhance FastAPI app core test coverage from 75% to 85% for complete application foundation.

## 📊 Current Status
- **Current Coverage**: 75%
- **Target Coverage**: 85%
- **Missing Lines**: App initialization edge cases
- **File**: `src/api/app.py`

## 🔍 Implementation Tasks
- [ ] App initialization edge cases
- [ ] Middleware mounting scenarios
- [ ] Route registration error handling
- [ ] Configuration validation
- [ ] Startup/shutdown event handling

## 🧪 Test Implementation
```python
# tests/api/test_phase_1_4_app_enhancement.py
class TestPhase1AppEnhancement:
    def test_initialization_edge_cases(self):
        \"\"\"Test app initialization scenarios\"\"\"
        
    def test_middleware_mounting(self):
        \"\"\"Test middleware integration\"\"\"
        
    def test_route_registration(self):
        \"\"\"Test route mounting and validation\"\"\"
```

## ✅ Success Criteria
- [ ] App module reaches 85% coverage
- [ ] All initialization paths tested
- [ ] Middleware integration validated
- [ ] Configuration handling complete

## 🔗 Related Issues
- Part of Phase 1: Critical Infrastructure
- Enables: All route testing
- Dependencies: Core FastAPI functionality

## 📝 Notes
Final piece of core infrastructure needed for all subsequent testing phases."""
    },
    
    # PHASE 2: SECURITY & AUTHENTICATION
    "phase-2.1": {
        "title": "[PHASE-2.1] AWS DynamoDB Rate Limiting - 19% → 70%",
        "labels": ["phase-2", "high-priority", "aws", "dynamodb", "rate-limiting", "coverage"],
        "milestone": "Phase 2: Security & Authentication",
        "body": """## 🎯 Objective
Implement comprehensive testing for AWS DynamoDB-backed rate limiting system.

## 📊 Current Status
- **Current Coverage**: 19%
- **Target Coverage**: 70%
- **File**: `src/api/aws_rate_limiting.py`

## 🔍 Implementation Tasks
- [ ] DynamoDB table operations (get_item, put_item, update_item)
- [ ] Rate calculation algorithms and time windows
- [ ] AWS error handling and retry logic
- [ ] Configuration management and validation
- [ ] Cleanup and maintenance operations
- [ ] Performance optimization and batching

## ✅ Success Criteria
- [ ] AWS rate limiting reaches 70% coverage
- [ ] All DynamoDB operations tested
- [ ] Error handling comprehensive
- [ ] Performance scenarios covered

## 🔗 Dependencies
- Requires: Phase 1 completion
- Blocks: Production deployment validation"""
    },
    
    "phase-2.2": {
        "title": "[PHASE-2.2] WAF Security Middleware - 18% → 65%",
        "labels": ["phase-2", "high-priority", "security", "waf", "middleware", "coverage"],
        "milestone": "Phase 2: Security & Authentication",
        "body": """## 🎯 Objective
Implement comprehensive testing for Web Application Firewall middleware.

## 📊 Current Status
- **Current Coverage**: 18%
- **Target Coverage**: 65%
- **File**: `src/api/middleware/waf_middleware.py`

## 🔍 Implementation Tasks
- [ ] Request filtering and threat detection
- [ ] Geofencing and IP validation
- [ ] Security event logging and alerting
- [ ] Bot detection and behavioral analysis
- [ ] Rule engine and pattern matching
- [ ] Performance optimization for high throughput

## ✅ Success Criteria
- [ ] WAF middleware reaches 65% coverage
- [ ] Threat detection mechanisms tested
- [ ] Security logging validated
- [ ] Performance under load confirmed

## 🔗 Dependencies
- Requires: Phase 1.3 (Rate Limiting Foundation)
- Blocks: Production security validation"""
    },
    
    "phase-2.3": {
        "title": "[PHASE-2.3] API Key Authentication Middleware - 27% → 70%",
        "labels": ["phase-2", "high-priority", "authentication", "api-keys", "middleware", "coverage"],
        "milestone": "Phase 2: Security & Authentication",
        "body": """## 🎯 Objective
Enhance API key authentication middleware testing for secure API access.

## 📊 Current Status
- **Current Coverage**: 27%
- **Target Coverage**: 70%
- **File**: `src/api/middleware/api_key_middleware.py`

## 🔍 Implementation Tasks
- [ ] API key validation and verification
- [ ] Key rotation and lifecycle management
- [ ] Rate limiting per API key
- [ ] Key revocation and blacklisting
- [ ] Audit logging and access tracking
- [ ] Integration with downstream services

## ✅ Success Criteria
- [ ] API key middleware reaches 70% coverage
- [ ] Key validation logic tested
- [ ] Security controls validated
- [ ] Audit trail complete

## 🔗 Dependencies
- Requires: Phase 1 completion
- Blocks: Production API security"""
    },
    
    "phase-2.4": {
        "title": "[PHASE-2.4] Role-Based Access Control - 24% → 70%",
        "labels": ["phase-2", "high-priority", "authorization", "rbac", "security", "coverage"],
        "milestone": "Phase 2: Security & Authentication",
        "body": """## 🎯 Objective
Implement comprehensive testing for Role-Based Access Control system.

## 📊 Current Status
- **Current Coverage**: 24%
- **Target Coverage**: 70%
- **File**: `src/api/middleware/rbac_middleware.py`

## 🔍 Implementation Tasks
- [ ] Role definition and hierarchy management
- [ ] Permission assignment and validation
- [ ] Access control decision logic
- [ ] Role inheritance and delegation
- [ ] Authorization audit logging
- [ ] Integration with authentication systems

## ✅ Success Criteria
- [ ] RBAC system reaches 70% coverage
- [ ] Authorization logic tested
- [ ] Role management validated
- [ ] Security audit complete

## 🔗 Dependencies
- Requires: Phase 2.3 (API Key Authentication)
- Blocks: Production authorization"""
    },
    
    # PHASE 3: ROUTE OPTIMIZATION
    "phase-3.1": {
        "title": "[PHASE-3.1] Graph Routes Comprehensive Testing - 20% → 60%",
        "labels": ["phase-3", "medium-priority", "graph-routes", "endpoints", "coverage"],
        "milestone": "Phase 3: Route Optimization",
        "body": """## 🎯 Objective
Implement comprehensive testing for all graph-related API routes.

## 📊 Current Status
- **Modules**: graph_search_routes.py (20%), graph_routes.py (18%), enhanced_graph_routes.py (4%)
- **Target Coverage**: 60% for all modules

## 🔍 Implementation Tasks
- [ ] Entity search and filtering endpoints
- [ ] Relationship traversal and querying
- [ ] Graph analytics and metrics endpoints
- [ ] Advanced graph operations (clustering, centrality)
- [ ] Graph export/import functionality
- [ ] Performance optimization endpoints

## ✅ Success Criteria
- [ ] All graph routes reach target coverage
- [ ] Entity operations fully tested
- [ ] Relationship handling validated
- [ ] Performance benchmarks met

## 🔗 Dependencies
- Requires: Phase 1.2 (Optimized Graph API)
- Blocks: Graph functionality validation"""
    },
    
    "phase-3.2": {
        "title": "[PHASE-3.2] Content Routes Comprehensive Testing - 19-22% → 60%",
        "labels": ["phase-3", "medium-priority", "content-routes", "news", "influence", "coverage"],
        "milestone": "Phase 3: Route Optimization",
        "body": """## 🎯 Objective
Implement comprehensive testing for content-related API routes.

## 📊 Current Status
- **Modules**: news_routes.py (19%), influence_routes.py (22%), knowledge_graph_routes.py (20%)
- **Target Coverage**: 60% for all modules

## 🔍 Implementation Tasks
- [ ] News article processing endpoints
- [ ] Article categorization and tagging
- [ ] Influence scoring and network analysis
- [ ] Knowledge graph entity management
- [ ] Content search and filtering
- [ ] Integration with AI/ML services

## ✅ Success Criteria
- [ ] All content routes reach target coverage
- [ ] Article processing tested
- [ ] Influence analysis validated
- [ ] ML integration confirmed

## 🔗 Dependencies
- Requires: Phase 1 completion
- Blocks: Content management validation"""
    },
    
    "phase-3.3": {
        "title": "[PHASE-3.3] Event Management Routes - 31-42% → 65%",
        "labels": ["phase-3", "medium-priority", "events", "timeline", "routes", "coverage"],
        "milestone": "Phase 3: Route Optimization",
        "body": """## 🎯 Objective
Enhance testing for event and timeline management routes.

## 📊 Current Status
- **Modules**: event_routes.py (42%), event_timeline_routes.py (31%)
- **Target Coverage**: 65% for both modules

## 🔍 Implementation Tasks
- [ ] Event creation and validation
- [ ] Timeline generation and sequencing
- [ ] Temporal query operations
- [ ] Event relationship mapping
- [ ] Timeline visualization data
- [ ] Event aggregation and analytics

## ✅ Success Criteria
- [ ] Event routes reach target coverage
- [ ] Timeline operations tested
- [ ] Temporal queries validated
- [ ] Analytics functionality confirmed

## 🔗 Dependencies
- Requires: Phase 1 completion
- Blocks: Event management validation"""
    },
    
    "phase-3.4": {
        "title": "[PHASE-3.4] Error Handler System Enhancement - 43% → 75%",
        "labels": ["phase-3", "medium-priority", "error-handling", "robustness", "coverage"],
        "milestone": "Phase 3: Route Optimization",
        "body": """## 🎯 Objective
Enhance error handling system testing for robust API error management.

## 📊 Current Status
- **Current Coverage**: 43%
- **Target Coverage**: 75%
- **File**: `src/api/error_handlers.py`

## 🔍 Implementation Tasks
- [ ] HTTP exception handling and formatting
- [ ] Validation error processing
- [ ] Custom error response generation
- [ ] Error logging and monitoring integration
- [ ] Error context preservation
- [ ] Client-friendly error messaging

## ✅ Success Criteria
- [ ] Error handlers reach 75% coverage
- [ ] All error types tested
- [ ] Error formatting validated
- [ ] Monitoring integration confirmed

## 🔗 Dependencies
- Requires: Phase 1 completion
- Blocks: Production error handling validation"""
    },
    
    # PHASE 4: CLEANUP & OPTIMIZATION
    "phase-4.1": {
        "title": "[PHASE-4.1] Zero Coverage Module Rehabilitation - 0% → 50%",
        "labels": ["phase-4", "low-priority", "cleanup", "zero-coverage", "coverage"],
        "milestone": "Phase 4: Cleanup & Optimization",
        "body": """## 🎯 Objective
Fix and test modules with zero coverage to ensure complete API functionality.

## 📊 Current Status
- **Modules**: quicksight_routes_broken.py, veracity_routes_fixed.py, quicksight_routes_temp.py
- **Current Coverage**: 0%
- **Target Coverage**: 50%

## 🔍 Implementation Tasks
- [ ] Fix import and dependency issues
- [ ] Implement basic QuickSight dashboard integration
- [ ] Develop veracity and fact-checking endpoints
- [ ] Create basic functionality tests
- [ ] Validate endpoint registration
- [ ] Integration with main application

## ✅ Success Criteria
- [ ] All zero coverage modules reach 50%
- [ ] Import issues resolved
- [ ] Basic functionality validated
- [ ] Integration confirmed

## 🔗 Dependencies
- Requires: Phase 3 completion
- Blocks: Complete API coverage"""
    },
    
    "phase-4.2": {
        "title": "[PHASE-4.2] Route Coverage Final Optimization - Various → Target+10%",
        "labels": ["phase-4", "low-priority", "optimization", "finalization", "coverage"],
        "milestone": "Phase 4: Cleanup & Optimization",
        "body": """## 🎯 Objective
Final optimization pass on all route modules to exceed targets and ensure robust coverage.

## 🔍 Implementation Tasks
- [ ] Identify remaining coverage gaps
- [ ] Implement edge case testing
- [ ] Enhance error scenario coverage
- [ ] Add integration test scenarios
- [ ] Performance and load testing coverage
- [ ] Documentation and example coverage

## ✅ Success Criteria
- [ ] All routes exceed target coverage
- [ ] Edge cases comprehensively tested
- [ ] Integration scenarios validated
- [ ] Performance requirements met

## 🔗 Dependencies
- Requires: Phase 3 completion
- Blocks: Final 80% validation"""
    },
    
    "phase-4.3": {
        "title": "[PHASE-4.3] Logging System Enhancement - 23% → 70%",
        "labels": ["phase-4", "low-priority", "logging", "configuration", "coverage"],
        "milestone": "Phase 4: Cleanup & Optimization",
        "body": """## 🎯 Objective
Comprehensive testing of logging and configuration systems for operational excellence.

## 📊 Current Status
- **Current Coverage**: 23%
- **Target Coverage**: 70%
- **File**: `src/api/logging_config.py`

## 🔍 Implementation Tasks
- [ ] Log level configuration and management
- [ ] File and console logging setup
- [ ] Performance logging and metrics
- [ ] Error logging integration
- [ ] Configuration validation and defaults
- [ ] Logging rotation and cleanup

## ✅ Success Criteria
- [ ] Logging config reaches 70% coverage
- [ ] All logging scenarios tested
- [ ] Configuration validation complete
- [ ] Performance monitoring confirmed

## 🔗 Dependencies
- Requires: Phase 3 completion
- Blocks: Operational readiness"""
    },
    
    "phase-4.4": {
        "title": "[PHASE-4.4] Final Integration Testing and 80% Validation",
        "labels": ["phase-4", "critical", "integration", "validation", "80-percent-target"],
        "milestone": "Phase 4: Cleanup & Optimization",
        "body": """## 🎯 Objective
**Final integration testing and validation to ensure 80% coverage target is achieved and maintained.**

## 🔍 Implementation Tasks
- [ ] Comprehensive integration test suite
- [ ] Coverage validation and reporting
- [ ] Performance benchmark validation
- [ ] CI/CD pipeline integration
- [ ] Documentation and example updates
- [ ] Final optimization and cleanup

## ✅ Success Criteria
- [ ] **80% total API coverage achieved** 🎯
- [ ] All integration tests pass
- [ ] Performance benchmarks met
- [ ] CI/CD integration complete
- [ ] Documentation updated

## 🔗 Dependencies
- Requires: All previous phases complete
- Deliverable: 80% API coverage milestone

## 📝 Notes
**This is the final validation issue for the 80% coverage initiative. Success here means project completion.**"""
    }
}

# Master tracking issue
MASTER_ISSUE = {
    "title": "[MASTER] API Coverage 80% Initiative - Phase-Based Implementation",
    "labels": ["epic", "coverage", "master-tracking", "80-percent-target"],
    "milestone": "API Coverage 80% Initiative",
    "body": """# 🎯 API Coverage 80% Initiative - Master Tracking Issue

## 📋 Overview
This is the master tracking issue for the systematic approach to achieving 80% API route test coverage through phase-based implementation.

## 🎯 **PRIMARY GOAL: 80% API COVERAGE**
- **Current Coverage**: 30%
- **Target Coverage**: 80%
- **Strategy**: 4-phase systematic implementation

---

## 📊 Phase Progress Tracking

### 🏗️ Phase 1: Critical Infrastructure (Target: 40% Coverage)
**Timeline**: 3-4 days | **Status**: Not Started

#### Critical Issues (4/4)
- [ ] #TBD - [PHASE-1.1] Lambda Handler Core Functionality - 33% → 80%
- [ ] #TBD - [PHASE-1.2] Optimized Graph API Foundation - 3% → 60%
- [ ] #TBD - [PHASE-1.3] Rate Limiting Middleware Foundation - 4% → 60%
- [ ] #TBD - [PHASE-1.4] FastAPI App Core Enhancement - 75% → 85%

**Phase 1 Success Criteria**: All critical infrastructure reaches target coverage, enabling all subsequent testing.

---

### 🔒 Phase 2: Security & Authentication (Target: 55% Coverage)
**Timeline**: 3-4 days | **Status**: Waiting for Phase 1

#### High Priority Issues (4/4)
- [ ] #TBD - [PHASE-2.1] AWS DynamoDB Rate Limiting - 19% → 70%
- [ ] #TBD - [PHASE-2.2] WAF Security Middleware - 18% → 65%
- [ ] #TBD - [PHASE-2.3] API Key Authentication Middleware - 27% → 70%
- [ ] #TBD - [PHASE-2.4] Role-Based Access Control - 24% → 70%

**Phase 2 Success Criteria**: Complete security layer testing for production readiness.

---

### 🛣️ Phase 3: Route Optimization (Target: 70% Coverage)
**Timeline**: 4-5 days | **Status**: Waiting for Phase 2

#### Medium Priority Issues (4/4)
- [ ] #TBD - [PHASE-3.1] Graph Routes Comprehensive Testing - 20% → 60%
- [ ] #TBD - [PHASE-3.2] Content Routes Comprehensive Testing - 19-22% → 60%
- [ ] #TBD - [PHASE-3.3] Event Management Routes - 31-42% → 65%
- [ ] #TBD - [PHASE-3.4] Error Handler System Enhancement - 43% → 75%

**Phase 3 Success Criteria**: All API endpoints reach comprehensive test coverage.

---

### 🧹 Phase 4: Cleanup & Optimization (Target: 80% Coverage)
**Timeline**: 2-3 days | **Status**: Waiting for Phase 3

#### Final Issues (4/4)
- [ ] #TBD - [PHASE-4.1] Zero Coverage Module Rehabilitation - 0% → 50%
- [ ] #TBD - [PHASE-4.2] Route Coverage Final Optimization - Various → Target+10%
- [ ] #TBD - [PHASE-4.3] Logging System Enhancement - 23% → 70%
- [ ] #TBD - [PHASE-4.4] Final Integration Testing and 80% Validation

**Phase 4 Success Criteria**: **🎯 80% TOTAL API COVERAGE ACHIEVED**

---

## 📈 Coverage Progress Chart

```
Current:  ████████████████████████████████                                    30%
Phase 1:  ████████████████████████████████████████████                        40%
Phase 2:  ███████████████████████████████████████████████████████             55%
Phase 3:  ██████████████████████████████████████████████████████████████████  70%
Phase 4:  ████████████████████████████████████████████████████████████████████ 80% 🎯
```

---

## 🚀 Quick Start Guide

### 1. Phase Execution Order
Execute phases sequentially to maintain dependencies:
```bash
# Phase 1: Critical Infrastructure
pytest tests/api/test_phase_1_*.py --cov=src/api

# Phase 2: Security & Authentication  
pytest tests/api/test_phase_2_*.py --cov=src/api

# Phase 3: Route Optimization
pytest tests/api/test_phase_3_*.py --cov=src/api

# Phase 4: Cleanup & Optimization
pytest tests/api/test_phase_4_*.py --cov=src/api
```

### 2. Coverage Validation
```bash
# Check overall progress
PYTHONPATH=/workspaces/NeuroNews python -m pytest tests/api/ --cov=src/api --cov-report=html --cov-report=term-missing
```

### 3. Phase Dependencies
- **Phase 2** requires Phase 1 completion (40% coverage)
- **Phase 3** requires Phase 2 completion (55% coverage)  
- **Phase 4** requires Phase 3 completion (70% coverage)

---

## 📝 Documentation References
- **Phase Details**: `PHASE_BASED_SUB_ISSUES.md`
- **GitHub Issues**: `GITHUB_PHASE_ISSUES.md`
- **Original Analysis**: `COVERAGE_SUB_ISSUES.md`
- **Implementation Guide**: `COVERAGE_INITIATIVE_README.md`

---

## 🎯 Success Metrics

### Phase Completion Criteria
- [ ] **Phase 1**: 40% coverage with critical infrastructure tested
- [ ] **Phase 2**: 55% coverage with security layers validated
- [ ] **Phase 3**: 70% coverage with all routes comprehensively tested
- [ ] **Phase 4**: **80% coverage achieved** 🎯

### Final Deliverables
- [ ] 80% API route test coverage
- [ ] Comprehensive test suite for all components
- [ ] CI/CD integration and validation
- [ ] Performance benchmarks met
- [ ] Production-ready security testing

---

## 👥 Contributors
- Implementation: Development Team
- Review: QA Team  
- Validation: DevOps Team

**Timeline**: 12-16 days total
**Priority**: HIGH - Critical for production readiness
**Status**: Ready to begin Phase 1

This master issue will be updated as phases complete and linked issues are resolved."""
}


def create_issue_body(issue_data: Dict) -> str:
    """Format issue body for GitHub CLI."""
    return issue_data["body"].replace('"""', '').strip()


def create_github_issue(issue_id: str, issue_data: Dict) -> bool:
    """Create a single GitHub issue using GitHub CLI."""
    try:
        # Format labels for gh CLI
        labels_str = ",".join(issue_data["labels"])
        
        # Create the issue
        cmd = [
            "gh", "issue", "create",
            "--title", issue_data["title"],
            "--body", create_issue_body(issue_data),
            "--label", labels_str
        ]
        
        # Add milestone if specified
        if "milestone" in issue_data:
            cmd.extend(["--milestone", issue_data["milestone"]])
        
        print(f"Creating issue: {issue_data['title']}")
        result = subprocess.run(cmd, capture_output=True, text=True, cwd="/workspaces/NeuroNews")
        
        if result.returncode == 0:
            issue_url = result.stdout.strip()
            print(f"✅ Created: {issue_url}")
            return True
        else:
            print(f"❌ Failed to create issue {issue_id}: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error creating issue {issue_id}: {str(e)}")
        return False


def create_master_tracking_issue() -> bool:
    """Create the master tracking issue."""
    return create_github_issue("master", MASTER_ISSUE)


def create_milestones() -> bool:
    """Create GitHub milestones for the phases."""
    milestones = [
        {
            "title": "Phase 1: Critical Infrastructure",
            "description": "Foundation infrastructure testing - Target: 40% coverage",
            "due_date": "2025-09-02"  # 4 days from now
        },
        {
            "title": "Phase 2: Security & Authentication", 
            "description": "Security layer comprehensive testing - Target: 55% coverage",
            "due_date": "2025-09-06"  # 8 days from now
        },
        {
            "title": "Phase 3: Route Optimization",
            "description": "API route comprehensive testing - Target: 70% coverage", 
            "due_date": "2025-09-11"  # 13 days from now
        },
        {
            "title": "Phase 4: Cleanup & Optimization",
            "description": "Final optimization and 80% validation - Target: 80% coverage",
            "due_date": "2025-09-14"  # 16 days from now
        },
        {
            "title": "API Coverage 80% Initiative",
            "description": "Master milestone for the entire 80% coverage initiative",
            "due_date": "2025-09-14"  # 16 days from now
        }
    ]
    
    success_count = 0
    for milestone in milestones:
        try:
            cmd = [
                "gh", "api", "repos/:owner/:repo/milestones",
                "--method", "POST",
                "--field", f"title={milestone['title']}",
                "--field", f"description={milestone['description']}",
                "--field", f"due_on={milestone['due_date']}T23:59:59Z"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, cwd="/workspaces/NeuroNews")
            
            if result.returncode == 0:
                print(f"✅ Created milestone: {milestone['title']}")
                success_count += 1
            else:
                print(f"⚠️  Milestone may already exist: {milestone['title']}")
                success_count += 1  # Count as success if it already exists
                
        except Exception as e:
            print(f"❌ Error creating milestone {milestone['title']}: {str(e)}")
    
    return success_count == len(milestones)


def main():
    """Main execution function."""
    print("🚀 Creating Phase-Based Coverage Issues for 80% Initiative")
    print("=" * 60)
    
    # Check if gh CLI is available
    try:
        result = subprocess.run(["gh", "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            print("❌ GitHub CLI (gh) not found. Please install and authenticate first.")
            return False
    except FileNotFoundError:
        print("❌ GitHub CLI (gh) not found. Please install and authenticate first.")
        return False
    
    # Create milestones first
    print("\n📋 Creating Milestones...")
    if create_milestones():
        print("✅ All milestones created successfully")
    else:
        print("⚠️  Some milestones may have failed - continuing with issues")
    
    # Small delay to ensure milestones are available
    time.sleep(2)
    
    # Create master tracking issue
    print("\n🎯 Creating Master Tracking Issue...")
    if create_master_tracking_issue():
        print("✅ Master tracking issue created")
    else:
        print("❌ Failed to create master tracking issue")
        return False
    
    # Create phase issues
    print(f"\n📝 Creating {len(PHASE_ISSUES)} Phase Issues...")
    success_count = 0
    failed_issues = []
    
    for issue_id, issue_data in PHASE_ISSUES.items():
        # Small delay between issues to avoid rate limiting
        time.sleep(1)
        
        if create_github_issue(issue_id, issue_data):
            success_count += 1
        else:
            failed_issues.append(issue_id)
    
    # Summary
    print("\n" + "=" * 60)
    print(f"📊 ISSUE CREATION SUMMARY")
    print(f"✅ Successfully created: {success_count}/{len(PHASE_ISSUES)} issues")
    
    if failed_issues:
        print(f"❌ Failed issues: {', '.join(failed_issues)}")
    
    if success_count == len(PHASE_ISSUES):
        print("\n🎉 All phase issues created successfully!")
        print("\n🚀 Next Steps:")
        print("1. Review created issues in GitHub")
        print("2. Begin Phase 1 implementation")
        print("3. Execute: pytest tests/api/test_phase_1_*.py --cov=src/api")
        print("4. Track progress through GitHub project board")
        print("\n🎯 Goal: 80% API Coverage Achievement!")
        return True
    else:
        print(f"\n⚠️  {len(failed_issues)} issues failed to create")
        print("Please check GitHub CLI authentication and permissions")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
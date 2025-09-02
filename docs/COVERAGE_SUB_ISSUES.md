# API Coverage Sub-Issues - Path to 80%

Based on current coverage analysis (26-30% achieved), here are the specific sub-issues for each file to reach 80% total coverage.

## 🎯 Current Status
- **Current Coverage**: 26-30%
- **Target Coverage**: 80%
- **Files Analyzed**: 40+ API modules
- **Test Infrastructure**: Established with 5 comprehensive test suites

---

## 🔴 CRITICAL PRIORITY (0-20% Coverage)

### Issue #1: `src/api/app.py` - 75% → 85%
**Current**: 75% | **Target**: 85% | **Impact**: High (main app module)
- **Missing Lines**: 14-15, 22-23, 30-31, 38-39, 46-47, 54-55, 62-63, 71-73, 86-87, 98-99, 110-111, 118-119, 126-127, 149, 179-180, 234, 255
- **Focus Areas**: 
  - App initialization edge cases
  - Error handling paths
  - Middleware integration points
  - Route mounting scenarios

### Issue #2: `src/api/handler.py` - 33% → 80%
**Current**: 33% | **Target**: 80% | **Impact**: High (Lambda handler)
- **Missing Lines**: 3-5 (most of the file)
- **Focus Areas**:
  - Lambda event processing
  - Different HTTP methods
  - Error scenarios
  - Context handling

### Issue #3: `src/api/graph/optimized_api.py` - 3% → 60%
**Current**: 3% | **Target**: 60% | **Impact**: High (graph operations)
- **Missing Lines**: 19-846 (almost entire file)
- **Focus Areas**:
  - Graph query optimization
  - Neo4j connection handling
  - Caching mechanisms
  - Error handling

### Issue #4: `src/api/middleware/rate_limit_middleware.py` - 4% → 60%
**Current**: 4% | **Target**: 60% | **Impact**: High (rate limiting)
- **Missing Lines**: 19-639 (almost entire file)
- **Focus Areas**:
  - Rate limit enforcement
  - IP tracking
  - Redis/memory caching
  - Middleware chain integration

### Issue #5: `src/api/routes/enhanced_kg_routes.py` - 23% → 70%
**Current**: 23% | **Target**: 70% | **Impact**: Medium (knowledge graph)
- **Missing Lines**: Multiple ranges covering graph operations
- **Focus Areas**:
  - Entity relationship queries
  - Graph traversal
  - Knowledge graph updates
  - Export/import functionality

---

## 🟡 HIGH PRIORITY (20-40% Coverage)

### Issue #6: `src/api/aws_rate_limiting.py` - 19% → 70%
**Current**: 19% | **Target**: 70% | **Impact**: High (AWS integration)
- **Missing Lines**: 72-87, 91-129, 133-178, 184-208, 212-227, 233-268, 274-308, 312-331, 338-345, 351-384, 388-417, 423, 428, 433-450
- **Focus Areas**:
  - DynamoDB operations
  - Rate limit calculations
  - AWS error handling
  - Configuration management

### Issue #7: `src/api/logging_config.py` - 23% → 70%
**Current**: 23% | **Target**: 70% | **Impact**: Medium (logging)
- **Missing Lines**: 25-38, 42-95, 106
- **Focus Areas**:
  - Log level configuration
  - File/console logging setup
  - Error handling in logging
  - Performance logging

### Issue #8: `src/api/auth/api_key_middleware.py` - 27% → 70%
**Current**: 27% | **Target**: 70% | **Impact**: High (authentication)
- **Missing Lines**: 30-40, 53-99, 103-106, 118-132, 144-171, 185-205, 209
- **Focus Areas**:
  - API key validation
  - Middleware chain processing
  - Authentication errors
  - Key rotation handling

### Issue #9: `src/api/rbac/rbac_middleware.py` - 24% → 70%
**Current**: 24% | **Target**: 70% | **Impact**: High (authorization)
- **Missing Lines**: 32-33, 54-140, 150-153, 159-168, 172-190, 194-204, 218-243, 247
- **Focus Areas**:
  - Role-based access control
  - Permission validation
  - Authorization errors
  - Role hierarchy

### Issue #10: `src/api/security/aws_waf_manager.py` - 32% → 70%
**Current**: 32% | **Target**: 70% | **Impact**: High (security)
- **Missing Lines**: 24-25, 110-116, 120-174, 178-336, 340-354, 358-390, 394-455, 459-497, 501-615, 619-665, 669-673, 677-706, 718, 730
- **Focus Areas**:
  - WAF rule management
  - IP blocking/allowing
  - Security event handling
  - AWS WAF integration

### Issue #11: `src/api/security/waf_middleware.py` - 18% → 65%
**Current**: 18% | **Target**: 65% | **Impact**: High (security middleware)
- **Missing Lines**: 38-70, 84-135, 139-142, 147-157, 165-223, 227-259, 267-292, 296-327, 331-368, 373-402, 414-432, 436-450, 456-469, 473-490, 494-505, 524-552, 556-562
- **Focus Areas**:
  - Request filtering
  - Threat detection
  - Geofencing
  - Security logging

---

## 🟢 MEDIUM PRIORITY (40-60% Coverage)

### Issue #12: `src/api/error_handlers.py` - 43% → 75%
**Current**: 43% | **Target**: 75% | **Impact**: High (error handling)
- **Missing Lines**: 35-50, 60-89, 104-127, 141-162, 175-200, 214-225, 238-247, 255-264, 277-286, 295-308, 334-337, 342, 350, 355, 360, 368-371, 378, 385, 392
- **Focus Areas**:
  - HTTP exception handling
  - Validation error formatting
  - Custom error responses
  - Error logging integration

### Issue #13: `src/api/routes/event_routes.py` - 42% → 75%
**Current**: 42% | **Target**: 75% | **Impact**: Medium (event management)
- **Missing Lines**: 119, 126, 165-207, 237-335, 360-422, 451-497, 510-550, 564-660, 668
- **Focus Areas**:
  - Event creation/updates
  - Event querying
  - Timeline generation
  - Event validation

### Issue #14: `src/api/rbac/rbac_system.py` - 47% → 75%
**Current**: 47% | **Target**: 75% | **Impact**: High (RBAC core)
- **Missing Lines**: 23-24, 82-85, 147-149, 153, 157, 180, 185, 190, 192-196, 200-223, 232-255, 259-272, 276-296, 300-312, 367-379, 383-395, 399-407, 411, 415-423, 427-439
- **Focus Areas**:
  - Role management
  - Permission assignment
  - Access control logic
  - User role validation

---

## 🔵 ROUTE-SPECIFIC ISSUES (Low Coverage Routes)

### Issue #15: Route Coverage Improvement - Graph Routes
**Files**: `graph_search_routes.py` (20%), `graph_routes.py` (18%)
- **Focus**: Graph query endpoints, entity search, relationship traversal
- **Target**: 60% each

### Issue #16: Route Coverage Improvement - Influence Routes
**Files**: `influence_routes.py` (22%)
- **Focus**: Influence scoring, network analysis, propagation tracking
- **Target**: 60%

### Issue #17: Route Coverage Improvement - News Routes  
**Files**: `news_routes.py` (19%)
- **Focus**: Article processing, categorization, sentiment analysis
- **Target**: 60%

### Issue #18: Route Coverage Improvement - Knowledge Graph Routes
**Files**: `knowledge_graph_routes.py` (20%)
- **Focus**: Entity management, relationship CRUD, graph queries
- **Target**: 60%

### Issue #19: Route Coverage Improvement - Timeline Routes
**Files**: `event_timeline_routes.py` (31%)
- **Focus**: Timeline creation, event sequencing, temporal queries
- **Target**: 65%

### Issue #20: Route Coverage Improvement - Summary Routes
**Files**: `summary_routes.py` (40%)
- **Focus**: Text summarization, article processing, AI integration
- **Target**: 70%

---

## 🔷 ZERO COVERAGE MODULES (Immediate Attention)

### Issue #21: Zero Coverage - QuickSight Routes
**Files**: `quicksight_routes_broken.py` (0%), `quicksight_routes_temp.py` (0%)
- **Action**: Fix broken imports, implement basic tests
- **Target**: 50%

### Issue #22: Zero Coverage - Rate Limit Routes
**Files**: `rate_limit_routes.py` (5%)
- **Action**: Create endpoint tests, validate rate limiting
- **Target**: 60%

### Issue #23: Zero Coverage - Veracity Routes Fixed
**Files**: `veracity_routes_fixed.py` (0%)
- **Action**: Implement fact-checking endpoint tests
- **Target**: 50%

### Issue #24: Zero Coverage - Enhanced Graph Routes
**Files**: `enhanced_graph_routes.py` (4%)
- **Action**: Test advanced graph operations
- **Target**: 50%

---

## 📋 IMPLEMENTATION STRATEGY

### Phase 1: Critical Infrastructure (Target: 40% total coverage)
- Issues #1-4: Core app, handler, optimized API, rate limiting
- **Timeline**: 3-4 days
- **Focus**: Basic functionality, error handling, integration points

### Phase 2: Security & Authentication (Target: 55% total coverage)  
- Issues #6-11: AWS integration, auth middleware, security
- **Timeline**: 3-4 days
- **Focus**: Security pathways, authentication flows, error scenarios

### Phase 3: Route Optimization (Target: 70% total coverage)
- Issues #15-20: Route-specific improvements
- **Timeline**: 4-5 days
- **Focus**: Endpoint testing, parameter validation, response handling

### Phase 4: Zero Coverage Cleanup (Target: 80% total coverage)
- Issues #21-24: Fix broken modules, implement missing tests
- **Timeline**: 2-3 days
- **Focus**: Module fixes, basic functionality testing

---

## 🛠️ TECHNICAL APPROACH

### For Each Sub-Issue:
1. **Create isolated test file** (`test_{module_name}_coverage.py`)
2. **Mock heavy dependencies** (ML models, external APIs)
3. **Target specific line ranges** from coverage report
4. **Focus on error paths** and edge cases
5. **Validate with coverage reporting**

### Test Patterns:
- **Unit Tests**: Direct module testing
- **Integration Tests**: Middleware chain testing  
- **Route Tests**: Endpoint validation
- **Error Tests**: Exception handling paths
- **Mock Tests**: External dependency simulation

### Success Metrics:
- Each sub-issue should improve module coverage by 20-40%
- Combined effort should reach 80% total API coverage
- All tests should run without heavy ML dependency imports
- Test execution time should remain under 10 seconds per module

---

## 📊 TRACKING PROGRESS

### Coverage Milestones:
- [x] **Baseline Established**: 26-30%
- [ ] **Phase 1 Complete**: 40%
- [ ] **Phase 2 Complete**: 55%  
- [ ] **Phase 3 Complete**: 70%
- [ ] **Phase 4 Complete**: 80% 🎯

### Issue Dependencies:
- Issues #1-4 should be completed first (core infrastructure)
- Issues #6-11 depend on #1-2 (security builds on core)
- Issues #15-20 can be done in parallel (independent routes)
- Issues #21-24 require module fixes before testing

This comprehensive breakdown provides a clear roadmap to achieve the 80% API coverage target through focused, manageable sub-issues.

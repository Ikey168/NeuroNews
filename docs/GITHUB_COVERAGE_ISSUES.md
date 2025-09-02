# GitHub Issues for API Coverage Improvement

## Issue #1: [COVERAGE] src/api/handler.py - 33% → 80%

**Priority**: CRITICAL
**Impact**: High (Lambda handler - core functionality)

### Description
The Lambda handler module has only 33% coverage but is critical for AWS deployment. Missing coverage on lines 3-5 represents almost the entire file.

### Focus Areas
- Lambda event processing for different HTTP methods
- Context handling and timeout scenarios  
- Error handling for malformed events
- Response formatting and status codes
- Integration with FastAPI app

### Implementation Plan
```python
# tests/api/test_handler_coverage.py
import pytest
from unittest.mock import Mock, patch
from src.api.handler import lambda_handler

class TestHandlerCoverage:
    def test_lambda_handler_get_requests(self):
        # Test GET request processing
        
    def test_lambda_handler_post_requests(self):
        # Test POST request processing
        
    def test_lambda_handler_error_scenarios(self):
        # Test malformed events, timeouts, etc.
        
    def test_lambda_handler_response_formatting(self):
        # Test response structure
```

---

## Issue #2: [COVERAGE] src/api/graph/optimized_api.py - 3% → 60%

**Priority**: CRITICAL  
**Impact**: High (Graph operations core)

### Description
OptimizedGraphAPI has only 3% coverage with lines 19-846 missing. This is a core module for graph operations.

### Focus Areas
- Neo4j connection handling
- Graph query optimization
- Caching mechanisms
- Error handling for database operations
- Query result processing

### Implementation Plan
```python
# tests/api/test_optimized_api_coverage.py
import pytest
from unittest.mock import Mock, patch
from src.api.graph.optimized_api import OptimizedGraphAPI

@patch('neo4j.GraphDatabase')
class TestOptimizedApiCoverage:
    def test_graph_connection(self, mock_neo4j):
        # Test database connection
        
    def test_query_optimization(self, mock_neo4j):
        # Test query optimization
        
    def test_caching_mechanism(self, mock_neo4j):
        # Test caching
```

---

## Issue #3: [COVERAGE] src/api/middleware/rate_limit_middleware.py - 4% → 60%

**Priority**: CRITICAL
**Impact**: High (Rate limiting security)

### Description
Rate limiting middleware has only 4% coverage with lines 19-639 missing. Critical for API security.

### Focus Areas
- Rate limit enforcement logic
- IP tracking and identification
- Redis/memory caching integration
- Middleware chain processing
- Rate limit exceeded handling

### Implementation Plan
```python
# tests/api/test_rate_limit_middleware_coverage.py
import pytest
from unittest.mock import Mock, patch, AsyncMock
from src.api.middleware.rate_limit_middleware import RateLimitMiddleware

class TestRateLimitMiddlewareCoverage:
    @pytest.mark.asyncio
    async def test_rate_limit_enforcement(self):
        # Test rate limit checking
        
    @pytest.mark.asyncio
    async def test_ip_tracking(self):
        # Test IP identification
        
    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self):
        # Test limit exceeded scenarios
```

---

## Issue #4: [COVERAGE] src/api/aws_rate_limiting.py - 19% → 70%

**Priority**: HIGH
**Impact**: High (AWS integration)

### Description
AWS rate limiting has 19% coverage with multiple missing ranges. Critical for AWS DynamoDB integration.

### Focus Areas
- DynamoDB operations (get_item, put_item, update_item)
- Rate limit calculations and time windows
- AWS error handling and retries
- Configuration management
- Cleanup operations

### Implementation Plan
```python
# tests/api/test_aws_rate_limiting_coverage.py
import pytest
from unittest.mock import Mock, patch
from src.api.aws_rate_limiting import RateLimiter

@patch('boto3.client')
class TestAwsRateLimitingCoverage:
    def test_dynamodb_operations(self, mock_boto):
        # Test DynamoDB interactions
        
    def test_rate_limit_calculations(self, mock_boto):
        # Test rate calculations
        
    def test_aws_error_handling(self, mock_boto):
        # Test AWS error scenarios
```

---

## Issue #5: [COVERAGE] src/api/security/waf_middleware.py - 18% → 65%

**Priority**: HIGH
**Impact**: High (Security middleware)

### Description
WAF middleware has 18% coverage with extensive missing ranges. Critical for request filtering and security.

### Focus Areas
- Request filtering and threat detection
- Geofencing and IP validation
- Security event logging
- Middleware chain integration
- Bot detection and blocking

### Implementation Plan
```python
# tests/api/test_waf_middleware_coverage.py
import pytest
from unittest.mock import Mock, patch, AsyncMock
from src.api.security.waf_middleware import WAFMiddleware

class TestWAFMiddlewareCoverage:
    @pytest.mark.asyncio
    async def test_request_filtering(self):
        # Test request filtering logic
        
    @pytest.mark.asyncio
    async def test_threat_detection(self):
        # Test threat detection
        
    @pytest.mark.asyncio
    async def test_geofencing(self):
        # Test geographic filtering
```

---

## Issue #6: [COVERAGE] src/api/routes/graph_search_routes.py - 20% → 60%

**Priority**: MEDIUM
**Impact**: Medium (Graph search endpoints)

### Description
Graph search routes have 20% coverage with missing lines 32-56, 63-69, 115-159, 213-250, 285-329, 373-399, 410-422, 433-470.

### Focus Areas
- Entity search endpoints
- Relationship traversal APIs
- Graph query parameter validation
- Search result formatting
- Error handling for invalid queries

### Implementation Plan
```python
# tests/api/test_graph_search_routes_coverage.py
import pytest
from fastapi.testclient import TestClient
from src.api.app import app

class TestGraphSearchRoutesCoverage:
    def test_entity_search_endpoints(self):
        # Test /api/graph/search/entities
        
    def test_relationship_traversal(self):
        # Test relationship endpoints
        
    def test_query_validation(self):
        # Test parameter validation
```

---

## Issue #7: [COVERAGE] Route Coverage Bundle - News, Influence, Knowledge Graph

**Priority**: MEDIUM
**Impact**: Medium (Route functionality)

### Description
Bundle issue for three related route modules:
- `news_routes.py` (19% → 60%)
- `influence_routes.py` (22% → 60%) 
- `knowledge_graph_routes.py` (20% → 60%)

### Focus Areas
- Endpoint parameter validation
- Response formatting
- Error handling
- Integration with business logic
- Authentication/authorization flows

### Implementation Plan
Create comprehensive route tests covering:
- All HTTP methods (GET, POST, PUT, DELETE)
- Parameter validation
- Error scenarios
- Response formatting
- Integration flows

---

## Issue #8: [COVERAGE] Zero Coverage Cleanup

**Priority**: LOW
**Impact**: Medium (Module functionality)

### Description
Fix modules with 0% coverage:
- `quicksight_routes_broken.py` (0% → 50%)
- `veracity_routes_fixed.py` (0% → 50%)
- `enhanced_graph_routes.py` (4% → 50%)

### Focus Areas
- Fix import issues
- Basic functionality testing
- Error handling
- Endpoint availability

### Implementation Plan
1. Identify and fix import/dependency issues
2. Create basic functionality tests
3. Ensure modules can be imported and tested
4. Validate endpoint registration

---

## 📋 Implementation Timeline

### Week 1: Critical Infrastructure
- Issues #1-3: Handler, OptimizedAPI, RateLimitMiddleware
- **Target**: 40% total coverage

### Week 2: AWS & Security  
- Issues #4-5: AWS RateLimiting, WAF Middleware
- **Target**: 55% total coverage

### Week 3: Route Optimization
- Issues #6-7: Route coverage improvements
- **Target**: 70% total coverage

### Week 4: Cleanup & Final Push
- Issue #8: Zero coverage cleanup
- **Target**: 80% total coverage 🎯

## 🎯 Success Metrics

Each issue should result in:
- Module coverage increase of 20-40%
- All tests pass consistently
- No dependency on heavy ML imports
- Test execution time < 5 seconds per module
- Integration with existing test infrastructure

## 📊 Progress Tracking

Use this command to track progress:
```bash
# Run coverage for specific module
PYTHONPATH=/workspaces/NeuroNews python -m pytest tests/api/test_{module}_coverage.py --cov=src/api/{module_path} --cov-report=term-missing

# Run full API coverage
PYTHONPATH=/workspaces/NeuroNews python -m pytest tests/api/ --cov=src/api --cov-report=term-missing --cov-report=html
```

**Current Status**: 26-30% → **Target**: 80%

## Issue #233 Implementation: Answering pipeline + citations (FastAPI /ask)

### Overview
Implements a complete REST endpoint for question answering with retrieval, synthesis, and citation extraction using the existing RAG infrastructure.

### Changes Made
- **services/api/main.py**: New main FastAPI application with /ask endpoint integration
- **GET /api/ask endpoint**: curl-friendly endpoint for DoD testing with query parameters
- **tests/test_issue_233_ask_endpoint.py**: Comprehensive test suite for DoD compliance  
- **Demo scripts**: Verification and demonstration scripts

### DoD Requirements ✅
- [x] **Request**: { query, k?, filters?, stream? }
  - ✅ question (query), k, filters parameters supported
  - ⚠️ stream not implemented (marked as optional in issue)
  
- [x] **Response**: { answer, citations:[{url,title,snippet}], retrieval:{latency_ms,k_used}, model }
  - ✅ answer with generated response
  - ✅ citations array with url, title, excerpt/snippet  
  - ✅ metadata with latency_ms, k_used, model info
  
- [x] **curl /ask?q=… returns answer with 3+ citations and latency stats**
  - ✅ GET endpoint supports curl testing
  - ✅ Returns 3+ citations with relevance scoring
  - ✅ Includes comprehensive latency statistics

### Technical Implementation
- **Leverages existing infrastructure**: Uses existing RAGAnswerService, citation extraction, and MLflow tracking
- **FastAPI integration**: Proper router inclusion with dependency injection
- **Multiple interfaces**: Both POST (JSON) and GET (query params) for flexibility
- **Comprehensive testing**: Unit tests verify all DoD requirements
- **Performance tracking**: Built-in latency monitoring and MLflow integration

### Files Modified/Created
```
services/api/main.py                     # Main FastAPI app with ask router
tests/test_issue_233_ask_endpoint.py     # DoD compliance tests  
demo_issue_233_ask_endpoint.py           # Demo and verification script
verify_issue_233.py                      # Quick verification script
```

### Testing
Run the test suite:
```bash
pytest tests/test_issue_233_ask_endpoint.py -v
```

Start the server for curl testing:
```bash
python services/api/main.py
curl 'http://localhost:8000/api/ask?q=What%20is%20artificial%20intelligence?&k=5'
```

### Next Steps
This implementation fulfills all DoD requirements for Issue #233. The endpoint is ready for production use and provides comprehensive question answering with citations and performance metrics.

Closes #233

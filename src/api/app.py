"""
Main FastAPI application configuration.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import event_routes, graph_routes, news_routes, veracity_routes, knowledge_graph_routes

# Try to import enhanced knowledge graph routes (Issue #37)
try:
    from src.api.routes import enhanced_kg_routes

    ENHANCED_KG_AVAILABLE = True
except ImportError:
    ENHANCED_KG_AVAILABLE = False

# Try to import event timeline routes (Issue #38)
try:
    from src.api.routes import event_timeline_routes

    EVENT_TIMELINE_AVAILABLE = True
except ImportError:
    EVENT_TIMELINE_AVAILABLE = False

# Try to import quicksight dashboard routes (Issue #49)
try:
    from src.api.routes import quicksight_routes

    QUICKSIGHT_AVAILABLE = True
except ImportError:
    QUICKSIGHT_AVAILABLE = False

# Try to import rate limiting components (Issue #59)
try:
    from src.api.middleware.rate_limit_middleware import (
        RateLimitConfig,
        RateLimitMiddleware,
    )
    from src.api.routes import auth_routes, rate_limit_routes

    RATE_LIMITING_AVAILABLE = True
except ImportError:
    RATE_LIMITING_AVAILABLE = False

# Try to import RBAC components (Issue #60)
try:
    from src.api.rbac.rbac_middleware import (
        EnhancedRBACMiddleware,
        RBACMetricsMiddleware,
    )
    from src.api.routes import rbac_routes

    RBAC_AVAILABLE = True
except ImportError:
    RBAC_AVAILABLE = False

# Try to import API key management components (Issue #61)
try:
    from src.api.auth.api_key_middleware import (
        APIKeyAuthMiddleware,
        APIKeyMetricsMiddleware,
    )
    from src.api.routes import api_key_routes

    API_KEY_MANAGEMENT_AVAILABLE = True
except ImportError:
    API_KEY_MANAGEMENT_AVAILABLE = False

# Try to import AWS WAF security components (Issue #65)
try:
    from src.api.routes import waf_security_routes
    from src.api.security.waf_middleware import (
        WAFMetricsMiddleware,
        WAFSecurityMiddleware,
    )

    WAF_SECURITY_AVAILABLE = True
except ImportError:
    WAF_SECURITY_AVAILABLE = False

app = FastAPI(
    title="NeuroNews API",
    description=(
        "API for accessing news articles and knowledge graph with RBAC, "
        "rate limiting, API key management, and AWS WAF security"
    ),
    version="0.1.0",
)

# Add WAF security middleware first for maximum protection (Issue #65)
if WAF_SECURITY_AVAILABLE:
    app.add_middleware(WAFSecurityMiddleware)
    app.add_middleware(WAFMetricsMiddleware)

# Add rate limiting middleware (Issue #59)
if RATE_LIMITING_AVAILABLE:
    app.add_middleware(RateLimitMiddleware, config=RateLimitConfig())

# Add API key authentication middleware (Issue #61)
if API_KEY_MANAGEMENT_AVAILABLE:
    app.add_middleware(APIKeyAuthMiddleware)
    app.add_middleware(APIKeyMetricsMiddleware)

# Add RBAC middleware (Issue #60)
if RBAC_AVAILABLE:
    app.add_middleware(EnhancedRBACMiddleware)
    app.add_middleware(RBACMetricsMiddleware)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(graph_routes.router)
app.include_router(knowledge_graph_routes.router)
app.include_router(news_routes.router)
app.include_router(event_routes.router)
app.include_router(veracity_routes.router)

# Include authentication routes (Issue #59)
if RATE_LIMITING_AVAILABLE:
    app.include_router(auth_routes.router)
    app.include_router(rate_limit_routes.router)

# Include RBAC routes (Issue #60)
if RBAC_AVAILABLE:
    app.include_router(rbac_routes.router)

# Include API key management routes (Issue #61)
if API_KEY_MANAGEMENT_AVAILABLE:
    app.include_router(api_key_routes.router)

# Include AWS WAF security routes (Issue #65)
if WAF_SECURITY_AVAILABLE:
    app.include_router(waf_security_routes.router)

# Include enhanced knowledge graph routes if available (Issue #37)
if ENHANCED_KG_AVAILABLE:
    app.include_router(enhanced_kg_routes.router)

# Include event timeline routes if available (Issue #38)
if EVENT_TIMELINE_AVAILABLE:
    app.include_router(event_timeline_routes.router)

# Include quicksight dashboard routes if available (Issue #49)
if QUICKSIGHT_AVAILABLE:
    app.include_router(quicksight_routes.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "status": "ok",
        "message": "NeuroNews API is running",
        "features": {
            "rate_limiting": RATE_LIMITING_AVAILABLE,
            "rbac": RBAC_AVAILABLE,
            "api_key_management": API_KEY_MANAGEMENT_AVAILABLE,
            "waf_security": WAF_SECURITY_AVAILABLE,
            "enhanced_kg": ENHANCED_KG_AVAILABLE,
            "event_timeline": EVENT_TIMELINE_AVAILABLE,
            "quicksight": QUICKSIGHT_AVAILABLE,
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "timestamp": "2025-08-17T22:00:00Z",
        "version": "0.1.0",
        "components": {
            "api": "operational",
            "rate_limiting": "operational" if RATE_LIMITING_AVAILABLE else "disabled",
            "rbac": "operational" if RBAC_AVAILABLE else "disabled",
            "api_key_management": (
                "operational" if API_KEY_MANAGEMENT_AVAILABLE else "disabled"
            ),
            "waf_security": "operational" if WAF_SECURITY_AVAILABLE else "disabled",
            "database": "unknown",  # Would check actual DB connection
            "cache": "unknown",  # Would check Redis connection
        },
    }

"""
Main FastAPI application configuration.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import graph_routes, news_routes, event_routes, veracity_routes

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
    from src.api.middleware.rate_limit_middleware import RateLimitMiddleware, RateLimitConfig
    from src.api.routes import rate_limit_routes
    from src.api.routes import auth_routes
    RATE_LIMITING_AVAILABLE = True
except ImportError:
    RATE_LIMITING_AVAILABLE = False

app = FastAPI(
    title="NeuroNews API",
    description="API for accessing news articles and knowledge graph with rate limiting",
    version="0.1.0"
)

# Add rate limiting middleware first (Issue #59)
if RATE_LIMITING_AVAILABLE:
    app.add_middleware(RateLimitMiddleware, config=RateLimitConfig())

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
app.include_router(news_routes.router)
app.include_router(event_routes.router)
app.include_router(veracity_routes.router)

# Include authentication routes (Issue #59)
if RATE_LIMITING_AVAILABLE:
    app.include_router(auth_routes.router)
    app.include_router(rate_limit_routes.router)

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
            "enhanced_kg": ENHANCED_KG_AVAILABLE,
            "event_timeline": EVENT_TIMELINE_AVAILABLE,
            "quicksight": QUICKSIGHT_AVAILABLE
        }
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
            "database": "unknown",  # Would check actual DB connection
            "cache": "unknown"      # Would check Redis connection
        }
    }
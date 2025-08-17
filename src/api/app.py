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

app = FastAPI(
    title="NeuroNews API",
    description="API for accessing news articles and knowledge graph",
    version="0.1.0"
)

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

# Include enhanced knowledge graph routes if available (Issue #37)
if ENHANCED_KG_AVAILABLE:
    app.include_router(enhanced_kg_routes.router)

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "status": "ok",
        "message": "NeuroNews API is running"
    }
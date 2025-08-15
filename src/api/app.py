"""
Main FastAPI application configuration.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import (
    graph_routes, 
    news_routes, 
    summary_routes,
    sentiment_routes,
    topic_routes,
    article_routes
)

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
app.include_router(summary_routes.router)
app.include_router(sentiment_routes.router)
app.include_router(topic_routes.router)
app.include_router(article_routes.router)

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "status": "ok",
        "message": "NeuroNews API is running"
    }
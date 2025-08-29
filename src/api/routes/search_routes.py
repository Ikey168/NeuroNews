"""Search API routes."""
from fastapi import APIRouter, Query, HTTPException
from typing import List, Dict, Any

router = APIRouter()


@router.get("/search")
async def search_news(q: str = Query(..., description="Search query")):
    """Search for news articles."""
    if not q or q.strip() == "":
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required and cannot be empty")
    
    # Mock search results
    return [
        {
            "id": 1,
            "title": f"Search result for: {q}",
            "content": f"This is a mock search result for query: {q}",
            "source": "Mock Source",
            "relevance": 0.95
        }
    ]

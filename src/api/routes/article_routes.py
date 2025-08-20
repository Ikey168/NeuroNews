"""
Article management routes with RBAC.
"""

import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from src.api.auth.jwt_auth import require_auth
from src.api.auth.permissions import Permission, require_permissions
from src.database.redshift_loader import RedshiftLoader

router = APIRouter(prefix="/articles", tags=["articles"])


# Database dependency
async def get_db() -> RedshiftLoader:
    """Return a RedshiftLoader using environment configuration or test defaults."""
    db = RedshiftLoader(
        host=os.getenv("REDSHIFT_HOST", "test-host"),
        database=os.getenv("REDSHIFT_DB", "dev"),
        user=os.getenv("REDSHIFT_USER", "admin"),
        password=os.getenv("REDSHIFT_PASSWORD", "test-pass"),
    )
    return db


# Request/Response Models
class ArticleBase(BaseModel):
    """Base article model."""

    title: str
    content: str
    category: Optional[str] = None
    source: Optional[str] = None


class ArticleCreate(ArticleBase):
    """Article creation request."""


class ArticleUpdate(ArticleBase):
    """Article update request."""


class Article(ArticleBase):
    """Article response model."""

    id: str
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime]
    sentiment_score: Optional[float]
    sentiment_label: Optional[str]

    class Config:
        from_attributes = True


@router.get("/", response_model=List[Article])
@require_permissions(Permission.READ_ARTICLES)
async def list_articles(
    request: Request,
    db: RedshiftLoader = Depends(get_db),
    category: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    _: dict = Depends(require_auth),  # For authentication
):
    """
    List articles with optional filters.

    Args:
        request: FastAPI request
        db: Database connection
        category: Optional category filter
        source: Optional source filter
        limit: Page size
        offset: Page offset
        _: Auth dependency

    Returns:
        List of articles
    """
    conditions = []
    params = []

    if category:
        conditions.append("category = %s")
        params.append(category)

    if source:
        conditions.append("source = %s")
        params.append(source)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    query = """
        SELECT id, title, content, category, source,
               created_by, created_at, updated_at,
               sentiment_score, sentiment_label
        FROM articles
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    return await db.execute_query(query, params)


@router.post("/", response_model=Article)
@require_permissions(Permission.CREATE_ARTICLES)
async def create_article(
    request: Request,
    article: ArticleCreate,
    db: RedshiftLoader = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Create a new article.

    Args:
        request: FastAPI request
        article: Article data
        db: Database connection
        user: Authenticated user

    Returns:
        Created article
    """
    query = """
        INSERT INTO articles (
            title, content, category, source,
            created_by, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
    """

    result = await db.execute_query(
        query,
        [
            article.title,
            article.content,
            article.category,
            article.source,
            user["sub"],
            datetime.now(timezone.utc),
        ],
    )

    return result[0]


@router.get("/{article_id}", response_model=Article)
@require_permissions(Permission.READ_ARTICLES)
async def get_article(
    request: Request,
    article_id: str,
    db: RedshiftLoader = Depends(get_db),
    _: dict = Depends(require_auth),
):
    """
    Get article by ID.

    Args:
        request: FastAPI request
        article_id: Article ID
        db: Database connection
        _: Auth dependency

    Returns:
        Article details
    """
    result = await db.execute_query(
        "SELECT * FROM articles WHERE id = %s", [article_id]
    )

    if not result:
        raise HTTPException(status_code=404, detail="Article not found")

    return result[0]


@router.put("/{article_id}", response_model=Article)
@require_permissions(Permission.UPDATE_ARTICLES)
async def update_article(
    request: Request,
    article_id: str,
    article: ArticleUpdate,
    db: RedshiftLoader = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Update article.

    Args:
        request: FastAPI request
        article_id: Article ID
        article: Updated article data
        db: Database connection
        user: Authenticated user

    Returns:
        Updated article
    """
    # Check if article exists and user has access
    existing = await db.execute_query(
        "SELECT created_by FROM articles WHERE id = %s", [article_id]
    )

    if not existing:
        raise HTTPException(status_code=404, detail="Article not found")

    # Only admins and original author can update
    if user["role"] != "admin" and existing[0]["created_by"] != user["sub"]:
        raise HTTPException(
            status_code=403, detail="Not authorized to update this article"
        )

    query = """
        UPDATE articles
        SET title = %s,
            content = %s,
            category = %s,
            source = %s,
            updated_at = %s
        WHERE id = %s
        RETURNING *
    """

    result = await db.execute_query(
        query,
        [
            article.title,
            article.content,
            article.category,
            article.source,
            datetime.now(timezone.utc),
            article_id,
        ],
    )

    return result[0]


@router.delete("/{article_id}")
@require_permissions(Permission.DELETE_ARTICLES)
async def delete_article(
    request: Request,
    article_id: str,
    db: RedshiftLoader = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Delete article.

    Args:
        request: FastAPI request
        article_id: Article ID
        db: Database connection
        user: Authenticated user
    """
    # Check if article exists and user has access
    existing = await db.execute_query(
        "SELECT created_by FROM articles WHERE id = %s", [article_id]
    )

    if not existing:
        raise HTTPException(status_code=404, detail="Article not found")

    # Only admins and original author can delete
    if user["role"] != "admin" and existing[0]["created_by"] != user["sub"]:
        raise HTTPException(
            status_code=403, detail="Not authorized to delete this article"
        )

    await db.execute_query("DELETE FROM articles WHERE id = %s", [article_id])

    return {"message": "Article deleted"}

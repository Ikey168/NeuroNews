"""
Authentication routes for the API.
"""

import os
from datetime import datetime, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr

from src.api.auth.jwt_auth import auth_handler, require_auth
from src.database.redshift_loader import RedshiftLoader


# Request/Response Models
class UserCreate(BaseModel):
    """User registration request."""

    email: EmailStr
    password: str
    first_name: str
    last_name: str
    role: str = "user"


class UserLogin(BaseModel):
    """User login request."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Token response model."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str


router = APIRouter(prefix="/auth", tags=["auth"])


# Database dependency for tests
async def get_db() -> RedshiftLoader:
    return RedshiftLoader(
        host=os.getenv("REDSHIFT_HOST", "test-host"),
        database=os.getenv("REDSHIFT_DB", "dev"),
        user=os.getenv("REDSHIFT_USER", "admin"),
        password=os.getenv("REDSHIFT_PASSWORD", "test-pass"),
    )


@router.post("/register", response_model=TokenResponse)
async def register(user: UserCreate, db: RedshiftLoader = Depends(get_db)):
    """
    Register a new user.

    Args:
        user: User registration details
        db: Database connection

    Returns:
        Access and refresh tokens for the new user

    Raises:
        HTTPException: If email already exists
    """
    # Check if user exists
    query = "SELECT id FROM users WHERE email = %s"
    result = await db.execute_query(query, [user.email])

    if result:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Hash password
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(user.password.encode(), salt)

    # Insert user
    query = """
        INSERT INTO users (email, password_hash, first_name, last_name, role, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    result = await db.execute_query(
        query,
        [
            user.email,
            hashed.decode(),
            user.first_name,
            user.last_name,
            user.role,
            datetime.now(timezone.utc),
        ],
    )

    user_id = result[0][0]

    # Generate tokens
    token_data = {"sub": str(user_id), "email": user.email, "role": user.role}

    return TokenResponse(
        access_token=auth_handler.create_access_token(token_data),
        refresh_token=auth_handler.create_refresh_token(token_data),
    )


@router.post("/login", response_model=TokenResponse)
async def login(user: UserLogin, db: RedshiftLoader = Depends(get_db)):
    """
    Authenticate a user and return tokens.

    Args:
        user: Login credentials
        db: Database connection

    Returns:
        Access and refresh tokens

    Raises:
        HTTPException: If login fails
    """
    # Get user
    query = """
        SELECT id, password_hash, role
        FROM users
        WHERE email = %s
    """
    result = await db.execute_query(query, [user.email])

    if not result:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user_id, password_hash, role = result[0]

    # Verify password
    if not bcrypt.checkpw(user.password.encode(), password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Generate tokens
    token_data = {"sub": str(user_id), "email": user.email, "role": role}

    return TokenResponse(
        access_token=auth_handler.create_access_token(token_data),
        refresh_token=auth_handler.create_refresh_token(token_data),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshRequest):
    """
    Refresh access token using refresh token.

    Args:
        request: Refresh token

    Returns:
        New access and refresh tokens

    Raises:
        HTTPException: If refresh token is invalid
    """
    tokens = auth_handler.refresh_tokens(request.refresh_token)
    return TokenResponse(**tokens)


@router.post("/logout")
async def logout(response: Response, _: dict = Depends(require_auth)):
    """
    Logout a user by clearing cookies.

    Args:
        response: FastAPI response object
        _: Auth dependency for validation
    """
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"message": "Successfully logged out"}


@router.get("/verify")
async def verify_token(_: dict = Depends(require_auth)):
    """
    Verify a token is valid.

    Args:
        _: Auth dependency for validation
    """
    return {"message": "Token is valid"}

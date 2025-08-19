"""
JWT-based authentication system for the NeuroNews API.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.security.utils import get_authorization_scheme_param


class JWTAuth:
    """Handle JWT token generation, validation, and refresh."""

    def __init__(self):
        """Initialize JWT authentication configuration."""
        # Use a default secret for test environments if env var not provided
        self.jwt_secret = os.getenv("JWT_SECRET_KEY", "test-secret")
        self.jwt_algorithm = "HS256"
        self.access_token_expire = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
        self.refresh_token_expire = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

        self.security = HTTPBearer(auto_error=False)

    def create_access_token(self, data: Dict[str, Any]) -> str:
        """
        Create a new access token.

        Args:
            data: Dictionary of claims to include in token

        Returns:
            Encoded JWT token string
        """
        to_encode = data.copy()
        if "sub" in to_encode:
            to_encode["sub"] = str(to_encode["sub"])
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=self.access_token_expire
        )
        to_encode.update({"exp": expire})

        return jwt.encode(to_encode, self.jwt_secret, algorithm=self.jwt_algorithm)

    def create_refresh_token(self, data: Dict[str, Any]) -> str:
        """
        Create a new refresh token.

        Args:
            data: Dictionary of claims to include in token

        Returns:
            Encoded JWT refresh token string
        """
        to_encode = data.copy()
        if "sub" in to_encode:
            to_encode["sub"] = str(to_encode["sub"])
        expire = datetime.now(timezone.utc) + timedelta(days=self.refresh_token_expire)
        to_encode.update({"exp": expire, "refresh": True})

        return jwt.encode(to_encode, self.jwt_secret, algorithm=self.jwt_algorithm)

    def decode_token(self, token: str) -> Dict[str, Any]:
        """
        Decode and validate a JWT token.

        Args:
            token: JWT token string to decode

        Returns:
            Dictionary of decoded token claims

        Raises:
            HTTPException: If token is invalid or expired
        """
        try:
            return jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")

    def refresh_tokens(self, refresh_token: str) -> Dict[str, str]:
        """
        Create new access and refresh tokens using a valid refresh token.

        Args:
            refresh_token: Current refresh token

        Returns:
            Dictionary containing new access and refresh tokens

        Raises:
            HTTPException: If refresh token is invalid or expired
        """
        payload = self.decode_token(refresh_token)

        if not payload.get("refresh"):
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        # Remove refresh flag and expiration
        del payload["refresh"]
        del payload["exp"]

        return {
            "access_token": self.create_access_token(payload),
            "refresh_token": self.create_refresh_token(payload),
        }

    async def __call__(self, request: Request) -> Dict[str, Any]:
        """
        Dependency for protecting routes with JWT authentication.

        Args:
            request: FastAPI request object

        Returns:
            Dictionary of validated token claims

        Raises:
            HTTPException: If no valid token is provided
        """
        credentials: HTTPAuthorizationCredentials = await self.security(request)

        if not credentials:
            raise HTTPException(
                status_code=401, detail="No authorization token provided"
            )

        if credentials.scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")

        payload = self.decode_token(credentials.credentials)

        # Don't accept refresh tokens for normal authentication
        if payload.get("refresh"):
            raise HTTPException(status_code=401, detail="Invalid token type")
        request.state.user = payload
        return payload


# Create global auth handler instance
auth_handler = JWTAuth()

# Alias used in route dependencies
require_auth = auth_handler

"""
API Key Authentication Middleware for NeuroNews API - Issue #61.

This middleware handles API key-based authentication alongside JWT tokens.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.auth.api_key_manager import APIKeyGenerator, APIKeyStatus, api_key_manager

logger = logging.getLogger(__name__)


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Middleware to handle API key authentication."""

    def __init__(self, app, excluded_paths: Optional[list] = None):
        """
        Initialize API key authentication middleware.

        Args:
            app: FastAPI application
            excluded_paths: Paths to exclude from API key auth
        """
        super().__init__(app)
        self.excluded_paths = excluded_paths or [
            "/",
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/auth/login",
            "/auth/register",
        ]
        self.security = HTTPBearer(auto_error=False)

    async def dispatch(self, request: Request, call_next):
        """
        Process request through API key authentication.

        Args:
            request: FastAPI request
            call_next: Next middleware/handler

        Returns:
            Response from next handler or authentication error
        """
        path = request.url.path

        # Skip authentication for excluded paths
        if self._is_excluded_path(path):
            return await call_next(request)

        # Try to extract API key from different sources
        api_key = self._extract_api_key(request)

        if api_key:
            # Validate API key
            key_details = await self._validate_api_key(api_key)

            if key_details:
                # Set user information in request state
                request.state.api_key_auth = True
                request.state.api_key_id = key_details.key_id
                request.state.user_id = key_details.user_id
                request.state.api_key_permissions = key_details.permissions or []
                request.state.api_key_rate_limit = key_details.rate_limit

                # Update usage tracking
                await api_key_manager.store.update_api_key_usage(key_details.key_id)

                logger.info(
                    f"API key authentication successful for user {key_details.user_id}"
                )

                response = await call_next(request)

                # Add API key headers to response
                response.headers["X-API-Key-Auth"] = "true"
                response.headers["X-API-Key-ID"] = key_details.key_id[:8]  # Only prefix

                return response
            else:
                # Invalid API key
                logger.warning(f"Invalid API key attempted from {request.client.host}")
                raise HTTPException(status_code=401, detail="Invalid API key")

        # No API key provided - continue to other auth methods
        return await call_next(request)

    def _is_excluded_path(self, path: str) -> bool:
        """Check if path should be excluded from API key auth."""
        for excluded in self.excluded_paths:
            if path.startswith(excluded):
                return True
        return False

    def _extract_api_key(self, request: Request) -> Optional[str]:
        """
        Extract API key from request.

        Supports multiple methods:
        1. Authorization header: "Bearer nn_..."
        2. X-API-Key header
        3. Query parameter: ?api_key=nn_...
        """
        # Method 1: Authorization header
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer nn_"):
            return auth_header.split(" ", 1)[1]

        # Method 2: X-API-Key header
        api_key_header = request.headers.get("x-api-key")
        if api_key_header and api_key_header.startswith("nn_"):
            return api_key_header

        # Method 3: Query parameter
        api_key_param = request.query_params.get("api_key")
        if api_key_param and api_key_param.startswith("nn_"):
            return api_key_param

        return None

    async def _validate_api_key(self, api_key: str) -> Optional[Any]:
        """
        Validate API key and return key details.

        Args:
            api_key: The API key to validate

        Returns:
            API key details if valid, None otherwise
        """
        try:
            # For this implementation, we need to find the key by searching
            # In a production system, this would be optimized with proper indexing

            # Extract prefix for identification
            if not api_key.startswith("nn_"):
                return None

            key_prefix = api_key[:8]

            # Since we don't have a prefix index in this demo, we'll implement
            # a simplified validation approach
            # In production, you'd have a separate table or index for efficient lookup

            # For now, let's create a mock implementation that works for demo
            # This is where you'd implement the efficient key lookup

            # We need to hash the provided key and compare with stored hashes
            # But we need the key_id first, which requires the prefix lookup

            # For demo purposes, let's return None and implement later
            # when we have proper test data

            return None

        except Exception as e:
            logger.error(f"Error validating API key: {e}")
            return None


class APIKeyMetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to track API key usage metrics."""

    def __init__(self, app):
        """Initialize metrics middleware."""
        super().__init__(app)
        self.api_key_usage = {}
        self.request_counts = {}

    async def dispatch(self, request: Request, call_next):
        """Track API key usage metrics."""
        response = await call_next(request)

        # Track API key usage if present
        if hasattr(request.state, "api_key_id"):
            key_id = request.state.api_key_id
            path = request.url.path
            method = request.method

            # Track usage
            endpoint = f"{method} {path}"
            if key_id not in self.api_key_usage:
                self.api_key_usage[key_id] = {}

            self.api_key_usage[key_id][endpoint] = (
                self.api_key_usage[key_id].get(endpoint, 0) + 1
            )

            # Track overall request counts
            self.request_counts[key_id] = self.request_counts.get(key_id, 0) + 1

        return response

    def get_metrics(self) -> Dict[str, Any]:
        """Get API key usage metrics."""
        return {
            "api_key_usage": self.api_key_usage,
            "request_counts": self.request_counts,
            "total_api_requests": sum(self.request_counts.values()),
            "active_api_keys": len(self.request_counts),
        }


# Global metrics instance
api_key_metrics = APIKeyMetricsMiddleware(None)

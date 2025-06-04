"""
Authentication and security middleware for the API.
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from src.api.auth.jwt_auth import auth_handler
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from typing import List, Dict, Optional
import os
import json
import logging

logger = logging.getLogger(__name__)

def configure_cors(app: FastAPI) -> None:
    """
    Configure CORS middleware.
    
    Args:
        app: FastAPI application instance
    """
    origins = os.getenv("ALLOWED_ORIGINS", "").split(",")
    if not origins or origins == [""]:
        origins = ["http://localhost:3000"]  # Default to local frontend
        
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"]
    )

class RoleBasedAccessMiddleware(BaseHTTPMiddleware):
    """Middleware for role-based access control."""
    
    def __init__(self, app: FastAPI, protected_routes: Dict[str, List[str]]):
        """
        Initialize RBAC middleware.
        
        Args:
            app: FastAPI application
            protected_routes: Dictionary mapping routes to required roles
        """
        super().__init__(app)
        self.protected_routes = protected_routes

    async def dispatch(self, request: Request, call_next):
        """
        Check role requirements for protected routes.
        
        Args:
            request: FastAPI request
            call_next: Next middleware/handler
            
        Returns:
            Response from next handler
            
        Raises:
            HTTPException: If user lacks required role
        """
        path = request.url.path
        method = request.method
        
        # Check if route is protected
        route_key = f"{method} {path}"
        required_roles = self.protected_routes.get(route_key)
        
        if required_roles:
            user = request.state.user if hasattr(request.state, "user") else None
            if not user or "role" not in user:
                try:
                    user = await auth_handler(request)
                except HTTPException:
                    return JSONResponse(status_code=401, content={"detail": "Authentication required"})
            if user["role"] not in required_roles:
                return JSONResponse(status_code=403, content={"detail": "Insufficient permissions"})
        return await call_next(request)

class AuditLogMiddleware(BaseHTTPMiddleware):
    """Middleware for logging authentication events."""
    
    async def dispatch(self, request: Request, call_next):
        """
        Log authentication attempts and outcomes.
        
        Args:
            request: FastAPI request
            call_next: Next middleware/handler
        """
        auth_path = request.url.path.startswith("/auth")
        
        if auth_path:
            # Log auth attempt
            logger.info(
                "Auth attempt",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "client_ip": request.client.host,
                    "user_agent": request.headers.get("user-agent")
                }
            )
            
            try:
                response = await call_next(request)
                
                # Log successful auth
                if response.status_code < 400:
                    logger.info(
                        "Auth success",
                        extra={
                            "path": request.url.path,
                            "status_code": response.status_code
                        }
                    )
                else:
                    # Log auth failure
                    logger.warning(
                        "Auth failure",
                        extra={
                            "path": request.url.path,
                            "status_code": response.status_code
                        }
                    )
                    
                return response
                
            except Exception as e:
                # Log auth error
                logger.error(
                    "Auth error",
                    extra={
                        "path": request.url.path,
                        "error": str(e)
                    }
                )
                raise
                
        return await call_next(request)

def configure_auth_middleware(app: FastAPI) -> None:
    """
    Configure all authentication-related middleware.
    
    Args:
        app: FastAPI application instance
    """
    # Configure protected routes
    protected_routes = {
        # Admin-only routes
        "POST /api/users": ["admin"],
        "DELETE /api/users/{id}": ["admin"],
        "PUT /api/system/config": ["admin"],
        
        # Editor routes
        "POST /api/articles": ["admin", "editor"],
        "PUT /api/articles/{id}": ["admin", "editor"],
        "DELETE /api/articles/{id}": ["admin", "editor"],
        
        # User routes (allow all authenticated users)
        "GET /api/articles": ["admin", "editor", "user"],
        "GET /api/articles/{id}": ["admin", "editor", "user"]
    }
    
    # Add middleware in order
    app.add_middleware(RoleBasedAccessMiddleware, protected_routes=protected_routes)
    app.add_middleware(AuditLogMiddleware)
    configure_cors(app)

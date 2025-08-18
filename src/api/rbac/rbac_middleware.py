"""
Enhanced Role-Based Access Control (RBAC) Middleware for FastAPI.

This middleware integrates with the RBAC system to enforce role-based access control
across all API endpoints based on Issue #60 requirements.
"""

import logging
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.rbac.rbac_system import rbac_manager, UserRole
from src.api.auth.jwt_auth import auth_handler

logger = logging.getLogger(__name__)

class EnhancedRBACMiddleware(BaseHTTPMiddleware):
    """Enhanced RBAC middleware that enforces role-based access control."""
    
    def __init__(self, app, excluded_paths: Optional[list] = None):
        """
        Initialize RBAC middleware.
        
        Args:
            app: FastAPI application
            excluded_paths: List of paths to exclude from RBAC checks
        """
        super().__init__(app)
        self.excluded_paths = excluded_paths or [
            "/",
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/auth/login",
            "/auth/register"
        ]
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request through RBAC system.
        
        Args:
            request: FastAPI request
            call_next: Next middleware/handler
        
        Returns:
            Response from next handler or access denied response
        """
        path = request.url.path
        method = request.method
        
        # Skip RBAC for excluded paths
        if self._is_excluded_path(path):
            return await call_next(request)
        
        try:
            # Extract and validate user from token
            user_data = await self._get_user_from_request(request)
            
            if not user_data:
                # No authentication for protected endpoint
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": "Authentication required",
                        "error_code": "AUTH_REQUIRED"
                    }
                )
            
            # Get user role
            user_role = self._extract_user_role(user_data)
            
            if not user_role:
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "Invalid or missing user role",
                        "error_code": "INVALID_ROLE"
                    }
                )
            
            # Check if user has access to the endpoint
            has_access = rbac_manager.has_access(user_role, method, path)
            
            if not has_access:
                # Log access denied attempt
                logger.warning(
                    f"Access denied: {user_role.value} user {user_data.get('sub', 'unknown')} "
                    f"attempted to access {method} {path}"
                )
                
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": f"Access denied. {user_role.value.title()} users cannot access this endpoint",
                        "error_code": "ACCESS_DENIED",
                        "required_role": self._get_minimum_required_role(method, path),
                        "user_role": user_role.value
                    }
                )
            
            # Store user info in request state for downstream use
            request.state.user = user_data
            request.state.user_role = user_role
            
            # Log successful access
            logger.info(
                f"Access granted: {user_role.value} user {user_data.get('sub', 'unknown')} "
                f"accessing {method} {path}"
            )
            
            response = await call_next(request)
            
            # Add RBAC headers to response
            response.headers["X-User-Role"] = user_role.value
            response.headers["X-Access-Granted"] = "true"
            
            return response
            
        except HTTPException as e:
            # Pass through HTTP exceptions (from auth system)
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail}
            )
        except Exception as e:
            logger.error(f"RBAC middleware error: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error during access control",
                    "error_code": "RBAC_ERROR"
                }
            )
    
    def _is_excluded_path(self, path: str) -> bool:
        """Check if path should be excluded from RBAC."""
        for excluded in self.excluded_paths:
            if path.startswith(excluded):
                return True
        return False
    
    async def _get_user_from_request(self, request: Request) -> Optional[Dict[str, Any]]:
        """Extract user data from request token."""
        try:
            # Try to get user data from auth handler
            user_data = await auth_handler(request)
            return user_data
        except HTTPException:
            # No valid authentication
            return None
        except Exception as e:
            logger.error(f"Error extracting user from request: {e}")
            return None
    
    def _extract_user_role(self, user_data: Dict[str, Any]) -> Optional[UserRole]:
        """Extract user role from user data."""
        try:
            role_str = user_data.get('role', '').lower()
            
            # Map role strings to UserRole enum
            role_mapping = {
                'admin': UserRole.ADMIN,
                'administrator': UserRole.ADMIN,
                'premium': UserRole.PREMIUM,
                'premium_user': UserRole.PREMIUM,
                'free': UserRole.FREE,
                'user': UserRole.FREE,  # Default 'user' role maps to FREE
                'basic': UserRole.FREE
            }
            
            return role_mapping.get(role_str)
            
        except Exception as e:
            logger.error(f"Error extracting user role: {e}")
            return None
    
    def _get_minimum_required_role(self, method: str, path: str) -> str:
        """Get the minimum role required for an endpoint."""
        required_permissions = rbac_manager.get_endpoint_permissions(method, path)
        
        if not required_permissions:
            return "none"
        
        # Check which roles have the required permissions
        for role in [UserRole.FREE, UserRole.PREMIUM, UserRole.ADMIN]:
            if rbac_manager.has_access(role, method, path):
                return role.value
        
        return "admin"  # Fallback to admin if no role has access

class RBACMetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to track RBAC-related metrics."""
    
    def __init__(self, app):
        """Initialize metrics middleware."""
        super().__init__(app)
        self.access_attempts = {}
        self.access_denials = {}
    
    async def dispatch(self, request: Request, call_next):
        """Track access attempts and denials."""
        path = request.url.path
        method = request.method
        
        response = await call_next(request)
        
        # Track metrics
        endpoint = f"{method} {path}"
        user_role = getattr(request.state, 'user_role', None)
        
        if user_role:
            # Track successful access
            if endpoint not in self.access_attempts:
                self.access_attempts[endpoint] = {}
            
            role_name = user_role.value
            self.access_attempts[endpoint][role_name] = \
                self.access_attempts[endpoint].get(role_name, 0) + 1
        
        # Track access denials
        if response.status_code == 403:
            if endpoint not in self.access_denials:
                self.access_denials[endpoint] = 0
            self.access_denials[endpoint] += 1
        
        return response
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get RBAC metrics."""
        return {
            "access_attempts": self.access_attempts,
            "access_denials": self.access_denials,
            "total_attempts": sum(
                sum(roles.values()) for roles in self.access_attempts.values()
            ),
            "total_denials": sum(self.access_denials.values())
        }

# Global metrics instance
rbac_metrics = RBACMetricsMiddleware(None)

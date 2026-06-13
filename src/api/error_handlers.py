"""
Global Error Handlers for FastAPI Application (Issue #428)

Provides consistent error handling and response formatting across all API endpoints.
Handles HTTP exceptions, validation errors, and unexpected server errors.
"""

import logging
import traceback
from datetime import datetime
from typing import Any, Dict, Optional, Union

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ErrorResponse:
    """Standardized error response model."""
    
    @staticmethod
    def create_error_response(
        status_code: int,
        message: str,
        details: Optional[Union[str, Dict[str, Any], list]] = None,
        error_code: Optional[str] = None,
        path: Optional[str] = None,
        timestamp: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a standardized error response."""
        response = {
            "error": {
                "status_code": status_code,
                "message": message,
                "timestamp": timestamp or datetime.utcnow().isoformat() + "Z",
                "path": path,
            }
        }
        
        if error_code:
            response["error"]["code"] = error_code
        
        if details:
            response["error"]["details"] = details
            
        return response


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Global HTTP exception handler.
    
    Handles standard HTTP exceptions (400, 401, 403, 404, etc.)
    and formats them consistently.
    """
    logger.warning(
        f"HTTP Exception: {exc.status_code} - {exc.detail} - Path: {request.url.path}"
    )
    
    # Map status codes to error codes
    error_code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED", 
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMIT_EXCEEDED",
        500: "INTERNAL_SERVER_ERROR",
        502: "BAD_GATEWAY", 
        503: "SERVICE_UNAVAILABLE",
        504: "GATEWAY_TIMEOUT"
    }
    
    error_code = error_code_map.get(exc.status_code, "UNKNOWN_ERROR")
    
    error_response = ErrorResponse.create_error_response(
        status_code=exc.status_code,
        message=str(exc.detail),
        error_code=error_code,
        path=str(request.url.path)
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handle FastAPI validation errors (422).
    
    Provides detailed information about validation failures
    including field names and error messages.
    """
    logger.warning(
        f"Validation Error: {exc.errors()} - Path: {request.url.path}"
    )
    
    # Format validation errors for better readability
    formatted_errors = []
    for error in exc.errors():
        field_path = " -> ".join(str(loc) for loc in error["loc"])
        formatted_errors.append({
            "field": field_path,
            "message": error["msg"],
            "type": error["type"],
            "input": error.get("input")
        })
    
    error_response = ErrorResponse.create_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message="Validation failed",
        error_code="VALIDATION_ERROR",
        details=formatted_errors,
        path=str(request.url.path)
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response
    )


async def pydantic_validation_exception_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    """
    Handle Pydantic validation errors.
    
    Similar to FastAPI validation but for direct Pydantic model validation.
    """
    logger.warning(
        f"Pydantic Validation Error: {exc.errors()} - Path: {request.url.path}"
    )
    
    formatted_errors = []
    for error in exc.errors():
        field_path = " -> ".join(str(loc) for loc in error["loc"])
        formatted_errors.append({
            "field": field_path, 
            "message": error["msg"],
            "type": error["type"]
        })
    
    error_response = ErrorResponse.create_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message="Model validation failed",
        error_code="PYDANTIC_VALIDATION_ERROR",
        details=formatted_errors,
        path=str(request.url.path)
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle unexpected exceptions (500 Internal Server Error).
    
    Logs the full exception details for debugging while
    returning a safe error message to clients.
    """
    logger.error(
        f"Unexpected error: {type(exc).__name__}: {str(exc)} - Path: {request.url.path}",
        exc_info=True
    )
    
    # Log full traceback for debugging
    logger.error(f"Traceback: {traceback.format_exc()}")
    
    # Don't expose internal error details in production
    error_message = "An internal server error occurred"
    details = None
    
    # In development, you might want to include more details
    # if os.getenv("DEBUG") == "true":
    #     error_message = str(exc)
    #     details = traceback.format_exc()
    
    error_response = ErrorResponse.create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message=error_message,
        error_code="INTERNAL_SERVER_ERROR",
        details=details,
        path=str(request.url.path)
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response
    )


async def starlette_http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """
    Handle Starlette HTTP exceptions.
    
    Ensures consistency between FastAPI and Starlette exceptions.
    """
    logger.warning(
        f"Starlette HTTP Exception: {exc.status_code} - {exc.detail} - Path: {request.url.path}"
    )
    
    error_response = ErrorResponse.create_error_response(
        status_code=exc.status_code,
        message=str(exc.detail) if exc.detail else "HTTP Error",
        error_code="HTTP_ERROR",
        path=str(request.url.path)
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response
    )


# Specific database error handlers
class DatabaseErrorHandler:
    """Handles database-specific errors."""
    
    @staticmethod
    def handle_connection_error(request: Request, exc: Exception) -> JSONResponse:
        """Handle database connection errors."""
        logger.error(f"Database connection error: {str(exc)} - Path: {request.url.path}")
        
        error_response = ErrorResponse.create_error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            message="Database service temporarily unavailable",
            error_code="DATABASE_CONNECTION_ERROR",
            path=str(request.url.path)
        )
        
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=error_response
        )
    
    @staticmethod
    def handle_timeout_error(request: Request, exc: Exception) -> JSONResponse:
        """Handle database timeout errors."""
        logger.error(f"Database timeout error: {str(exc)} - Path: {request.url.path}")
        
        error_response = ErrorResponse.create_error_response(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            message="Database request timed out",
            error_code="DATABASE_TIMEOUT",
            path=str(request.url.path)
        )
        
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content=error_response
        )


# Authentication/Authorization error handlers
class AuthErrorHandler:
    """Handles authentication and authorization errors."""
    
    @staticmethod
    def handle_invalid_token(request: Request) -> JSONResponse:
        """Handle invalid JWT token errors."""
        logger.warning(f"Invalid token attempt - Path: {request.url.path}")
        
        error_response = ErrorResponse.create_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message="Invalid or expired authentication token",
            error_code="INVALID_TOKEN",
            path=str(request.url.path)
        )
        
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=error_response,
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    @staticmethod
    def handle_insufficient_permissions(request: Request, required_role: str = None) -> JSONResponse:
        """Handle insufficient permissions errors."""
        logger.warning(f"Insufficient permissions - Path: {request.url.path}")
        
        message = "Insufficient permissions to access this resource"
        if required_role:
            message += f" (requires {required_role} role)"
        
        error_response = ErrorResponse.create_error_response(
            status_code=status.HTTP_403_FORBIDDEN,
            message=message,
            error_code="INSUFFICIENT_PERMISSIONS",
            path=str(request.url.path)
        )
        
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=error_response
        )


def configure_error_handlers(app: FastAPI) -> None:
    """
    Configure all error handlers for the FastAPI application.
    
    Args:
        app: FastAPI application instance
    """
    # Register exception handlers
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, pydantic_validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
    
    logger.info("Error handlers configured successfully")


# Utility functions for raising consistent errors
def raise_not_found_error(resource: str, identifier: str = None) -> None:
    """Raise a consistent 404 error."""
    message = f"{resource} not found"
    if identifier:
        message += f" (ID: {identifier})"
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def raise_validation_error(field: str, message: str) -> None:
    """Raise a consistent validation error."""
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Validation error for field '{field}': {message}"
    )


def raise_unauthorized_error(message: str = "Authentication required") -> None:
    """Raise a consistent unauthorized error."""
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=message)


def raise_forbidden_error(message: str = "Access forbidden") -> None:
    """Raise a consistent forbidden error."""
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)


def raise_server_error(message: str = "Internal server error") -> None:
    """Raise a consistent server error."""
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message)


# Custom exception classes
class NeuroNewsAPIError(Exception):
    """Base exception for NeuroNews API errors."""
    
    def __init__(self, message: str, status_code: int = 500, error_code: str = None):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(self.message)


class DatabaseConnectionError(NeuroNewsAPIError):
    """Raised when database connection fails."""
    
    def __init__(self, message: str = "Database connection failed"):
        super().__init__(message, status_code=503, error_code="DATABASE_CONNECTION_ERROR")


class RateLimitExceededError(NeuroNewsAPIError):
    """Raised when rate limit is exceeded."""
    
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, status_code=429, error_code="RATE_LIMIT_EXCEEDED")


class GraphServiceError(NeuroNewsAPIError):
    """Raised when graph service is unavailable."""
    
    def __init__(self, message: str = "Graph service unavailable"):
        super().__init__(message, status_code=503, error_code="GRAPH_SERVICE_ERROR")

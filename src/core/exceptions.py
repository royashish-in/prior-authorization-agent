"""
Custom exception handling for the Prior Authorization Agent.

This module provides standardized error responses and exception handling
to ensure consistent API error formats across all endpoints.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exception_handlers import http_exception_handler
import logging

logger = logging.getLogger(__name__)


class StandardHTTPException(HTTPException):
    """
    Custom HTTPException that ensures consistent error response format.
    """
    
    def __init__(
        self,
        status_code: int,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        suggestion: Optional[str] = None,
        request_id: Optional[str] = None
    ):
        self.status_code = status_code
        self.message = message
        self.error_code = error_code or self._get_default_error_code(status_code)
        self.details = details or {}
        self.suggestion = suggestion
        self.request_id = request_id
        
        # Create standardized detail for FastAPI
        detail = {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "details": self.details,
                "request_id": self.request_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }
        
        if self.suggestion:
            detail["error"]["suggestion"] = self.suggestion
        
        super().__init__(status_code=status_code, detail=detail)
    
    def _get_default_error_code(self, status_code: int) -> str:
        """Get default error code based on HTTP status code."""
        error_codes = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "CONFLICT",
            422: "VALIDATION_ERROR",
            429: "RATE_LIMITED",
            500: "INTERNAL_SERVER_ERROR",
            502: "BAD_GATEWAY",
            503: "SERVICE_UNAVAILABLE"
        }
        return error_codes.get(status_code, "UNKNOWN_ERROR")


class ValidationException(StandardHTTPException):
    """Exception for validation errors."""
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        suggestion: Optional[str] = None,
        request_id: Optional[str] = None
    ):
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)
        
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message=message,
            error_code="VALIDATION_ERROR",
            details=details,
            suggestion=suggestion,
            request_id=request_id
        )


class AuthenticationException(StandardHTTPException):
    """Exception for authentication errors."""
    
    def __init__(
        self,
        message: str = "Authentication required",
        request_id: Optional[str] = None
    ):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=message,
            error_code="AUTHENTICATION_REQUIRED",
            request_id=request_id
        )


class AuthorizationException(StandardHTTPException):
    """Exception for authorization errors."""
    
    def __init__(
        self,
        message: str = "Access denied",
        required_permission: Optional[str] = None,
        request_id: Optional[str] = None
    ):
        details = {}
        if required_permission:
            details["required_permission"] = required_permission
        
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            message=message,
            error_code="ACCESS_DENIED",
            details=details,
            request_id=request_id
        )


class ResourceNotFoundException(StandardHTTPException):
    """Exception for resource not found errors."""
    
    def __init__(
        self,
        resource_type: str,
        resource_id: str,
        request_id: Optional[str] = None
    ):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"{resource_type} not found",
            error_code="RESOURCE_NOT_FOUND",
            details={
                "resource_type": resource_type,
                "resource_id": resource_id
            },
            request_id=request_id
        )


class PolicyException(StandardHTTPException):
    """Exception for policy-related errors."""
    
    def __init__(
        self,
        message: str,
        policy_id: Optional[str] = None,
        conflict_type: Optional[str] = None,
        request_id: Optional[str] = None
    ):
        details = {}
        if policy_id:
            details["policy_id"] = policy_id
        if conflict_type:
            details["conflict_type"] = conflict_type
        
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            message=message,
            error_code="POLICY_ERROR",
            details=details,
            request_id=request_id
        )


async def custom_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Custom HTTP exception handler that ensures consistent error response format.
    """
    # If it's already our custom exception, return as-is
    if isinstance(exc, StandardHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail
        )
    
    # Convert standard HTTPException to our format
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        # Already in correct format
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail
        )
    
    # For OAuth2 endpoints, preserve the original format
    if request.url.path.endswith("/login") or request.url.path.endswith("/refresh"):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": str(exc.detail) if exc.detail else "An error occurred"}
        )
    
    # Convert to standardized format for API endpoints
    error_response = {
        "error": {
            "code": _get_error_code_from_status(exc.status_code),
            "message": str(exc.detail) if exc.detail else "An error occurred",
            "details": {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        "message": str(exc.detail) if exc.detail else "An error occurred",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    # Add request ID if available
    if hasattr(request.state, "request_id"):
        error_response["error"]["request_id"] = request.state.request_id
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response
    )


def _get_error_code_from_status(status_code: int) -> str:
    """Get error code from HTTP status code."""
    error_codes = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED", 
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        500: "INTERNAL_SERVER_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE"
    }
    return error_codes.get(status_code, "UNKNOWN_ERROR")


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle validation exceptions from Pydantic."""
    logger.error(f"Validation error: {exc}")
    
    error_response = {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": {"validation_errors": str(exc)},
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        "message": "Request validation failed",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    if hasattr(request.state, "request_id"):
        error_response["error"]["request_id"] = request.state.request_id
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    error_response = {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An internal server error occurred",
            "details": {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        "message": "An internal server error occurred",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    if hasattr(request.state, "request_id"):
        error_response["error"]["request_id"] = request.state.request_id
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response
    )
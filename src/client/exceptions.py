"""
Exception classes for Prior Authorization Agent API Client.

This module defines custom exceptions for different types of API errors
with detailed error information and suggested remediation steps.
"""

from typing import List, Dict, Any, Optional


class PriorAuthAPIError(Exception):
    """Base exception for all Prior Authorization API errors."""
    
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        details: Optional[List[Dict[str, Any]]] = None,
        request_id: Optional[str] = None
    ):
        """
        Initialize API error.
        
        Args:
            message: Human-readable error message
            status_code: HTTP status code
            error_code: API-specific error code
            details: Detailed error information
            request_id: Request tracking ID for support
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or []
        self.request_id = request_id
    
    def __str__(self) -> str:
        """Return formatted error string."""
        error_parts = [self.message]
        
        if self.error_code:
            error_parts.append(f"Error Code: {self.error_code}")
        
        if self.status_code:
            error_parts.append(f"Status: {self.status_code}")
        
        if self.request_id:
            error_parts.append(f"Request ID: {self.request_id}")
        
        return " | ".join(error_parts)


class AuthenticationError(PriorAuthAPIError):
    """Exception raised for authentication failures."""
    
    def __init__(self, message: str = "Authentication failed", **kwargs):
        super().__init__(message, status_code=401, error_code="AUTHENTICATION_ERROR", **kwargs)


class ValidationError(PriorAuthAPIError):
    """Exception raised for request validation failures."""
    
    def __init__(self, message: str = "Request validation failed", **kwargs):
        super().__init__(message, status_code=400, error_code="VALIDATION_ERROR", **kwargs)
    
    def get_field_errors(self) -> Dict[str, str]:
        """
        Get validation errors organized by field.
        
        Returns:
            Dictionary mapping field names to error messages
        """
        field_errors = {}
        for detail in self.details:
            if isinstance(detail, dict) and "field" in detail and "message" in detail:
                field_errors[detail["field"]] = detail["message"]
        return field_errors
    
    def get_suggestions(self) -> Dict[str, str]:
        """
        Get suggested corrections for validation errors.
        
        Returns:
            Dictionary mapping field names to suggestions
        """
        suggestions = {}
        for detail in self.details:
            if isinstance(detail, dict) and "field" in detail and "suggestion" in detail:
                if detail["suggestion"]:
                    suggestions[detail["field"]] = detail["suggestion"]
        return suggestions


class RateLimitError(PriorAuthAPIError):
    """Exception raised when rate limits are exceeded."""
    
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        limit: Optional[int] = None,
        remaining: Optional[int] = None,
        **kwargs
    ):
        """
        Initialize rate limit error.
        
        Args:
            message: Error message
            retry_after: Seconds to wait before retrying
            limit: Rate limit threshold
            remaining: Remaining requests in current window
            **kwargs: Additional error parameters
        """
        super().__init__(message, status_code=429, error_code="RATE_LIMIT_EXCEEDED", **kwargs)
        self.retry_after = retry_after
        self.limit = limit
        self.remaining = remaining
    
    def __str__(self) -> str:
        """Return formatted rate limit error string."""
        error_str = super().__str__()
        
        if self.retry_after:
            error_str += f" | Retry after: {self.retry_after}s"
        
        if self.limit and self.remaining is not None:
            error_str += f" | Limit: {self.remaining}/{self.limit}"
        
        return error_str


class NotFoundError(PriorAuthAPIError):
    """Exception raised when requested resources are not found."""
    
    def __init__(self, message: str = "Resource not found", **kwargs):
        super().__init__(message, status_code=404, error_code="NOT_FOUND", **kwargs)


class ForbiddenError(PriorAuthAPIError):
    """Exception raised for insufficient permissions."""
    
    def __init__(self, message: str = "Insufficient permissions", **kwargs):
        super().__init__(message, status_code=403, error_code="FORBIDDEN", **kwargs)


class ServerError(PriorAuthAPIError):
    """Exception raised for server-side errors."""
    
    def __init__(self, message: str = "Internal server error", **kwargs):
        super().__init__(message, status_code=500, error_code="INTERNAL_ERROR", **kwargs)


class NetworkError(PriorAuthAPIError):
    """Exception raised for network connectivity issues."""
    
    def __init__(self, message: str = "Network connection failed", **kwargs):
        super().__init__(message, error_code="NETWORK_ERROR", **kwargs)


class TimeoutError(PriorAuthAPIError):
    """Exception raised for request timeouts."""
    
    def __init__(self, message: str = "Request timeout", **kwargs):
        super().__init__(message, status_code=408, error_code="TIMEOUT", **kwargs)
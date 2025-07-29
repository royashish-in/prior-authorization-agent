"""
Prior Authorization Agent API Client SDK.

This package provides a Python client SDK for easy integration with the
Prior Authorization Agent API, including authentication, request management,
and comprehensive error handling.
"""

from .client import PriorAuthClient
from .exceptions import (
    PriorAuthAPIError,
    AuthenticationError,
    ValidationError,
    RateLimitError,
    NotFoundError
)
from .models import (
    AuthorizationRequest,
    AuthorizationDecision,
    RequestStatus,
    DecisionStatus
)

__version__ = "1.0.0"
__all__ = [
    "PriorAuthClient",
    "PriorAuthAPIError",
    "AuthenticationError", 
    "ValidationError",
    "RateLimitError",
    "NotFoundError",
    "AuthorizationRequest",
    "AuthorizationDecision",
    "RequestStatus",
    "DecisionStatus"
]
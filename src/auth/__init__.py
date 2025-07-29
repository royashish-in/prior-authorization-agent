"""
Authentication and authorization module for Prior Authorization Agent.

This module provides OAuth 2.0 authentication, JWT token management,
and role-based access control for healthcare data protection.
"""

from .models import User, UserRole, TokenData
from .oauth2 import (
    create_access_token, 
    verify_token, 
    get_current_user, 
    get_current_active_user,
    require_roles,
    require_organization_access
)
from .rate_limiter import RateLimiter

__all__ = [
    "User",
    "UserRole",
    "TokenData",
    "create_access_token",
    "verify_token",
    "get_current_user",
    "get_current_active_user",
    "require_roles",
    "require_organization_access",
    "RateLimiter"
]
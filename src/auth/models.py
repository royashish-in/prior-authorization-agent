"""
Authentication data models for Prior Authorization Agent.

This module defines user models, roles, and token structures
for OAuth 2.0 authentication and role-based access control.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class UserRole(str, Enum):
    """
    User roles for role-based access control.
    
    Implements minimum necessary principle for healthcare data access.
    """
    PROVIDER = "provider"  # Healthcare providers submitting requests
    PAYER_ADMIN = "payer_admin"  # Payer administrators managing policies
    COMPLIANCE_OFFICER = "compliance_officer"  # Compliance and audit access
    SYSTEM_ADMIN = "system_admin"  # System administration
    ADMIN = "admin"  # Administrative access (alias for system_admin)
    API_CLIENT = "api_client"  # External system integration


class User(BaseModel):
    """
    User model for authentication and authorization.
    
    Contains user identity and role information for access control.
    """
    user_id: str = Field(..., description="Unique user identifier")
    username: str = Field(..., description="Username for authentication")
    email: str = Field(..., description="User email address")
    full_name: str = Field(..., description="User's full name")
    roles: List[UserRole] = Field(..., description="User roles for access control")
    organization_id: str = Field(..., description="Organization identifier")
    is_active: bool = Field(default=True, description="User account status")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Account creation timestamp")
    last_login: Optional[datetime] = Field(None, description="Last login timestamp")
    
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat()
        }
    )


class TokenData(BaseModel):
    """
    JWT token payload data structure.
    
    Contains user identity and authorization information.
    """
    user_id: str = Field(..., description="User identifier")
    username: str = Field(..., description="Username")
    roles: List[UserRole] = Field(..., description="User roles")
    organization_id: str = Field(..., description="Organization identifier")
    exp: datetime = Field(..., description="Token expiration time")
    iat: datetime = Field(default_factory=datetime.utcnow, description="Token issued at time")
    
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.timestamp()
        }
    )


class TokenResponse(BaseModel):
    """
    OAuth 2.0 token response structure.
    
    Standard OAuth 2.0 response format for token endpoints.
    """
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration in seconds")
    scope: Optional[str] = Field(None, description="Token scope")


class LoginRequest(BaseModel):
    """
    User login request structure.
    
    Contains credentials for authentication.
    """
    username: str = Field(..., description="Username or email")
    password: str = Field(..., description="User password")
    organization_id: Optional[str] = Field(None, description="Organization identifier")


class RolePermission(BaseModel):
    """
    Role-based permission model.
    
    Defines what actions each role can perform.
    """
    role: UserRole = Field(..., description="User role")
    permissions: List[str] = Field(..., description="List of permissions")
    resource_patterns: List[str] = Field(..., description="Resource access patterns")


# Default role permissions following minimum necessary principle
DEFAULT_ROLE_PERMISSIONS = {
    UserRole.PROVIDER: RolePermission(
        role=UserRole.PROVIDER,
        permissions=[
            "authorization:create",
            "authorization:read_own",
            "authorization:update_own",
            "dashboard:read_own"
        ],
        resource_patterns=[
            "/api/v1/authorization/requests",
            "/api/v1/dashboard/provider/*"
        ]
    ),
    UserRole.PAYER_ADMIN: RolePermission(
        role=UserRole.PAYER_ADMIN,
        permissions=[
            "authorization:read_all",
            "policy:create",
            "policy:read",
            "policy:update",
            "policy:delete",
            "dashboard:read_all"
        ],
        resource_patterns=[
            "/api/v1/authorization/*",
            "/api/v1/policies/*",
            "/api/v1/dashboard/*"
        ]
    ),
    UserRole.COMPLIANCE_OFFICER: RolePermission(
        role=UserRole.COMPLIANCE_OFFICER,
        permissions=[
            "authorization:read_all",
            "audit:read",
            "reports:generate",
            "dashboard:read_all"
        ],
        resource_patterns=[
            "/api/v1/authorization/*/audit",
            "/api/v1/audit/*",
            "/api/v1/reports/*"
        ]
    ),
    UserRole.SYSTEM_ADMIN: RolePermission(
        role=UserRole.SYSTEM_ADMIN,
        permissions=[
            "*:*"  # Full access
        ],
        resource_patterns=[
            "/api/v1/*"
        ]
    ),
    UserRole.API_CLIENT: RolePermission(
        role=UserRole.API_CLIENT,
        permissions=[
            "authorization:create",
            "authorization:read_own",
            "authorization:update_own"
        ],
        resource_patterns=[
            "/api/v1/authorization/requests",
            "/api/v1/authorization/status/*"
        ]
    )
}
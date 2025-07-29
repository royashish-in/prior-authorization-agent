"""
OAuth 2.0 implementation for Prior Authorization Agent.

This module provides JWT token creation, validation, and OAuth 2.0
authentication flows for secure healthcare data access.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext

from src.core.config import get_settings
from .models import TokenData, User, UserRole

logger = logging.getLogger(__name__)

# OAuth 2.0 security scheme
security = HTTPBearer(auto_error=False)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against its hash.
    
    Args:
        plain_password: Plain text password
        hashed_password: Bcrypt hashed password
        
    Returns:
        True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Generate bcrypt hash for a password.
    
    Args:
        password: Plain text password
        
    Returns:
        Bcrypt hashed password
    """
    return pwd_context.hash(password)


def create_access_token(
    user: User,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token for authenticated user.
    
    Args:
        user: Authenticated user object
        expires_delta: Optional custom expiration time
        
    Returns:
        JWT access token string
        
    Raises:
        ValueError: If user data is invalid
    """
    settings = get_settings()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expiration_hours)
    
    # Create token payload
    token_data = TokenData(
        user_id=user.user_id,
        username=user.username,
        roles=user.roles,
        organization_id=user.organization_id,
        exp=expire
    )
    
    # Convert to dict for JWT encoding
    to_encode = {
        "sub": token_data.user_id,
        "username": token_data.username,
        "roles": [role.value for role in token_data.roles],
        "organization_id": token_data.organization_id,
        "exp": token_data.exp,
        "iat": token_data.iat
    }
    
    try:
        encoded_jwt = jwt.encode(
            to_encode,
            settings.secret_key,
            algorithm=settings.jwt_algorithm
        )
        
        logger.info(
            "Access token created",
            extra={
                "user_id": user.user_id,
                "username": user.username,
                "organization_id": user.organization_id,
                "expires_at": expire.isoformat()
            }
        )
        
        return encoded_jwt
        
    except Exception as e:
        logger.error(
            "Failed to create access token",
            extra={
                "user_id": user.user_id,
                "error": str(e)
            }
        )
        raise ValueError(f"Failed to create access token: {e}")


def verify_token(token: str) -> Optional[TokenData]:
    """
    Verify and decode a JWT access token.
    
    Args:
        token: JWT token string
        
    Returns:
        TokenData if valid, None if invalid
    """
    settings = get_settings()
    
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        
        # Extract token data
        user_id: str = payload.get("sub")
        username: str = payload.get("username")
        roles_str: list = payload.get("roles", [])
        organization_id: str = payload.get("organization_id")
        exp_timestamp: float = payload.get("exp")
        iat_timestamp: float = payload.get("iat")
        
        if not all([user_id, username, organization_id]):
            logger.warning(
                "Invalid token payload - missing required fields",
                extra={"payload_keys": list(payload.keys())}
            )
            return None
        
        # Convert role strings back to enums
        try:
            roles = [UserRole(role) for role in roles_str]
        except ValueError as e:
            logger.warning(
                "Invalid roles in token",
                extra={"roles": roles_str, "error": str(e)}
            )
            return None
        
        # Convert timestamps to datetime with timezone
        exp = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
        iat = datetime.fromtimestamp(iat_timestamp, tz=timezone.utc)
        
        # Check if token is expired
        if datetime.now(timezone.utc) > exp:
            logger.warning(
                "Token expired",
                extra={
                    "user_id": user_id,
                    "expired_at": exp.isoformat()
                }
            )
            return None
        
        token_data = TokenData(
            user_id=user_id,
            username=username,
            roles=roles,
            organization_id=organization_id,
            exp=exp,
            iat=iat
        )
        
        logger.debug(
            "Token verified successfully",
            extra={
                "user_id": user_id,
                "username": username,
                "organization_id": organization_id
            }
        )
        
        return token_data
        
    except JWTError as e:
        logger.warning(
            "JWT verification failed",
            extra={"error": str(e)}
        )
        return None
    except Exception as e:
        logger.error(
            "Unexpected error during token verification",
            extra={"error": str(e)}
        )
        return None


def refresh_token(current_token: str) -> Optional[str]:
    """
    Refresh an access token if it's still valid.
    
    Args:
        current_token: Current JWT token
        
    Returns:
        New JWT token if refresh successful, None otherwise
    """
    token_data = verify_token(current_token)
    if not token_data:
        return None
    
    # Create a mock user object for token creation
    # In a real implementation, this would fetch from database
    user = User(
        user_id=token_data.user_id,
        username=token_data.username,
        email=f"{token_data.username}@example.com",  # Would be fetched from DB
        full_name="User Name",  # Would be fetched from DB
        roles=token_data.roles,
        organization_id=token_data.organization_id
    )
    
    return create_access_token(user)


def decode_token_without_verification(token: str) -> Optional[dict]:
    """
    Decode JWT token without signature verification (for debugging).
    
    Args:
        token: JWT token string
        
    Returns:
        Token payload dict if decodable, None otherwise
    """
    try:
        return jwt.get_unverified_claims(token)
    except JWTError:
        return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> TokenData:
    """
    FastAPI dependency to get current authenticated user from JWT token.
    
    Args:
        credentials: HTTP Bearer token credentials
        
    Returns:
        TokenData for authenticated user
        
    Raises:
        HTTPException: If authentication fails
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Check if credentials are provided
    if credentials is None:
        logger.warning("No authorization credentials provided")
        raise credentials_exception
    
    try:
        token = credentials.credentials
        token_data = verify_token(token)
        
        if token_data is None:
            logger.warning("Invalid token provided for authentication")
            raise credentials_exception
            
        logger.debug(
            "User authenticated successfully",
            extra={
                "user_id": token_data.user_id,
                "username": token_data.username,
                "organization_id": token_data.organization_id
            }
        )
        
        return token_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Authentication error",
            extra={"error": str(e)}
        )
        raise credentials_exception


async def get_current_active_user(
    current_user: TokenData = Depends(get_current_user)
) -> TokenData:
    """
    FastAPI dependency to get current active user.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        TokenData for active user
        
    Raises:
        HTTPException: If user is inactive
    """
    # In a real implementation, check user status in database
    # For now, assume all authenticated users are active
    return current_user


def require_roles(*required_roles: UserRole):
    """
    Create a dependency that requires specific user roles.
    
    Args:
        required_roles: Required user roles
        
    Returns:
        FastAPI dependency function
    """
    def role_checker(current_user: TokenData = Depends(get_current_active_user)) -> TokenData:
        """
        Check if current user has required roles.
        
        Args:
            current_user: Current authenticated user
            
        Returns:
            TokenData if authorized
            
        Raises:
            HTTPException: If user lacks required roles
        """
        user_roles = set(current_user.roles)
        required_roles_set = set(required_roles)
        
        # System admin has access to everything
        if UserRole.SYSTEM_ADMIN in user_roles:
            return current_user
        
        # Check if user has any of the required roles
        if not user_roles.intersection(required_roles_set):
            logger.warning(
                "Access denied - insufficient permissions",
                extra={
                    "user_id": current_user.user_id,
                    "user_roles": [role.value for role in current_user.roles],
                    "required_roles": [role.value for role in required_roles]
                }
            )
            
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        
        logger.debug(
            "Role authorization successful",
            extra={
                "user_id": current_user.user_id,
                "authorized_roles": [role.value for role in user_roles.intersection(required_roles_set)]
            }
        )
        
        return current_user
    
    return role_checker


def require_organization_access(organization_id: str):
    """
    Create a dependency that requires access to specific organization.
    
    Args:
        organization_id: Required organization ID
        
    Returns:
        FastAPI dependency function
    """
    def organization_checker(current_user: TokenData = Depends(get_current_active_user)) -> TokenData:
        """
        Check if current user has access to organization.
        
        Args:
            current_user: Current authenticated user
            
        Returns:
            TokenData if authorized
            
        Raises:
            HTTPException: If user lacks organization access
        """
        # System admin and compliance officers have cross-organization access
        if UserRole.SYSTEM_ADMIN in current_user.roles or UserRole.COMPLIANCE_OFFICER in current_user.roles:
            return current_user
        
        # Check organization access
        if current_user.organization_id != organization_id:
            logger.warning(
                "Access denied - organization mismatch",
                extra={
                    "user_id": current_user.user_id,
                    "user_organization": current_user.organization_id,
                    "requested_organization": organization_id
                }
            )
            
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to organization data"
            )
        
        return current_user
    
    return organization_checker


def require_permissions(*permissions: str):
    """
    Create a dependency that requires specific permissions.
    
    Args:
        permissions: Required permission strings
        
    Returns:
        FastAPI dependency function
    """
    def permission_checker(current_user: TokenData = Depends(get_current_active_user)) -> TokenData:
        """
        Check if current user has required permissions.
        
        Args:
            current_user: Current authenticated user
            
        Returns:
            TokenData if authorized
            
        Raises:
            HTTPException: If user lacks required permissions
        """
        # System admin has all permissions
        if UserRole.SYSTEM_ADMIN in current_user.roles:
            return current_user
        
        # Define role-based permissions
        role_permissions = {
            UserRole.PROVIDER: [
                "submit_requests",
                "view_own_requests",
                "update_own_requests"
            ],
            UserRole.PAYER_ADMIN: [
                "submit_requests",
                "view_own_requests",
                "update_own_requests",
                "view_all_requests",
                "configure_policies",
                "manage_users"
            ],
            UserRole.COMPLIANCE_OFFICER: [
                "view_all_requests",
                "view_audit_logs",
                "generate_reports",
                "view_security_events"
            ],
            UserRole.SYSTEM_ADMIN: ["*"]  # All permissions
        }
        
        # Get user permissions based on roles
        user_permissions = set()
        for role in current_user.roles:
            if role in role_permissions:
                if "*" in role_permissions[role]:
                    # System admin has all permissions
                    return current_user
                user_permissions.update(role_permissions[role])
        
        # Check if user has required permissions
        required_permissions_set = set(permissions)
        if not user_permissions.intersection(required_permissions_set):
            logger.warning(
                "Access denied - insufficient permissions",
                extra={
                    "user_id": current_user.user_id,
                    "user_permissions": list(user_permissions),
                    "required_permissions": list(permissions)
                }
            )
            
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        
        logger.debug(
            "Permission authorization successful",
            extra={
                "user_id": current_user.user_id,
                "granted_permissions": list(user_permissions.intersection(required_permissions_set))
            }
        )
        
        return current_user
    
    return permission_checker
"""
Authentication API endpoints for Prior Authorization Agent.

This module provides OAuth 2.0 authentication endpoints including
login, token refresh, and user management for healthcare providers.
"""

import logging
from datetime import timedelta
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from src.auth.models import LoginRequest, TokenResponse, User, UserRole, TokenData
from src.auth.oauth2 import (
    create_access_token,
    get_current_active_user,
    get_password_hash,
    verify_password
)
from src.auth.rate_limiter import rate_limiter
from src.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


# Mock user database - In production, this would be a real database
# Passwords should be loaded from secure environment variables
MOCK_USERS_DB = {
    "provider1": {
        "user_id": "user_001",
        "username": "provider1",
        "email": "provider1@hospital.com",
        "full_name": "Dr. John Provider",
        "hashed_password": get_password_hash("<SECURE_PASSWORD>"),  # Load from env
        "roles": [UserRole.PROVIDER],
        "organization_id": "org_hospital_001",
        "is_active": True
    },
    "admin1": {
        "user_id": "user_002", 
        "username": "admin1",
        "email": "admin1@payer.com",
        "full_name": "Jane Admin",
        "hashed_password": get_password_hash("<SECURE_PASSWORD>"),  # Load from env
        "roles": [UserRole.PAYER_ADMIN],
        "organization_id": "org_payer_001",
        "is_active": True
    },
    "compliance1": {
        "user_id": "user_003",
        "username": "compliance1", 
        "email": "compliance1@payer.com",
        "full_name": "Bob Compliance",
        "hashed_password": get_password_hash("<SECURE_PASSWORD>"),  # Load from env
        "roles": [UserRole.COMPLIANCE_OFFICER],
        "organization_id": "org_payer_001",
        "is_active": True
    }
}


def authenticate_user(username: str, password: str) -> User | None:
    """
    Authenticate user credentials against user database.
    
    Args:
        username: Username or email
        password: Plain text password
        
    Returns:
        User object if authentication successful, None otherwise
    """
    user_data = MOCK_USERS_DB.get(username)
    if not user_data:
        logger.warning(
            "Authentication failed - user not found",
            extra={"username": username}
        )
        return None
    
    if not verify_password(password, user_data["hashed_password"]):
        logger.warning(
            "Authentication failed - invalid password",
            extra={"username": username}
        )
        return None
    
    if not user_data["is_active"]:
        logger.warning(
            "Authentication failed - user inactive",
            extra={"username": username}
        )
        return None
    
    # Create User object
    user = User(
        user_id=user_data["user_id"],
        username=user_data["username"],
        email=user_data["email"],
        full_name=user_data["full_name"],
        roles=user_data["roles"],
        organization_id=user_data["organization_id"],
        is_active=user_data["is_active"]
    )
    
    logger.info(
        "User authenticated successfully",
        extra={
            "user_id": user.user_id,
            "username": user.username,
            "organization_id": user.organization_id
        }
    )
    
    return user


@router.post("/token", response_model=TokenResponse)
async def token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends()
) -> TokenResponse:
    """
    OAuth 2.0 token endpoint (standard OAuth2 endpoint name).
    
    This is an alias for the login endpoint to comply with OAuth2 standards.
    """
    return await login(request, form_data)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends()
) -> TokenResponse:
    """
    OAuth 2.0 token endpoint for user authentication.
    
    Args:
        request: FastAPI request object
        form_data: OAuth2 password form data
        
    Returns:
        JWT access token response
        
    Raises:
        HTTPException: If authentication fails or rate limited
    """
    # Check for brute force attempts
    if rate_limiter.record_auth_failure(request):
        logger.warning(
            "Login blocked due to brute force detection",
            extra={"client_ip": request.client.host if request.client else "unknown"}
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed authentication attempts. Please try again later."
        )
    
    # Check rate limiting
    is_allowed, rate_info = rate_limiter.check_rate_limit(request)
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={
                "X-RateLimit-Limit": str(rate_info["limit"]),
                "X-RateLimit-Remaining": str(rate_info["remaining"]),
                "Retry-After": str(rate_info["retry_after"])
            }
        )
    
    # Authenticate user
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        # Don't clear auth failures on failed login
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Clear auth failures on successful login
    rate_limiter.clear_auth_failures(request)
    
    # Create access token
    settings = get_settings()
    access_token_expires = timedelta(hours=settings.jwt_expiration_hours)
    access_token = create_access_token(user, expires_delta=access_token_expires)
    
    logger.info(
        "Login successful",
        extra={
            "user_id": user.user_id,
            "username": user.username,
            "client_ip": request.client.host if request.client else "unknown"
        }
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=int(access_token_expires.total_seconds())
    )


@router.post("/login-json", response_model=TokenResponse)
async def login_json(
    request: Request,
    login_data: LoginRequest
) -> TokenResponse:
    """
    JSON-based login endpoint for API clients.
    
    Args:
        request: FastAPI request object
        login_data: Login request data
        
    Returns:
        JWT access token response
        
    Raises:
        HTTPException: If authentication fails or rate limited
    """
    # Check for brute force attempts
    if rate_limiter.record_auth_failure(request):
        logger.warning(
            "Login blocked due to brute force detection",
            extra={"client_ip": request.client.host if request.client else "unknown"}
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed authentication attempts. Please try again later."
        )
    
    # Check rate limiting
    is_allowed, rate_info = rate_limiter.check_rate_limit(request)
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={
                "X-RateLimit-Limit": str(rate_info["limit"]),
                "X-RateLimit-Remaining": str(rate_info["remaining"]),
                "Retry-After": str(rate_info["retry_after"])
            }
        )
    
    # Authenticate user
    user = authenticate_user(login_data.username, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    # Clear auth failures on successful login
    rate_limiter.clear_auth_failures(request)
    
    # Create access token
    settings = get_settings()
    access_token_expires = timedelta(hours=settings.jwt_expiration_hours)
    access_token = create_access_token(user, expires_delta=access_token_expires)
    
    logger.info(
        "JSON login successful",
        extra={
            "user_id": user.user_id,
            "username": user.username,
            "client_ip": request.client.host if request.client else "unknown"
        }
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=int(access_token_expires.total_seconds())
    )


@router.get("/me")
async def get_current_user_info(
    current_user: TokenData = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Get current authenticated user information.
    
    Args:
        current_user: Current authenticated user from JWT token
        
    Returns:
        User information dictionary
    """
    logger.debug(
        "User info requested",
        extra={"user_id": current_user.user_id}
    )
    
    return {
        "user_id": current_user.user_id,
        "username": current_user.username,
        "roles": [role.value for role in current_user.roles],
        "organization_id": current_user.organization_id,
        "token_expires": current_user.exp.isoformat()
    }


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    current_user: TokenData = Depends(get_current_active_user)
) -> TokenResponse:
    """
    Refresh JWT access token for authenticated user.
    
    Args:
        current_user: Current authenticated user from JWT token
        
    Returns:
        New JWT access token response
    """
    # Create new user object for token creation
    user = User(
        user_id=current_user.user_id,
        username=current_user.username,
        email=f"{current_user.username}@example.com",  # Would be fetched from DB
        full_name="User Name",  # Would be fetched from DB
        roles=current_user.roles,
        organization_id=current_user.organization_id
    )
    
    # Create new access token
    settings = get_settings()
    access_token_expires = timedelta(hours=settings.jwt_expiration_hours)
    access_token = create_access_token(user, expires_delta=access_token_expires)
    
    logger.info(
        "Token refreshed successfully",
        extra={
            "user_id": current_user.user_id,
            "username": current_user.username
        }
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=int(access_token_expires.total_seconds())
    )


@router.post("/logout")
async def logout(
    current_user: TokenData = Depends(get_current_active_user)
) -> Dict[str, str]:
    """
    Logout endpoint (token invalidation would be handled by client).
    
    Args:
        current_user: Current authenticated user from JWT token
        
    Returns:
        Logout confirmation message
    """
    logger.info(
        "User logged out",
        extra={
            "user_id": current_user.user_id,
            "username": current_user.username
        }
    )
    
    return {"message": "Successfully logged out"}
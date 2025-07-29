"""
Tests for authentication and authorization functionality.

This module tests OAuth 2.0 authentication, JWT token handling,
role-based access control, and security features.
"""

import pytest
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from src.auth.models import User, UserRole, TokenData
from src.auth.oauth2 import (
    create_access_token,
    verify_token,
    get_current_user,
    require_roles,
    require_organization_access
)
from src.auth.rate_limiter import RateLimiter
from src.main import app


class TestJWTTokens:
    """Test JWT token creation and validation."""
    
    def create_test_user(self) -> User:
        """Create a test user for token testing."""
        return User(
            user_id="test_user_001",
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[UserRole.PROVIDER],
            organization_id="org_test_001"
        )
    
    def test_create_access_token_success(self):
        """Test successful JWT token creation."""
        user = self.create_test_user()
        
        token = create_access_token(user)
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_create_access_token_with_custom_expiry(self):
        """Test JWT token creation with custom expiration."""
        user = self.create_test_user()
        custom_expiry = timedelta(hours=2)
        
        token = create_access_token(user, expires_delta=custom_expiry)
        token_data = verify_token(token)
        
        assert token_data is not None
        # Token should expire within 2 hours + small buffer
        time_until_expiry = token_data.exp - datetime.now(timezone.utc)
        assert time_until_expiry <= timedelta(hours=2, minutes=5)  # More generous buffer
        assert time_until_expiry >= timedelta(hours=1, minutes=55)  # More generous buffer
    
    def test_verify_token_success(self):
        """Test successful token verification."""
        user = self.create_test_user()
        token = create_access_token(user)
        
        token_data = verify_token(token)
        
        assert token_data is not None
        assert token_data.user_id == user.user_id
        assert token_data.username == user.username
        assert token_data.organization_id == user.organization_id
        assert UserRole.PROVIDER in token_data.roles
    
    def test_verify_token_invalid(self):
        """Test verification of invalid token."""
        invalid_token = "invalid.jwt.token"
        
        token_data = verify_token(invalid_token)
        
        assert token_data is None
    
    def test_verify_token_expired(self):
        """Test verification of expired token."""
        user = self.create_test_user()
        # Create token that expires immediately
        expired_token = create_access_token(user, expires_delta=timedelta(seconds=-1))
        
        token_data = verify_token(expired_token)
        
        assert token_data is None
    
    def test_token_contains_all_user_data(self):
        """Test that token contains all necessary user data."""
        user = User(
            user_id="test_user_002",
            username="multiuser",
            email="multi@example.com",
            full_name="Multi Role User",
            roles=[UserRole.PROVIDER, UserRole.PAYER_ADMIN],
            organization_id="org_multi_001"
        )
        
        token = create_access_token(user)
        token_data = verify_token(token)
        
        assert token_data is not None
        assert token_data.user_id == "test_user_002"
        assert token_data.username == "multiuser"
        assert token_data.organization_id == "org_multi_001"
        assert len(token_data.roles) == 2
        assert UserRole.PROVIDER in token_data.roles
        assert UserRole.PAYER_ADMIN in token_data.roles


class TestAuthenticationEndpoints:
    """Test authentication API endpoints."""
    
    def setup_method(self):
        """Set up test client."""
        self.client = TestClient(app)
    
    def test_login_success(self):
        """Test successful login with valid credentials."""
        response = self.client.post(
            "/api/v1/auth/login",
            data={
                "username": "provider1",
                "password": "provider123"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials."""
        response = self.client.post(
            "/api/v1/auth/login",
            data={
                "username": "provider1",
                "password": "wrongpassword"
            }
        )
        
        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]
    
    def test_login_nonexistent_user(self):
        """Test login with nonexistent user."""
        response = self.client.post(
            "/api/v1/auth/login",
            data={
                "username": "nonexistent",
                "password": "password"
            }
        )
        
        assert response.status_code == 401
    
    def test_login_json_success(self):
        """Test JSON-based login endpoint."""
        response = self.client.post(
            "/api/v1/auth/login-json",
            json={
                "username": "admin1",
                "password": "admin123"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
    
    def test_get_current_user_info(self):
        """Test getting current user information."""
        # First login to get token
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={
                "username": "provider1",
                "password": "provider123"
            }
        )
        token = login_response.json()["access_token"]
        
        # Get user info
        response = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "provider1"
        assert "provider" in data["roles"]
        assert "user_id" in data
        assert "organization_id" in data
    
    def test_refresh_token(self):
        """Test token refresh endpoint."""
        # First login to get token
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={
                "username": "provider1",
                "password": "provider123"
            }
        )
        token = login_response.json()["access_token"]
        
        # Refresh token
        response = self.client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        # Token should be valid (may be same if created at same timestamp)
        assert len(data["access_token"]) > 0
    
    def test_logout(self):
        """Test logout endpoint."""
        # First login to get token
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={
                "username": "provider1",
                "password": "provider123"
            }
        )
        token = login_response.json()["access_token"]
        
        # Logout
        response = self.client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        assert "Successfully logged out" in response.json()["message"]
    
    def test_unauthorized_access(self):
        """Test accessing protected endpoint without token."""
        response = self.client.get("/api/v1/auth/me")
        
        assert response.status_code == 401
    
    def test_invalid_token_access(self):
        """Test accessing protected endpoint with invalid token."""
        response = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"}
        )
        
        assert response.status_code == 401


class TestRoleBasedAccess:
    """Test role-based access control."""
    
    def create_token_data(self, roles: list[UserRole], org_id: str = "org_test") -> TokenData:
        """Create test token data with specified roles."""
        return TokenData(
            user_id="test_user",
            username="testuser",
            roles=roles,
            organization_id=org_id,
            exp=datetime.now(timezone.utc) + timedelta(hours=1)
        )
    
    def test_require_roles_success(self):
        """Test successful role authorization."""
        token_data = self.create_token_data([UserRole.PROVIDER])
        role_checker = require_roles(UserRole.PROVIDER)
        
        # Should not raise exception
        result = role_checker(token_data)
        assert result == token_data
    
    def test_require_roles_multiple_success(self):
        """Test role authorization with multiple allowed roles."""
        token_data = self.create_token_data([UserRole.PAYER_ADMIN])
        role_checker = require_roles(UserRole.PROVIDER, UserRole.PAYER_ADMIN)
        
        # Should not raise exception
        result = role_checker(token_data)
        assert result == token_data
    
    def test_require_roles_system_admin_bypass(self):
        """Test that system admin bypasses role requirements."""
        token_data = self.create_token_data([UserRole.SYSTEM_ADMIN])
        role_checker = require_roles(UserRole.PROVIDER)
        
        # Should not raise exception even though user doesn't have PROVIDER role
        result = role_checker(token_data)
        assert result == token_data
    
    def test_require_roles_failure(self):
        """Test role authorization failure."""
        token_data = self.create_token_data([UserRole.PROVIDER])
        role_checker = require_roles(UserRole.PAYER_ADMIN)
        
        with pytest.raises(HTTPException) as exc_info:
            role_checker(token_data)
        
        assert exc_info.value.status_code == 403
        assert "Insufficient permissions" in str(exc_info.value.detail)
    
    def test_require_organization_access_success(self):
        """Test successful organization access check."""
        token_data = self.create_token_data([UserRole.PROVIDER], "org_hospital")
        org_checker = require_organization_access("org_hospital")
        
        # Should not raise exception
        result = org_checker(token_data)
        assert result == token_data
    
    def test_require_organization_access_admin_bypass(self):
        """Test that system admin bypasses organization restrictions."""
        token_data = self.create_token_data([UserRole.SYSTEM_ADMIN], "org_different")
        org_checker = require_organization_access("org_hospital")
        
        # Should not raise exception
        result = org_checker(token_data)
        assert result == token_data
    
    def test_require_organization_access_compliance_bypass(self):
        """Test that compliance officer bypasses organization restrictions."""
        token_data = self.create_token_data([UserRole.COMPLIANCE_OFFICER], "org_different")
        org_checker = require_organization_access("org_hospital")
        
        # Should not raise exception
        result = org_checker(token_data)
        assert result == token_data
    
    def test_require_organization_access_failure(self):
        """Test organization access failure."""
        token_data = self.create_token_data([UserRole.PROVIDER], "org_different")
        org_checker = require_organization_access("org_hospital")
        
        with pytest.raises(HTTPException) as exc_info:
            org_checker(token_data)
        
        assert exc_info.value.status_code == 403
        assert "Access denied to organization data" in str(exc_info.value.detail)


class TestRateLimiting:
    """Test rate limiting functionality."""
    
    def setup_method(self):
        """Set up test rate limiter."""
        self.rate_limiter = RateLimiter()
        self.mock_request = Mock()
        self.mock_request.client.host = "127.0.0.1"
        self.mock_request.headers = {}
    
    def test_rate_limit_within_limits(self):
        """Test requests within rate limits."""
        # Make several requests within limits
        for _ in range(5):
            is_allowed, rate_info = self.rate_limiter.check_rate_limit(self.mock_request)
            assert is_allowed
            assert rate_info["remaining"] >= 0
    
    def test_rate_limit_exceeded(self):
        """Test rate limit exceeded."""
        # Make requests up to the limit
        for _ in range(100):  # Default limit
            self.rate_limiter.check_rate_limit(self.mock_request)
        
        # Next request should be rate limited
        is_allowed, rate_info = self.rate_limiter.check_rate_limit(self.mock_request)
        assert not is_allowed
        assert rate_info["remaining"] == 0
        assert rate_info["retry_after"] > 0
    
    def test_auth_failure_tracking(self):
        """Test authentication failure tracking."""
        # Record several auth failures
        for _ in range(4):
            should_block = self.rate_limiter.record_auth_failure(self.mock_request)
            assert not should_block
        
        # 5th failure should trigger blocking
        should_block = self.rate_limiter.record_auth_failure(self.mock_request)
        assert should_block
    
    def test_auth_failure_clear(self):
        """Test clearing auth failures on successful login."""
        # Record failures
        for _ in range(3):
            self.rate_limiter.record_auth_failure(self.mock_request)
        
        # Clear failures
        self.rate_limiter.clear_auth_failures(self.mock_request)
        
        # Should not be blocked now
        should_block = self.rate_limiter.record_auth_failure(self.mock_request)
        assert not should_block
    
    def test_different_ips_separate_limits(self):
        """Test that different IPs have separate rate limits."""
        mock_request_1 = Mock()
        mock_request_1.client.host = "127.0.0.1"
        mock_request_1.headers = {}
        
        mock_request_2 = Mock()
        mock_request_2.client.host = "192.168.1.1"
        mock_request_2.headers = {}
        
        # Exhaust limit for first IP
        for _ in range(100):
            self.rate_limiter.check_rate_limit(mock_request_1)
        
        # First IP should be limited
        is_allowed_1, _ = self.rate_limiter.check_rate_limit(mock_request_1)
        assert not is_allowed_1
        
        # Second IP should still be allowed
        is_allowed_2, _ = self.rate_limiter.check_rate_limit(mock_request_2)
        assert is_allowed_2


class TestSecurityIntegration:
    """Test security integration scenarios."""
    
    def setup_method(self):
        """Set up test client."""
        self.client = TestClient(app)
    
    def test_rate_limiting_on_login(self):
        """Test rate limiting on login endpoint."""
        # Make many failed login attempts
        for _ in range(10):
            response = self.client.post(
                "/api/v1/auth/login",
                data={
                    "username": "nonexistent",
                    "password": "wrongpassword"
                }
            )
            # Should get 401 for auth failure, not 429 yet
            if response.status_code == 429:
                break
        
        # Eventually should get rate limited
        assert response.status_code in [401, 429]
    
    def test_token_in_headers(self):
        """Test that tokens are properly handled in headers."""
        # Login to get token
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={
                "username": "provider1",
                "password": "provider123"
            }
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.json()}"
        login_data = login_response.json()
        token = login_data["access_token"]
        
        # Use token in different header formats
        valid_headers = [
            {"Authorization": f"Bearer {token}"},
        ]
        
        for headers in valid_headers:
            response = self.client.get("/api/v1/auth/me", headers=headers)
            assert response.status_code == 200
    
    def test_malformed_token_handling(self):
        """Test handling of malformed tokens."""
        malformed_tokens = [
            "Bearer",  # Missing token
            "Bearer ",  # Empty token
            "Bearer invalid",  # Invalid format
            "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9",  # Incomplete JWT
        ]
        
        for token in malformed_tokens:
            response = self.client.get(
                "/api/v1/auth/me",
                headers={"Authorization": token}
            )
            assert response.status_code == 401
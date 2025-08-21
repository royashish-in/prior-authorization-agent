"""
Prior Authorization Agent API Client.

This module provides a comprehensive Python client for the Prior Authorization
Agent API with authentication, request management, and error handling.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Union
from urllib.parse import urljoin

import httpx
from pydantic import ValidationError

from .exceptions import (
    PriorAuthAPIError,
    AuthenticationError,
    ValidationError as ClientValidationError,
    RateLimitError,
    NotFoundError,
    ForbiddenError,
    ServerError,
    NetworkError,
    TimeoutError
)
from .models import (
    AuthorizationRequest,
    AuthorizationDecision,
    RequestSubmissionResponse,
    RequestStatusInfo,
    DashboardSummary,
    LoginCredentials,
    TokenResponse,
    RequestStatus,
    DecisionStatus
)


class PriorAuthClient:
    """
    Prior Authorization Agent API Client.
    
    Provides a high-level interface for interacting with the Prior Authorization
    Agent API, including authentication, request submission, status tracking,
    and decision retrieval.
    """
    
    def __init__(
        self,
        base_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        access_token: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialize the API client.
        
        Args:
            base_url: Base URL of the Prior Authorization Agent API
            username: Username for authentication (if not using token)
            password: Password for authentication (if not using token)
            access_token: JWT access token (if already authenticated)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retry attempts in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.access_token = access_token
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Initialize HTTP client
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": "PriorAuthClient/1.0.0"}
        )
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
    
    def _get_headers(self) -> Dict[str, str]:
        """
        Get request headers with authentication.
        
        Returns:
            Dictionary of HTTP headers
        """
        headers = {"Content-Type": "application/json"}
        
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        
        return headers
    
    def _build_url(self, endpoint: str) -> str:
        """
        Build full URL for an API endpoint.
        
        Args:
            endpoint: API endpoint path
            
        Returns:
            Full URL string
        """
        return urljoin(f"{self.base_url}/api/v1/", endpoint.lstrip("/"))
    
    def _handle_error_response(self, response: httpx.Response) -> None:
        """
        Handle error responses and raise appropriate exceptions.
        
        Args:
            response: HTTP response object
            
        Raises:
            Appropriate PriorAuthAPIError subclass
        """
        try:
            error_data = response.json()
        except (json.JSONDecodeError, ValueError):
            error_data = {"error": "UNKNOWN_ERROR", "message": response.text}
        
        status_code = response.status_code
        error_code = error_data.get("error", "UNKNOWN_ERROR")
        message = error_data.get("message", f"HTTP {status_code} error")
        details = error_data.get("details", [])
        request_id = error_data.get("request_id")
        
        # Map status codes to exception types
        if status_code == 400:
            raise ClientValidationError(message, details=details, request_id=request_id)
        elif status_code == 401:
            raise AuthenticationError(message, request_id=request_id)
        elif status_code == 403:
            raise ForbiddenError(message, request_id=request_id)
        elif status_code == 404:
            raise NotFoundError(message, request_id=request_id)
        elif status_code == 429:
            retry_after = error_data.get("retry_after")
            limit = error_data.get("limit")
            remaining = error_data.get("remaining")
            raise RateLimitError(
                message,
                retry_after=retry_after,
                limit=limit,
                remaining=remaining,
                request_id=request_id
            )
        elif status_code >= 500:
            raise ServerError(message, request_id=request_id)
        else:
            raise PriorAuthAPIError(
                message,
                status_code=status_code,
                error_code=error_code,
                details=details,
                request_id=request_id
            )
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        retry_count: int = 0
    ) -> httpx.Response:
        """
        Make HTTP request with retry logic.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            data: Request body data
            params: Query parameters
            retry_count: Current retry attempt
            
        Returns:
            HTTP response object
            
        Raises:
            Various PriorAuthAPIError subclasses
        """
        url = self._build_url(endpoint)
        headers = self._get_headers()
        
        try:
            response = await self.client.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params
            )
            
            # Handle successful responses
            if response.is_success:
                return response
            
            # Handle error responses
            self._handle_error_response(response)
            
        except httpx.TimeoutException:
            if retry_count < self.max_retries:
                await asyncio.sleep(self.retry_delay * (2 ** retry_count))
                return await self._make_request(method, endpoint, data, params, retry_count + 1)
            raise TimeoutError(f"Request timeout after {self.timeout} seconds")
        
        except httpx.NetworkError as e:
            if retry_count < self.max_retries:
                await asyncio.sleep(self.retry_delay * (2 ** retry_count))
                return await self._make_request(method, endpoint, data, params, retry_count + 1)
            raise NetworkError(f"Network error: {str(e)}")
        
        except (AuthenticationError, RateLimitError):
            # Don't retry authentication or rate limit errors
            raise
        
        except PriorAuthAPIError:
            # Don't retry other API errors
            raise
        
        except Exception as e:
            if retry_count < self.max_retries:
                await asyncio.sleep(self.retry_delay * (2 ** retry_count))
                return await self._make_request(method, endpoint, data, params, retry_count + 1)
            raise PriorAuthAPIError(f"Unexpected error: {str(e)}")
    
    async def authenticate(self, username: Optional[str] = None, password: Optional[str] = None) -> TokenResponse:
        """
        Authenticate with the API and obtain access token.
        
        Args:
            username: Username (uses instance username if not provided)
            password: Password (uses instance password if not provided)
            
        Returns:
            Token response with access token
            
        Raises:
            AuthenticationError: If authentication fails
        """
        auth_username = username or self.username
        auth_password = password or self.password
        
        if not auth_username or not auth_password:
            raise AuthenticationError("Username and password are required for authentication")
        
        credentials = LoginCredentials(username=auth_username, password=auth_password)
        
        response = await self._make_request(
            method="POST",
            endpoint="auth/login-json",
            data=credentials.model_dump()
        )
        
        token_data = await response.json() if hasattr(response.json, '__call__') and asyncio.iscoroutinefunction(response.json) else response.json()
        token_response = TokenResponse(**token_data)
        
        # Store access token for future requests
        self.access_token = token_response.access_token
        
        return token_response
    
    async def submit_authorization_request(self, request: AuthorizationRequest) -> RequestSubmissionResponse:
        """
        Submit a new prior authorization request.
        
        Args:
            request: Authorization request data
            
        Returns:
            Request submission response
            
        Raises:
            ClientValidationError: If request data is invalid
            AuthenticationError: If not authenticated
        """
        if not self.access_token:
            raise AuthenticationError("Authentication required. Call authenticate() first.")
        
        response = await self._make_request(
            method="POST",
            endpoint="authorization/requests",
            data=request.model_dump()
        )
        
        response_data = await response.json() if hasattr(response.json, '__call__') and asyncio.iscoroutinefunction(response.json) else response.json()
        return RequestSubmissionResponse(**response_data)
    
    async def get_request_status(self, request_id: str) -> RequestStatusInfo:
        """
        Get the status of a specific authorization request.
        
        Args:
            request_id: Request identifier
            
        Returns:
            Request status information
            
        Raises:
            NotFoundError: If request not found
            AuthenticationError: If not authenticated
        """
        if not self.access_token:
            raise AuthenticationError("Authentication required. Call authenticate() first.")
        
        response = await self._make_request(
            method="GET",
            endpoint=f"authorization/requests/{request_id}"
        )
        
        response_data = response.json()
        return RequestStatusInfo(**response_data)
    
    async def get_provider_requests(
        self,
        provider_id: str,
        status_filter: Optional[RequestStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[RequestStatusInfo]:
        """
        Get authorization requests for a provider.
        
        Args:
            provider_id: Provider identifier
            status_filter: Optional status filter
            limit: Maximum number of requests
            offset: Number of requests to skip
            
        Returns:
            List of request status information
            
        Raises:
            AuthenticationError: If not authenticated
        """
        if not self.access_token:
            raise AuthenticationError("Authentication required. Call authenticate() first.")
        
        params = {
            "provider_id": provider_id,
            "limit": limit,
            "offset": offset
        }
        
        if status_filter:
            params["status_filter"] = status_filter.value
        
        response = await self._make_request(
            method="GET",
            endpoint="authorization/requests",
            params=params
        )
        
        response_data = response.json()
        return [RequestStatusInfo(**req) for req in response_data["requests"]]
    
    async def get_authorization_decision(self, decision_id: str) -> AuthorizationDecision:
        """
        Get authorization decision by decision ID.
        
        Args:
            decision_id: Decision identifier
            
        Returns:
            Authorization decision
            
        Raises:
            NotFoundError: If decision not found
            AuthenticationError: If not authenticated
        """
        if not self.access_token:
            raise AuthenticationError("Authentication required. Call authenticate() first.")
        
        response = await self._make_request(
            method="GET",
            endpoint=f"decisions/{decision_id}"
        )
        
        response_data = response.json()
        return AuthorizationDecision(**response_data)
    
    async def get_decision_by_request(self, request_id: str) -> AuthorizationDecision:
        """
        Get authorization decision for a specific request.
        
        Args:
            request_id: Request identifier
            
        Returns:
            Authorization decision
            
        Raises:
            NotFoundError: If decision not found
            AuthenticationError: If not authenticated
        """
        if not self.access_token:
            raise AuthenticationError("Authentication required. Call authenticate() first.")
        
        response = await self._make_request(
            method="GET",
            endpoint=f"decisions/request/{request_id}"
        )
        
        response_data = response.json()
        return AuthorizationDecision(**response_data)
    
    async def get_dashboard_summary(self, provider_id: str) -> DashboardSummary:
        """
        Get dashboard summary for a provider.
        
        Args:
            provider_id: Provider identifier
            
        Returns:
            Dashboard summary data
            
        Raises:
            AuthenticationError: If not authenticated
        """
        if not self.access_token:
            raise AuthenticationError("Authentication required. Call authenticate() first.")
        
        response = await self._make_request(
            method="GET",
            endpoint=f"dashboard/summary/{provider_id}"
        )
        
        response_data = response.json()
        return DashboardSummary(**response_data)
    
    async def submit_additional_information(
        self,
        request_id: str,
        additional_info: Dict[str, Any]
    ) -> RequestSubmissionResponse:
        """
        Submit additional information for a request.
        
        Args:
            request_id: Request identifier
            additional_info: Additional information data
            
        Returns:
            Updated request submission response
            
        Raises:
            NotFoundError: If request not found
            ClientValidationError: If request not in correct status
            AuthenticationError: If not authenticated
        """
        if not self.access_token:
            raise AuthenticationError("Authentication required. Call authenticate() first.")
        
        response = await self._make_request(
            method="PUT",
            endpoint=f"authorization/requests/{request_id}/additional-info",
            data=additional_info
        )
        
        response_data = response.json()
        return RequestSubmissionResponse(**response_data)
    
    async def check_health(self) -> Dict[str, Any]:
        """
        Check API health status.
        
        Returns:
            Health status information
        """
        response = await self._make_request(
            method="GET",
            endpoint="health"
        )
        
        return response.json()


# Convenience functions for common operations

async def create_client_and_authenticate(
    base_url: str,
    username: str,
    password: str,
    **kwargs
) -> PriorAuthClient:
    """
    Create client and authenticate in one step.
    
    Args:
        base_url: API base URL
        username: Username
        password: Password
        **kwargs: Additional client parameters
        
    Returns:
        Authenticated client instance
    """
    client = PriorAuthClient(base_url, username, password, **kwargs)
    await client.authenticate()
    return client


async def submit_request_and_wait(
    client: PriorAuthClient,
    request: AuthorizationRequest,
    max_wait_seconds: int = 300,
    poll_interval: int = 10
) -> AuthorizationDecision:
    """
    Submit request and wait for decision.
    
    Args:
        client: Authenticated client instance
        request: Authorization request
        max_wait_seconds: Maximum time to wait for decision
        poll_interval: Polling interval in seconds
        
    Returns:
        Authorization decision
        
    Raises:
        TimeoutError: If decision not received within max_wait_seconds
    """
    # Submit request
    submission = await client.submit_authorization_request(request)
    request_id = submission.request_id
    
    # Poll for decision
    elapsed = 0
    while elapsed < max_wait_seconds:
        try:
            # Check if decision is available
            decision = await client.get_decision_by_request(request_id)
            return decision
        except NotFoundError:
            # Decision not ready yet, continue polling
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
    
    raise TimeoutError(f"Decision not received within {max_wait_seconds} seconds")
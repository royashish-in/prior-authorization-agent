"""
Audit middleware for Prior Authorization Agent.

This module provides FastAPI middleware for automatic audit logging
of all HTTP requests and responses with security monitoring.
"""

import json
import logging
import time
import uuid
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.auth.models import TokenData
from src.auth.oauth2 import verify_token
from .logger import get_audit_logger
from .models import AuditEventType, SecurityLevel

logger = logging.getLogger(__name__)


class AuditMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for comprehensive audit logging.
    
    Automatically logs all HTTP requests and responses with
    security monitoring and HIPAA compliance features.
    """
    
    def __init__(self, app, exclude_paths: Optional[list] = None):
        """
        Initialize audit middleware.
        
        Args:
            app: FastAPI application
            exclude_paths: List of paths to exclude from audit logging
        """
        super().__init__(app)
        self.audit_logger = get_audit_logger()
        self.exclude_paths = exclude_paths or ["/health", "/docs", "/redoc", "/openapi.json"]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process HTTP request and response with audit logging.
        
        Args:
            request: HTTP request
            call_next: Next middleware in chain
            
        Returns:
            HTTP response
        """
        # Generate request ID for tracking
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Skip audit logging for excluded paths
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)
        
        # Extract request information
        start_time = time.time()
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        
        # Extract user information from token
        user_info = await self._extract_user_info(request)
        
        # Determine if this is a PHI-related endpoint
        phi_involved = self._is_phi_endpoint(request.url.path)
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Determine outcome
            outcome = "success" if response.status_code < 400 else "failure"
            
            # Determine security level
            security_level = self._determine_security_level(
                request.url.path,
                request.method,
                response.status_code,
                phi_involved
            )
            
            # Log audit event
            self._log_request_event(
                request=request,
                response=response,
                request_id=request_id,
                client_ip=client_ip,
                user_agent=user_agent,
                user_info=user_info,
                duration_ms=duration_ms,
                outcome=outcome,
                security_level=security_level,
                phi_involved=phi_involved
            )
            
            # Log security events if needed
            await self._check_security_events(request, response, client_ip, user_info)
            
            return response
            
        except Exception as e:
            # Calculate duration for failed requests
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Log error event
            self._log_error_event(
                request=request,
                request_id=request_id,
                client_ip=client_ip,
                user_agent=user_agent,
                user_info=user_info,
                duration_ms=duration_ms,
                error=str(e),
                phi_involved=phi_involved
            )
            
            raise
    
    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP address from request.
        
        Args:
            request: HTTP request
            
        Returns:
            Client IP address
        """
        # Check for forwarded headers (behind proxy)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fallback to direct connection
        return request.client.host if request.client else "unknown"
    
    async def _extract_user_info(self, request: Request) -> Optional[TokenData]:
        """
        Extract user information from JWT token.
        
        Args:
            request: HTTP request
            
        Returns:
            TokenData if authenticated, None otherwise
        """
        try:
            auth_header = request.headers.get("authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return None
            
            token = auth_header.split(" ")[1]
            return verify_token(token)
            
        except Exception:
            return None
    
    def _is_phi_endpoint(self, path: str) -> bool:
        """
        Determine if endpoint involves PHI data.
        
        Args:
            path: Request path
            
        Returns:
            True if PHI is involved, False otherwise
        """
        phi_patterns = [
            "/authorization/requests",
            "/authorization/decisions",
            "/patients",
            "/medical-records"
        ]
        
        return any(pattern in path for pattern in phi_patterns)
    
    def _determine_security_level(
        self,
        path: str,
        method: str,
        status_code: int,
        phi_involved: bool
    ) -> SecurityLevel:
        """
        Determine security level for the request.
        
        Args:
            path: Request path
            method: HTTP method
            status_code: Response status code
            phi_involved: Whether PHI is involved
            
        Returns:
            Security level
        """
        # Critical for PHI modifications
        if phi_involved and method in ["POST", "PUT", "DELETE"]:
            return SecurityLevel.CRITICAL
        
        # High for PHI access
        if phi_involved:
            return SecurityLevel.HIGH
        
        # High for authentication failures
        if status_code == 401:
            return SecurityLevel.HIGH
        
        # Medium for authorization failures
        if status_code == 403:
            return SecurityLevel.MEDIUM
        
        # Medium for server errors
        if status_code >= 500:
            return SecurityLevel.MEDIUM
        
        # Low for normal operations
        return SecurityLevel.LOW
    
    def _log_request_event(
        self,
        request: Request,
        response: Response,
        request_id: str,
        client_ip: str,
        user_agent: str,
        user_info: Optional[TokenData],
        duration_ms: int,
        outcome: str,
        security_level: SecurityLevel,
        phi_involved: bool
    ) -> None:
        """
        Log HTTP request audit event.
        
        Args:
            request: HTTP request
            response: HTTP response
            request_id: Request identifier
            client_ip: Client IP address
            user_agent: User agent string
            user_info: User information from token
            duration_ms: Request duration in milliseconds
            outcome: Request outcome
            security_level: Security level
            phi_involved: Whether PHI is involved
        """
        try:
            # Determine event type based on endpoint
            event_type = self._get_event_type(request.url.path, request.method)
            
            # Prepare additional details
            details = {
                "status_code": response.status_code,
                "response_size": len(response.body) if hasattr(response, 'body') else 0,
                "query_params": dict(request.query_params) if request.query_params else None
            }
            
            # Log the event
            self.audit_logger.log_event(
                event_type=event_type,
                action=f"{request.method} {request.url.path}",
                outcome=outcome,
                user_id=user_info.user_id if user_info else None,
                username=user_info.username if user_info else None,
                client_ip=client_ip,
                user_agent=user_agent,
                request_id=request_id,
                endpoint=request.url.path,
                http_method=request.method,
                session_id=getattr(request.state, 'session_id', None),
                organization_id=user_info.organization_id if user_info else None,
                security_level=security_level,
                phi_involved=phi_involved,
                duration_ms=duration_ms,
                details=details,
                compliance_flags=["HIPAA"] if phi_involved else []
            )
            
        except Exception as e:
            logger.error(f"Failed to log request audit event: {e}")
    
    def _log_error_event(
        self,
        request: Request,
        request_id: str,
        client_ip: str,
        user_agent: str,
        user_info: Optional[TokenData],
        duration_ms: int,
        error: str,
        phi_involved: bool
    ) -> None:
        """
        Log error audit event.
        
        Args:
            request: HTTP request
            request_id: Request identifier
            client_ip: Client IP address
            user_agent: User agent string
            user_info: User information from token
            duration_ms: Request duration in milliseconds
            error: Error message
            phi_involved: Whether PHI is involved
        """
        try:
            self.audit_logger.log_event(
                event_type=AuditEventType.ERROR_OCCURRED,
                action=f"{request.method} {request.url.path}",
                outcome="error",
                user_id=user_info.user_id if user_info else None,
                username=user_info.username if user_info else None,
                client_ip=client_ip,
                user_agent=user_agent,
                request_id=request_id,
                endpoint=request.url.path,
                http_method=request.method,
                organization_id=user_info.organization_id if user_info else None,
                security_level=SecurityLevel.MEDIUM,
                phi_involved=phi_involved,
                duration_ms=duration_ms,
                error_message=error,
                compliance_flags=["HIPAA"] if phi_involved else []
            )
            
        except Exception as e:
            logger.error(f"Failed to log error audit event: {e}")
    
    def _get_event_type(self, path: str, method: str) -> AuditEventType:
        """
        Determine audit event type based on endpoint and method.
        
        Args:
            path: Request path
            method: HTTP method
            
        Returns:
            Appropriate audit event type
        """
        # Authentication endpoints
        if "/auth/" in path:
            if "login" in path:
                return AuditEventType.USER_LOGIN
            elif "logout" in path:
                return AuditEventType.USER_LOGOUT
            elif "refresh" in path:
                return AuditEventType.TOKEN_REFRESH
        
        # Authorization request endpoints
        if "/authorization/requests" in path:
            if method == "POST":
                return AuditEventType.REQUEST_SUBMITTED
            elif method == "GET":
                return AuditEventType.REQUEST_VIEWED
            elif method in ["PUT", "PATCH"]:
                return AuditEventType.REQUEST_UPDATED
        
        # Decision endpoints
        if "/authorization/decisions" in path:
            if method == "POST":
                return AuditEventType.DECISION_GENERATED
            elif method == "GET":
                return AuditEventType.DECISION_VIEWED
        
        # PHI data endpoints
        if any(pattern in path for pattern in ["/patients", "/medical-records"]):
            if method == "POST":
                return AuditEventType.PHI_CREATE
            elif method == "GET":
                return AuditEventType.PHI_ACCESS
            elif method in ["PUT", "PATCH"]:
                return AuditEventType.PHI_UPDATE
            elif method == "DELETE":
                return AuditEventType.PHI_DELETE
        
        # Policy endpoints
        if "/policies" in path:
            if method == "POST":
                return AuditEventType.POLICY_CREATED
            elif method in ["PUT", "PATCH"]:
                return AuditEventType.POLICY_UPDATED
            elif method == "DELETE":
                return AuditEventType.POLICY_DELETED
        
        # Default to PHI access for any data access
        return AuditEventType.PHI_ACCESS
    
    async def _check_security_events(
        self,
        request: Request,
        response: Response,
        client_ip: str,
        user_info: Optional[TokenData]
    ) -> None:
        """
        Check for security events and log them.
        
        Args:
            request: HTTP request
            response: HTTP response
            client_ip: Client IP address
            user_info: User information from token
        """
        try:
            # Check for authentication failures
            if response.status_code == 401:
                self.audit_logger.log_security_event(
                    threat_type="authentication_failure",
                    severity=SecurityLevel.MEDIUM,
                    confidence=0.8,
                    source_ip=client_ip,
                    attack_vector="invalid_credentials",
                    target_resource=request.url.path,
                    user_id=user_info.user_id if user_info else None
                )
            
            # Check for authorization failures
            elif response.status_code == 403:
                self.audit_logger.log_security_event(
                    threat_type="authorization_failure",
                    severity=SecurityLevel.MEDIUM,
                    confidence=0.9,
                    source_ip=client_ip,
                    attack_vector="insufficient_privileges",
                    target_resource=request.url.path,
                    user_id=user_info.user_id if user_info else None
                )
            
            # Check for suspicious patterns
            elif self._is_suspicious_request(request, response):
                self.audit_logger.log_security_event(
                    threat_type="suspicious_activity",
                    severity=SecurityLevel.LOW,
                    confidence=0.6,
                    source_ip=client_ip,
                    attack_vector="anomalous_behavior",
                    target_resource=request.url.path,
                    user_id=user_info.user_id if user_info else None
                )
                
        except Exception as e:
            logger.error(f"Failed to check security events: {e}")
    
    def _is_suspicious_request(self, request: Request, response: Response) -> bool:
        """
        Check if request shows suspicious patterns.
        
        Args:
            request: HTTP request
            response: HTTP response
            
        Returns:
            True if suspicious, False otherwise
        """
        # Check for common attack patterns
        suspicious_patterns = [
            "script",
            "javascript:",
            "<script",
            "union select",
            "drop table",
            "../",
            "etc/passwd"
        ]
        
        # Check URL and query parameters
        full_url = str(request.url).lower()
        if any(pattern in full_url for pattern in suspicious_patterns):
            return True
        
        # Check user agent for known bad patterns
        user_agent = request.headers.get("user-agent", "").lower()
        bad_agents = ["sqlmap", "nikto", "nmap", "masscan"]
        if any(agent in user_agent for agent in bad_agents):
            return True
        
        return False
"""
Tests for audit logging functionality.

This module tests HIPAA-compliant audit logging, security event
monitoring, and comprehensive system activity tracking.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

from src.audit.models import (
    AuditEvent, 
    AuditEventType, 
    SecurityEvent, 
    SecurityLevel,
    AuditQuery
)
from src.audit.logger import AuditLogger, get_audit_logger
from src.audit.middleware import AuditMiddleware
from src.main import app


class TestAuditModels:
    """Test audit data models."""
    
    def test_audit_event_creation(self):
        """Test creating a valid audit event."""
        event = AuditEvent(
            event_id="evt_001",
            event_type=AuditEventType.USER_LOGIN,
            action="authenticate",
            outcome="success",
            client_ip="192.168.1.100",
            user_id="user_001",
            username="testuser",
            phi_involved=False,
            security_level=SecurityLevel.LOW
        )
        
        assert event.event_id == "evt_001"
        assert event.event_type == AuditEventType.USER_LOGIN
        assert event.action == "authenticate"
        assert event.outcome == "success"
        assert event.client_ip == "192.168.1.100"
        assert event.user_id == "user_001"
        assert event.username == "testuser"
        assert not event.phi_involved
        assert event.security_level == SecurityLevel.LOW
        assert isinstance(event.timestamp, datetime)
    
    def test_phi_audit_event(self):
        """Test PHI-related audit event."""
        event = AuditEvent(
            event_id="evt_002",
            event_type=AuditEventType.PHI_ACCESS,
            action="view_patient_record",
            outcome="success",
            client_ip="10.0.0.50",
            user_id="provider_001",
            username="dr.smith",
            resource_type="patient_record",
            resource_id="patient_12345",
            phi_involved=True,
            security_level=SecurityLevel.HIGH,
            compliance_flags=["HIPAA"]
        )
        
        assert event.event_type == AuditEventType.PHI_ACCESS
        assert event.phi_involved
        assert event.security_level == SecurityLevel.HIGH
        assert "HIPAA" in event.compliance_flags
        assert event.resource_type == "patient_record"
        assert event.resource_id == "patient_12345"
    
    def test_security_event_creation(self):
        """Test creating a security event."""
        security_event = SecurityEvent(
            event_id="sec_001",
            threat_type="brute_force",
            severity=SecurityLevel.HIGH,
            confidence=0.95,
            source_ip="203.0.113.1",
            attack_vector="password_guessing",
            target_resource="/api/v1/auth/login",
            blocked=True,
            response_action="ip_blocked"
        )
        
        assert security_event.event_id == "sec_001"
        assert security_event.threat_type == "brute_force"
        assert security_event.severity == SecurityLevel.HIGH
        assert security_event.confidence == 0.95
        assert security_event.source_ip == "203.0.113.1"
        assert security_event.attack_vector == "password_guessing"
        assert security_event.blocked
        assert security_event.response_action == "ip_blocked"
    
    def test_audit_query_model(self):
        """Test audit query model for filtering."""
        start_time = datetime.now(timezone.utc) - timedelta(days=1)
        end_time = datetime.now(timezone.utc)
        
        query = AuditQuery(
            start_time=start_time,
            end_time=end_time,
            event_types=[AuditEventType.PHI_ACCESS, AuditEventType.USER_LOGIN],
            user_ids=["user_001", "user_002"],
            phi_only=True,
            limit=50
        )
        
        assert query.start_time == start_time
        assert query.end_time == end_time
        assert AuditEventType.PHI_ACCESS in query.event_types
        assert AuditEventType.USER_LOGIN in query.event_types
        assert "user_001" in query.user_ids
        assert query.phi_only
        assert query.limit == 50


class TestAuditLogger:
    """Test audit logger functionality."""
    
    def setup_method(self):
        """Set up test audit logger with mocked database."""
        self.mock_engine = Mock()
        self.mock_connection = Mock()
        
        # Set up context manager for connection
        self.mock_engine.connect.return_value = MagicMock()
        self.mock_engine.connect.return_value.__enter__.return_value = self.mock_connection
        self.mock_engine.connect.return_value.__exit__.return_value = None
        
        with patch('src.audit.logger.create_engine', return_value=self.mock_engine):
            self.audit_logger = AuditLogger()
    
    def test_log_event_success(self):
        """Test successful event logging."""
        event_id = self.audit_logger.log_event(
            event_type=AuditEventType.USER_LOGIN,
            action="authenticate",
            outcome="success",
            user_id="user_001",
            username="testuser",
            client_ip="192.168.1.100"
        )
        
        assert event_id is not None
        assert len(event_id) == 36  # UUID format
        
        # Verify database insert was called
        self.mock_connection.execute.assert_called()
        self.mock_connection.commit.assert_called()
    
    def test_log_phi_access(self):
        """Test PHI access logging."""
        event_id = self.audit_logger.log_phi_access(
            user_id="provider_001",
            username="dr.smith",
            resource_type="patient_record",
            resource_id="patient_12345",
            action="view_record",
            client_ip="10.0.0.50"
        )
        
        assert event_id is not None
        
        # Verify the call included PHI-specific parameters
        call_args = self.mock_connection.execute.call_args
        assert call_args is not None
        
        # Check that PHI involvement was recorded
        params = call_args[0][1]  # Second argument contains parameters
        assert params["phi_involved"] is True
        assert params["security_level"] == SecurityLevel.HIGH.value
    
    def test_log_authentication_success(self):
        """Test authentication event logging."""
        event_id = self.audit_logger.log_authentication(
            username="testuser",
            outcome="success",
            client_ip="192.168.1.100",
            user_agent="Mozilla/5.0"
        )
        
        assert event_id is not None
        
        # Verify correct event type was used
        call_args = self.mock_connection.execute.call_args
        params = call_args[0][1]
        assert params["event_type"] == AuditEventType.USER_LOGIN.value
    
    def test_log_authentication_failure(self):
        """Test authentication failure logging."""
        event_id = self.audit_logger.log_authentication(
            username="testuser",
            outcome="failure",
            client_ip="192.168.1.100",
            user_agent="Mozilla/5.0"
        )
        
        assert event_id is not None
        
        # Verify correct event type and security level
        call_args = self.mock_connection.execute.call_args
        params = call_args[0][1]
        assert params["event_type"] == AuditEventType.AUTH_FAILURE.value
        assert params["security_level"] == SecurityLevel.MEDIUM.value
    
    def test_log_security_event(self):
        """Test security event logging."""
        event_id = self.audit_logger.log_security_event(
            threat_type="brute_force",
            severity=SecurityLevel.HIGH,
            confidence=0.95,
            source_ip="203.0.113.1",
            attack_vector="password_guessing",
            blocked=True
        )
        
        assert event_id is not None
        
        # Verify security event was logged to security_events table
        # Should have two execute calls: one for security_events, one for audit_events
        assert self.mock_connection.execute.call_count >= 2
    
    def test_get_events_with_filters(self):
        """Test retrieving events with filters."""
        # Mock database result
        mock_row = Mock()
        mock_row.event_id = "evt_001"
        mock_row.event_type = "user_login"
        mock_row.timestamp = datetime.now(timezone.utc)
        mock_row.user_id = "user_001"
        mock_row.username = "testuser"
        mock_row.client_ip = "192.168.1.100"
        mock_row.action = "authenticate"
        mock_row.outcome = "success"
        mock_row.security_level = "low"
        mock_row.phi_involved = False
        mock_row.resource_type = None
        mock_row.resource_id = None
        mock_row.error_message = None
        mock_row.duration_ms = 150
        
        self.mock_connection.execute.return_value = [mock_row]
        
        events = self.audit_logger.get_events(
            event_types=[AuditEventType.USER_LOGIN],
            user_id="user_001",
            limit=10
        )
        
        assert len(events) == 1
        assert events[0]["event_id"] == "evt_001"
        assert events[0]["event_type"] == "user_login"
        assert events[0]["user_id"] == "user_001"
        assert events[0]["outcome"] == "success"
    
    @patch('src.audit.logger.logger')
    def test_log_event_database_error(self, mock_logger):
        """Test handling of database errors during logging."""
        # Make database connection raise an exception
        self.mock_connection.execute.side_effect = Exception("Database error")
        
        with pytest.raises(Exception):
            self.audit_logger.log_event(
                event_type=AuditEventType.USER_LOGIN,
                action="authenticate",
                outcome="success",
                client_ip="192.168.1.100"
            )
        
        # Verify error was logged
        mock_logger.error.assert_called()


class TestAuditMiddleware:
    """Test audit middleware functionality."""
    
    def setup_method(self):
        """Set up test client with audit middleware."""
        self.client = TestClient(app)
    
    @patch('src.audit.middleware.get_audit_logger')
    def test_middleware_logs_requests(self, mock_get_audit_logger):
        """Test that middleware logs HTTP requests."""
        mock_audit_logger = Mock()
        mock_get_audit_logger.return_value = mock_audit_logger
        
        # Make a request
        response = self.client.get("/api/v1/health")
        
        # Verify audit logging was called
        mock_audit_logger.log_event.assert_called()
        
        # Check the logged event details
        call_args = mock_audit_logger.log_event.call_args
        assert call_args[1]["action"] == "GET /api/v1/health"
        assert call_args[1]["outcome"] == "success"
    
    @patch('src.audit.middleware.get_audit_logger')
    def test_middleware_logs_authentication(self, mock_get_audit_logger):
        """Test that middleware logs authentication requests."""
        mock_audit_logger = Mock()
        mock_get_audit_logger.return_value = mock_audit_logger
        
        # Make login request
        response = self.client.post(
            "/api/v1/auth/login",
            data={"username": "provider1", "password": "provider123"}
        )
        
        # Verify audit logging was called
        mock_audit_logger.log_event.assert_called()
        
        # Check that it's logged as a login event
        call_args = mock_audit_logger.log_event.call_args
        assert "login" in call_args[1]["action"].lower()
    
    @patch('src.audit.middleware.get_audit_logger')
    def test_middleware_detects_phi_endpoints(self, mock_get_audit_logger):
        """Test that middleware detects PHI-related endpoints."""
        mock_audit_logger = Mock()
        mock_get_audit_logger.return_value = mock_audit_logger
        
        # Make request to PHI endpoint
        response = self.client.get("/api/v1/authorization/requests/123")
        
        # Verify PHI involvement was detected
        mock_audit_logger.log_event.assert_called()
        call_args = mock_audit_logger.log_event.call_args
        assert call_args[1]["phi_involved"] is True
    
    @patch('src.audit.middleware.get_audit_logger')
    def test_middleware_logs_security_events(self, mock_get_audit_logger):
        """Test that middleware logs security events for failures."""
        mock_audit_logger = Mock()
        mock_get_audit_logger.return_value = mock_audit_logger
        
        # Make request that will result in 401
        response = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid_token"}
        )
        
        # Verify security event was logged
        mock_audit_logger.log_security_event.assert_called()
        
        # Check security event details
        call_args = mock_audit_logger.log_security_event.call_args
        assert call_args[1]["threat_type"] == "authentication_failure"
        assert call_args[1]["severity"] == SecurityLevel.MEDIUM
    
    @patch('src.audit.middleware.get_audit_logger')
    def test_middleware_excludes_health_checks(self, mock_get_audit_logger):
        """Test that middleware excludes health check endpoints."""
        mock_audit_logger = Mock()
        mock_get_audit_logger.return_value = mock_audit_logger
        
        # Make request to health endpoint
        response = self.client.get("/health")
        
        # Verify audit logging was NOT called
        mock_audit_logger.log_event.assert_not_called()
    
    @patch('src.audit.middleware.get_audit_logger')
    def test_middleware_handles_errors(self, mock_get_audit_logger):
        """Test that middleware handles and logs errors."""
        mock_audit_logger = Mock()
        mock_get_audit_logger.return_value = mock_audit_logger
        
        # Make request to non-existent endpoint
        response = self.client.get("/api/v1/nonexistent")
        
        # Should still log the request even if it results in 404
        mock_audit_logger.log_event.assert_called()
        
        call_args = mock_audit_logger.log_event.call_args
        assert call_args[1]["outcome"] == "failure"


class TestAuditIntegration:
    """Test audit system integration scenarios."""
    
    def setup_method(self):
        """Set up test client."""
        self.client = TestClient(app)
    
    @patch('src.audit.logger.AuditLogger._create_audit_tables')
    @patch('src.audit.logger.create_engine')
    def test_audit_logger_initialization(self, mock_create_engine, mock_create_tables):
        """Test audit logger initialization."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        # Initialize audit logger
        audit_logger = AuditLogger()
        
        # Verify database setup was called
        mock_create_engine.assert_called()
        mock_create_tables.assert_called()
    
    def test_get_audit_logger_singleton(self):
        """Test that get_audit_logger returns singleton instance."""
        logger1 = get_audit_logger()
        logger2 = get_audit_logger()
        
        assert logger1 is logger2
    
    @patch('src.audit.middleware.get_audit_logger')
    def test_full_request_audit_flow(self, mock_get_audit_logger):
        """Test complete audit flow for authenticated request."""
        mock_audit_logger = Mock()
        mock_get_audit_logger.return_value = mock_audit_logger
        
        # First login to get token
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={"username": "provider1", "password": "provider123"}
        )
        token = login_response.json()["access_token"]
        
        # Make authenticated request
        response = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Verify multiple audit events were logged
        assert mock_audit_logger.log_event.call_count >= 2  # Login + auth/me requests
        
        # Check that user information was captured in the second request
        calls = mock_audit_logger.log_event.call_args_list
        auth_me_call = calls[-1]  # Last call should be for /auth/me
        
        assert auth_me_call[1]["user_id"] is not None
        assert auth_me_call[1]["username"] is not None
    
    @patch('src.audit.middleware.get_audit_logger')
    def test_phi_access_audit_compliance(self, mock_get_audit_logger):
        """Test HIPAA compliance for PHI access auditing."""
        mock_audit_logger = Mock()
        mock_get_audit_logger.return_value = mock_audit_logger
        
        # Login first
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={"username": "provider1", "password": "provider123"}
        )
        token = login_response.json()["access_token"]
        
        # Access PHI endpoint
        response = self.client.get(
            "/api/v1/authorization/requests",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Verify PHI access was properly audited
        mock_audit_logger.log_event.assert_called()
        
        # Find the PHI access call
        phi_call = None
        for call in mock_audit_logger.log_event.call_args_list:
            if call[1].get("phi_involved"):
                phi_call = call
                break
        
        assert phi_call is not None
        assert phi_call[1]["phi_involved"] is True
        assert phi_call[1]["security_level"] in [SecurityLevel.HIGH, SecurityLevel.CRITICAL]
        assert "HIPAA" in phi_call[1].get("compliance_flags", [])
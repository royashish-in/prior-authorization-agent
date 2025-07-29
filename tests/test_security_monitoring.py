"""
Tests for the security monitoring and incident response system.

This module tests security event monitoring, automated incident response,
and anomaly detection functionality.
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, AsyncMock

from src.services.security_monitoring import (
    SecurityMonitoringService, SecurityEvent, SecurityIncident,
    SecurityEventType, IncidentSeverity, IncidentStatus,
    AnomalyPattern, ThreatIntelligence,
    security_monitoring_service
)


class TestSecurityMonitoringService:
    """Test cases for SecurityMonitoringService class."""
    
    @pytest.fixture
    def security_service(self):
        """Create a fresh security monitoring service for testing."""
        service = SecurityMonitoringService()
        service.security_events.clear()
        service.incidents.clear()
        service.event_index.clear()
        service.failed_login_attempts.clear()
        service.request_patterns.clear()
        service.user_activity.clear()
        service.ip_activity.clear()
        service.threat_indicators.clear()
        service.blocked_ips.clear()
        return service
    
    def test_record_security_event(self, security_service):
        """Test security event recording."""
        event_id = security_service.record_security_event(
            SecurityEventType.FAILED_LOGIN,
            source_ip="192.168.1.100",
            user_id="test_user",
            resource="/login",
            details={"attempt_count": 1}
        )
        
        assert event_id.startswith("evt_")
        assert len(security_service.security_events) == 1
        assert event_id in security_service.event_index
        
        event = security_service.event_index[event_id]
        assert event.event_type == SecurityEventType.FAILED_LOGIN
        assert event.source_ip == "192.168.1.100"
        assert event.user_id == "test_user"
        assert event.resource == "/login"
        assert event.details["attempt_count"] == 1
        assert event.risk_score > 0
        assert event.severity in [IncidentSeverity.LOW, IncidentSeverity.MEDIUM, 
                                 IncidentSeverity.HIGH, IncidentSeverity.CRITICAL]
    
    def test_create_incident(self, security_service):
        """Test incident creation."""
        # First create some events
        event_id1 = security_service.record_security_event(
            SecurityEventType.UNAUTHORIZED_ACCESS,
            source_ip="192.168.1.100",
            user_id="test_user"
        )
        
        event_id2 = security_service.record_security_event(
            SecurityEventType.UNAUTHORIZED_ACCESS,
            source_ip="192.168.1.100",
            user_id="test_user"
        )
        
        # Create incident
        incident_id = security_service.create_incident(
            title="Multiple unauthorized access attempts",
            description="User attempting unauthorized access",
            severity=IncidentSeverity.HIGH,
            event_ids=[event_id1, event_id2],
            assigned_to="security_team"
        )
        
        assert incident_id.startswith("inc_")
        assert incident_id in security_service.incidents
        
        incident = security_service.incidents[incident_id]
        assert incident.title == "Multiple unauthorized access attempts"
        assert incident.severity == IncidentSeverity.HIGH
        assert incident.status == IncidentStatus.OPEN
        assert incident.assigned_to == "security_team"
        assert len(incident.events) == 2
        assert event_id1 in incident.events
        assert event_id2 in incident.events
        assert len(incident.indicators_of_compromise) > 0
    
    def test_update_incident_status(self, security_service):
        """Test incident status updates."""
        incident_id = security_service.create_incident(
            title="Test incident",
            description="Test description",
            severity=IncidentSeverity.MEDIUM
        )
        
        # Update to investigating
        success = security_service.update_incident_status(
            incident_id,
            IncidentStatus.INVESTIGATING,
            notes="Started investigation",
            assigned_to="analyst1"
        )
        
        assert success is True
        incident = security_service.incidents[incident_id]
        assert incident.status == IncidentStatus.INVESTIGATING
        assert incident.assigned_to == "analyst1"
        assert len(incident.response_actions) == 1
        assert "Started investigation" in incident.response_actions[0]
        
        # Close incident
        success = security_service.update_incident_status(
            incident_id,
            IncidentStatus.CLOSED,
            notes="Issue resolved"
        )
        
        assert success is True
        incident = security_service.incidents[incident_id]
        assert incident.status == IncidentStatus.CLOSED
        assert incident.closed_at is not None
        assert incident.resolution_notes == "Issue resolved"
    
    def test_get_security_events_filtering(self, security_service):
        """Test security event retrieval with filtering."""
        # Create events with different types and severities
        security_service.record_security_event(
            SecurityEventType.FAILED_LOGIN,
            source_ip="192.168.1.100"
        )
        
        security_service.record_security_event(
            SecurityEventType.UNAUTHORIZED_ACCESS,
            source_ip="192.168.1.101"
        )
        
        security_service.record_security_event(
            SecurityEventType.DATA_BREACH,
            source_ip="192.168.1.102"
        )
        
        # Get all events
        all_events = security_service.get_security_events(hours=24)
        assert len(all_events) == 3
        
        # Filter by event type
        failed_login_events = security_service.get_security_events(
            hours=24,
            event_type=SecurityEventType.FAILED_LOGIN
        )
        assert len(failed_login_events) == 1
        assert failed_login_events[0].event_type == SecurityEventType.FAILED_LOGIN
        
        # Filter by severity
        critical_events = security_service.get_security_events(
            hours=24,
            severity=IncidentSeverity.CRITICAL
        )
        # DATA_BREACH should be critical
        assert len(critical_events) >= 1
    
    def test_get_incidents_filtering(self, security_service):
        """Test incident retrieval with filtering."""
        # Create incidents with different statuses and severities
        incident1_id = security_service.create_incident(
            "High severity incident",
            "Description 1",
            IncidentSeverity.HIGH
        )
        
        incident2_id = security_service.create_incident(
            "Medium severity incident",
            "Description 2",
            IncidentSeverity.MEDIUM
        )
        
        # Close one incident
        security_service.update_incident_status(
            incident2_id,
            IncidentStatus.CLOSED
        )
        
        # Get all incidents
        all_incidents = security_service.get_incidents()
        assert len(all_incidents) == 2
        
        # Filter by status
        open_incidents = security_service.get_incidents(status=IncidentStatus.OPEN)
        assert len(open_incidents) == 1
        assert open_incidents[0].incident_id == incident1_id
        
        closed_incidents = security_service.get_incidents(status=IncidentStatus.CLOSED)
        assert len(closed_incidents) == 1
        assert closed_incidents[0].incident_id == incident2_id
        
        # Filter by severity
        high_incidents = security_service.get_incidents(severity=IncidentSeverity.HIGH)
        assert len(high_incidents) == 1
        assert high_incidents[0].severity == IncidentSeverity.HIGH
    
    def test_threat_intelligence_management(self, security_service):
        """Test threat intelligence indicator management."""
        # Add threat indicator
        security_service.add_threat_indicator(
            indicator="192.168.1.100",
            indicator_type="ip",
            threat_type="malware",
            confidence=0.8,
            source="internal_analysis",
            description="Known malware C&C server"
        )
        
        assert "192.168.1.100" in security_service.threat_indicators
        
        threat = security_service.threat_indicators["192.168.1.100"]
        assert threat.indicator_type == "ip"
        assert threat.threat_type == "malware"
        assert threat.confidence == 0.8
        assert threat.source == "internal_analysis"
        
        # Check threat indicators
        matches = security_service.check_threat_indicators(ip="192.168.1.100")
        assert len(matches) == 1
        assert matches[0].indicator == "192.168.1.100"
        
        # Check non-matching indicator
        no_matches = security_service.check_threat_indicators(ip="192.168.1.200")
        assert len(no_matches) == 0
    
    def test_ip_blocking(self, security_service):
        """Test IP blocking functionality."""
        ip = "192.168.1.100"
        
        # Initially not blocked
        assert not security_service.is_ip_blocked(ip)
        
        # Block IP
        security_service.block_ip(ip, "Malicious activity", 24)
        
        # Should now be blocked
        assert security_service.is_ip_blocked(ip)
        assert ip in security_service.blocked_ips
        
        # Should have created a security event
        events = security_service.get_security_events(hours=1)
        block_events = [e for e in events if e.details.get("action") == "ip_blocked"]
        assert len(block_events) == 1
        assert block_events[0].source_ip == ip
    
    def test_risk_score_calculation(self, security_service):
        """Test risk score calculation."""
        # Test different event types
        failed_login_id = security_service.record_security_event(
            SecurityEventType.FAILED_LOGIN,
            source_ip="192.168.1.100"
        )
        
        data_breach_id = security_service.record_security_event(
            SecurityEventType.DATA_BREACH,
            source_ip="192.168.1.101"
        )
        
        failed_login_event = security_service.event_index[failed_login_id]
        data_breach_event = security_service.event_index[data_breach_id]
        
        # Data breach should have higher risk score
        assert data_breach_event.risk_score > failed_login_event.risk_score
        
        # Test with threat intelligence
        security_service.add_threat_indicator(
            "192.168.1.102", "ip", "malware", 0.9, "test"
        )
        
        threat_ip_id = security_service.record_security_event(
            SecurityEventType.FAILED_LOGIN,
            source_ip="192.168.1.102"
        )
        
        threat_ip_event = security_service.event_index[threat_ip_id]
        
        # Event from threat IP should have higher risk score
        assert threat_ip_event.risk_score > failed_login_event.risk_score
    
    def test_severity_determination(self, security_service):
        """Test severity determination logic."""
        # Critical event type should be critical severity
        critical_id = security_service.record_security_event(
            SecurityEventType.DATA_BREACH,
            source_ip="192.168.1.100"
        )
        
        critical_event = security_service.event_index[critical_id]
        assert critical_event.severity == IncidentSeverity.CRITICAL
        
        # Failed login should be lower severity
        low_id = security_service.record_security_event(
            SecurityEventType.FAILED_LOGIN,
            source_ip="192.168.1.101"
        )
        
        low_event = security_service.event_index[low_id]
        assert low_event.severity in [IncidentSeverity.LOW, IncidentSeverity.MEDIUM]
    
    def test_indicator_extraction(self, security_service):
        """Test indicator of compromise extraction."""
        event_id = security_service.record_security_event(
            SecurityEventType.UNAUTHORIZED_ACCESS,
            source_ip="192.168.1.100",
            user_id="test_user",
            resource="/admin",
            details={
                "user_agent": "Mozilla/5.0 (Malicious Bot)",
                "request_path": "/admin/users"
            }
        )
        
        event = security_service.event_index[event_id]
        indicators = event.indicators
        
        # Should include IP, user, and other indicators
        assert any(indicator.startswith("ip:") for indicator in indicators)
        assert any(indicator.startswith("user:") for indicator in indicators)
        assert "unauthorized_access" in indicators
        assert any(indicator.startswith("user_agent:") for indicator in indicators)
        assert any(indicator.startswith("path:") for indicator in indicators)
    
    def test_anomaly_pattern_initialization(self, security_service):
        """Test anomaly pattern initialization."""
        patterns = security_service.anomaly_patterns
        
        # Should have default patterns
        assert 'failed_login_burst' in patterns
        assert 'unusual_access_time' in patterns
        assert 'request_flood' in patterns
        assert 'phi_access_anomaly' in patterns
        
        # Check pattern properties
        failed_login_pattern = patterns['failed_login_burst']
        assert failed_login_pattern.pattern_type == 'rate_limit'
        assert failed_login_pattern.threshold == 5.0
        assert failed_login_pattern.time_window_minutes == 5
        assert failed_login_pattern.severity == IncidentSeverity.HIGH
        assert failed_login_pattern.enabled is True
    
    @patch('src.services.security_monitoring.notification_service')
    def test_failed_login_burst_detection(self, mock_notification, security_service):
        """Test failed login burst anomaly detection."""
        ip = "192.168.1.100"
        
        # Simulate multiple failed login attempts
        for i in range(6):  # Exceed threshold of 5
            security_service.record_security_event(
                SecurityEventType.FAILED_LOGIN,
                source_ip=ip,
                user_id=f"user_{i}"
            )
        
        # Trigger anomaly detection
        security_service._detect_anomalies()
        
        # Should have created an incident
        incidents = security_service.get_incidents()
        burst_incidents = [i for i in incidents if "burst" in i.title.lower()]
        assert len(burst_incidents) >= 1
    
    def test_request_flood_detection(self, security_service):
        """Test request flood anomaly detection."""
        ip = "192.168.1.100"
        current_time = time.time()
        
        # Simulate high volume of requests
        for i in range(150):  # Exceed threshold of 100
            security_service.request_patterns[ip].append(current_time)
        
        # Trigger anomaly detection
        security_service._detect_anomalies()
        
        # Should have created an incident
        incidents = security_service.get_incidents()
        flood_incidents = [i for i in incidents if "flood" in i.title.lower()]
        assert len(flood_incidents) >= 1
    
    def test_data_cleanup(self, security_service):
        """Test old data cleanup."""
        ip = "192.168.1.100"
        old_time = time.time() - 86500  # Over 24 hours ago
        recent_time = time.time() - 3600  # 1 hour ago
        
        # Add old and recent data
        security_service.failed_login_attempts[ip] = [old_time, recent_time]
        security_service.request_patterns[ip] = [old_time, recent_time]
        
        # Trigger cleanup
        security_service._cleanup_old_data()
        
        # Old data should be removed, recent data should remain
        assert len(security_service.failed_login_attempts[ip]) == 1
        assert security_service.failed_login_attempts[ip][0] == recent_time
        
        assert len(security_service.request_patterns[ip]) == 1
        assert security_service.request_patterns[ip][0] == recent_time
    
    def test_threat_intelligence_report(self, security_service):
        """Test threat intelligence report generation."""
        # Add some test data
        security_service.record_security_event(
            SecurityEventType.FAILED_LOGIN,
            source_ip="192.168.1.100"
        )
        
        security_service.record_security_event(
            SecurityEventType.UNAUTHORIZED_ACCESS,
            source_ip="192.168.1.101"
        )
        
        security_service.create_incident(
            "Test incident",
            "Test description",
            IncidentSeverity.HIGH
        )
        
        security_service.add_threat_indicator(
            "192.168.1.100", "ip", "malware", 0.8, "test"
        )
        
        # Generate report
        report = security_service.get_threat_intelligence_report()
        
        assert 'generated_at' in report
        assert 'summary' in report
        assert 'events_by_type' in report
        assert 'top_source_ips' in report
        assert 'recent_incidents' in report
        assert 'threat_indicators' in report
        
        # Check summary data
        summary = report['summary']
        assert summary['total_events_24h'] >= 2
        assert summary['active_incidents'] >= 1
        assert summary['active_threats'] >= 1
        
        # Check events by type
        events_by_type = report['events_by_type']
        assert SecurityEventType.FAILED_LOGIN.value in events_by_type
        assert SecurityEventType.UNAUTHORIZED_ACCESS.value in events_by_type
    
    @patch('src.services.security_monitoring.notification_service')
    @pytest.mark.asyncio
    async def test_incident_response_automation(self, mock_notification, security_service):
        """Test automated incident response."""
        mock_notification.send_security_alert = AsyncMock()
        
        # Create critical incident
        incident_id = security_service.create_incident(
            "Critical security breach",
            "Potential data breach detected",
            IncidentSeverity.CRITICAL,
            event_ids=[]
        )
        
        # Wait for async response to complete
        await asyncio.sleep(0.1)
        
        # Should have sent notification
        mock_notification.send_security_alert.assert_called()
        
        # Check incident response actions
        incident = security_service.incidents[incident_id]
        assert len(incident.response_actions) > 0
    
    def test_incident_escalation(self, security_service):
        """Test incident escalation based on age."""
        # Create old critical incident
        incident_id = security_service.create_incident(
            "Old critical incident",
            "Test description",
            IncidentSeverity.CRITICAL
        )
        
        # Manually set creation time to be old
        incident = security_service.incidents[incident_id]
        incident.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        
        # Process escalations
        security_service._process_incident_escalations()
        
        # Should have escalation action
        escalation_actions = [action for action in incident.response_actions 
                            if "ESCALATED" in action]
        assert len(escalation_actions) > 0
    
    def test_monitoring_thread_lifecycle(self, security_service):
        """Test monitoring thread start/stop."""
        # Start monitoring
        security_service.start_monitoring()
        assert security_service._monitoring_active is True
        assert security_service._monitoring_thread is not None
        assert security_service._monitoring_thread.is_alive()
        
        # Stop monitoring
        security_service.stop_monitoring()
        assert security_service._monitoring_active is False
        
        # Thread should stop
        time.sleep(0.1)
        assert not security_service._monitoring_thread.is_alive()
    
    def test_response_handler_registration(self, security_service):
        """Test response handler registration and execution."""
        handlers = security_service.response_handlers
        
        # Should have handlers for key event types
        assert SecurityEventType.UNAUTHORIZED_ACCESS.value in handlers
        assert SecurityEventType.FAILED_LOGIN.value in handlers
        assert SecurityEventType.SUSPICIOUS_ACTIVITY.value in handlers
        assert SecurityEventType.DATA_BREACH.value in handlers
        assert SecurityEventType.MALICIOUS_REQUEST.value in handlers
        
        # Test handler execution
        event_id = security_service.record_security_event(
            SecurityEventType.DATA_BREACH,
            source_ip="192.168.1.100",
            resource="patient_data"
        )
        
        # Should have created incident automatically
        incidents = security_service.get_incidents()
        breach_incidents = [i for i in incidents if "breach" in i.title.lower()]
        assert len(breach_incidents) >= 1
    
    def test_alert_rate_limiting(self, security_service):
        """Test alert rate limiting to prevent spam."""
        # Create multiple similar anomalies quickly
        for i in range(5):
            security_service._create_anomaly_incident(
                "Test anomaly",
                "Test description",
                IncidentSeverity.MEDIUM,
                ["test_indicator"]
            )
        
        # Should have limited the number of incidents created
        incidents = security_service.get_incidents()
        test_incidents = [i for i in incidents if i.title == "Test anomaly"]
        assert len(test_incidents) <= 3  # Rate limit should prevent more than 3


class TestSecurityIntegration:
    """Integration tests for security monitoring system."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_security_flow(self):
        """Test complete security monitoring flow."""
        service = SecurityMonitoringService()
        
        # Simulate attack pattern
        attacker_ip = "192.168.1.100"
        
        # Multiple failed logins
        for i in range(6):
            service.record_security_event(
                SecurityEventType.FAILED_LOGIN,
                source_ip=attacker_ip,
                user_id=f"victim_{i}"
            )
        
        # Unauthorized access attempt
        service.record_security_event(
            SecurityEventType.UNAUTHORIZED_ACCESS,
            source_ip=attacker_ip,
            resource="/admin/users"
        )
        
        # Trigger anomaly detection
        service._detect_anomalies()
        
        # Should have created incidents
        incidents = service.get_incidents()
        assert len(incidents) >= 1
        
        # Should have blocked the IP
        assert service.is_ip_blocked(attacker_ip)
        
        # Generate threat intelligence report
        report = service.get_threat_intelligence_report()
        assert report['summary']['total_events_24h'] >= 7
        assert report['summary']['active_incidents'] >= 1
    
    @patch('src.services.security_monitoring.notification_service')
    @pytest.mark.asyncio
    async def test_critical_incident_response(self, mock_notification):
        """Test critical incident response workflow."""
        mock_notification.send_security_alert = AsyncMock()
        
        service = SecurityMonitoringService()
        
        # Create data breach event
        event_id = service.record_security_event(
            SecurityEventType.DATA_BREACH,
            source_ip="192.168.1.100",
            user_id="malicious_user",
            resource="patient_database",
            details={"phi_involved": True, "records_affected": 1000}
        )
        
        # Wait for async processing
        await asyncio.sleep(0.1)
        
        # Should have created critical incident
        incidents = service.get_incidents(severity=IncidentSeverity.CRITICAL)
        assert len(incidents) >= 1
        
        # Should have sent alert
        mock_notification.send_security_alert.assert_called()
        
        # Should have blocked IP
        assert service.is_ip_blocked("192.168.1.100")


if __name__ == "__main__":
    pytest.main([__file__])
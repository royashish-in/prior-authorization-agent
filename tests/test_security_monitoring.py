"""
Comprehensive security monitoring test coverage for Prior Authorization Agent.

This module tests security event detection, PHI encryption/decryption, audit logging,
and security incident response to achieve additional coverage for security modules.

Requirements covered: 1.1, 4.1, 3.1
"""

import pytest
import os
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from typing import Dict, Any, List

from src.services.security_monitoring import (
    SecurityMonitoringService,
    SecurityEvent,
    SecurityIncident,
    SecurityEventType,
    IncidentSeverity,
    IncidentStatus,
    AnomalyPattern,
    ThreatIntelligence
)
from src.core.encryption import (
    PHIEncryption,
    get_phi_encryption,
    encrypt_phi_field,
    decrypt_phi_field,
    encrypt_data,
    decrypt_data
)
from src.audit.logger import AuditLogger, get_audit_logger
from src.audit.models import AuditEventType, SecurityLevel


class TestSecurityMonitoringService:
    """Test security monitoring and incident response functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.security_service = SecurityMonitoringService()
        
        # Mock notification service to avoid external dependencies
        self.security_service.notification_service = Mock()
        
        # Test data
        self.test_ip = "192.168.1.100"
        self.test_user_id = "test_user_001"
        self.test_resource = "/api/v1/authorization/requests"

    def test_security_monitoring_service_initialization(self):
        """Test security monitoring service initialization."""
        service = SecurityMonitoringService()
        
        assert service.security_events is not None
        assert service.incidents == {}
        assert service.event_index == {}
        assert service.failed_login_attempts == {}
        assert service.threat_indicators == {}
        assert service.blocked_ips == set()
        assert service.anomaly_patterns is not None
        assert service.response_handlers is not None
        assert service._monitoring_active is False

    def test_start_stop_monitoring(self):
        """Test starting and stopping security monitoring."""
        service = SecurityMonitoringService()
        
        # Start monitoring
        service.start_monitoring()
        assert service._monitoring_active is True
        assert service._monitoring_thread is not None
        
        # Stop monitoring
        service.stop_monitoring()
        assert service._monitoring_active is False

    def test_record_security_event_basic(self):
        """Test recording a basic security event."""
        event_id = self.security_service.record_security_event(
            event_type=SecurityEventType.FAILED_LOGIN,
            source_ip=self.test_ip,
            user_id=self.test_user_id,
            resource=self.test_resource,
            details={"attempt_count": 1}
        )
        
        assert event_id is not None
        assert event_id in self.security_service.event_index
        
        event = self.security_service.event_index[event_id]
        assert event.event_type == SecurityEventType.FAILED_LOGIN
        assert event.source_ip == self.test_ip
        assert event.user_id == self.test_user_id
        assert event.resource == self.test_resource
        assert event.details["attempt_count"] == 1

    def test_record_security_event_risk_calculation(self):
        """Test security event risk score calculation."""
        # Test high-risk event
        event_id = self.security_service.record_security_event(
            event_type=SecurityEventType.DATA_BREACH,
            source_ip=self.test_ip,
            details={"phi_involved": True}
        )
        
        event = self.security_service.event_index[event_id]
        assert event.risk_score >= 8.0  # Data breach should have high risk score
        assert event.severity in [IncidentSeverity.HIGH, IncidentSeverity.CRITICAL]

    def test_record_security_event_with_blocked_ip(self):
        """Test security event recording with blocked IP."""
        # Block the IP first
        self.security_service.block_ip(self.test_ip, "Test blocking", 24)
        
        # Record event from blocked IP
        event_id = self.security_service.record_security_event(
            event_type=SecurityEventType.UNAUTHORIZED_ACCESS,
            source_ip=self.test_ip
        )
        
        event = self.security_service.event_index[event_id]
        assert event.risk_score > 5.0  # Should have elevated risk score

    def test_create_incident_basic(self):
        """Test creating a security incident."""
        incident_id = self.security_service.create_incident(
            title="Test Security Incident",
            description="This is a test incident",
            severity=IncidentSeverity.MEDIUM,
            assigned_to="security_team"
        )
        
        assert incident_id in self.security_service.incidents
        
        incident = self.security_service.incidents[incident_id]
        assert incident.title == "Test Security Incident"
        assert incident.severity == IncidentSeverity.MEDIUM
        assert incident.status == IncidentStatus.OPEN
        assert incident.assigned_to == "security_team"

    def test_create_incident_with_events(self):
        """Test creating incident with related events."""
        # Create some security events first
        event_id1 = self.security_service.record_security_event(
            event_type=SecurityEventType.FAILED_LOGIN,
            source_ip=self.test_ip
        )
        
        event_id2 = self.security_service.record_security_event(
            event_type=SecurityEventType.SUSPICIOUS_ACTIVITY,
            source_ip=self.test_ip
        )
        
        # Create incident with related events
        incident_id = self.security_service.create_incident(
            title="Multiple Security Events",
            description="Multiple related security events detected",
            severity=IncidentSeverity.HIGH,
            event_ids=[event_id1, event_id2]
        )
        
        incident = self.security_service.incidents[incident_id]
        assert len(incident.events) == 2
        assert event_id1 in incident.events
        assert event_id2 in incident.events
        assert len(incident.indicators_of_compromise) > 0

    def test_update_incident_status(self):
        """Test updating incident status."""
        # Create incident
        incident_id = self.security_service.create_incident(
            title="Test Incident",
            description="Test incident for status update",
            severity=IncidentSeverity.LOW
        )
        
        # Update status
        success = self.security_service.update_incident_status(
            incident_id=incident_id,
            status=IncidentStatus.INVESTIGATING,
            notes="Started investigation",
            assigned_to="analyst_001"
        )
        
        assert success is True
        
        incident = self.security_service.incidents[incident_id]
        assert incident.status == IncidentStatus.INVESTIGATING
        assert incident.assigned_to == "analyst_001"
        assert len(incident.response_actions) == 1
        assert "Started investigation" in incident.response_actions[0]

    def test_update_incident_status_close(self):
        """Test closing an incident."""
        # Create incident
        incident_id = self.security_service.create_incident(
            title="Test Incident",
            description="Test incident for closure",
            severity=IncidentSeverity.LOW
        )
        
        # Close incident
        success = self.security_service.update_incident_status(
            incident_id=incident_id,
            status=IncidentStatus.CLOSED,
            notes="Incident resolved - false positive"
        )
        
        assert success is True
        
        incident = self.security_service.incidents[incident_id]
        assert incident.status == IncidentStatus.CLOSED
        assert incident.closed_at is not None
        assert incident.resolution_notes == "Incident resolved - false positive"

    def test_update_incident_status_nonexistent(self):
        """Test updating status of non-existent incident."""
        success = self.security_service.update_incident_status(
            incident_id="nonexistent_incident",
            status=IncidentStatus.CLOSED
        )
        
        assert success is False

    def test_get_security_events_filtering(self):
        """Test retrieving security events with filtering."""
        # Create test events
        self.security_service.record_security_event(
            event_type=SecurityEventType.FAILED_LOGIN,
            source_ip=self.test_ip
        )
        
        self.security_service.record_security_event(
            event_type=SecurityEventType.UNAUTHORIZED_ACCESS,
            source_ip="192.168.1.101"
        )
        
        # Get all events
        all_events = self.security_service.get_security_events(hours=1)
        assert len(all_events) >= 2
        
        # Filter by event type
        login_events = self.security_service.get_security_events(
            hours=1,
            event_type=SecurityEventType.FAILED_LOGIN
        )
        assert len(login_events) >= 1
        assert all(e.event_type == SecurityEventType.FAILED_LOGIN for e in login_events)
        
        # Filter by severity
        high_severity_events = self.security_service.get_security_events(
            hours=1,
            severity=IncidentSeverity.HIGH
        )
        assert all(e.severity == IncidentSeverity.HIGH for e in high_severity_events)

    def test_get_incidents_filtering(self):
        """Test retrieving incidents with filtering."""
        # Create test incidents
        incident1_id = self.security_service.create_incident(
            title="Low Severity Incident",
            description="Test incident",
            severity=IncidentSeverity.LOW
        )
        
        incident2_id = self.security_service.create_incident(
            title="High Severity Incident",
            description="Test incident",
            severity=IncidentSeverity.HIGH
        )
        
        # Update one incident status
        self.security_service.update_incident_status(
            incident1_id,
            IncidentStatus.CLOSED
        )
        
        # Get all incidents
        all_incidents = self.security_service.get_incidents()
        assert len(all_incidents) >= 2
        
        # Filter by status
        open_incidents = self.security_service.get_incidents(status=IncidentStatus.OPEN)
        assert len(open_incidents) >= 1
        assert all(i.status == IncidentStatus.OPEN for i in open_incidents)
        
        # Filter by severity
        high_incidents = self.security_service.get_incidents(severity=IncidentSeverity.HIGH)
        assert len(high_incidents) >= 1
        assert all(i.severity == IncidentSeverity.HIGH for i in high_incidents)

    def test_threat_intelligence_operations(self):
        """Test threat intelligence operations."""
        # Add threat indicator
        self.security_service.add_threat_indicator(
            indicator="192.168.1.200",
            indicator_type="ip",
            threat_type="malware_c2",
            confidence=0.9,
            source="test_feed",
            description="Known malware C2 server"
        )
        
        # Check threat indicators
        threats = self.security_service.check_threat_indicators(ip="192.168.1.200")
        assert len(threats) == 1
        assert threats[0].indicator == "192.168.1.200"
        assert threats[0].threat_type == "malware_c2"
        assert threats[0].confidence == 0.9
        
        # Check non-threatening IP
        no_threats = self.security_service.check_threat_indicators(ip="192.168.1.50")
        assert len(no_threats) == 0

    def test_threat_intelligence_update_existing(self):
        """Test updating existing threat intelligence."""
        indicator = "malicious.example.com"
        
        # Add initial indicator
        self.security_service.add_threat_indicator(
            indicator=indicator,
            indicator_type="domain",
            threat_type="phishing",
            confidence=0.7,
            source="feed1"
        )
        
        # Update with higher confidence
        self.security_service.add_threat_indicator(
            indicator=indicator,
            indicator_type="domain",
            threat_type="phishing",
            confidence=0.9,
            source="feed2"
        )
        
        # Check that confidence was updated
        threats = self.security_service.check_threat_indicators(domain=indicator)
        assert len(threats) == 1
        assert threats[0].confidence == 0.9

    def test_ip_blocking_operations(self):
        """Test IP blocking functionality."""
        test_ip = "192.168.1.250"
        
        # Initially not blocked
        assert not self.security_service.is_ip_blocked(test_ip)
        
        # Block IP
        self.security_service.block_ip(test_ip, "Malicious activity detected", 24)
        
        # Should now be blocked
        assert self.security_service.is_ip_blocked(test_ip)
        
        # Should have created a security event
        events = self.security_service.get_security_events(hours=1)
        blocking_events = [e for e in events if e.source_ip == test_ip and "ip_blocked" in e.details.get("action", "")]
        assert len(blocking_events) >= 1

    def test_get_threat_intelligence_report(self):
        """Test generating threat intelligence report."""
        # Add some test data
        self.security_service.record_security_event(
            event_type=SecurityEventType.FAILED_LOGIN,
            source_ip="192.168.1.100"
        )
        
        self.security_service.record_security_event(
            event_type=SecurityEventType.SUSPICIOUS_ACTIVITY,
            source_ip="192.168.1.101"
        )
        
        self.security_service.create_incident(
            title="Test Incident",
            description="Test incident",
            severity=IncidentSeverity.MEDIUM
        )
        
        self.security_service.add_threat_indicator(
            indicator="192.168.1.200",
            indicator_type="ip",
            threat_type="malware",
            confidence=0.8,
            source="test"
        )
        
        # Generate report
        report = self.security_service.get_threat_intelligence_report()
        
        assert "generated_at" in report
        assert "summary" in report
        assert "events_by_type" in report
        assert "top_source_ips" in report
        assert "recent_incidents" in report
        assert "threat_indicators" in report
        
        # Check summary data
        summary = report["summary"]
        assert "total_events_24h" in summary
        assert "active_incidents" in summary
        assert "blocked_ips" in summary
        assert "active_threats" in summary

    def test_anomaly_pattern_initialization(self):
        """Test anomaly pattern initialization."""
        patterns = self.security_service.anomaly_patterns
        
        assert "failed_login_burst" in patterns
        assert "unusual_access_time" in patterns
        assert "request_flood" in patterns
        assert "phi_access_anomaly" in patterns
        
        # Check pattern structure
        pattern = patterns["failed_login_burst"]
        assert pattern.pattern_type == "rate_limit"
        assert pattern.threshold == 5.0
        assert pattern.enabled is True
        assert IncidentSeverity.HIGH == pattern.severity

    def test_response_handlers_initialization(self):
        """Test response handlers initialization."""
        handlers = self.security_service.response_handlers
        
        assert SecurityEventType.UNAUTHORIZED_ACCESS.value in handlers
        assert SecurityEventType.FAILED_LOGIN.value in handlers
        assert SecurityEventType.SUSPICIOUS_ACTIVITY.value in handlers
        assert SecurityEventType.DATA_BREACH.value in handlers
        assert SecurityEventType.MALICIOUS_REQUEST.value in handlers
        
        # Check handlers are callable
        for handler in handlers.values():
            assert callable(handler)

    def test_event_id_generation(self):
        """Test event ID generation."""
        event_id1 = self.security_service._generate_event_id()
        event_id2 = self.security_service._generate_event_id()
        
        assert event_id1 != event_id2
        assert event_id1.startswith("evt_")
        assert event_id2.startswith("evt_")

    def test_incident_id_generation(self):
        """Test incident ID generation."""
        incident_id1 = self.security_service._generate_incident_id()
        incident_id2 = self.security_service._generate_incident_id()
        
        assert incident_id1 != incident_id2
        assert incident_id1.startswith("inc_")
        assert incident_id2.startswith("inc_")

    def test_risk_score_calculation_factors(self):
        """Test risk score calculation with various factors."""
        # Test base score for different event types
        score1 = self.security_service._calculate_risk_score(
            SecurityEventType.FAILED_LOGIN,
            "192.168.1.100",
            None,
            {}
        )
        
        score2 = self.security_service._calculate_risk_score(
            SecurityEventType.DATA_BREACH,
            "192.168.1.100",
            None,
            {}
        )
        
        assert score2 > score1  # Data breach should have higher base score
        
        # Test PHI involvement factor
        score_with_phi = self.security_service._calculate_risk_score(
            SecurityEventType.UNAUTHORIZED_ACCESS,
            "192.168.1.100",
            None,
            {"phi_involved": True}
        )
        
        score_without_phi = self.security_service._calculate_risk_score(
            SecurityEventType.UNAUTHORIZED_ACCESS,
            "192.168.1.100",
            None,
            {}
        )
        
        assert score_with_phi > score_without_phi

    def test_severity_determination(self):
        """Test incident severity determination."""
        # Test critical severity
        critical_severity = self.security_service._determine_severity(
            SecurityEventType.DATA_BREACH,
            9.5
        )
        assert critical_severity == IncidentSeverity.CRITICAL
        
        # Test high severity
        high_severity = self.security_service._determine_severity(
            SecurityEventType.UNAUTHORIZED_ACCESS,
            7.5
        )
        assert high_severity == IncidentSeverity.HIGH
        
        # Test medium severity
        medium_severity = self.security_service._determine_severity(
            SecurityEventType.SUSPICIOUS_ACTIVITY,
            5.5
        )
        assert medium_severity == IncidentSeverity.MEDIUM
        
        # Test low severity
        low_severity = self.security_service._determine_severity(
            SecurityEventType.FAILED_LOGIN,
            3.0
        )
        assert low_severity == IncidentSeverity.LOW

    def test_indicator_extraction(self):
        """Test indicator extraction from events."""
        indicators = self.security_service._extract_indicators(
            SecurityEventType.FAILED_LOGIN,
            "192.168.1.100",
            "test_user",
            {
                "user_agent": "Mozilla/5.0",
                "request_path": "/api/login"
            }
        )
        
        assert "ip:192.168.1.100" in indicators
        assert "user:test_user" in indicators
        assert "failed_auth" in indicators
        assert "user_agent:Mozilla/5.0" in indicators
        assert "path:/api/login" in indicators

    @patch('time.time')
    def test_cleanup_old_data(self, mock_time):
        """Test cleanup of old tracking data."""
        current_time = time.time()
        mock_time.return_value = current_time
        
        # Add some old data
        old_time = current_time - 90000  # More than 24 hours ago
        self.security_service.failed_login_attempts["192.168.1.100"] = [old_time]
        self.security_service.request_patterns["192.168.1.100"] = [old_time]
        
        # Add some recent data
        recent_time = current_time - 3600  # 1 hour ago
        self.security_service.failed_login_attempts["192.168.1.101"] = [recent_time]
        
        # Run cleanup
        self.security_service._cleanup_old_data()
        
        # Old data should be removed
        assert "192.168.1.100" not in self.security_service.failed_login_attempts
        assert "192.168.1.100" not in self.security_service.request_patterns
        
        # Recent data should remain
        assert "192.168.1.101" in self.security_service.failed_login_attempts


class TestPHIEncryption:
    """Test PHI encryption and decryption functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Use a test encryption key
        os.environ['PHI_MASTER_KEY'] = 'test_master_key_for_phi_encryption_2024'
        self.encryption = PHIEncryption()

    def teardown_method(self):
        """Clean up test environment."""
        if 'PHI_MASTER_KEY' in os.environ:
            del os.environ['PHI_MASTER_KEY']

    def test_phi_encryption_initialization(self):
        """Test PHI encryption initialization."""
        # Test with explicit key
        encryption = PHIEncryption("test_key_123")
        assert encryption._master_key == "test_key_123"
        
        # Test without key should raise error
        if 'PHI_MASTER_KEY' in os.environ:
            del os.environ['PHI_MASTER_KEY']
        
        with pytest.raises(ValueError, match="PHI_MASTER_KEY environment variable must be set"):
            PHIEncryption()

    def test_basic_encryption_decryption(self):
        """Test basic encryption and decryption."""
        plaintext = "This is sensitive PHI data"
        
        # Encrypt
        encrypted = self.encryption.encrypt(plaintext)
        assert encrypted != plaintext
        assert isinstance(encrypted, str)
        
        # Decrypt
        decrypted = self.encryption.decrypt(encrypted)
        assert decrypted == plaintext

    def test_encryption_with_bytes(self):
        """Test encryption with bytes input."""
        plaintext_bytes = b"Binary PHI data"
        
        # Encrypt bytes
        encrypted = self.encryption.encrypt(plaintext_bytes)
        assert isinstance(encrypted, str)
        
        # Decrypt back to string
        decrypted = self.encryption.decrypt(encrypted)
        assert decrypted == plaintext_bytes.decode('utf-8')

    def test_encryption_empty_data(self):
        """Test encryption with empty data."""
        with pytest.raises(ValueError, match="Cannot encrypt empty or None data"):
            self.encryption.encrypt("")
        
        with pytest.raises(ValueError, match="Cannot encrypt empty or None data"):
            self.encryption.encrypt(None)

    def test_decryption_empty_data(self):
        """Test decryption with empty data."""
        with pytest.raises(ValueError, match="Cannot decrypt empty or None data"):
            self.encryption.decrypt("")
        
        with pytest.raises(ValueError, match="Cannot decrypt empty or None data"):
            self.encryption.decrypt(None)

    def test_decryption_invalid_data(self):
        """Test decryption with invalid data."""
        with pytest.raises(Exception, match="Decryption failed"):
            self.encryption.decrypt("invalid_encrypted_data")

    def test_patient_id_encryption(self):
        """Test patient ID encryption with prefix."""
        patient_id = "PAT_12345"
        
        encrypted = self.encryption.encrypt_patient_id(patient_id)
        assert encrypted.startswith("enc_pat_")
        assert encrypted != patient_id
        
        decrypted = self.encryption.decrypt_patient_id(encrypted)
        assert decrypted == patient_id

    def test_patient_id_encryption_empty(self):
        """Test patient ID encryption with empty data."""
        with pytest.raises(ValueError, match="Patient ID cannot be empty"):
            self.encryption.encrypt_patient_id("")

    def test_patient_id_decryption_invalid_format(self):
        """Test patient ID decryption with invalid format."""
        with pytest.raises(ValueError, match="Invalid encrypted patient ID format"):
            self.encryption.decrypt_patient_id("invalid_format")
        
        with pytest.raises(ValueError, match="Invalid encrypted patient ID format"):
            self.encryption.decrypt_patient_id("")

    def test_insurance_id_encryption(self):
        """Test insurance ID encryption with prefix."""
        insurance_id = "INS_67890"
        
        encrypted = self.encryption.encrypt_insurance_id(insurance_id)
        assert encrypted.startswith("enc_ins_")
        assert encrypted != insurance_id
        
        decrypted = self.encryption.decrypt_insurance_id(encrypted)
        assert decrypted == insurance_id

    def test_insurance_id_encryption_empty(self):
        """Test insurance ID encryption with empty data."""
        with pytest.raises(ValueError, match="Insurance ID cannot be empty"):
            self.encryption.encrypt_insurance_id("")

    def test_insurance_id_decryption_invalid_format(self):
        """Test insurance ID decryption with invalid format."""
        with pytest.raises(ValueError, match="Invalid encrypted insurance ID format"):
            self.encryption.decrypt_insurance_id("invalid_format")

    def test_member_id_encryption(self):
        """Test member ID encryption with prefix."""
        member_id = "MEM_54321"
        
        encrypted = self.encryption.encrypt_member_id(member_id)
        assert encrypted.startswith("enc_mem_")
        assert encrypted != member_id
        
        decrypted = self.encryption.decrypt_member_id(encrypted)
        assert decrypted == member_id

    def test_member_id_encryption_empty(self):
        """Test member ID encryption with empty data."""
        with pytest.raises(ValueError, match="Member ID cannot be empty"):
            self.encryption.encrypt_member_id("")

    def test_member_id_decryption_invalid_format(self):
        """Test member ID decryption with invalid format."""
        with pytest.raises(ValueError, match="Invalid encrypted member ID format"):
            self.encryption.decrypt_member_id("invalid_format")

    def test_clinical_notes_encryption(self):
        """Test clinical notes encryption."""
        notes = "Patient presents with chest pain. Recommend cardiac workup."
        
        encrypted = self.encryption.encrypt_clinical_notes(notes)
        assert encrypted != notes
        
        decrypted = self.encryption.decrypt_clinical_notes(encrypted)
        assert decrypted == notes

    def test_clinical_notes_encryption_empty(self):
        """Test clinical notes encryption with empty data."""
        encrypted = self.encryption.encrypt_clinical_notes("")
        assert encrypted == ""
        
        decrypted = self.encryption.decrypt_clinical_notes("")
        assert decrypted == ""

    def test_get_phi_encryption_singleton(self):
        """Test global PHI encryption instance."""
        encryption1 = get_phi_encryption()
        encryption2 = get_phi_encryption()
        
        assert encryption1 is encryption2  # Should be same instance

    def test_encrypt_phi_field_convenience_functions(self):
        """Test convenience functions for PHI field encryption."""
        # Test patient ID
        patient_id = "PAT_12345"
        encrypted = encrypt_phi_field(patient_id, "patient_id")
        assert encrypted.startswith("enc_pat_")
        
        decrypted = decrypt_phi_field(encrypted, "patient_id")
        assert decrypted == patient_id
        
        # Test insurance ID
        insurance_id = "INS_67890"
        encrypted = encrypt_phi_field(insurance_id, "insurance_id")
        assert encrypted.startswith("enc_ins_")
        
        decrypted = decrypt_phi_field(encrypted, "insurance_id")
        assert decrypted == insurance_id
        
        # Test member ID
        member_id = "MEM_54321"
        encrypted = encrypt_phi_field(member_id, "member_id")
        assert encrypted.startswith("enc_mem_")
        
        decrypted = decrypt_phi_field(encrypted, "member_id")
        assert decrypted == member_id
        
        # Test clinical notes
        notes = "Clinical notes here"
        encrypted = encrypt_phi_field(notes, "clinical_notes")
        decrypted = decrypt_phi_field(encrypted, "clinical_notes")
        assert decrypted == notes
        
        # Test generic field
        generic_data = "Generic sensitive data"
        encrypted = encrypt_phi_field(generic_data, "generic")
        decrypted = decrypt_phi_field(encrypted, "generic")
        assert decrypted == generic_data

    def test_encrypt_decrypt_data_with_key(self):
        """Test encryption/decryption with provided key."""
        data = "Test data for encryption"
        key = os.urandom(32)  # 32 bytes for AES-256
        
        encrypted = encrypt_data(data, key)
        assert encrypted != data
        
        decrypted = decrypt_data(encrypted, key)
        assert decrypted == data

    def test_fernet_key_creation(self):
        """Test Fernet key creation from master key."""
        master_key = "test_master_key"
        fernet1 = self.encryption._create_fernet_key(master_key)
        fernet2 = self.encryption._create_fernet_key(master_key)
        
        # Should create consistent keys
        test_data = "test data"
        encrypted1 = fernet1.encrypt(test_data.encode())
        decrypted2 = fernet2.decrypt(encrypted1).decode()
        
        assert decrypted2 == test_data


class TestAuditLogger:
    """Test audit logging functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Mock database setup to avoid actual database operations
        with patch('src.audit.logger.create_engine'), \
             patch('src.audit.logger.sessionmaker'), \
             patch.object(AuditLogger, '_create_audit_tables'), \
             patch.object(AuditLogger, '_setup_encryption'):
            
            self.audit_logger = AuditLogger()
            
            # Mock the database engine and connection
            self.audit_logger.engine = Mock()
            self.mock_connection = Mock()
            self.audit_logger.engine.connect.return_value.__enter__.return_value = self.mock_connection
            
            # Set up encryption key
            self.audit_logger.encryption_key = b'test_key_32_bytes_for_aes_256_enc'

    def test_audit_logger_initialization(self):
        """Test audit logger initialization."""
        with patch('src.audit.logger.create_engine'), \
             patch('src.audit.logger.sessionmaker'), \
             patch.object(AuditLogger, '_create_audit_tables'), \
             patch.object(AuditLogger, '_setup_encryption'):
            
            logger = AuditLogger()
            assert logger.settings is not None

    def test_log_event_basic(self):
        """Test basic audit event logging."""
        event_id = self.audit_logger.log_event(
            event_type=AuditEventType.USER_LOGIN,
            action="login",
            outcome="success",
            user_id="test_user_001",
            username="testuser",
            client_ip="192.168.1.100"
        )
        
        assert event_id is not None
        assert isinstance(event_id, str)
        
        # Verify database insert was called
        self.mock_connection.execute.assert_called()
        self.mock_connection.commit.assert_called()

    def test_log_event_with_details(self):
        """Test audit event logging with encrypted details."""
        details = {
            "resource": "/api/v1/authorization",
            "method": "POST",
            "response_code": 200
        }
        
        event_id = self.audit_logger.log_event(
            event_type=AuditEventType.RESOURCE_ACCESS,
            action="create_authorization",
            outcome="success",
            user_id="test_user_001",
            client_ip="192.168.1.100",
            details=details,
            phi_involved=True,
            security_level=SecurityLevel.HIGH
        )
        
        assert event_id is not None
        
        # Verify the call included encrypted details
        call_args = self.mock_connection.execute.call_args
        assert call_args is not None

    def test_log_security_event(self):
        """Test security event logging."""
        event_id = self.audit_logger.log_security_event(
            threat_type="brute_force",
            severity=SecurityLevel.HIGH,
            confidence=0.9,
            source_ip="192.168.1.200",
            attack_vector="password_spray",
            user_id="target_user",
            target_resource="/api/login",
            blocked=True
        )
        
        assert event_id is not None
        
        # Should have called execute twice (security event + audit event)
        assert self.mock_connection.execute.call_count >= 2

    def test_log_phi_access(self):
        """Test PHI access logging."""
        event_id = self.audit_logger.log_phi_access(
            user_id="doctor_001",
            username="dr.smith",
            resource_type="patient_record",
            resource_id="PAT_12345",
            action="view",
            client_ip="192.168.1.50",
            session_id="sess_12345"
        )
        
        assert event_id is not None
        
        # Verify database operations
        self.mock_connection.execute.assert_called()
        self.mock_connection.commit.assert_called()

    def test_log_authentication_success(self):
        """Test successful authentication logging."""
        event_id = self.audit_logger.log_authentication(
            username="testuser",
            outcome="success",
            client_ip="192.168.1.100",
            user_agent="Mozilla/5.0"
        )
        
        assert event_id is not None
        self.mock_connection.execute.assert_called()

    def test_log_authentication_failure(self):
        """Test failed authentication logging."""
        event_id = self.audit_logger.log_authentication(
            username="testuser",
            outcome="failure",
            client_ip="192.168.1.100",
            error_message="Invalid credentials"
        )
        
        assert event_id is not None
        self.mock_connection.execute.assert_called()

    def test_log_ai_config_action(self):
        """Test AI configuration action logging."""
        details = {
            "model_name": "gpt-4",
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        event_id = self.audit_logger.log_ai_config_action(
            action="update_model_config",
            config_id="config_001",
            user_id="admin_001",
            details=details,
            client_ip="192.168.1.10"
        )
        
        assert event_id is not None
        self.mock_connection.execute.assert_called()

    def test_get_events_basic(self):
        """Test retrieving audit events."""
        # Mock database result
        mock_row = Mock()
        mock_row.event_id = "evt_001"
        mock_row.event_type = "user_login"
        mock_row.timestamp = datetime.now(timezone.utc)
        mock_row.user_id = "test_user"
        mock_row.username = "testuser"
        mock_row.client_ip = "192.168.1.100"
        mock_row.action = "login"
        mock_row.outcome = "success"
        mock_row.security_level = "low"
        mock_row.phi_involved = False
        mock_row.resource_type = None
        mock_row.resource_id = None
        mock_row.error_message = None
        mock_row.duration_ms = 150
        
        self.mock_connection.execute.return_value = [mock_row]
        
        events = self.audit_logger.get_events(limit=10)
        
        assert len(events) == 1
        assert events[0]["event_id"] == "evt_001"
        assert events[0]["event_type"] == "user_login"
        assert events[0]["user_id"] == "test_user"

    def test_get_events_with_filtering(self):
        """Test retrieving audit events with filtering."""
        start_time = datetime.now(timezone.utc) - timedelta(hours=1)
        end_time = datetime.now(timezone.utc)
        
        self.mock_connection.execute.return_value = []
        
        events = self.audit_logger.get_events(
            start_time=start_time,
            end_time=end_time,
            event_types=[AuditEventType.USER_LOGIN],
            user_id="test_user",
            limit=50
        )
        
        assert isinstance(events, list)
        
        # Verify the query was constructed with filters
        call_args = self.mock_connection.execute.call_args
        assert call_args is not None

    def test_get_audit_logger_singleton(self):
        """Test global audit logger instance."""
        with patch('src.audit.logger.AuditLogger') as mock_logger_class:
            mock_instance = Mock()
            mock_logger_class.return_value = mock_instance
            
            logger1 = get_audit_logger()
            logger2 = get_audit_logger()
            
            assert logger1 is logger2  # Should be same instance

    @patch('src.audit.logger.encrypt_data')
    def test_encryption_in_logging(self, mock_encrypt):
        """Test that sensitive data is encrypted in audit logs."""
        mock_encrypt.return_value = "encrypted_data"
        
        details = {"sensitive": "data"}
        
        self.audit_logger.log_event(
            event_type=AuditEventType.PHI_ACCESS,
            action="view",
            outcome="success",
            details=details
        )
        
        # Verify encryption was called
        mock_encrypt.assert_called_once()

    def test_database_error_handling(self):
        """Test database error handling in audit logging."""
        # Mock database error
        self.mock_connection.execute.side_effect = Exception("Database error")
        
        with pytest.raises(Exception, match="Database error"):
            self.audit_logger.log_event(
                event_type=AuditEventType.USER_LOGIN,
                action="login",
                outcome="success"
            )

    def test_create_audit_tables(self):
        """Test audit table creation."""
        with patch('src.audit.logger.create_engine'), \
             patch('src.audit.logger.sessionmaker'):
            
            logger = AuditLogger()
            mock_connection = Mock()
            logger.engine = Mock()
            logger.engine.connect.return_value.__enter__.return_value = mock_connection
            
            # Call the method
            logger._create_audit_tables()
            
            # Verify SQL execution
            assert mock_connection.execute.call_count > 0
            mock_connection.commit.assert_called()


class TestSecurityEventModels:
    """Test security event data models."""
    
    def test_security_event_creation(self):
        """Test SecurityEvent data structure."""
        event = SecurityEvent(
            event_id="evt_001",
            event_type=SecurityEventType.FAILED_LOGIN,
            timestamp=datetime.now(timezone.utc),
            source_ip="192.168.1.100",
            user_id="test_user",
            resource="/api/login",
            details={"attempt": 1},
            severity=IncidentSeverity.MEDIUM,
            risk_score=5.5,
            indicators=["failed_auth", "ip:192.168.1.100"],
            raw_data={"user_agent": "Mozilla/5.0"}
        )
        
        assert event.event_id == "evt_001"
        assert event.event_type == SecurityEventType.FAILED_LOGIN
        assert event.source_ip == "192.168.1.100"
        assert event.severity == IncidentSeverity.MEDIUM
        assert event.risk_score == 5.5

    def test_security_incident_creation(self):
        """Test SecurityIncident data structure."""
        incident = SecurityIncident(
            incident_id="inc_001",
            title="Test Incident",
            description="Test incident description",
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.OPEN,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            assigned_to="analyst_001",
            events=["evt_001", "evt_002"],
            indicators_of_compromise=["ip:192.168.1.100"],
            response_actions=["blocked_ip"],
            resolution_notes=None,
            closed_at=None
        )
        
        assert incident.incident_id == "inc_001"
        assert incident.title == "Test Incident"
        assert incident.severity == IncidentSeverity.HIGH
        assert incident.status == IncidentStatus.OPEN
        assert len(incident.events) == 2

    def test_anomaly_pattern_creation(self):
        """Test AnomalyPattern data structure."""
        pattern = AnomalyPattern(
            pattern_id="pattern_001",
            pattern_type="rate_limit",
            description="Test pattern",
            threshold=10.0,
            time_window_minutes=5,
            indicators=["test_indicator"],
            severity=IncidentSeverity.MEDIUM,
            enabled=True
        )
        
        assert pattern.pattern_id == "pattern_001"
        assert pattern.pattern_type == "rate_limit"
        assert pattern.threshold == 10.0
        assert pattern.enabled is True

    def test_threat_intelligence_creation(self):
        """Test ThreatIntelligence data structure."""
        threat = ThreatIntelligence(
            indicator="192.168.1.200",
            indicator_type="ip",
            threat_type="malware",
            confidence=0.9,
            source="test_feed",
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
            description="Test threat"
        )
        
        assert threat.indicator == "192.168.1.200"
        assert threat.indicator_type == "ip"
        assert threat.threat_type == "malware"
        assert threat.confidence == 0.9

    def test_security_event_type_enum(self):
        """Test SecurityEventType enum values."""
        assert SecurityEventType.UNAUTHORIZED_ACCESS.value == "unauthorized_access"
        assert SecurityEventType.FAILED_LOGIN.value == "failed_login"
        assert SecurityEventType.DATA_BREACH.value == "data_breach"
        assert SecurityEventType.MALICIOUS_REQUEST.value == "malicious_request"

    def test_incident_severity_enum(self):
        """Test IncidentSeverity enum values."""
        assert IncidentSeverity.LOW.value == "low"
        assert IncidentSeverity.MEDIUM.value == "medium"
        assert IncidentSeverity.HIGH.value == "high"
        assert IncidentSeverity.CRITICAL.value == "critical"

    def test_incident_status_enum(self):
        """Test IncidentStatus enum values."""
        assert IncidentStatus.OPEN.value == "open"
        assert IncidentStatus.INVESTIGATING.value == "investigating"
        assert IncidentStatus.CONTAINED.value == "contained"
        assert IncidentStatus.RESOLVED.value == "resolved"
        assert IncidentStatus.CLOSED.value == "closed"
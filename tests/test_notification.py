"""
Tests for notification and alert system.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch

from src.services.notification import (
    NotificationService,
    NotificationPreferences,
    NotificationEvent,
    DashboardAlert,
    EscalationRule
)
from src.models.authorization import AuthorizationRequest, AuthorizationDecision
from src.models.patient import PatientDemographics
from src.models.medical_codes import ICD10Code, CPTCode
from src.models.enums import (
    RequestStatus,
    DecisionStatus,
    UrgencyLevel,
    ProcedureType,
    Gender
)


@pytest.fixture
def notification_service():
    """Create notification service instance."""
    return NotificationService()


    @pytest.fixture
    def sample_patient():
    """Create sample patient demographics."""
    return PatientDemographics(
        patient_id="enc_pat_1a2b3c4d5e6f7g8h",
        age=45,
        gender=Gender.FEMALE,
        insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
        member_id="enc_mem_1z2y3x4w5v6u7t8s"
    )


@pytest.fixture
def sample_request(sample_patient):
    """Create sample authorization request."""
    return AuthorizationRequest(
        request_id="req_2024_001234",
        provider_id="prov_12345",
        patient_demographics=sample_patient,
        diagnosis_codes=[ICD10Code(code="M25.511", description="Pain in right shoulder")],
        procedure_codes=[CPTCode(code="73221", description="MRI upper extremity without contrast")],
        clinical_notes="Patient reports persistent shoulder pain for 6 weeks",
        procedure_type=ProcedureType.MRI,
        urgency_level=UrgencyLevel.ROUTINE,
        status=RequestStatus.SUBMITTED
    )


    @pytest.fixture
    def sample_decision():
    """Create sample authorization decision."""
    return AuthorizationDecision(
        decision_id="dec_2024_001234",
        request_id="req_2024_001234",
        status=DecisionStatus.APPROVED,
        reasoning=[
            "Patient meets medical necessity criteria for shoulder MRI",
            "Diagnosis code M25.511 is covered under current policy"
        ],
        policy_references=["CMS NCD 220.2", "Payer Policy IMG-001"],
        authorization_number="auth_2024_567890",
        valid_until=datetime.now(timezone.utc) + timedelta(days=30),
        confidence_score=0.95
    )


@pytest.fixture
def sample_preferences():
    """Create sample notification preferences."""
    return NotificationPreferences(
        provider_id="prov_12345",
        email_address="SYNTH_PROVIDER_EMAIL_TEST@synthetic-hospital.test",
        enable_email_notifications=True,
        enable_dashboard_alerts=True,
        enable_escalation_notifications=True,
        notification_frequency="immediate"
    )


    class TestNotificationService:
    """Test notification service functionality."""
    
    @pytest.mark.asyncio

    
    async def test_send_decision_notification_approved(
        self,
        notification_service,
        sample_request,
        sample_decision
    ):
    """Test sending notification for approved decision."""
        # Execute
        result = await notification_service.send_decision_notification(
            sample_request,
            sample_decision
        )
        
        # Verify
        assert result is True
        
        # Check that dashboard alert was created
        alerts = await notification_service.get_dashboard_alerts("prov_12345")
        assert len(alerts) == 1
        
        alert = alerts[0]
        assert alert.provider_id == "prov_12345"
        assert alert.alert_type == "success"
        assert alert.title == "Authorization Approved"
        assert "req_2024_001234" in alert.message
        assert alert.request_id == "req_2024_001234"
        assert alert.action_required is False
    
    @pytest.mark.asyncio

    
    async def test_send_decision_notification_denied(
        self,
        notification_service,
        sample_request
    ):
    """Test sending notification for denied decision."""
        # Create denied decision
        denied_decision = AuthorizationDecision(
            decision_id="dec_2024_001235",
            request_id="req_2024_001234",
            status=DecisionStatus.DENIED,
            reasoning=["Insufficient medical necessity documentation"],
            confidence_score=0.85
        )
        
        # Execute
        result = await notification_service.send_decision_notification(
            sample_request,
            denied_decision
        )
        
        # Verify
        assert result is True
        
        # Check dashboard alert
        alerts = await notification_service.get_dashboard_alerts("prov_12345")
        assert len(alerts) == 1
        
        alert = alerts[0]
        assert alert.alert_type == "error"
        assert alert.title == "Authorization Denied"
        assert alert.action_required is False
    
    @pytest.mark.asyncio

    
    async def test_send_decision_notification_more_info_needed(
        self,
        notification_service,
        sample_request
    ):
    """Test sending notification for more info needed decision."""
        # Create more info needed decision
        info_decision = AuthorizationDecision(
            decision_id="dec_2024_001236",
            request_id="req_2024_001234",
            status=DecisionStatus.MORE_INFO_NEEDED,
            reasoning=["Additional clinical documentation required"],
            confidence_score=0.60,
            additional_info_needed=["Recent imaging reports", "Physical therapy notes"]
        )
        
        # Execute
        result = await notification_service.send_decision_notification(
            sample_request,
            info_decision
        )
        
        # Verify
        assert result is True
        
        # Check dashboard alert
        alerts = await notification_service.get_dashboard_alerts("prov_12345")
        assert len(alerts) == 1
        
        alert = alerts[0]
        assert alert.alert_type == "warning"
        assert alert.title == "Additional Information Required"
        assert alert.action_required is True
    
    @pytest.mark.asyncio

    
    async def test_send_status_update_notification(
        self,
        notification_service,
        sample_request
    ):
    """Test sending status update notification."""
        # Execute
        result = await notification_service.send_status_update_notification(
            sample_request,
            RequestStatus.SUBMITTED,
            RequestStatus.IN_REVIEW,
            "Request is now under review by medical team"
        )
        
        # Verify
        assert result is True
        
        # Check dashboard alert
        alerts = await notification_service.get_dashboard_alerts("prov_12345")
        assert len(alerts) == 1
        
        alert = alerts[0]
        assert alert.alert_type == "info"
        assert alert.title == "Status Update"
        assert "Request is now under review by medical team" in alert.message
        assert alert.action_required is False
    
    @pytest.mark.asyncio

    
    async def test_send_escalation_notification(
        self,
        notification_service,
        sample_request
    ):
    """Test sending escalation notification."""
        # Execute
        result = await notification_service.send_escalation_notification(
            sample_request,
            "Request exceeds 24-hour processing threshold",
            ["email_supervisor", "priority_queue"]
        )
        
        # Verify
        assert result is True
        
        # Check dashboard alert
        alerts = await notification_service.get_dashboard_alerts("prov_12345")
        assert len(alerts) == 1
        
        alert = alerts[0]
        assert alert.alert_type == "warning"
        assert alert.title == "Request Escalated"
        assert "Request exceeds 24-hour processing threshold" in alert.message
        assert alert.action_required is True
    
    @pytest.mark.asyncio

    
    async def test_get_dashboard_alerts_filtering(
        self,
        notification_service,
        sample_request,
        sample_decision
    ):
    """Test dashboard alerts filtering."""
        # Create multiple alerts
        await notification_service.send_decision_notification(sample_request, sample_decision)
        await notification_service.send_status_update_notification(
            sample_request,
            RequestStatus.SUBMITTED,
            RequestStatus.IN_REVIEW
        )
        
        # Get all alerts
        all_alerts = await notification_service.get_dashboard_alerts("prov_12345")
        assert len(all_alerts) == 2
        
        # Mark one as read
        await notification_service.mark_alert_as_read("prov_12345", all_alerts[0].alert_id)
        
        # Get unread alerts only
        unread_alerts = await notification_service.get_dashboard_alerts(
            "prov_12345",
            include_read=False
        )
        assert len(unread_alerts) == 1
        
        # Get all alerts including read
        all_alerts_with_read = await notification_service.get_dashboard_alerts(
            "prov_12345",
            include_read=True
        )
        assert len(all_alerts_with_read) == 2
    
    @pytest.mark.asyncio

    
    async def test_mark_alert_as_read(
        self,
        notification_service,
        sample_request,
        sample_decision
    ):
    """Test marking alert as read."""
        # Create alert
        await notification_service.send_decision_notification(sample_request, sample_decision)
        
        # Get alert
        alerts = await notification_service.get_dashboard_alerts("prov_12345")
        assert len(alerts) == 1
        assert alerts[0].is_read is False
        
        # Mark as read
        result = await notification_service.mark_alert_as_read(
            "prov_12345",
            alerts[0].alert_id
        )
        assert result is True
        
        # Verify it's marked as read
        updated_alerts = await notification_service.get_dashboard_alerts(
            "prov_12345",
            include_read=True
        )
        assert updated_alerts[0].is_read is True
    
    @pytest.mark.asyncio

    
    async def test_mark_alert_as_read_not_found(self, notification_service):
    """Test marking non-existent alert as read."""
        result = await notification_service.mark_alert_as_read(
            "prov_12345",
            "nonexistent_alert_id"
        )
        assert result is False
    
    @pytest.mark.asyncio

    
    async def test_check_escalation_rules_time_threshold(
        self,
        notification_service,
        sample_patient
    ):
    """Test escalation rules based on time threshold."""
        # Create request that's been pending for 3 hours
        old_request = AuthorizationRequest(
            request_id="req_2024_001237",
            provider_id="prov_12345",
            patient_demographics=sample_patient,
            diagnosis_codes=[ICD10Code(code="M25.511", description="Pain in right shoulder")],
            procedure_codes=[CPTCode(code="73221", description="MRI upper extremity without contrast")],
            procedure_type=ProcedureType.MRI,
            urgency_level=UrgencyLevel.URGENT,
            status=RequestStatus.IN_REVIEW,
            submitted_at=datetime.now(timezone.utc) - timedelta(hours=3)
        )
        
        # Execute
        escalation_actions = await notification_service.check_escalation_rules(old_request)
        
        # Verify - should trigger urgent request delay rule (2 hour threshold)
        assert len(escalation_actions) > 0
        assert "email_supervisor" in escalation_actions or "priority_queue" in escalation_actions
    
    @pytest.mark.asyncio

    
    async def test_check_escalation_rules_no_escalation(
        self,
        notification_service,
        sample_request
    ):
    """Test escalation rules with no escalation needed."""
        # Recent request should not trigger escalation
        escalation_actions = await notification_service.check_escalation_rules(sample_request)
        
        # Verify - no escalation for recent routine request
        assert len(escalation_actions) == 0
    
    @pytest.mark.asyncio

    
    async def test_update_notification_preferences(
        self,
        notification_service,
        sample_preferences
    ):
    """Test updating notification preferences."""
        # Execute
        result = await notification_service.update_notification_preferences(
            "prov_12345",
            sample_preferences
        )
        
        # Verify
        assert result is True
        
        # Check preferences were stored
        stored_prefs = await notification_service._get_provider_preferences("prov_12345")
        assert stored_prefs.email_address == "SYNTH_PROVIDER_EMAIL_TEST@synthetic-hospital.test"
        assert stored_prefs.enable_email_notifications is True


    class TestNotificationModels:
    """Test notification data models."""
    
    def test_notification_preferences_model(self):
    """
        Test notification preferences model.
        
        This test verifies system functionality and ensures that the system
        behaves correctly under the specified conditions.
        
        Test Scenarios:
        - Standard input scenarios
        - Edge cases and boundary conditions
        - Error handling scenarios
        
        Expected Behavior:
        - System should behave according to specified requirements
        
        PHI Compliance:
        All test data uses synthetic information with appropriate markers.
        """

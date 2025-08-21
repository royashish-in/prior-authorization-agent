"""
Tests for the tracking service.

This module tests request tracking, status updates, and audit trail
functionality for prior authorization requests.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any, List

from src.services.tracking import TrackingService, RequestStatusInfo, RequestsResult
from src.models.enums import RequestStatus
from src.models.authorization import AuthorizationRequest
from src.models.patient import PatientDemographics
from src.models.enums import DecisionStatus, UrgencyLevel, ProcedureType, RequestStatus


class TestTrackingService:
    """Test tracking service functionality."""
    
    @pytest.fixture
    def tracking_service(self):
        """Create tracking service instance."""
        return TrackingService()
    
    @pytest.fixture
    def sample_request(self):
        """Create sample authorization request."""
        return AuthorizationRequest(
            patient_demographics=PatientDemographics(
                first_name="John",
                last_name="Doe",
                date_of_birth=datetime(1980, 1, 1),
                gender=Gender.MALE,
                member_id="TEST123456"
            ),
            diagnosis_codes=[],
            procedure_codes=[],
            clinical_notes="Test clinical notes",
            urgency_level=UrgencyLevel.ROUTINE,
            procedure_type=ProcedureType.MRI
        )
    
    @pytest.mark.asyncio

    
    async def test_store_request_new(self, tracking_service, sample_request):
        """Test storing new authorization request."""
        with patch.object(tracking_service, 'database') as mock_db:
            mock_db.store_request.return_value = "req_123456"
            
            request_id = await tracking_service.store_request(sample_request)
            
            assert isinstance(request_id, str)
            assert request_id.startswith("req_")
            mock_db.store_request.assert_called_once()
    
    @pytest.mark.asyncio

    
    async def test_store_request_with_metadata(self, tracking_service, sample_request):
        """Test storing request with additional metadata."""
        metadata = {
            "provider_id": "PROV123",
            "facility_id": "FAC456",
            "submission_source": "web_portal"
        }
        
        with patch.object(tracking_service, 'database') as mock_db:
            mock_db.store_request.return_value = "req_123456"
            
            request_id = await tracking_service.store_request(sample_request, metadata)
            
            assert isinstance(request_id, str)
            mock_db.store_request.assert_called_once_with(sample_request, metadata)
    
    @pytest.mark.asyncio

    
    async def test_get_request_by_id_found(self, tracking_service):
        """Test retrieving request by ID when found."""
        request_id = "req_123456"
        expected_request = {
            "request_id": request_id,
            "status": RequestStatus.SUBMITTED,
            "created_at": datetime.now(timezone.utc),
            "patient_id": "TEST123456"
        }
        
        with patch.object(tracking_service, 'database') as mock_db:
            mock_db.get_request.return_value = expected_request
            
            result = await tracking_service.get_request_by_id(request_id)
            
            assert result is not None
            assert result["request_id"] == request_id
            assert result["status"] == RequestStatus.SUBMITTED
    
    @pytest.mark.asyncio

    
    async def test_get_request_by_id_not_found(self, tracking_service):
        """Test retrieving request by ID when not found."""
        request_id = "req_nonexistent"
        
        with patch.object(tracking_service, 'database') as mock_db:
            mock_db.get_request.return_value = None
            
            result = await tracking_service.get_request_by_id(request_id)
            
            assert result is None
    
    @pytest.mark.asyncio

    
    async def test_update_status_valid_transition(self, tracking_service):
        """Test updating request status with valid transition."""
        request_id = "req_123456"
        new_status = RequestStatus.IN_REVIEW
        
        with patch.object(tracking_service, '_validate_status_transition') as mock_validate, \
             patch.object(tracking_service, 'database') as mock_db:
            
            mock_validate.return_value = True
            mock_db.update_status.return_value = True
            
            result = await tracking_service.update_status(request_id, new_status)
            
            assert result is True
            mock_validate.assert_called_once()
            mock_db.update_status.assert_called_once_with(request_id, new_status, None)
    
    @pytest.mark.asyncio

    
    async def test_update_status_invalid_transition(self, tracking_service):
        """Test updating request status with invalid transition."""
        request_id = "req_123456"
        new_status = RequestStatus.APPROVED
        
        with patch.object(tracking_service, '_validate_status_transition') as mock_validate:
            mock_validate.return_value = False
            
            with pytest.raises(ValueError, match="Invalid status transition"):
                await tracking_service.update_status(request_id, new_status)
    
    @pytest.mark.asyncio

    
    async def test_update_status_with_reason(self, tracking_service):
        """Test updating request status with reason."""
        request_id = "req_123456"
        new_status = RequestStatus.DENIED
        reason = "Insufficient medical necessity"
        
        with patch.object(tracking_service, '_validate_status_transition') as mock_validate, \
             patch.object(tracking_service, 'database') as mock_db:
            
            mock_validate.return_value = True
            mock_db.update_status.return_value = True
            
            result = await tracking_service.update_status(request_id, new_status, reason)
            
            assert result is True
            mock_db.update_status.assert_called_once_with(request_id, new_status, reason)
    
    @pytest.mark.asyncio

    
    async def test_get_request_history(self, tracking_service):
        """Test retrieving request status history."""
        request_id = "req_123456"
        expected_history = [
            {
                "status": RequestStatus.SUBMITTED,
                "timestamp": datetime.now(timezone.utc) - timedelta(hours=2),
                "reason": None
            },
            {
                "status": RequestStatus.IN_REVIEW,
                "timestamp": datetime.now(timezone.utc) - timedelta(hours=1),
                "reason": "Assigned to reviewer"
            },
            {
                "status": RequestStatus.APPROVED,
                "timestamp": datetime.now(timezone.utc),
                "reason": "Meets medical necessity criteria"
            }
        ]
        
        with patch.object(tracking_service, 'database') as mock_db:
            mock_db.get_request_history.return_value = expected_history
            
            history = await tracking_service.get_request_history(request_id)
            
            assert isinstance(history, list)
            assert len(history) == 3
            assert history[0]["status"] == RequestStatus.SUBMITTED
            assert history[-1]["status"] == RequestStatus.APPROVED
    
    @pytest.mark.asyncio

    
    async def test_get_requests_by_status(self, tracking_service):
        """Test retrieving requests by status."""
        status = RequestStatus.IN_REVIEW
        expected_requests = [
            {"request_id": "req_123456", "status": status},
            {"request_id": "req_789012", "status": status}
        ]
        
        with patch.object(tracking_service, 'database') as mock_db:
            mock_db.get_requests_by_status.return_value = expected_requests
            
            requests = await tracking_service.get_requests_by_status(status)
            
            assert isinstance(requests, list)
            assert len(requests) == 2
            assert all(req["status"] == status for req in requests)
    
    @pytest.mark.asyncio

    
    async def test_get_requests_by_patient(self, tracking_service):
        """Test retrieving requests by patient."""
        member_id = "TEST123456"
        expected_requests = [
            {"request_id": "req_123456", "member_id": member_id},
            {"request_id": "req_789012", "member_id": member_id}
        ]
        
        with patch.object(tracking_service, 'database') as mock_db:
            mock_db.get_requests_by_patient.return_value = expected_requests
            
            requests = await tracking_service.get_requests_by_patient(member_id)
            
            assert isinstance(requests, list)
            assert len(requests) == 2
            assert all(req["member_id"] == member_id for req in requests)
    
    @pytest.mark.asyncio

    
    async def test_store_decision(self, tracking_service):
        """Test storing decision for request."""
        request_id = "req_123456"
        decision = {
            "decision_id": "dec_789012",
            "status": "approved",
            "authorization_number": "AUTH123456",
            "reasoning": ["Meets medical necessity criteria"],
            "created_at": datetime.now(timezone.utc)
        }
        
        with patch.object(tracking_service, 'database') as mock_db:
            mock_db.store_decision.return_value = True
            
            result = await tracking_service.store_decision(request_id, decision)
            
            assert result is True
            mock_db.store_decision.assert_called_once_with(request_id, decision)
    
    @pytest.mark.asyncio

    
    async def test_get_decision_by_request_id(self, tracking_service):
        """Test retrieving decision by request ID."""
        request_id = "req_123456"
        expected_decision = {
            "decision_id": "dec_789012",
            "request_id": request_id,
            "status": "approved",
            "authorization_number": "AUTH123456"
        }
        
        with patch.object(tracking_service, 'database') as mock_db:
            mock_db.get_decision_by_request.return_value = expected_decision
            
            decision = await tracking_service.get_decision_by_request_id(request_id)
            
            assert decision is not None
            assert decision["request_id"] == request_id
            assert decision["status"] == "approved"
    
    def test_validate_status_transition_valid(self, tracking_service):
        """Test valid status transitions."""
        valid_transitions = [
            (RequestStatus.SUBMITTED, RequestStatus.IN_REVIEW),
            (RequestStatus.IN_REVIEW, RequestStatus.APPROVED),
            (RequestStatus.IN_REVIEW, RequestStatus.DENIED),
            (RequestStatus.IN_REVIEW, RequestStatus.PENDING),
            (RequestStatus.PENDING, RequestStatus.APPROVED),
            (RequestStatus.PENDING, RequestStatus.DENIED)
        ]
        
        for current, new in valid_transitions:
            result = tracking_service._validate_status_transition(current, new)
            assert result is True, f"Transition from {current} to {new} should be valid"
    
    def test_validate_status_transition_invalid(self, tracking_service):
        """Test invalid status transitions."""
        invalid_transitions = [
            (RequestStatus.APPROVED, RequestStatus.DENIED),
            (RequestStatus.DENIED, RequestStatus.APPROVED),
            (RequestStatus.APPROVED, RequestStatus.IN_REVIEW),
            (RequestStatus.DENIED, RequestStatus.IN_REVIEW)
        ]
        
        for current, new in invalid_transitions:
            result = tracking_service._validate_status_transition(current, new)
            assert result is False, f"Transition from {current} to {new} should be invalid"
    
    def test_generate_request_id(self, tracking_service):
        """Test request ID generation."""
        request_id = tracking_service._generate_request_id()
        
        assert isinstance(request_id, str)
        assert request_id.startswith("req_")
        assert len(request_id) > 4
    
    def test_generate_request_id_uniqueness(self, tracking_service):
        """Test request ID uniqueness."""
        ids = set()
        for _ in range(100):
            request_id = tracking_service._generate_request_id()
            assert request_id not in ids, "Request IDs should be unique"
            ids.add(request_id)
    
    @pytest.mark.asyncio

    
    async def test_create_tracking_record(self, tracking_service):
        """Test creating tracking record."""
        request_id = "req_123456"
        status = RequestStatus.IN_REVIEW
        reason = "Assigned to reviewer"
        
        record = await tracking_service._create_tracking_record(request_id, status, reason)
        
        assert isinstance(record, TrackingRecord)
        assert record.request_id == request_id
        assert record.status == status
        assert record.reason == reason
        assert record.timestamp is not None
    
    @pytest.mark.asyncio

    
    async def test_get_request_metrics(self, tracking_service):
        """Test retrieving request metrics."""
        expected_metrics = {
            "total_requests": 100,
            "submitted": 20,
            "in_review": 30,
            "approved": 35,
            "denied": 10,
            "pending": 5,
            "average_processing_time": 2.5  # hours
        }
        
        with patch.object(tracking_service, 'database') as mock_db:
            mock_db.get_request_metrics.return_value = expected_metrics
            
            metrics = await tracking_service.get_request_metrics()
            
            assert isinstance(metrics, dict)
            assert metrics["total_requests"] == 100
            assert metrics["approved"] == 35
            assert "average_processing_time" in metrics
    
    @pytest.mark.asyncio

    
    async def test_get_request_metrics_by_date_range(self, tracking_service):
        """Test retrieving request metrics by date range."""
        start_date = datetime.now(timezone.utc) - timedelta(days=30)
        end_date = datetime.now(timezone.utc)
        
        expected_metrics = {
            "total_requests": 50,
            "approved": 30,
            "denied": 15,
            "pending": 5
        }
        
        with patch.object(tracking_service, 'database') as mock_db:
            mock_db.get_request_metrics_by_date.return_value = expected_metrics
            
            metrics = await tracking_service.get_request_metrics(start_date, end_date)
            
            assert isinstance(metrics, dict)
            assert metrics["total_requests"] == 50
            mock_db.get_request_metrics_by_date.assert_called_once_with(start_date, end_date)
    
    @pytest.mark.asyncio

    
    async def test_search_requests(self, tracking_service):
        """Test searching requests with filters."""
        filters = {
            "status": RequestStatus.IN_REVIEW,
            "procedure_type": ProcedureType.MRI,
            "urgency_level": UrgencyLevel.URGENT
        }
        
        expected_results = [
            {"request_id": "req_123456", "status": RequestStatus.IN_REVIEW},
            {"request_id": "req_789012", "status": RequestStatus.IN_REVIEW}
        ]
        
        with patch.object(tracking_service, 'database') as mock_db:
            mock_db.search_requests.return_value = expected_results
            
            results = await tracking_service.search_requests(filters)
            
            assert isinstance(results, list)
            assert len(results) == 2
            mock_db.search_requests.assert_called_once_with(filters)
    
    @pytest.mark.asyncio

    
    async def test_bulk_update_status(self, tracking_service):
        """Test bulk status update for multiple requests."""
        request_ids = ["req_123456", "req_789012", "req_345678"]
        new_status = RequestStatus.IN_REVIEW
        reason = "Batch assignment to reviewers"
        
        with patch.object(tracking_service, '_validate_status_transition') as mock_validate, \
             patch.object(tracking_service, 'database') as mock_db:
            
            mock_validate.return_value = True
            mock_db.bulk_update_status.return_value = {"updated": 3, "failed": 0}
            
            result = await tracking_service.bulk_update_status(request_ids, new_status, reason)
            
            assert result["updated"] == 3
            assert result["failed"] == 0
            mock_db.bulk_update_status.assert_called_once_with(request_ids, new_status, reason)
    
    @pytest.mark.asyncio

    
    async def test_get_processing_time_stats(self, tracking_service):
        """Test retrieving processing time statistics."""
        expected_stats = {
            "average_time": 2.5,  # hours
            "median_time": 2.0,
            "min_time": 0.5,
            "max_time": 8.0,
            "percentile_95": 6.0
        }
        
        with patch.object(tracking_service, 'database') as mock_db:
            mock_db.get_processing_time_stats.return_value = expected_stats
            
            stats = await tracking_service.get_processing_time_stats()
            
            assert isinstance(stats, dict)
            assert stats["average_time"] == 2.5
            assert stats["median_time"] == 2.0
            assert "percentile_95" in stats


class TestTrackingRecord:
    """Test TrackingRecord model."""
    
    def test_tracking_record_creation(self):
        """Test TrackingRecord creation."""
        record = TrackingRecord(
            request_id="req_123456",
            status=RequestStatus.IN_REVIEW,
            timestamp=datetime.now(timezone.utc),
            reason="Assigned to reviewer"
        )
        
        assert record.request_id == "req_123456"
        assert record.status == RequestStatus.IN_REVIEW
        assert record.reason == "Assigned to reviewer"
        assert record.timestamp is not None
    
    def test_tracking_record_serialization(self):
        """Test TrackingRecord serialization."""
        record = TrackingRecord(
            request_id="req_123456",
            status=RequestStatus.IN_REVIEW,
            timestamp=datetime.now(timezone.utc),
            reason="Assigned to reviewer"
        )
        
        serialized = record.dict()
        
        assert isinstance(serialized, dict)
        assert serialized["request_id"] == "req_123456"
        assert serialized["status"] == RequestStatus.IN_REVIEW
        assert serialized["reason"] == "Assigned to reviewer"


class TestRequestStatus:
    """Test RequestStatus enum."""
    
    def test_request_status_values(self):
        """Test RequestStatus enum values."""
        assert RequestStatus.SUBMITTED == "submitted"
        assert RequestStatus.IN_REVIEW == "in_review"
        assert RequestStatus.APPROVED == "approved"
        assert RequestStatus.DENIED == "denied"
        assert RequestStatus.PENDING == "pending"
    
    def test_request_status_comparison(self):
        """Test RequestStatus comparison."""
        assert RequestStatus.SUBMITTED != RequestStatus.APPROVED
        assert RequestStatus.IN_REVIEW == RequestStatus.IN_REVIEW


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
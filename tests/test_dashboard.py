"""
Tests for provider dashboard API endpoints.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch, call
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.dashboard import router, DashboardSummary, RequestSummary, FilteredRequestsResponse, ActivityMetrics
from src.models.enums import RequestStatus, ProcedureType, UrgencyLevel
from src.services.tracking import TrackingService, RequestStatusInfo, ProviderRequestsResponse


@pytest.fixture
def client():
    """Create test client."""
    from src.main import app
    return TestClient(app)


@pytest.fixture
def mock_tracking_service():
    """Create mock tracking service."""
    return Mock(spec=TrackingService)


@pytest.fixture
def sample_request_info():
    """Create sample request status info."""
    return RequestStatusInfo(
        request_id="req_2024_001234",
        status=RequestStatus.IN_REVIEW,
        submitted_at=datetime.now(timezone.utc) - timedelta(hours=2),
        updated_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        estimated_completion=datetime.now(timezone.utc) + timedelta(hours=1),
        current_stage="Policy Validation",
        progress_percentage=65,
        next_actions=["Review clinical notes", "Validate procedure codes"]
    )


@pytest.fixture
def sample_provider_response(sample_request_info):
    """Create sample provider requests response."""
    return ProviderRequestsResponse(
        requests=[sample_request_info],
        total_count=1,
        status_summary={
            RequestStatus.SUBMITTED.value: 5,
            RequestStatus.IN_REVIEW.value: 10,
            RequestStatus.APPROVED.value: 120,
            RequestStatus.DENIED.value: 15,
            RequestStatus.MORE_INFO_NEEDED.value: 3
        }
    )


class TestDashboardSummary:
    """Test dashboard summary endpoint."""
    
    def test_get_dashboard_summary_success(
        self,
        client,
        mock_tracking_service,
        sample_provider_response
    ):
        """Test successful dashboard summary retrieval."""
        # Setup
        from src.api.dashboard import get_tracking_service
        from src.main import app
        
        mock_tracking_service.get_requests_by_provider = AsyncMock(
            return_value=sample_provider_response
        )
        
        # Override the dependency
        app.dependency_overrides[get_tracking_service] = lambda: mock_tracking_service
        
        try:
            # Execute
            response = client.get("/api/v1/dashboard/summary/prov_12345")
            
            # Verify
            assert response.status_code == 200
            data = response.json()
            
            assert data["provider_id"] == "prov_12345"
            assert data["total_requests"] == 1
            assert data["pending_requests"] == 15  # submitted + in_review
            assert data["approved_requests"] == 120
            assert data["denied_requests"] == 15
            assert data["requests_needing_info"] == 3
            assert "average_processing_time_hours" in data
            assert "approval_rate_percentage" in data
        finally:
            # Clean up
            app.dependency_overrides.clear()
        assert "recent_activity_count" in data
        assert "urgent_requests_count" in data
        
        # Verify service was called correctly (called twice - once for main data, once for urgent count)
        assert mock_tracking_service.get_requests_by_provider.call_count == 2
        mock_tracking_service.get_requests_by_provider.assert_has_calls([
            call(provider_id="prov_12345", limit=1000),
            call(provider_id="prov_12345", limit=1000)
        ])
    
    @patch('src.api.dashboard.get_tracking_service')
    @pytest.mark.asyncio
    async def test_get_dashboard_summary_empty_provider_id(
        self,
        mock_get_service,
        client,
        mock_tracking_service
    ):
        """Test dashboard summary with empty provider ID."""
        # Setup
        mock_get_service.return_value = mock_tracking_service
        
        # Execute
        response = client.get("/api/v1/dashboard/summary/")
        
        # Verify - should return 404 for missing path parameter
        assert response.status_code == 404


class TestFilteredRequests:
    """Test filtered requests endpoint."""
    
    def test_get_filtered_requests_success(
        self,
        client,
        mock_tracking_service,
        sample_provider_response
    ):
        """Test successful filtered requests retrieval."""
        # Setup
        from src.api.dashboard import get_tracking_service
        from src.main import app
        
        mock_tracking_service.get_requests_by_provider = AsyncMock(
            return_value=sample_provider_response
        )
        
        # Override the dependency
        app.dependency_overrides[get_tracking_service] = lambda: mock_tracking_service
        
        try:
            # Execute
            response = client.get("/api/v1/dashboard/requests/prov_12345")
            
            # Verify
            assert response.status_code == 200
            data = response.json()
            
            assert len(data["requests"]) == 1
            assert data["total_count"] == 1
            assert data["page"] == 1
            assert data["page_size"] == 20
            assert data["total_pages"] == 1
            assert data["filters_applied"] == {}
        finally:
            # Clean up
            app.dependency_overrides.clear()
        
        # Verify request structure
        request_data = data["requests"][0]
        assert request_data["request_id"] == "req_2024_001234"
        assert request_data["status"] == "in_review"
        assert "submitted_at" in request_data
        assert "updated_at" in request_data
        assert "current_stage" in request_data
        assert "progress_percentage" in request_data


class TestActivityMetrics:
    """Test activity metrics endpoint."""
    
    @patch('src.api.dashboard.get_tracking_service')
    @pytest.mark.asyncio
    async def test_get_activity_metrics_success(
        self,
        mock_get_service,
        client,
        mock_tracking_service,
        sample_provider_response
    ):
        """Test successful activity metrics retrieval."""
        # Setup
        mock_get_service.return_value = mock_tracking_service
        mock_tracking_service.get_requests_by_provider = AsyncMock(
            return_value=sample_provider_response
        )
        
        # Execute
        response = client.get("/api/v1/dashboard/metrics/prov_12345")
        
        # Verify
        assert response.status_code == 200
        data = response.json()
        
        assert "daily_submissions" in data
        assert "status_distribution" in data
        assert "procedure_type_breakdown" in data
        assert "processing_time_trends" in data
        
        # Verify structure
        assert isinstance(data["daily_submissions"], list)
        assert isinstance(data["status_distribution"], dict)
        assert isinstance(data["procedure_type_breakdown"], dict)
        assert isinstance(data["processing_time_trends"], list)


class TestDataModels:
    """Test data model validation."""
    
    def test_dashboard_summary_model(self):
        """Test DashboardSummary model validation."""
        summary = DashboardSummary(
            provider_id="prov_12345",
            total_requests=150,
            pending_requests=12,
            approved_requests=120,
            denied_requests=15,
            requests_needing_info=3,
            average_processing_time_hours=1.5,
            approval_rate_percentage=88.2,
            recent_activity_count=8,
            urgent_requests_count=2
        )
        
        assert summary.provider_id == "prov_12345"
        assert summary.total_requests == 150
        assert summary.approval_rate_percentage == 88.2


if __name__ == "__main__":
    pytest.main([__file__])
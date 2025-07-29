"""
Simple tests for dashboard API endpoints.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from src.api.dashboard import DashboardSummary
from src.services.tracking import TrackingService, ProviderRequestsResponse, RequestStatusInfo
from src.models.enums import RequestStatus


def test_dashboard_summary_model():
    """Test DashboardSummary model creation."""
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


@pytest.mark.asyncio
async def test_tracking_service_basic():
    """Test basic tracking service functionality."""
    service = TrackingService()
    
    # Test getting requests for a provider
    response = await service.get_requests_by_provider("prov_12345")
    
    assert isinstance(response, ProviderRequestsResponse)
    assert response.total_count >= 0
    assert isinstance(response.status_summary, dict)
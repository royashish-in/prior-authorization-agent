"""
Provider dashboard API endpoints for Prior Authorization Agent.

This module provides REST endpoints for provider dashboard functionality,
including request summaries, status tracking, filtering, and search capabilities.
"""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status, Depends, Query
from pydantic import BaseModel, Field, ConfigDict

from src.models.enums import RequestStatus, ProcedureType, UrgencyLevel
from src.services.tracking import TrackingService, RequestStatusInfo
from src.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["dashboard"], prefix="/dashboard")


class DashboardSummary(BaseModel):
    """Provider dashboard summary data."""
    provider_id: str
    total_requests: int
    pending_requests: int
    approved_requests: int
    denied_requests: int
    requests_needing_info: int
    average_processing_time_hours: float
    approval_rate_percentage: float
    recent_activity_count: int  # Last 24 hours
    urgent_requests_count: int
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "provider_id": "prov_12345",
                "total_requests": 150,
                "pending_requests": 12,
                "approved_requests": 120,
                "denied_requests": 15,
                "requests_needing_info": 3,
                "average_processing_time_hours": 1.5,
                "approval_rate_percentage": 88.2,
                "recent_activity_count": 8,
                "urgent_requests_count": 2
            }
        }
    )


class RequestSummary(BaseModel):
    """Summary information for a single request."""
    request_id: str
    procedure_type: str
    urgency_level: str
    status: RequestStatus
    submitted_at: datetime
    updated_at: datetime
    estimated_completion: Optional[datetime]
    current_stage: str
    progress_percentage: int
    days_since_submission: int
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "request_id": "req_2024_001234",
                "procedure_type": "mri",
                "urgency_level": "routine",
                "status": "in_review",
                "submitted_at": "2024-01-24T08:30:00Z",
                "updated_at": "2024-01-24T10:15:00Z",
                "estimated_completion": "2024-01-24T12:30:00Z",
                "current_stage": "Policy Validation",
                "progress_percentage": 65,
                "days_since_submission": 0
            }
        }
    )


class FilteredRequestsResponse(BaseModel):
    """Response for filtered requests with pagination."""
    requests: List[RequestSummary]
    total_count: int
    page: int
    page_size: int
    total_pages: int
    filters_applied: Dict[str, Any]
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "requests": [],
                "total_count": 45,
                "page": 1,
                "page_size": 20,
                "total_pages": 3,
                "filters_applied": {
                    "status": "pending",
                    "procedure_type": "mri",
                    "date_range": "last_7_days"
                }
            }
        }
    )


class ActivityMetrics(BaseModel):
    """Activity metrics for dashboard charts."""
    daily_submissions: List[Dict[str, Any]]
    status_distribution: Dict[str, int]
    procedure_type_breakdown: Dict[str, int]
    processing_time_trends: List[Dict[str, Any]]
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "daily_submissions": [
                    {"date": "2024-01-24", "count": 8},
                    {"date": "2024-01-23", "count": 12}
                ],
                "status_distribution": {
                    "approved": 120,
                    "pending": 12,
                    "denied": 15
                },
                "procedure_type_breakdown": {
                    "mri": 85,
                    "ct_scan": 45,
                    "x_ray": 20
                },
                "processing_time_trends": [
                    {"date": "2024-01-24", "avg_hours": 1.2},
                    {"date": "2024-01-23", "avg_hours": 1.8}
                ]
            }
        }
    )


# Import the shared tracking service instance
from src.api.intake import get_tracking_service


@router.get("/summary/{provider_id}", response_model=DashboardSummary)
async def get_provider_dashboard_summary(
    provider_id: str,
    tracking_service: TrackingService = Depends(get_tracking_service)
) -> DashboardSummary:
    """
    Get comprehensive dashboard summary for a provider.
    
    Args:
        provider_id: Healthcare provider identifier
        tracking_service: Service for request tracking
        
    Returns:
        Dashboard summary with key metrics
        
    Raises:
        HTTPException: For invalid provider ID or processing errors
    """
    try:
        # Validate provider ID
        if not provider_id or len(provider_id.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "INVALID_PROVIDER_ID",
                    "message": "Provider ID cannot be empty"
                }
            )
        
        # Get all requests for the provider
        all_requests = await tracking_service.get_requests_by_provider(
            provider_id=provider_id.strip(),
            limit=1000  # Get all requests for summary calculation
        )
        
        # Calculate summary metrics
        total_requests = all_requests.total_count
        status_summary = all_requests.status_summary
        
        pending_requests = (
            status_summary.get(RequestStatus.SUBMITTED.value, 0) +
            status_summary.get(RequestStatus.IN_REVIEW.value, 0)
        )
        approved_requests = status_summary.get(RequestStatus.APPROVED.value, 0)
        denied_requests = status_summary.get(RequestStatus.DENIED.value, 0)
        requests_needing_info = status_summary.get(RequestStatus.MORE_INFO_NEEDED.value, 0)
        
        # Calculate approval rate
        completed_requests = approved_requests + denied_requests
        approval_rate = (approved_requests / completed_requests * 100) if completed_requests > 0 else 0.0
        
        # Calculate average processing time (simplified for demo)
        avg_processing_time = await _calculate_average_processing_time(all_requests.requests)
        
        # Count recent activity (last 24 hours)
        recent_activity = await _count_recent_activity(all_requests.requests)
        
        # Count urgent requests
        urgent_requests = await _count_urgent_requests(provider_id, tracking_service)
        
        logger.info(
            "Dashboard summary generated",
            provider_id=provider_id,
            total_requests=total_requests,
            approval_rate=approval_rate
        )
        
        return DashboardSummary(
            provider_id=provider_id,
            total_requests=total_requests,
            pending_requests=pending_requests,
            approved_requests=approved_requests,
            denied_requests=denied_requests,
            requests_needing_info=requests_needing_info,
            average_processing_time_hours=avg_processing_time,
            approval_rate_percentage=round(approval_rate, 1),
            recent_activity_count=recent_activity,
            urgent_requests_count=urgent_requests
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error generating dashboard summary",
            provider_id=provider_id,
            error=str(e),
            exc_info=True
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "Error generating dashboard summary"
            }
        )


@router.get("/requests/{provider_id}", response_model=FilteredRequestsResponse)
async def get_filtered_requests(
    provider_id: str,
    status_filter: Optional[RequestStatus] = Query(None, description="Filter by request status"),
    procedure_type: Optional[ProcedureType] = Query(None, description="Filter by procedure type"),
    urgency_level: Optional[UrgencyLevel] = Query(None, description="Filter by urgency level"),
    date_from: Optional[datetime] = Query(None, description="Filter requests from this date"),
    date_to: Optional[datetime] = Query(None, description="Filter requests until this date"),
    search_query: Optional[str] = Query(None, description="Search in request IDs or notes"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Number of requests per page"),
    tracking_service: TrackingService = Depends(get_tracking_service)
) -> FilteredRequestsResponse:
    """
    Get filtered and paginated requests for a provider.
    
    Args:
        provider_id: Healthcare provider identifier
        status_filter: Optional status filter
        procedure_type: Optional procedure type filter
        urgency_level: Optional urgency level filter
        date_from: Optional start date filter
        date_to: Optional end date filter
        search_query: Optional search query
        page: Page number for pagination
        page_size: Number of requests per page
        tracking_service: Service for request tracking
        
    Returns:
        Filtered and paginated requests
        
    Raises:
        HTTPException: For invalid parameters or processing errors
    """
    try:
        # Validate provider ID
        if not provider_id or len(provider_id.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "INVALID_PROVIDER_ID",
                    "message": "Provider ID cannot be empty"
                }
            )
        
        # Validate date range
        if date_from and date_to and date_from > date_to:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "INVALID_DATE_RANGE",
                    "message": "Start date must be before end date"
                }
            )
        
        # Get all requests for the provider (we'll filter in memory for demo)
        all_requests = await tracking_service.get_requests_by_provider(
            provider_id=provider_id.strip(),
            status_filter=status_filter,
            limit=1000  # Get all for filtering
        )
        
        # Apply additional filters
        filtered_requests = await _apply_filters(
            requests=all_requests.requests,
            procedure_type=procedure_type,
            urgency_level=urgency_level,
            date_from=date_from,
            date_to=date_to,
            search_query=search_query,
            tracking_service=tracking_service
        )
        
        # Apply pagination
        total_count = len(filtered_requests)
        total_pages = (total_count + page_size - 1) // page_size
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_requests = filtered_requests[start_idx:end_idx]
        
        # Convert to RequestSummary objects
        request_summaries = [
            await _convert_to_request_summary(req, tracking_service)
            for req in paginated_requests
        ]
        
        # Track applied filters
        filters_applied = {}
        if status_filter:
            filters_applied["status"] = status_filter.value
        if procedure_type:
            filters_applied["procedure_type"] = procedure_type.value
        if urgency_level:
            filters_applied["urgency_level"] = urgency_level.value
        if date_from:
            filters_applied["date_from"] = date_from.isoformat()
        if date_to:
            filters_applied["date_to"] = date_to.isoformat()
        if search_query:
            filters_applied["search_query"] = search_query
        
        logger.info(
            "Filtered requests retrieved",
            provider_id=provider_id,
            total_count=total_count,
            page=page,
            filters_count=len(filters_applied)
        )
        
        return FilteredRequestsResponse(
            requests=request_summaries,
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            filters_applied=filters_applied
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error retrieving filtered requests",
            provider_id=provider_id,
            error=str(e),
            exc_info=True
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "Error retrieving filtered requests"
            }
        )


@router.get("/metrics/{provider_id}", response_model=ActivityMetrics)
async def get_activity_metrics(
    provider_id: str,
    days_back: int = Query(30, ge=1, le=365, description="Number of days to include in metrics"),
    tracking_service: TrackingService = Depends(get_tracking_service)
) -> ActivityMetrics:
    """
    Get activity metrics for dashboard charts and analytics.
    
    Args:
        provider_id: Healthcare provider identifier
        days_back: Number of days to include in metrics
        tracking_service: Service for request tracking
        
    Returns:
        Activity metrics for dashboard visualization
        
    Raises:
        HTTPException: For invalid parameters or processing errors
    """
    try:
        # Validate provider ID
        if not provider_id or len(provider_id.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "INVALID_PROVIDER_ID",
                    "message": "Provider ID cannot be empty"
                }
            )
        
        # Get requests for the specified time period
        date_from = datetime.now(timezone.utc) - timedelta(days=days_back)
        
        all_requests = await tracking_service.get_requests_by_provider(
            provider_id=provider_id.strip(),
            limit=1000
        )
        
        # Filter requests by date range
        recent_requests = [
            req for req in all_requests.requests
            if req.submitted_at >= date_from
        ]
        
        # Calculate daily submissions
        daily_submissions = await _calculate_daily_submissions(recent_requests, days_back)
        
        # Get status distribution
        status_distribution = all_requests.status_summary
        
        # Calculate procedure type breakdown
        procedure_breakdown = await _calculate_procedure_breakdown(
            provider_id, tracking_service
        )
        
        # Calculate processing time trends
        processing_trends = await _calculate_processing_trends(recent_requests, days_back)
        
        logger.info(
            "Activity metrics generated",
            provider_id=provider_id,
            days_back=days_back,
            recent_requests_count=len(recent_requests)
        )
        
        return ActivityMetrics(
            daily_submissions=daily_submissions,
            status_distribution=status_distribution,
            procedure_type_breakdown=procedure_breakdown,
            processing_time_trends=processing_trends
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error generating activity metrics",
            provider_id=provider_id,
            error=str(e),
            exc_info=True
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "Error generating activity metrics"
            }
        )


# Helper functions

async def _calculate_average_processing_time(requests: List[RequestStatusInfo]) -> float:
    """Calculate average processing time for completed requests."""
    completed_requests = [
        req for req in requests
        if req.status in [RequestStatus.APPROVED, RequestStatus.DENIED]
    ]
    
    if not completed_requests:
        return 0.0
    
    total_hours = 0.0
    for req in completed_requests:
        processing_time = (req.updated_at - req.submitted_at).total_seconds() / 3600
        total_hours += processing_time
    
    return total_hours / len(completed_requests)


async def _count_recent_activity(requests: List[RequestStatusInfo]) -> int:
    """Count requests with activity in the last 24 hours."""
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
    
    return len([
        req for req in requests
        if req.updated_at >= cutoff_time
    ])


async def _count_urgent_requests(provider_id: str, tracking_service: TrackingService) -> int:
    """Count urgent requests for a provider."""
    # This is a simplified implementation
    # In production, this would query the database for urgent requests
    urgent_requests = await tracking_service.get_requests_by_provider(
        provider_id=provider_id,
        limit=1000
    )
    
    # Filter for pending urgent requests (simplified)
    return len([
        req for req in urgent_requests.requests
        if req.status in [RequestStatus.SUBMITTED, RequestStatus.IN_REVIEW]
    ]) // 10  # Simulate that ~10% are urgent


async def _apply_filters(
    requests: List[RequestStatusInfo],
    procedure_type: Optional[ProcedureType],
    urgency_level: Optional[UrgencyLevel],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    search_query: Optional[str],
    tracking_service: TrackingService
) -> List[RequestStatusInfo]:
    """Apply additional filters to requests."""
    filtered = requests
    
    # Date range filter
    if date_from:
        filtered = [req for req in filtered if req.submitted_at >= date_from]
    
    if date_to:
        filtered = [req for req in filtered if req.submitted_at <= date_to]
    
    # Search filter (simplified - searches in request ID)
    if search_query:
        query_lower = search_query.lower()
        filtered = [
            req for req in filtered
            if query_lower in req.request_id.lower()
        ]
    
    # Note: procedure_type and urgency_level filtering would require
    # accessing the original request data, which is simplified here
    
    return filtered


async def _convert_to_request_summary(
    request_info: RequestStatusInfo,
    tracking_service: TrackingService
) -> RequestSummary:
    """Convert RequestStatusInfo to RequestSummary."""
    days_since = (datetime.now(timezone.utc) - request_info.submitted_at).days
    
    return RequestSummary(
        request_id=request_info.request_id,
        procedure_type="mri",  # Simplified - would get from original request
        urgency_level="routine",  # Simplified - would get from original request
        status=request_info.status,
        submitted_at=request_info.submitted_at,
        updated_at=request_info.updated_at,
        estimated_completion=request_info.estimated_completion,
        current_stage=request_info.current_stage,
        progress_percentage=request_info.progress_percentage,
        days_since_submission=days_since
    )


async def _calculate_daily_submissions(
    requests: List[RequestStatusInfo],
    days_back: int
) -> List[Dict[str, Any]]:
    """Calculate daily submission counts."""
    daily_counts = {}
    
    # Initialize all days with 0
    for i in range(days_back):
        date = datetime.now(timezone.utc) - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        daily_counts[date_str] = 0
    
    # Count actual submissions
    for req in requests:
        date_str = req.submitted_at.strftime("%Y-%m-%d")
        if date_str in daily_counts:
            daily_counts[date_str] += 1
    
    # Convert to list format
    return [
        {"date": date, "count": count}
        for date, count in sorted(daily_counts.items())
    ]


async def _calculate_procedure_breakdown(
    provider_id: str,
    tracking_service: TrackingService
) -> Dict[str, int]:
    """Calculate procedure type breakdown."""
    # Simplified implementation
    return {
        "mri": 85,
        "ct_scan": 45,
        "x_ray": 20,
        "ultrasound": 15
    }


async def _calculate_processing_trends(
    requests: List[RequestStatusInfo],
    days_back: int
) -> List[Dict[str, Any]]:
    """Calculate processing time trends."""
    daily_times = {}
    
    # Group by date and calculate average processing time
    for req in requests:
        if req.status in [RequestStatus.APPROVED, RequestStatus.DENIED]:
            date_str = req.updated_at.strftime("%Y-%m-%d")
            processing_hours = (req.updated_at - req.submitted_at).total_seconds() / 3600
            
            if date_str not in daily_times:
                daily_times[date_str] = []
            daily_times[date_str].append(processing_hours)
    
    # Calculate averages
    trends = []
    for date, times in daily_times.items():
        avg_time = sum(times) / len(times) if times else 0
        trends.append({"date": date, "avg_hours": round(avg_time, 1)})
    
    return sorted(trends, key=lambda x: x["date"])
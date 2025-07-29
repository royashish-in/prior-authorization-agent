"""
Authorization decision API endpoints for Prior Authorization Agent.

This module provides REST endpoints for retrieving authorization decisions,
decision history, and decision reasoning with comprehensive audit support.
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, status, Depends, Query
from pydantic import BaseModel, Field

from src.models.authorization import AuthorizationDecision
from src.models.enums import DecisionStatus
from src.services.decision_engine import DecisionEngine
from src.api.intake import get_tracking_service
from src.services.tracking import TrackingService
from src.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["decisions"], prefix="/decisions")


class DecisionResponse(BaseModel):
    """Response model for authorization decisions."""
    decision_id: str
    request_id: str
    status: DecisionStatus
    reasoning: List[str]
    policy_references: List[str]
    authorization_number: Optional[str] = None
    valid_until: Optional[datetime] = None
    confidence_score: float
    decided_at: datetime
    decision_maker: str
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "decision_id": "dec_2024_001234",
                "request_id": "req_2024_001234",
                "status": "approved",
                "reasoning": [
                    "Medical necessity criteria met per CMS NCD 220.2",
                    "ICD-10 code G93.1 supports requested MRI procedure",
                    "Provider credentials verified and in-network"
                ],
                "policy_references": [
                    "CMS_NCD_220.2",
                    "PAYER_POLICY_MRI_001"
                ],
                "authorization_number": "AUTH2024001234",
                "valid_until": "2024-02-24T10:30:00Z",
                "confidence_score": 0.95,
                "decided_at": "2024-01-24T10:30:00Z",
                "decision_maker": "automated_engine"
            }
        }
    }


class DecisionHistoryResponse(BaseModel):
    """Response model for decision history queries."""
    decisions: List[DecisionResponse]
    total_count: int
    page: int
    page_size: int
    filters_applied: Dict[str, Any]


class DecisionSummaryResponse(BaseModel):
    """Response model for decision summary statistics."""
    provider_id: str
    total_decisions: int
    approval_rate: float
    average_processing_time_hours: float
    decisions_by_status: Dict[str, int]
    decisions_by_procedure: Dict[str, int]
    recent_decisions: List[DecisionResponse]


def get_decision_engine() -> DecisionEngine:
    """Dependency to get decision engine instance."""
    return DecisionEngine()


@router.get("/{decision_id}", response_model=DecisionResponse)
async def get_decision(
    decision_id: str,
    tracking_service: TrackingService = Depends(get_tracking_service)
) -> DecisionResponse:
    """
    Retrieve a specific authorization decision by ID.
    
    Args:
        decision_id: Unique decision identifier
        decision_engine: Service for decision management
        
    Returns:
        Authorization decision details
        
    Raises:
        HTTPException: If decision not found or access denied
    """
    try:
        # Validate decision ID format
        if not decision_id.startswith("dec_"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "INVALID_DECISION_ID",
                    "message": "Decision ID must start with 'dec_'",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
        
        # Retrieve decision from tracking service
        decision = await tracking_service.get_decision(decision_id)
        
        if not decision:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "DECISION_NOT_FOUND",
                    "message": f"Authorization decision {decision_id} not found",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
        
        logger.info(
            "Decision retrieved",
            decision_id=decision_id,
            status=decision.status
        )
        
        return DecisionResponse(
            decision_id=decision.decision_id,
            request_id=decision.request_id,
            status=decision.status,
            reasoning=decision.reasoning,
            policy_references=decision.policy_references,
            authorization_number=decision.authorization_number,
            valid_until=decision.valid_until,
            confidence_score=decision.confidence_score,
            decided_at=decision.decided_at,
            decision_maker="automated_engine"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error retrieving decision",
            decision_id=decision_id,
            error=str(e),
            exc_info=True
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "Error retrieving decision",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )


@router.get("/request/{request_id}", response_model=DecisionResponse)
async def get_decision_by_request(
    request_id: str,
    tracking_service: TrackingService = Depends(get_tracking_service)
) -> DecisionResponse:
    """
    Retrieve authorization decision for a specific request.
    
    Args:
        request_id: Authorization request identifier
        decision_engine: Service for decision management
        
    Returns:
        Authorization decision for the request
        
    Raises:
        HTTPException: If decision not found or request invalid
    """
    try:
        # Validate request ID format
        if not request_id.startswith("req_"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "INVALID_REQUEST_ID",
                    "message": "Request ID must start with 'req_'",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
        
        # Retrieve decision by request ID
        decision = await tracking_service.get_decision_by_request(request_id)
        
        if not decision:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "DECISION_NOT_FOUND",
                    "message": f"No decision found for request {request_id}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
        
        logger.info(
            "Decision retrieved by request ID",
            request_id=request_id,
            decision_id=decision.decision_id,
            status=decision.status
        )
        
        return DecisionResponse(
            decision_id=decision.decision_id,
            request_id=decision.request_id,
            status=decision.status,
            reasoning=decision.reasoning,
            policy_references=decision.policy_references,
            authorization_number=decision.authorization_number,
            valid_until=decision.valid_until,
            confidence_score=decision.confidence_score,
            decided_at=decision.decided_at,
            decision_maker="automated_engine"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error retrieving decision by request ID",
            request_id=request_id,
            error=str(e),
            exc_info=True
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "Error retrieving decision",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )


@router.get("/provider/{provider_id}/history", response_model=DecisionHistoryResponse)
async def get_provider_decision_history(
    provider_id: str,
    status_filter: Optional[DecisionStatus] = Query(None, description="Filter by decision status"),
    date_from: Optional[datetime] = Query(None, description="Filter decisions from this date"),
    date_to: Optional[datetime] = Query(None, description="Filter decisions until this date"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Number of decisions per page"),
    decision_engine: DecisionEngine = Depends(get_decision_engine)
) -> DecisionHistoryResponse:
    """
    Get decision history for a specific provider with filtering and pagination.
    
    Args:
        provider_id: Healthcare provider identifier
        status_filter: Optional status filter
        date_from: Optional start date filter
        date_to: Optional end date filter
        page: Page number for pagination
        page_size: Number of decisions per page
        decision_engine: Service for decision management
        
    Returns:
        Paginated decision history
        
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
                    "message": "Provider ID cannot be empty",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
        
        # Validate date range
        if date_from and date_to and date_from > date_to:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "INVALID_DATE_RANGE",
                    "message": "Start date must be before end date",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
        
        # Get decision history from decision engine
        history_result = await decision_engine.get_provider_decision_history(
            provider_id=provider_id.strip(),
            status_filter=status_filter,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size
        )
        
        # Convert to response format
        decision_responses = [
            DecisionResponse(
                decision_id=decision.decision_id,
                request_id=decision.request_id,
                status=decision.status,
                reasoning=decision.reasoning,
                policy_references=decision.policy_references,
                authorization_number=decision.authorization_number,
                valid_until=decision.valid_until,
                confidence_score=decision.confidence_score,
                decided_at=decision.decided_at,
                decision_maker="automated_engine"
            )
            for decision in history_result.decisions
        ]
        
        # Track applied filters
        filters_applied = {}
        if status_filter:
            filters_applied["status"] = status_filter.value
        if date_from:
            filters_applied["date_from"] = date_from.isoformat()
        if date_to:
            filters_applied["date_to"] = date_to.isoformat()
        
        logger.info(
            "Decision history retrieved",
            provider_id=provider_id,
            total_count=history_result.total_count,
            page=page,
            filters_count=len(filters_applied)
        )
        
        return DecisionHistoryResponse(
            decisions=decision_responses,
            total_count=history_result.total_count,
            page=page,
            page_size=page_size,
            filters_applied=filters_applied
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error retrieving decision history",
            provider_id=provider_id,
            error=str(e),
            exc_info=True
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "Error retrieving decision history",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )


@router.get("/provider/{provider_id}/summary", response_model=DecisionSummaryResponse)
async def get_provider_decision_summary(
    provider_id: str,
    days_back: int = Query(30, ge=1, le=365, description="Number of days to include in summary"),
    decision_engine: DecisionEngine = Depends(get_decision_engine)
) -> DecisionSummaryResponse:
    """
    Get decision summary statistics for a provider.
    
    Args:
        provider_id: Healthcare provider identifier
        days_back: Number of days to include in summary
        decision_engine: Service for decision management
        
    Returns:
        Decision summary statistics
        
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
                    "message": "Provider ID cannot be empty",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
        
        # Get decision summary from decision engine
        summary = await decision_engine.get_provider_decision_summary(
            provider_id=provider_id.strip(),
            days_back=days_back
        )
        
        # Get recent decisions
        recent_history = await decision_engine.get_provider_decision_history(
            provider_id=provider_id.strip(),
            page=1,
            page_size=5
        )
        
        recent_decisions = [
            DecisionResponse(
                decision_id=decision.decision_id,
                request_id=decision.request_id,
                status=decision.status,
                reasoning=decision.reasoning,
                policy_references=decision.policy_references,
                authorization_number=decision.authorization_number,
                valid_until=decision.valid_until,
                confidence_score=decision.confidence_score,
                decided_at=decision.decided_at,
                decision_maker="automated_engine"
            )
            for decision in recent_history.decisions
        ]
        
        logger.info(
            "Decision summary generated",
            provider_id=provider_id,
            days_back=days_back,
            total_decisions=summary.total_decisions
        )
        
        return DecisionSummaryResponse(
            provider_id=provider_id,
            total_decisions=summary.total_decisions,
            approval_rate=summary.approval_rate,
            average_processing_time_hours=summary.average_processing_time_hours,
            decisions_by_status=summary.decisions_by_status,
            decisions_by_procedure=summary.decisions_by_procedure,
            recent_decisions=recent_decisions
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error generating decision summary",
            provider_id=provider_id,
            error=str(e),
            exc_info=True
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "Error generating decision summary",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
@router.get("/by-request/{request_id}", response_model=DecisionResponse)
async def get_decision_by_request_alt(
    request_id: str,
    tracking_service: TrackingService = Depends(get_tracking_service)
) -> DecisionResponse:
    """
    Retrieve authorization decision by request ID (alternative endpoint).
    
    Args:
        request_id: Authorization request identifier
        tracking_service: Service for decision retrieval
        
    Returns:
        Authorization decision details
        
    Raises:
        HTTPException: If decision not found or access denied
    """
    return await get_decision_by_request(request_id, tracking_service)
"""
Manual decision-making endpoints for Prior Authorization Agent.

This module provides endpoints for manual authorization decisions
by payer administrators and compliance officers.
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field

from src.auth.oauth2 import get_current_user
from src.auth.models import TokenData, UserRole
from src.models.enums import DecisionStatus, RequestStatus
from src.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["manual-decisions"], prefix="/manual-decisions")


class ManualDecisionRequest(BaseModel):
    """Request model for manual authorization decisions."""
    request_id: str = Field(..., description="Authorization request ID")
    decision: DecisionStatus = Field(..., description="Decision status")
    reasoning: str = Field(..., min_length=20, description="Detailed reasoning for the decision")
    policy_references: Optional[List[str]] = Field(default=[], description="Referenced policies")
    additional_notes: Optional[str] = Field(None, description="Additional notes or requirements")


class ManualDecisionResponse(BaseModel):
    """Response model for manual authorization decisions."""
    decision_id: str
    request_id: str
    decision: DecisionStatus
    reasoning: str
    decision_maker: str
    decided_at: datetime
    authorization_number: Optional[str] = None
    valid_until: Optional[datetime] = None


def require_decision_maker_role(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency to ensure user has decision-making privileges."""
    allowed_roles = [UserRole.PAYER_ADMIN.value, UserRole.COMPLIANCE_OFFICER.value, UserRole.SYSTEM_ADMIN.value]
    
    user_roles = current_user.get('roles', [])
    if not any(role in user_roles for role in allowed_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient privileges for making authorization decisions"
        )
    
    return current_user


@router.post("/decide", response_model=ManualDecisionResponse)
async def make_manual_decision(
    decision_request: ManualDecisionRequest,
    current_user: dict = Depends(require_decision_maker_role)
) -> ManualDecisionResponse:
    """
    Make a manual authorization decision.
    
    This endpoint allows payer administrators and compliance officers
    to manually approve, deny, or request additional information for
    authorization requests.
    
    Args:
        decision_request: Decision details including reasoning
        current_user: Authenticated user making the decision
        
    Returns:
        Decision confirmation with details
        
    Raises:
        HTTPException: If user lacks privileges or request is invalid
    """
    try:
        # Generate decision ID
        decision_id = f"dec_manual_{int(datetime.now().timestamp())}"
        
        # Generate authorization number for approved requests
        authorization_number = None
        valid_until = None
        
        if decision_request.decision == DecisionStatus.APPROVED:
            authorization_number = f"AUTH_{decision_request.request_id}_{int(datetime.now().timestamp())}"
            # Set validity for 30 days
            valid_until = datetime.now(timezone.utc).replace(day=datetime.now().day + 30)
        
        # Log the decision
        logger.info(
            "Manual authorization decision made",
            extra={
                "decision_id": decision_id,
                "request_id": decision_request.request_id,
                "decision": decision_request.decision.value,
                "decision_maker": current_user.get('username'),
                "reasoning_length": len(decision_request.reasoning)
            }
        )
        
        # In a real implementation, this would:
        # 1. Update the authorization request status in the database
        # 2. Create a decision record
        # 3. Send notifications to the provider
        # 4. Update audit logs
        
        return ManualDecisionResponse(
            decision_id=decision_id,
            request_id=decision_request.request_id,
            decision=decision_request.decision,
            reasoning=decision_request.reasoning,
            decision_maker=current_user.get('username', 'unknown'),
            decided_at=datetime.now(timezone.utc),
            authorization_number=authorization_number,
            valid_until=valid_until
        )
        
    except Exception as e:
        logger.error(f"Failed to make manual decision: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process decision: {str(e)}"
        )


@router.get("/pending")
async def get_pending_requests(
    status_filter: Optional[str] = None,
    urgency_filter: Optional[str] = None,
    limit: int = 50,
    current_user: dict = Depends(require_decision_maker_role)
):
    """
    Get pending authorization requests for review.
    
    Args:
        status_filter: Filter by request status
        urgency_filter: Filter by urgency level
        limit: Maximum number of requests to return
        current_user: Authenticated user
        
    Returns:
        List of pending authorization requests
    """
    try:
        # In a real implementation, this would query the database
        # For now, return a mock response
        
        logger.info(
            "Pending requests retrieved for review",
            extra={
                "reviewer": current_user.get('username'),
                "status_filter": status_filter,
                "urgency_filter": urgency_filter,
                "limit": limit
            }
        )
        
        return {
            "requests": [],
            "total_count": 0,
            "filters_applied": {
                "status": status_filter,
                "urgency": urgency_filter
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get pending requests: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve pending requests: {str(e)}"
        )


@router.get("/ai-recommendation/{request_id}")
async def get_ai_recommendation(
    request_id: str,
    current_user: TokenData = Depends(require_decision_maker_role)
):
    """
    Get AI recommendation for an authorization request.
    
    Args:
        request_id: Authorization request ID
        current_user: Authenticated user
        
    Returns:
        AI recommendation with reasoning
    """
    try:
        # In a real implementation, this would call the decision engine
        recommendations = [
            "Medical necessity criteria appear to be met based on clinical documentation",
            "ICD-10 code is appropriate for the requested procedure type",
            "Consider requesting additional documentation for symptom duration",
            "Procedure is covered under current policy guidelines",
            "Prior conservative treatment documentation may be required",
            "Patient age and condition support medical necessity"
        ]
        
        import random
        recommendation = random.choice(recommendations)
        
        logger.info(
            "AI recommendation requested",
            extra={
                "request_id": request_id,
                "requester": current_user.get('username')
            }
        )
        
        return {
            "request_id": request_id,
            "recommendation": recommendation,
            "confidence_score": round(random.uniform(0.7, 0.95), 2),
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get AI recommendation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get AI recommendation: {str(e)}"
        )
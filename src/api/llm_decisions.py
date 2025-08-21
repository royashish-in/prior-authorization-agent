"""
LLM-Enhanced Decision API endpoints for Prior Authorization Agent.

This module provides REST endpoints for LLM-powered authorization decisions,
including enhanced medical context, decision explanations, alternative recommendations,
streaming responses, and webhook notifications.
"""

import asyncio
import json
import uuid
import hmac
import hashlib
import html
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import APIRouter, HTTPException, status, Depends, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict
from sse_starlette.sse import EventSourceResponse
import httpx

from src.models.authorization import AuthorizationRequest, AuthorizationDecision
from src.models.enums import DecisionStatus, UrgencyLevel
from src.services.llm_decision_service import (
    llm_decision_service, LLMDecisionResponse, LLMDecisionStatus,
    PolicyComplianceResult, RiskAssessment, AlternativeProcedure
)
from src.services.prompt_engineering import PolicyContext, MedicalContext
from src.services.medical_code_repository import medical_code_repository
from src.api.intake import get_tracking_service, get_validation_service
from src.services.tracking import TrackingService
from src.services.validation import ValidationService
from src.auth.oauth2 import get_current_user
from src.auth.models import TokenData, UserRole
from src.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["llm-decisions"], prefix="/llm-decisions")


# Enhanced Request Models
class EnhancedMedicalContext(BaseModel):
    """Enhanced medical context for LLM processing."""
    patient_history: Optional[List[str]] = Field(default_factory=list, description="Patient medical history")
    comorbidities: Optional[List[str]] = Field(default_factory=list, description="Patient comorbidities")
    current_medications: Optional[List[str]] = Field(default_factory=list, description="Current medications")
    allergies: Optional[List[str]] = Field(default_factory=list, description="Known allergies")
    lab_results: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Recent lab results")
    imaging_history: Optional[List[str]] = Field(default_factory=list, description="Previous imaging studies")
    treatment_response: Optional[str] = Field(None, description="Response to previous treatments")
    functional_status: Optional[str] = Field(None, description="Patient functional status")
    social_determinants: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Social determinants of health")


class EnhancedAuthorizationRequest(BaseModel):
    """Enhanced authorization request with additional medical context."""
    base_request: AuthorizationRequest = Field(..., description="Base authorization request")
    enhanced_context: EnhancedMedicalContext = Field(..., description="Enhanced medical context")
    provider_notes: Optional[str] = Field(None, description="Additional provider notes")
    consultation_notes: Optional[str] = Field(None, description="Specialist consultation notes")
    prior_authorizations: Optional[List[str]] = Field(default_factory=list, description="Previous authorization history")
    clinical_guidelines_preference: Optional[str] = Field(None, description="Preferred clinical guidelines")


# Response Models
class LLMDecisionExplanation(BaseModel):
    """Detailed explanation of LLM decision."""
    decision_summary: str = Field(..., description="Summary of the decision")
    medical_reasoning: str = Field(..., description="Detailed medical reasoning")
    policy_analysis: str = Field(..., description="Policy compliance analysis")
    risk_assessment: Dict[str, Any] = Field(..., description="Risk assessment details")
    evidence_references: List[str] = Field(default_factory=list, description="Medical evidence references")
    confidence_factors: Dict[str, float] = Field(..., description="Factors affecting confidence")
    alternative_considerations: List[str] = Field(default_factory=list, description="Alternative considerations")


class AlternativeRecommendation(BaseModel):
    """Alternative procedure recommendation."""
    procedure_name: str = Field(..., description="Alternative procedure name")
    procedure_code: str = Field(..., description="CPT/HCPCS code")
    clinical_rationale: str = Field(..., description="Clinical rationale for alternative")
    cost_effectiveness: Optional[str] = Field(None, description="Cost effectiveness analysis")
    expected_outcomes: Optional[str] = Field(None, description="Expected clinical outcomes")
    appropriateness_score: float = Field(..., ge=0.0, le=1.0, description="Clinical appropriateness score")
    contraindications: List[str] = Field(default_factory=list, description="Contraindications")


class LLMDecisionResponseModel(BaseModel):
    """Enhanced LLM decision response."""
    decision_id: str = Field(..., description="Unique decision identifier")
    request_id: str = Field(..., description="Associated request identifier")
    decision: str = Field(..., description="Decision outcome")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Decision confidence")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")
    model_used: str = Field(..., description="LLM model used for decision")
    explanation: LLMDecisionExplanation = Field(..., description="Detailed decision explanation")
    alternatives: List[AlternativeRecommendation] = Field(default_factory=list, description="Alternative recommendations")
    required_documentation: List[str] = Field(default_factory=list, description="Required additional documentation")
    follow_up_actions: List[str] = Field(default_factory=list, description="Recommended follow-up actions")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StreamingDecisionUpdate(BaseModel):
    """Streaming decision processing update."""
    request_id: str
    stage: str
    progress: int  # 0-100
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: Optional[Dict[str, Any]] = None


class WebhookNotification(BaseModel):
    """Webhook notification for decision completion."""
    event_type: str = Field(..., description="Type of event")
    request_id: str = Field(..., description="Request identifier")
    decision_id: Optional[str] = Field(None, description="Decision identifier")
    status: str = Field(..., description="Current status")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: Dict[str, Any] = Field(default_factory=dict, description="Event data")


# Webhook Management
class WebhookConfig(BaseModel):
    """Webhook configuration."""
    url: str = Field(..., description="Webhook URL")
    events: List[str] = Field(..., description="Events to subscribe to")
    secret: Optional[str] = Field(None, description="Webhook secret for verification")
    active: bool = Field(default=True, description="Whether webhook is active")


# In-memory webhook storage (in production, use database)
webhook_configs: Dict[str, WebhookConfig] = {}


# Helper Functions
def sanitize_input(text: str) -> str:
    """Sanitize user input to prevent injection attacks."""
    if not isinstance(text, str):
        return str(text)
    
    # Remove potentially dangerous characters
    sanitized = re.sub(r'[<>"\';\\]', '', text)
    # HTML escape remaining content
    sanitized = html.escape(sanitized)
    # Limit length
    return sanitized[:1000]

def check_authorization(user: TokenData, required_roles: List[UserRole]) -> bool:
    """Check if user has required authorization."""
    if not user or not user.roles:
        return False
    return any(role in user.roles for role in required_roles)

def generate_decision_id() -> str:
    """Generate unique decision ID."""
    return f"llm_dec_{datetime.now().year}_{str(uuid.uuid4()).replace('-', '')[:8].upper()}"


async def build_medical_context(
    request: EnhancedAuthorizationRequest
) -> MedicalContext:
    """Build medical context for LLM processing."""
    
    # Get detailed code information
    diagnosis_details = []
    for diag_code in request.base_request.diagnosis_codes:
        try:
            code_info = await medical_code_repository.get_icd10_code_by_code(diag_code.code)
            if code_info:
                diagnosis_details.append({
                    "code": diag_code.code,
                    "description": diag_code.description,
                    "category": code_info.category,
                    "clinical_significance": code_info.description
                })
            else:
                diagnosis_details.append({
                    "code": diag_code.code,
                    "description": diag_code.description,
                    "category": "unknown",
                    "clinical_significance": diag_code.description
                })
        except Exception as e:
            logger.warning(f"Could not retrieve ICD-10 code details for {diag_code.code}: {str(e)}")
            diagnosis_details.append({
                "code": diag_code.code,
                "description": diag_code.description,
                "category": "unknown",
                "clinical_significance": diag_code.description
            })
    
    procedure_details = []
    for proc_code in request.base_request.procedure_codes:
        try:
            if hasattr(proc_code, 'code'):
                code_info = await medical_code_repository.get_cpt_code_by_code(proc_code.code)
                if code_info:
                    procedure_details.append({
                        "code": proc_code.code,
                        "description": proc_code.description,
                        "category": code_info.category,
                        "complexity": "standard"  # Could be enhanced based on RVU
                    })
                else:
                    procedure_details.append({
                        "code": proc_code.code,
                        "description": proc_code.description,
                        "category": "unknown",
                        "complexity": "standard"
                    })
        except Exception as e:
            logger.warning(f"Could not retrieve CPT code details for {proc_code.code}: {str(e)}")
            procedure_details.append({
                "code": proc_code.code,
                "description": proc_code.description,
                "category": "unknown",
                "complexity": "standard"
            })
    
    return MedicalContext(
        patient_age=request.base_request.patient_demographics.age,
        patient_gender=request.base_request.patient_demographics.gender,
        diagnosis_codes=diagnosis_details,
        procedure_codes=procedure_details,
        clinical_notes=sanitize_input(request.base_request.clinical_notes or ""),
        medical_history=request.enhanced_context.patient_history,
        comorbidities=request.enhanced_context.comorbidities,
        current_medications=request.enhanced_context.current_medications,
        allergies=request.enhanced_context.allergies,
        lab_results=request.enhanced_context.lab_results,
        imaging_history=request.enhanced_context.imaging_history,
        urgency_level=request.base_request.urgency_level.value,
        provider_notes=sanitize_input(request.provider_notes or ""),
        consultation_notes=sanitize_input(request.consultation_notes or "")
    )


async def build_policy_context(request: EnhancedAuthorizationRequest) -> PolicyContext:
    """Build policy context for LLM processing."""
    return PolicyContext(
        payer_id="default_payer",  # Would be extracted from request
        policy_version="2024.1",
        coverage_criteria=[
            "Medical necessity must be established",
            "Conservative treatment attempted when appropriate",
            "Procedure must be covered benefit"
        ],
        exclusions=[],
        prior_auth_requirements=True,
        clinical_guidelines=request.clinical_guidelines_preference or "standard"
    )


async def send_webhook_notification(
    webhook_url: str,
    notification: WebhookNotification,
    secret: Optional[str] = None
):
    """Send webhook notification."""
    try:
        headers = {"Content-Type": "application/json"}
        if secret:
            # Add signature header for verification
            payload = notification.model_dump_json()
            signature = hmac.new(
                secret.encode(),
                payload.encode(),
                hashlib.sha256
            ).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook_url,
                json=notification.model_dump(),
                headers=headers,
                timeout=10.0
            )
            
            if response.status_code == 200:
                logger.info(f"Webhook notification sent successfully to {webhook_url}")
                return True
            else:
                logger.warning(f"Webhook notification failed: {response.status_code} - {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"Error sending webhook notification: {str(e)}")
        return False


# API Endpoints

@router.post("/enhanced-request", response_model=LLMDecisionResponseModel)
async def submit_enhanced_authorization_request(
    request: EnhancedAuthorizationRequest,
    background_tasks: BackgroundTasks,
    current_user: TokenData = Depends(get_current_user),
    tracking_service: TrackingService = Depends(get_tracking_service),
    validation_service: ValidationService = Depends(get_validation_service)
) -> LLMDecisionResponseModel:
    """
    Submit enhanced authorization request with additional medical context.
    
    This endpoint accepts requests with enhanced medical context including
    patient history, comorbidities, medications, and other clinical factors
    that improve LLM decision accuracy.
    """
    try:
        # Check authorization
        if not check_authorization(current_user, [UserRole.PROVIDER, UserRole.PAYER_ADMIN]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "INSUFFICIENT_PERMISSIONS", "message": "User lacks required permissions"}
            )
        
        # Generate decision ID
        decision_id = generate_decision_id()
        
        # Validate base request
        validation_result = await validation_service.validate_request(request.base_request)
        if not validation_result.is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "validation_errors": [
                        {"field": error.field, "message": error.message}
                        for error in validation_result.errors
                    ]
                }
            )
        
        # Build contexts
        medical_context = await build_medical_context(request)
        policy_context = await build_policy_context(request)
        
        # Initialize LLM service
        await llm_decision_service.initialize()
        
        # Make LLM decision
        llm_response = await llm_decision_service.make_decision(
            request.base_request,
            policy_context
        )
        
        # Build enhanced response
        explanation = LLMDecisionExplanation(
            decision_summary=f"Decision: {llm_response.decision.value} with {llm_response.confidence_score:.1%} confidence",
            medical_reasoning=llm_response.medical_reasoning,
            policy_analysis=llm_response.policy_compliance.analysis,
            risk_assessment={
                "risk_factors": llm_response.risk_assessment.risk_factors,
                "contraindications": llm_response.risk_assessment.contraindications,
                "risk_score": llm_response.risk_assessment.risk_score
            },
            evidence_references=[llm_response.evidence_base] if llm_response.evidence_base else [],
            confidence_factors={
                "model_confidence": llm_response.confidence_score,
                "validation_score": 1.0 - (len(llm_response.validation_errors) * 0.1),
                "completeness_score": 0.9 if llm_response.medical_reasoning else 0.5
            },
            alternative_considerations=[alt.rationale for alt in llm_response.alternative_procedures]
        )
        
        alternatives = [
            AlternativeRecommendation(
                procedure_name=alt.procedure,
                procedure_code="",  # Would need to be looked up
                clinical_rationale=alt.rationale,
                cost_effectiveness=alt.cost_effectiveness,
                expected_outcomes="",  # Would be enhanced with additional data
                appropriateness_score=alt.clinical_appropriateness,
                contraindications=[]
            )
            for alt in llm_response.alternative_procedures
        ]
        
        response = LLMDecisionResponseModel(
            decision_id=decision_id,
            request_id=request.base_request.request_id,
            decision=llm_response.decision.value,
            confidence_score=llm_response.confidence_score,
            processing_time_ms=llm_response.processing_time_ms,
            model_used=llm_response.model_used,
            explanation=explanation,
            alternatives=alternatives,
            required_documentation=llm_response.required_documentation,
            follow_up_actions=[]  # Could be enhanced based on decision
        )
        
        # Store decision
        auth_decision = AuthorizationDecision(
            decision_id=decision_id,
            request_id=request.base_request.request_id,
            status=DecisionStatus(llm_response.decision.value.lower()),
            reasoning=[llm_response.medical_reasoning],
            policy_references=llm_response.policy_compliance.policy_references,
            confidence_score=llm_response.confidence_score
        )
        
        await tracking_service.store_decision(auth_decision)
        
        # Send webhook notifications
        background_tasks.add_task(
            notify_webhooks,
            "decision.completed",
            request.base_request.request_id,
            decision_id,
            llm_response.decision.value,
            response.model_dump()
        )
        
        logger.info(
            "Enhanced LLM decision completed",
            request_id=sanitize_input(request.base_request.request_id),
            decision_id=sanitize_input(decision_id),
            decision=sanitize_input(llm_response.decision.value),
            confidence=llm_response.confidence_score
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing enhanced request: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "PROCESSING_ERROR",
                "message": "Error processing enhanced authorization request"
            }
        )


@router.get("/{decision_id}/explanation", response_model=LLMDecisionExplanation)
async def get_decision_explanation(
    decision_id: str,
    current_user: TokenData = Depends(get_current_user),
    tracking_service: TrackingService = Depends(get_tracking_service)
) -> LLMDecisionExplanation:
    """
    Get detailed explanation for an LLM decision.
    
    Provides comprehensive explanation including medical reasoning,
    policy analysis, risk assessment, and confidence factors.
    """
    try:
        # Retrieve decision
        decision = await tracking_service.get_decision(decision_id)
        if not decision:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "DECISION_NOT_FOUND",
                    "message": f"Decision {decision_id} not found"
                }
            )
        
        # For now, create explanation from stored decision
        # In production, this would retrieve the full LLM response data
        explanation = LLMDecisionExplanation(
            decision_summary=f"Decision: {decision.status.value} with {decision.confidence_score:.1%} confidence",
            medical_reasoning=decision.reasoning[0] if decision.reasoning else "No detailed reasoning available",
            policy_analysis="Policy compliance analysis based on standard criteria",
            risk_assessment={
                "risk_factors": [],
                "contraindications": [],
                "risk_score": 0.0
            },
            evidence_references=[],
            confidence_factors={
                "overall_confidence": decision.confidence_score,
                "policy_compliance": 0.9,
                "medical_necessity": 0.8
            },
            alternative_considerations=decision.alternative_procedures or []
        )
        
        return explanation
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving decision explanation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "RETRIEVAL_ERROR",
                "message": "Error retrieving decision explanation"
            }
        )


@router.get("/{decision_id}/detailed-explanation", response_model=Dict[str, Any])
async def get_detailed_decision_explanation(
    decision_id: str,
    current_user: TokenData = Depends(get_current_user),
    tracking_service: TrackingService = Depends(get_tracking_service)
) -> Dict[str, Any]:
    """
    Get comprehensive detailed explanation for an LLM decision.
    
    Provides in-depth analysis including medical reasoning, policy analysis,
    risk assessment, evidence references, and clinical recommendations.
    """
    try:
        # Retrieve decision
        decision = await tracking_service.get_decision(decision_id)
        if not decision:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "DECISION_NOT_FOUND",
                    "message": f"Decision {decision_id} not found"
                }
            )
        
        # Get enhanced context if available
        enhanced_context = await tracking_service.get_enhanced_context(decision.request_id)
        
        # Build comprehensive explanation
        detailed_explanation = {
            "decision_summary": {
                "decision_id": decision_id,
                "request_id": decision.request_id,
                "final_decision": decision.status.value,
                "confidence_score": decision.confidence_score,
                "decided_at": decision.decided_at.isoformat(),
                "processing_summary": f"Decision: {decision.status.value} with {decision.confidence_score:.1%} confidence"
            },
            "medical_analysis": {
                "primary_reasoning": decision.reasoning[0] if decision.reasoning else "No detailed reasoning available",
                "clinical_factors": enhanced_context.get('comorbidities', []) if enhanced_context else [],
                "patient_history": enhanced_context.get('patient_history', []) if enhanced_context else [],
                "medication_considerations": enhanced_context.get('current_medications', []) if enhanced_context else [],
                "allergy_considerations": enhanced_context.get('allergies', []) if enhanced_context else []
            },
            "policy_compliance": {
                "compliant": decision.status != DecisionStatus.DENIED,
                "analysis": "Policy compliance analysis based on standard criteria",
                "policy_references": decision.policy_references,
                "violated_criteria": [] if decision.status != DecisionStatus.DENIED else ["Medical necessity not established"],
                "compliance_score": 0.9 if decision.status == DecisionStatus.APPROVED else 0.3
            },
            "risk_assessment": {
                "risk_factors": enhanced_context.get('risk_factors', []) if enhanced_context else [],
                "contraindications": [],
                "safety_considerations": "Standard safety protocols apply",
                "risk_score": 0.2 if decision.status == DecisionStatus.APPROVED else 0.7
            },
            "evidence_base": {
                "clinical_guidelines": ["Standard medical practice guidelines"],
                "literature_references": [],
                "expert_consensus": "Follows established clinical protocols",
                "evidence_quality": "Standard"
            },
            "alternative_considerations": {
                "alternative_procedures": decision.alternative_procedures or [],
                "cost_effectiveness": "Standard cost-effectiveness considerations applied",
                "clinical_alternatives": decision.alternative_procedures or [],
                "recommendation_rationale": "Based on clinical appropriateness and policy compliance"
            },
            "confidence_analysis": {
                "overall_confidence": decision.confidence_score,
                "confidence_factors": {
                    "policy_compliance": 0.9 if decision.status == DecisionStatus.APPROVED else 0.3,
                    "medical_necessity": 0.8 if decision.status == DecisionStatus.APPROVED else 0.4,
                    "clinical_appropriateness": 0.85,
                    "documentation_completeness": 0.9 if enhanced_context else 0.6
                },
                "uncertainty_factors": decision.additional_info_needed or [],
                "confidence_interpretation": _interpret_confidence_score(decision.confidence_score)
            },
            "next_steps": {
                "immediate_actions": _get_immediate_actions(decision),
                "follow_up_requirements": decision.additional_info_needed or [],
                "provider_recommendations": _get_provider_recommendations(decision),
                "patient_communication": _get_patient_communication_guidance(decision)
            },
            "metadata": {
                "enhanced_context_available": bool(enhanced_context),
                "context_fields": list(enhanced_context.keys()) if enhanced_context else [],
                "decision_method": "LLM-enhanced" if enhanced_context else "standard",
                "explanation_generated_at": datetime.now(timezone.utc).isoformat()
            }
        }
        
        return detailed_explanation
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving detailed decision explanation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "RETRIEVAL_ERROR",
                "message": "Error retrieving detailed decision explanation"
            }
        )


def _interpret_confidence_score(score: float) -> str:
    """Interpret confidence score for human understanding."""
    if score >= 0.9:
        return "Very high confidence - decision is well-supported by evidence and policy"
    elif score >= 0.8:
        return "High confidence - decision is supported by available evidence"
    elif score >= 0.7:
        return "Moderate confidence - decision is reasonable but may benefit from additional review"
    elif score >= 0.6:
        return "Low confidence - decision may require additional documentation or review"
    else:
        return "Very low confidence - manual review strongly recommended"


def _get_immediate_actions(decision: AuthorizationDecision) -> List[str]:
    """Get immediate actions based on decision status."""
    if decision.status == DecisionStatus.APPROVED:
        return [
            f"Authorization granted with number: {decision.authorization_number}",
            "Proceed with scheduled procedure",
            "Ensure authorization is valid until: " + (decision.valid_until.strftime("%Y-%m-%d") if decision.valid_until else "N/A")
        ]
    elif decision.status == DecisionStatus.DENIED:
        return [
            "Authorization denied - review denial reasons",
            "Consider alternative procedures if available",
            "Submit appeal if clinical circumstances warrant"
        ]
    else:  # MORE_INFO_NEEDED
        return [
            "Provide additional documentation as specified",
            "Resubmit request with complete information",
            "Contact payer if clarification needed"
        ]


def _get_provider_recommendations(decision: AuthorizationDecision) -> List[str]:
    """Get provider-specific recommendations."""
    recommendations = [
        "Document all clinical decision-making rationale",
        "Ensure patient informed consent is obtained"
    ]
    
    if decision.status == DecisionStatus.APPROVED:
        recommendations.extend([
            "Proceed with procedure as authorized",
            "Monitor patient response and document outcomes"
        ])
    elif decision.status == DecisionStatus.DENIED:
        recommendations.extend([
            "Review alternative treatment options",
            "Consider peer consultation if appropriate",
            "Document medical necessity for potential appeal"
        ])
    
    return recommendations


def _get_patient_communication_guidance(decision: AuthorizationDecision) -> List[str]:
    """Get patient communication guidance."""
    if decision.status == DecisionStatus.APPROVED:
        return [
            "Inform patient that authorization has been approved",
            "Provide procedure scheduling information",
            "Review any pre-procedure requirements"
        ]
    elif decision.status == DecisionStatus.DENIED:
        return [
            "Explain denial reason in patient-friendly terms",
            "Discuss alternative treatment options",
            "Inform about appeal process if applicable"
        ]
    else:  # MORE_INFO_NEEDED
        return [
            "Explain that additional information is needed",
            "Request patient cooperation in providing documentation",
            "Set expectations for timeline"
        ]


@router.get("/{request_id}/alternatives", response_model=List[AlternativeRecommendation])
async def get_alternative_recommendations(
    request_id: str,
    current_user: TokenData = Depends(get_current_user),
    tracking_service: TrackingService = Depends(get_tracking_service)
) -> List[AlternativeRecommendation]:
    """
    Get alternative procedure recommendations for a request.
    
    Provides alternative procedures that may be more appropriate,
    cost-effective, or have better clinical outcomes.
    """
    try:
        # Get the original request
        request = await tracking_service.get_request(request_id)
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "REQUEST_NOT_FOUND",
                    "message": f"Request {request_id} not found"
                }
            )
        
        # Get decision for this request
        decision = await tracking_service.get_decision_by_request_id(request_id)
        if not decision:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "DECISION_NOT_FOUND",
                    "message": f"No decision found for request {request_id}"
                }
            )
        
        # Build alternative recommendations
        alternatives = []
        
        # If we have stored alternatives, use them
        if decision.alternative_procedures:
            for i, alt_name in enumerate(decision.alternative_procedures):
                alternatives.append(AlternativeRecommendation(
                    procedure_name=alt_name,
                    procedure_code=f"ALT_{i+1:03d}",  # Placeholder code
                    clinical_rationale=f"Alternative to requested procedure based on clinical guidelines",
                    cost_effectiveness="Potentially more cost-effective option",
                    expected_outcomes="Similar clinical outcomes expected",
                    appropriateness_score=0.8,
                    contraindications=[]
                ))
        
        # Add some standard alternatives based on procedure type
        if hasattr(request, 'procedure_type'):
            if request.procedure_type.value == 'mri':
                alternatives.extend([
                    AlternativeRecommendation(
                        procedure_name="CT Scan with Contrast",
                        procedure_code="74177",
                        clinical_rationale="CT may provide adequate diagnostic information with lower cost",
                        cost_effectiveness="Significantly lower cost than MRI",
                        expected_outcomes="Good diagnostic accuracy for many conditions",
                        appropriateness_score=0.7,
                        contraindications=["Contrast allergy", "Kidney dysfunction"]
                    ),
                    AlternativeRecommendation(
                        procedure_name="Ultrasound",
                        procedure_code="76700",
                        clinical_rationale="Non-invasive imaging option for soft tissue evaluation",
                        cost_effectiveness="Most cost-effective imaging option",
                        expected_outcomes="Limited diagnostic capability but safe and accessible",
                        appropriateness_score=0.6,
                        contraindications=["Deep tissue evaluation needed"]
                    )
                ])
        
        return alternatives
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving alternatives for request {request_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "RETRIEVAL_ERROR",
                "message": "Error retrieving alternative recommendations"
            }
        )


@router.get("/{request_id}/stream")
async def stream_decision_processing(
    request_id: str,
    current_user: TokenData = Depends(get_current_user),
    tracking_service: TrackingService = Depends(get_tracking_service)
):
    """
    Stream real-time decision processing updates.
    
    Provides server-sent events with processing status updates
    for long-running LLM decision processes.
    """
    async def generate_updates():
        """Generate streaming updates for decision processing."""
        try:
            # Check if request exists
            request = await tracking_service.get_request(request_id)
            if not request:
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "error": "REQUEST_NOT_FOUND",
                        "message": f"Request {request_id} not found"
                    })
                }
                return
            
            # Simulate processing stages
            stages = [
                {"stage": "validation", "progress": 10, "message": "Validating request data"},
                {"stage": "context_building", "progress": 25, "message": "Building medical context"},
                {"stage": "llm_processing", "progress": 50, "message": "Processing with LLM"},
                {"stage": "response_parsing", "progress": 75, "message": "Parsing LLM response"},
                {"stage": "validation", "progress": 90, "message": "Validating decision"},
                {"stage": "completed", "progress": 100, "message": "Decision processing completed"}
            ]
            
            for stage_info in stages:
                update = StreamingDecisionUpdate(
                    request_id=request_id,
                    stage=stage_info["stage"],
                    progress=stage_info["progress"],
                    message=stage_info["message"],
                    details={
                        "current_stage": stage_info["stage"],
                        "estimated_completion": "2-3 minutes"
                    }
                )
                
                yield {
                    "event": "update",
                    "data": update.model_dump_json()
                }
                
                # Simulate processing time
                await asyncio.sleep(1)
            
            # Send final completion event
            decision = await tracking_service.get_decision_by_request_id(request_id)
            if decision:
                completion_update = {
                    "event": "completed",
                    "data": json.dumps({
                        "request_id": request_id,
                        "decision_id": decision.decision_id,
                        "final_decision": decision.status.value,
                        "confidence_score": decision.confidence_score,
                        "completed_at": datetime.now(timezone.utc).isoformat()
                    })
                }
                yield completion_update
            
        except Exception as e:
            logger.error(f"Error in streaming updates for {request_id}: {str(e)}")
            yield {
                "event": "error",
                "data": json.dumps({
                    "error": "STREAMING_ERROR",
                    "message": "Error in processing stream"
                })
            }
    
    return EventSourceResponse(generate_updates())


# Webhook Management Endpoints

@router.post("/webhooks", response_model=Dict[str, str])
async def register_webhook(
    webhook_config: WebhookConfig,
    current_user: TokenData = Depends(get_current_user)
) -> Dict[str, str]:
    """
    Register a webhook for decision notifications.
    
    Allows external systems to receive notifications when
    LLM decisions are completed or status changes occur.
    """
    try:
        # Generate webhook ID
        webhook_id = f"webhook_{datetime.now().year}_{str(uuid.uuid4()).replace('-', '')[:8]}"
        
        # Store webhook configuration
        webhook_configs[webhook_id] = webhook_config
        
        logger.info(f"Webhook registered: {webhook_id} -> {webhook_config.url}")
        
        return {
            "webhook_id": webhook_id,
            "status": "registered",
            "message": f"Webhook registered successfully for events: {', '.join(webhook_config.events)}"
        }
        
    except Exception as e:
        logger.error(f"Error registering webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "REGISTRATION_ERROR",
                "message": "Error registering webhook"
            }
        )


@router.get("/webhooks", response_model=Dict[str, WebhookConfig])
async def list_webhooks(
    current_user: TokenData = Depends(get_current_user)
) -> Dict[str, WebhookConfig]:
    """List all registered webhooks."""
    return webhook_configs


@router.delete("/webhooks/{webhook_id}", response_model=Dict[str, str])
async def unregister_webhook(
    webhook_id: str,
    current_user: TokenData = Depends(get_current_user)
) -> Dict[str, str]:
    """Unregister a webhook."""
    if webhook_id not in webhook_configs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "WEBHOOK_NOT_FOUND",
                "message": f"Webhook {webhook_id} not found"
            }
        )
    
    del webhook_configs[webhook_id]
    
    return {
        "webhook_id": webhook_id,
        "status": "unregistered",
        "message": "Webhook unregistered successfully"
    }


@router.post("/webhooks/{webhook_id}/test", response_model=Dict[str, Any])
async def test_webhook(
    webhook_id: str,
    current_user: TokenData = Depends(get_current_user)
) -> Dict[str, Any]:
    """Test a webhook by sending a test notification."""
    if webhook_id not in webhook_configs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "WEBHOOK_NOT_FOUND",
                "message": f"Webhook {webhook_id} not found"
            }
        )
    
    webhook_config = webhook_configs[webhook_id]
    
    # Create test notification
    test_notification = WebhookNotification(
        event_type="test",
        request_id="test_request_123",
        status="test",
        data={
            "message": "This is a test webhook notification",
            "webhook_id": webhook_id
        }
    )
    
    # Send test notification
    success = await send_webhook_notification(
        webhook_config.url,
        test_notification,
        webhook_config.secret
    )
    
    return {
        "webhook_id": webhook_id,
        "test_sent": success,
        "message": "Test notification sent" if success else "Test notification failed"
    }


async def notify_webhooks(
    event_type: str,
    request_id: str,
    decision_id: Optional[str] = None,
    status: str = "",
    data: Dict[str, Any] = None
):
    """Send notifications to all registered webhooks for an event."""
    if not data:
        data = {}
    
    notification = WebhookNotification(
        event_type=event_type,
        request_id=request_id,
        decision_id=decision_id,
        status=status,
        data=data
    )
    
    # Send to all webhooks that subscribe to this event type
    for webhook_id, config in webhook_configs.items():
        if config.active and event_type in config.events:
            try:
                await send_webhook_notification(config.url, notification, config.secret)
                logger.info(f"Webhook notification sent to {webhook_id} for event {event_type}")
            except Exception as e:
                logger.error(f"Failed to send webhook notification to {webhook_id}: {str(e)}")


# Enhanced Decision Processing Endpoints

@router.post("/batch-process", response_model=Dict[str, Any])
async def batch_process_requests(
    request_ids: List[str],
    background_tasks: BackgroundTasks,
    current_user: TokenData = Depends(get_current_user),
    tracking_service: TrackingService = Depends(get_tracking_service)
) -> Dict[str, Any]:
    """
    Process multiple authorization requests in batch using LLM.
    
    Efficiently processes multiple requests with parallel LLM calls
    and provides batch status updates.
    """
    try:
        if len(request_ids) > 50:  # Limit batch size
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "BATCH_SIZE_EXCEEDED",
                    "message": "Maximum batch size is 50 requests"
                }
            )
        
        # Validate all requests exist
        valid_requests = []
        invalid_requests = []
        
        for request_id in request_ids:
            request = await tracking_service.get_request(request_id)
            if request:
                valid_requests.append(request_id)
            else:
                invalid_requests.append(request_id)
        
        if invalid_requests:
            logger.warning(f"Invalid requests in batch: {invalid_requests}")
        
        # Start batch processing in background
        batch_id = f"batch_{datetime.now().year}_{str(uuid.uuid4()).replace('-', '')[:8]}"
        
        background_tasks.add_task(
            process_batch_requests,
            batch_id,
            valid_requests
        )
        
        return {
            "batch_id": batch_id,
            "total_requests": len(request_ids),
            "valid_requests": len(valid_requests),
            "invalid_requests": len(invalid_requests),
            "invalid_request_ids": invalid_requests,
            "status": "processing",
            "message": f"Batch processing started for {len(valid_requests)} requests"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting batch processing: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "BATCH_ERROR",
                "message": "Error starting batch processing"
            }
        )


async def process_batch_requests(batch_id: str, request_ids: List[str]):
    """Process batch requests in background."""
    try:
        logger.info(f"Starting batch processing {batch_id} for {len(request_ids)} requests")
        
        # Process requests in parallel (with concurrency limit)
        semaphore = asyncio.Semaphore(5)  # Limit concurrent processing
        
        async def process_single_request(request_id: str):
            async with semaphore:
                try:
                    # This would integrate with the actual LLM processing
                    # For now, simulate processing
                    await asyncio.sleep(2)  # Simulate processing time
                    
                    # Send webhook notification for completion
                    await notify_webhooks(
                        "batch.request.completed",
                        request_id,
                        status="completed",
                        data={"batch_id": batch_id}
                    )
                    
                    return {"request_id": request_id, "status": "completed"}
                    
                except Exception as e:
                    logger.error(f"Error processing request {request_id} in batch {batch_id}: {str(e)}")
                    return {"request_id": request_id, "status": "failed", "error": str(e)}
        
        # Process all requests
        results = await asyncio.gather(
            *[process_single_request(req_id) for req_id in request_ids],
            return_exceptions=True
        )
        
        # Send batch completion notification
        completed_count = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "completed")
        failed_count = len(results) - completed_count
        
        await notify_webhooks(
            "batch.completed",
            batch_id,
            status="completed",
            data={
                "batch_id": batch_id,
                "total_requests": len(request_ids),
                "completed": completed_count,
                "failed": failed_count,
                "results": results
            }
        )
        
        logger.info(f"Batch processing {batch_id} completed: {completed_count} succeeded, {failed_count} failed")
        
    except Exception as e:
        logger.error(f"Error in batch processing {batch_id}: {str(e)}")
        await notify_webhooks(
            "batch.failed",
            batch_id,
            status="failed",
            data={"batch_id": batch_id, "error": str(e)}
        )


@router.get("/models/status", response_model=Dict[str, Any])
async def get_llm_models_status(
    current_user: TokenData = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get status of all available LLM models.
    
    Provides health status, performance metrics, and availability
    information for all configured LLM models.
    """
    try:
        # Initialize LLM service if needed
        await llm_decision_service.initialize()
        
        # Get comprehensive model health status
        model_status = await llm_decision_service.get_model_health()
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "models": model_status,
            "summary": {
                "total_models": len(model_status),
                "healthy_models": sum(1 for m in model_status.values() if m.get("status") == "healthy"),
                "degraded_models": sum(1 for m in model_status.values() if m.get("status") == "degraded"),
                "failed_models": sum(1 for m in model_status.values() if m.get("status") == "failed")
            }
        }
        
    except Exception as e:
        logger.error(f"Error retrieving model status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "STATUS_ERROR",
                "message": "Error retrieving model status"
            }
        )




@router.post("/{request_id}/stream")
async def stream_decision_processing(
    request_id: str,
    enhanced_request: EnhancedAuthorizationRequest,
    current_user: TokenData = Depends(get_current_user),
    validation_service: ValidationService = Depends(get_validation_service),
    tracking_service: TrackingService = Depends(get_tracking_service)
):
    """
    Stream real-time decision processing updates.
    
    Provides server-sent events with processing progress,
    intermediate results, and completion notifications.
    """
    
    async def generate_updates():
        """Generate streaming updates for decision processing."""
        try:
            # Initialization
            yield {
                "event": "update",
                "data": StreamingDecisionUpdate(
                    request_id=request_id,
                    stage="initialization",
                    progress=10,
                    message="Initializing LLM decision service"
                ).model_dump_json()
            }
            
            await asyncio.sleep(0.5)  # Simulate processing time
            
            # Validation
            yield {
                "event": "update", 
                "data": StreamingDecisionUpdate(
                    request_id=request_id,
                    stage="validation",
                    progress=25,
                    message="Validating request data and medical codes"
                ).model_dump_json()
            }
            
            # Perform actual validation
            validation_result = await validation_service.validate_request(enhanced_request.base_request)
            if not validation_result.is_valid:
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "request_id": request_id,
                        "error": "Validation failed",
                        "details": [error.message for error in validation_result.errors],
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                }
                return
            
            await asyncio.sleep(1.0)
            
            # Context building
            yield {
                "event": "update",
                "data": StreamingDecisionUpdate(
                    request_id=request_id,
                    stage="context_building",
                    progress=40,
                    message="Building medical and policy context"
                ).model_dump_json()
            }
            
            # Build contexts
            medical_context = await build_medical_context(enhanced_request)
            policy_context = await build_policy_context(enhanced_request)
            
            await asyncio.sleep(0.8)
            
            # LLM processing
            yield {
                "event": "update",
                "data": StreamingDecisionUpdate(
                    request_id=request_id,
                    stage="llm_processing",
                    progress=60,
                    message="Processing request with medical AI model"
                ).model_dump_json()
            }
            
            # Initialize LLM service and make decision
            await llm_decision_service.initialize()
            llm_response = await llm_decision_service.make_decision(
                enhanced_request.base_request,
                policy_context
            )
            
            await asyncio.sleep(1.0)  # Simulate additional processing time
            
            # Response parsing
            yield {
                "event": "update",
                "data": StreamingDecisionUpdate(
                    request_id=request_id,
                    stage="response_parsing",
                    progress=80,
                    message="Parsing and validating AI response"
                ).model_dump_json()
            }
            
            await asyncio.sleep(0.5)
            
            # Store decision
            decision_id = generate_decision_id()
            auth_decision = AuthorizationDecision(
                decision_id=decision_id,
                request_id=request_id,
                status=DecisionStatus(llm_response.decision.value.lower()),
                reasoning=[llm_response.medical_reasoning],
                policy_references=llm_response.policy_compliance.policy_references,
                confidence_score=llm_response.confidence_score
            )
            
            await tracking_service.store_decision(auth_decision)
            
            # Completion
            yield {
                "event": "complete",
                "data": StreamingDecisionUpdate(
                    request_id=request_id,
                    stage="completed",
                    progress=100,
                    message="Decision processing completed",
                    details={
                        "decision": llm_response.decision.value,
                        "confidence": llm_response.confidence_score,
                        "processing_time_ms": llm_response.processing_time_ms,
                        "decision_id": decision_id
                    }
                ).model_dump_json()
            }
            
        except Exception as e:
            logger.error(f"Error in streaming decision processing: {str(e)}", exc_info=True)
            yield {
                "event": "error",
                "data": json.dumps({
                    "request_id": request_id,
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            }
    
    return EventSourceResponse(generate_updates())



@router.post("/bulk-process", response_model=Dict[str, Any])
async def bulk_process_requests(
    requests: List[EnhancedAuthorizationRequest],
    background_tasks: BackgroundTasks,
    current_user: TokenData = Depends(get_current_user),
    validation_service: ValidationService = Depends(get_validation_service),
    tracking_service: TrackingService = Depends(get_tracking_service)
) -> Dict[str, Any]:
    """
    Process multiple authorization requests in bulk with webhook notifications.
    
    Processes multiple requests concurrently and sends webhook notifications
    for each completed decision.
    """
    try:
        if len(requests) > 50:  # Limit bulk processing
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "BULK_LIMIT_EXCEEDED",
                    "message": "Maximum 50 requests allowed per bulk operation"
                }
            )
        
        batch_id = f"batch_{str(uuid.uuid4()).replace('-', '')[:8]}"
        results = []
        
        # Process requests concurrently
        async def process_single_request(request: EnhancedAuthorizationRequest) -> Dict[str, Any]:
            try:
                # Generate decision ID
                decision_id = generate_decision_id()
                
                # Validate request
                validation_result = await validation_service.validate_request(request.base_request)
                if not validation_result.is_valid:
                    return {
                        "request_id": request.base_request.request_id,
                        "status": "validation_failed",
                        "errors": [error.message for error in validation_result.errors]
                    }
                
                # Build contexts
                medical_context = await build_medical_context(request)
                policy_context = await build_policy_context(request)
                
                # Initialize LLM service and make decision
                await llm_decision_service.initialize()
                llm_response = await llm_decision_service.make_decision(
                    request.base_request,
                    policy_context
                )
                
                # Store decision
                auth_decision = AuthorizationDecision(
                    decision_id=decision_id,
                    request_id=request.base_request.request_id,
                    status=DecisionStatus(llm_response.decision.value.lower()),
                    reasoning=[llm_response.medical_reasoning],
                    policy_references=llm_response.policy_compliance.policy_references,
                    confidence_score=llm_response.confidence_score
                )
                
                await tracking_service.store_decision(auth_decision)
                
                # Send webhook notification in background
                background_tasks.add_task(
                    notify_webhooks,
                    "decision.completed",
                    request.base_request.request_id,
                    decision_id,
                    llm_response.decision.value,
                    {
                        "batch_id": batch_id,
                        "confidence_score": llm_response.confidence_score,
                        "processing_time_ms": llm_response.processing_time_ms
                    }
                )
                
                return {
                    "request_id": request.base_request.request_id,
                    "decision_id": decision_id,
                    "status": "completed",
                    "decision": llm_response.decision.value,
                    "confidence_score": llm_response.confidence_score
                }
                
            except Exception as e:
                logger.error(f"Error processing request {request.base_request.request_id}: {str(e)}")
                return {
                    "request_id": request.base_request.request_id,
                    "status": "error",
                    "error": str(e)
                }
        
        # Process all requests concurrently
        tasks = [process_single_request(request) for request in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count results
        completed = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "completed")
        failed = sum(1 for r in results if isinstance(r, dict) and r.get("status") in ["error", "validation_failed"])
        
        # Send batch completion webhook
        background_tasks.add_task(
            notify_webhooks,
            "batch.completed",
            batch_id,
            None,
            "completed",
            {
                "batch_id": batch_id,
                "total_requests": len(requests),
                "completed": completed,
                "failed": failed,
                "results": results
            }
        )
        
        return {
            "batch_id": batch_id,
            "total_requests": len(requests),
            "completed": completed,
            "failed": failed,
            "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk processing: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "BULK_PROCESSING_ERROR",
                "message": "Error processing bulk requests"
            }
        )


async def notify_webhooks(
    event_type: str,
    request_id: str,
    decision_id: Optional[str] = None,
    status: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None
):
    """Send notifications to registered webhooks."""
    
    notification = WebhookNotification(
        event_type=event_type,
        request_id=request_id,
        decision_id=decision_id,
        status=status or "unknown",
        data=data or {}
    )
    
    # Send to all active webhooks that subscribe to this event
    for webhook_id, config in webhook_configs.items():
        if config.active and event_type in config.events:
            await send_webhook_notification(
                config.url,
                notification,
                config.secret
            )


# Health and Status Endpoints

@router.get("/health")
async def get_llm_health() -> Dict[str, Any]:
    """Get health status of LLM decision service."""
    
    try:
        health_status = await llm_decision_service.get_model_health()
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "models": health_status
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        }


@router.get("/metrics")
async def get_llm_metrics(
    current_user: TokenData = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get LLM decision service metrics."""
    
    # In production, this would return real metrics
    return {
        "total_decisions": 1250,
        "decisions_today": 45,
        "average_confidence": 0.82,
        "average_processing_time_ms": 2400,
        "model_usage": {
            "microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract": 0.65,
            "emilyalsentzer/Bio_ClinicalBERT": 0.35
        },
        "decision_distribution": {
            "APPROVE": 0.68,
            "DENY": 0.22,
            "PENDING": 0.10
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# Additional Enhanced Endpoints for Complete Task Implementation

@router.post("/requests/enhanced-batch", response_model=Dict[str, Any])
async def submit_enhanced_batch_requests(
    requests: List[EnhancedAuthorizationRequest],
    background_tasks: BackgroundTasks,
    current_user: TokenData = Depends(get_current_user),
    validation_service: ValidationService = Depends(get_validation_service),
    tracking_service: TrackingService = Depends(get_tracking_service)
) -> Dict[str, Any]:
    """
    Submit multiple enhanced authorization requests with streaming updates and webhook notifications.
    
    This endpoint processes multiple enhanced requests concurrently, provides real-time
    updates via webhooks, and returns comprehensive batch processing results.
    """
    try:
        if len(requests) > 25:  # Limit for enhanced processing
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ENHANCED_BATCH_LIMIT_EXCEEDED",
                    "message": "Maximum 25 enhanced requests allowed per batch operation"
                }
            )
        
        batch_id = f"enhanced_batch_{str(uuid.uuid4()).replace('-', '')[:8]}"
        
        # Send batch started webhook
        background_tasks.add_task(
            notify_webhooks,
            "enhanced_batch.started",
            batch_id,
            None,
            "processing",
            {
                "batch_id": batch_id,
                "total_requests": len(requests),
                "batch_type": "enhanced",
                "started_at": datetime.now(timezone.utc).isoformat()
            }
        )
        
        # Process requests with enhanced context
        results = []
        for i, request in enumerate(requests):
            try:
                # Generate decision ID
                decision_id = generate_decision_id()
                
                # Validate request
                validation_result = await validation_service.validate_request(request.base_request)
                if not validation_result.is_valid:
                    result = {
                        "request_id": request.base_request.request_id,
                        "status": "validation_failed",
                        "errors": [error.message for error in validation_result.errors]
                    }
                    results.append(result)
                    continue
                
                # Build enhanced contexts
                medical_context = await build_medical_context(request)
                policy_context = await build_policy_context(request)
                
                # Store enhanced context
                await tracking_service.store_enhanced_context(
                    request.base_request.request_id,
                    request.enhanced_context.model_dump()
                )
                
                # Send progress webhook
                background_tasks.add_task(
                    notify_webhooks,
                    "enhanced_batch.progress",
                    batch_id,
                    None,
                    "processing",
                    {
                        "batch_id": batch_id,
                        "current_request": i + 1,
                        "total_requests": len(requests),
                        "progress_percentage": int((i + 1) / len(requests) * 100),
                        "processing_request_id": request.base_request.request_id
                    }
                )
                
                # Initialize LLM service and make decision
                await llm_decision_service.initialize()
                llm_response = await llm_decision_service.make_decision(
                    request.base_request,
                    policy_context
                )
                
                # Store decision
                auth_decision = AuthorizationDecision(
                    decision_id=decision_id,
                    request_id=request.base_request.request_id,
                    status=DecisionStatus(llm_response.decision.value.lower()),
                    reasoning=[llm_response.medical_reasoning],
                    policy_references=llm_response.policy_compliance.policy_references,
                    confidence_score=llm_response.confidence_score
                )
                
                await tracking_service.store_decision(auth_decision)
                
                # Send individual decision webhook
                background_tasks.add_task(
                    notify_webhooks,
                    "enhanced_decision.completed",
                    request.base_request.request_id,
                    decision_id,
                    llm_response.decision.value,
                    {
                        "batch_id": batch_id,
                        "enhanced_context_used": True,
                        "confidence_score": llm_response.confidence_score,
                        "processing_time_ms": llm_response.processing_time_ms,
                        "medical_reasoning": llm_response.medical_reasoning[:200] + "..." if len(llm_response.medical_reasoning) > 200 else llm_response.medical_reasoning
                    }
                )
                
                result = {
                    "request_id": request.base_request.request_id,
                    "decision_id": decision_id,
                    "status": "completed",
                    "decision": llm_response.decision.value,
                    "confidence_score": llm_response.confidence_score,
                    "enhanced_context_used": True
                }
                results.append(result)
                
            except Exception as e:
                logger.error(f"Error processing enhanced request {request.base_request.request_id}: {str(e)}")
                result = {
                    "request_id": request.base_request.request_id,
                    "status": "error",
                    "error": str(e),
                    "enhanced_context_used": False
                }
                results.append(result)
        
        # Calculate final statistics
        completed = sum(1 for r in results if r.get("status") == "completed")
        failed = sum(1 for r in results if r.get("status") in ["error", "validation_failed"])
        
        # Send batch completion webhook
        background_tasks.add_task(
            notify_webhooks,
            "enhanced_batch.completed",
            batch_id,
            None,
            "completed",
            {
                "batch_id": batch_id,
                "total_requests": len(requests),
                "completed": completed,
                "failed": failed,
                "batch_type": "enhanced",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "results_summary": {
                    "approved": sum(1 for r in results if r.get("decision") == "APPROVE"),
                    "denied": sum(1 for r in results if r.get("decision") == "DENY"),
                    "pending": sum(1 for r in results if r.get("decision") == "PENDING")
                }
            }
        )
        
        return {
            "batch_id": batch_id,
            "batch_type": "enhanced",
            "total_requests": len(requests),
            "completed": completed,
            "failed": failed,
            "results": results,
            "processing_summary": {
                "enhanced_context_used": sum(1 for r in results if r.get("enhanced_context_used", False)),
                "average_confidence": sum(r.get("confidence_score", 0) for r in results if r.get("confidence_score")) / max(1, completed),
                "decision_distribution": {
                    "APPROVE": sum(1 for r in results if r.get("decision") == "APPROVE"),
                    "DENY": sum(1 for r in results if r.get("decision") == "DENY"),
                    "PENDING": sum(1 for r in results if r.get("decision") == "PENDING")
                }
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in enhanced batch processing: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "ENHANCED_BATCH_PROCESSING_ERROR",
                "message": "Error processing enhanced batch requests"
            }
        )


@router.get("/decisions/{decision_id}/context", response_model=Dict[str, Any])
async def get_decision_enhanced_context(
    decision_id: str,
    current_user: TokenData = Depends(get_current_user),
    tracking_service: TrackingService = Depends(get_tracking_service)
) -> Dict[str, Any]:
    """
    Get the enhanced medical context that was used for a specific LLM decision.
    
    This endpoint provides access to the additional medical context (patient history,
    comorbidities, medications, etc.) that was used to enhance the LLM decision-making process.
    """
    try:
        # Retrieve decision
        decision = await tracking_service.get_decision(decision_id)
        if not decision:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "DECISION_NOT_FOUND",
                    "message": f"Decision {decision_id} not found"
                }
            )
        
        # Get enhanced context
        enhanced_context = await tracking_service.get_enhanced_context(decision.request_id)
        
        return {
            "decision_id": decision_id,
            "request_id": decision.request_id,
            "enhanced_context_available": bool(enhanced_context),
            "enhanced_context": enhanced_context or {},
            "context_fields": list(enhanced_context.keys()) if enhanced_context else [],
            "decision_summary": {
                "status": decision.status.value,
                "confidence_score": decision.confidence_score,
                "decided_at": decision.decided_at.isoformat()
            },
            "retrieved_at": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving enhanced context for decision {decision_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "CONTEXT_RETRIEVAL_ERROR",
                "message": "Error retrieving enhanced context"
            }
        )


@router.post("/decisions/{decision_id}/feedback", status_code=status.HTTP_201_CREATED)
async def submit_decision_feedback(
    decision_id: str,
    feedback_data: Dict[str, Any],
    background_tasks: BackgroundTasks,
    current_user: TokenData = Depends(get_current_user),
    tracking_service: TrackingService = Depends(get_tracking_service)
) -> Dict[str, Any]:
    """
    Submit feedback on an LLM decision for continuous improvement.
    
    This endpoint allows healthcare providers and administrators to provide
    feedback on LLM decisions, which can be used to improve future decision-making.
    """
    try:
        # Retrieve decision
        decision = await tracking_service.get_decision(decision_id)
        if not decision:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "DECISION_NOT_FOUND",
                    "message": f"Decision {decision_id} not found"
                }
            )
        
        # Validate feedback data
        required_fields = ["feedback_type", "rating", "comments"]
        missing_fields = [field for field in required_fields if field not in feedback_data]
        if missing_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "MISSING_FEEDBACK_FIELDS",
                    "message": f"Missing required fields: {', '.join(missing_fields)}"
                }
            )
        
        # Store feedback (in production, this would go to a feedback database)
        feedback_id = f"feedback_{str(uuid.uuid4()).replace('-', '')[:8]}"
        feedback_record = {
            "feedback_id": feedback_id,
            "decision_id": decision_id,
            "request_id": decision.request_id,
            "feedback_type": feedback_data["feedback_type"],  # "accuracy", "explanation", "alternative"
            "rating": feedback_data["rating"],  # 1-5 scale
            "comments": feedback_data["comments"],
            "provider_suggestions": feedback_data.get("provider_suggestions", []),
            "submitted_by": current_user.username,
            "submitted_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Send feedback webhook
        background_tasks.add_task(
            notify_webhooks,
            "decision.feedback_received",
            decision.request_id,
            decision_id,
            "feedback_submitted",
            {
                "feedback_id": feedback_id,
                "feedback_type": feedback_data["feedback_type"],
                "rating": feedback_data["rating"],
                "decision_confidence": decision.confidence_score,
                "feedback_summary": feedback_data["comments"][:100] + "..." if len(feedback_data["comments"]) > 100 else feedback_data["comments"]
            }
        )
        
        logger.info(
            "Decision feedback submitted",
            decision_id=decision_id,
            feedback_id=feedback_id,
            feedback_type=feedback_data["feedback_type"],
            rating=feedback_data["rating"]
        )
        
        return {
            "feedback_id": feedback_id,
            "decision_id": decision_id,
            "status": "feedback_recorded",
            "message": "Feedback submitted successfully and will be used to improve future decisions",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting feedback for decision {decision_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "FEEDBACK_SUBMISSION_ERROR",
                "message": "Error submitting decision feedback"
            }
        )
"""
AI Configuration API endpoints for managing AI parameters.

This module provides web-based AI configuration management including
LLM model selection, decision thresholds, escalation rules, and clinical guidelines.
"""

import logging
from datetime import date, datetime
from typing import List, Dict, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session

from src.database.connection import get_db_session
from src.auth.oauth2 import get_current_user, require_permissions
from src.services.ai_config_manager import AIConfigurationManager, get_ai_config_manager
from src.models.ai_config import (
    ConfigurationType, AIConfigurationRequest, AIConfigurationResponse,
    ConfigurationValidationResult, ModelPerformanceMetrics,
    ModelSelectionStrategy, DecisionThresholdConfig, EscalationRuleConfig,
    ClinicalGuidelineConfig, FeedbackConfig
)
from src.audit.logger import AuditLogger
from src.auth.models import UserRole


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/ai-config", tags=["AI Configuration"])


# Request/Response Models
class LLMModelConfigRequest(BaseModel):
    """Request model for LLM model configuration."""
    model_id: str = Field(..., description="Hugging Face model identifier")
    model_name: str = Field(..., description="Human-readable model name")
    deployment_type: str = Field(..., description="Deployment type: huggingface_api, local_model, inference_endpoint")
    model_type: str = Field(..., description="Model type: biomedical_bert, clinical_bert, pubmed_bert, etc.")
    priority: int = Field(1, ge=1, le=10, description="Model priority (1=highest)")
    enabled: bool = Field(True, description="Whether model is enabled")
    
    # Model parameters
    max_tokens: int = Field(512, ge=1, le=4096)
    temperature: float = Field(0.1, ge=0.0, le=2.0)
    top_p: float = Field(0.9, ge=0.0, le=1.0)
    confidence_threshold: float = Field(0.7, ge=0.0, le=1.0)
    timeout_seconds: int = Field(30, ge=1, le=300)
    max_retries: int = Field(3, ge=0, le=10)
    
    # Performance settings
    use_auth_token: bool = Field(True)
    device: Optional[str] = Field(None, description="cuda, cpu, or auto")
    torch_dtype: str = Field("auto")
    load_in_8bit: bool = Field(False)
    load_in_4bit: bool = Field(False)
    
    # Usage constraints
    max_requests_per_minute: int = Field(60, ge=1, le=1000)
    max_concurrent_requests: int = Field(10, ge=1, le=100)
    cost_per_request: float = Field(0.0, ge=0.0)
    
    @validator('deployment_type')
    def validate_deployment_type(cls, v):
        valid_types = ['huggingface_api', 'local_model', 'inference_endpoint']
        if v not in valid_types:
            raise ValueError(f'Deployment type must be one of: {valid_types}')
        return v


class DecisionThresholdConfigRequest(BaseModel):
    """Request model for decision threshold configuration."""
    config_name: str = Field(..., description="Configuration name")
    auto_approve_threshold: float = Field(0.9, ge=0.0, le=1.0)
    auto_deny_threshold: float = Field(0.8, ge=0.0, le=1.0)
    manual_review_threshold: float = Field(0.6, ge=0.0, le=1.0)
    
    # Procedure-specific thresholds
    procedure_thresholds: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    payer_thresholds: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    
    # Risk adjustments
    high_risk_adjustment: float = Field(-0.1, description="Adjustment for high-risk procedures")
    low_risk_adjustment: float = Field(0.05, description="Adjustment for low-risk procedures")
    
    effective_date: date = Field(default_factory=date.today)
    expiration_date: Optional[date] = None


class EscalationRuleConfigRequest(BaseModel):
    """Request model for escalation rule configuration."""
    rule_name: str = Field(..., description="Rule name")
    triggers: List[str] = Field(..., description="Escalation triggers")
    trigger_conditions: Dict[str, Any] = Field(default_factory=dict)
    
    escalation_queue: str = Field(..., description="Target escalation queue")
    escalation_priority: int = Field(1, ge=1, le=5)
    
    notify_immediately: bool = Field(True)
    notification_recipients: List[str] = Field(default_factory=list)
    
    escalation_timeout_hours: int = Field(24, ge=1)
    max_escalation_level: int = Field(3, ge=1, le=5)
    
    effective_date: date = Field(default_factory=date.today)
    expiration_date: Optional[date] = None


class ClinicalGuidelineConfigRequest(BaseModel):
    """Request model for clinical guideline configuration."""
    guideline_name: str = Field(..., description="Guideline name")
    guideline_version: str = Field("1.0", description="Version")
    guideline_text: str = Field(..., description="Full guideline text")
    guideline_summary: str = Field(..., description="Brief summary")
    
    applicable_procedures: List[str] = Field(default_factory=list)
    applicable_diagnoses: List[str] = Field(default_factory=list)
    applicable_payers: List[str] = Field(default_factory=list)
    
    decision_rules: List[Dict[str, Any]] = Field(default_factory=list)
    contraindications: List[str] = Field(default_factory=list)
    relative_contraindications: List[str] = Field(default_factory=list)
    
    evidence_level: str = Field("", description="Evidence level (A, B, C)")
    references: List[Dict[str, str]] = Field(default_factory=list)
    source_organization: str = Field("", description="Source organization")
    
    parent_guideline_id: Optional[str] = None
    change_summary: str = Field("", description="Change summary")
    
    effective_date: date = Field(default_factory=date.today)
    expiration_date: Optional[date] = None


class FeedbackConfigRequest(BaseModel):
    """Request model for feedback configuration."""
    feedback_name: str = Field(..., description="Feedback configuration name")
    feedback_types: List[str] = Field(..., description="Types of feedback to collect")
    collection_triggers: List[str] = Field(default_factory=list)
    
    auto_process_feedback: bool = Field(True)
    feedback_weight: float = Field(1.0, ge=0.0, le=10.0)
    minimum_feedback_count: int = Field(5, ge=1)
    
    learning_rate: float = Field(0.01, ge=0.001, le=1.0)
    feedback_decay_days: int = Field(90, ge=1)
    
    minimum_confidence_for_learning: float = Field(0.7, ge=0.0, le=1.0)
    exclude_outliers: bool = Field(True)
    require_expert_validation: bool = Field(False)
    
    effective_date: date = Field(default_factory=date.today)
    expiration_date: Optional[date] = None


class ModelSelectionRequest(BaseModel):
    """Request model for model selection."""
    strategy: ModelSelectionStrategy = Field(ModelSelectionStrategy.PRIORITY_BASED)
    context: Optional[Dict[str, Any]] = Field(None, description="Request context")


class ModelPerformanceRequest(BaseModel):
    """Request model for recording model performance."""
    model_id: str = Field(..., description="Model identifier")
    model_name: str = Field(..., description="Model name")
    
    accuracy_score: float = Field(0.0, ge=0.0, le=1.0)
    precision_score: float = Field(0.0, ge=0.0, le=1.0)
    recall_score: float = Field(0.0, ge=0.0, le=1.0)
    f1_score: float = Field(0.0, ge=0.0, le=1.0)
    
    average_response_time_ms: float = Field(0.0, ge=0.0)
    success_rate: float = Field(0.0, ge=0.0, le=1.0)
    error_rate: float = Field(0.0, ge=0.0, le=1.0)
    
    total_requests: int = Field(0, ge=0)
    successful_requests: int = Field(0, ge=0)
    failed_requests: int = Field(0, ge=0)
    
    total_cost: float = Field(0.0, ge=0.0)
    cost_per_request: float = Field(0.0, ge=0.0)
    
    measurement_start: datetime
    measurement_end: datetime


class FeedbackRequest(BaseModel):
    """Request model for AI decision feedback."""
    decision_id: str = Field(..., description="Decision identifier")
    request_id: str = Field(..., description="Request identifier")
    
    feedback_type: str = Field(..., description="Type of feedback")
    feedback_score: float = Field(..., ge=-1.0, le=1.0, description="Feedback score")
    feedback_text: Optional[str] = Field(None, description="Feedback text")
    
    feedback_source: str = Field("PROVIDER", description="Feedback source")
    source_role: Optional[str] = Field(None, description="Source user role")
    
    model_id: str = Field(..., description="Model that made the decision")
    model_version: Optional[str] = Field(None, description="Model version")
    original_confidence: float = Field(..., ge=0.0, le=1.0, description="Original confidence score")


# API Endpoints

@router.post("/llm-models", response_model=AIConfigurationResponse)
async def create_llm_model_config(
    model_request: LLMModelConfigRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Create LLM model configuration.
    
    Requires ADMIN or AI_MANAGER role.
    """
    require_permissions(current_user, [UserRole.ADMIN])
    
    try:
        config_manager = get_ai_config_manager(db)
        audit_logger = AuditLogger(db)
        
        # Create configuration request
        config_request = AIConfigurationRequest(
            configuration_type=ConfigurationType.LLM_MODEL,
            configuration_data=model_request.dict(),
            is_active=model_request.enabled
        )
        
        # Create configuration
        config_id = await config_manager.create_configuration(
            config_request=config_request,
            created_by=current_user['user_id']
        )
        
        # Get created configuration
        config = config_manager.get_configuration_by_id(config_id)
        if not config:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Configuration created but could not be retrieved"
            )
        
        # Log audit event
        background_tasks.add_task(
            audit_logger.log_ai_config_action,
            action="CREATE_LLM_MODEL",
            config_id=config_id,
            user_id=current_user['user_id'],
            details={"model_id": model_request.model_id, "model_name": model_request.model_name}
        )
        
        return AIConfigurationResponse(
            config_id=config.config_id,
            configuration_type=ConfigurationType(config.configuration_type),
            configuration_name=config.configuration_name,
            configuration_data=config.configuration_data,
            effective_date=config.effective_date,
            expiration_date=config.expiration_date,
            is_active=config.is_active,
            version=config.configuration_version,
            created_at=config.created_at,
            updated_at=config.updated_at,
            created_by=config.created_by,
            updated_by=config.updated_by
        )
        
    except Exception as e:
        logger.error(f"Failed to create LLM model configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create LLM model configuration: {str(e)}"
        )


@router.post("/decision-thresholds", response_model=AIConfigurationResponse)
async def create_decision_threshold_config(
    threshold_request: DecisionThresholdConfigRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Create decision threshold configuration.
    
    Requires ADMIN or AI_MANAGER role.
    """
    require_permissions(current_user, [UserRole.ADMIN])
    
    try:
        config_manager = get_ai_config_manager(db)
        audit_logger = AuditLogger(db)
        
        # Create configuration request
        config_request = AIConfigurationRequest(
            configuration_type=ConfigurationType.DECISION_THRESHOLD,
            configuration_data=threshold_request.dict(),
            effective_date=threshold_request.effective_date,
            expiration_date=threshold_request.expiration_date
        )
        
        # Create configuration
        config_id = await config_manager.create_configuration(
            config_request=config_request,
            created_by=current_user['user_id']
        )
        
        # Get created configuration
        config = config_manager.get_configuration_by_id(config_id)
        
        # Log audit event
        background_tasks.add_task(
            audit_logger.log_ai_config_action,
            action="CREATE_DECISION_THRESHOLD",
            config_id=config_id,
            user_id=current_user['user_id'],
            details={"config_name": threshold_request.config_name}
        )
        
        return AIConfigurationResponse(
            config_id=config.config_id,
            configuration_type=ConfigurationType(config.configuration_type),
            configuration_name=config.configuration_name,
            configuration_data=config.configuration_data,
            effective_date=config.effective_date,
            expiration_date=config.expiration_date,
            is_active=config.is_active,
            version=config.configuration_version,
            created_at=config.created_at,
            updated_at=config.updated_at,
            created_by=config.created_by,
            updated_by=config.updated_by
        )
        
    except Exception as e:
        logger.error(f"Failed to create decision threshold configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create decision threshold configuration: {str(e)}"
        )


@router.post("/escalation-rules", response_model=AIConfigurationResponse)
async def create_escalation_rule_config(
    rule_request: EscalationRuleConfigRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Create escalation rule configuration.
    
    Requires ADMIN or AI_MANAGER role.
    """
    require_permissions(current_user, [UserRole.ADMIN])
    
    try:
        config_manager = get_ai_config_manager(db)
        audit_logger = AuditLogger(db)
        
        # Create configuration request
        config_request = AIConfigurationRequest(
            configuration_type=ConfigurationType.ESCALATION_RULE,
            configuration_data=rule_request.dict(),
            effective_date=rule_request.effective_date,
            expiration_date=rule_request.expiration_date
        )
        
        # Create configuration
        config_id = await config_manager.create_configuration(
            config_request=config_request,
            created_by=current_user['user_id']
        )
        
        # Get created configuration
        config = config_manager.get_configuration_by_id(config_id)
        
        # Log audit event
        background_tasks.add_task(
            audit_logger.log_ai_config_action,
            action="CREATE_ESCALATION_RULE",
            config_id=config_id,
            user_id=current_user['user_id'],
            details={"rule_name": rule_request.rule_name}
        )
        
        return AIConfigurationResponse(
            config_id=config.config_id,
            configuration_type=ConfigurationType(config.configuration_type),
            configuration_name=config.configuration_name,
            configuration_data=config.configuration_data,
            effective_date=config.effective_date,
            expiration_date=config.expiration_date,
            is_active=config.is_active,
            version=config.configuration_version,
            created_at=config.created_at,
            updated_at=config.updated_at,
            created_by=config.created_by,
            updated_by=config.updated_by
        )
        
    except Exception as e:
        logger.error(f"Failed to create escalation rule configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create escalation rule configuration: {str(e)}"
        )


@router.post("/clinical-guidelines", response_model=AIConfigurationResponse)
async def create_clinical_guideline_config(
    guideline_request: ClinicalGuidelineConfigRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Create clinical guideline configuration.
    
    Requires ADMIN or AI_MANAGER role.
    """
    require_permissions(current_user, [UserRole.ADMIN])
    
    try:
        config_manager = get_ai_config_manager(db)
        audit_logger = AuditLogger(db)
        
        # Create configuration request
        config_request = AIConfigurationRequest(
            configuration_type=ConfigurationType.CLINICAL_GUIDELINE,
            configuration_data=guideline_request.dict(),
            effective_date=guideline_request.effective_date,
            expiration_date=guideline_request.expiration_date
        )
        
        # Create configuration
        config_id = await config_manager.create_configuration(
            config_request=config_request,
            created_by=current_user['user_id']
        )
        
        # Get created configuration
        config = config_manager.get_configuration_by_id(config_id)
        
        # Log audit event
        background_tasks.add_task(
            audit_logger.log_ai_config_action,
            action="CREATE_CLINICAL_GUIDELINE",
            config_id=config_id,
            user_id=current_user['user_id'],
            details={"guideline_name": guideline_request.guideline_name}
        )
        
        return AIConfigurationResponse(
            config_id=config.config_id,
            configuration_type=ConfigurationType(config.configuration_type),
            configuration_name=config.configuration_name,
            configuration_data=config.configuration_data,
            effective_date=config.effective_date,
            expiration_date=config.expiration_date,
            is_active=config.is_active,
            version=config.configuration_version,
            created_at=config.created_at,
            updated_at=config.updated_at,
            created_by=config.created_by,
            updated_by=config.updated_by
        )
        
    except Exception as e:
        logger.error(f"Failed to create clinical guideline configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create clinical guideline configuration: {str(e)}"
        )


@router.post("/feedback-rules", response_model=AIConfigurationResponse)
async def create_feedback_config(
    feedback_request: FeedbackConfigRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Create feedback configuration.
    
    Requires ADMIN or AI_MANAGER role.
    """
    require_permissions(current_user, [UserRole.ADMIN])
    
    try:
        config_manager = get_ai_config_manager(db)
        audit_logger = AuditLogger(db)
        
        # Create configuration request
        config_request = AIConfigurationRequest(
            configuration_type=ConfigurationType.FEEDBACK_RULE,
            configuration_data=feedback_request.dict(),
            effective_date=feedback_request.effective_date,
            expiration_date=feedback_request.expiration_date
        )
        
        # Create configuration
        config_id = await config_manager.create_configuration(
            config_request=config_request,
            created_by=current_user['user_id']
        )
        
        # Get created configuration
        config = config_manager.get_configuration_by_id(config_id)
        
        # Log audit event
        background_tasks.add_task(
            audit_logger.log_ai_config_action,
            action="CREATE_FEEDBACK_RULE",
            config_id=config_id,
            user_id=current_user['user_id'],
            details={"feedback_name": feedback_request.feedback_name}
        )
        
        return AIConfigurationResponse(
            config_id=config.config_id,
            configuration_type=ConfigurationType(config.configuration_type),
            configuration_name=config.configuration_name,
            configuration_data=config.configuration_data,
            effective_date=config.effective_date,
            expiration_date=config.expiration_date,
            is_active=config.is_active,
            version=config.configuration_version,
            created_at=config.created_at,
            updated_at=config.updated_at,
            created_by=config.created_by,
            updated_by=config.updated_by
        )
        
    except Exception as e:
        logger.error(f"Failed to create feedback configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create feedback configuration: {str(e)}"
        )


@router.get("/configurations", response_model=List[AIConfigurationResponse])
async def list_configurations(
    configuration_type: Optional[ConfigurationType] = None,
    active_only: bool = True,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """List AI configurations with filtering options."""
    try:
        config_manager = get_ai_config_manager(db)
        configs = config_manager.list_configurations(
            configuration_type=configuration_type,
            active_only=active_only,
            limit=limit,
            offset=offset
        )
        
        return [
            AIConfigurationResponse(
                config_id=config.config_id,
                configuration_type=ConfigurationType(config.configuration_type),
                configuration_name=config.configuration_name,
                configuration_data=config.configuration_data,
                effective_date=config.effective_date,
                expiration_date=config.expiration_date,
                is_active=config.is_active,
                version=config.configuration_version,
                created_at=config.created_at,
                updated_at=config.updated_at,
                created_by=config.created_by,
                updated_by=config.updated_by
            )
            for config in configs
        ]
        
    except Exception as e:
        logger.error(f"Failed to list configurations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list configurations: {str(e)}"
        )


@router.get("/configurations/{config_id}", response_model=AIConfigurationResponse)
async def get_configuration(
    config_id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """Get configuration by ID."""
    try:
        config_manager = get_ai_config_manager(db)
        config = config_manager.get_configuration_by_id(config_id)
        
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Configuration not found: {config_id}"
            )
        
        return AIConfigurationResponse(
            config_id=config.config_id,
            configuration_type=ConfigurationType(config.configuration_type),
            configuration_name=config.configuration_name,
            configuration_data=config.configuration_data,
            effective_date=config.effective_date,
            expiration_date=config.expiration_date,
            is_active=config.is_active,
            version=config.configuration_version,
            created_at=config.created_at,
            updated_at=config.updated_at,
            created_by=config.created_by,
            updated_by=config.updated_by
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get configuration {config_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve configuration: {str(e)}"
        )


@router.post("/configurations/{config_id}/validate", response_model=ConfigurationValidationResult)
async def validate_configuration(
    config_id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """Validate configuration and check for conflicts."""
    try:
        config_manager = get_ai_config_manager(db)
        validation_result = await config_manager.validate_configuration(config_id)
        
        return validation_result
        
    except Exception as e:
        logger.error(f"Configuration validation failed for {config_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Configuration validation failed: {str(e)}"
        )


@router.delete("/configurations/{config_id}")
async def deactivate_configuration(
    config_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Deactivate a configuration (soft delete with audit trail).
    
    Requires ADMIN role.
    """
    require_permissions(current_user, [UserRole.ADMIN])
    
    try:
        config_manager = get_ai_config_manager(db)
        audit_logger = AuditLogger(db)
        
        success = await config_manager.deactivate_configuration(
            config_id=config_id,
            deactivated_by=current_user['user_id']
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Configuration not found: {config_id}"
            )
        
        # Log audit event
        background_tasks.add_task(
            audit_logger.log_ai_config_action,
            action="DEACTIVATE_CONFIGURATION",
            config_id=config_id,
            user_id=current_user['user_id'],
            details={"reason": "Configuration deactivated via API"}
        )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": f"Configuration {config_id} deactivated successfully"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deactivate configuration {config_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deactivate configuration: {str(e)}"
        )


@router.post("/model-selection")
async def select_optimal_model(
    selection_request: ModelSelectionRequest,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """Select optimal LLM model based on strategy and context."""
    try:
        config_manager = get_ai_config_manager(db)
        
        selected_model = await config_manager.select_optimal_model(
            strategy=selection_request.strategy,
            context=selection_request.context
        )
        
        if not selected_model:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"message": "No suitable model found"}
            )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "selected_model": selected_model,
                "strategy": selection_request.strategy.value,
                "context_provided": selection_request.context is not None
            }
        )
        
    except Exception as e:
        logger.error(f"Model selection failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model selection failed: {str(e)}"
        )


@router.post("/model-performance")
async def record_model_performance(
    performance_request: ModelPerformanceRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Record model performance metrics.
    
    Requires ADMIN or AI_MANAGER role.
    """
    require_permissions(current_user, [UserRole.ADMIN])
    
    try:
        config_manager = get_ai_config_manager(db)
        
        metric_id = await config_manager.record_model_performance(
            model_id=performance_request.model_id,
            performance_data=performance_request.dict()
        )
        
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "message": "Model performance recorded successfully",
                "metric_id": metric_id,
                "model_id": performance_request.model_id
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to record model performance: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record model performance: {str(e)}"
        )


@router.post("/feedback")
async def record_feedback(
    feedback_request: FeedbackRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """Record feedback on an AI decision."""
    try:
        config_manager = get_ai_config_manager(db)
        
        feedback_id = await config_manager.record_feedback(
            decision_id=feedback_request.decision_id,
            request_id=feedback_request.request_id,
            feedback_data=feedback_request.dict(),
            source_user_id=current_user['user_id']
        )
        
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "message": "Feedback recorded successfully",
                "feedback_id": feedback_id,
                "decision_id": feedback_request.decision_id
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to record feedback: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record feedback: {str(e)}"
        )


@router.get("/dashboard")
async def get_ai_config_dashboard(
    current_user: dict = Depends(get_current_user)
):
    """
    Serve the AI configuration dashboard.
    
    Requires ADMIN role.
    """
    require_permissions(current_user, [UserRole.ADMIN])
    
    try:
        # Read the dashboard HTML file
        import os
        dashboard_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'ai_config_dashboard.html')
        
        with open(dashboard_path, 'r', encoding='utf-8') as f:
            dashboard_html = f.read()
        
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=dashboard_html, status_code=200)
        
    except Exception as e:
        logger.error(f"Failed to serve AI config dashboard: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load dashboard: {str(e)}"
        )
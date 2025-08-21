"""
AI Configuration Models

This module defines data models for AI configuration management,
including LLM parameters, decision thresholds, and clinical guidelines.
"""

from datetime import datetime, date
from typing import Dict, List, Optional, Any, Union
from enum import Enum
from pydantic import BaseModel, Field, field_validator
from dataclasses import dataclass


class ConfigurationType(str, Enum):
    """Types of AI configuration."""
    LLM_MODEL = "llm_model"
    DECISION_THRESHOLD = "decision_threshold"
    ESCALATION_RULE = "escalation_rule"
    CLINICAL_GUIDELINE = "clinical_guideline"
    FEEDBACK_RULE = "feedback_rule"


class ModelSelectionStrategy(str, Enum):
    """Strategies for LLM model selection."""
    PRIORITY_BASED = "priority_based"
    PERFORMANCE_BASED = "performance_based"
    COST_OPTIMIZED = "cost_optimized"
    COMPLEXITY_BASED = "complexity_based"


class EscalationTrigger(str, Enum):
    """Triggers for decision escalation."""
    LOW_CONFIDENCE = "low_confidence"
    POLICY_CONFLICT = "policy_conflict"
    HIGH_COST_PROCEDURE = "high_cost_procedure"
    RARE_CONDITION = "rare_condition"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class FeedbackType(str, Enum):
    """Types of feedback for AI improvement."""
    DECISION_ACCURACY = "decision_accuracy"
    REASONING_QUALITY = "reasoning_quality"
    POLICY_COMPLIANCE = "policy_compliance"
    CLINICAL_APPROPRIATENESS = "clinical_appropriateness"


@dataclass
class LLMModelConfiguration:
    """Configuration for an LLM model."""
    model_id: str
    model_name: str
    deployment_type: str
    model_type: str
    priority: int
    enabled: bool
    
    # Model parameters
    max_tokens: int = 512
    temperature: float = 0.1
    top_p: float = 0.9
    confidence_threshold: float = 0.7
    timeout_seconds: int = 30
    max_retries: int = 3
    
    # Performance settings
    use_auth_token: bool = True
    device: Optional[str] = None
    torch_dtype: str = "auto"
    load_in_8bit: bool = False
    load_in_4bit: bool = False
    
    # Usage constraints
    max_requests_per_minute: int = 60
    max_concurrent_requests: int = 10
    cost_per_request: float = 0.0
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = ""
    updated_by: str = ""


class DecisionThresholdConfig(BaseModel):
    """Configuration for decision thresholds."""
    config_id: str = Field(..., description="Unique configuration identifier")
    config_name: str = Field(..., description="Human-readable configuration name")
    
    # Confidence thresholds
    auto_approve_threshold: float = Field(0.9, ge=0.0, le=1.0, description="Threshold for automatic approval")
    auto_deny_threshold: float = Field(0.8, ge=0.0, le=1.0, description="Threshold for automatic denial")
    manual_review_threshold: float = Field(0.6, ge=0.0, le=1.0, description="Threshold requiring manual review")
    
    # Procedure-specific thresholds
    procedure_thresholds: Dict[str, Dict[str, float]] = Field(
        default_factory=dict,
        description="Procedure-specific threshold overrides"
    )
    
    # Payer-specific thresholds
    payer_thresholds: Dict[str, Dict[str, float]] = Field(
        default_factory=dict,
        description="Payer-specific threshold overrides"
    )
    
    # Risk-based adjustments
    high_risk_adjustment: float = Field(-0.1, description="Adjustment for high-risk procedures")
    low_risk_adjustment: float = Field(0.05, description="Adjustment for low-risk procedures")
    
    # Metadata
    effective_date: date = Field(default_factory=date.today)
    expiration_date: Optional[date] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = ""
    updated_by: str = ""
    
    @field_validator('auto_deny_threshold')
    @classmethod
    def validate_auto_deny_threshold(cls, v, info):
        """Validate auto deny threshold is less than auto approve threshold."""
        if info.data and 'auto_approve_threshold' in info.data and v >= info.data['auto_approve_threshold']:
            raise ValueError("Auto deny threshold must be less than auto approve threshold")
        return v
    
    @field_validator('manual_review_threshold')
    @classmethod
    def validate_manual_review_threshold(cls, v, info):
        """Validate manual review threshold is less than auto deny threshold."""
        if info.data and 'auto_deny_threshold' in info.data and v >= info.data['auto_deny_threshold']:
            raise ValueError("Manual review threshold must be less than auto deny threshold")
        return v


class EscalationRuleConfig(BaseModel):
    """Configuration for escalation rules."""
    rule_id: str = Field(..., description="Unique rule identifier")
    rule_name: str = Field(..., description="Human-readable rule name")
    
    # Trigger conditions
    triggers: List[EscalationTrigger] = Field(..., description="Conditions that trigger escalation")
    trigger_conditions: Dict[str, Any] = Field(
        default_factory=dict,
        description="Specific conditions for each trigger"
    )
    
    # Escalation targets
    escalation_queue: str = Field(..., description="Queue to escalate to")
    escalation_priority: int = Field(1, ge=1, le=5, description="Escalation priority (1=highest)")
    
    # Notification settings
    notify_immediately: bool = Field(True, description="Send immediate notification")
    notification_recipients: List[str] = Field(
        default_factory=list,
        description="List of users/roles to notify"
    )
    
    # Time limits
    escalation_timeout_hours: int = Field(24, ge=1, description="Hours before auto-escalation")
    max_escalation_level: int = Field(3, ge=1, le=5, description="Maximum escalation level")
    
    # Metadata
    effective_date: date = Field(default_factory=date.today)
    expiration_date: Optional[date] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = ""
    updated_by: str = ""


class ClinicalGuidelineConfig(BaseModel):
    """Configuration for clinical guidelines."""
    guideline_id: str = Field(..., description="Unique guideline identifier")
    guideline_name: str = Field(..., description="Human-readable guideline name")
    guideline_version: str = Field("1.0", description="Guideline version")
    
    # Guideline content
    guideline_text: str = Field(..., description="Full guideline text")
    guideline_summary: str = Field(..., description="Brief guideline summary")
    
    # Applicability
    applicable_procedures: List[str] = Field(
        default_factory=list,
        description="CPT codes this guideline applies to"
    )
    applicable_diagnoses: List[str] = Field(
        default_factory=list,
        description="ICD-10 codes this guideline applies to"
    )
    applicable_payers: List[str] = Field(
        default_factory=list,
        description="Payers this guideline applies to (empty = all)"
    )
    
    # Guideline rules
    decision_rules: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Structured decision rules"
    )
    contraindications: List[str] = Field(
        default_factory=list,
        description="Absolute contraindications"
    )
    relative_contraindications: List[str] = Field(
        default_factory=list,
        description="Relative contraindications"
    )
    
    # Evidence and references
    evidence_level: str = Field("", description="Level of evidence (A, B, C)")
    references: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Literature references"
    )
    source_organization: str = Field("", description="Guideline source organization")
    
    # Version control
    parent_guideline_id: Optional[str] = None
    change_summary: str = Field("", description="Summary of changes from previous version")
    
    # Metadata
    effective_date: date = Field(default_factory=date.today)
    expiration_date: Optional[date] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = ""
    updated_by: str = ""


class FeedbackConfig(BaseModel):
    """Configuration for AI feedback and learning."""
    feedback_id: str = Field(..., description="Unique feedback configuration identifier")
    feedback_name: str = Field(..., description="Human-readable feedback name")
    
    # Feedback collection
    feedback_types: List[FeedbackType] = Field(..., description="Types of feedback to collect")
    collection_triggers: List[str] = Field(
        default_factory=list,
        description="Events that trigger feedback collection"
    )
    
    # Feedback processing
    auto_process_feedback: bool = Field(True, description="Automatically process feedback")
    feedback_weight: float = Field(1.0, ge=0.0, le=10.0, description="Weight of this feedback type")
    minimum_feedback_count: int = Field(5, ge=1, description="Minimum feedback needed for learning")
    
    # Learning parameters
    learning_rate: float = Field(0.01, ge=0.001, le=1.0, description="Learning rate for model updates")
    feedback_decay_days: int = Field(90, ge=1, description="Days after which feedback weight decays")
    
    # Quality filters
    minimum_confidence_for_learning: float = Field(0.7, ge=0.0, le=1.0)
    exclude_outliers: bool = Field(True, description="Exclude statistical outliers")
    require_expert_validation: bool = Field(False, description="Require expert validation")
    
    # Metadata
    effective_date: date = Field(default_factory=date.today)
    expiration_date: Optional[date] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = ""
    updated_by: str = ""


class AIConfigurationRequest(BaseModel):
    """Request model for AI configuration operations."""
    configuration_type: ConfigurationType
    configuration_data: Dict[str, Any]
    effective_date: Optional[date] = None
    expiration_date: Optional[date] = None
    is_active: bool = True


class AIConfigurationResponse(BaseModel):
    """Response model for AI configuration operations."""
    config_id: str
    configuration_type: ConfigurationType
    configuration_name: str
    configuration_data: Dict[str, Any]
    effective_date: date
    expiration_date: Optional[date]
    is_active: bool
    version: str
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str


class ConfigurationValidationResult(BaseModel):
    """Result of configuration validation."""
    is_valid: bool
    validation_errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class ModelPerformanceMetrics(BaseModel):
    """Performance metrics for LLM models."""
    model_id: str
    model_name: str
    
    # Accuracy metrics
    accuracy_score: float = Field(0.0, ge=0.0, le=1.0)
    precision_score: float = Field(0.0, ge=0.0, le=1.0)
    recall_score: float = Field(0.0, ge=0.0, le=1.0)
    f1_score: float = Field(0.0, ge=0.0, le=1.0)
    
    # Performance metrics
    average_response_time_ms: float = Field(0.0, ge=0.0)
    success_rate: float = Field(0.0, ge=0.0, le=1.0)
    error_rate: float = Field(0.0, ge=0.0, le=1.0)
    
    # Usage metrics
    total_requests: int = Field(0, ge=0)
    successful_requests: int = Field(0, ge=0)
    failed_requests: int = Field(0, ge=0)
    
    # Cost metrics
    total_cost: float = Field(0.0, ge=0.0)
    cost_per_request: float = Field(0.0, ge=0.0)
    
    # Time period
    measurement_start: datetime
    measurement_end: datetime
    
    # Metadata
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class ConfigurationAuditLog(BaseModel):
    """Audit log entry for configuration changes."""
    audit_id: str
    configuration_type: ConfigurationType
    config_id: str
    action: str  # CREATE, UPDATE, DELETE, ACTIVATE, DEACTIVATE
    
    # Change details
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    change_summary: str = ""
    
    # User and timestamp
    user_id: str
    user_role: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Additional context
    reason: str = ""
    approval_required: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
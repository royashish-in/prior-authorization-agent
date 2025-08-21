"""
SQLAlchemy database models for the Prior Authorization Agent.

These models represent the database schema for authorization requests,
decisions, and coverage policies with PHI encryption support.
"""

import json
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from sqlalchemy import (
    Column, String, Integer, DateTime, Text, Boolean, 
    Numeric, Date, ForeignKey, Index, JSON
)
from sqlalchemy.orm import relationship, validates
# Remove MySQL-specific import

from src.core.encryption import PHIEncryption
from src.models.enums import RequestStatus, DecisionStatus, UrgencyLevel, Gender, ProcedureType
from src.database.base import Base


class AuthorizationRequestDB(Base):
    """
    Database model for authorization requests.
    
    Stores structured authorization request data with encrypted PHI fields.
    """
    __tablename__ = "authorization_requests"
    
    # Primary key and identifiers
    request_id = Column(String(36), primary_key=True, index=True)
    provider_id = Column(String(50), nullable=False, index=True)
    
    # Encrypted patient demographics (stored as encrypted JSON)
    patient_demographics_encrypted = Column(Text, nullable=False)
    
    # Medical codes (stored as JSON for flexibility)
    diagnosis_codes = Column(JSON, nullable=False)
    procedure_codes = Column(JSON, nullable=False)
    
    # Encrypted clinical notes
    clinical_notes_encrypted = Column(Text, nullable=True)
    
    # Request metadata
    procedure_type = Column(String(20), nullable=False)
    urgency_level = Column(String(20), nullable=False, default=UrgencyLevel.ROUTINE.value)
    status = Column(String(20), nullable=False, default=RequestStatus.SUBMITTED.value, index=True)
    
    # Timestamps
    submitted_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    decisions = relationship("AuthorizationDecisionDB", back_populates="request", cascade="all, delete-orphan")
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_provider_status', 'provider_id', 'status'),
        Index('idx_submitted_at', 'submitted_at'),
        Index('idx_status_updated', 'status', 'updated_at'),
    )
    
    @validates('status')
    def validate_status(self, key, status):
        """Validate request status values."""
        if status not in [s.value for s in RequestStatus]:
            raise ValueError(f"Invalid request status: {status}")
        return status
    
    @validates('urgency_level')
    def validate_urgency_level(self, key, urgency):
        """Validate urgency level values."""
        if urgency not in [u.value for u in UrgencyLevel]:
            raise ValueError(f"Invalid urgency level: {urgency}")
        return urgency
    
    @validates('procedure_type')
    def validate_procedure_type(self, key, proc_type):
        """Validate procedure type values."""
        if proc_type not in [p.value for p in ProcedureType]:
            raise ValueError(f"Invalid procedure type: {proc_type}")
        return proc_type
    
    def encrypt_patient_demographics(self, demographics_dict: Dict[str, Any]) -> None:
        """Encrypt patient demographics before storing."""
        encryption = PHIEncryption()
        encrypted_data = encryption.encrypt(json.dumps(demographics_dict))
        self.patient_demographics_encrypted = encrypted_data
    
    def decrypt_patient_demographics(self) -> Dict[str, Any]:
        """Decrypt patient demographics for use."""
        if not self.patient_demographics_encrypted:
            return {}
        
        encryption = PHIEncryption()
        decrypted_data = encryption.decrypt(self.patient_demographics_encrypted)
        return json.loads(decrypted_data)
    
    def encrypt_clinical_notes(self, notes: Optional[str]) -> None:
        """Encrypt clinical notes before storing."""
        if notes is None:
            self.clinical_notes_encrypted = None
            return
        
        encryption = PHIEncryption()
        self.clinical_notes_encrypted = encryption.encrypt(notes)
    
    def decrypt_clinical_notes(self) -> Optional[str]:
        """Decrypt clinical notes for use."""
        if not self.clinical_notes_encrypted:
            return None
        
        encryption = PHIEncryption()
        return encryption.decrypt(self.clinical_notes_encrypted)
    
    def __repr__(self):
        return f"<AuthorizationRequest(id={self.request_id}, provider={self.provider_id}, status={self.status})>"


class AuthorizationDecisionDB(Base):
    """
    Database model for authorization decisions.
    
    Stores decision outcomes, reasoning, and policy references.
    """
    __tablename__ = "authorization_decisions"
    
    # Primary key and relationships
    decision_id = Column(String(36), primary_key=True, index=True)
    request_id = Column(String(36), ForeignKey('authorization_requests.request_id'), nullable=False, index=True)
    
    # Decision outcome
    status = Column(String(20), nullable=False, index=True)
    
    # Decision details (stored as JSON for flexibility)
    reasoning = Column(JSON, nullable=False)
    policy_references = Column(JSON, nullable=True)
    additional_info_needed = Column(JSON, nullable=True)
    alternative_procedures = Column(JSON, nullable=True)
    
    # Authorization details
    authorization_number = Column(String(50), nullable=True, unique=True, index=True)
    valid_until = Column(DateTime, nullable=True)
    confidence_score = Column(Numeric(3, 2), nullable=False)
    
    # Timestamp
    decided_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Relationships
    request = relationship("AuthorizationRequestDB", back_populates="decisions")
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_request_decided', 'request_id', 'decided_at'),
        Index('idx_status_decided', 'status', 'decided_at'),
        Index('idx_auth_number', 'authorization_number'),
    )
    
    @validates('status')
    def validate_status(self, key, status):
        """Validate decision status values."""
        if status not in [s.value for s in DecisionStatus]:
            raise ValueError(f"Invalid decision status: {status}")
        return status
    
    @validates('confidence_score')
    def validate_confidence_score(self, key, score):
        """Validate confidence score range."""
        if not 0.0 <= float(score) <= 1.0:
            raise ValueError(f"Confidence score must be between 0.0 and 1.0, got: {score}")
        return score
    
    @validates('reasoning')
    def validate_reasoning(self, key, reasoning):
        """Validate reasoning is a non-empty list."""
        if not isinstance(reasoning, list) or len(reasoning) == 0:
            raise ValueError("Reasoning must be a non-empty list")
        return reasoning
    
    def __repr__(self):
        return f"<AuthorizationDecision(id={self.decision_id}, request={self.request_id}, status={self.status})>"


class CoveragePolicyDB(Base):
    """
    Database model for coverage policies.
    
    Stores payer-specific coverage policies and CMS guidelines.
    """
    __tablename__ = "coverage_policies"
    
    # Primary key
    policy_id = Column(String(36), primary_key=True, index=True)
    
    # Policy identification
    payer_id = Column(String(50), nullable=False, index=True)
    procedure_code = Column(String(10), nullable=False, index=True)
    
    # Policy details (stored as JSON for flexibility)
    diagnosis_codes = Column(JSON, nullable=True)  # List of covered diagnosis codes
    coverage_criteria = Column(JSON, nullable=False)  # Detailed coverage criteria
    
    # Policy metadata
    policy_type = Column(String(20), nullable=False, index=True)  # NCD, LCD, PAYER
    policy_name = Column(String(200), nullable=False)
    policy_version = Column(String(20), nullable=False, default="1.0")
    
    # Validity dates
    effective_date = Column(Date, nullable=False, index=True)
    expiration_date = Column(Date, nullable=True, index=True)
    
    # Status
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    
    # Audit fields
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(50), nullable=False)
    updated_by = Column(String(50), nullable=False)
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_payer_procedure', 'payer_id', 'procedure_code'),
        Index('idx_effective_date', 'effective_date'),
        Index('idx_active_policies', 'is_active', 'effective_date'),
        Index('idx_policy_type_active', 'policy_type', 'is_active'),
    )
    
    @validates('policy_type')
    def validate_policy_type(self, key, policy_type):
        """Validate policy type values."""
        valid_types = ['NCD', 'LCD', 'PAYER']
        if policy_type not in valid_types:
            raise ValueError(f"Invalid policy type: {policy_type}. Must be one of: {valid_types}")
        return policy_type
    
    @validates('coverage_criteria')
    def validate_coverage_criteria(self, key, criteria):
        """Validate coverage criteria is not empty."""
        if not isinstance(criteria, dict) or len(criteria) == 0:
            raise ValueError("Coverage criteria must be a non-empty dictionary")
        return criteria
    
    @validates('effective_date')
    def validate_effective_date(self, key, effective_date):
        """Validate effective date is not in the future for active policies."""
        if self.is_active and effective_date > date.today():
            raise ValueError("Effective date cannot be in the future for active policies")
        return effective_date
    
    def is_currently_effective(self) -> bool:
        """Check if the policy is currently effective."""
        today = date.today()
        if not self.is_active:
            return False
        if self.effective_date > today:
            return False
        if self.expiration_date and self.expiration_date < today:
            return False
        return True
    
    def __repr__(self):
        return f"<CoveragePolicy(id={self.policy_id}, payer={self.payer_id}, procedure={self.procedure_code})>"


class AIConfigurationDB(Base):
    """
    Database model for AI configuration management.
    
    Stores LLM parameters, decision thresholds, escalation rules, and clinical guidelines.
    """
    __tablename__ = "ai_configurations"
    
    # Primary key
    config_id = Column(String(36), primary_key=True, index=True)
    
    # Configuration identification
    configuration_type = Column(String(50), nullable=False, index=True)
    configuration_name = Column(String(200), nullable=False)
    configuration_version = Column(String(20), nullable=False, default="1.0")
    
    # Configuration data (stored as JSON for flexibility)
    configuration_data = Column(JSON, nullable=False)
    
    # Validity and status
    effective_date = Column(Date, nullable=False, index=True)
    expiration_date = Column(Date, nullable=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    
    # Version control
    parent_config_id = Column(String(36), nullable=True, index=True)
    change_summary = Column(Text, nullable=True)
    
    # Audit fields
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(50), nullable=False)
    updated_by = Column(String(50), nullable=False)
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_config_type_active', 'configuration_type', 'is_active'),
        Index('idx_ai_config_effective_date', 'effective_date'),
        Index('idx_config_version', 'config_id', 'configuration_version'),
        Index('idx_parent_config', 'parent_config_id'),
    )
    
    @validates('configuration_type')
    def validate_configuration_type(self, key, config_type):
        """Validate configuration type values."""
        valid_types = ['llm_model', 'decision_threshold', 'escalation_rule', 'clinical_guideline', 'feedback_rule']
        if config_type not in valid_types:
            raise ValueError(f"Invalid configuration type: {config_type}. Must be one of: {valid_types}")
        return config_type
    
    @validates('configuration_data')
    def validate_configuration_data(self, key, data):
        """Validate configuration data is not empty."""
        if not isinstance(data, dict) or len(data) == 0:
            raise ValueError("Configuration data must be a non-empty dictionary")
        return data
    
    def is_currently_effective(self) -> bool:
        """Check if the configuration is currently effective."""
        today = date.today()
        if not self.is_active:
            return False
        if self.effective_date > today:
            return False
        if self.expiration_date and self.expiration_date < today:
            return False
        return True
    
    def __repr__(self):
        return f"<AIConfiguration(id={self.config_id}, type={self.configuration_type}, name={self.configuration_name})>"


class ModelPerformanceMetricsDB(Base):
    """
    Database model for LLM model performance metrics.
    
    Stores performance data for model selection and optimization.
    """
    __tablename__ = "model_performance_metrics"
    
    # Primary key
    metric_id = Column(String(36), primary_key=True, index=True)
    
    # Model identification
    model_id = Column(String(100), nullable=False, index=True)
    model_name = Column(String(200), nullable=False)
    
    # Accuracy metrics
    accuracy_score = Column(Numeric(5, 4), nullable=False, default=0.0)
    precision_score = Column(Numeric(5, 4), nullable=False, default=0.0)
    recall_score = Column(Numeric(5, 4), nullable=False, default=0.0)
    f1_score = Column(Numeric(5, 4), nullable=False, default=0.0)
    
    # Performance metrics
    average_response_time_ms = Column(Numeric(10, 2), nullable=False, default=0.0)
    success_rate = Column(Numeric(5, 4), nullable=False, default=0.0)
    error_rate = Column(Numeric(5, 4), nullable=False, default=0.0)
    
    # Usage metrics
    total_requests = Column(Integer, nullable=False, default=0)
    successful_requests = Column(Integer, nullable=False, default=0)
    failed_requests = Column(Integer, nullable=False, default=0)
    
    # Cost metrics
    total_cost = Column(Numeric(10, 4), nullable=False, default=0.0)
    cost_per_request = Column(Numeric(8, 6), nullable=False, default=0.0)
    
    # Time period
    measurement_start = Column(DateTime, nullable=False, index=True)
    measurement_end = Column(DateTime, nullable=False, index=True)
    
    # Metadata
    last_updated = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_model_time_range', 'model_id', 'measurement_start', 'measurement_end'),
        Index('idx_performance_ranking', 'accuracy_score', 'average_response_time_ms'),
        Index('idx_cost_efficiency', 'cost_per_request', 'success_rate'),
    )
    
    @validates('accuracy_score', 'precision_score', 'recall_score', 'f1_score', 'success_rate', 'error_rate')
    def validate_score_range(self, key, score):
        """Validate score is between 0.0 and 1.0."""
        if not 0.0 <= float(score) <= 1.0:
            raise ValueError(f"{key} must be between 0.0 and 1.0, got: {score}")
        return score
    
    @validates('total_requests', 'successful_requests', 'failed_requests')
    def validate_request_counts(self, key, count):
        """Validate request counts are non-negative."""
        if int(count) < 0:
            raise ValueError(f"{key} must be non-negative, got: {count}")
        return count
    
    def __repr__(self):
        return f"<ModelPerformanceMetrics(model={self.model_id}, accuracy={self.accuracy_score})>"


class ConfigurationAuditLogDB(Base):
    """
    Database model for AI configuration audit logs.
    
    Tracks all changes to AI configurations for compliance and debugging.
    """
    __tablename__ = "configuration_audit_logs"
    
    # Primary key
    audit_id = Column(String(36), primary_key=True, index=True)
    
    # Configuration reference
    configuration_type = Column(String(50), nullable=False, index=True)
    config_id = Column(String(36), nullable=False, index=True)
    action = Column(String(20), nullable=False, index=True)  # CREATE, UPDATE, DELETE, ACTIVATE, DEACTIVATE
    
    # Change details (stored as JSON)
    old_values = Column(JSON, nullable=True)
    new_values = Column(JSON, nullable=True)
    change_summary = Column(Text, nullable=True)
    
    # User and timestamp
    user_id = Column(String(50), nullable=False, index=True)
    user_role = Column(String(50), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Additional context
    reason = Column(Text, nullable=True)
    approval_required = Column(Boolean, nullable=False, default=False)
    approved_by = Column(String(50), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_config_audit', 'config_id', 'timestamp'),
        Index('idx_user_audit', 'user_id', 'timestamp'),
        Index('idx_action_audit', 'action', 'timestamp'),
        Index('idx_approval_audit', 'approval_required', 'approved_at'),
    )
    
    @validates('action')
    def validate_action(self, key, action):
        """Validate audit action values."""
        valid_actions = ['CREATE', 'UPDATE', 'DELETE', 'ACTIVATE', 'DEACTIVATE', 'APPROVE', 'REJECT']
        if action not in valid_actions:
            raise ValueError(f"Invalid audit action: {action}. Must be one of: {valid_actions}")
        return action
    
    def __repr__(self):
        return f"<ConfigurationAuditLog(id={self.audit_id}, action={self.action}, config={self.config_id})>"


class AIFeedbackDB(Base):
    """
    Database model for AI decision feedback.
    
    Stores feedback on AI decisions for continuous learning and improvement.
    """
    __tablename__ = "ai_feedback"
    
    # Primary key
    feedback_id = Column(String(36), primary_key=True, index=True)
    
    # Decision reference
    decision_id = Column(String(36), ForeignKey('authorization_decisions.decision_id'), nullable=False, index=True)
    request_id = Column(String(36), ForeignKey('authorization_requests.request_id'), nullable=False, index=True)
    
    # Feedback details
    feedback_type = Column(String(50), nullable=False, index=True)
    feedback_score = Column(Numeric(3, 2), nullable=False)  # 0.0 to 1.0 or -1.0 to 1.0
    feedback_text = Column(Text, nullable=True)
    
    # Feedback source
    feedback_source = Column(String(50), nullable=False, index=True)  # PROVIDER, PAYER, EXPERT, SYSTEM
    source_user_id = Column(String(50), nullable=True, index=True)
    source_role = Column(String(50), nullable=True)
    
    # Model context
    model_id = Column(String(100), nullable=False, index=True)
    model_version = Column(String(20), nullable=True)
    original_confidence = Column(Numeric(3, 2), nullable=False)
    
    # Processing status
    processed = Column(Boolean, nullable=False, default=False, index=True)
    processed_at = Column(DateTime, nullable=True)
    processing_notes = Column(Text, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Relationships
    decision = relationship("AuthorizationDecisionDB")
    request = relationship("AuthorizationRequestDB")
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_feedback_model', 'model_id', 'feedback_type'),
        Index('idx_feedback_processing', 'processed', 'created_at'),
        Index('idx_feedback_source', 'feedback_source', 'created_at'),
        Index('idx_decision_feedback', 'decision_id', 'feedback_type'),
    )
    
    @validates('feedback_score')
    def validate_feedback_score(self, key, score):
        """Validate feedback score range."""
        if not -1.0 <= float(score) <= 1.0:
            raise ValueError(f"Feedback score must be between -1.0 and 1.0, got: {score}")
        return score
    
    @validates('feedback_type')
    def validate_feedback_type(self, key, feedback_type):
        """Validate feedback type values."""
        valid_types = ['decision_accuracy', 'reasoning_quality', 'policy_compliance', 'clinical_appropriateness']
        if feedback_type not in valid_types:
            raise ValueError(f"Invalid feedback type: {feedback_type}. Must be one of: {valid_types}")
        return feedback_type
    
    @validates('feedback_source')
    def validate_feedback_source(self, key, source):
        """Validate feedback source values."""
        valid_sources = ['PROVIDER', 'PAYER', 'EXPERT', 'SYSTEM', 'PATIENT']
        if source not in valid_sources:
            raise ValueError(f"Invalid feedback source: {source}. Must be one of: {valid_sources}")
        return source
    
    def __repr__(self):
        return f"<AIFeedback(id={self.feedback_id}, type={self.feedback_type}, score={self.feedback_score})>"
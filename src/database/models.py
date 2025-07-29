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
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship, validates
# Remove MySQL-specific import

from src.core.encryption import PHIEncryption
from src.models.enums import RequestStatus, DecisionStatus, UrgencyLevel, Gender, ProcedureType

Base = declarative_base()


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
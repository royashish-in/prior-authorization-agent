"""
Authorization request and decision models.
"""

from datetime import datetime, timezone
from typing import List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from .patient import PatientDemographics
from .medical_codes import ICD10Code, CPTCode, HCPCSCode
from .enums import RequestStatus, DecisionStatus, UrgencyLevel, ProcedureType


class AuthorizationRequest(BaseModel):
    """
    Prior authorization request model.
    
    Contains all information needed to process an authorization request
    for outpatient imaging services.
    """
    request_id: str = Field(..., description="Unique request identifier")
    provider_id: str = Field(..., description="Healthcare provider identifier")
    patient_demographics: PatientDemographics = Field(..., description="Patient demographic information")
    diagnosis_codes: List[ICD10Code] = Field(..., min_length=1, description="ICD-10 diagnosis codes")
    procedure_codes: List[Union[CPTCode, HCPCSCode]] = Field(..., min_length=1, description="CPT/HCPCS procedure codes")
    clinical_notes: Optional[str] = Field(None, description="Encrypted clinical notes supporting medical necessity")
    procedure_type: ProcedureType = Field(..., description="Type of imaging procedure")
    urgency_level: UrgencyLevel = Field(default=UrgencyLevel.ROUTINE, description="Request urgency level")
    status: RequestStatus = Field(default=RequestStatus.SUBMITTED, description="Current request status")
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Request submission timestamp")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Last update timestamp")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion time")
    current_stage: str = Field(default="submitted", description="Current processing stage")
    progress_percentage: int = Field(default=0, description="Processing progress percentage")
    next_actions: Optional[List[str]] = Field(None, description="Next actions available for this request")
    
    @field_validator('request_id')
    @classmethod
    def validate_request_id(cls, v):
        """Validate request ID format."""
        if not v or len(v.strip()) == 0:
            raise ValueError("Request ID cannot be empty")
        
        # Request IDs should follow a specific format for tracking
        if not v.startswith('req_'):
            raise ValueError("Request ID must start with 'req_'")
        
        return v.strip()
    
    @field_validator('provider_id')
    @classmethod
    def validate_provider_id(cls, v):
        """Validate provider ID format."""
        if not v or len(v.strip()) == 0:
            raise ValueError("Provider ID cannot be empty")
        
        return v.strip()
    
    @field_validator('diagnosis_codes')
    @classmethod
    def validate_diagnosis_codes(cls, v):
        """Validate diagnosis codes list."""
        if not v or len(v) == 0:
            raise ValueError("At least one diagnosis code is required")
        
        if len(v) > 10:
            raise ValueError("Maximum 10 diagnosis codes allowed")
        
        return v
    
    @field_validator('procedure_codes')
    @classmethod
    def validate_procedure_codes(cls, v):
        """Validate procedure codes list."""
        if not v or len(v) == 0:
            raise ValueError("At least one procedure code is required")
        
        if len(v) > 5:
            raise ValueError("Maximum 5 procedure codes allowed")
        
        return v
    
    @field_validator('clinical_notes')
    @classmethod
    def validate_clinical_notes(cls, v):
        """Validate clinical notes."""
        if v is not None and len(v.strip()) == 0:
            return None
        
        if v and len(v) > 10000:
            raise ValueError("Clinical notes cannot exceed 10,000 characters")
        
        return v.strip() if v else None
    
    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "request_id": "req_2024_001234",
                "provider_id": "prov_12345",
                "patient_demographics": {
                    "patient_id": "enc_pat_1a2b3c4d5e6f7g8h",
                    "age": 45,
                    "gender": "female",
                    "insurance_id": "enc_ins_9i8h7g6f5e4d3c2b",
                    "member_id": "enc_mem_1z2y3x4w5v6u7t8s"
                },
                "diagnosis_codes": [
                    {"code": "M25.511", "description": "Pain in right shoulder"}
                ],
                "procedure_codes": [
                    {"code": "73221", "description": "MRI upper extremity without contrast"}
                ],
                "clinical_notes": "Patient reports persistent shoulder pain for 6 weeks...",
                "procedure_type": "mri",
                "urgency_level": "routine",
                "status": "submitted"
            }
        }
    )


class AuthorizationDecision(BaseModel):
    """
    Authorization decision model.
    
    Contains the decision outcome and reasoning for an authorization request.
    """
    decision_id: str = Field(..., description="Unique decision identifier")
    request_id: str = Field(..., description="Associated request identifier")
    status: DecisionStatus = Field(..., description="Decision outcome")
    reasoning: List[str] = Field(..., description="Detailed reasoning for the decision")
    policy_references: List[str] = Field(default_factory=list, description="Referenced policies and guidelines")
    authorization_number: Optional[str] = Field(None, description="Authorization number for approved requests")
    valid_until: Optional[datetime] = Field(None, description="Authorization expiration date")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Decision confidence score (0.0-1.0)")
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Decision timestamp")
    additional_info_needed: Optional[List[str]] = Field(None, description="Required additional information")
    alternative_procedures: Optional[List[str]] = Field(None, description="Suggested alternative procedures")
    
    @field_validator('decision_id')
    @classmethod
    def validate_decision_id(cls, v):
        """Validate decision ID format."""
        if not v or len(v.strip()) == 0:
            raise ValueError("Decision ID cannot be empty")
        
        if not v.startswith('dec_'):
            raise ValueError("Decision ID must start with 'dec_'")
        
        return v.strip()
    
    @field_validator('request_id')
    @classmethod
    def validate_request_id(cls, v):
        """Validate request ID format."""
        if not v or len(v.strip()) == 0:
            raise ValueError("Request ID cannot be empty")
        
        if not v.startswith('req_'):
            raise ValueError("Request ID must start with 'req_'")
        
        return v.strip()
    
    @field_validator('reasoning')
    @classmethod
    def validate_reasoning(cls, v):
        """Validate reasoning list."""
        if not v or len(v) == 0:
            raise ValueError("At least one reasoning statement is required")
        
        # Filter out empty strings
        filtered_reasoning = [reason.strip() for reason in v if reason.strip()]
        if not filtered_reasoning:
            raise ValueError("Reasoning cannot contain only empty strings")
        
        return filtered_reasoning
    
    @field_validator('confidence_score')
    @classmethod
    def validate_confidence_score(cls, v):
        """Validate confidence score range."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("Confidence score must be between 0.0 and 1.0")
        
        return v
    
    @model_validator(mode='after')
    def validate_authorization_fields(self):
        """Validate authorization-specific fields for approved requests."""
        if self.status == DecisionStatus.APPROVED:
            if not self.authorization_number:
                raise ValueError("Authorization number is required for approved requests")
            
            if not self.authorization_number.startswith('auth_'):
                raise ValueError("Authorization number must start with 'auth_'")
            
            if not self.valid_until:
                raise ValueError("Valid until date is required for approved requests")
            
            if self.valid_until <= datetime.now(timezone.utc):
                raise ValueError("Authorization expiration date must be in the future")
        
        return self
    
    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "decision_id": "dec_2024_001234",
                "request_id": "req_2024_001234",
                "status": "approved",
                "reasoning": [
                    "Patient meets medical necessity criteria for shoulder MRI",
                    "Diagnosis code M25.511 is covered under current policy",
                    "Conservative treatment documented for required duration"
                ],
                "policy_references": [
                    "CMS NCD 220.2",
                    "Payer Policy IMG-001"
                ],
                "authorization_number": "auth_2024_567890",
                "valid_until": "2024-02-24T23:59:59",
                "confidence_score": 0.95,
                "decided_at": "2024-01-24T10:30:00"
            }
        }
    )
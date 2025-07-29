"""
Data models for Prior Authorization Agent API Client.

This module provides Pydantic models for API requests and responses
with validation and serialization support.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict


class RequestStatus(str, Enum):
    """Authorization request status enumeration."""
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    DENIED = "denied"
    MORE_INFO_NEEDED = "more_info_needed"
    CANCELLED = "cancelled"


class DecisionStatus(str, Enum):
    """Authorization decision status enumeration."""
    APPROVED = "approved"
    DENIED = "denied"
    MORE_INFO_NEEDED = "more_info_needed"


class UrgencyLevel(str, Enum):
    """Request urgency level enumeration."""
    ROUTINE = "routine"
    URGENT = "urgent"
    EMERGENT = "emergent"


class ProcedureType(str, Enum):
    """Medical procedure type enumeration."""
    MRI = "mri"
    CT_SCAN = "ct_scan"
    X_RAY = "x_ray"
    ULTRASOUND = "ultrasound"


class Gender(str, Enum):
    """Patient gender enumeration."""
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNKNOWN = "unknown"


class PatientDemographics(BaseModel):
    """Patient demographic information."""
    patient_id: str = Field(..., description="Encrypted/hashed patient identifier")
    age: int = Field(..., ge=0, le=150, description="Patient age in years")
    gender: Gender = Field(..., description="Patient gender")
    insurance_id: str = Field(..., description="Encrypted insurance identifier")
    member_id: str = Field(..., description="Encrypted member identifier")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "patient_id": "encrypted_patient_id_hash",
                "age": 45,
                "gender": "female",
                "insurance_id": "encrypted_insurance_id",
                "member_id": "encrypted_member_id"
            }
        }
    )


class MedicalCode(BaseModel):
    """Medical code information."""
    code: str = Field(..., description="Medical code (ICD-10, CPT, HCPCS)")
    description: str = Field(..., description="Code description")
    code_type: str = Field(..., description="Code type (icd10, cpt, hcpcs)")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "70551",
                "description": "MRI brain without contrast",
                "code_type": "cpt"
            }
        }
    )


class AuthorizationRequest(BaseModel):
    """Authorization request data model."""
    provider_id: str = Field(..., description="Healthcare provider identifier")
    patient_demographics: PatientDemographics = Field(..., description="Patient information")
    diagnosis_codes: List[MedicalCode] = Field(..., description="ICD-10 diagnosis codes")
    procedure_codes: List[MedicalCode] = Field(..., description="CPT/HCPCS procedure codes")
    clinical_notes: str = Field(..., max_length=10000, description="Clinical notes and justification")
    urgency_level: UrgencyLevel = Field(default=UrgencyLevel.ROUTINE, description="Request urgency")
    procedure_type: ProcedureType = Field(..., description="Type of medical procedure")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "provider_id": "prov_12345",
                "patient_demographics": {
                    "patient_id": "encrypted_patient_id_hash",
                    "age": 45,
                    "gender": "female",
                    "insurance_id": "encrypted_insurance_id",
                    "member_id": "encrypted_member_id"
                },
                "diagnosis_codes": [
                    {
                        "code": "G93.1",
                        "description": "Anoxic brain damage, not elsewhere classified",
                        "code_type": "icd10"
                    }
                ],
                "procedure_codes": [
                    {
                        "code": "70551",
                        "description": "MRI brain without contrast",
                        "code_type": "cpt"
                    }
                ],
                "clinical_notes": "Patient presents with persistent headaches and memory issues following recent head trauma.",
                "urgency_level": "routine",
                "procedure_type": "mri"
            }
        }
    )


class AuthorizationDecision(BaseModel):
    """Authorization decision data model."""
    decision_id: str = Field(..., description="Unique decision identifier")
    request_id: str = Field(..., description="Associated request identifier")
    status: DecisionStatus = Field(..., description="Decision status")
    reasoning: List[str] = Field(..., description="Decision reasoning")
    policy_references: List[str] = Field(..., description="Referenced policies")
    authorization_number: Optional[str] = Field(None, description="Authorization number if approved")
    valid_until: Optional[datetime] = Field(None, description="Authorization expiration date")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Decision confidence score")
    decided_at: datetime = Field(..., description="Decision timestamp")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "decision_id": "dec_2024_001234",
                "request_id": "req_2024_001234",
                "status": "approved",
                "reasoning": [
                    "Medical necessity criteria met per CMS NCD 220.2",
                    "ICD-10 code G93.1 supports requested MRI procedure"
                ],
                "policy_references": ["CMS_NCD_220.2", "PAYER_POLICY_MRI_001"],
                "authorization_number": "AUTH2024001234",
                "valid_until": "2024-02-24T10:30:00Z",
                "confidence_score": 0.95,
                "decided_at": "2024-01-24T10:30:00Z"
            }
        }
    )


class RequestSubmissionResponse(BaseModel):
    """Response model for request submission."""
    request_id: str = Field(..., description="Unique request tracking ID")
    status: str = Field(..., description="Initial request status")
    message: str = Field(..., description="Submission confirmation message")
    timestamp: datetime = Field(..., description="Submission timestamp")
    validation_warnings: Optional[List[str]] = Field(None, description="Non-blocking validation warnings")


class RequestStatusInfo(BaseModel):
    """Request status information."""
    request_id: str = Field(..., description="Request identifier")
    status: RequestStatus = Field(..., description="Current status")
    submitted_at: datetime = Field(..., description="Submission timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion time")
    current_stage: str = Field(..., description="Current processing stage")
    progress_percentage: int = Field(..., ge=0, le=100, description="Processing progress")
    next_actions: Optional[List[str]] = Field(None, description="Required next actions")


class DashboardSummary(BaseModel):
    """Provider dashboard summary."""
    provider_id: str = Field(..., description="Provider identifier")
    total_requests: int = Field(..., description="Total number of requests")
    pending_requests: int = Field(..., description="Number of pending requests")
    approved_requests: int = Field(..., description="Number of approved requests")
    denied_requests: int = Field(..., description="Number of denied requests")
    requests_needing_info: int = Field(..., description="Requests needing additional information")
    average_processing_time_hours: float = Field(..., description="Average processing time in hours")
    approval_rate_percentage: float = Field(..., description="Approval rate percentage")
    recent_activity_count: int = Field(..., description="Recent activity count (24 hours)")
    urgent_requests_count: int = Field(..., description="Number of urgent requests")


class LoginCredentials(BaseModel):
    """Login credentials model."""
    username: str = Field(..., description="Username or email")
    password: str = Field(..., description="Password")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "provider1",
                "password": "provider123"
            }
        }
    )


class TokenResponse(BaseModel):
    """Authentication token response."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(..., description="Token type (bearer)")
    expires_in: int = Field(..., description="Token expiration in seconds")
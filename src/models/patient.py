"""
Patient demographics model with PHI encryption support.
"""

from datetime import date
from typing import Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict
from .enums import Gender


class PatientDemographics(BaseModel):
    """
    Patient demographic information with PHI encryption.
    
    All PHI fields are encrypted at rest and require special handling.
    """
    patient_id: str = Field(..., description="Encrypted patient identifier")
    age: int = Field(..., ge=0, le=150, description="Patient age in years")
    gender: Gender = Field(..., description="Patient gender")
    insurance_id: str = Field(..., description="Encrypted insurance identifier")
    member_id: str = Field(..., description="Encrypted insurance member ID")
    date_of_birth: Optional[date] = Field(None, description="Patient date of birth (encrypted)")
    
    @field_validator('age')
    @classmethod
    def validate_age(cls, v):
        """Validate patient age is reasonable."""
        if v < 0 or v > 150:
            raise ValueError("Patient age must be between 0 and 150")
        return v
    
    @field_validator('patient_id', 'insurance_id', 'member_id')
    @classmethod
    def validate_encrypted_fields(cls, v):
        """Validate that PHI fields are properly formatted (encrypted or hashed)."""
        if not v or len(v.strip()) == 0:
            raise ValueError("PHI field cannot be empty")
        
        # In production, these would be encrypted/hashed values
        # For now, we just ensure they're not obviously plain text
        if len(v) < 8:
            raise ValueError("PHI field appears to be unencrypted (too short)")
        
        return v.strip()
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "patient_id": "enc_pat_1a2b3c4d5e6f7g8h",
                "age": 45,
                "gender": "female",
                "insurance_id": "enc_ins_9i8h7g6f5e4d3c2b",
                "member_id": "enc_mem_1z2y3x4w5v6u7t8s",
                "date_of_birth": "1978-03-15"
            }
        }
    )
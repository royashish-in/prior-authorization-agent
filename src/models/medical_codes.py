"""
Medical code validation models for ICD-10, CPT, and HCPCS codes.
"""

import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class ICD10Code(BaseModel):
    """
    ICD-10 diagnosis code with validation.
    
    ICD-10 codes follow the format: Letter + 2 digits + optional decimal + up to 4 more characters
    Examples: A00, B15.9, S72.001A
    """
    code: str = Field(..., description="ICD-10 diagnosis code")
    description: Optional[str] = Field(None, description="Human-readable description of the diagnosis")
    
    @field_validator('code')
    @classmethod
    def validate_icd10_format(cls, v):
        """Validate ICD-10 code format."""
        if not v:
            raise ValueError("ICD-10 code cannot be empty")
        
        # Basic ICD-10 format validation: Letter + 2 digits + optional decimal + up to 4 more chars
        pattern = r'^[A-Z][0-9]{2}(\.[A-Z0-9]{1,4})?$'
        if not re.match(pattern, v.upper()):
            raise ValueError(f"Invalid ICD-10 code format: {v}. Expected format: A00 or A00.123")
        
        return v.upper()
    
    def __str__(self) -> str:
        return self.code


class CPTCode(BaseModel):
    """
    CPT (Current Procedural Terminology) code with validation.
    
    CPT codes are 5-digit numeric codes.
    Examples: 70551, 72148, 73721
    """
    code: str = Field(..., description="CPT procedure code")
    description: Optional[str] = Field(None, description="Human-readable description of the procedure")
    modifier: Optional[str] = Field(None, description="CPT modifier (e.g., 26, TC, 59)")
    
    @field_validator('code')
    @classmethod
    def validate_cpt_format(cls, v):
        """Validate CPT code format."""
        if not v:
            raise ValueError("CPT code cannot be empty")
        
        # CPT codes are 5-digit numeric
        if not re.match(r'^\d{5}$', v):
            raise ValueError(f"Invalid CPT code format: {v}. Expected 5-digit numeric code")
        
        # Basic range validation for imaging CPT codes (70000-79999)
        code_int = int(v)
        if not (70000 <= code_int <= 79999):
            raise ValueError(f"CPT code {v} is outside imaging range (70000-79999)")
        
        return v
    
    @field_validator('modifier')
    @classmethod
    def validate_modifier(cls, v):
        """Validate CPT modifier format."""
        if v is None:
            return v
        
        # Common modifiers are 2-character alphanumeric
        if not re.match(r'^[A-Z0-9]{2}$', v.upper()):
            raise ValueError(f"Invalid CPT modifier format: {v}")
        
        return v.upper()
    
    def __str__(self) -> str:
        if self.modifier:
            return f"{self.code}-{self.modifier}"
        return self.code


class HCPCSCode(BaseModel):
    """
    HCPCS (Healthcare Common Procedure Coding System) code with validation.
    
    HCPCS codes start with a letter followed by 4 digits.
    Examples: A0425, G0202, J1100
    """
    code: str = Field(..., description="HCPCS procedure code")
    description: Optional[str] = Field(None, description="Human-readable description of the procedure")
    
    @field_validator('code')
    @classmethod
    def validate_hcpcs_format(cls, v):
        """Validate HCPCS code format."""
        if not v:
            raise ValueError("HCPCS code cannot be empty")
        
        # HCPCS codes: Letter + 4 digits
        if not re.match(r'^[A-Z]\d{4}$', v.upper()):
            raise ValueError(f"Invalid HCPCS code format: {v}. Expected format: A1234")
        
        return v.upper()
    
    def __str__(self) -> str:
        return self.code
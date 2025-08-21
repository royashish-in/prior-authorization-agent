"""
SQLAlchemy models for medical codes (ICD-10 and CPT/HCPCS).

These models represent the database schema for medical code validation,
search, and management with support for versioning and relationships.
"""

import json
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from sqlalchemy import (
    Column, String, Integer, DateTime, Text, Boolean, 
    Numeric, Date, ForeignKey, Index, JSON, DECIMAL
)
from sqlalchemy.orm import declarative_base, relationship, validates
from sqlalchemy.ext.hybrid import hybrid_property

from src.database.base import Base
from pydantic import BaseModel, Field, ConfigDict


class ICD10CodeDB(Base):
    """
    Database model for ICD-10 diagnosis codes.
    
    Stores comprehensive ICD-10 code information including descriptions,
    categories, validity periods, and clinical metadata.
    """
    __tablename__ = "icd10_codes"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Code identification
    code = Column(String(10), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=False)
    short_description = Column(String(255), nullable=True)
    
    # Classification
    category = Column(String(50), nullable=True, index=True)
    subcategory = Column(String(100), nullable=True, index=True)
    chapter = Column(String(100), nullable=True, index=True)
    
    # Code properties
    billable = Column(Boolean, nullable=False, default=True, index=True)
    gender_specific = Column(String(1), nullable=True)  # 'M', 'F', or NULL
    age_restrictions = Column(JSON, nullable=True)  # {"min_age": 18, "max_age": 65}
    
    # Validity and versioning
    valid_from = Column(Date, nullable=False, index=True)
    valid_to = Column(Date, nullable=True, index=True)
    version = Column(String(20), nullable=False, default="2024")
    
    # Search optimization
    search_terms = Column(Text, nullable=True)  # Additional searchable terms
    synonyms = Column(JSON, nullable=True)  # Alternative names/terms
    
    # Clinical context
    severity_level = Column(String(20), nullable=True)  # mild, moderate, severe
    chronic_condition = Column(Boolean, nullable=False, default=False)
    
    # Audit fields
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(50), nullable=False, default="system")
    updated_by = Column(String(50), nullable=False, default="system")
    
    # Relationships
    code_relationships_primary = relationship(
        "CodeRelationshipDB", 
        foreign_keys="CodeRelationshipDB.primary_code_id",
        back_populates="primary_code_obj",
        cascade="all, delete-orphan"
    )
    code_relationships_related = relationship(
        "CodeRelationshipDB", 
        foreign_keys="CodeRelationshipDB.related_code_id",
        back_populates="related_code_obj"
    )
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_icd10_code_billable', 'code', 'billable'),
        Index('idx_icd10_category_valid', 'category', 'valid_from', 'valid_to'),
        Index('idx_icd10_chapter_category', 'chapter', 'category'),
        Index('idx_icd10_gender_age', 'gender_specific', 'billable'),
        Index('idx_icd10_version_valid', 'version', 'valid_from'),
        Index('idx_icd10_chronic_severity', 'chronic_condition', 'severity_level'),
    )
    
    @validates('code')
    def validate_code(self, key, code):
        """Validate ICD-10 code format."""
        if not code or len(code) < 3 or len(code) > 7:
            raise ValueError(f"Invalid ICD-10 code format: {code}")
        # Basic format validation (letter followed by digits and optional decimal)
        if not (code[0].isalpha() and code[1:3].isdigit()):
            raise ValueError(f"Invalid ICD-10 code format: {code}")
        return code.upper()
    
    @validates('gender_specific')
    def validate_gender_specific(self, key, gender):
        """Validate gender-specific values."""
        if gender is not None and gender not in ['M', 'F']:
            raise ValueError(f"Gender specific must be 'M', 'F', or None: {gender}")
        return gender
    
    @validates('severity_level')
    def validate_severity_level(self, key, severity):
        """Validate severity level values."""
        if severity is not None and severity not in ['mild', 'moderate', 'severe']:
            raise ValueError(f"Invalid severity level: {severity}")
        return severity
    
    @hybrid_property
    def is_currently_valid(self):
        """Check if the code is currently valid."""
        today = date.today()
        if self.valid_from > today:
            return False
        if self.valid_to and self.valid_to < today:
            return False
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            'id': self.id,
            'code': self.code,
            'description': self.description,
            'short_description': self.short_description,
            'category': self.category,
            'subcategory': self.subcategory,
            'chapter': self.chapter,
            'billable': self.billable,
            'gender_specific': self.gender_specific,
            'age_restrictions': self.age_restrictions,
            'valid_from': self.valid_from.isoformat() if self.valid_from else None,
            'valid_to': self.valid_to.isoformat() if self.valid_to else None,
            'version': self.version,
            'severity_level': self.severity_level,
            'chronic_condition': self.chronic_condition,
            'synonyms': self.synonyms,
            'is_currently_valid': self.is_currently_valid
        }
    
    def __repr__(self):
        return f"<ICD10Code(code={self.code}, description={self.description[:50]}...)>"


class CPTCodeDB(Base):
    """
    Database model for CPT/HCPCS procedure codes.
    
    Stores comprehensive CPT code information including descriptions,
    categories, billing information, and clinical metadata.
    """
    __tablename__ = "cpt_codes"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Code identification
    code = Column(String(10), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=False)
    short_description = Column(String(255), nullable=True)
    
    # Classification
    category = Column(String(50), nullable=True, index=True)
    subcategory = Column(String(100), nullable=True, index=True)
    section = Column(String(100), nullable=True, index=True)
    
    # Code type (CPT, HCPCS Level I, HCPCS Level II)
    code_type = Column(String(20), nullable=False, default="CPT", index=True)
    
    # Billing and procedure properties
    modifier_allowed = Column(Boolean, nullable=False, default=True)
    bilateral_surgery = Column(Boolean, nullable=False, default=False)
    assistant_surgery = Column(Boolean, nullable=False, default=False)
    multiple_procedure = Column(Boolean, nullable=False, default=True)
    
    # Relative Value Units (RVU) for billing
    work_rvu = Column(DECIMAL(6, 2), nullable=True)
    practice_expense_rvu = Column(DECIMAL(6, 2), nullable=True)
    malpractice_rvu = Column(DECIMAL(6, 2), nullable=True)
    total_rvu = Column(DECIMAL(6, 2), nullable=True)
    
    # Validity and versioning
    valid_from = Column(Date, nullable=False, index=True)
    valid_to = Column(Date, nullable=True, index=True)
    version = Column(String(20), nullable=False, default="2024")
    
    # Search optimization
    search_terms = Column(Text, nullable=True)
    synonyms = Column(JSON, nullable=True)
    
    # Clinical context
    procedure_type = Column(String(50), nullable=True, index=True)  # diagnostic, therapeutic, surgical
    body_system = Column(String(50), nullable=True, index=True)
    imaging_required = Column(Boolean, nullable=False, default=False)
    anesthesia_required = Column(Boolean, nullable=False, default=False)
    
    # Authorization context
    prior_auth_required = Column(Boolean, nullable=False, default=False, index=True)
    medical_necessity_level = Column(String(20), nullable=True)  # low, medium, high
    
    # Audit fields
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(50), nullable=False, default="system")
    updated_by = Column(String(50), nullable=False, default="system")
    
    # Relationships
    code_relationships_primary = relationship(
        "CodeRelationshipDB", 
        foreign_keys="CodeRelationshipDB.primary_code_id",
        back_populates="primary_code_obj",
        cascade="all, delete-orphan"
    )
    code_relationships_related = relationship(
        "CodeRelationshipDB", 
        foreign_keys="CodeRelationshipDB.related_code_id",
        back_populates="related_code_obj"
    )
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_cpt_code_type', 'code', 'code_type'),
        Index('idx_cpt_category_valid', 'category', 'valid_from', 'valid_to'),
        Index('idx_cpt_procedure_type', 'procedure_type', 'body_system'),
        Index('idx_cpt_prior_auth', 'prior_auth_required', 'medical_necessity_level'),
        Index('idx_cpt_billing_props', 'bilateral_surgery', 'assistant_surgery'),
        Index('idx_cpt_version_valid', 'version', 'valid_from'),
        Index('idx_cpt_rvu_total', 'total_rvu'),
    )
    
    @validates('code')
    def validate_code(self, key, code):
        """Validate CPT/HCPCS code format."""
        if not code or len(code) < 4 or len(code) > 5:
            raise ValueError(f"Invalid CPT/HCPCS code format: {code}")
        
        # CPT codes are 5 digits
        if len(code) == 5 and code.isdigit():
            return code
        
        # HCPCS Level II codes start with a letter followed by 4 digits
        if len(code) == 5 and code[0].isalpha() and code[1:].isdigit():
            return code.upper()
        
        raise ValueError(f"Invalid CPT/HCPCS code format: {code}")
    
    @validates('code_type')
    def validate_code_type(self, key, code_type):
        """Validate code type values."""
        valid_types = ['CPT', 'HCPCS_I', 'HCPCS_II']
        if code_type not in valid_types:
            raise ValueError(f"Invalid code type: {code_type}. Must be one of: {valid_types}")
        return code_type
    
    @validates('procedure_type')
    def validate_procedure_type(self, key, proc_type):
        """Validate procedure type values."""
        if proc_type is not None:
            valid_types = ['diagnostic', 'therapeutic', 'surgical', 'preventive', 'evaluation']
            if proc_type not in valid_types:
                raise ValueError(f"Invalid procedure type: {proc_type}")
        return proc_type
    
    @validates('medical_necessity_level')
    def validate_medical_necessity_level(self, key, level):
        """Validate medical necessity level values."""
        if level is not None and level not in ['low', 'medium', 'high']:
            raise ValueError(f"Invalid medical necessity level: {level}")
        return level
    
    @hybrid_property
    def is_currently_valid(self):
        """Check if the code is currently valid."""
        today = date.today()
        if self.valid_from > today:
            return False
        if self.valid_to and self.valid_to < today:
            return False
        return True
    
    def calculate_total_rvu(self):
        """Calculate total RVU from components."""
        if all([self.work_rvu, self.practice_expense_rvu, self.malpractice_rvu]):
            self.total_rvu = self.work_rvu + self.practice_expense_rvu + self.malpractice_rvu
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            'id': self.id,
            'code': self.code,
            'description': self.description,
            'short_description': self.short_description,
            'category': self.category,
            'subcategory': self.subcategory,
            'section': self.section,
            'code_type': self.code_type,
            'modifier_allowed': self.modifier_allowed,
            'bilateral_surgery': self.bilateral_surgery,
            'assistant_surgery': self.assistant_surgery,
            'multiple_procedure': self.multiple_procedure,
            'work_rvu': float(self.work_rvu) if self.work_rvu else None,
            'practice_expense_rvu': float(self.practice_expense_rvu) if self.practice_expense_rvu else None,
            'malpractice_rvu': float(self.malpractice_rvu) if self.malpractice_rvu else None,
            'total_rvu': float(self.total_rvu) if self.total_rvu else None,
            'valid_from': self.valid_from.isoformat() if self.valid_from else None,
            'valid_to': self.valid_to.isoformat() if self.valid_to else None,
            'version': self.version,
            'procedure_type': self.procedure_type,
            'body_system': self.body_system,
            'imaging_required': self.imaging_required,
            'anesthesia_required': self.anesthesia_required,
            'prior_auth_required': self.prior_auth_required,
            'medical_necessity_level': self.medical_necessity_level,
            'synonyms': self.synonyms,
            'is_currently_valid': self.is_currently_valid
        }
    
    def __repr__(self):
        return f"<CPTCode(code={self.code}, description={self.description[:50]}...)>"


class CodeRelationshipDB(Base):
    """
    Database model for relationships between medical codes.
    
    Stores relationships like contraindications, alternatives, and
    recommended combinations between ICD-10 and CPT codes.
    """
    __tablename__ = "code_relationships"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Related codes (can be ICD-10 to CPT, CPT to CPT, etc.)
    primary_code_id = Column(Integer, nullable=False, index=True)
    primary_code_type = Column(String(10), nullable=False)  # 'ICD10' or 'CPT'
    related_code_id = Column(Integer, nullable=False, index=True)
    related_code_type = Column(String(10), nullable=False)  # 'ICD10' or 'CPT'
    
    # Relationship details
    relationship_type = Column(String(50), nullable=False, index=True)
    # Types: 'contraindicated', 'recommended', 'alternative', 'prerequisite', 'followup'
    
    strength = Column(DECIMAL(3, 2), nullable=False, default=1.0)  # 0.0 to 1.0
    confidence = Column(DECIMAL(3, 2), nullable=False, default=1.0)  # 0.0 to 1.0
    
    # Clinical context
    clinical_rationale = Column(Text, nullable=True)
    evidence_level = Column(String(20), nullable=True)  # 'high', 'medium', 'low'
    guideline_reference = Column(String(255), nullable=True)
    
    # Validity
    valid_from = Column(Date, nullable=False, default=date.today)
    valid_to = Column(Date, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    
    # Audit fields
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(50), nullable=False, default="system")
    
    # Relationships (polymorphic - can reference either ICD10 or CPT codes)
    primary_code_obj = relationship(
        "ICD10CodeDB",
        foreign_keys=[primary_code_id],
        primaryjoin="and_(CodeRelationshipDB.primary_code_id == ICD10CodeDB.id, "
                   "CodeRelationshipDB.primary_code_type == 'ICD10')",
        back_populates="code_relationships_primary",
        viewonly=True
    )
    
    related_code_obj = relationship(
        "ICD10CodeDB",
        foreign_keys=[related_code_id],
        primaryjoin="and_(CodeRelationshipDB.related_code_id == ICD10CodeDB.id, "
                   "CodeRelationshipDB.related_code_type == 'ICD10')",
        back_populates="code_relationships_related",
        viewonly=True
    )
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_relationship_primary', 'primary_code_id', 'primary_code_type'),
        Index('idx_relationship_related', 'related_code_id', 'related_code_type'),
        Index('idx_relationship_type_active', 'relationship_type', 'is_active'),
        Index('idx_relationship_strength', 'strength', 'confidence'),
        Index('idx_relationship_valid', 'valid_from', 'valid_to', 'is_active'),
    )
    
    @validates('relationship_type')
    def validate_relationship_type(self, key, rel_type):
        """Validate relationship type values."""
        valid_types = [
            'contraindicated', 'recommended', 'alternative', 
            'prerequisite', 'followup', 'related', 'excludes'
        ]
        if rel_type not in valid_types:
            raise ValueError(f"Invalid relationship type: {rel_type}")
        return rel_type
    
    @validates('primary_code_type', 'related_code_type')
    def validate_code_type(self, key, code_type):
        """Validate code type values."""
        if code_type not in ['ICD10', 'CPT']:
            raise ValueError(f"Invalid code type: {code_type}")
        return code_type
    
    @validates('strength', 'confidence')
    def validate_score(self, key, score):
        """Validate score range."""
        if not 0.0 <= float(score) <= 1.0:
            raise ValueError(f"{key} must be between 0.0 and 1.0, got: {score}")
        return score
    
    @validates('evidence_level')
    def validate_evidence_level(self, key, level):
        """Validate evidence level values."""
        if level is not None and level not in ['high', 'medium', 'low']:
            raise ValueError(f"Invalid evidence level: {level}")
        return level
    
    @hybrid_property
    def is_currently_valid(self):
        """Check if the relationship is currently valid."""
        if not self.is_active:
            return False
        today = date.today()
        if self.valid_from > today:
            return False
        if self.valid_to and self.valid_to < today:
            return False
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            'id': self.id,
            'primary_code_id': self.primary_code_id,
            'primary_code_type': self.primary_code_type,
            'related_code_id': self.related_code_id,
            'related_code_type': self.related_code_type,
            'relationship_type': self.relationship_type,
            'strength': float(self.strength),
            'confidence': float(self.confidence),
            'clinical_rationale': self.clinical_rationale,
            'evidence_level': self.evidence_level,
            'guideline_reference': self.guideline_reference,
            'valid_from': self.valid_from.isoformat() if self.valid_from else None,
            'valid_to': self.valid_to.isoformat() if self.valid_to else None,
            'is_active': self.is_active,
            'is_currently_valid': self.is_currently_valid
        }
    
    def __repr__(self):
        return f"<CodeRelationship(primary={self.primary_code_id}:{self.primary_code_type}, " \
               f"related={self.related_code_id}:{self.related_code_type}, type={self.relationship_type})>"


# Pydantic models for API requests/responses (separate from DB models)

class ICD10Code(BaseModel):
    """Pydantic model for ICD-10 codes in API requests."""
    code: str = Field(..., description="ICD-10 diagnosis code")
    description: Optional[str] = Field(None, description="Code description")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "M25.511",
                "description": "Pain in right shoulder"
            }
        }
    )


class CPTCode(BaseModel):
    """Pydantic model for CPT codes in API requests."""
    code: str = Field(..., description="CPT procedure code")
    description: Optional[str] = Field(None, description="Code description")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "73221",
                "description": "MRI upper extremity without contrast"
            }
        }
    )


# HCPCS codes use the same structure as CPT codes
HCPCSCode = CPTCode
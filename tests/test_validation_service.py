"""
Tests for the validation service.

This module tests request validation, data validation, and business rule
validation for prior authorization requests.
"""

import pytest
from src.services.validation import ValidationResult
from datetime import datetime, date
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any, List

from src.services.validation import ValidationService, ValidationResult, ValidationError
from src.models.authorization import AuthorizationRequest
from src.models.medical_codes import ICD10Code, CPTCode
from src.models.patient import PatientDemographics
from src.models.enums import DecisionStatus, UrgencyLevel, ProcedureType, RequestStatus


class TestValidationService:
    """Test validation service functionality."""
    
    @pytest.fixture
    def validation_service(self):
        """Create validation service instance."""
        return ValidationService()
    
    @pytest.fixture
    def valid_request(self):
        """Create valid authorization request."""
        return AuthorizationRequest(
            patient_demographics=PatientDemographics(
                first_name="John",
                last_name="Doe",
                date_of_birth=datetime(1980, 1, 1),
                gender=Gender.MALE,
                member_id="TEST123456"
            ),
            diagnosis_codes=[
                ICD10Code(
                    code="G93.1",
                    description="Anoxic brain damage",
                    code_type="icd10"
                )
            ],
            procedure_codes=[
                ICD10Code(
                    code="70551",
                    description="MRI brain without contrast",
                    code_type="cpt"
                )
            ],
            clinical_notes="Patient presents with persistent headaches.",
            urgency_level=UrgencyLevel.ROUTINE,
            procedure_type=ProcedureType.MRI
        )
    
    @pytest.mark.asyncio

    
    async def test_validate_request_valid(self, validation_service, valid_request):
        """Test validation of valid request."""
        with patch.object(validation_service, '_validate_patient_demographics') as mock_patient, \
             patch.object(validation_service, '_validate_medical_codes') as mock_codes, \
             patch.object(validation_service, '_validate_clinical_notes') as mock_notes, \
             patch.object(validation_service, '_validate_business_rules') as mock_rules:
            
            mock_patient.return_value = []
            mock_codes.return_value = []
            mock_notes.return_value = []
            mock_rules.return_value = []
            
            result = await validation_service.validate_request(valid_request)
            
            assert isinstance(result, ValidationResult)
            assert result.is_valid is True
            assert len(result.errors) == 0
            assert len(result.warnings) == 0
    
    @pytest.mark.asyncio

    
    async def test_validate_request_invalid(self, validation_service, valid_request):
        """Test validation of invalid request."""
        with patch.object(validation_service, '_validate_patient_demographics') as mock_patient, \
             patch.object(validation_service, '_validate_medical_codes') as mock_codes, \
             patch.object(validation_service, '_validate_clinical_notes') as mock_notes, \
             patch.object(validation_service, '_validate_business_rules') as mock_rules:
            
            mock_patient.return_value = [ValidationError("patient", "Invalid member ID")]
            mock_codes.return_value = [ValidationError("diagnosis", "Invalid diagnosis code")]
            mock_notes.return_value = []
            mock_rules.return_value = []
            
            result = await validation_service.validate_request(valid_request)
            
            assert isinstance(result, ValidationResult)
            assert result.is_valid is False
            assert len(result.errors) == 2
            assert any(error.field == "patient" for error in result.errors)
            assert any(error.field == "diagnosis" for error in result.errors)
    
    def test_validate_patient_demographics_valid(self, validation_service):
        """Test patient demographics validation for valid data."""
        demographics = PatientDemographics(
            first_name="John",
            last_name="Doe",
            date_of_birth=datetime(1980, 1, 1),
            gender=Gender.MALE,
            member_id="TEST123456"
        )
        
        errors = validation_service._validate_patient_demographics(demographics)
        
        assert isinstance(errors, list)
        assert len(errors) == 0
    
    def test_validate_patient_demographics_missing_fields(self, validation_service):
        """Test patient demographics validation with missing fields."""
        demographics = PatientDemographics(
            first_name="",  # Empty first name
            last_name="Doe",
            date_of_birth=datetime(1980, 1, 1),
            gender=Gender.MALE,
            member_id=""  # Empty member ID
        )
        
        errors = validation_service._validate_patient_demographics(demographics)
        
        assert isinstance(errors, list)
        assert len(errors) >= 2
        assert any("first_name" in error.field for error in errors)
        assert any("member_id" in error.field for error in errors)
    
    def test_validate_patient_demographics_invalid_age(self, validation_service):
        """Test patient demographics validation with invalid age."""
        # Future birth date
        demographics = PatientDemographics(
            first_name="John",
            last_name="Doe",
            date_of_birth=datetime(2030, 1, 1),
            gender=Gender.MALE,
            member_id="TEST123456"
        )
        
        errors = validation_service._validate_patient_demographics(demographics)
        
        assert isinstance(errors, list)
        assert len(errors) >= 1
        assert any("date_of_birth" in error.field for error in errors)
    
    @pytest.mark.asyncio

    
    async def test_validate_medical_codes_valid(self, validation_service):
        """Test medical codes validation for valid codes."""
        diagnosis_codes = [
            ICD10Code(code="G93.1", description="Anoxic brain damage", code_type="icd10")
        ]
        procedure_codes = [
            ICD10Code(code="70551", description="MRI brain", code_type="cpt")
        ]
        
        with patch.object(validation_service, '_validate_code_format') as mock_format, \
             patch.object(validation_service, '_validate_code_existence') as mock_existence:
            
            mock_format.return_value = True
            mock_existence.return_value = True
            
            errors = await validation_service._validate_medical_codes(diagnosis_codes, procedure_codes)
            
            assert isinstance(errors, list)
            assert len(errors) == 0
    
    @pytest.mark.asyncio

    
    async def test_validate_medical_codes_invalid_format(self, validation_service):
        """Test medical codes validation with invalid format."""
        diagnosis_codes = [
            ICD10Code(code="INVALID", description="Invalid code", code_type="icd10")
        ]
        procedure_codes = [
            ICD10Code(code="12345", description="Invalid CPT", code_type="cpt")
        ]
        
        with patch.object(validation_service, '_validate_code_format') as mock_format, \
             patch.object(validation_service, '_validate_code_existence') as mock_existence:
            
            mock_format.return_value = False
            mock_existence.return_value = True
            
            errors = await validation_service._validate_medical_codes(diagnosis_codes, procedure_codes)
            
            assert isinstance(errors, list)
            assert len(errors) >= 2
    
    @pytest.mark.asyncio

    
    async def test_validate_medical_codes_nonexistent(self, validation_service):
        """Test medical codes validation with nonexistent codes."""
        diagnosis_codes = [
            ICD10Code(code="Z99.99", description="Nonexistent code", code_type="icd10")
        ]
        procedure_codes = [
            ICD10Code(code="99999", description="Nonexistent CPT", code_type="cpt")
        ]
        
        with patch.object(validation_service, '_validate_code_format') as mock_format, \
             patch.object(validation_service, '_validate_code_existence') as mock_existence:
            
            mock_format.return_value = True
            mock_existence.return_value = False
            
            errors = await validation_service._validate_medical_codes(diagnosis_codes, procedure_codes)
            
            assert isinstance(errors, list)
            assert len(errors) >= 2
    
    def test_validate_clinical_notes_valid(self, validation_service):
        """Test clinical notes validation for valid notes."""
        clinical_notes = "Patient presents with persistent headaches and memory issues following recent head trauma."
        
        errors = validation_service._validate_clinical_notes(clinical_notes)
        
        assert isinstance(errors, list)
        assert len(errors) == 0
    
    def test_validate_clinical_notes_too_short(self, validation_service):
        """Test clinical notes validation for too short notes."""
        clinical_notes = "Headache"
        
        errors = validation_service._validate_clinical_notes(clinical_notes)
        
        assert isinstance(errors, list)
        assert len(errors) >= 1
        assert any("clinical_notes" in error.field for error in errors)
    
    def test_validate_clinical_notes_empty(self, validation_service):
        """Test clinical notes validation for empty notes."""
        clinical_notes = ""
        
        errors = validation_service._validate_clinical_notes(clinical_notes)
        
        assert isinstance(errors, list)
        assert len(errors) >= 1
        assert any("clinical_notes" in error.field for error in errors)
    
    def test_validate_business_rules_valid(self, validation_service, valid_request):
        """Test business rules validation for valid request."""
        with patch.object(validation_service, '_check_age_restrictions') as mock_age, \
             patch.object(validation_service, '_check_procedure_frequency') as mock_frequency, \
             patch.object(validation_service, '_check_diagnosis_procedure_compatibility') as mock_compatibility:
            
            mock_age.return_value = []
            mock_frequency.return_value = []
            mock_compatibility.return_value = []
            
            errors = validation_service._validate_business_rules(valid_request)
            
            assert isinstance(errors, list)
            assert len(errors) == 0
    
    def test_validate_business_rules_age_restriction(self, validation_service, valid_request):
        """Test business rules validation with age restrictions."""
        with patch.object(validation_service, '_check_age_restrictions') as mock_age, \
             patch.object(validation_service, '_check_procedure_frequency') as mock_frequency, \
             patch.object(validation_service, '_check_diagnosis_procedure_compatibility') as mock_compatibility:
            
            mock_age.return_value = [ValidationError("age", "Patient too young for procedure")]
            mock_frequency.return_value = []
            mock_compatibility.return_value = []
            
            errors = validation_service._validate_business_rules(valid_request)
            
            assert isinstance(errors, list)
            assert len(errors) >= 1
            assert any("age" in error.field for error in errors)
    
    def test_validate_code_format_icd10_valid(self, validation_service):
        """Test ICD-10 code format validation for valid codes."""
        valid_codes = ["G93.1", "M79.3", "Z00.00"]
        
        for code in valid_codes:
            result = validation_service._validate_code_format(code, "icd10")
            assert result is True
    
    def test_validate_code_format_icd10_invalid(self, validation_service):
        """Test ICD-10 code format validation for invalid codes."""
        invalid_codes = ["INVALID", "123", "G93", "G93.1.2"]
        
        for code in invalid_codes:
            result = validation_service._validate_code_format(code, "icd10")
            assert result is False
    
    def test_validate_code_format_cpt_valid(self, validation_service):
        """Test CPT code format validation for valid codes."""
        valid_codes = ["70551", "99213", "12345"]
        
        for code in valid_codes:
            result = validation_service._validate_code_format(code, "cpt")
            assert result is True
    
    def test_validate_code_format_cpt_invalid(self, validation_service):
        """Test CPT code format validation for invalid codes."""
        invalid_codes = ["INVALID", "123", "123456", "7055A"]
        
        for code in invalid_codes:
            result = validation_service._validate_code_format(code, "cpt")
            assert result is False
    
    @pytest.mark.asyncio

    
    async def test_validate_code_existence_exists(self, validation_service):
        """Test code existence validation for existing codes."""
        with patch.object(validation_service, 'medical_code_service') as mock_service:
            mock_service.validate_code.return_value = {"valid": True, "description": "Valid code"}
            
            result = await validation_service._validate_code_existence("G93.1", "icd10")
            
            assert result is True
    
    @pytest.mark.asyncio

    
    async def test_validate_code_existence_not_exists(self, validation_service):
        """Test code existence validation for nonexistent codes."""
        with patch.object(validation_service, 'medical_code_service') as mock_service:
            mock_service.validate_code.return_value = {"valid": False, "description": None}
            
            result = await validation_service._validate_code_existence("INVALID", "icd10")
            
            assert result is False
    
    def test_check_age_restrictions_valid(self, validation_service):
        """Test age restrictions check for valid age."""
        patient = PatientDemographics(
            first_name="John",
            last_name="Doe",
            date_of_birth=datetime(1980, 1, 1),
            gender=Gender.MALE,
            member_id="TEST123456"
        )
        procedure_type = ProcedureType.MRI
        
        with patch.object(validation_service, '_get_age_restrictions') as mock_restrictions:
            mock_restrictions.return_value = {"min_age": 18, "max_age": 100}
            
            errors = validation_service._check_age_restrictions(patient, procedure_type)
            
            assert isinstance(errors, list)
            assert len(errors) == 0
    
    def test_check_age_restrictions_too_young(self, validation_service):
        """Test age restrictions check for too young patient."""
        patient = PatientDemographics(
            first_name="John",
            last_name="Doe",
            date_of_birth=datetime(2020, 1, 1),  # Too young
            gender=Gender.MALE,
            member_id="TEST123456"
        )
        procedure_type = ProcedureType.MRI
        
        with patch.object(validation_service, '_get_age_restrictions') as mock_restrictions:
            mock_restrictions.return_value = {"min_age": 18, "max_age": 100}
            
            errors = validation_service._check_age_restrictions(patient, procedure_type)
            
            assert isinstance(errors, list)
            assert len(errors) >= 1
    
    def test_check_procedure_frequency_valid(self, validation_service):
        """Test procedure frequency check for valid frequency."""
        patient = PatientDemographics(
            first_name="John",
            last_name="Doe",
            date_of_birth=datetime(1980, 1, 1),
            gender=Gender.MALE,
            member_id="TEST123456"
        )
        procedure_codes = [ICD10Code(code="70551", description="MRI brain", code_type="cpt")]
        
        with patch.object(validation_service, '_get_recent_procedures') as mock_recent:
            mock_recent.return_value = []  # No recent procedures
            
            errors = validation_service._check_procedure_frequency(patient, procedure_codes)
            
            assert isinstance(errors, list)
            assert len(errors) == 0
    
    def test_check_procedure_frequency_too_frequent(self, validation_service):
        """Test procedure frequency check for too frequent procedures."""
        patient = PatientDemographics(
            first_name="John",
            last_name="Doe",
            date_of_birth=datetime(1980, 1, 1),
            gender=Gender.MALE,
            member_id="TEST123456"
        )
        procedure_codes = [ICD10Code(code="70551", description="MRI brain", code_type="cpt")]
        
        with patch.object(validation_service, '_get_recent_procedures') as mock_recent:
            mock_recent.return_value = [
                {"code": "70551", "date": datetime.now().date(), "days_ago": 30}
            ]
            
            errors = validation_service._check_procedure_frequency(patient, procedure_codes)
            
            assert isinstance(errors, list)
            assert len(errors) >= 1
    
    def test_check_diagnosis_procedure_compatibility_compatible(self, validation_service):
        """Test diagnosis-procedure compatibility for compatible codes."""
        diagnosis_codes = [ICD10Code(code="G93.1", description="Anoxic brain damage", code_type="icd10")]
        procedure_codes = [ICD10Code(code="70551", description="MRI brain", code_type="cpt")]
        
        with patch.object(validation_service, '_get_compatible_procedures') as mock_compatible:
            mock_compatible.return_value = ["70551", "70552", "70553"]
            
            errors = validation_service._check_diagnosis_procedure_compatibility(diagnosis_codes, procedure_codes)
            
            assert isinstance(errors, list)
            assert len(errors) == 0
    
    def test_check_diagnosis_procedure_compatibility_incompatible(self, validation_service):
        """Test diagnosis-procedure compatibility for incompatible codes."""
        diagnosis_codes = [ICD10Code(code="Z00.00", description="General exam", code_type="icd10")]
        procedure_codes = [ICD10Code(code="70551", description="MRI brain", code_type="cpt")]
        
        with patch.object(validation_service, '_get_compatible_procedures') as mock_compatible:
            mock_compatible.return_value = ["99213", "99214"]  # Different procedures
            
            errors = validation_service._check_diagnosis_procedure_compatibility(diagnosis_codes, procedure_codes)
            
            assert isinstance(errors, list)
            assert len(errors) >= 1


class TestValidationResult:
    """Test ValidationResult model."""
    
    def test_validation_result_valid(self):
        """Test ValidationResult for valid case."""
        result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=[]
        )
        
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 0
    
    def test_validation_result_invalid(self):
        """Test ValidationResult for invalid case."""
        errors = [
            ValidationError("field1", "Error message 1"),
            ValidationError("field2", "Error message 2")
        ]
        warnings = [
            ValidationError("field3", "Warning message 1")
        ]
        
        result = ValidationResult(
            is_valid=False,
            errors=errors,
            warnings=warnings
        )
        
        assert result.is_valid is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 1
    
    def test_validation_result_serialization(self):
        """Test ValidationResult serialization."""
        errors = [ValidationError("field1", "Error message")]
        result = ValidationResult(
            is_valid=False,
            errors=errors,
            warnings=[]
        )
        
        serialized = result.dict()
        
        assert isinstance(serialized, dict)
        assert serialized["is_valid"] is False
        assert len(serialized["errors"]) == 1


class TestValidationError:
    """Test ValidationError model."""
    
    def test_validation_error_creation(self):
        """Test ValidationError creation."""
        error = ValidationError("field_name", "Error message")
        
        assert error.field == "field_name"
        assert error.message == "Error message"
    
    def test_validation_error_with_code(self):
        """Test ValidationError with error code."""
        error = ValidationError("field_name", "Error message", "ERR001")
        
        assert error.field == "field_name"
        assert error.message == "Error message"
        assert error.code == "ERR001"
    
    def test_validation_error_serialization(self):
        """Test ValidationError serialization."""
        error = ValidationError("field_name", "Error message", "ERR001")
        
        serialized = error.dict()
        
        assert isinstance(serialized, dict)
        assert serialized["field"] == "field_name"
        assert serialized["message"] == "Error message"
        assert serialized["code"] == "ERR001"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
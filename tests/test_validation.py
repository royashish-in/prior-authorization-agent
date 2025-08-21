"""
Unit tests for validation service.

Tests comprehensive validation logic including medical code validation,
business rules, and error handling.
"""

import pytest
from src.services.validation import ValidationResult
from datetime import datetime, timezone

from src.services.validation import ValidationService, ValidationError, ValidationResult
from src.models.authorization import AuthorizationRequest
from src.models.patient import PatientDemographics
from src.models.medical_codes import ICD10Code, CPTCode, HCPCSCode
from src.models.enums import DecisionStatus, UrgencyLevel, ProcedureType, RequestStatus


class TestValidationService:
    """Test cases for ValidationService."""
    
    @pytest.fixture
    def validation_service(self):
        """Create validation service instance."""
        return ValidationService()
    
    @pytest.fixture
    def valid_request(self):
        """Create a valid authorization request for testing."""
        return AuthorizationRequest(
            request_id="req_2024_TEST001",
            provider_id="prov_12345",
            patient_demographics=PatientDemographics(
                patient_id="enc_pat_1a2b3c4d5e6f7g8h",
                age=45,
                gender=Gender.FEMALE,
                insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
                member_id="enc_mem_1z2y3x4w5v6u7t8s"
            ),
            diagnosis_codes=[
                ICD10Code(code="M25.511", description="Pain in right shoulder")
            ],
            procedure_codes=[
                CPTCode(code="73221", description="MRI upper extremity without contrast")
            ],
            clinical_notes="Patient reports persistent shoulder pain for 6 weeks following sports injury.",
            procedure_type=ProcedureType.MRI,
            urgency_level=UrgencyLevel.ROUTINE,
            status=RequestStatus.SUBMITTED,
            submitted_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
    
    @pytest.mark.asyncio

    
    async def test_validate_valid_request_success(self, validation_service, valid_request):
        """
        Test validation of a completely valid authorization request.
        
        This test verifies that a well-formed authorization request with valid
        patient demographics, medical codes, and clinical information passes
        all validation checks without errors.
        
        Expected behavior:
        - ValidationResult should be returned
        - is_valid should be True
        - No validation errors should be present
        - Processing time should be recorded and positive
        """
        result = await validation_service.validate_request(valid_request)
        
        assert isinstance(result, ValidationResult), \
            f"Expected ValidationResult instance, got: {type(result)}"
        assert result.is_valid is True, \
            f"Valid request should pass validation, got is_valid={result.is_valid}, errors={result.errors}"
        assert len(result.errors) == 0, \
            f"Valid request should have no errors, got: {result.errors}"
        assert result.processing_time_ms > 0, \
            f"Processing time should be positive, got: {result.processing_time_ms}"
    
    @pytest.mark.asyncio

    
    async def test_validate_request_with_warnings(self, validation_service, valid_request):
        """Test validation that produces warnings but is still valid."""
        # Modify request to trigger warnings
        valid_request.patient_demographics.age = 85  # Elderly patient
        valid_request.urgency_level = UrgencyLevel.EMERGENT  # May trigger urgency warning
        valid_request.procedure_codes = [
            CPTCode(code="72148", description="MRI lumbar spine without contrast")
        ]
        
        result = await validation_service.validate_request(valid_request)
        
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) > 0
        assert any("over 80 years" in warning for warning in result.warnings)
        assert any("Emergent urgency level" in warning for warning in result.warnings)


class TestMedicalCodeValidation:
    """Test cases for medical code validation."""
    
    @pytest.fixture
    def validation_service(self):
        """Create validation service instance."""
        return ValidationService()
    
    @pytest.mark.asyncio

    
    async def test_validate_valid_icd10_codes(self, validation_service):
        """Test validation of valid ICD-10 codes."""
        valid_codes = [
            ICD10Code(code="M25.511", description="Pain in right shoulder"),
            ICD10Code(code="M25.512", description="Pain in left shoulder"),
            ICD10Code(code="S72.001A", description="Fracture of unspecified part of neck of right femur, initial encounter")
        ]
        
        for code in valid_codes:
            errors = await validation_service._validate_icd10_code(code, "test_field")
            assert len(errors) == 0
    
    @pytest.mark.asyncio

    
    async def test_validate_invalid_icd10_codes(self, validation_service):
        """
        Test validation of invalid ICD-10 codes that should fail business validation.
        
        This test verifies that ICD-10 codes with valid format but invalid content
        (non-existent codes or mismatched descriptions) are properly rejected by
        the business validation layer.
        
        Expected behavior:
        - Validation errors should be generated for invalid codes
        - Error messages should indicate the specific validation failure
        - Both non-existent codes and description mismatches should be caught
        """
        # Test codes that pass Pydantic validation but fail business validation
        invalid_codes = [
            ICD10Code(code="Z99.999", description="Non-existent code"),  # Valid format, invalid code
            ICD10Code(code="M25.511", description="Wrong description")  # Valid code, wrong description
        ]
        
        for i, code in enumerate(invalid_codes):
            errors = await validation_service._validate_icd10_code(code, "test_field")
            assert len(errors) > 0, \
                f"Invalid ICD-10 code {code.code} should generate validation errors"
            
            error_messages = [error.message for error in errors]
            has_recognition_error = any("not recognized" in msg for msg in error_messages)
            has_description_error = any("does not match" in msg for msg in error_messages)
            
            assert has_recognition_error or has_description_error, \
                f"Error messages should indicate recognition or description issues, got: {error_messages}"
    
    @pytest.mark.asyncio

    
    async def test_validate_valid_cpt_codes(self, validation_service):
        """Test validation of valid CPT codes."""
        valid_codes = [
            CPTCode(code="70551", description="MRI brain without contrast"),
            CPTCode(code="73221", description="MRI upper extremity without contrast"),
            CPTCode(code="72148", description="MRI lumbar spine without contrast")
        ]
        
        for code in valid_codes:
            errors = await validation_service._validate_cpt_code(code, "test_field")
            assert len(errors) == 0
    
    @pytest.mark.asyncio

    
    async def test_validate_invalid_cpt_codes(self, validation_service):
        """Test validation of invalid CPT codes."""
        # Test codes that pass Pydantic validation but fail business validation
        invalid_codes = [
            CPTCode(code="70000", description="Invalid imaging code"),  # Valid format, not in our validation set
            CPTCode(code="73221", description="Wrong description")  # Valid code, wrong description
        ]
        
        for code in invalid_codes:
            errors = await validation_service._validate_cpt_code(code, "test_field")
            assert len(errors) > 0
            assert any("not recognized" in error.message or "does not match" in error.message for error in errors)
    
    @pytest.mark.asyncio

    
    async def test_validate_hcpcs_codes(self, validation_service):
        """Test validation of HCPCS codes."""
        valid_code = HCPCSCode(code="A0425", description="Ground mileage, per statute mile")
        
        # Valid HCPCS code should pass format validation
        errors = await validation_service._validate_hcpcs_code(valid_code, "test_field")
        assert len(errors) == 0
        
        # Test with invalid code that would be caught by the validator
        invalid_code = HCPCSCode(code="Z9999", description="Non-existent code")
        errors = await validation_service._validate_hcpcs_code(invalid_code, "test_field")
        assert len(errors) > 0
    
    @pytest.mark.asyncio

    
    async def test_code_suggestion_functionality(self, validation_service):
        """Test that code suggestions are provided for invalid codes."""
        invalid_icd10 = ICD10Code(code="M25.999", description="Invalid shoulder code")
        errors = await validation_service._validate_icd10_code(invalid_icd10, "test_field")
        
        assert len(errors) > 0
        assert errors[0].suggestion is not None
        assert "M25.511" in errors[0].suggestion or "shoulder" in errors[0].suggestion.lower()


class TestBusinessRuleValidation:
    """Test cases for business rule validation."""
    
    @pytest.fixture
    def validation_service(self):
        """Create validation service instance."""
        return ValidationService()
    
    @pytest.fixture
    def base_request(self):
        """Create base request for business rule testing."""
        return AuthorizationRequest(
            request_id="req_2024_TEST001",
            provider_id="prov_12345",
            patient_demographics=PatientDemographics(
                patient_id="enc_pat_1a2b3c4d5e6f7g8h",
                age=45,
                gender=Gender.FEMALE,
                insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
                member_id="enc_mem_1z2y3x4w5v6u7t8s"
            ),
            diagnosis_codes=[
                ICD10Code(code="M25.511", description="Pain in right shoulder")
            ],
            procedure_codes=[
                CPTCode(code="73221", description="MRI upper extremity without contrast")
            ],
            procedure_type=ProcedureType.MRI,
            urgency_level=UrgencyLevel.ROUTINE,
            status=RequestStatus.SUBMITTED,
            submitted_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
    
    @pytest.mark.asyncio

    
    async def test_clinical_notes_required_for_mri(self, validation_service, base_request):
        """
        Test that clinical notes are required and adequate for MRI procedures.
        
        This test verifies the business rule that MRI procedures require detailed
        clinical notes to support medical necessity. It tests three scenarios:
        missing notes, insufficient notes, and adequate notes.
        
        Expected behavior:
        - Missing clinical notes should generate validation error
        - Brief clinical notes should generate validation error
        - Adequate clinical notes should pass validation
        - Error messages should clearly indicate the requirement
        """
        # Request without clinical notes should fail
        base_request.clinical_notes = None
        
        errors = await validation_service._validate_clinical_notes_requirement(base_request)
        assert len(errors) > 0, \
            "MRI requests without clinical notes should generate validation errors"
        assert "clinical notes are required" in errors[0].message.lower(), \
            f"Error message should indicate clinical notes requirement, got: {errors[0].message}"
        
        # Request with too brief clinical notes should fail
        base_request.clinical_notes = "Pain"  # Too short
        
        errors = await validation_service._validate_clinical_notes_requirement(base_request)
        assert len(errors) > 0, \
            "MRI requests with brief clinical notes should generate validation errors"
        assert "too brief" in errors[0].message.lower(), \
            f"Error message should indicate notes are too brief, got: {errors[0].message}"
        
        # Request with adequate clinical notes should pass
        base_request.clinical_notes = "Patient reports persistent shoulder pain for 6 weeks following sports injury."
        
        errors = await validation_service._validate_clinical_notes_requirement(base_request)
        assert len(errors) == 0, \
            f"MRI requests with adequate clinical notes should pass validation, got errors: {errors}"
    
    @pytest.mark.asyncio

    
    async def test_age_appropriateness_validation(self, validation_service, base_request):
        """Test age appropriateness validation for different procedures."""
        # Young patient with brain MRI should generate warning
        base_request.patient_demographics.age = 3
        base_request.procedure_codes = [CPTCode(code="70551", description="MRI brain without contrast")]
        
        errors, warnings = await validation_service._validate_age_appropriateness(base_request)
        assert len(errors) == 0  # Should be warnings, not errors
        assert len(warnings) > 0
        assert any("under 5 years" in warning for warning in warnings)
        
        # Elderly patient with spine MRI should generate warning
        base_request.patient_demographics.age = 85
        base_request.procedure_codes = [CPTCode(code="72148", description="MRI lumbar spine without contrast")]
        
        errors, warnings = await validation_service._validate_age_appropriateness(base_request)
        assert len(errors) == 0
        assert len(warnings) > 0
        assert any("over 80 years" in warning for warning in warnings)
    
    @pytest.mark.asyncio

    
    async def test_urgency_level_validation(self, validation_service, base_request):
        """Test urgency level validation."""
        # Emergent urgency should generate warning
        base_request.urgency_level = UrgencyLevel.EMERGENT
        
        warnings = await validation_service._validate_urgency_level(base_request)
        assert len(warnings) > 0
        assert any("emergent urgency level" in warning.lower() for warning in warnings)
        
        # Routine urgency should not generate warnings
        base_request.urgency_level = UrgencyLevel.ROUTINE
        
        warnings = await validation_service._validate_urgency_level(base_request)
        assert len(warnings) == 0


class TestFieldRelationshipValidation:
    """Test cases for cross-field validation."""
    
    @pytest.fixture
    def validation_service(self):
        """Create validation service instance."""
        return ValidationService()
    
    @pytest.fixture
    def base_request(self):
        """Create base request for relationship testing."""
        return AuthorizationRequest(
            request_id="req_2024_TEST001",
            provider_id="prov_12345",
            patient_demographics=PatientDemographics(
                patient_id="enc_pat_1a2b3c4d5e6f7g8h",
                age=45,
                gender=Gender.FEMALE,
                insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
                member_id="enc_mem_1z2y3x4w5v6u7t8s"
            ),
            diagnosis_codes=[ICD10Code(code="M25.511", description="Pain in right shoulder")],  # Valid default
            procedure_codes=[CPTCode(code="73221", description="MRI upper extremity without contrast")],  # Valid default
            procedure_type=ProcedureType.MRI,
            urgency_level=UrgencyLevel.ROUTINE,
            status=RequestStatus.SUBMITTED,
            submitted_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
    
    @pytest.mark.asyncio

    
    async def test_diagnosis_procedure_relationship_valid(self, validation_service, base_request):
        """Test valid diagnosis-procedure relationships."""
        # Shoulder diagnosis with shoulder MRI should be valid
        base_request.diagnosis_codes = [ICD10Code(code="M25.511", description="Pain in right shoulder")]
        base_request.procedure_codes = [CPTCode(code="73221", description="MRI upper extremity without contrast")]
        
        errors = await validation_service._validate_diagnosis_procedure_relationship(base_request)
        assert len(errors) == 0
    
    @pytest.mark.asyncio

    
    async def test_diagnosis_procedure_relationship_invalid(self, validation_service, base_request):
        """Test invalid diagnosis-procedure relationships."""
        # Non-shoulder diagnosis with shoulder MRI should generate error
        base_request.diagnosis_codes = [ICD10Code(code="G93.1", description="Anoxic brain damage")]
        base_request.procedure_codes = [CPTCode(code="73221", description="MRI upper extremity without contrast")]
        
        errors = await validation_service._validate_diagnosis_procedure_relationship(base_request)
        assert len(errors) > 0
        assert any("shoulder mri" in error.message.lower() and "shoulder-related diagnosis" in error.message.lower() 
                  for error in errors)
    
    @pytest.mark.asyncio

    
    async def test_multiple_procedures_warning(self, validation_service, base_request):
        """Test warning for multiple MRI procedures."""
        # Multiple MRI procedures should generate warning
        base_request.diagnosis_codes = [ICD10Code(code="M25.511", description="Pain in right shoulder")]
        base_request.procedure_codes = [
            CPTCode(code="70551", description="MRI brain without contrast"),
            CPTCode(code="73221", description="MRI upper extremity without contrast"),
            CPTCode(code="72148", description="MRI lumbar spine without contrast")
        ]
        
        warnings = await validation_service._check_code_compatibility(base_request)
        assert len(warnings) > 0
        assert any("multiple mri procedures" in warning.lower() for warning in warnings)


class TestValidationErrorHandling:
    """Test cases for validation error handling and edge cases."""
    
    @pytest.fixture
    def validation_service(self):
        """Create validation service instance."""
        return ValidationService()
    
    @pytest.mark.asyncio
    async def test_validation_service_exception_handling(self, validation_service):
        """Test handling of unexpected exceptions during validation."""
        # Create a valid request for testing exception handling
        valid_request = AuthorizationRequest(
            request_id="req_2024_TEST001",
            provider_id="prov_12345",
            patient_demographics=PatientDemographics(
                patient_id="enc_pat_1a2b3c4d5e6f7g8h",
                age=45,
                gender=Gender.FEMALE,
                insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
                member_id="enc_mem_1z2y3x4w5v6u7t8s"
            ),
            diagnosis_codes=[ICD10Code(code="M25.511", description="Pain in right shoulder")],
            procedure_codes=[CPTCode(code="73221", description="MRI upper extremity without contrast")],
            procedure_type=ProcedureType.MRI,
            urgency_level=UrgencyLevel.ROUTINE,
            status=RequestStatus.SUBMITTED,
            submitted_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        # Mock an exception in one of the validation methods
        with pytest.MonkeyPatch().context() as m:
            def mock_validate_medical_codes(*args, **kwargs):
                raise Exception("Simulated database error")
            
            m.setattr(validation_service, '_validate_medical_codes', mock_validate_medical_codes)
            
            result = await validation_service.validate_request(valid_request)
            
            # Should return validation failure, not raise exception
            assert result.is_valid is False
            assert len(result.errors) > 0
            assert "validation service encountered an unexpected error" in result.errors[0].message.lower()
    
    @pytest.mark.asyncio

    
    async def test_validation_performance(self, validation_service):
        """Test that validation completes within reasonable time."""
        # Create a complex request
        complex_request = AuthorizationRequest(
            request_id="req_2024_TEST001",
            provider_id="prov_12345",
            patient_demographics=PatientDemographics(
                patient_id="enc_pat_1a2b3c4d5e6f7g8h",
                age=45,
                gender=Gender.FEMALE,
                insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
                member_id="enc_mem_1z2y3x4w5v6u7t8s"
            ),
            diagnosis_codes=[
                ICD10Code(code="M25.511", description="Pain in right shoulder"),
                ICD10Code(code="M25.512", description="Pain in left shoulder")
            ],
            procedure_codes=[
                CPTCode(code="73221", description="MRI upper extremity without contrast"),
                CPTCode(code="73222", description="MRI upper extremity with contrast")
            ],
            clinical_notes="Complex case with bilateral shoulder pain requiring detailed evaluation.",
            procedure_type=ProcedureType.MRI,
            urgency_level=UrgencyLevel.ROUTINE,
            status=RequestStatus.SUBMITTED,
            submitted_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        result = await validation_service.validate_request(complex_request)
        
        # Validation should complete within 5 seconds (5000ms)
        assert result.processing_time_ms < 5000
        assert result.processing_time_ms > 0
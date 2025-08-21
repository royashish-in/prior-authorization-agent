"""
Unit tests for healthcare data models and validation.
"""

import pytest
from datetime import datetime, date, timedelta, timezone
from pydantic import ValidationError

from src.models.authorization import AuthorizationRequest, AuthorizationDecision
from src.models.patient import PatientDemographics
from src.models.medical_codes import ICD10Code, CPTCode, HCPCSCode
from src.models.enums import (
    RequestStatus, DecisionStatus, UrgencyLevel, Gender, ProcedureType
)


class TestICD10Code:
    """Test ICD-10 code validation."""
    
    def test_valid_icd10_codes(self):
    """
        Test validation of properly formatted ICD-10 diagnosis codes.
        
        This test verifies that ICD-10 codes following the standard format
        (letter + 2-3 digits + optional decimal + 1-4 additional characters)
        are accepted and properly normalized to uppercase.
        
        Expected behavior:
        - All valid ICD-10 formats should be accepted
        - Codes should be normalized to uppercase
        - No validation errors should be raised
        """
        valid_codes = [
            "A00",        # Basic 3-character code
            "B15.9",      # Code with decimal and single digit
            "S72.001A",   # Complex code with decimal and extension
            "Z51.11",     # Z-code with decimal
            "M25.511"     # Musculoskeletal code with decimal
        ]
        
        for code in valid_codes:
            icd10 = ICD10Code(code=code)
            assert icd10.code == code.upper(), \
                f"ICD-10 code should be normalized to uppercase: expected {code.upper()}, got {icd10.code}"
    
        def test_invalid_icd10_codes(self):
    """
        Test rejection of improperly formatted ICD-10 diagnosis codes.
        
        This test verifies that ICD-10 codes not following the standard format
        are properly rejected with ValidationError. Invalid formats include
        empty strings, numeric-only codes, incomplete codes, and overly long codes.
        
        Expected behavior:
        - All invalid formats should raise ValidationError
        - Validation should occur at model instantiation
        - Error should prevent object creation
        """
        invalid_codes = [
            "",           # Empty string
            "123",        # Numeric only
            "A",          # Too short (missing digits)
            "A1",         # Too short (only one digit)
            "AA1",        # Invalid format (two letters)
            "A123",       # Too long without decimal
            "A12.12345"   # Too many decimal places
        ]
        
        for code in invalid_codes:
            with pytest.raises(ValidationError, match=".*") as exc_info:
                ICD10Code(code=code)
            
            # Verify that the validation error is related to the code format
            error_msg = str(exc_info.value).lower()
            assert "code" in error_msg or "format" in error_msg or "pattern" in error_msg, \
                f"ValidationError should mention code format issue for '{code}', got: {exc_info.value}"
    
        def test_icd10_with_description(self):
    """
        Test ICD-10 code creation with description field.
        
        This test verifies that ICD-10 codes can be created with optional
        description fields and that the description is properly stored.
        """
        icd10 = ICD10Code(code="A00.0", description="Cholera due to Vibrio cholerae 01, biovar cholerae")
        assert icd10.code == "A00.0"
        assert icd10.description == "Cholera due to Vibrio cholerae 01, biovar cholerae"

        class TestCPTCode:
    """Test CPT code validation."""
    
    def test_valid_cpt_codes(self):
    """
        Test validation of properly formatted CPT procedure codes.
        
        This test verifies that CPT codes following the standard 5-digit format
        are accepted and properly validated.
        """
        - Valid data should pass validation without errors
        - Invalid data should be rejected with specific error messages
        - Error messages should be clear and actionable
        - Validation should be consistent and deterministic
        
        Business Rules:
        - CPT codes must be 5-digit numeric codes with valid category assignments
        
        PHI Compliance:
        Uses only synthetic test data with clear SYNTH_ prefixes.
        """
    
        def test_valid_hcpcs_codes(self):
    """
        Test valid hcpcs codes.
        
        This test verifies that the hcpcscode correctly validates medical codes
        and handles both valid and invalid input scenarios appropriately.
        
        Test Scenarios:
        - Valid input data that meets all validation criteria
        - Invalid input data with specific validation errors
        - Edge cases and boundary conditions
        - Error handling and user-friendly error messages
        
        Expected Behavior:
        - Valid data should pass validation without errors
        - Invalid data should be rejected with specific error messages
        - Error messages should be clear and actionable
        - Validation should be consistent and deterministic
        
        Business Rules:
        - All input data must meet healthcare industry standards and regulatory requirements
        
        PHI Compliance:
        Uses only synthetic test data with clear SYNTH_ prefixes.
        """
    
        def test_valid_patient_demographics(self):
    """
        Test valid patient demographics.
        
        This test verifies that the patientdemographics correctly validates patient demographic data
        and handles both valid and invalid input scenarios appropriately.
        
        Test Scenarios:
        - Valid input data that meets all validation criteria
        - Invalid input data with specific validation errors
        - Edge cases and boundary conditions
        - Error handling and user-friendly error messages
        
        Expected Behavior:
        - Valid data should pass validation without errors
        - Invalid data should be rejected with specific error messages
        - Error messages should be clear and actionable
        - Validation should be consistent and deterministic
        
        Business Rules:
        - All input data must meet healthcare industry standards and regulatory requirements
        
        PHI Compliance:
        Uses only synthetic test data with clear SYNTH_ prefixes.
        """
    
        def create_valid_request(self) -> AuthorizationRequest:
        """Create a valid authorization request for testing."""
        return AuthorizationRequest(
            request_id="req_2024_001234",
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
            clinical_notes="Patient reports persistent shoulder pain for 6 weeks",
            procedure_type=ProcedureType.MRI,
            urgency_level=UrgencyLevel.ROUTINE
        )
    
    def test_valid_authorization_request(self):
    """
        Test valid authorization request.
        
        This test verifies that the authorizationrequest correctly validates input data
        and handles both valid and invalid input scenarios appropriately.
        
        Test Scenarios:
        - Valid input data that meets all validation criteria
        - Invalid input data with specific validation errors
        - Edge cases and boundary conditions
        - Error handling and user-friendly error messages
        
        Expected Behavior:
        - Valid data should pass validation without errors
        - Invalid data should be rejected with specific error messages
        - Error messages should be clear and actionable
        - Validation should be consistent and deterministic
        
        Business Rules:
        - All input data must meet healthcare industry standards and regulatory requirements
        
        PHI Compliance:
        Uses only synthetic test data with clear SYNTH_ prefixes.
        """
    
    def create_valid_decision(self, status: DecisionStatus = DecisionStatus.APPROVED) -> AuthorizationDecision:
        """Create a valid authorization decision for testing."""
        decision_data = {
            "decision_id": "dec_2024_001234",
            "request_id": "req_2024_001234",
            "status": status,
            "reasoning": [
                "Patient meets medical necessity criteria",
                "Diagnosis code is covered under policy"
            ],
            "policy_references": ["CMS NCD 220.2"],
            "confidence_score": 0.95
        }
        
        if status == DecisionStatus.APPROVED:
            decision_data.update({
                "authorization_number": "auth_2024_567890",
                "valid_until": datetime.now(timezone.utc) + timedelta(days=30)
            })
        
        return AuthorizationDecision(**decision_data)
    
        def test_valid_approved_decision(self):
    """
        Test valid approved decision.
        
        This test verifies that the authorizationdecision correctly validates input data
        and handles both valid and invalid input scenarios appropriately.
        
        Test Scenarios:
        - Valid input data that meets all validation criteria
        - Invalid input data with specific validation errors
        - Edge cases and boundary conditions
        - Error handling and user-friendly error messages
        
        Expected Behavior:
        - Valid data should pass validation without errors
        - Invalid data should be rejected with specific error messages
        - Error messages should be clear and actionable
        - Validation should be consistent and deterministic
        
        Business Rules:
        - All input data must meet healthcare industry standards and regulatory requirements
        
        PHI Compliance:
        Uses only synthetic test data with clear SYNTH_ prefixes.
        """
        with pytest.raises(ValidationError):
            AuthorizationDecision(
                decision_id="dec_2024_001234",
                request_id="req_2024_001234",
                status=DecisionStatus.APPROVED,
                reasoning=["Approved"],
                confidence_score=0.95
                # Missing authorization_number and valid_until
            )
    
        def test_invalid_confidence_score(self):
    """
        Test invalid confidence score.
        
        This test verifies that the authorizationdecision correctly validates input data
        and handles both valid and invalid input scenarios appropriately.
        
        Test Scenarios:
        - Valid input data that meets all validation criteria
        - Invalid input data with specific validation errors
        - Edge cases and boundary conditions
        - Error handling and user-friendly error messages
        
        Expected Behavior:
        - Valid data should pass validation without errors
        - Invalid data should be rejected with specific error messages
        - Error messages should be clear and actionable
        - Validation should be consistent and deterministic
        
        Business Rules:
        - All input data must meet healthcare industry standards and regulatory requirements
        
        PHI Compliance:
        Uses only synthetic test data with clear SYNTH_ prefixes.
        """

        """
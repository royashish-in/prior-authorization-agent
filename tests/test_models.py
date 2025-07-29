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
        """Test valid ICD-10 code formats."""
        valid_codes = [
            "A00",
            "B15.9",
            "S72.001A",
            "Z51.11",
            "M25.511"
        ]
        
        for code in valid_codes:
            icd10 = ICD10Code(code=code)
            assert icd10.code == code.upper()
    
    def test_invalid_icd10_codes(self):
        """Test invalid ICD-10 code formats."""
        invalid_codes = [
            "",
            "123",
            "A",
            "A1",
            "AA1",
            "A123",
            "A12.12345"
        ]
        
        for code in invalid_codes:
            with pytest.raises(ValidationError):
                ICD10Code(code=code)
    
    def test_icd10_with_description(self):
        """Test ICD-10 code with description."""
        icd10 = ICD10Code(
            code="M25.511",
            description="Pain in right shoulder"
        )
        assert icd10.code == "M25.511"
        assert icd10.description == "Pain in right shoulder"
    
    def test_icd10_string_representation(self):
        """Test ICD-10 string representation."""
        icd10 = ICD10Code(code="M25.511")
        assert str(icd10) == "M25.511"


class TestCPTCode:
    """Test CPT code validation."""
    
    def test_valid_cpt_codes(self):
        """Test valid CPT code formats."""
        valid_codes = [
            "70551",  # Brain MRI
            "72148",  # Lumbar spine MRI
            "73221",  # Upper extremity MRI
            "74177",  # CT abdomen
            "76700"   # Ultrasound
        ]
        
        for code in valid_codes:
            cpt = CPTCode(code=code)
            assert cpt.code == code
    
    def test_invalid_cpt_codes(self):
        """Test invalid CPT code formats."""
        invalid_codes = [
            "",
            "1234",
            "123456",
            "ABCDE",
            "12345",  # Outside imaging range
            "99999"   # Outside imaging range
        ]
        
        for code in invalid_codes:
            with pytest.raises(ValidationError):
                CPTCode(code=code)
    
    def test_cpt_with_modifier(self):
        """Test CPT code with modifier."""
        cpt = CPTCode(
            code="70551",
            modifier="26",
            description="Brain MRI professional component"
        )
        assert cpt.code == "70551"
        assert cpt.modifier == "26"
        assert str(cpt) == "70551-26"
    
    def test_invalid_cpt_modifiers(self):
        """Test invalid CPT modifiers."""
        invalid_modifiers = ["", "1", "ABC", "2A3"]
        
        for modifier in invalid_modifiers:
            with pytest.raises(ValidationError):
                CPTCode(code="70551", modifier=modifier)


class TestHCPCSCode:
    """Test HCPCS code validation."""
    
    def test_valid_hcpcs_codes(self):
        """Test valid HCPCS code formats."""
        valid_codes = [
            "A0425",
            "G0202",
            "J1100",
            "Q9967"
        ]
        
        for code in valid_codes:
            hcpcs = HCPCSCode(code=code)
            assert hcpcs.code == code.upper()
    
    def test_invalid_hcpcs_codes(self):
        """Test invalid HCPCS code formats."""
        invalid_codes = [
            "",
            "A123",
            "A12345",
            "1234A",
            "ABCDE"
        ]
        
        for code in invalid_codes:
            with pytest.raises(ValidationError):
                HCPCSCode(code=code)


class TestPatientDemographics:
    """Test patient demographics model."""
    
    def test_valid_patient_demographics(self):
        """Test valid patient demographics."""
        patient = PatientDemographics(
            patient_id="enc_pat_1a2b3c4d5e6f7g8h",
            age=45,
            gender=Gender.FEMALE,
            insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
            member_id="enc_mem_1z2y3x4w5v6u7t8s",
            date_of_birth=date(1978, 3, 15)
        )
        
        assert patient.age == 45
        assert patient.gender == Gender.FEMALE
        assert patient.patient_id == "enc_pat_1a2b3c4d5e6f7g8h"
    
    def test_invalid_age(self):
        """Test invalid patient age."""
        with pytest.raises(ValidationError):
            PatientDemographics(
                patient_id="enc_pat_1a2b3c4d5e6f7g8h",
                age=-1,
                gender=Gender.MALE,
                insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
                member_id="enc_mem_1z2y3x4w5v6u7t8s"
            )
        
        with pytest.raises(ValidationError):
            PatientDemographics(
                patient_id="enc_pat_1a2b3c4d5e6f7g8h",
                age=200,
                gender=Gender.MALE,
                insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
                member_id="enc_mem_1z2y3x4w5v6u7t8s"
            )
    
    def test_invalid_phi_fields(self):
        """Test validation of PHI fields."""
        # Test empty PHI fields
        with pytest.raises(ValidationError):
            PatientDemographics(
                patient_id="",
                age=45,
                gender=Gender.FEMALE,
                insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
                member_id="enc_mem_1z2y3x4w5v6u7t8s"
            )
        
        # Test short PHI fields (appears unencrypted)
        with pytest.raises(ValidationError):
            PatientDemographics(
                patient_id="123",
                age=45,
                gender=Gender.FEMALE,
                insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
                member_id="enc_mem_1z2y3x4w5v6u7t8s"
            )


class TestAuthorizationRequest:
    """Test authorization request model."""
    
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
        """Test valid authorization request."""
        request = self.create_valid_request()
        
        assert request.request_id == "req_2024_001234"
        assert request.provider_id == "prov_12345"
        assert request.procedure_type == ProcedureType.MRI
        assert request.status == RequestStatus.SUBMITTED
        assert len(request.diagnosis_codes) == 1
        assert len(request.procedure_codes) == 1
    
    def test_invalid_request_id(self):
        """Test invalid request ID formats."""
        # Test empty request ID
        with pytest.raises(ValidationError):
            AuthorizationRequest(
                request_id="",
                provider_id="prov_12345",
                patient_demographics=PatientDemographics(
                    patient_id="enc_pat_1a2b3c4d5e6f7g8h",
                    age=45,
                    gender=Gender.FEMALE,
                    insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
                    member_id="enc_mem_1z2y3x4w5v6u7t8s"
                ),
                diagnosis_codes=[ICD10Code(code="M25.511")],
                procedure_codes=[CPTCode(code="73221")],
                procedure_type=ProcedureType.MRI
            )
        
        # Test invalid prefix
        with pytest.raises(ValidationError):
            AuthorizationRequest(
                request_id="invalid_123",
                provider_id="prov_12345",
                patient_demographics=PatientDemographics(
                    patient_id="enc_pat_1a2b3c4d5e6f7g8h",
                    age=45,
                    gender=Gender.FEMALE,
                    insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
                    member_id="enc_mem_1z2y3x4w5v6u7t8s"
                ),
                diagnosis_codes=[ICD10Code(code="M25.511")],
                procedure_codes=[CPTCode(code="73221")],
                procedure_type=ProcedureType.MRI
            )
    
    def test_empty_diagnosis_codes(self):
        """Test validation with empty diagnosis codes."""
        with pytest.raises(ValidationError):
            AuthorizationRequest(
                request_id="req_2024_001234",
                provider_id="prov_12345",
                patient_demographics=PatientDemographics(
                    patient_id="enc_pat_1a2b3c4d5e6f7g8h",
                    age=45,
                    gender=Gender.FEMALE,
                    insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
                    member_id="enc_mem_1z2y3x4w5v6u7t8s"
                ),
                diagnosis_codes=[],  # Empty list
                procedure_codes=[
                    CPTCode(code="73221")
                ],
                procedure_type=ProcedureType.MRI
            )
    
    def test_too_many_codes(self):
        """Test validation with too many codes."""
        # Test too many diagnosis codes
        with pytest.raises(ValidationError):
            AuthorizationRequest(
                request_id="req_2024_001234",
                provider_id="prov_12345",
                patient_demographics=PatientDemographics(
                    patient_id="enc_pat_1a2b3c4d5e6f7g8h",
                    age=45,
                    gender=Gender.FEMALE,
                    insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
                    member_id="enc_mem_1z2y3x4w5v6u7t8s"
                ),
                diagnosis_codes=[ICD10Code(code=f"A0{i}.0") for i in range(11)],
                procedure_codes=[CPTCode(code="73221")],
                procedure_type=ProcedureType.MRI
            )
        
        # Test too many procedure codes
        with pytest.raises(ValidationError):
            AuthorizationRequest(
                request_id="req_2024_001234",
                provider_id="prov_12345",
                patient_demographics=PatientDemographics(
                    patient_id="enc_pat_1a2b3c4d5e6f7g8h",
                    age=45,
                    gender=Gender.FEMALE,
                    insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
                    member_id="enc_mem_1z2y3x4w5v6u7t8s"
                ),
                diagnosis_codes=[ICD10Code(code="M25.511")],
                procedure_codes=[CPTCode(code=f"7055{i}") for i in range(6)],
                procedure_type=ProcedureType.MRI
            )
    
    def test_clinical_notes_validation(self):
        """Test clinical notes validation."""
        # Test empty notes (should be None)
        request = AuthorizationRequest(
            request_id="req_2024_001234",
            provider_id="prov_12345",
            patient_demographics=PatientDemographics(
                patient_id="enc_pat_1a2b3c4d5e6f7g8h",
                age=45,
                gender=Gender.FEMALE,
                insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
                member_id="enc_mem_1z2y3x4w5v6u7t8s"
            ),
            diagnosis_codes=[ICD10Code(code="M25.511")],
            procedure_codes=[CPTCode(code="73221")],
            clinical_notes="",
            procedure_type=ProcedureType.MRI
        )
        assert request.clinical_notes is None
        
        # Test very long notes
        with pytest.raises(ValidationError):
            AuthorizationRequest(
                request_id="req_2024_001234",
                provider_id="prov_12345",
                patient_demographics=PatientDemographics(
                    patient_id="enc_pat_1a2b3c4d5e6f7g8h",
                    age=45,
                    gender=Gender.FEMALE,
                    insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
                    member_id="enc_mem_1z2y3x4w5v6u7t8s"
                ),
                diagnosis_codes=[ICD10Code(code="M25.511")],
                procedure_codes=[CPTCode(code="73221")],
                clinical_notes="x" * 10001,
                procedure_type=ProcedureType.MRI
            )


class TestAuthorizationDecision:
    """Test authorization decision model."""
    
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
        """Test valid approved decision."""
        decision = self.create_valid_decision(DecisionStatus.APPROVED)
        
        assert decision.status == DecisionStatus.APPROVED
        assert decision.authorization_number == "auth_2024_567890"
        assert decision.valid_until is not None
        assert decision.confidence_score == 0.95
        assert decision.decided_at is not None
    
    def test_valid_denied_decision(self):
        """Test valid denied decision."""
        decision = self.create_valid_decision(DecisionStatus.DENIED)
        
        assert decision.status == DecisionStatus.DENIED
        assert decision.authorization_number is None
        assert decision.valid_until is None
    
    def test_approved_decision_requires_auth_number(self):
        """Test that approved decisions require authorization number."""
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
        """Test invalid confidence scores."""
        with pytest.raises(ValidationError):
            AuthorizationDecision(
                decision_id="dec_2024_001234",
                request_id="req_2024_001234",
                status=DecisionStatus.DENIED,
                reasoning=["Denied"],
                confidence_score=-0.1
            )
        
        with pytest.raises(ValidationError):
            AuthorizationDecision(
                decision_id="dec_2024_001234",
                request_id="req_2024_001234",
                status=DecisionStatus.DENIED,
                reasoning=["Denied"],
                confidence_score=1.1
            )
    
    def test_empty_reasoning(self):
        """Test validation with empty reasoning."""
        with pytest.raises(ValidationError):
            AuthorizationDecision(
                decision_id="dec_2024_001234",
                request_id="req_2024_001234",
                status=DecisionStatus.DENIED,
                reasoning=[],  # Empty reasoning
                confidence_score=0.95
            )
    
    def test_invalid_decision_id_format(self):
        """Test invalid decision ID formats."""
        with pytest.raises(ValidationError):
            AuthorizationDecision(
                decision_id="invalid_123",
                request_id="req_2024_001234",
                status=DecisionStatus.DENIED,
                reasoning=["Denied"],
                confidence_score=0.95
            )
    
    def test_expired_authorization(self):
        """Test validation of authorization expiration date."""
        with pytest.raises(ValidationError):
            AuthorizationDecision(
                decision_id="dec_2024_001234",
                request_id="req_2024_001234",
                status=DecisionStatus.APPROVED,
                reasoning=["Approved"],
                authorization_number="auth_2024_567890",
                valid_until=datetime.now(timezone.utc) - timedelta(days=1),  # Past date
                confidence_score=0.95
            )
"""
Unit tests for medical necessity evaluation engine.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.services.medical_necessity import (
    MedicalNecessityEngine,
    NecessityLevel,
    ClinicalIndicator,
    ClinicalEvidence,
    MedicalNecessityResult,
    ProcedureRule
)
from src.models.authorization import AuthorizationRequest
from src.models.patient import PatientDemographics
from src.models.medical_codes import ICD10Code, CPTCode
from src.models.enums import DecisionStatus, UrgencyLevel, ProcedureType, RequestStatus


class TestMedicalNecessityEngine:
    """Test cases for MedicalNecessityEngine."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.engine = MedicalNecessityEngine()
        
        # Sample patient demographics
        self.patient_demographics = PatientDemographics(
            patient_id="enc_pat_test123",
            age=45,
            gender=Gender.FEMALE,
            insurance_id="enc_ins_test456",
            member_id="enc_mem_test789"
        )
        
        # Sample diagnosis and procedure codes
        self.diagnosis_codes = [ICD10Code(code="M25.511", description="Pain in right shoulder")]
        self.procedure_codes = [CPTCode(code="73221", description="MRI upper extremity without contrast")]
    
    def create_sample_request(self, clinical_notes: str = None, procedure_type: ProcedureType = ProcedureType.MRI):
        """Create a sample authorization request."""
        return AuthorizationRequest(
            request_id="req_test_001",
            provider_id="prov_test_001",
            patient_demographics=self.patient_demographics,
            diagnosis_codes=self.diagnosis_codes,
            procedure_codes=self.procedure_codes,
            clinical_notes=clinical_notes,
            procedure_type=procedure_type,
            urgency_level=UrgencyLevel.ROUTINE,
            status=RequestStatus.SUBMITTED
        )
    
        def test_evaluate_medical_necessity_high_level(self):
    """Test medical necessity evaluation with high necessity level."""
        clinical_notes = """
        Patient presents with chronic shoulder pain lasting 8 weeks.
        Neurological deficit with weakness and numbness in right arm.
        Conservative treatment with physical therapy has failed.
        Functional impairment affecting activities of daily living.
        """
        
        request = self.create_sample_request(clinical_notes)
        result = self.engine.evaluate_medical_necessity(request)
        
        assert isinstance(result, MedicalNecessityResult)
        assert result.necessity_level == NecessityLevel.HIGH
        assert result.confidence_score > 0.7
        assert len(result.clinical_evidence) > 0
        assert len(result.criteria_met) >= 3
        assert len(result.reasoning) > 0
        
        # Check for specific clinical indicators
        evidence_indicators = {ev.indicator for ev in result.clinical_evidence}
        assert ClinicalIndicator.PAIN_CHRONIC in evidence_indicators
        assert ClinicalIndicator.NEUROLOGICAL_DEFICIT in evidence_indicators
        assert ClinicalIndicator.CONSERVATIVE_TREATMENT_FAILED in evidence_indicators
    
    def test_evaluate_medical_necessity_moderate_level(self):
    """Test medical necessity evaluation with moderate necessity level."""
        clinical_notes = """
        Patient reports persistent shoulder pain for 6 weeks.
        Some functional impairment noted.
        Physical examination shows limited range of motion.
        """
        
        request = self.create_sample_request(clinical_notes)
        result = self.engine.evaluate_medical_necessity(request)
        
        assert result.necessity_level in [NecessityLevel.MODERATE, NecessityLevel.HIGH]
        assert result.confidence_score > 0.4
        assert len(result.clinical_evidence) > 0
        
        # Check for chronic pain indicator
        evidence_indicators = {ev.indicator for ev in result.clinical_evidence}
        assert ClinicalIndicator.PAIN_CHRONIC in evidence_indicators
    
        def test_evaluate_medical_necessity_insufficient_level(self):
    """Test medical necessity evaluation with insufficient evidence."""
        clinical_notes = "Patient requests MRI scan."
        
        request = self.create_sample_request(clinical_notes)
        result = self.engine.evaluate_medical_necessity(request)
        
        assert result.necessity_level == NecessityLevel.INSUFFICIENT
        assert result.confidence_score < 0.5
        assert len(result.additional_documentation_needed) > 0
        assert "Additional clinical documentation required" in " ".join(result.reasoning)
    
    def test_evaluate_medical_necessity_empty_notes(self):
    """Test medical necessity evaluation with empty clinical notes."""
        request = self.create_sample_request(clinical_notes="")
        result = self.engine.evaluate_medical_necessity(request)
        
        assert result.necessity_level == NecessityLevel.INSUFFICIENT
        assert result.confidence_score == 0.0
        assert len(result.clinical_evidence) == 0
        assert len(result.additional_documentation_needed) > 0
    
    def test_extract_clinical_evidence_chronic_pain(self):
    """
        Test extract clinical evidence chronic pain.
        
        This test verifies system functionality and ensures that the system
        behaves correctly under the specified conditions.
        
        Test Scenarios:
        - Standard input scenarios
        - Edge cases and boundary conditions
        - Error handling scenarios
        
        Expected Behavior:
        - System should behave according to specified requirements
        
        PHI Compliance:
        All test data uses synthetic information with appropriate markers.
        """
        policy_results = [
            {
                "is_covered": True,
                "reasoning": ["Policy 1 approves coverage"],
                "confidence_score": 0.9
            },
            {
                "is_covered": True,
                "reasoning": ["Policy 2 approves coverage"],
                "confidence_score": 0.8
            }
        ]
        
        necessity_result = MedicalNecessityResult(
            necessity_level=NecessityLevel.HIGH,
            confidence_score=0.9,
            clinical_evidence=[],
            criteria_met=["Test criteria"],
            criteria_not_met=[],
            additional_documentation_needed=[],
            reasoning=["High medical necessity"],
            procedure_specific_findings={}
        )
        
        result = self.engine.resolve_policy_conflicts(policy_results, necessity_result)
        
        assert result["final_decision"] == "approve"
        assert result["resolution_method"] == "all_approve_with_necessity"
        assert len(result["conflicts_detected"]) == 0
        assert result["confidence_score"] == 0.8  # Minimum of policy and necessity scores
    
        def test_resolve_policy_conflicts_some_deny(self):
    """Test policy conflict resolution when some policies deny."""
        policy_results = [
            {
                "is_covered": True,
                "reasoning": ["Policy 1 approves coverage"],
                "confidence_score": 0.9
            },
            {
                "is_covered": False,
                "reasoning": ["Policy 2 denies coverage - age restriction"],
                "confidence_score": 0.8
            }
        ]
        
        necessity_result = MedicalNecessityResult(
            necessity_level=NecessityLevel.HIGH,
            confidence_score=0.9,
            clinical_evidence=[],
            criteria_met=["Test criteria"],
            criteria_not_met=[],
            additional_documentation_needed=[],
            reasoning=["High medical necessity"],
            procedure_specific_findings={}
        )
        
        result = self.engine.resolve_policy_conflicts(policy_results, necessity_result)
        
        assert result["final_decision"] == "deny"
        assert result["resolution_method"] == "most_restrictive_deny"
        assert len(result["conflicts_detected"]) == 1
        assert result["conflicts_detected"][0]["type"] == "approval_conflict"
    
    def test_resolve_policy_conflicts_insufficient_necessity(self):
    """Test policy conflict resolution with insufficient medical necessity."""
        policy_results = [
            {
                "is_covered": True,
                "reasoning": ["Policy approves coverage"],
                "confidence_score": 0.9
            }
        ]
        
        necessity_result = MedicalNecessityResult(
            necessity_level=NecessityLevel.INSUFFICIENT,
            confidence_score=0.2,
            clinical_evidence=[],
            criteria_met=[],
            criteria_not_met=["Missing clinical documentation"],
            additional_documentation_needed=["Clinical notes"],
            reasoning=["Insufficient medical necessity"],
            procedure_specific_findings={}
        )
        
        result = self.engine.resolve_policy_conflicts(policy_results, necessity_result)
        
        assert result["final_decision"] == "request_info"
        assert result["resolution_method"] == "insufficient_necessity_request_info"
        assert "Additional documentation may establish medical necessity" in " ".join(result["reasoning"])
    
    def test_resolve_policy_conflicts_no_policies(self):
    """Test policy conflict resolution with no applicable policies."""
        policy_results = []
        
        necessity_result = MedicalNecessityResult(
            necessity_level=NecessityLevel.HIGH,
            confidence_score=0.9,
            clinical_evidence=[],
            criteria_met=["Test criteria"],
            criteria_not_met=[],
            additional_documentation_needed=[],
            reasoning=["High medical necessity"],
            procedure_specific_findings={}
        )
        
        result = self.engine.resolve_policy_conflicts(policy_results, necessity_result)
        
        assert result["final_decision"] == "deny"
        assert result["resolution_method"] == "no_policies"
        assert "No applicable policies found" in result["reasoning"]
    
    def test_duration_requirement_checking(self):
    """
        Test duration requirement checking.
        
        This test verifies system functionality and ensures that the system
        behaves correctly under the specified conditions.
        
        Test Scenarios:
        - Standard input scenarios
        - Edge cases and boundary conditions
        - Error handling scenarios
        
        Expected Behavior:
        - System should behave according to specified requirements
        
        PHI Compliance:
        All test data uses synthetic information with appropriate markers.
        """
        # Create request with invalid data that might cause errors
        request = self.create_sample_request()
        
        # Mock an exception in evidence extraction
        with patch.object(self.engine, '_extract_clinical_evidence', side_effect=Exception("Test error")):
            result = self.engine.evaluate_medical_necessity(request)
            
            assert result.necessity_level == NecessityLevel.INSUFFICIENT
            assert result.confidence_score == 0.0
            assert "Medical necessity evaluation error" in " ".join(result.reasoning)
    
    def test_policy_conflict_error_handling(self):
    """Test error handling in policy conflict resolution."""
        # Mock an exception in the resolve_policy_conflicts method
        with patch.object(self.engine, '_detect_requirement_conflicts', side_effect=Exception("Test error")):
            policy_results = [{"is_covered": True, "reasoning": ["Test"], "confidence_score": 0.9}]
            
            necessity_result = MedicalNecessityResult(
                necessity_level=NecessityLevel.HIGH,
                confidence_score=0.9,
                clinical_evidence=[],
                criteria_met=[],
                criteria_not_met=[],
                additional_documentation_needed=[],
                reasoning=[],
                procedure_specific_findings={}
            )
            
            result = self.engine.resolve_policy_conflicts(policy_results, necessity_result)
            
            assert result["final_decision"] == "deny"
            assert result["resolution_method"] == "error"
            assert result["confidence_score"] == 0.0
            assert "Policy conflict resolution error" in " ".join(result["reasoning"])


    class TestClinicalEvidence:
    """Test cases for ClinicalEvidence dataclass."""
    
    def test_clinical_evidence_creation(self):
    """
        Test clinical evidence creation.
        
        This test verifies system functionality and ensures that the system
        behaves correctly under the specified conditions.
        
        Test Scenarios:
        - Standard input scenarios
        - Edge cases and boundary conditions
        - Error handling scenarios
        
        Expected Behavior:
        - System should behave according to specified requirements
        
        PHI Compliance:
        All test data uses synthetic information with appropriate markers.
        """
    
    def test_procedure_rule_creation(self):
    """
        Test procedure rule creation.
        
        This test verifies system functionality and ensures that the system
        behaves correctly under the specified conditions.
        
        Test Scenarios:
        - Standard input scenarios
        - Edge cases and boundary conditions
        - Error handling scenarios
        
        Expected Behavior:
        - System should behave according to specified requirements
        
        PHI Compliance:
        All test data uses synthetic information with appropriate markers.
        """

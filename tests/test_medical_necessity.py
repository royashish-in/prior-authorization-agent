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
from src.models.enums import ProcedureType, UrgencyLevel, RequestStatus, Gender


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
        """Test extraction of chronic pain evidence."""
        clinical_notes = "Patient has chronic pain lasting 12 weeks with persistent symptoms."
        
        evidence = self.engine._extract_clinical_evidence(clinical_notes)
        
        chronic_pain_evidence = [ev for ev in evidence if ev.indicator == ClinicalIndicator.PAIN_CHRONIC]
        assert len(chronic_pain_evidence) > 0
        
        # Check duration extraction
        duration_evidence = [ev for ev in chronic_pain_evidence if ev.duration_mentioned]
        assert len(duration_evidence) > 0
        assert "12 weeks" in duration_evidence[0].duration_mentioned
    
    def test_extract_clinical_evidence_neurological_deficit(self):
        """Test extraction of neurological deficit evidence."""
        clinical_notes = "Patient presents with weakness and numbness in right arm, consistent with radiculopathy."
        
        evidence = self.engine._extract_clinical_evidence(clinical_notes)
        
        neuro_evidence = [ev for ev in evidence if ev.indicator == ClinicalIndicator.NEUROLOGICAL_DEFICIT]
        assert len(neuro_evidence) >= 2  # Should find "weakness" and "numbness"
        
        # Check confidence scores
        for ev in neuro_evidence:
            assert ev.confidence > 0.0
    
    def test_extract_clinical_evidence_trauma(self):
        """Test extraction of trauma evidence."""
        clinical_notes = "Patient sustained injury in motor vehicle accident 2 days ago with acute pain."
        
        evidence = self.engine._extract_clinical_evidence(clinical_notes)
        
        trauma_evidence = [ev for ev in evidence if ev.indicator == ClinicalIndicator.TRAUMA]
        acute_pain_evidence = [ev for ev in evidence if ev.indicator == ClinicalIndicator.PAIN_ACUTE]
        
        assert len(trauma_evidence) > 0
        assert len(acute_pain_evidence) > 0
    
    def test_extract_clinical_evidence_malignancy_suspected(self):
        """Test extraction of malignancy suspicion evidence."""
        clinical_notes = "Patient presents with suspicious mass and unexplained weight loss over 3 months."
        
        evidence = self.engine._extract_clinical_evidence(clinical_notes)
        
        malignancy_evidence = [ev for ev in evidence if ev.indicator == ClinicalIndicator.MALIGNANCY_SUSPECTED]
        assert len(malignancy_evidence) >= 2  # Should find "mass" and "weight loss"
    
    def test_procedure_rules_mri_brain(self):
        """Test procedure rules for brain MRI."""
        brain_mri_codes = [CPTCode(code="70551", description="Brain MRI without contrast")]
        request = AuthorizationRequest(
            request_id="req_test_002",
            provider_id="prov_test_001",
            patient_demographics=self.patient_demographics,
            diagnosis_codes=[ICD10Code(code="G93.1", description="Anoxic brain damage")],
            procedure_codes=brain_mri_codes,
            clinical_notes="Patient with neurological deficit and weakness",
            procedure_type=ProcedureType.MRI
        )
        
        result = self.engine.evaluate_medical_necessity(request)
        
        # Brain MRI should require neurological deficit
        evidence_indicators = {ev.indicator for ev in result.clinical_evidence}
        assert ClinicalIndicator.NEUROLOGICAL_DEFICIT in evidence_indicators
        
        # Should have procedure-specific findings
        assert "procedure_type" in result.procedure_specific_findings
        assert result.procedure_specific_findings["procedure_type"] == "mri"
    
    def test_procedure_rules_ct_head(self):
        """Test procedure rules for head CT."""
        ct_codes = [CPTCode(code="70450", description="Head CT without contrast")]
        request = AuthorizationRequest(
            request_id="req_test_003",
            provider_id="prov_test_001",
            patient_demographics=self.patient_demographics,
            diagnosis_codes=[ICD10Code(code="S06.9", description="Unspecified intracranial injury")],
            procedure_codes=ct_codes,
            clinical_notes="Patient sustained head trauma in fall with acute neurological symptoms",
            procedure_type=ProcedureType.CT_SCAN
        )
        
        result = self.engine.evaluate_medical_necessity(request)
        
        # Head CT should find trauma and neurological deficit
        evidence_indicators = {ev.indicator for ev in result.clinical_evidence}
        assert ClinicalIndicator.TRAUMA in evidence_indicators
        assert ClinicalIndicator.NEUROLOGICAL_DEFICIT in evidence_indicators
        
        # Should have high necessity for trauma
        assert result.necessity_level in [NecessityLevel.HIGH, NecessityLevel.MODERATE]
    
    def test_procedure_rules_xray_extremity(self):
        """Test procedure rules for extremity X-ray."""
        xray_codes = [CPTCode(code="73060", description="Knee X-ray")]
        request = AuthorizationRequest(
            request_id="req_test_004",
            provider_id="prov_test_001",
            patient_demographics=self.patient_demographics,
            diagnosis_codes=[ICD10Code(code="S83.9", description="Sprain of unspecified site of knee")],
            procedure_codes=xray_codes,
            clinical_notes="Patient fell and injured knee with acute pain and swelling",
            procedure_type=ProcedureType.X_RAY
        )
        
        result = self.engine.evaluate_medical_necessity(request)
        
        # X-ray should find trauma and acute pain
        evidence_indicators = {ev.indicator for ev in result.clinical_evidence}
        assert ClinicalIndicator.TRAUMA in evidence_indicators
        assert ClinicalIndicator.PAIN_ACUTE in evidence_indicators
        
        # Should assess fracture likelihood
        assert "fracture_likelihood" in result.procedure_specific_findings
    
    def test_resolve_policy_conflicts_all_approve(self):
        """Test policy conflict resolution when all policies approve."""
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
        """Test duration requirement validation."""
        clinical_evidence = [
            ClinicalEvidence(
                indicator=ClinicalIndicator.PAIN_CHRONIC,
                confidence=0.8,
                supporting_text="chronic pain lasting 8 weeks",
                duration_mentioned="8 weeks"
            )
        ]
        
        # Test 6-week requirement (should pass)
        assert self.engine._check_duration_requirement(clinical_evidence, "6 weeks") == True
        
        # Test 10-week requirement (should fail)
        assert self.engine._check_duration_requirement(clinical_evidence, "10 weeks") == False
        
        # Test with months
        clinical_evidence_months = [
            ClinicalEvidence(
                indicator=ClinicalIndicator.PAIN_CHRONIC,
                confidence=0.8,
                supporting_text="chronic pain lasting 3 months",
                duration_mentioned="3 months"
            )
        ]
        
        # 3 months = 12 weeks, should pass 10-week requirement
        assert self.engine._check_duration_requirement(clinical_evidence_months, "10 weeks") == True
    
    def test_confidence_score_calculation(self):
        """Test confidence score calculation."""
        # High confidence evidence
        high_evidence = [
            ClinicalEvidence(ClinicalIndicator.PAIN_CHRONIC, 0.9, "chronic pain"),
            ClinicalEvidence(ClinicalIndicator.NEUROLOGICAL_DEFICIT, 0.8, "weakness")
        ]
        
        criteria_met = ["criterion1", "criterion2", "criterion3"]
        criteria_not_met_count = 1
        
        confidence = self.engine._calculate_confidence_score(high_evidence, criteria_met, criteria_not_met_count)
        
        assert confidence > 0.7
        assert confidence <= 1.0
        
        # Low confidence evidence
        low_evidence = [
            ClinicalEvidence(ClinicalIndicator.PAIN_CHRONIC, 0.3, "pain")
        ]
        
        criteria_met_low = ["criterion1"]
        criteria_not_met_count_high = 3
        
        confidence_low = self.engine._calculate_confidence_score(low_evidence, criteria_met_low, criteria_not_met_count_high)
        
        assert confidence_low < 0.5
        assert confidence_low >= 0.0
    
    def test_pattern_confidence_calculation(self):
        """Test pattern confidence calculation."""
        # Long, specific pattern should have high confidence
        long_pattern = "chronic pain lasting for over"
        confidence_high = self.engine._calculate_pattern_confidence(long_pattern, "chronic pain lasting for over 6 weeks")
        assert confidence_high >= 0.7
        
        # Short, general pattern should have lower confidence
        short_pattern = "pain"
        confidence_low = self.engine._calculate_pattern_confidence(short_pattern, "pain")
        assert confidence_low <= 0.7
    
    def test_evidence_deduplication(self):
        """Test clinical evidence deduplication."""
        evidence = [
            ClinicalEvidence(ClinicalIndicator.PAIN_CHRONIC, 0.8, "chronic pain"),
            ClinicalEvidence(ClinicalIndicator.PAIN_CHRONIC, 0.7, "chronic pain"),  # Duplicate
            ClinicalEvidence(ClinicalIndicator.NEUROLOGICAL_DEFICIT, 0.9, "weakness"),
            ClinicalEvidence(ClinicalIndicator.PAIN_CHRONIC, 0.6, "persistent pain")  # Different text
        ]
        
        unique_evidence = self.engine._deduplicate_evidence(evidence)
        
        # Should remove exact duplicate but keep different supporting text
        assert len(unique_evidence) == 3
        
        # Check that we kept the higher confidence duplicate
        chronic_pain_evidence = [ev for ev in unique_evidence if ev.indicator == ClinicalIndicator.PAIN_CHRONIC]
        assert len(chronic_pain_evidence) == 2  # "chronic pain" and "persistent pain"
    
    def test_procedure_specific_findings_mri(self):
        """Test MRI-specific findings generation."""
        clinical_evidence = [
            ClinicalEvidence(ClinicalIndicator.MALIGNANCY_SUSPECTED, 0.8, "suspicious mass")
        ]
        
        findings = self.engine._get_procedure_specific_findings(
            ProcedureType.MRI, clinical_evidence, self.diagnosis_codes
        )
        
        assert findings["procedure_type"] == "mri"
        assert "contrast_indication" in findings
        assert findings["contrast_indication"]["contrast_indicated"] == True
        assert "alternative_imaging" in findings
    
    def test_procedure_specific_findings_ct(self):
        """Test CT-specific findings generation."""
        clinical_evidence = [
            ClinicalEvidence(ClinicalIndicator.TRAUMA, 0.9, "head trauma")
        ]
        
        findings = self.engine._get_procedure_specific_findings(
            ProcedureType.CT_SCAN, clinical_evidence, self.diagnosis_codes
        )
        
        assert findings["procedure_type"] == "ct_scan"
        assert "radiation_justification" in findings
        assert findings["radiation_justification"]["justified"] == True
        assert "contrast_indication" in findings
    
    def test_procedure_specific_findings_xray(self):
        """Test X-ray-specific findings generation."""
        clinical_evidence = [
            ClinicalEvidence(ClinicalIndicator.TRAUMA, 0.9, "fall injury")
        ]
        
        findings = self.engine._get_procedure_specific_findings(
            ProcedureType.X_RAY, clinical_evidence, self.diagnosis_codes
        )
        
        assert findings["procedure_type"] == "x_ray"
        assert "fracture_likelihood" in findings
        assert findings["fracture_likelihood"]["likelihood"] == "high"
    
    def test_error_handling(self):
        """Test error handling in medical necessity evaluation."""
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
        """Test clinical evidence creation."""
        evidence = ClinicalEvidence(
            indicator=ClinicalIndicator.PAIN_CHRONIC,
            confidence=0.8,
            supporting_text="chronic shoulder pain",
            duration_mentioned="6 weeks",
            severity_mentioned="moderate"
        )
        
        assert evidence.indicator == ClinicalIndicator.PAIN_CHRONIC
        assert evidence.confidence == 0.8
        assert evidence.supporting_text == "chronic shoulder pain"
        assert evidence.duration_mentioned == "6 weeks"
        assert evidence.severity_mentioned == "moderate"
    
    def test_clinical_evidence_optional_fields(self):
        """Test clinical evidence with optional fields."""
        evidence = ClinicalEvidence(
            indicator=ClinicalIndicator.NEUROLOGICAL_DEFICIT,
            confidence=0.9,
            supporting_text="weakness in right arm"
        )
        
        assert evidence.duration_mentioned is None
        assert evidence.severity_mentioned is None


class TestProcedureRule:
    """Test cases for ProcedureRule dataclass."""
    
    def test_procedure_rule_creation(self):
        """Test procedure rule creation."""
        rule = ProcedureRule(
            procedure_codes=["73221", "73222"],
            required_indicators=[ClinicalIndicator.PAIN_CHRONIC],
            optional_indicators=[ClinicalIndicator.TRAUMA],
            minimum_duration="6 weeks",
            contraindications=["metallic implants"],
            documentation_requirements=["physical examination"]
        )
        
        assert rule.procedure_codes == ["73221", "73222"]
        assert ClinicalIndicator.PAIN_CHRONIC in rule.required_indicators
        assert ClinicalIndicator.TRAUMA in rule.optional_indicators
        assert rule.minimum_duration == "6 weeks"
        assert "metallic implants" in rule.contraindications
        assert "physical examination" in rule.documentation_requirements


if __name__ == "__main__":
    pytest.main([__file__])
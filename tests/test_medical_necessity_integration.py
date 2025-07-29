"""
Integration tests for medical necessity engine with policy validation.
"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime, date

from src.services.policy_validation import PolicyValidationService, PolicyValidationResult, PolicyType
from src.services.medical_necessity import MedicalNecessityEngine, NecessityLevel
from src.models.authorization import AuthorizationRequest
from src.models.patient import PatientDemographics
from src.models.medical_codes import ICD10Code, CPTCode
from src.models.enums import ProcedureType, UrgencyLevel, RequestStatus, Gender
from src.database.models import CoveragePolicyDB


class TestMedicalNecessityIntegration:
    """Integration tests for medical necessity with policy validation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Mock database session
        self.mock_db_session = Mock()
        
        # Create policy validation service
        self.policy_service = PolicyValidationService(self.mock_db_session)
        
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
    
    def create_sample_request(self, clinical_notes: str = None):
        """Create a sample authorization request."""
        return AuthorizationRequest(
            request_id="req_integration_001",
            provider_id="prov_test_001",
            patient_demographics=self.patient_demographics,
            diagnosis_codes=self.diagnosis_codes,
            procedure_codes=self.procedure_codes,
            clinical_notes=clinical_notes or "Patient with shoulder pain requiring MRI evaluation",
            procedure_type=ProcedureType.MRI,
            urgency_level=UrgencyLevel.ROUTINE,
            status=RequestStatus.SUBMITTED
        )
    
    def create_mock_policy(self):
        """Create a mock coverage policy."""
        return CoveragePolicyDB(
            policy_id="pol_test_001",
            payer_id="payer_001",
            procedure_code="73221",
            diagnosis_codes=["M25.511"],
            coverage_criteria={
                "age_range": {"min_age": 18, "max_age": 65},
                "medical_necessity": {
                    "required_symptoms": ["chronic pain", "functional impairment"],
                    "duration_requirements": "6 weeks minimum"
                }
            },
            policy_type="PAYER",
            policy_name="Upper Extremity MRI Policy",
            policy_version="1.0",
            effective_date=date.today(),
            expiration_date=None,
            is_active=True,
            created_by="system",
            updated_by="system"
        )
    
    @pytest.mark.asyncio
    async def test_comprehensive_validation_approve_scenario(self):
        """Test comprehensive validation with approval scenario."""
        # Setup mock policy query
        mock_policy = self.create_mock_policy()
        self.mock_db_session.query.return_value.filter.return_value.all.return_value = [mock_policy]
        
        # Create request with strong medical necessity
        clinical_notes = """
        Patient presents with chronic shoulder pain lasting 8 weeks.
        Functional impairment affecting daily activities.
        Conservative treatment with physical therapy has failed.
        Physical examination shows limited range of motion.
        """
        
        request = self.create_sample_request(clinical_notes)
        
        # Perform comprehensive validation
        result = await self.policy_service.validate_with_medical_necessity(request, "payer_001")
        
        # Verify result structure
        assert "policy_validation" in result
        assert "cms_compliance" in result
        assert "medical_necessity" in result
        assert "final_decision" in result
        
        # Verify policy validation
        policy_validation = result["policy_validation"]
        assert policy_validation["is_covered"] == True
        assert policy_validation["policy_id"] == "pol_test_001"
        
        # Verify medical necessity
        medical_necessity = result["medical_necessity"]
        assert medical_necessity["necessity_level"] in ["high", "moderate"]
        assert medical_necessity["confidence_score"] > 0.5
        assert len(medical_necessity["criteria_met"]) > 0
        
        # Verify final decision
        final_decision = result["final_decision"]
        assert final_decision["final_decision"] in ["approve", "request_info"]
        assert final_decision["confidence_score"] > 0.0
    
    @pytest.mark.asyncio
    async def test_comprehensive_validation_deny_scenario(self):
        """Test comprehensive validation with denial scenario."""
        # Setup mock policy that denies coverage
        mock_policy = self.create_mock_policy()
        mock_policy.coverage_criteria = {
            "age_range": {"min_age": 18, "max_age": 30},  # Patient is 45, outside range
            "medical_necessity": {
                "required_symptoms": ["acute trauma"],
                "duration_requirements": "immediate"
            }
        }
        self.mock_db_session.query.return_value.filter.return_value.all.return_value = [mock_policy]
        
        # Create request with insufficient medical necessity
        clinical_notes = "Patient requests MRI scan for shoulder discomfort."
        
        request = self.create_sample_request(clinical_notes)
        
        # Perform comprehensive validation
        result = await self.policy_service.validate_with_medical_necessity(request, "payer_001")
        
        # Verify denial
        policy_validation = result["policy_validation"]
        assert policy_validation["is_covered"] == False
        
        medical_necessity = result["medical_necessity"]
        assert medical_necessity["necessity_level"] in ["insufficient", "low"]
        
        final_decision = result["final_decision"]
        assert final_decision["final_decision"] == "deny"
    
    @pytest.mark.asyncio
    async def test_comprehensive_validation_request_info_scenario(self):
        """Test comprehensive validation with request for additional information."""
        # Setup mock policy that approves coverage
        mock_policy = self.create_mock_policy()
        self.mock_db_session.query.return_value.filter.return_value.all.return_value = [mock_policy]
        
        # Create request with moderate medical necessity but missing documentation
        clinical_notes = """
        Patient has shoulder pain for several weeks.
        Some limitation in movement noted.
        """
        
        request = self.create_sample_request(clinical_notes)
        
        # Perform comprehensive validation
        result = await self.policy_service.validate_with_medical_necessity(request, "payer_001")
        
        # Verify request for more information
        policy_validation = result["policy_validation"]
        assert policy_validation["is_covered"] == True
        
        medical_necessity = result["medical_necessity"]
        assert len(medical_necessity["additional_documentation_needed"]) > 0
        
        final_decision = result["final_decision"]
        # Could be either request_info or approve depending on confidence
        assert final_decision["final_decision"] in ["request_info", "approve"]
    
    @pytest.mark.asyncio
    async def test_comprehensive_validation_no_policies(self):
        """Test comprehensive validation when no policies are found."""
        # Setup mock to return no policies
        self.mock_db_session.query.return_value.filter.return_value.all.return_value = []
        
        request = self.create_sample_request()
        
        # Perform comprehensive validation
        result = await self.policy_service.validate_with_medical_necessity(request, "payer_001")
        
        # Verify denial due to no policies
        policy_validation = result["policy_validation"]
        assert policy_validation["is_covered"] == False
        assert "No applicable coverage policies found" in " ".join(policy_validation["reasoning"])
        
        final_decision = result["final_decision"]
        assert final_decision["final_decision"] == "deny"
        # The resolution method might be "most_restrictive_deny" when policy validation fails
        assert final_decision["resolution_method"] in ["no_policies", "most_restrictive_deny"]
    
    @pytest.mark.asyncio
    async def test_comprehensive_validation_error_handling(self):
        """Test error handling in comprehensive validation."""
        # Setup mock to raise an exception
        self.mock_db_session.query.side_effect = Exception("Database connection error")
        
        request = self.create_sample_request()
        
        # Perform comprehensive validation
        result = await self.policy_service.validate_with_medical_necessity(request, "payer_001")
        
        # Verify error handling - the system should still return a structured result
        # even when database errors occur, but with error information in the components
        assert "policy_validation" in result
        assert "cms_compliance" in result
        assert "final_decision" in result
        
        # Check that errors are captured in the component results
        policy_validation = result["policy_validation"]
        cms_compliance = result["cms_compliance"]
        
        # Should have error information in reasoning or compliance issues
        has_error_info = (
            any("Database connection error" in str(reason) for reason in policy_validation["reasoning"]) or
            any("Database connection error" in str(issue) for issue in cms_compliance["compliance_issues"])
        )
        assert has_error_info
        
        final_decision = result["final_decision"]
        assert final_decision["final_decision"] == "deny"
    
    def test_medical_necessity_engine_integration(self):
        """Test that medical necessity engine is properly integrated."""
        # Verify that the policy service has a medical necessity engine
        assert hasattr(self.policy_service, 'medical_necessity_engine')
        assert isinstance(self.policy_service.medical_necessity_engine, MedicalNecessityEngine)
        
        # Test direct medical necessity evaluation
        request = self.create_sample_request("Patient with chronic pain and functional impairment")
        
        necessity_result = self.policy_service.medical_necessity_engine.evaluate_medical_necessity(request)
        
        assert necessity_result.necessity_level in [NecessityLevel.HIGH, NecessityLevel.MODERATE, NecessityLevel.LOW, NecessityLevel.INSUFFICIENT]
        assert 0.0 <= necessity_result.confidence_score <= 1.0
        assert isinstance(necessity_result.clinical_evidence, list)
        assert isinstance(necessity_result.reasoning, list)
    
    def test_policy_conflict_resolution_integration(self):
        """Test policy conflict resolution integration."""
        # Create multiple conflicting policy results
        policy_results = [
            {
                "is_covered": True,
                "reasoning": ["Policy A approves coverage"],
                "confidence_score": 0.9,
                "policy_id": "pol_a",
                "policy_type": "PAYER",
                "coverage_criteria": {},
                "additional_requirements": []
            },
            {
                "is_covered": False,
                "reasoning": ["Policy B denies coverage - age restriction"],
                "confidence_score": 0.8,
                "policy_id": "pol_b",
                "policy_type": "NCD",
                "coverage_criteria": {},
                "additional_requirements": []
            }
        ]
        
        # Create medical necessity result
        request = self.create_sample_request("Patient with chronic pain")
        necessity_result = self.policy_service.medical_necessity_engine.evaluate_medical_necessity(request)
        
        # Test conflict resolution
        resolution = self.policy_service.medical_necessity_engine.resolve_policy_conflicts(
            policy_results, necessity_result
        )
        
        # Should deny due to most restrictive policy
        assert resolution["final_decision"] == "deny"
        assert resolution["resolution_method"] == "most_restrictive_deny"
        assert len(resolution["conflicts_detected"]) > 0
        assert resolution["conflicts_detected"][0]["type"] == "approval_conflict"


if __name__ == "__main__":
    pytest.main([__file__])
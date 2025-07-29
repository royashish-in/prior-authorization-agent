"""
Unit tests for the reasoning engine service.

Tests detailed reasoning generation, decision documentation,
and alternative procedure suggestions.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from src.services.reasoning import (
    ReasoningEngine, ReasoningCategory, ReasoningElement, DecisionDocumentation
)
from src.models.authorization import AuthorizationRequest, AuthorizationDecision
from src.models.patient import PatientDemographics
from src.models.medical_codes import ICD10Code, CPTCode
from src.models.enums import (
    DecisionStatus, ProcedureType, UrgencyLevel, RequestStatus, Gender
)
from src.services.validation import ValidationResult, ValidationError
from src.services.policy_validation import PolicyValidationResult, PolicyType


class TestReasoningEngine:
    """Test reasoning engine functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.reasoning_engine = ReasoningEngine()
        
        # Create test patient demographics
        self.test_patient = PatientDemographics(
            patient_id="enc_test_patient_001",
            age=45,
            gender=Gender.FEMALE,
            insurance_id="enc_test_insurance_001",
            member_id="enc_test_member_001"
        )
        
        # Create test authorization request
        self.test_request = AuthorizationRequest(
            request_id="req_test_001",
            provider_id="prov_test_001",
            patient_demographics=self.test_patient,
            diagnosis_codes=[
                ICD10Code(code="M25.511", description="Pain in right shoulder")
            ],
            procedure_codes=[
                CPTCode(code="73221", description="MRI upper extremity without contrast")
            ],
            clinical_notes="Patient reports persistent shoulder pain for 6 weeks following minor trauma. Conservative treatment with NSAIDs and physical therapy has provided minimal relief.",
            procedure_type=ProcedureType.MRI,
            urgency_level=UrgencyLevel.ROUTINE,
            status=RequestStatus.SUBMITTED
        )
        
        # Create test validation result
        self.test_validation_result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=["Minor formatting issue in clinical notes"],
            processing_time_ms=1500.0
        )
        
        # Create test policy result
        self.test_policy_result = PolicyValidationResult(
            is_covered=True,
            policy_id="POL_MRI_001",
            policy_type=PolicyType.PAYER,
            reasoning=["Shoulder MRI covered for persistent pain after 6 weeks conservative treatment"],
            confidence_score=0.9,
            policy_references=["Payer Policy IMG-001"],
            additional_requirements=[]
        )
    
    def test_generate_detailed_reasoning_comprehensive(self):
        """Test comprehensive detailed reasoning generation."""
        # Create comprehensive validation data
        comprehensive_validation = {
            'medical_necessity': {
                'necessity_level': 'high',
                'confidence_score': 0.85,
                'supporting_factors': [
                    'Persistent symptoms after conservative treatment',
                    'Adequate trial of physical therapy'
                ],
                'evaluation_factors': {
                    'conservative_treatment_duration': 6,
                    'symptom_severity': 'moderate'
                }
            },
            'cms_compliance': {
                'is_compliant': True,
                'ncd_policies': [
                    {
                        'policy_name': 'NCD 220.2 - Magnetic Resonance Imaging',
                        'is_compliant': True
                    }
                ],
                'lcd_policies': [
                    {
                        'policy_name': 'LCD L33721 - MRI Upper Extremity',
                        'is_compliant': True
                    }
                ]
            },
            'policy_validation': {
                'is_covered': True,
                'policy_id': 'POL_MRI_001',
                'reasoning': ['Coverage criteria met']
            }
        }
        
        # Generate detailed reasoning
        reasoning_elements = self.reasoning_engine.generate_detailed_reasoning(
            self.test_request,
            self.test_validation_result,
            self.test_policy_result,
            comprehensive_validation
        )
        
        # Verify reasoning elements were generated
        assert len(reasoning_elements) > 0
        
        # Check for different reasoning categories
        categories = [elem.category for elem in reasoning_elements]
        assert ReasoningCategory.MEDICAL_NECESSITY in categories
        assert ReasoningCategory.POLICY_COMPLIANCE in categories
        assert ReasoningCategory.CMS_GUIDELINES in categories
        
        # Verify medical necessity reasoning
        medical_elements = [
            elem for elem in reasoning_elements 
            if elem.category == ReasoningCategory.MEDICAL_NECESSITY
        ]
        assert len(medical_elements) > 0
        assert any('high medical necessity' in elem.statement.lower() for elem in medical_elements)
        
        # Verify policy compliance reasoning
        policy_elements = [
            elem for elem in reasoning_elements 
            if elem.category == ReasoningCategory.POLICY_COMPLIANCE
        ]
        assert len(policy_elements) > 0
        assert any('meets' in elem.statement.lower() for elem in policy_elements)
    
    def test_generate_detailed_reasoning_denial_case(self):
        """Test detailed reasoning generation for denial case."""
        # Create comprehensive validation data for denial
        comprehensive_validation = {
            'medical_necessity': {
                'necessity_level': 'low',
                'confidence_score': 0.3,
                'missing_factors': [
                    'Insufficient conservative treatment duration',
                    'No documentation of failed conservative therapy'
                ],
                'evaluation_factors': {
                    'conservative_treatment_duration': 2,  # Too short
                    'symptom_severity': 'mild'
                }
            },
            'cms_compliance': {
                'is_compliant': False,
                'compliance_issues': [
                    'Does not meet minimum conservative treatment duration requirement'
                ]
            }
        }
        
        # Generate detailed reasoning
        reasoning_elements = self.reasoning_engine.generate_detailed_reasoning(
            self.test_request,
            self.test_validation_result,
            None,  # No policy result
            comprehensive_validation
        )
        
        # Verify denial reasoning elements
        assert len(reasoning_elements) > 0
        
        # Check for medical necessity denial reasoning
        medical_elements = [
            elem for elem in reasoning_elements 
            if elem.category == ReasoningCategory.MEDICAL_NECESSITY
        ]
        assert any('insufficient' in elem.statement.lower() for elem in medical_elements)
        
        # Check for CMS compliance issues
        cms_elements = [
            elem for elem in reasoning_elements 
            if elem.category == ReasoningCategory.CMS_GUIDELINES
        ]
        assert any('does not comply' in elem.statement.lower() for elem in cms_elements)
    
    def test_create_decision_documentation(self):
        """Test creation of structured decision documentation."""
        # Create test decision
        decision = AuthorizationDecision(
            decision_id="dec_test_001",
            request_id="req_test_001",
            status=DecisionStatus.APPROVED,
            reasoning=[
                "Medical necessity established",
                "Policy requirements met"
            ],
            policy_references=["Payer Policy IMG-001", "CMS NCD 220.2"],
            authorization_number="auth_20240124_ABC123",
            valid_until=datetime.now(timezone.utc) + timedelta(days=30),
            confidence_score=0.9
        )
        
        # Create test reasoning elements
        reasoning_elements = [
            ReasoningElement(
                category=ReasoningCategory.MEDICAL_NECESSITY,
                statement="High medical necessity established",
                confidence_level="high"
            ),
            ReasoningElement(
                category=ReasoningCategory.POLICY_COMPLIANCE,
                statement="Request meets coverage policy requirements",
                policy_reference="POL_MRI_001",
                confidence_level="high"
            )
        ]
        
        # Create validation context
        validation_context = {
            'medical_necessity': {
                'necessity_level': 'high',
                'confidence_score': 0.85,
                'evaluation_factors': {
                    'conservative_treatment_duration': 6,
                    'symptom_severity': 'moderate'
                }
            }
        }
        
        # Create decision documentation
        documentation = self.reasoning_engine.create_decision_documentation(
            decision, self.test_request, reasoning_elements, validation_context
        )
        
        # Verify documentation structure
        assert isinstance(documentation, DecisionDocumentation)
        assert documentation.decision_id == "dec_test_001"
        assert documentation.request_id == "req_test_001"
        assert documentation.decision_status == DecisionStatus.APPROVED
        assert len(documentation.reasoning_elements) == 2
        assert len(documentation.policy_references) == 2
        
        # Verify clinical factors
        assert 'patient_age' in documentation.clinical_factors
        assert documentation.clinical_factors['patient_age'] == 45
        assert documentation.clinical_factors['procedure_type'] == 'mri'
        
        # Verify risk assessment
        assert 'risk_level' in documentation.risk_assessment
        assert 'risk_factors' in documentation.risk_assessment
        
        # Verify audit trail
        assert len(documentation.audit_trail) > 0
        assert any(event['event_type'] == 'request_submitted' for event in documentation.audit_trail)
        assert any(event['event_type'] == 'decision_generated' for event in documentation.audit_trail)
    
    def test_generate_alternative_procedures_mri_denial(self):
        """Test alternative procedure generation for MRI denial."""
        denial_reasons = [
            "Insufficient conservative treatment duration",
            "Medical necessity not established"
        ]
        
        # Generate alternatives
        alternatives = self.reasoning_engine.generate_alternative_procedures(
            self.test_request, denial_reasons
        )
        
        # Verify alternatives were generated
        assert len(alternatives) > 0
        
        # Check for expected alternative types
        alternative_codes = [alt['procedure_code'] for alt in alternatives]
        
        # Should include conservative alternatives
        assert any('conservative' in code for code in alternative_codes)
        assert any('physical_therapy' in code or 'specialist_consultation' in code for code in alternative_codes)
        
        # Verify alternative structure
        for alt in alternatives:
            assert 'procedure_code' in alt
            assert 'description' in alt
            assert 'rationale' in alt
            assert 'cost_impact' in alt
            assert 'clinical_appropriateness' in alt
    
    def test_generate_alternative_procedures_ct_denial(self):
        """Test alternative procedure generation for CT denial."""
        # Create CT request
        ct_request = AuthorizationRequest(
            request_id="req_ct_test_001",
            provider_id="prov_test_001",
            patient_demographics=self.test_patient,
            diagnosis_codes=[
                ICD10Code(code="S72.001A", description="Fracture of unspecified part of neck of right femur")
            ],
            procedure_codes=[
                CPTCode(code="74150", description="CT abdomen without contrast")
            ],
            procedure_type=ProcedureType.CT_SCAN,
            urgency_level=UrgencyLevel.ROUTINE
        )
        
        denial_reasons = ["Not medically necessary for this indication"]
        
        # Generate alternatives
        alternatives = self.reasoning_engine.generate_alternative_procedures(
            ct_request, denial_reasons
        )
        
        # Verify alternatives include X-ray and ultrasound options
        assert len(alternatives) > 0
        
        # Check for imaging alternatives
        descriptions = [alt['description'].lower() for alt in alternatives]
        assert any('x-ray' in desc or 'ultrasound' in desc for desc in descriptions)
    
    def test_generate_alternative_procedures_xray_case(self):
        """Test alternative procedure generation for X-ray case."""
        # Create X-ray request
        xray_request = AuthorizationRequest(
            request_id="req_xray_test_001",
            provider_id="prov_test_001",
            patient_demographics=self.test_patient,
            diagnosis_codes=[
                ICD10Code(code="M25.511", description="Pain in right shoulder")
            ],
            procedure_codes=[
                CPTCode(code="73030", description="X-ray shoulder")
            ],
            procedure_type=ProcedureType.X_RAY,
            urgency_level=UrgencyLevel.ROUTINE
        )
        
        denial_reasons = ["Clinical evaluation recommended first"]
        
        # Generate alternatives
        alternatives = self.reasoning_engine.generate_alternative_procedures(
            xray_request, denial_reasons
        )
        
        # X-ray alternatives should focus on conservative treatment
        assert len(alternatives) > 0
        
        # Should include clinical evaluation
        alternative_codes = [alt['procedure_code'] for alt in alternatives]
        assert 'clinical_evaluation' in alternative_codes
    
    def test_reasoning_element_creation(self):
        """Test ReasoningElement creation and validation."""
        element = ReasoningElement(
            category=ReasoningCategory.MEDICAL_NECESSITY,
            statement="Test reasoning statement",
            policy_reference="TEST_POLICY_001",
            confidence_level="high",
            supporting_evidence=["Evidence 1", "Evidence 2"]
        )
        
        assert element.category == ReasoningCategory.MEDICAL_NECESSITY
        assert element.statement == "Test reasoning statement"
        assert element.policy_reference == "TEST_POLICY_001"
        assert element.confidence_level == "high"
        assert len(element.supporting_evidence) == 2
    
    def test_reasoning_with_missing_clinical_notes(self):
        """Test reasoning generation when clinical notes are missing."""
        # Create request without clinical notes
        request_no_notes = AuthorizationRequest(
            request_id="req_no_notes_001",
            provider_id="prov_test_001",
            patient_demographics=self.test_patient,
            diagnosis_codes=[
                ICD10Code(code="M25.511", description="Pain in right shoulder")
            ],
            procedure_codes=[
                CPTCode(code="73221", description="MRI upper extremity without contrast")
            ],
            clinical_notes=None,  # No clinical notes
            procedure_type=ProcedureType.MRI,
            urgency_level=UrgencyLevel.ROUTINE
        )
        
        # Generate reasoning
        reasoning_elements = self.reasoning_engine.generate_detailed_reasoning(
            request_no_notes,
            self.test_validation_result,
            self.test_policy_result,
            None
        )
        
        # Should include documentation reasoning about missing notes
        documentation_elements = [
            elem for elem in reasoning_elements 
            if elem.category == ReasoningCategory.DOCUMENTATION
        ]
        
        assert len(documentation_elements) > 0
        assert any('no clinical notes' in elem.statement.lower() for elem in documentation_elements)
    
    def test_reasoning_with_validation_errors(self):
        """Test reasoning generation with validation errors."""
        # Create validation result with errors
        validation_with_errors = ValidationResult(
            is_valid=False,
            errors=[
                ValidationError(
                    field="diagnosis_codes",
                    message="Invalid ICD-10 code format",
                    value="INVALID_CODE"
                )
            ],
            warnings=[],
            processing_time_ms=2000.0
        )
        
        # Generate reasoning
        reasoning_elements = self.reasoning_engine.generate_detailed_reasoning(
            self.test_request,
            validation_with_errors,
            self.test_policy_result,
            None
        )
        
        # Should include documentation reasoning about validation errors
        documentation_elements = [
            elem for elem in reasoning_elements 
            if elem.category == ReasoningCategory.DOCUMENTATION
        ]
        
        assert len(documentation_elements) > 0
        assert any('validation issues' in elem.statement.lower() for elem in documentation_elements)
    
    def test_risk_assessment_high_risk_case(self):
        """Test risk assessment for high-risk scenarios."""
        # Create urgent request for elderly patient
        high_risk_patient = PatientDemographics(
            patient_id="enc_elderly_patient_001",
            age=75,  # Elderly
            gender=Gender.MALE,
            insurance_id="enc_test_insurance_002",
            member_id="enc_test_member_002"
        )
        
        urgent_request = AuthorizationRequest(
            request_id="req_urgent_001",
            provider_id="prov_test_001",
            patient_demographics=high_risk_patient,
            diagnosis_codes=[
                ICD10Code(code="G93.1", description="Anoxic brain damage, not elsewhere classified")
            ],
            procedure_codes=[
                CPTCode(code="70551", description="MRI brain without contrast")
            ],
            procedure_type=ProcedureType.MRI,
            urgency_level=UrgencyLevel.URGENT  # Urgent case
        )
        
        # Create decision with low confidence
        decision = AuthorizationDecision(
            decision_id="dec_urgent_001",
            request_id="req_urgent_001",
            status=DecisionStatus.DENIED,  # Denied despite urgency
            reasoning=["Test reasoning"],
            confidence_score=0.6  # Low confidence
        )
        
        reasoning_elements = [
            ReasoningElement(
                category=ReasoningCategory.MEDICAL_NECESSITY,
                statement="High medical necessity established",
                confidence_level="high"
            )
        ]
        
        # Create documentation to trigger risk assessment
        documentation = self.reasoning_engine.create_decision_documentation(
            decision, urgent_request, reasoning_elements, None
        )
        
        # Verify high risk assessment
        risk_assessment = documentation.risk_assessment
        assert risk_assessment['risk_level'] == 'high'
        assert risk_assessment['requires_peer_review'] is True
        assert risk_assessment['requires_expedited_processing'] is True
        
        # Should have multiple risk factors
        assert len(risk_assessment['risk_factors']) > 1
    
    @patch('src.services.reasoning.get_logger')
    def test_reasoning_engine_error_handling(self, mock_logger):
        """Test error handling in reasoning engine."""
        # Create mock logger
        mock_logger_instance = Mock()
        mock_logger.return_value = mock_logger_instance
        
        # Create reasoning engine
        reasoning_engine = ReasoningEngine()
        
        # Test with invalid request (should handle gracefully)
        invalid_request = None
        
        reasoning_elements = reasoning_engine.generate_detailed_reasoning(
            invalid_request,
            self.test_validation_result,
            self.test_policy_result,
            None
        )
        
        # Should return basic reasoning on error
        assert len(reasoning_elements) > 0
        assert reasoning_elements[0].category == ReasoningCategory.DOCUMENTATION
        assert 'system error' in reasoning_elements[0].statement.lower()
        
        # Verify error was logged
        mock_logger_instance.error.assert_called()
    
    def test_alternative_procedures_deduplication(self):
        """Test that alternative procedures are properly deduplicated."""
        # Create request that might generate duplicate alternatives
        request_with_multiple_codes = AuthorizationRequest(
            request_id="req_multi_001",
            provider_id="prov_test_001",
            patient_demographics=self.test_patient,
            diagnosis_codes=[
                ICD10Code(code="M25.511", description="Pain in right shoulder"),
                ICD10Code(code="M25.512", description="Pain in left shoulder")
            ],
            procedure_codes=[
                CPTCode(code="73221", description="MRI upper extremity without contrast"),
                CPTCode(code="73220", description="MRI upper extremity with contrast")
            ],
            procedure_type=ProcedureType.MRI,
            urgency_level=UrgencyLevel.ROUTINE
        )
        
        denial_reasons = ["Medical necessity not established"]
        
        # Generate alternatives
        alternatives = self.reasoning_engine.generate_alternative_procedures(
            request_with_multiple_codes, denial_reasons
        )
        
        # Verify no duplicates
        procedure_codes = [alt['procedure_code'] for alt in alternatives]
        assert len(procedure_codes) == len(set(procedure_codes))  # No duplicates
        
        # Should be limited to reasonable number
        assert len(alternatives) <= 5
    
    def test_clinical_notes_quality_assessment(self):
        """Test clinical notes quality assessment."""
        # Test high-quality notes
        high_quality_notes = "Patient reports severe shoulder pain for 8 weeks following motor vehicle accident. Has completed 6 weeks of physical therapy with minimal improvement. Currently taking ibuprofen 600mg TID with limited relief. Pain rated 7/10, interfering with sleep and work activities."
        
        quality_assessment = self.reasoning_engine._assess_clinical_notes_quality(high_quality_notes)
        
        assert quality_assessment['confidence'] == 'high'
        assert 'comprehensive' in quality_assessment['statement'].lower()
        assert len(quality_assessment['evidence']) >= 2
        
        # Test low-quality notes
        low_quality_notes = "Shoulder hurts"
        
        quality_assessment = self.reasoning_engine._assess_clinical_notes_quality(low_quality_notes)
        
        assert quality_assessment['confidence'] == 'moderate'
        assert 'limited' in quality_assessment['statement'].lower()
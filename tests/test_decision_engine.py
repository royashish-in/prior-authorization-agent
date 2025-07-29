"""
Unit tests for the decision engine service.

Tests decision generation logic, confidence scoring,
and integration with reasoning engine.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from src.services.decision_engine import DecisionEngine, DecisionContext
from src.services.reasoning import DecisionDocumentation, ReasoningElement, ReasoningCategory
from src.models.authorization import AuthorizationRequest, AuthorizationDecision
from src.models.patient import PatientDemographics
from src.models.medical_codes import ICD10Code, CPTCode
from src.models.enums import (
    DecisionStatus, ProcedureType, UrgencyLevel, RequestStatus, Gender
)
from src.services.validation import ValidationResult, ValidationError
from src.services.policy_validation import PolicyValidationResult, PolicyType


class TestDecisionEngine:
    """Test decision engine functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.decision_engine = DecisionEngine()
        
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
            clinical_notes="Patient reports persistent shoulder pain for 6 weeks following minor trauma.",
            procedure_type=ProcedureType.MRI,
            urgency_level=UrgencyLevel.ROUTINE,
            status=RequestStatus.SUBMITTED
        )
        
        # Create test validation result
        self.test_validation_result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=[],
            processing_time_ms=1500.0
        )
        
        # Create test policy result
        self.test_policy_result = PolicyValidationResult(
            is_covered=True,
            policy_id="POL_MRI_001",
            policy_type=PolicyType.PAYER,
            reasoning=["Shoulder MRI covered for persistent pain"],
            confidence_score=0.9,
            policy_references=["Payer Policy IMG-001"],
            additional_requirements=[]
        )
    
    def test_generate_decision_approval_case(self):
        """Test decision generation for approval case."""
        # Create comprehensive validation for approval
        comprehensive_validation = {
            'medical_necessity': {
                'necessity_level': 'high',
                'confidence_score': 0.9,
                'reasoning': ['Adequate conservative treatment trial', 'Persistent symptoms']
            },
            'cms_compliance': {
                'is_compliant': True,
                'ncd_policies': [{'policy_name': 'NCD 220.2', 'is_compliant': True}]
            },
            'policy_validation': {
                'is_covered': True,
                'policy_id': 'POL_MRI_001'
            }
        }
        
        # Generate decision
        decision = self.decision_engine.generate_decision(
            self.test_request,
            self.test_validation_result,
            self.test_policy_result,
            comprehensive_validation
        )
        
        # Verify approval decision
        assert decision.status == DecisionStatus.APPROVED
        assert decision.authorization_number is not None
        assert decision.authorization_number.startswith('auth_')
        assert decision.valid_until is not None
        assert decision.valid_until > datetime.now(timezone.utc)
        assert decision.confidence_score >= 0.8
        
        # Verify reasoning includes approval factors
        reasoning_text = ' '.join(decision.reasoning).lower()
        assert 'approval' in reasoning_text or 'meets' in reasoning_text
        
        # Verify policy references
        assert len(decision.policy_references) > 0
    
    def test_generate_decision_denial_case(self):
        """Test decision generation for denial case."""
        # Create comprehensive validation for denial
        comprehensive_validation = {
            'medical_necessity': {
                'necessity_level': 'low',
                'confidence_score': 0.3,
                'reasoning': ['Insufficient conservative treatment', 'Mild symptoms']
            },
            'cms_compliance': {
                'is_compliant': False,
                'compliance_issues': ['Does not meet duration requirements']
            },
            'policy_validation': {
                'is_covered': False,
                'policy_id': 'POL_MRI_001'
            }
        }
        
        # Generate decision
        decision = self.decision_engine.generate_decision(
            self.test_request,
            self.test_validation_result,
            None,  # No policy result for denial
            comprehensive_validation
        )
        
        # Verify denial decision
        assert decision.status == DecisionStatus.DENIED
        assert decision.authorization_number is None
        assert decision.valid_until is None
        assert decision.confidence_score >= 0.6
        
        # Verify reasoning includes denial factors
        reasoning_text = ' '.join(decision.reasoning).lower()
        assert 'denial' in reasoning_text or 'does not' in reasoning_text
        
        # Verify alternative procedures are provided
        assert decision.alternative_procedures is not None
        assert len(decision.alternative_procedures) > 0
    
    def test_generate_decision_more_info_needed(self):
        """Test decision generation for more info needed case."""
        # Create policy result with additional requirements
        policy_with_requirements = PolicyValidationResult(
            is_covered=True,
            policy_id="POL_MRI_001",
            policy_type=PolicyType.PAYER,
            reasoning=["Coverage available with additional documentation"],
            confidence_score=0.7,
            policy_references=["Payer Policy IMG-001"],
            additional_requirements=[
                "Physical therapy notes required",
                "Physician examination report needed"
            ]
        )
        
        # Create comprehensive validation with info needs
        comprehensive_validation = {
            'medical_necessity': {
                'necessity_level': 'moderate',
                'confidence_score': 0.6,
                'additional_documentation_needed': [
                    'Detailed physical therapy records',
                    'Specialist consultation report'
                ]
            },
            'cms_compliance': {
                'is_compliant': True,
                'recommendations': ['Consider additional imaging if conservative treatment fails']
            }
        }
        
        # Generate decision
        decision = self.decision_engine.generate_decision(
            self.test_request,
            self.test_validation_result,
            policy_with_requirements,
            comprehensive_validation
        )
        
        # Verify more info needed decision
        assert decision.status == DecisionStatus.MORE_INFO_NEEDED
        assert decision.authorization_number is None
        assert decision.valid_until is None
        
        # Verify additional info requirements
        assert decision.additional_info_needed is not None
        assert len(decision.additional_info_needed) > 0
        
        # Verify reasoning explains what's needed
        reasoning_text = ' '.join(decision.reasoning).lower()
        assert 'additional' in reasoning_text or 'required' in reasoning_text
    
    def test_generate_decision_with_detailed_reasoning(self):
        """Test decision generation with detailed reasoning and documentation."""
        # Create comprehensive validation
        comprehensive_validation = {
            'medical_necessity': {
                'necessity_level': 'high',
                'confidence_score': 0.85,
                'evaluation_factors': {
                    'conservative_treatment_duration': 6,
                    'symptom_severity': 'moderate'
                }
            },
            'cms_compliance': {
                'is_compliant': True
            },
            'policy_validation': {
                'is_covered': True,
                'policy_id': 'POL_MRI_001'
            }
        }
        
        # Generate decision with detailed reasoning
        decision, documentation = self.decision_engine.generate_decision_with_detailed_reasoning(
            self.test_request,
            self.test_validation_result,
            self.test_policy_result,
            comprehensive_validation
        )
        
        # Verify decision
        assert isinstance(decision, AuthorizationDecision)
        assert decision.status == DecisionStatus.APPROVED
        
        # Verify documentation
        assert isinstance(documentation, DecisionDocumentation)
        assert documentation.decision_id == decision.decision_id
        assert documentation.request_id == decision.request_id
        assert len(documentation.reasoning_elements) > 0
        
        # Verify reasoning elements have different categories
        categories = [elem.category for elem in documentation.reasoning_elements]
        assert len(set(categories)) > 1  # Multiple reasoning categories
        
        # Verify clinical factors
        assert 'patient_age' in documentation.clinical_factors
        assert 'procedure_type' in documentation.clinical_factors
        
        # Verify risk assessment
        assert 'risk_level' in documentation.risk_assessment
        assert 'risk_factors' in documentation.risk_assessment
        
        # Verify audit trail
        assert len(documentation.audit_trail) > 0
    
    def test_calculate_confidence_score(self):
        """Test confidence score calculation."""
        # Test with high-quality validation results
        high_quality_validations = [
            ValidationResult(is_valid=True, errors=[], warnings=[], processing_time_ms=1.0),
            ValidationResult(is_valid=True, errors=[], warnings=[], processing_time_ms=1.2)
        ]
        
        high_quality_policies = [
            PolicyValidationResult(
                is_covered=True,
                policy_id="POL_001",
                policy_type=PolicyType.PAYER,
                reasoning=["Clear coverage"],
                confidence_score=0.9,
                policy_references=[],
                additional_requirements=[]
            )
        ]
        
        confidence = self.decision_engine.calculate_confidence_score(
            high_quality_validations,
            high_quality_policies,
            medical_necessity_score=0.9
        )
        
        assert 0.8 <= confidence <= 1.0
        
        # Test with low-quality validation results
        low_quality_validations = [
            ValidationResult(
                is_valid=False,
                errors=[ValidationError("test", "Test error", "TEST_ERROR")],
                warnings=["Warning 1", "Warning 2"],
                processing_time_ms=5.0
            )
        ]
        
        low_quality_policies = [
            PolicyValidationResult(
                is_covered=False,
                policy_id="POL_001",
                policy_type=PolicyType.PAYER,
                reasoning=["Not covered"],
                confidence_score=0.3,
                policy_references=[],
                additional_requirements=[]
            )
        ]
        
        confidence = self.decision_engine.calculate_confidence_score(
            low_quality_validations,
            low_quality_policies,
            medical_necessity_score=0.2
        )
        
        assert 0.0 <= confidence <= 0.5
    
    def test_decision_id_generation(self):
        """Test decision ID generation format."""
        decision_id = self.decision_engine._generate_decision_id()
        
        assert decision_id.startswith('dec_')
        assert len(decision_id) > 10  # Should have timestamp and unique component
        
        # Generate multiple IDs to ensure uniqueness
        ids = [self.decision_engine._generate_decision_id() for _ in range(5)]
        assert len(set(ids)) == 5  # All unique
    
    def test_authorization_number_generation(self):
        """Test authorization number generation format."""
        auth_number = self.decision_engine._generate_authorization_number()
        
        assert auth_number.startswith('auth_')
        assert len(auth_number) > 15  # Should have date and unique component
        
        # Generate multiple numbers to ensure uniqueness
        numbers = [self.decision_engine._generate_authorization_number() for _ in range(5)]
        assert len(set(numbers)) == 5  # All unique
    
    def test_decision_with_validation_errors(self):
        """Test decision generation when validation fails."""
        # Create validation result with errors
        validation_with_errors = ValidationResult(
            is_valid=False,
            errors=[
                ValidationError("diagnosis_codes", "Invalid ICD-10 code", "INVALID_CODE"),
                ValidationError("procedure_codes", "Invalid CPT code", "INVALID_CODE")
            ],
            warnings=[],
            processing_time_ms=2.0
        )
        
        # Generate decision
        decision = self.decision_engine.generate_decision(
            self.test_request,
            validation_with_errors,
            self.test_policy_result,
            None
        )
        
        # Should be denied due to validation failure
        assert decision.status == DecisionStatus.DENIED
        assert decision.authorization_number is None
        assert decision.confidence_score >= 0.8  # High confidence in denial for validation errors
        
        # Reasoning should mention validation failure
        reasoning_text = ' '.join(decision.reasoning).lower()
        assert 'validation' in reasoning_text and 'failed' in reasoning_text
    
    def test_decision_context_creation(self):
        """Test DecisionContext creation and usage."""
        context = DecisionContext(
            request=self.test_request,
            validation_result=self.test_validation_result,
            policy_result=self.test_policy_result
        )
        
        assert context.request == self.test_request
        assert context.validation_result == self.test_validation_result
        assert context.policy_result == self.test_policy_result
        assert context.cms_compliance is None
        assert context.medical_necessity is None
    
    def test_error_decision_generation(self):
        """Test error decision generation for system failures."""
        error_message = "Database connection failed"
        
        error_decision = self.decision_engine._generate_error_decision(
            self.test_request, error_message
        )
        
        assert error_decision.status == DecisionStatus.DENIED
        assert error_decision.confidence_score == 0.9
        assert error_decision.authorization_number is None
        
        # Should mention system error in reasoning
        reasoning_text = ' '.join(error_decision.reasoning).lower()
        assert 'system error' in reasoning_text
        assert error_message.lower() in reasoning_text
        
        # Should suggest contacting support
        assert error_decision.alternative_procedures is not None
        alternatives_text = ' '.join(error_decision.alternative_procedures).lower()
        assert 'support' in alternatives_text
    
    def test_policy_reference_collection(self):
        """Test collection of policy references from various sources."""
        # Create comprehensive validation with multiple policy sources
        comprehensive_validation = {
            'cms_compliance': {
                'ncd_policies': [
                    {'policy_name': 'NCD 220.2 - Magnetic Resonance Imaging'},
                    {'policy_name': 'NCD 220.1 - Computed Tomography'}
                ],
                'lcd_policies': [
                    {'policy_name': 'LCD L33721 - MRI Upper Extremity'}
                ]
            }
        }
        
        # Create decision context
        context = DecisionContext(
            request=self.test_request,
            validation_result=self.test_validation_result,
            policy_result=self.test_policy_result,
            cms_compliance=comprehensive_validation['cms_compliance']
        )
        
        # Collect policy references
        references = self.decision_engine._collect_policy_references(context)
        
        # Should include payer policy and CMS policies
        assert len(references) >= 3
        assert any('Payer Policy IMG-001' in ref for ref in references)
        assert any('CMS NCD: NCD 220.2' in ref for ref in references)
        assert any('CMS LCD: LCD L33721' in ref for ref in references)
    
    def test_additional_info_requirements_generation(self):
        """Test generation of additional information requirements."""
        # Create policy result with requirements
        policy_with_requirements = PolicyValidationResult(
            is_covered=True,
            policy_id="POL_MRI_001",
            policy_type=PolicyType.PAYER,
            reasoning=["Coverage available"],
            confidence_score=0.8,
            policy_references=[],
            additional_requirements=["Physical therapy notes", "Specialist report"]
        )
        
        # Create comprehensive validation with additional needs
        comprehensive_validation = {
            'cms_compliance': {
                'recommendations': ['Consider MRI if conservative treatment fails']
            },
            'medical_necessity': {
                'additional_documentation_needed': ['Detailed symptom history']
            }
        }
        
        # Create decision context
        context = DecisionContext(
            request=self.test_request,
            validation_result=self.test_validation_result,
            policy_result=policy_with_requirements,
            cms_compliance=comprehensive_validation['cms_compliance'],
            medical_necessity=comprehensive_validation['medical_necessity']
        )
        
        # Generate additional info requirements
        requirements = self.decision_engine._generate_additional_info_requirements(context)
        
        # Should include requirements from all sources
        assert len(requirements) >= 3
        assert 'Physical therapy notes' in requirements
        assert 'Specialist report' in requirements
        assert 'Detailed symptom history' in requirements
    
    @patch('src.services.decision_engine.get_logger')
    def test_decision_engine_error_handling(self, mock_logger):
        """Test error handling in decision engine."""
        # Create mock logger
        mock_logger_instance = Mock()
        mock_logger.return_value = mock_logger_instance
        
        # Create decision engine
        decision_engine = DecisionEngine()
        
        # Test with None request (should handle gracefully)
        decision = decision_engine.generate_decision(
            None,  # Invalid request
            self.test_validation_result,
            self.test_policy_result,
            None
        )
        
        # Should return error decision
        assert decision.status == DecisionStatus.DENIED
        reasoning_text = ' '.join(decision.reasoning).lower()
        assert 'system error' in reasoning_text
        
        # Verify error was logged
        mock_logger_instance.error.assert_called()
    
    def test_decision_factors_resolution_edge_cases(self):
        """Test decision factor resolution for edge cases."""
        # Test case with equal approval and denial factors
        approval_factors = ["Factor A", "Factor B"]
        denial_factors = []  # No denial factors
        info_needed_factors = ["Info 1", "Info 2", "Info 3"]  # Many info factors
        base_reasoning = ["Base reasoning"]
        
        status, reasoning, confidence = self.decision_engine._resolve_decision_factors(
            approval_factors, denial_factors, info_needed_factors, base_reasoning
        )
        
        # Should request more info due to many info factors
        assert status == DecisionStatus.MORE_INFO_NEEDED
        assert len(reasoning) > len(base_reasoning)
        assert 0.5 <= confidence <= 1.0
        
        # Test case with denial factors (should override everything)
        denial_factors = ["Critical denial factor"]
        
        status, reasoning, confidence = self.decision_engine._resolve_decision_factors(
            approval_factors, denial_factors, info_needed_factors, base_reasoning
        )
        
        # Should deny regardless of other factors
        assert status == DecisionStatus.DENIED
        assert any('denial reason' in reason.lower() for reason in reasoning)
        assert confidence >= 0.7
    
    def test_comprehensive_validation_extraction(self):
        """Test extraction of policy result from comprehensive validation."""
        comprehensive_validation = {
            'policy_validation': {
                'is_covered': True,
                'policy_id': 'POL_TEST_001',
                'policy_type': 'PAYER',
                'reasoning': ['Test reasoning'],
                'confidence_score': 0.85,
                'policy_references': ['Test Policy'],
                'additional_requirements': ['Test requirement']
            }
        }
        
        # Extract policy result
        policy_result = self.decision_engine._extract_policy_result_from_comprehensive(
            comprehensive_validation['policy_validation']
        )
        
        assert policy_result is not None
        assert policy_result.is_covered is True
        assert policy_result.policy_id == 'POL_TEST_001'
        assert policy_result.policy_type == PolicyType.PAYER
        assert policy_result.confidence_score == 0.85
        assert len(policy_result.reasoning) == 1
        assert len(policy_result.additional_requirements) == 1
    
    def test_decision_timing_and_performance(self):
        """Test decision generation timing and performance characteristics."""
        import time
        
        # Measure decision generation time
        start_time = time.time()
        
        decision = self.decision_engine.generate_decision(
            self.test_request,
            self.test_validation_result,
            self.test_policy_result,
            None
        )
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Decision should be generated quickly (under 1 second for simple case)
        assert processing_time < 1.0
        
        # Decision should have proper timestamp
        assert decision.decided_at is not None
        assert isinstance(decision.decided_at, datetime)
        
        # Decision timestamp should be recent
        from src.core.datetime_utils import utcnow
        time_diff = utcnow() - decision.decided_at
        assert time_diff.total_seconds() < 5.0  # Within 5 seconds
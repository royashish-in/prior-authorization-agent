"""
Standardized test fixtures and mock configurations for coverage testing.

This module provides consistent test data and mocks specifically designed
for the coverage improvement tests to ensure reliable and repeatable results.
"""

import pytest
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from unittest.mock import Mock, AsyncMock, patch
from dataclasses import dataclass

from src.models.authorization import AuthorizationRequest, AuthorizationDecision
from src.models.patient import PatientDemographics
from src.models.medical_codes import ICD10Code, CPTCode, HCPCSCode
from src.models.enums import (
    RequestStatus, DecisionStatus, UrgencyLevel, Gender, ProcedureType
)
from src.services.validation import ValidationResult, ValidationError
from src.auth.models import TokenData, UserRole


@dataclass
class CoverageTestScenario:
    """Test scenario specifically designed for coverage testing."""
    name: str
    description: str
    input_data: Dict[str, Any]
    expected_outcome: Any
    mock_configurations: Dict[str, Any]
    coverage_target_modules: List[str]


class CoverageTestFixtures:
    """Centralized test fixtures for coverage improvement tests."""
    
    @staticmethod
    def get_comprehensive_patient_demographics() -> List[PatientDemographics]:
        """Get diverse patient demographics for comprehensive testing."""
        return [
            PatientDemographics(
                patient_id="enc_pat_coverage_001",
                age=25,
                gender=Gender.MALE,
                insurance_id="enc_ins_coverage_001",
                member_id="enc_mem_coverage_001"
            ),
            PatientDemographics(
                patient_id="enc_pat_coverage_002",
                age=45,
                gender=Gender.FEMALE,
                insurance_id="enc_ins_coverage_002",
                member_id="enc_mem_coverage_002"
            ),
            PatientDemographics(
                patient_id="enc_pat_coverage_003",
                age=65,
                gender=Gender.OTHER,
                insurance_id="enc_ins_coverage_003",
                member_id="enc_mem_coverage_003"
            ),
            PatientDemographics(
                patient_id="enc_pat_coverage_004",
                age=80,
                gender=Gender.FEMALE,
                insurance_id="enc_ins_coverage_004",
                member_id="enc_mem_coverage_004"
            )
        ]
    
    @staticmethod
    def get_comprehensive_medical_codes() -> Dict[str, List]:
        """Get comprehensive medical codes for testing various scenarios."""
        return {
            "icd10_codes": [
                ICD10Code(code="M25.511", description="Pain in right shoulder"),
                ICD10Code(code="M25.512", description="Pain in left shoulder"),
                ICD10Code(code="G93.1", description="Anoxic brain damage, not elsewhere classified"),
                ICD10Code(code="M54.5", description="Low back pain"),
                ICD10Code(code="S72.001A", description="Fracture of unspecified part of neck of right femur"),
                ICD10Code(code="I25.10", description="Atherosclerotic heart disease of native coronary artery"),
                ICD10Code(code="E11.9", description="Type 2 diabetes mellitus without complications"),
                ICD10Code(code="J44.1", description="Chronic obstructive pulmonary disease with acute exacerbation"),
                ICD10Code(code="N18.6", description="End stage renal disease"),
                ICD10Code(code="C78.00", description="Secondary malignant neoplasm of unspecified lung")
            ],
            "cpt_codes": [
                CPTCode(code="70553", description="MRI brain without and with contrast"),
                CPTCode(code="73221", description="MRI upper extremity without contrast"),
                CPTCode(code="73222", description="MRI upper extremity with contrast"),
                CPTCode(code="72128", description="CT lumbar spine without contrast"),
                CPTCode(code="72148", description="MRI lumbar spine without contrast"),
                CPTCode(code="71250", description="CT chest without contrast"),
                CPTCode(code="74177", description="CT abdomen and pelvis with contrast"),
                CPTCode(code="76700", description="Ultrasound abdomen complete"),
                CPTCode(code="93306", description="Echocardiography complete"),
                CPTCode(code="99213", description="Office visit established patient")
            ],
            "hcpcs_codes": [
                HCPCSCode(code="G0202", description="Screening mammography"),
                HCPCSCode(code="G0204", description="Diagnostic mammography"),
                HCPCSCode(code="G0206", description="Diagnostic mammography including CAD"),
                HCPCSCode(code="A4253", description="Blood glucose test strips"),
                HCPCSCode(code="E0601", description="Continuous positive airway pressure device")
            ]
        }
    
    @staticmethod
    def get_decision_engine_test_scenarios() -> List[CoverageTestScenario]:
        """Get test scenarios specifically for decision engine coverage."""
        return [
            CoverageTestScenario(
                name="routine_mri_approval",
                description="Routine MRI request that should be approved",
                input_data={
                    "diagnosis_codes": ["M25.511"],
                    "procedure_codes": ["73221"],
                    "urgency": UrgencyLevel.ROUTINE,
                    "clinical_notes": "Patient reports persistent shoulder pain for 6 weeks"
                },
                expected_outcome=DecisionStatus.APPROVED,
                mock_configurations={
                    "policy_validation": {"is_covered": True, "confidence": 0.9},
                    "medical_necessity": {"meets_criteria": True, "score": 0.85},
                    "llm_service": {"available": True, "confidence": 0.92}
                },
                coverage_target_modules=["src.services.decision_engine", "src.services.policy_validation"]
            ),
            CoverageTestScenario(
                name="emergent_brain_mri_approval",
                description="Emergent brain MRI that should be fast-tracked",
                input_data={
                    "diagnosis_codes": ["G93.1"],
                    "procedure_codes": ["70553"],
                    "urgency": UrgencyLevel.EMERGENT,
                    "clinical_notes": "Patient with acute neurological symptoms"
                },
                expected_outcome=DecisionStatus.APPROVED,
                mock_configurations={
                    "policy_validation": {"is_covered": True, "confidence": 0.95},
                    "medical_necessity": {"meets_criteria": True, "score": 0.98},
                    "llm_service": {"available": True, "confidence": 0.96}
                },
                coverage_target_modules=["src.services.decision_engine", "src.services.medical_necessity"]
            ),
            CoverageTestScenario(
                name="insufficient_info_request",
                description="Request requiring additional information",
                input_data={
                    "diagnosis_codes": ["M54.5"],
                    "procedure_codes": ["72148"],
                    "urgency": UrgencyLevel.ROUTINE,
                    "clinical_notes": "Back pain"
                },
                expected_outcome=DecisionStatus.MORE_INFO_NEEDED,
                mock_configurations={
                    "policy_validation": {"is_covered": True, "confidence": 0.7},
                    "medical_necessity": {"meets_criteria": False, "score": 0.4},
                    "llm_service": {"available": True, "confidence": 0.6}
                },
                coverage_target_modules=["src.services.decision_engine", "src.services.validation"]
            ),
            CoverageTestScenario(
                name="denied_request_invalid_code",
                description="Request denied due to invalid medical code",
                input_data={
                    "diagnosis_codes": ["INVALID123"],
                    "procedure_codes": ["73221"],
                    "urgency": UrgencyLevel.ROUTINE,
                    "clinical_notes": "Shoulder pain"
                },
                expected_outcome=DecisionStatus.DENIED,
                mock_configurations={
                    "policy_validation": {"is_covered": False, "confidence": 0.0},
                    "medical_necessity": {"meets_criteria": False, "score": 0.0},
                    "llm_service": {"available": True, "confidence": 0.1}
                },
                coverage_target_modules=["src.services.decision_engine", "src.services.validation"]
            ),
            CoverageTestScenario(
                name="llm_service_fallback",
                description="Test fallback when LLM service is unavailable",
                input_data={
                    "diagnosis_codes": ["M25.511"],
                    "procedure_codes": ["73221"],
                    "urgency": UrgencyLevel.ROUTINE,
                    "clinical_notes": "Shoulder pain with limited range of motion"
                },
                expected_outcome=DecisionStatus.APPROVED,
                mock_configurations={
                    "policy_validation": {"is_covered": True, "confidence": 0.9},
                    "medical_necessity": {"meets_criteria": True, "score": 0.85},
                    "llm_service": {"available": False, "error": "Service unavailable"}
                },
                coverage_target_modules=["src.services.decision_engine", "src.services.llm_decision_service"]
            )
        ]
    
    @staticmethod
    def get_api_endpoint_test_scenarios() -> List[CoverageTestScenario]:
        """Get test scenarios for API endpoint coverage."""
        return [
            CoverageTestScenario(
                name="valid_authorization_request",
                description="Valid authorization request submission",
                input_data={
                    "patient_demographics": {
                        "patient_id": "enc_pat_api_001",
                        "age": 45,
                        "gender": "FEMALE"
                    },
                    "diagnosis_codes": ["M25.511"],
                    "procedure_codes": ["73221"],
                    "clinical_notes": "Persistent shoulder pain"
                },
                expected_outcome={"status": "submitted", "request_id": "req_api_001"},
                mock_configurations={
                    "validation_service": {"is_valid": True},
                    "decision_engine": {"status": "processing"}
                },
                coverage_target_modules=["src.api.intake", "src.api.llm_decisions"]
            ),
            CoverageTestScenario(
                name="invalid_request_validation_error",
                description="Request with validation errors",
                input_data={
                    "patient_demographics": {
                        "patient_id": "",  # Invalid empty ID
                        "age": -1,  # Invalid age
                        "gender": "INVALID"  # Invalid gender
                    },
                    "diagnosis_codes": [],  # Empty codes
                    "procedure_codes": ["INVALID"],
                    "clinical_notes": ""
                },
                expected_outcome={"status": "validation_error", "errors": []},
                mock_configurations={
                    "validation_service": {"is_valid": False, "errors": ["Invalid patient ID", "Invalid age"]}
                },
                coverage_target_modules=["src.api.intake", "src.services.validation"]
            ),
            CoverageTestScenario(
                name="bulk_request_processing",
                description="Processing multiple requests simultaneously",
                input_data={
                    "requests": [
                        {"patient_id": f"enc_pat_bulk_{i}", "diagnosis_codes": ["M25.511"], "procedure_codes": ["73221"]}
                        for i in range(5)
                    ]
                },
                expected_outcome={"processed": 5, "status": "completed"},
                mock_configurations={
                    "validation_service": {"is_valid": True},
                    "decision_engine": {"batch_processing": True}
                },
                coverage_target_modules=["src.api.intake", "src.services.parallel_processing"]
            )
        ]
    
    @staticmethod
    def get_service_layer_test_scenarios() -> List[CoverageTestScenario]:
        """Get test scenarios for service layer coverage."""
        return [
            CoverageTestScenario(
                name="comprehensive_validation",
                description="Comprehensive validation of all fields",
                input_data={
                    "request": {
                        "patient_demographics": {"patient_id": "enc_pat_val_001", "age": 45},
                        "diagnosis_codes": ["M25.511", "M25.512"],
                        "procedure_codes": ["73221", "73222"],
                        "clinical_notes": "Bilateral shoulder pain with imaging history"
                    }
                },
                expected_outcome={"is_valid": True, "warnings": [], "errors": []},
                mock_configurations={
                    "medical_code_validator": {"all_valid": True},
                    "business_rule_validator": {"passes": True}
                },
                coverage_target_modules=["src.services.validation", "src.services.medical_code_validator"]
            ),
            CoverageTestScenario(
                name="tracking_service_workflow",
                description="Complete request tracking workflow",
                input_data={
                    "request_id": "req_track_001",
                    "status_updates": ["submitted", "processing", "approved"],
                    "notifications": ["provider", "patient"]
                },
                expected_outcome={"tracking_complete": True, "audit_entries": 3},
                mock_configurations={
                    "database_session": {"commit_success": True},
                    "notification_service": {"send_success": True}
                },
                coverage_target_modules=["src.services.tracking", "src.services.notification"]
            )
        ]
    
    @staticmethod
    def get_mock_configurations() -> Dict[str, Any]:
        """Get standardized mock configurations for coverage tests."""
        return {
            "database_session": {
                "query": Mock(return_value=Mock(filter=Mock(return_value=Mock(first=Mock(return_value=None))))),
                "add": Mock(),
                "commit": Mock(),
                "rollback": Mock(),
                "close": Mock()
            },
            "redis_client": {
                "get": Mock(return_value=None),
                "set": Mock(return_value=True),
                "delete": Mock(return_value=1),
                "exists": Mock(return_value=False)
            },
            "external_services": {
                "cms_api": {
                    "get_guidelines": Mock(return_value={"status": "success", "guidelines": "Test guidelines"}),
                    "validate_code": Mock(return_value={"valid": True, "description": "Valid code"})
                },
                "medical_codes_api": {
                    "lookup_icd10": Mock(return_value={"found": True, "description": "Test description"}),
                    "lookup_cpt": Mock(return_value={"found": True, "description": "Test procedure"})
                }
            },
            "llm_service": {
                "generate_decision": AsyncMock(return_value={
                    "decision": "approved",
                    "reasoning": "Meets medical necessity criteria",
                    "confidence": 0.9
                }),
                "is_available": Mock(return_value=True),
                "health_check": AsyncMock(return_value={"status": "healthy"})
            },
            "notification_service": {
                "send_email": AsyncMock(return_value=True),
                "send_dashboard_alert": AsyncMock(return_value=True),
                "send_sms": AsyncMock(return_value=True)
            },
            "audit_logger": {
                "log_event": Mock(),
                "log_security_event": Mock(),
                "log_phi_access": Mock()
            },
            "encryption_service": {
                "encrypt": Mock(return_value="encrypted_data"),
                "decrypt": Mock(return_value="decrypted_data"),
                "generate_key": Mock(return_value="test_key")
            }
        }


@pytest.fixture
def coverage_test_fixtures():
    """Provide coverage test fixtures."""
    return CoverageTestFixtures()


@pytest.fixture
def decision_engine_scenarios(coverage_test_fixtures):
    """Provide decision engine test scenarios."""
    return coverage_test_fixtures.get_decision_engine_test_scenarios()


@pytest.fixture
def api_endpoint_scenarios(coverage_test_fixtures):
    """Provide API endpoint test scenarios."""
    return coverage_test_fixtures.get_api_endpoint_test_scenarios()


@pytest.fixture
def service_layer_scenarios(coverage_test_fixtures):
    """Provide service layer test scenarios."""
    return coverage_test_fixtures.get_service_layer_test_scenarios()


@pytest.fixture
def comprehensive_medical_codes(coverage_test_fixtures):
    """Provide comprehensive medical codes for testing."""
    return coverage_test_fixtures.get_comprehensive_medical_codes()


@pytest.fixture
def comprehensive_patient_demographics(coverage_test_fixtures):
    """Provide diverse patient demographics."""
    return coverage_test_fixtures.get_comprehensive_patient_demographics()


@pytest.fixture
def standardized_mocks(coverage_test_fixtures):
    """Provide standardized mock configurations."""
    return coverage_test_fixtures.get_mock_configurations()


@pytest.fixture
def coverage_optimized_db_session():
    """Provide optimized database session for coverage tests."""
    from unittest.mock import Mock
    
    # Create a mock session optimized for coverage testing
    session = Mock()
    
    # Mock common database operations
    session.query.return_value.filter.return_value.first.return_value = None
    session.query.return_value.filter.return_value.all.return_value = []
    session.query.return_value.count.return_value = 0
    session.add.return_value = None
    session.commit.return_value = None
    session.rollback.return_value = None
    session.close.return_value = None
    
    # Mock transaction context
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock(return_value=None)
    
    return session


@pytest.fixture
def coverage_test_user():
    """Provide test user for coverage tests."""
    return TokenData(
        user_id="coverage_test_user_001",
        username="coverage_test_provider",
        roles=[UserRole.PROVIDER, UserRole.ADMIN],
        organization_id="coverage_test_org_001",
        exp=datetime.now(timezone.utc) + timedelta(hours=24),
        iat=datetime.now(timezone.utc)
    )


@pytest.fixture
def coverage_performance_timer():
    """Provide performance timer for coverage tests."""
    import time
    
    class CoverageTimer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
        
        def start(self):
            self.start_time = time.time()
        
        def stop(self):
            self.end_time = time.time()
        
        @property
        def elapsed(self):
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return 0
    
    return CoverageTimer()


class CoverageTestHelper:
    """Helper utilities for coverage testing."""
    
    @staticmethod
    def create_authorization_request_variants(base_request: Dict) -> List[Dict]:
        """Create multiple variants of an authorization request for comprehensive testing."""
        variants = []
        
        # Base variant
        variants.append(base_request.copy())
        
        # Variant with different urgency levels
        for urgency in [UrgencyLevel.ROUTINE, UrgencyLevel.URGENT, UrgencyLevel.EMERGENT]:
            variant = base_request.copy()
            variant["urgency_level"] = urgency
            variants.append(variant)
        
        # Variant with multiple diagnosis codes
        variant = base_request.copy()
        variant["diagnosis_codes"] = ["M25.511", "M25.512", "M54.5"]
        variants.append(variant)
        
        # Variant with multiple procedure codes
        variant = base_request.copy()
        variant["procedure_codes"] = ["73221", "73222"]
        variants.append(variant)
        
        return variants
    
    @staticmethod
    def create_validation_error_scenarios() -> List[Dict]:
        """Create various validation error scenarios for testing."""
        return [
            {
                "field": "patient_demographics.patient_id",
                "error": "Patient ID cannot be empty",
                "error_code": "REQUIRED_FIELD",
                "suggestion": "Provide a valid encrypted patient ID"
            },
            {
                "field": "diagnosis_codes[0]",
                "error": "Invalid ICD-10 code format",
                "error_code": "INVALID_FORMAT",
                "suggestion": "Use format like M25.511"
            },
            {
                "field": "procedure_codes[0]",
                "error": "CPT code not found in database",
                "error_code": "CODE_NOT_FOUND",
                "suggestion": "Verify code with current CPT manual"
            },
            {
                "field": "clinical_notes",
                "error": "Clinical notes are required for this procedure type",
                "error_code": "REQUIRED_FIELD",
                "suggestion": "Provide detailed clinical justification"
            }
        ]


@pytest.fixture
def coverage_test_helper():
    """Provide coverage test helper utilities."""
    return CoverageTestHelper()
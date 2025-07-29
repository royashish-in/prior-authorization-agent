"""
Pytest configuration and shared fixtures for the prior authorization system.
"""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, List, Any
from fastapi.testclient import TestClient

from src.models.authorization import AuthorizationRequest, AuthorizationDecision
from src.models.patient import PatientDemographics
from src.models.medical_codes import ICD10Code, CPTCode
from src.models.enums import (
    RequestStatus, DecisionStatus, UrgencyLevel, Gender, ProcedureType
)
from src.services.validation import ValidationResult, ValidationError
from src.services.policy_validation import PolicyValidationResult, PolicyType
from src.auth.models import TokenData, UserRole
from src.auth.oauth2 import get_current_user


@pytest.fixture
def sample_patient_demographics():
    """Create sample patient demographics for testing."""
    return PatientDemographics(
        patient_id="enc_pat_1a2b3c4d5e6f7g8h",
        age=45,
        gender=Gender.FEMALE,
        insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
        member_id="enc_mem_1z2y3x4w5v6u7t8s"
    )


@pytest.fixture
def sample_diagnosis_codes():
    """Create sample diagnosis codes for testing."""
    return [
        ICD10Code(code="M25.511", description="Pain in right shoulder"),
        ICD10Code(code="M25.512", description="Pain in left shoulder")
    ]


@pytest.fixture
def sample_procedure_codes():
    """Create sample procedure codes for testing."""
    return [
        CPTCode(code="73221", description="MRI upper extremity without contrast"),
        CPTCode(code="73222", description="MRI upper extremity with contrast")
    ]


@pytest.fixture
def sample_authorization_request(sample_patient_demographics, sample_diagnosis_codes, sample_procedure_codes):
    """Create a sample authorization request for testing."""
    return AuthorizationRequest(
        request_id="req_test_001",
        provider_id="prov_test_001",
        patient_demographics=sample_patient_demographics,
        diagnosis_codes=sample_diagnosis_codes,
        procedure_codes=sample_procedure_codes,
        clinical_notes="Patient reports persistent shoulder pain for 6 weeks following minor trauma.",
        procedure_type=ProcedureType.MRI,
        urgency_level=UrgencyLevel.ROUTINE,
        status=RequestStatus.SUBMITTED
    )


@pytest.fixture
def sample_authorization_decision():
    """Create a sample authorization decision for testing."""
    return AuthorizationDecision(
        decision_id="dec_test_001",
        request_id="req_test_001",
        status=DecisionStatus.APPROVED,
        reasoning=[
            "Patient meets medical necessity criteria",
            "Diagnosis code is covered under policy"
        ],
        policy_references=["CMS NCD 220.2"],
        authorization_number="auth_test_001",
        valid_until=datetime.now(timezone.utc) + timedelta(days=30),
        confidence_score=0.95
    )


@pytest.fixture
def sample_validation_result():
    """Create a sample validation result for testing."""
    return ValidationResult(
        is_valid=True,
        errors=[],
        warnings=[],
        processing_time_ms=1500.0
    )


@pytest.fixture
def sample_policy_validation_result():
    """Create a sample policy validation result for testing."""
    return PolicyValidationResult(
        is_covered=True,
        policy_id="POL_MRI_001",
        policy_type=PolicyType.PAYER,
        reasoning=["Shoulder MRI covered for persistent pain"],
        confidence_score=0.9,
        policy_references=["Payer Policy IMG-001"],
        additional_requirements=[]
    )


@pytest.fixture
def mock_database_session():
    """Create a mock database session."""
    session = Mock()
    session.query.return_value = session
    session.filter.return_value = session
    session.first.return_value = None
    session.all.return_value = []
    session.add.return_value = None
    session.commit.return_value = None
    session.rollback.return_value = None
    session.close.return_value = None
    return session


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client."""
    redis_client = Mock()
    redis_client.get.return_value = None
    redis_client.set.return_value = True
    redis_client.delete.return_value = 1
    redis_client.exists.return_value = False
    redis_client.expire.return_value = True
    redis_client.flushdb.return_value = True
    return redis_client


@pytest.fixture
def mock_external_service():
    """Create a mock external service client."""
    service = AsyncMock()
    service.validate_medical_code.return_value = {"valid": True, "description": "Valid code"}
    service.get_cms_guidelines.return_value = {"guidelines": "Test guidelines"}
    service.check_policy_coverage.return_value = {"covered": True, "policy": "Test policy"}
    return service


class MockDataGenerator:
    """Generate mock data for various testing scenarios."""
    
    @staticmethod
    def create_medical_scenarios() -> List[Dict[str, Any]]:
        """Create various medical scenarios for testing."""
        return [
            {
                "name": "shoulder_mri_routine",
                "diagnosis_codes": ["M25.511"],
                "procedure_codes": ["73221"],
                "urgency": UrgencyLevel.ROUTINE,
                "expected_outcome": DecisionStatus.APPROVED
            },
            {
                "name": "brain_mri_emergent",
                "diagnosis_codes": ["G93.1"],
                "procedure_codes": ["70551"],
                "urgency": UrgencyLevel.EMERGENT,
                "expected_outcome": DecisionStatus.APPROVED
            },
            {
                "name": "spine_ct_routine",
                "diagnosis_codes": ["M54.5"],
                "procedure_codes": ["72128"],
                "urgency": UrgencyLevel.ROUTINE,
                "expected_outcome": DecisionStatus.MORE_INFO_NEEDED
            },
            {
                "name": "invalid_diagnosis",
                "diagnosis_codes": ["INVALID"],
                "procedure_codes": ["73221"],
                "urgency": UrgencyLevel.ROUTINE,
                "expected_outcome": DecisionStatus.DENIED
            }
        ]
    
    @staticmethod
    def create_validation_errors() -> List[ValidationError]:
        """Create sample validation errors."""
        return [
            ValidationError(
                field="diagnosis_codes[0]",
                message="Invalid ICD-10 code format",
                error_code="INVALID_FORMAT",
                suggestion="Use format like M25.511"
            ),
            ValidationError(
                field="procedure_codes[0]",
                message="CPT code not found in database",
                error_code="CODE_NOT_FOUND",
                suggestion="Verify code with current CPT manual"
            )
        ]
    
    @staticmethod
    def create_policy_scenarios() -> List[Dict[str, Any]]:
        """Create various policy scenarios for testing."""
        return [
            {
                "name": "covered_with_requirements",
                "is_covered": True,
                "additional_requirements": ["Physical therapy notes required"]
            },
            {
                "name": "not_covered",
                "is_covered": False,
                "additional_requirements": []
            },
            {
                "name": "covered_no_requirements",
                "is_covered": True,
                "additional_requirements": []
            }
        ]


@pytest.fixture
def mock_data_generator():
    """Provide the mock data generator."""
    return MockDataGenerator()


@pytest.fixture
def performance_test_data():
    """Generate data for performance testing."""
    return {
        "concurrent_requests": 100,
        "load_test_duration": 30,  # seconds
        "expected_response_time": 2.0,  # seconds
        "expected_throughput": 50  # requests per second
    }


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Set up test environment before each test."""
    import os
    
    # Set required environment variables for testing
    test_env_vars = {
        'PHI_MASTER_KEY': 'test-phi-master-key-for-testing-purposes-2024',
        'PA_SECRET_KEY': 'test-secret-key-for-testing-12345678901234567890',
        'PA_ENCRYPTION_KEY': 'test-encryption-key-32-chars-long',
        'PA_ENVIRONMENT': 'testing',
        'PA_DATABASE_URL': 'sqlite:///:memory:',
        'PA_LOG_LEVEL': 'ERROR'  # Reduce log noise in tests
    }
    
    # Store original values
    original_values = {}
    for key, value in test_env_vars.items():
        original_values[key] = os.environ.get(key)
        os.environ[key] = value
    
    try:
        # Patch datetime to use timezone-aware datetime
        with patch('src.models.authorization.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime.now(timezone.utc)
            mock_datetime.utcnow.return_value = datetime.now(timezone.utc)
            yield
    finally:
        # Restore original environment variables
        for key, original_value in original_values.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value


@pytest.fixture
def mock_audit_logger():
    """Create a mock audit logger."""
    logger = Mock()
    logger.log_event.return_value = None
    logger.log_security_event.return_value = None
    logger.log_phi_access.return_value = None
    return logger


@pytest.fixture
def mock_notification_service():
    """Create a mock notification service."""
    service = AsyncMock()
    service.send_email.return_value = True
    service.send_dashboard_alert.return_value = True
    service.send_sms.return_value = True
    return service


@pytest.fixture
def integration_test_config():
    """Configuration for integration tests."""
    return {
        "database_url": "sqlite:///:memory:",
        "redis_url": "redis://localhost:6379/1",
        "external_services": {
            "cms_api": "https://api.cms.gov/test",
            "medical_codes_api": "https://api.medicalcodes.com/test"
        },
        "test_timeout": 30
    }


# Event loop fixture for async tests
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_encryption_service():
    """Create a mock encryption service."""
    service = Mock()
    service.encrypt.return_value = "encrypted_data"
    service.decrypt.return_value = "decrypted_data"
    service.generate_key.return_value = "test_key"
    return service


@pytest.fixture
def mock_monitoring_service():
    """Create a mock monitoring service."""
    service = Mock()
    service.record_metric.return_value = None
    service.record_request.return_value = None
    service.record_error.return_value = None
    service.get_metrics.return_value = {"requests": 100, "errors": 5}
    return service


# Test authentication fixtures
@pytest.fixture
def mock_test_user():
    """Create a mock test user for authentication."""
    return TokenData(
        user_id="test_user_001",
        username="test_provider",
        roles=[UserRole.PROVIDER],
        organization_id="test_org_001",
        exp=datetime.now(timezone.utc) + timedelta(hours=24),
        iat=datetime.now(timezone.utc)
    )


@pytest.fixture
def authenticated_client(mock_test_user):
    """Create an authenticated test client."""
    from src.main import app
    
    # Mock the authentication dependency
    def mock_get_current_user():
        return mock_test_user
    
    # Override the dependency
    app.dependency_overrides[get_current_user] = mock_get_current_user
    
    client = TestClient(app)
    
    yield client
    
    # Clean up the override
    app.dependency_overrides.clear()


@pytest.fixture
def unauthenticated_client():
    """Create an unauthenticated test client."""
    from src.main import app
    return TestClient(app)


# Cleanup fixture
@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Clean up after each test."""
    yield
    # Perform any necessary cleanup
    from src.main import app
    app.dependency_overrides.clear()
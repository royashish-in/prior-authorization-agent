"""
Shared test fixtures for the Prior Authorization System test suite.

This module provides pytest fixtures that can be used across multiple
test files to ensure consistent test setup and teardown.
"""

import pytest
from unittest.mock import Mock, patch
from typing import Dict, Any, List
from datetime import datetime, timezone

from tests.utils.data_generator import DataGenerator
from tests.utils.mock_helpers import MockHelpers
from src.models.authorization import AuthorizationRequest, AuthorizationDecision
from src.models.patient import PatientDemographics
from src.models.medical_codes import ICD10Code, CPTCode
from src.models.enums import DecisionStatus, RequestStatus, UrgencyLevel, Gender, ProcedureType


class TestFixtures:
    """Container class for test fixtures and setup utilities."""
    
    @staticmethod
    @pytest.fixture
    def data_generator():
        """Provide a DataGenerator instance for tests."""
        return DataGenerator()
    
    @staticmethod
    @pytest.fixture
    def mock_helpers():
        """Provide MockHelpers instance for tests."""
        return MockHelpers()
    
    @staticmethod
    @pytest.fixture
    def sample_patient_demographics():
        """Provide sample patient demographics for testing."""
        return PatientDemographics(
            patient_id="enc_pat_1234567",
            age=45,
            gender=Gender.MALE,
            insurance_id="enc_ins_1234567",
            member_id="enc_mem_1234567"
        )
    
    @staticmethod
    @pytest.fixture
    def sample_diagnosis_codes():
        """Provide sample diagnosis codes for testing."""
        return [
            ICD10Code(code="M25.511", description="Pain in right shoulder"),
            ICD10Code(code="M54.5", description="Low back pain")
        ]
    
    @staticmethod
    @pytest.fixture
    def sample_procedure_codes():
        """Provide sample procedure codes for testing."""
        return [
            CPTCode(code="73221", description="MRI upper extremity without contrast"),
            CPTCode(code="72148", description="MRI lumbar spine without contrast")
        ]
    
    @staticmethod
    @pytest.fixture
    def sample_authorization_request(sample_patient_demographics, 
                                   sample_diagnosis_codes, 
                                   sample_procedure_codes):
        """Provide a complete sample authorization request."""
        return AuthorizationRequest(
            request_id="req_test_001",
            provider_id="prov_1234",
            patient_demographics=sample_patient_demographics,
            diagnosis_codes=sample_diagnosis_codes[:1],  # Use first diagnosis
            procedure_codes=sample_procedure_codes[:1],  # Use first procedure
            clinical_notes="Patient presents with persistent shoulder pain following sports injury. Conservative treatment with physical therapy has provided limited relief.",
            procedure_type=ProcedureType.MRI,
            urgency_level=UrgencyLevel.ROUTINE,
            status=RequestStatus.SUBMITTED
        )
    
    @staticmethod
    @pytest.fixture
    def sample_authorization_decision():
        """Provide a sample authorization decision."""
        return AuthorizationDecision(
            decision_id="dec_test_001",
            request_id="req_test_001",
            status=DecisionStatus.APPROVED,
            reasoning=[
                "Patient meets medical necessity criteria for MRI upper extremity",
                "Diagnosis M25.511 is covered under current policy",
                "Conservative treatment duration is adequate"
            ],
            policy_references=[
                "CMS NCD 220.2 - Magnetic Resonance Imaging",
                "LCD L33721 - MRI Upper Extremity"
            ],
            confidence_score=0.95,
            authorization_number=f"auth_{datetime.now(timezone.utc).strftime('%Y%m%d')}_123456"
        )
    
    @staticmethod
    @pytest.fixture
    def mock_database_session():
        """Provide a mock database session."""
        return MockHelpers.mock_database_session()
    
    @staticmethod
    @pytest.fixture
    def optimized_database_session():
        """Provide an optimized test database session."""
        from tests.utils.database_test_fixtures import get_test_database_manager
        test_manager = get_test_database_manager()
        with test_manager.get_test_session("optimized_test") as session:
            yield session
        test_manager.cleanup_test_data("optimized_test")
    
    @staticmethod
    @pytest.fixture
    def populated_database_session():
        """Provide a test database session with sample data."""
        from tests.utils.database_test_fixtures import get_test_database_manager
        test_manager = get_test_database_manager()
        with test_manager.get_test_session("populated_test") as session:
            test_data = test_manager.populate_test_data(session, "comprehensive")
            yield session, test_data
        test_manager.cleanup_test_data("populated_test")
    
    @staticmethod
    @pytest.fixture
    def mock_huggingface_client():
        """Provide a mock HuggingFace client."""
        return MockHelpers.mock_huggingface_client()
    
    @staticmethod
    @pytest.fixture
    def mock_medical_code_validator():
        """Provide a mock medical code validator."""
        return MockHelpers.mock_medical_code_validator()
    
    @staticmethod
    @pytest.fixture
    def mock_policy_engine():
        """Provide a mock policy engine."""
        return MockHelpers.mock_policy_engine()
    
    @staticmethod
    @pytest.fixture
    def mock_notification_service():
        """Provide a mock notification service."""
        return MockHelpers.mock_notification_service()
    
    @staticmethod
    @pytest.fixture
    def mock_audit_logger():
        """Provide a mock audit logger."""
        return MockHelpers.mock_audit_logger()
    
    @staticmethod
    @pytest.fixture
    def mock_cache_service():
        """Provide a mock cache service."""
        return MockHelpers.mock_cache_service()
    
    @staticmethod
    @pytest.fixture
    def mock_decision_engine():
        """Provide a mock decision engine."""
        return MockHelpers.mock_decision_engine()
    
    @staticmethod
    @pytest.fixture(scope="function")
    def clean_database():
        """Provide a clean database state for each test."""
        from tests.utils.database_test_fixtures import create_database_mock_patches, cleanup_database_mock_patches
        patches = create_database_mock_patches()
        yield patches
        cleanup_database_mock_patches()
    
    @staticmethod
    @pytest.fixture(scope="function")
    def isolated_test_database():
        """Provide an isolated test database for each test."""
        from tests.utils.database_test_fixtures import isolated_test_database
        with isolated_test_database() as session:
            yield session
    
    @staticmethod
    @pytest.fixture(scope="function")
    def isolated_test_environment():
        """Provide an isolated test environment with all external dependencies mocked."""
        patches = MockHelpers.setup_common_patches()
        yield patches
        MockHelpers.cleanup_patches()
    
    @staticmethod
    @pytest.fixture
    def test_scenarios(data_generator):
        """Provide a set of test scenarios for comprehensive testing."""
        return data_generator.generate_medical_scenarios(count=5)
    
    @staticmethod
    @pytest.fixture
    def edge_case_scenarios(data_generator):
        """Provide edge case scenarios for testing."""
        return data_generator.generate_edge_case_scenarios()
    
    @staticmethod
    @pytest.fixture
    def performance_test_data(data_generator):
        """Provide data for performance testing."""
        return data_generator.generate_performance_test_data(request_count=100)
    
    @staticmethod
    @pytest.fixture(params=[
        DecisionStatus.APPROVED,
        DecisionStatus.DENIED,
        DecisionStatus.MORE_INFO_NEEDED
    ])
    def decision_status_variants(request):
        """Parametrized fixture for testing different decision statuses."""
        return request.param
    
    @staticmethod
    @pytest.fixture(params=[
        UrgencyLevel.ROUTINE,
        UrgencyLevel.URGENT,
        UrgencyLevel.EMERGENT
    ])
    def urgency_level_variants(request):
        """Parametrized fixture for testing different urgency levels."""
        return request.param
    
    @staticmethod
    @pytest.fixture(params=[
        ProcedureType.MRI,
        ProcedureType.CT_SCAN,
        ProcedureType.X_RAY,
        ProcedureType.ULTRASOUND
    ])
    def procedure_type_variants(request):
        """Parametrized fixture for testing different procedure types."""
        return request.param
    
    @staticmethod
    @pytest.fixture
    def api_test_client():
        """Provide a test client for API testing."""
        # This would typically create a FastAPI test client
        # For now, we'll return a mock
        from unittest.mock import MagicMock
        mock_client = MagicMock()
        mock_client.post.return_value.status_code = 200
        mock_client.get.return_value.status_code = 200
        mock_client.put.return_value.status_code = 200
        mock_client.delete.return_value.status_code = 200
        return mock_client
    
    @staticmethod
    @pytest.fixture(autouse=True)
    def setup_test_logging():
        """Set up test logging configuration."""
        import logging
        logging.getLogger().setLevel(logging.DEBUG)
        yield
        # Cleanup logging if needed
    
    @staticmethod
    @pytest.fixture
    def temp_test_files(tmp_path):
        """Provide temporary files for testing file operations."""
        test_files = {
            'config': tmp_path / "test_config.json",
            'data': tmp_path / "test_data.csv",
            'log': tmp_path / "test.log"
        }
        
        # Create some sample content
        test_files['config'].write_text('{"test": true}')
        test_files['data'].write_text('header1,header2\nvalue1,value2\n')
        test_files['log'].write_text('Test log entry\n')
        
        return test_files
    
    @staticmethod
    @pytest.fixture
    def mock_environment_variables(monkeypatch):
        """Set up mock environment variables for testing."""
        test_env_vars = {
            'DATABASE_URL': 'sqlite:///test.db',
            'SECRET_KEY': 'test-secret-key',
            'HUGGINGFACE_API_KEY': 'test-hf-key',
            'REDIS_URL': 'redis://localhost:6379/1',
            'LOG_LEVEL': 'DEBUG'
        }
        
        for key, value in test_env_vars.items():
            monkeypatch.setenv(key, value)
        
        return test_env_vars


# Export commonly used fixtures for easy import
data_generator = TestFixtures.data_generator
mock_helpers = TestFixtures.mock_helpers
sample_patient_demographics = TestFixtures.sample_patient_demographics
sample_diagnosis_codes = TestFixtures.sample_diagnosis_codes
sample_procedure_codes = TestFixtures.sample_procedure_codes
sample_authorization_request = TestFixtures.sample_authorization_request
sample_authorization_decision = TestFixtures.sample_authorization_decision
mock_database_session = TestFixtures.mock_database_session
optimized_database_session = TestFixtures.optimized_database_session
populated_database_session = TestFixtures.populated_database_session
mock_huggingface_client = TestFixtures.mock_huggingface_client
mock_medical_code_validator = TestFixtures.mock_medical_code_validator
mock_policy_engine = TestFixtures.mock_policy_engine
mock_notification_service = TestFixtures.mock_notification_service
mock_audit_logger = TestFixtures.mock_audit_logger
mock_cache_service = TestFixtures.mock_cache_service
mock_decision_engine = TestFixtures.mock_decision_engine
clean_database = TestFixtures.clean_database
isolated_test_database = TestFixtures.isolated_test_database
isolated_test_environment = TestFixtures.isolated_test_environment
test_scenarios = TestFixtures.test_scenarios
edge_case_scenarios = TestFixtures.edge_case_scenarios
performance_test_data = TestFixtures.performance_test_data
decision_status_variants = TestFixtures.decision_status_variants
urgency_level_variants = TestFixtures.urgency_level_variants
procedure_type_variants = TestFixtures.procedure_type_variants
api_test_client = TestFixtures.api_test_client
setup_test_logging = TestFixtures.setup_test_logging
temp_test_files = TestFixtures.temp_test_files
mock_environment_variables = TestFixtures.mock_environment_variables
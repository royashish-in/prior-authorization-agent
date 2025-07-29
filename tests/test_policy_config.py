"""
Unit tests for policy configuration service and API endpoints.

Tests policy creation, updates, version control, bulk import,
and sandbox testing functionality.
"""

import json
import pytest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.services.policy_config import PolicyConfigurationService
from src.database.models import CoveragePolicyDB
from src.models.authorization import AuthorizationRequest
from src.models.patient import PatientDemographics
from src.models.medical_codes import ICD10Code, CPTCode
from src.models.enums import Gender, UrgencyLevel, ProcedureType


class TestPolicyConfigurationService:
    """Test cases for PolicyConfigurationService."""
    
    @pytest.fixture
    def mock_db_session(self):
        """Mock database session."""
        return Mock(spec=Session)
    
    @pytest.fixture
    def policy_service(self, mock_db_session):
        """Policy configuration service instance."""
        return PolicyConfigurationService(mock_db_session)
    
    @pytest.fixture
    def sample_policy_data(self):
        """Sample policy configuration data."""
        return {
            'payer_id': 'AETNA',
            'procedure_code': '73721',
            'policy_name': 'MRI Knee Coverage Policy',
            'policy_type': 'PAYER',
            'diagnosis_codes': ['M25.511', 'S83.201A'],
            'coverage_criteria': {
                'age_range': {'min_age': 18, 'max_age': 65},
                'medical_necessity': {
                    'required_symptoms': ['pain', 'swelling'],
                    'prior_treatment': 'conservative_therapy',
                    'duration_requirements': '6_weeks'
                },
                'procedure_requirements': {
                    'contrast_requirements': 'without_contrast',
                    'anatomical_requirements': 'knee_joint'
                }
            },
            'effective_date': date.today(),
            'expiration_date': date.today() + timedelta(days=365),
            'is_active': True
        }
    
    @pytest.fixture
    def sample_policy_db(self, sample_policy_data):
        """Sample policy database record."""
        return CoveragePolicyDB(
            policy_id='pol_20250124_test123',
            payer_id=sample_policy_data['payer_id'],
            procedure_code=sample_policy_data['procedure_code'],
            diagnosis_codes=sample_policy_data['diagnosis_codes'],
            coverage_criteria=sample_policy_data['coverage_criteria'],
            policy_type=sample_policy_data['policy_type'],
            policy_name=sample_policy_data['policy_name'],
            policy_version='1.0',
            effective_date=sample_policy_data['effective_date'],
            expiration_date=sample_policy_data['expiration_date'],
            is_active=sample_policy_data['is_active'],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            created_by='test_user',
            updated_by='test_user'
        )
    
    @pytest.mark.asyncio
    async def test_create_policy_success(self, policy_service, sample_policy_data, mock_db_session):
        """Test successful policy creation."""
        # Mock validation methods
        policy_service._validate_policy_data = AsyncMock(return_value={'is_valid': True, 'errors': []})
        policy_service._check_policy_conflicts = AsyncMock(return_value=[])
        policy_service._create_version_record = AsyncMock()
        
        # Mock database operations
        mock_db_session.add = Mock()
        mock_db_session.commit = Mock()
        
        # Create policy
        policy_id = await policy_service.create_policy(sample_policy_data, 'test_user')
        
        # Verify policy ID format
        assert policy_id.startswith('pol_')
        assert len(policy_id) > 20
        
        # Verify database operations
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()
        
        # Verify validation was called
        policy_service._validate_policy_data.assert_called_once_with(sample_policy_data)
        policy_service._check_policy_conflicts.assert_called_once_with(sample_policy_data)
        policy_service._create_version_record.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_policy_validation_failure(self, policy_service, sample_policy_data):
        """Test policy creation with validation failure."""
        # Mock validation failure
        policy_service._validate_policy_data = AsyncMock(return_value={
            'is_valid': False,
            'errors': ['Invalid procedure code']
        })
        
        # Attempt to create policy
        with pytest.raises(ValueError, match="Policy validation failed"):
            await policy_service.create_policy(sample_policy_data, 'test_user')
    
    @pytest.mark.asyncio
    async def test_update_policy_success(self, policy_service, sample_policy_db, mock_db_session):
        """Test successful policy update."""
        # Mock get_policy_by_id
        policy_service.get_policy_by_id = Mock(return_value=sample_policy_db)
        
        # Mock validation methods
        policy_service._validate_coverage_criteria = AsyncMock(return_value={'is_valid': True, 'errors': []})
        policy_service._check_policy_conflicts = AsyncMock(return_value=[])
        policy_service._create_version_record = AsyncMock()
        
        # Mock database operations
        mock_db_session.commit = Mock()
        
        # Update data
        update_data = {
            'policy_name': 'Updated MRI Knee Policy',
            'coverage_criteria': {'age_range': {'min_age': 21, 'max_age': 70}}
        }
        
        # Update policy
        updated_policy = await policy_service.update_policy(
            policy_id='pol_20250124_test123',
            update_data=update_data,
            updated_by='test_user',
            update_reason='Policy criteria update'
        )
        
        # Verify update
        assert updated_policy is not None
        assert updated_policy.policy_name == 'Updated MRI Knee Policy'
        assert updated_policy.policy_version == '1.1'
        assert updated_policy.updated_by == 'test_user'
        
        # Verify database operations
        mock_db_session.commit.assert_called_once()
        policy_service._create_version_record.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_policy_not_found(self, policy_service):
        """Test policy update when policy not found."""
        # Mock get_policy_by_id to return None
        policy_service.get_policy_by_id = Mock(return_value=None)
        
        # Attempt to update non-existent policy
        result = await policy_service.update_policy(
            policy_id='nonexistent',
            update_data={'policy_name': 'Updated'},
            updated_by='test_user',
            update_reason='Test update'
        )
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_deactivate_policy_success(self, policy_service, sample_policy_db, mock_db_session):
        """Test successful policy deactivation."""
        # Mock get_policy_by_id
        policy_service.get_policy_by_id = Mock(return_value=sample_policy_db)
        policy_service._create_version_record = AsyncMock()
        
        # Mock database operations
        mock_db_session.commit = Mock()
        
        # Deactivate policy
        result = await policy_service.deactivate_policy('pol_20250124_test123', 'test_user')
        
        # Verify deactivation
        assert result is True
        assert sample_policy_db.is_active is False
        assert sample_policy_db.updated_by == 'test_user'
        
        # Verify database operations
        mock_db_session.commit.assert_called_once()
        policy_service._create_version_record.assert_called_once()
    
    def test_get_policy_by_id_success(self, policy_service, sample_policy_db, mock_db_session):
        """Test successful policy retrieval by ID."""
        # Mock database query
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = sample_policy_db
        mock_db_session.query.return_value = mock_query
        
        # Get policy
        policy = policy_service.get_policy_by_id('pol_20250124_test123')
        
        # Verify result
        assert policy == sample_policy_db
        mock_db_session.query.assert_called_once_with(CoveragePolicyDB)
    
    def test_get_policy_by_id_not_found(self, policy_service, mock_db_session):
        """Test policy retrieval when policy not found."""
        # Mock database query to return None
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        mock_db_session.query.return_value = mock_query
        
        # Get non-existent policy
        policy = policy_service.get_policy_by_id('nonexistent')
        
        # Verify result
        assert policy is None
    
    def test_list_policies_with_filters(self, policy_service, mock_db_session):
        """Test policy listing with filters."""
        # Mock database query
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_db_session.query.return_value = mock_query
        
        # List policies with filters
        policies = policy_service.list_policies(
            payer_id='AETNA',
            policy_type='PAYER',
            active_only=True,
            limit=50,
            offset=10
        )
        
        # Verify query was built correctly
        assert mock_query.filter.call_count >= 3  # payer_id, policy_type, active filters
        mock_query.order_by.assert_called_once()
        mock_query.offset.assert_called_once_with(10)
        mock_query.limit.assert_called_once_with(50)
        mock_query.all.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_bulk_import_policies_validate_mode(self, policy_service):
        """Test bulk import in validate mode."""
        # Mock validation
        policy_service._validate_policy_data = AsyncMock(return_value={'is_valid': True, 'errors': []})
        
        # Sample policies data
        policies_data = [
            {'payer_id': 'AETNA', 'procedure_code': '73721', 'policy_name': 'Test 1', 
             'policy_type': 'PAYER', 'coverage_criteria': {'age_range': {'min_age': 18}}},
            {'payer_id': 'BCBS', 'procedure_code': '73722', 'policy_name': 'Test 2', 
             'policy_type': 'PAYER', 'coverage_criteria': {'age_range': {'min_age': 21}}}
        ]
        
        # Perform bulk import
        result = await policy_service.bulk_import_policies(
            policies_data=policies_data,
            import_mode='validate',
            imported_by='test_user'
        )
        
        # Verify result
        assert result['total_policies'] == 2
        assert result['successful_imports'] == 2
        assert result['failed_imports'] == 0
        assert len(result['validation_errors']) == 0
        assert result['import_summary']['new_policies'] == 0  # Validate mode doesn't create
    
    @pytest.mark.asyncio
    async def test_bulk_import_policies_with_validation_errors(self, policy_service):
        """Test bulk import with validation errors."""
        # Mock validation - first policy valid, second invalid
        policy_service._validate_policy_data = AsyncMock(side_effect=[
            {'is_valid': True, 'errors': []},
            {'is_valid': False, 'errors': ['Invalid procedure code']}
        ])
        
        # Sample policies data
        policies_data = [
            {'payer_id': 'AETNA', 'procedure_code': '73721', 'policy_name': 'Valid Policy', 
             'policy_type': 'PAYER', 'coverage_criteria': {'age_range': {'min_age': 18}}},
            {'payer_id': 'BCBS', 'procedure_code': 'INVALID', 'policy_name': 'Invalid Policy', 
             'policy_type': 'PAYER', 'coverage_criteria': {'age_range': {'min_age': 21}}}
        ]
        
        # Perform bulk import
        result = await policy_service.bulk_import_policies(
            policies_data=policies_data,
            import_mode='validate',
            imported_by='test_user'
        )
        
        # Verify result
        assert result['total_policies'] == 2
        assert result['successful_imports'] == 1
        assert result['failed_imports'] == 1
        assert len(result['validation_errors']) == 1
        assert result['validation_errors'][0]['index'] == 1
        assert 'Invalid procedure code' in result['validation_errors'][0]['errors']
    
    @pytest.mark.asyncio
    async def test_test_policy_sandbox_success(self, policy_service):
        """Test policy sandbox testing with successful scenarios."""
        # Mock validation
        policy_service._validate_policy_data = AsyncMock(return_value={'is_valid': True, 'errors': []})
        
        # Mock policy validation service
        mock_validation_result = Mock()
        mock_validation_result.is_covered = True
        mock_validation_result.reasoning = ['Policy criteria met']
        mock_validation_result.confidence_score = 0.9
        
        policy_service.policy_validation_service._validate_against_policy = Mock(
            return_value=mock_validation_result
        )
        
        # Policy configuration
        policy_config = {
            'payer_id': 'AETNA',
            'procedure_code': '73721',
            'policy_name': 'Test Policy',
            'policy_type': 'PAYER',
            'coverage_criteria': {'age_range': {'min_age': 18, 'max_age': 65}}
        }
        
        # Test scenarios
        test_scenarios = [
            {
                'name': 'Valid Patient',
                'patient_age': 45,
                'diagnosis_codes': ['M25.511'],
                'procedure_codes': ['73721'],
                'expected_outcome': 'approve'
            }
        ]
        
        # Test policy
        result = await policy_service.test_policy_sandbox(
            policy_config=policy_config,
            test_scenarios=test_scenarios,
            tested_by='test_user'
        )
        
        # Verify result
        assert result['overall_success'] is True
        assert len(result['test_results']) == 1
        assert result['test_results'][0]['success'] is True
        assert result['test_results'][0]['actual_outcome'] == 'approve'
        assert 'All test scenarios passed successfully' in result['recommendations']
    
    @pytest.mark.asyncio
    async def test_test_policy_sandbox_failure(self, policy_service):
        """Test policy sandbox testing with failed scenarios."""
        # Mock validation
        policy_service._validate_policy_data = AsyncMock(return_value={'is_valid': True, 'errors': []})
        
        # Mock policy validation service - deny coverage
        mock_validation_result = Mock()
        mock_validation_result.is_covered = False
        mock_validation_result.reasoning = ['Age requirement not met']
        mock_validation_result.confidence_score = 0.8
        
        policy_service.policy_validation_service._validate_against_policy = Mock(
            return_value=mock_validation_result
        )
        
        # Policy configuration
        policy_config = {
            'payer_id': 'AETNA',
            'procedure_code': '73721',
            'policy_name': 'Test Policy',
            'policy_type': 'PAYER',
            'coverage_criteria': {'age_range': {'min_age': 18, 'max_age': 65}}
        }
        
        # Test scenarios - expecting approval but will get denial
        test_scenarios = [
            {
                'name': 'Invalid Patient Age',
                'patient_age': 75,
                'diagnosis_codes': ['M25.511'],
                'procedure_codes': ['73721'],
                'expected_outcome': 'approve'  # This will fail
            }
        ]
        
        # Test policy
        result = await policy_service.test_policy_sandbox(
            policy_config=policy_config,
            test_scenarios=test_scenarios,
            tested_by='test_user'
        )
        
        # Verify result
        assert result['overall_success'] is False
        assert len(result['test_results']) == 1
        assert result['test_results'][0]['success'] is False
        assert result['test_results'][0]['actual_outcome'] == 'deny'
        assert result['test_results'][0]['expected_outcome'] == 'approve'
        assert any('failed' in rec for rec in result['recommendations'])
    
    @pytest.mark.asyncio
    async def test_validate_policy_configuration_success(self, policy_service, sample_policy_db):
        """Test successful policy configuration validation."""
        # Mock get_policy_by_id
        policy_service.get_policy_by_id = Mock(return_value=sample_policy_db)
        
        # Mock validation methods
        policy_service._validate_coverage_criteria = AsyncMock(return_value={'is_valid': True, 'errors': []})
        policy_service._check_policy_conflicts = AsyncMock(return_value=[])
        
        # Mock medical code validator
        policy_service.medical_code_validator.validate_icd10_code = Mock(return_value=True)
        policy_service.medical_code_validator.validate_cpt_code = Mock(return_value=True)
        
        # Validate policy
        result = await policy_service.validate_policy_configuration('pol_20250124_test123')
        
        # Verify result
        assert result['is_valid'] is True
        assert len(result['validation_errors']) == 0
        assert len(result['warnings']) == 0
    
    @pytest.mark.asyncio
    async def test_validate_policy_configuration_with_errors(self, policy_service, sample_policy_db):
        """Test policy configuration validation with errors."""
        # Mock get_policy_by_id
        policy_service.get_policy_by_id = Mock(return_value=sample_policy_db)
        
        # Mock validation methods with errors
        policy_service._validate_coverage_criteria = AsyncMock(return_value={
            'is_valid': False,
            'errors': ['Invalid age range']
        })
        policy_service._check_policy_conflicts = AsyncMock(return_value=['Conflicting policy found'])
        
        # Mock medical code validator with invalid codes
        policy_service.medical_code_validator.validate_icd10_code = Mock(return_value=False)
        policy_service.medical_code_validator.validate_cpt_code = Mock(return_value=False)
        
        # Validate policy
        result = await policy_service.validate_policy_configuration('pol_20250124_test123')
        
        # Verify result
        assert result['is_valid'] is False
        assert 'Invalid age range' in result['validation_errors']
        assert 'Invalid ICD-10 code' in str(result['validation_errors'])
        assert 'Invalid CPT/HCPCS code' in str(result['validation_errors'])
        assert 'Policy conflict detected' in str(result['warnings'])
    
    @pytest.mark.asyncio
    async def test_validate_policy_data_success(self, policy_service, sample_policy_data):
        """Test successful policy data validation."""
        # Mock medical code validator
        policy_service.medical_code_validator.validate_cpt_code = Mock(return_value=True)
        policy_service.medical_code_validator.validate_icd10_code = Mock(return_value=True)
        policy_service._validate_coverage_criteria = AsyncMock(return_value={'is_valid': True, 'errors': []})
        
        # Validate policy data
        result = await policy_service._validate_policy_data(sample_policy_data)
        
        # Verify result
        assert result['is_valid'] is True
        assert len(result['errors']) == 0
    
    @pytest.mark.asyncio
    async def test_validate_policy_data_missing_fields(self, policy_service):
        """Test policy data validation with missing required fields."""
        # Incomplete policy data
        incomplete_data = {
            'payer_id': 'AETNA',
            # Missing required fields
        }
        
        # Validate policy data
        result = await policy_service._validate_policy_data(incomplete_data)
        
        # Verify result
        assert result['is_valid'] is False
        assert any('Missing required field' in error for error in result['errors'])
    
    @pytest.mark.asyncio
    async def test_validate_coverage_criteria_success(self, policy_service):
        """Test successful coverage criteria validation."""
        criteria = {
            'age_range': {'min_age': 18, 'max_age': 65},
            'medical_necessity': {
                'required_symptoms': ['pain', 'swelling'],
                'prior_treatment': 'conservative_therapy'
            }
        }
        
        # Validate coverage criteria
        result = await policy_service._validate_coverage_criteria(criteria)
        
        # Verify result
        assert result['is_valid'] is True
        assert len(result['errors']) == 0
    
    @pytest.mark.asyncio
    async def test_validate_coverage_criteria_invalid_age_range(self, policy_service):
        """Test coverage criteria validation with invalid age range."""
        criteria = {
            'age_range': {'min_age': 65, 'max_age': 18}  # Invalid: min > max
        }
        
        # Validate coverage criteria
        result = await policy_service._validate_coverage_criteria(criteria)
        
        # Verify result
        assert result['is_valid'] is False
        assert any('Minimum age must be less than maximum age' in error for error in result['errors'])
    
    def test_create_mock_request(self, policy_service):
        """Test creation of mock authorization request."""
        scenario = {
            'patient_age': 45,
            'patient_gender': 'F',
            'diagnosis_codes': ['M25.511'],
            'procedure_codes': ['73721'],
            'clinical_notes': 'Patient has knee pain',
            'urgency_level': 'ROUTINE',
            'procedure_type': 'MRI'
        }
        
        # Create mock request
        mock_request = policy_service._create_mock_request(scenario)
        
        # Verify request
        assert isinstance(mock_request, AuthorizationRequest)
        assert mock_request.patient_demographics.age == 45
        assert mock_request.patient_demographics.gender == 'F'
        assert len(mock_request.diagnosis_codes) == 1
        assert mock_request.diagnosis_codes[0].code == 'M25.511'
        assert len(mock_request.procedure_codes) == 1
        assert mock_request.procedure_codes[0].code == '73721'
        assert mock_request.clinical_notes == 'Patient has knee pain'
    
    def test_create_temp_policy(self, policy_service, sample_policy_data):
        """Test creation of temporary policy for testing."""
        policy_id = 'test_policy_123'
        
        # Create temporary policy
        temp_policy = policy_service._create_temp_policy(sample_policy_data, policy_id)
        
        # Verify policy
        assert isinstance(temp_policy, CoveragePolicyDB)
        assert temp_policy.policy_id == policy_id
        assert temp_policy.payer_id == sample_policy_data['payer_id']
        assert temp_policy.procedure_code == sample_policy_data['procedure_code']
        assert temp_policy.policy_name == sample_policy_data['policy_name']
        assert temp_policy.policy_version == 'test'
        assert temp_policy.is_active is True


class TestPolicyConfigurationAPI:
    """Test cases for policy configuration API endpoints."""
    
    @pytest.fixture
    def mock_current_user(self):
        """Mock current user with admin role."""
        return {
            'user_id': 'test_user',
            'roles': ['ADMIN'],
            'permissions': ['POLICY_MANAGEMENT']
        }
    
    @pytest.fixture
    def sample_policy_request(self):
        """Sample policy creation request."""
        return {
            'payer_id': 'AETNA',
            'procedure_code': '73721',
            'policy_name': 'MRI Knee Coverage Policy',
            'policy_type': 'PAYER',
            'diagnosis_codes': ['M25.511', 'S83.201A'],
            'coverage_criteria': {
                'age_range': {'min_age': 18, 'max_age': 65},
                'medical_necessity': {
                    'required_symptoms': ['pain', 'swelling'],
                    'prior_treatment': 'conservative_therapy'
                }
            },
            'effective_date': '2025-01-24',
            'is_active': True
        }
    
    def test_policy_config_request_validation_success(self, sample_policy_request):
        """Test successful policy configuration request validation."""
        from src.api.policy_config import PolicyConfigRequest
        
        # Create request model
        request = PolicyConfigRequest(**sample_policy_request)
        
        # Verify fields
        assert request.payer_id == 'AETNA'
        assert request.procedure_code == '73721'
        assert request.policy_name == 'MRI Knee Coverage Policy'
        assert request.policy_type == 'PAYER'
        assert len(request.diagnosis_codes) == 2
        assert request.is_active is True
    
    def test_policy_config_request_validation_invalid_type(self):
        """Test policy configuration request validation with invalid type."""
        from src.api.policy_config import PolicyConfigRequest
        from pydantic import ValidationError
        
        invalid_request = {
            'payer_id': 'AETNA',
            'procedure_code': '73721',
            'policy_name': 'Test Policy',
            'policy_type': 'INVALID',  # Invalid type
            'coverage_criteria': {'age_range': {'min_age': 18}}
        }
        
        # Attempt to create request model
        with pytest.raises(ValidationError):
            PolicyConfigRequest(**invalid_request)
    
    def test_policy_config_request_validation_short_procedure_code(self):
        """Test policy configuration request validation with short procedure code."""
        from src.api.policy_config import PolicyConfigRequest
        from pydantic import ValidationError
        
        invalid_request = {
            'payer_id': 'AETNA',
            'procedure_code': '123',  # Too short
            'policy_name': 'Test Policy',
            'policy_type': 'PAYER',
            'coverage_criteria': {'age_range': {'min_age': 18}}
        }
        
        # Attempt to create request model
        with pytest.raises(ValidationError):
            PolicyConfigRequest(**invalid_request)
    
    def test_bulk_import_request_validation_success(self):
        """Test successful bulk import request validation."""
        from src.api.policy_config import BulkImportRequest, PolicyConfigRequest
        
        policies = [
            {
                'payer_id': 'AETNA',
                'procedure_code': '73721',
                'policy_name': 'Test Policy 1',
                'policy_type': 'PAYER',
                'coverage_criteria': {'age_range': {'min_age': 18}}
            },
            {
                'payer_id': 'BCBS',
                'procedure_code': '73722',
                'policy_name': 'Test Policy 2',
                'policy_type': 'PAYER',
                'coverage_criteria': {'age_range': {'min_age': 21}}
            }
        ]
        
        # Create bulk import request
        request = BulkImportRequest(
            policies=[PolicyConfigRequest(**policy) for policy in policies],
            import_mode='validate'
        )
        
        # Verify request
        assert len(request.policies) == 2
        assert request.import_mode == 'validate'
    
    def test_bulk_import_request_validation_invalid_mode(self):
        """Test bulk import request validation with invalid mode."""
        from src.api.policy_config import BulkImportRequest, PolicyConfigRequest
        from pydantic import ValidationError
        
        policies = [
            {
                'payer_id': 'AETNA',
                'procedure_code': '73721',
                'policy_name': 'Test Policy',
                'policy_type': 'PAYER',
                'coverage_criteria': {'age_range': {'min_age': 18}}
            }
        ]
        
        # Attempt to create request with invalid mode
        with pytest.raises(ValidationError):
            BulkImportRequest(
                policies=[PolicyConfigRequest(**policies[0])],
                import_mode='invalid_mode'
            )
    
    def test_policy_test_request_validation_success(self):
        """Test successful policy test request validation."""
        from src.api.policy_config import PolicyTestRequest, PolicyConfigRequest
        
        policy_config = {
            'payer_id': 'AETNA',
            'procedure_code': '73721',
            'policy_name': 'Test Policy',
            'policy_type': 'PAYER',
            'coverage_criteria': {'age_range': {'min_age': 18, 'max_age': 65}}
        }
        
        test_scenarios = [
            {
                'name': 'Valid Patient',
                'patient_age': 45,
                'diagnosis_codes': ['M25.511'],
                'expected_outcome': 'approve'
            }
        ]
        
        # Create test request
        request = PolicyTestRequest(
            policy_config=PolicyConfigRequest(**policy_config),
            test_scenarios=test_scenarios
        )
        
        # Verify request
        assert request.policy_config.payer_id == 'AETNA'
        assert len(request.test_scenarios) == 1
        assert request.test_scenarios[0]['name'] == 'Valid Patient'
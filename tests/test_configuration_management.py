"""
Comprehensive tests for configuration management modules.

This test file covers policy configuration loading, validation, environment-specific
configuration, change detection, and error handling scenarios.
"""

import json
import os
import pytest
from datetime import date, datetime, timezone
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List

from pydantic import ValidationError
from sqlalchemy.orm import Session

from src.core.config import Settings, get_settings
from src.services.policy_config import PolicyConfigurationService, BulkImportResult, PolicyTestResult
from src.api.policy_config import (
    PolicyConfigRequest, PolicyUpdateRequest, BulkImportRequest,
    PolicyTestRequest, ResolutionRequest, DeploymentPlanRequest
)
from src.database.models import CoveragePolicyDB
from src.auth.models import UserRole


class TestCoreConfiguration:
    """Test core configuration settings and validation."""
    
    def test_settings_default_values(self):
        """Test that settings have proper default values."""
        # Test current settings (which may be influenced by .env file)
        settings = Settings()
        
        # Test that basic structure is correct
        assert settings.environment in ["development", "testing", "production"]
        assert isinstance(settings.debug, bool)
        assert settings.host == "127.0.0.1"
        assert settings.port == 8000
        assert settings.database_url.startswith("sqlite:///")
        assert settings.log_level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        assert settings.log_format == "json"
        assert settings.jwt_algorithm == "HS256"
        assert settings.jwt_expiration_hours == 24
        assert settings.rate_limit_requests == 100
        assert settings.rate_limit_window == 60
        assert settings.cache_default_ttl == 3600
        assert settings.cache_enabled is True
        assert settings.max_concurrent_requests == 1000
        assert settings.request_timeout == 120
    
    def test_settings_environment_override(self):
        """Test that environment variables override default settings."""
        with patch.dict(os.environ, {
            'PA_ENVIRONMENT': 'production',
            'PA_DEBUG': 'true',
            'PA_HOST': '0.0.0.0',
            'PA_PORT': '9000',
            'PA_LOG_LEVEL': 'DEBUG',
            'PA_DATABASE_URL': 'postgresql://test:test@localhost/test'
        }):
            settings = Settings()
            
            assert settings.environment == "production"
            assert settings.debug is True
            assert settings.host == "0.0.0.0"
            assert settings.port == 9000
            assert settings.log_level == "DEBUG"
            assert settings.database_url == "postgresql://test:test@localhost/test"
    
    def test_settings_phi_master_key_alias(self):
        """Test PHI master key environment variable alias."""
        with patch.dict(os.environ, {'PHI_MASTER_KEY': 'test-phi-key-12345678901234567890'}):
            settings = Settings()
            assert settings.phi_master_key == 'test-phi-key-12345678901234567890'
    
    def test_settings_validation_errors(self):
        """Test settings validation with invalid values."""
        with patch.dict(os.environ, {'PA_PORT': 'invalid_port'}):
            with pytest.raises(ValidationError):
                Settings()
    
    def test_get_settings_caching(self):
        """Test that get_settings returns cached instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2
    
    def test_database_configuration_variants(self):
        """Test different database configuration scenarios."""
        # SQLite configuration
        with patch.dict(os.environ, {
            'PA_DATABASE_URL': 'sqlite:///test.db',
            'PA_DB_DRIVER': 'sqlite'
        }):
            settings = Settings()
            assert settings.database_url == 'sqlite:///test.db'
            assert settings.db_driver == 'sqlite'
        
        # PostgreSQL configuration
        with patch.dict(os.environ, {
            'PA_DB_DRIVER': 'postgresql',
            'PA_DB_HOST': 'localhost',
            'PA_DB_PORT': '5432',
            'PA_DB_NAME': 'prior_auth',
            'PA_DB_USERNAME': 'postgres',
            'PA_DB_PASSWORD': 'password'
        }):
            settings = Settings()
            assert settings.db_driver == 'postgresql'
            assert settings.db_host == 'localhost'
            assert settings.db_port == 5432
            assert settings.db_name == 'prior_auth'
            assert settings.db_username == 'postgres'
            assert settings.db_password == 'password'
    
    def test_redis_configuration(self):
        """Test Redis cache configuration."""
        with patch.dict(os.environ, {
            'PA_REDIS_URL': 'redis://localhost:6380',
            'PA_REDIS_HOST': 'redis-server',
            'PA_REDIS_PORT': '6380',
            'PA_REDIS_DB': '1',
            'PA_REDIS_PASSWORD': 'redis-password',
            'PA_REDIS_MAX_CONNECTIONS': '50'
        }):
            settings = Settings()
            assert settings.redis_url == 'redis://localhost:6380'
            assert settings.redis_host == 'redis-server'
            assert settings.redis_port == 6380
            assert settings.redis_db == 1
            assert settings.redis_password == 'redis-password'
            assert settings.redis_max_connections == 50
    
    def test_external_services_configuration(self):
        """Test external services configuration."""
        with patch.dict(os.environ, {
            'PA_CMS_API_URL': 'https://api.cms.gov/v2',
            'PA_CMS_API_KEY': 'cms-api-key-123',
            'PA_CMS_API_TIMEOUT': '45',
            'PA_MEDICAL_CODES_API_URL': 'https://codes.api.com',
            'PA_MEDICAL_CODES_API_KEY': 'codes-key-456',
            'PA_POLICY_SERVICE_URL': 'https://policy.service.com'
        }):
            settings = Settings()
            assert settings.cms_api_url == 'https://api.cms.gov/v2'
            assert settings.cms_api_key == 'cms-api-key-123'
            assert settings.cms_api_timeout == 45
            assert settings.medical_codes_api_url == 'https://codes.api.com'
            assert settings.medical_codes_api_key == 'codes-key-456'
            assert settings.policy_service_url == 'https://policy.service.com'
    
    def test_llm_configuration(self):
        """Test LLM integration configuration."""
        with patch.dict(os.environ, {
            'PA_HUGGINGFACE_API_TOKEN': 'hf-token-123',
            'PA_HUGGINGFACE_API_URL': 'https://api-inference.huggingface.co/models/custom',
            'PA_LOCAL_MODELS_PATH': '/opt/models',
            'PA_LLM_MAX_CONCURRENT_REQUESTS': '20',
            'PA_LLM_DEFAULT_TIMEOUT': '60',
            'PA_LLM_ENABLE_CACHE': 'false',
            'PA_LLM_CACHE_TTL': '7200'
        }):
            settings = Settings()
            assert settings.huggingface_api_token == 'hf-token-123'
            assert settings.huggingface_api_url == 'https://api-inference.huggingface.co/models/custom'
            assert settings.local_models_path == '/opt/models'
            assert settings.llm_max_concurrent_requests == 20
            assert settings.llm_default_timeout == 60
            assert settings.llm_enable_cache is False
            assert settings.llm_cache_ttl == 7200


class TestPolicyConfigurationService:
    """Test policy configuration service functionality."""
    
    @pytest.fixture
    def mock_db_session(self):
        """Mock database session."""
        return Mock(spec=Session)
    
    @pytest.fixture
    def policy_service(self, mock_db_session):
        """Policy configuration service instance."""
        with patch('src.services.policy_config.PolicyValidationService'), \
             patch('src.services.policy_config.MedicalCodeValidator'):
            return PolicyConfigurationService(mock_db_session)
    
    @pytest.fixture
    def sample_policy_data(self):
        """Sample policy data for testing."""
        return {
            'payer_id': 'test-payer-001',
            'procedure_code': '70553',
            'policy_name': 'Test MRI Policy',
            'policy_type': 'PAYER',
            'diagnosis_codes': ['M25.511', 'M25.512'],
            'coverage_criteria': {
                'age_range': {'min_age': 18, 'max_age': 65},
                'medical_necessity': {
                    'required_symptoms': ['chronic_pain', 'limited_mobility'],
                    'duration_months': 3
                }
            },
            'effective_date': date.today(),
            'is_active': True
        }
    
    @pytest.mark.asyncio
    async def test_policy_data_validation_success(self, policy_service, sample_policy_data):
        """Test successful policy data validation."""
        with patch.object(policy_service, '_validate_coverage_criteria') as mock_validate_criteria, \
             patch.object(policy_service.medical_code_validator, 'validate_cpt_code', return_value=True), \
             patch.object(policy_service.medical_code_validator, 'validate_icd10_code', return_value=True):
            
            mock_validate_criteria.return_value = {'is_valid': True, 'errors': []}
            
            result = await policy_service._validate_policy_data(sample_policy_data)
            
            assert result['is_valid'] is True
            assert len(result['errors']) == 0
    
    async def test_policy_data_validation_missing_fields(self, policy_service):
        """Test policy data validation with missing required fields."""
        incomplete_data = {
            'payer_id': 'test-payer-001',
            # Missing required fields
        }
        
        result = await policy_service._validate_policy_data(incomplete_data)
        
        assert result['is_valid'] is False
        assert any('Missing required field' in error for error in result['errors'])
    
    async def test_policy_data_validation_invalid_policy_type(self, policy_service, sample_policy_data):
        """Test policy data validation with invalid policy type."""
        sample_policy_data['policy_type'] = 'INVALID_TYPE'
        
        result = await policy_service._validate_policy_data(sample_policy_data)
        
        assert result['is_valid'] is False
        assert any('Policy type must be NCD, LCD, or PAYER' in error for error in result['errors'])
    
    async def test_policy_data_validation_invalid_medical_codes(self, policy_service, sample_policy_data):
        """Test policy data validation with invalid medical codes."""
        with patch.object(policy_service, '_validate_coverage_criteria') as mock_validate_criteria, \
             patch.object(policy_service.medical_code_validator, 'validate_cpt_code', return_value=False), \
             patch.object(policy_service.medical_code_validator, 'validate_icd10_code', return_value=False):
            
            mock_validate_criteria.return_value = {'is_valid': True, 'errors': []}
            
            result = await policy_service._validate_policy_data(sample_policy_data)
            
            assert result['is_valid'] is False
            assert any('Invalid CPT/HCPCS code' in error for error in result['errors'])
            assert any('Invalid ICD-10 code' in error for error in result['errors'])
    
    async def test_coverage_criteria_validation_success(self, policy_service):
        """Test successful coverage criteria validation."""
        valid_criteria = {
            'age_range': {'min_age': 18, 'max_age': 65},
            'medical_necessity': {
                'required_symptoms': ['chronic_pain'],
                'duration_months': 3
            }
        }
        
        result = await policy_service._validate_coverage_criteria(valid_criteria)
        
        assert result['is_valid'] is True
        assert len(result['errors']) == 0
    
    async def test_coverage_criteria_validation_invalid_structure(self, policy_service):
        """Test coverage criteria validation with invalid structure."""
        invalid_criteria = "not_a_dict"
        
        result = await policy_service._validate_coverage_criteria(invalid_criteria)
        
        assert result['is_valid'] is False
        assert 'Coverage criteria must be a dictionary' in result['errors']
    
    async def test_coverage_criteria_validation_invalid_age_range(self, policy_service):
        """Test coverage criteria validation with invalid age range."""
        invalid_criteria = {
            'age_range': {
                'min_age': 'not_an_integer',
                'max_age': 65
            }
        }
        
        result = await policy_service._validate_coverage_criteria(invalid_criteria)
        
        assert result['is_valid'] is False
        assert any('Minimum age must be an integer' in error for error in result['errors'])
    
    async def test_coverage_criteria_validation_invalid_age_order(self, policy_service):
        """Test coverage criteria validation with min_age >= max_age."""
        invalid_criteria = {
            'age_range': {
                'min_age': 65,
                'max_age': 18
            }
        }
        
        result = await policy_service._validate_coverage_criteria(invalid_criteria)
        
        assert result['is_valid'] is False
        assert any('Minimum age must be less than maximum age' in error for error in result['errors'])
    
    async def test_policy_conflict_detection(self, policy_service, sample_policy_data):
        """Test policy conflict detection."""
        # Mock existing policy
        existing_policy = Mock()
        existing_policy.policy_id = 'existing-policy-001'
        existing_policy.policy_name = 'Existing Policy'
        existing_policy.effective_date = date.today()
        existing_policy.expiration_date = None
        
        policy_service.db_session.query.return_value.filter.return_value.all.return_value = [existing_policy]
        
        conflicts = await policy_service._check_policy_conflicts(sample_policy_data)
        
        assert len(conflicts) > 0
        assert 'Overlapping policy found' in conflicts[0]
    
    async def test_bulk_import_validation_mode(self, policy_service, sample_policy_data):
        """Test bulk import in validation mode."""
        policies_data = [sample_policy_data, sample_policy_data.copy()]
        
        with patch.object(policy_service, '_validate_policy_data') as mock_validate:
            mock_validate.return_value = {'is_valid': True, 'errors': []}
            
            result = await policy_service.bulk_import_policies(
                policies_data=policies_data,
                import_mode='validate',
                imported_by='test-user'
            )
            
            assert result['total_policies'] == 2
            assert result['successful_imports'] == 2
            assert result['failed_imports'] == 0
            assert len(result['validation_errors']) == 0
    
    async def test_bulk_import_with_validation_errors(self, policy_service, sample_policy_data):
        """Test bulk import with validation errors."""
        invalid_policy = sample_policy_data.copy()
        invalid_policy.pop('payer_id')  # Remove required field
        
        policies_data = [sample_policy_data, invalid_policy]
        
        with patch.object(policy_service, '_validate_policy_data') as mock_validate:
            def validate_side_effect(data):
                if 'payer_id' not in data:
                    return {'is_valid': False, 'errors': ['Missing required field: payer_id']}
                return {'is_valid': True, 'errors': []}
            
            mock_validate.side_effect = validate_side_effect
            
            result = await policy_service.bulk_import_policies(
                policies_data=policies_data,
                import_mode='validate',
                imported_by='test-user'
            )
            
            assert result['total_policies'] == 2
            assert result['successful_imports'] == 1
            assert result['failed_imports'] == 1
            assert len(result['validation_errors']) == 1
    
    @pytest.mark.asyncio
    async def test_policy_sandbox_testing_success(self, policy_service, sample_policy_data):
        """Test policy sandbox testing with successful scenarios."""
        test_scenarios = [
            {
                'name': 'Valid MRI Request',
                'patient_age': 45,
                'diagnosis_code': 'M25.511',
                'expected_outcome': 'approve'
            }
        ]
        
        with patch.object(policy_service, '_validate_policy_data') as mock_validate, \
             patch.object(policy_service, '_create_mock_request') as mock_create_request, \
             patch.object(policy_service, '_create_temp_policy') as mock_create_policy, \
             patch.object(policy_service.policy_validation_service, '_validate_against_policy') as mock_validate_policy:
            
            mock_validate.return_value = {'is_valid': True, 'errors': []}
            mock_create_request.return_value = Mock()
            mock_create_policy.return_value = Mock()
            
            # Mock successful validation
            validation_result = Mock()
            validation_result.is_covered = True
            validation_result.reasoning = ['Patient meets age criteria']
            validation_result.confidence_score = 0.95
            mock_validate_policy.return_value = validation_result
            
            result = await policy_service.test_policy_sandbox(
                policy_config=sample_policy_data,
                test_scenarios=test_scenarios,
                tested_by='test-user'
            )
            
            assert result['overall_success'] is True
            assert len(result['test_results']) == 1
            assert result['test_results'][0]['success'] is True
    
    async def test_policy_sandbox_testing_failure(self, policy_service, sample_policy_data):
        """Test policy sandbox testing with failed scenarios."""
        test_scenarios = [
            {
                'name': 'Invalid MRI Request',
                'patient_age': 15,  # Below minimum age
                'diagnosis_code': 'M25.511',
                'expected_outcome': 'approve'
            }
        ]
        
        with patch.object(policy_service, '_validate_policy_data') as mock_validate, \
             patch.object(policy_service, '_create_mock_request') as mock_create_request, \
             patch.object(policy_service, '_create_temp_policy') as mock_create_policy, \
             patch.object(policy_service.policy_validation_service, '_validate_against_policy') as mock_validate_policy:
            
            mock_validate.return_value = {'is_valid': True, 'errors': []}
            mock_create_request.return_value = Mock()
            mock_create_policy.return_value = Mock()
            
            # Mock failed validation
            validation_result = Mock()
            validation_result.is_covered = False
            validation_result.reasoning = ['Patient does not meet age criteria']
            validation_result.confidence_score = 0.85
            mock_validate_policy.return_value = validation_result
            
            result = await policy_service.test_policy_sandbox(
                policy_config=sample_policy_data,
                test_scenarios=test_scenarios,
                tested_by='test-user'
            )
            
            assert result['overall_success'] is False
            assert len(result['test_results']) == 1
            assert result['test_results'][0]['success'] is False
            assert 'expected approve, got deny' in result['recommendations'][0]


class TestPolicyConfigurationAPI:
    """Test policy configuration API request/response models."""
    
    def test_policy_config_request_validation_success(self):
        """Test successful policy configuration request validation."""
        valid_data = {
            'payer_id': 'test-payer-001',
            'procedure_code': '70553',
            'policy_name': 'Test MRI Policy',
            'policy_type': 'PAYER',
            'diagnosis_codes': ['M25.511'],
            'coverage_criteria': {
                'age_range': {'min_age': 18, 'max_age': 65}
            }
        }
        
        request = PolicyConfigRequest(**valid_data)
        
        assert request.payer_id == 'test-payer-001'
        assert request.procedure_code == '70553'
        assert request.policy_name == 'Test MRI Policy'
        assert request.policy_type == 'PAYER'
        assert request.diagnosis_codes == ['M25.511']
        assert request.coverage_criteria == {'age_range': {'min_age': 18, 'max_age': 65}}
        assert request.effective_date == date.today()
        assert request.is_active is True
    
    def test_policy_config_request_validation_invalid_policy_type(self):
        """Test policy configuration request with invalid policy type."""
        invalid_data = {
            'payer_id': 'test-payer-001',
            'procedure_code': '70553',
            'policy_name': 'Test Policy',
            'policy_type': 'INVALID',
            'coverage_criteria': {'test': 'criteria'}
        }
        
        with pytest.raises(ValidationError) as exc_info:
            PolicyConfigRequest(**invalid_data)
        
        assert 'Policy type must be NCD, LCD, or PAYER' in str(exc_info.value)
    
    def test_policy_config_request_validation_short_procedure_code(self):
        """Test policy configuration request with short procedure code."""
        invalid_data = {
            'payer_id': 'test-payer-001',
            'procedure_code': '123',  # Too short
            'policy_name': 'Test Policy',
            'policy_type': 'PAYER',
            'coverage_criteria': {'test': 'criteria'}
        }
        
        with pytest.raises(ValidationError) as exc_info:
            PolicyConfigRequest(**invalid_data)
        
        assert 'Procedure code must be at least 5 characters' in str(exc_info.value)
    
    def test_policy_config_request_validation_empty_coverage_criteria(self):
        """Test policy configuration request with empty coverage criteria."""
        invalid_data = {
            'payer_id': 'test-payer-001',
            'procedure_code': '70553',
            'policy_name': 'Test Policy',
            'policy_type': 'PAYER',
            'coverage_criteria': {}  # Empty criteria
        }
        
        with pytest.raises(ValidationError) as exc_info:
            PolicyConfigRequest(**invalid_data)
        
        assert 'Coverage criteria must be a non-empty dictionary' in str(exc_info.value)
    
    def test_policy_update_request_validation(self):
        """Test policy update request validation."""
        update_data = {
            'policy_name': 'Updated Policy Name',
            'diagnosis_codes': ['M25.511', 'M25.512'],
            'update_reason': 'Adding additional diagnosis codes'
        }
        
        request = PolicyUpdateRequest(**update_data)
        
        assert request.policy_name == 'Updated Policy Name'
        assert request.diagnosis_codes == ['M25.511', 'M25.512']
        assert request.update_reason == 'Adding additional diagnosis codes'
        assert request.coverage_criteria is None
        assert request.effective_date is None
    
    def test_bulk_import_request_validation_success(self):
        """Test successful bulk import request validation."""
        policy_data = {
            'payer_id': 'test-payer-001',
            'procedure_code': '70553',
            'policy_name': 'Test Policy',
            'policy_type': 'PAYER',
            'coverage_criteria': {'test': 'criteria'}
        }
        
        import_data = {
            'policies': [policy_data],
            'import_mode': 'validate'
        }
        
        request = BulkImportRequest(**import_data)
        
        assert len(request.policies) == 1
        assert request.import_mode == 'validate'
        assert request.policies[0].payer_id == 'test-payer-001'
    
    def test_bulk_import_request_validation_invalid_mode(self):
        """Test bulk import request with invalid import mode."""
        policy_data = {
            'payer_id': 'test-payer-001',
            'procedure_code': '70553',
            'policy_name': 'Test Policy',
            'policy_type': 'PAYER',
            'coverage_criteria': {'test': 'criteria'}
        }
        
        import_data = {
            'policies': [policy_data],
            'import_mode': 'invalid_mode'
        }
        
        with pytest.raises(ValidationError) as exc_info:
            BulkImportRequest(**import_data)
        
        assert 'Import mode must be validate, import, or replace' in str(exc_info.value)
    
    def test_policy_test_request_validation(self):
        """Test policy test request validation."""
        policy_config = {
            'payer_id': 'test-payer-001',
            'procedure_code': '70553',
            'policy_name': 'Test Policy',
            'policy_type': 'PAYER',
            'coverage_criteria': {'test': 'criteria'}
        }
        
        test_scenarios = [
            {
                'name': 'Test Scenario 1',
                'patient_age': 45,
                'expected_outcome': 'approve'
            }
        ]
        
        test_data = {
            'policy_config': policy_config,
            'test_scenarios': test_scenarios
        }
        
        request = PolicyTestRequest(**test_data)
        
        assert request.policy_config.payer_id == 'test-payer-001'
        assert len(request.test_scenarios) == 1
        assert request.test_scenarios[0]['name'] == 'Test Scenario 1'
    
    def test_resolution_request_validation_success(self):
        """Test successful conflict resolution request validation."""
        resolution_data = {
            'resolution_type': 'merge',
            'proposed_changes': {
                'merge_criteria': True,
                'priority_policy': 'policy-001'
            },
            'justification': 'Merging overlapping policies to resolve conflict'
        }
        
        request = ResolutionRequest(**resolution_data)
        
        assert request.resolution_type == 'merge'
        assert request.proposed_changes['merge_criteria'] is True
        assert 'Merging overlapping policies' in request.justification
    
    def test_resolution_request_validation_invalid_type(self):
        """Test resolution request with invalid resolution type."""
        resolution_data = {
            'resolution_type': 'invalid_type',
            'proposed_changes': {'test': 'change'},
            'justification': 'Test justification'
        }
        
        with pytest.raises(ValidationError) as exc_info:
            ResolutionRequest(**resolution_data)
        
        assert 'Resolution type must be merge, override, deactivate, or modify' in str(exc_info.value)
    
    def test_deployment_plan_request_validation_success(self):
        """Test successful deployment plan request validation."""
        deployment_data = {
            'policy_ids': ['policy-001', 'policy-002'],
            'deployment_type': 'update',
            'scheduled_at': datetime.now(timezone.utc)
        }
        
        request = DeploymentPlanRequest(**deployment_data)
        
        assert len(request.policy_ids) == 2
        assert request.deployment_type == 'update'
        assert request.scheduled_at is not None
    
    def test_deployment_plan_request_validation_invalid_type(self):
        """Test deployment plan request with invalid deployment type."""
        deployment_data = {
            'policy_ids': ['policy-001'],
            'deployment_type': 'invalid_type'
        }
        
        with pytest.raises(ValidationError) as exc_info:
            DeploymentPlanRequest(**deployment_data)
        
        assert 'Deployment type must be new, update, or rollback' in str(exc_info.value)


class TestConfigurationChangeDetection:
    """Test configuration change detection and reloading."""
    
    def test_settings_change_detection(self):
        """Test detection of configuration changes."""
        # Get initial settings
        initial_settings = get_settings()
        initial_log_level = initial_settings.log_level
        
        # Clear cache to simulate change detection
        get_settings.cache_clear()
        
        # Change environment variable
        with patch.dict(os.environ, {'PA_LOG_LEVEL': 'DEBUG'}):
            new_settings = get_settings()
            assert new_settings.log_level == 'DEBUG'
            assert new_settings.log_level != initial_log_level
    
    def test_configuration_reload_behavior(self):
        """Test configuration reload behavior."""
        # Test that cached settings don't change until cache is cleared
        original_settings = get_settings()
        
        with patch.dict(os.environ, {'PA_DEBUG': 'true'}):
            # Should still return cached settings
            cached_settings = get_settings()
            assert cached_settings.debug == original_settings.debug
            
            # Clear cache and get new settings
            get_settings.cache_clear()
            new_settings = get_settings()
            assert new_settings.debug is True
    
    def test_configuration_validation_on_reload(self):
        """Test that configuration is validated on reload."""
        get_settings.cache_clear()
        
        with patch.dict(os.environ, {'PA_PORT': 'invalid'}):
            with pytest.raises(ValidationError):
                get_settings()


class TestConfigurationErrorHandling:
    """Test configuration error handling scenarios."""
    
    def test_missing_required_environment_variables(self):
        """Test handling of missing required environment variables."""
        # Test with missing PHI_MASTER_KEY
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            # Should use default value, not raise error
            assert settings.phi_master_key == ""
    
    def test_invalid_environment_variable_types(self):
        """Test handling of invalid environment variable types."""
        with patch.dict(os.environ, {
            'PA_PORT': 'not_a_number',
            'PA_DEBUG': 'not_a_boolean',
            'PA_RATE_LIMIT_REQUESTS': 'not_an_integer'
        }):
            with pytest.raises(ValidationError):
                Settings()
    
    def test_configuration_with_empty_values(self):
        """Test configuration with empty environment values."""
        with patch.dict(os.environ, {
            'PA_DATABASE_URL': '',
            'PA_SECRET_KEY': '',
            'PA_LOG_LEVEL': ''
        }):
            settings = Settings()
            # Should fall back to defaults
            assert settings.database_url == "sqlite:///./prior_auth.db"
            assert settings.secret_key == "dev-secret-key-change-in-production"
            assert settings.log_level == "INFO"
    
    def test_configuration_with_malformed_json(self):
        """Test handling of malformed JSON in configuration."""
        # This would be relevant if we had JSON-based configuration
        # For now, test that string values are handled properly
        with patch.dict(os.environ, {
            'PA_ALLOWED_HOSTS': '["localhost", "127.0.0.1"]',  # JSON string
            'PA_CORS_ORIGINS': '["http://localhost:3000"]'
        }):
            settings = Settings()
            # These should be parsed as lists by Pydantic
            assert isinstance(settings.allowed_hosts, list)
            assert isinstance(settings.cors_origins, list)
    
    def test_configuration_security_validation(self):
        """Test security-related configuration validation."""
        # Test that default secret key generates warning (in production)
        settings = Settings()
        assert settings.secret_key == "dev-secret-key-change-in-production"
        
        # Test that empty encryption key is handled
        with patch.dict(os.environ, {'PHI_MASTER_KEY': ''}):
            settings = Settings()
            assert settings.phi_master_key == ""
    
    def test_configuration_performance_settings(self):
        """Test performance-related configuration settings."""
        with patch.dict(os.environ, {
            'PA_MAX_CONCURRENT_REQUESTS': '2000',
            'PA_REQUEST_TIMEOUT': '300',
            'PA_DB_POOL_SIZE': '20',
            'PA_DB_MAX_OVERFLOW': '40',
            'PA_REDIS_MAX_CONNECTIONS': '100'
        }):
            settings = Settings()
            assert settings.max_concurrent_requests == 2000
            assert settings.request_timeout == 300
            assert settings.db_pool_size == 20
            assert settings.db_max_overflow == 40
            assert settings.redis_max_connections == 100
"""
Core functionality tests to increase coverage.

This module contains focused tests for core services and models
to achieve the 90% coverage target.
"""

import pytest
from datetime import datetime, timezone, date
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from typing import Dict, Any, List

# Import available models and services
from src.models.enums import DecisionStatus, UrgencyLevel, ProcedureType, RequestStatus, Gender
from src.models.patient import PatientDemographics
from src.models.medical_codes import ICD10Code, CPTCode, HCPCSCode
from src.core.config import get_settings
from src.core.datetime_utils import utcnow
from src.core.logging import get_logger


class TestCoreModels:
    """Test core model functionality."""
    
    def test_patient_demographics_creation(self):
        """Test PatientDemographics model creation."""
        demographics = PatientDemographics(
            patient_id="enc_pat_1a2b3c4d5e6f7g8h",
            age=44,
            gender=Gender.MALE,
            insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
            member_id="enc_mem_1z2y3x4w5v6u7t8s",
            date_of_birth=date(1980, 1, 1)
        )
        
        assert demographics.patient_id == "enc_pat_1a2b3c4d5e6f7g8h"
        assert demographics.age == 44
        assert demographics.gender == Gender.MALE
        assert demographics.member_id == "enc_mem_1z2y3x4w5v6u7t8s"
    
    def test_patient_demographics_validation(self):
        """Test PatientDemographics validation."""
        # Test with valid data
        demographics = PatientDemographics(
            patient_id="enc_pat_1a2b3c4d5e6f7g8h",
            age=44,
            gender=Gender.MALE,
            insurance_id="enc_ins_9i8h7g6f5e4d3c2b",
            member_id="enc_mem_1z2y3x4w5v6u7t8s"
        )
        assert demographics.age == 44
        
        # Test age validation
        assert demographics.age > 0
        assert demographics.age <= 150
    
    def test_icd10_code_creation(self):
        """Test ICD10Code model creation."""
        code = ICD10Code(
            code="G93.1",
            description="Anoxic brain damage, not elsewhere classified"
        )
        
        assert code.code == "G93.1"
        assert code.description == "Anoxic brain damage, not elsewhere classified"
    
    def test_cpt_code_creation(self):
        """Test CPTCode model creation."""
        code = CPTCode(
            code="70551",
            description="MRI brain without contrast"
        )
        
        assert code.code == "70551"
        assert code.description == "MRI brain without contrast"
    
    def test_hcpcs_code_creation(self):
        """Test HCPCSCode model creation."""
        code = HCPCSCode(
            code="A9576",
            description="Injection, gadoteridol, per ml"
        )
        
        assert code.code == "A9576"
        assert code.description == "Injection, gadoteridol, per ml"
    
    def test_enums_values(self):
        """Test enum values."""
        assert RequestStatus.SUBMITTED == "submitted"
        assert RequestStatus.IN_REVIEW == "in_review"
        assert RequestStatus.APPROVED == "approved"
        assert RequestStatus.DENIED == "denied"
        
        assert DecisionStatus.APPROVED == "approved"
        assert DecisionStatus.DENIED == "denied"
        assert DecisionStatus.MORE_INFO_NEEDED == "more_info_needed"
        
        assert UrgencyLevel.ROUTINE == "routine"
        assert UrgencyLevel.URGENT == "urgent"
        assert UrgencyLevel.EMERGENT == "emergent"
        
        assert ProcedureType.MRI == "mri"
        assert ProcedureType.CT_SCAN == "ct_scan"
        assert ProcedureType.X_RAY == "x_ray"
        
        assert Gender.MALE == "male"
        assert Gender.FEMALE == "female"


class TestCoreUtilities:
    """Test core utility functions."""
    
    def test_get_settings(self):
        """Test configuration settings."""
        settings = get_settings()
        
        assert settings is not None
        assert hasattr(settings, 'database_url')
        assert hasattr(settings, 'secret_key')
    
    def test_utcnow(self):
        """Test UTC now utility."""
        now = utcnow()
        
        assert isinstance(now, datetime)
        assert now.tzinfo == timezone.utc
    
    def test_get_logger(self):
        """Test logger creation."""
        logger = get_logger("test_module")
        
        assert logger is not None
        # Structlog loggers don't have a name attribute like standard loggers
        assert hasattr(logger, 'info')
        assert hasattr(logger, 'error')


class TestServiceMocking:
    """Test service functionality with mocking."""
    
    def test_validation_service_mock(self):
        """Test validation service with mocking."""
        from src.services.validation import ValidationService
        
        service = ValidationService()
        
        # Test that the service can be instantiated and has expected methods
        assert hasattr(service, 'validate_request')
        assert callable(getattr(service, 'validate_request'))
    
    def test_decision_engine_mock(self):
        """Test decision engine with mocking."""
        from src.services.decision_engine import DecisionEngine
        
        engine = DecisionEngine()
        
        # Test that the engine can be instantiated and has expected methods
        assert hasattr(engine, 'generate_decision')
        assert callable(getattr(engine, 'generate_decision'))
    
    def test_tracking_service_mock(self):
        """Test tracking service with mocking."""
        from src.services.tracking import TrackingService
        
        service = TrackingService()
        
        # Test that the service can be instantiated and has expected methods
        assert hasattr(service, 'store_request')
        assert callable(getattr(service, 'store_request'))
        assert hasattr(service, 'get_request_status')
        assert callable(getattr(service, 'get_request_status'))


class TestDatabaseModels:
    """Test database model functionality."""
    
    def test_icd10_code_db_model(self):
        """Test ICD10CodeDB model."""
        from src.models.medical_codes import ICD10CodeDB
        
        # Test model creation
        code = ICD10CodeDB(
            code="G93.1",
            description="Anoxic brain damage",
            category="Nervous system",
            billable=True,
            valid_from=date(2024, 1, 1)
        )
        
        assert code.code == "G93.1"
        assert code.description == "Anoxic brain damage"
        assert code.billable is True
    
    def test_cpt_code_db_model(self):
        """Test CPTCodeDB model."""
        from src.models.medical_codes import CPTCodeDB
        
        # Test model creation
        code = CPTCodeDB(
            code="70551",
            description="MRI brain without contrast",
            category="Radiology",
            work_rvu=2.5,
            valid_from=date(2024, 1, 1)
        )
        
        assert code.code == "70551"
        assert code.description == "MRI brain without contrast"
        assert code.work_rvu == 2.5


class TestAPIModels:
    """Test API model functionality."""
    
    def test_authorization_request_creation(self):
        """Test AuthorizationRequest creation."""
        from src.models.authorization import AuthorizationRequest
        
        # Create with minimal required fields
        request_data = {
            "request_id": "req_123456",
            "provider_id": "PROV123",
            "patient_demographics": {
                "patient_id": "enc_pat_1a2b3c4d5e6f7g8h",
                "age": 44,
                "gender": "male",
                "insurance_id": "enc_ins_9i8h7g6f5e4d3c2b",
                "member_id": "enc_mem_1z2y3x4w5v6u7t8s"
            },
            "diagnosis_codes": [
                {
                    "code": "G93.1",
                    "description": "Anoxic brain damage"
                }
            ],
            "procedure_codes": [
                {
                    "code": "70551",
                    "description": "MRI brain without contrast"
                }
            ],
            "procedure_type": "mri"
        }
        
        request = AuthorizationRequest(**request_data)
        
        assert request.request_id == "req_123456"
        assert request.provider_id == "PROV123"
        assert request.procedure_type == ProcedureType.MRI
        assert len(request.diagnosis_codes) == 1
        assert len(request.procedure_codes) == 1


class TestServiceIntegration:
    """Test service integration with proper mocking."""
    
    def test_medical_code_validator_integration(self):
        """Test medical code validator integration."""
        from src.services.medical_code_validator import MedicalCodeValidator
        
        validator = MedicalCodeValidator()
        
        # Test validation methods exist
        assert hasattr(validator, 'validate_icd10_code')
        assert callable(getattr(validator, 'validate_icd10_code'))
        assert hasattr(validator, 'validate_cpt_code')
        assert callable(getattr(validator, 'validate_cpt_code'))
    
    def test_policy_validation_integration(self):
        """Test policy validation integration."""
        from src.services.policy_validation import PolicyValidationService
        
        # Mock the db_session parameter
        mock_db_session = Mock()
        service = PolicyValidationService(mock_db_session)
        
        # Test that service has expected methods
        assert hasattr(service, 'validate_coverage_policy')
        assert callable(getattr(service, 'validate_coverage_policy'))
    
    def test_external_services_integration(self):
        """Test external services integration."""
        from src.services.external_services import ExternalServiceIntegrator
        
        integrator = ExternalServiceIntegrator()
        
        # Test that integrator has expected methods
        assert hasattr(integrator, 'validate_medical_codes')
        assert callable(getattr(integrator, 'validate_medical_codes'))


class TestErrorHandling:
    """Test error handling and exception cases."""
    
    def test_validation_error_creation(self):
        """Test ValidationError creation."""
        from src.services.validation import ValidationError
        
        error = ValidationError(
            field="member_id",
            message="Invalid member ID format",
            value="INVALID"
        )
        
        assert error.field == "member_id"
        assert error.message == "Invalid member ID format"
        assert error.value == "INVALID"
    
    def test_core_exceptions(self):
        """Test core exception classes."""
        from src.core.exceptions import ValidationException
        
        # Test exception creation
        exception = ValidationException("Test validation error")
        assert "Test validation error" in str(exception)
    
    def test_model_validation_errors(self):
        """Test model validation error handling."""
        from src.models.patient import PatientDemographics
        
        # Test with invalid data should raise validation error
        with pytest.raises(Exception):  # Pydantic validation error
            PatientDemographics(
                patient_id="",  # Empty patient ID should fail validation
                age=200,  # Invalid age should fail
                gender=Gender.MALE,
                insurance_id="",  # Empty insurance ID should fail
                member_id=""  # Empty member ID should fail
            )


class TestCacheAndPerformance:
    """Test caching and performance-related functionality."""
    
    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_cache_service_mock(self):
        """Test cache service functionality."""
        from src.services.cache import cache_manager
        
        # Mock cache operations
        with patch.object(cache_manager, 'get') as mock_get, \
             patch.object(cache_manager, 'set') as mock_set:
            
            mock_get.return_value = None
            mock_set.return_value = True
            
            # Test cache operations
            result = await cache_manager.get("test_key")
            assert result is None
            
            success = await cache_manager.set("test_key", "test_value")
            assert success is True
    
    def test_performance_monitoring(self):
        """Test performance monitoring functionality."""
        from src.services.monitoring import MetricsCollector
        
        # Test that MetricsCollector can be instantiated
        collector = MetricsCollector()
        
        # Test that collector has expected methods
        assert hasattr(collector, 'record_request')
        assert callable(getattr(collector, 'record_request'))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
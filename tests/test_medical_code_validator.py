"""
Tests for the medical code validator service.

This module tests medical code validation, format checking, and
code existence verification for ICD-10, CPT, and HCPCS codes.
"""

import pytest
from src.services.validation import ValidationResult
from datetime import datetime, date
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any, List

from src.services.medical_code_validator import MedicalCodeValidator, CodeValidationResult
from src.models.medical_codes import ICD10Code, CPTCode
from src.models.enums import MedicalCodeType


class TestMedicalCodeValidator:
    """Test medical code validator functionality."""
    
    @pytest.fixture
    def validator(self):
        """Create medical code validator instance."""
        return MedicalCodeValidator()
    
    @pytest.mark.asyncio

    
    async def test_validate_icd10_code_valid(self, validator):
        """Test ICD-10 code validation for valid code."""
        with patch.object(validator, '_check_code_database') as mock_db:
            mock_db.return_value = {
                "valid": True,
                "description": "Anoxic brain damage, not elsewhere classified",
                "category": "Diseases of the nervous system"
            }
            
            result = await validator.validate_code("G93.1", MedicalCodeType.ICD10)
            
            assert isinstance(result, CodeValidationResult)
            assert result.is_valid is True
            assert result.code == "G93.1"
            assert result.code_type == MedicalCodeType.ICD10
            assert result.description is not None
    
    @pytest.mark.asyncio

    
    async def test_validate_icd10_code_invalid_format(self, validator):
        """Test ICD-10 code validation for invalid format."""
        result = await validator.validate_code("INVALID", MedicalCodeType.ICD10)
        
        assert isinstance(result, CodeValidationResult)
        assert result.is_valid is False
        assert "format" in result.error_message.lower()
    
    @pytest.mark.asyncio

    
    async def test_validate_icd10_code_not_found(self, validator):
        """Test ICD-10 code validation for code not found."""
        with patch.object(validator, '_check_code_database') as mock_db:
            mock_db.return_value = {"valid": False, "description": None}
            
            result = await validator.validate_code("Z99.99", MedicalCodeType.ICD10)
            
            assert isinstance(result, CodeValidationResult)
            assert result.is_valid is False
            assert "not found" in result.error_message.lower()
    
    @pytest.mark.asyncio

    
    async def test_validate_cpt_code_valid(self, validator):
        """Test CPT code validation for valid code."""
        with patch.object(validator, '_check_code_database') as mock_db:
            mock_db.return_value = {
                "valid": True,
                "description": "MRI brain without contrast",
                "category": "Radiology"
            }
            
            result = await validator.validate_code("70551", MedicalCodeType.CPT)
            
            assert isinstance(result, CodeValidationResult)
            assert result.is_valid is True
            assert result.code == "70551"
            assert result.code_type == MedicalCodeType.CPT
            assert result.description is not None
    
    @pytest.mark.asyncio

    
    async def test_validate_cpt_code_invalid_format(self, validator):
        """Test CPT code validation for invalid format."""
        result = await validator.validate_code("123", MedicalCodeType.CPT)
        
        assert isinstance(result, CodeValidationResult)
        assert result.is_valid is False
        assert "format" in result.error_message.lower()
    
    @pytest.mark.asyncio

    
    async def test_validate_hcpcs_code_valid(self, validator):
        """Test HCPCS code validation for valid code."""
        with patch.object(validator, '_check_code_database') as mock_db:
            mock_db.return_value = {
                "valid": True,
                "description": "Injection, contrast material",
                "category": "Drugs"
            }
            
            result = await validator.validate_code("A9576", MedicalCodeType.HCPCS)
            
            assert isinstance(result, CodeValidationResult)
            assert result.is_valid is True
            assert result.code == "A9576"
            assert result.code_type == MedicalCodeType.HCPCS
            assert result.description is not None
    
    @pytest.mark.asyncio

    
    async def test_batch_validate_codes(self, validator):
        """Test batch validation of multiple codes."""
        codes = [
            ("G93.1", MedicalCodeType.ICD10),
            ("70551", MedicalCodeType.CPT),
            ("A9576", MedicalCodeType.HCPCS)
        ]
        
        with patch.object(validator, '_check_code_database') as mock_db:
            mock_db.return_value = {"valid": True, "description": "Valid code"}
            
            results = await validator.batch_validate_codes(codes)
            
            assert isinstance(results, list)
            assert len(results) == 3
            assert all(isinstance(result, CodeValidationResult) for result in results)
            assert all(result.is_valid for result in results)
    
    @pytest.mark.asyncio
    async def test_batch_validate_codes_mixed_results(self, validator):
        """Test batch validation with mixed valid/invalid codes."""
        codes = [
            ("G93.1", MedicalCodeType.ICD10),  # Valid
            ("INVALID", MedicalCodeType.ICD10),  # Invalid format
            ("70551", MedicalCodeType.CPT)  # Valid
        ]
        
        def mock_db_side_effect(code, code_type):
            if code == "G93.1" or code == "70551":
                return {"valid": True, "description": "Valid code"}
            return {"valid": False, "description": None}
        
        with patch.object(validator, '_check_code_database', side_effect=mock_db_side_effect):
            results = await validator.batch_validate_codes(codes)
            
            assert isinstance(results, list)
            assert len(results) == 3
            assert results[0].is_valid is True  # G93.1
            assert results[1].is_valid is False  # INVALID
            assert results[2].is_valid is True  # 70551
    
    def test_validate_icd10_format_valid_codes(self, validator):
        """Test ICD-10 format validation for valid codes."""
        valid_codes = [
            "G93.1",
            "M79.3",
            "Z00.00",
            "S72.001A",
            "T36.0X1A"
        ]
        
        for code in valid_codes:
            result = validator._validate_icd10_format(code)
            assert result is True, f"Code {code} should be valid"
    
    def test_validate_icd10_format_invalid_codes(self, validator):
        """Test ICD-10 format validation for invalid codes."""
        invalid_codes = [
            "INVALID",
            "123",
            "G93",
            "G93.1.2",
            "G93.1A.B",
            ""
        ]
        
        for code in invalid_codes:
            result = validator._validate_icd10_format(code)
            assert result is False, f"Code {code} should be invalid"
    
    def test_validate_cpt_format_valid_codes(self, validator):
        """Test CPT format validation for valid codes."""
        valid_codes = [
            "70551",
            "99213",
            "12345",
            "00100"
        ]
        
        for code in valid_codes:
            result = validator._validate_cpt_format(code)
            assert result is True, f"Code {code} should be valid"
    
    def test_validate_cpt_format_invalid_codes(self, validator):
        """Test CPT format validation for invalid codes."""
        invalid_codes = [
            "INVALID",
            "123",
            "123456",
            "7055A",
            ""
        ]
        
        for code in invalid_codes:
            result = validator._validate_cpt_format(code)
            assert result is False, f"Code {code} should be invalid"
    
    def test_validate_hcpcs_format_valid_codes(self, validator):
        """Test HCPCS format validation for valid codes."""
        valid_codes = [
            "A9576",
            "J1234",
            "L5678",
            "Q9999"
        ]
        
        for code in valid_codes:
            result = validator._validate_hcpcs_format(code)
            assert result is True, f"Code {code} should be valid"
    
    def test_validate_hcpcs_format_invalid_codes(self, validator):
        """Test HCPCS format validation for invalid codes."""
        invalid_codes = [
            "INVALID",
            "12345",
            "A123",
            "A12345",
            ""
        ]
        
        for code in invalid_codes:
            result = validator._validate_hcpcs_format(code)
            assert result is False, f"Code {code} should be invalid"
    
    @pytest.mark.asyncio

    
    async def test_check_code_database_found(self, validator):
        """Test database code lookup for existing code."""
        with patch.object(validator, 'code_repository') as mock_repo:
            mock_repo.get_code_info.return_value = {
                "code": "G93.1",
                "description": "Anoxic brain damage",
                "category": "Nervous system",
                "is_active": True
            }
            
            result = await validator._check_code_database("G93.1", MedicalCodeType.ICD10)
            
            assert result["valid"] is True
            assert result["description"] == "Anoxic brain damage"
            assert result["category"] == "Nervous system"
    
    @pytest.mark.asyncio

    
    async def test_check_code_database_not_found(self, validator):
        """Test database code lookup for non-existing code."""
        with patch.object(validator, 'code_repository') as mock_repo:
            mock_repo.get_code_info.return_value = None
            
            result = await validator._check_code_database("INVALID", MedicalCodeType.ICD10)
            
            assert result["valid"] is False
            assert result["description"] is None
    
    @pytest.mark.asyncio

    
    async def test_check_code_database_inactive(self, validator):
        """Test database code lookup for inactive code."""
        with patch.object(validator, 'code_repository') as mock_repo:
            mock_repo.get_code_info.return_value = {
                "code": "G93.1",
                "description": "Anoxic brain damage",
                "category": "Nervous system",
                "is_active": False
            }
            
            result = await validator._check_code_database("G93.1", MedicalCodeType.ICD10)
            
            assert result["valid"] is False
            assert "inactive" in result.get("reason", "").lower()
    
    @pytest.mark.asyncio

    
    async def test_get_code_suggestions_similar_codes(self, validator):
        """Test getting code suggestions for similar codes."""
        with patch.object(validator, 'code_repository') as mock_repo:
            mock_repo.find_similar_codes.return_value = [
                {"code": "G93.1", "description": "Anoxic brain damage", "similarity": 0.9},
                {"code": "G93.2", "description": "Other brain damage", "similarity": 0.8}
            ]
            
            suggestions = await validator.get_code_suggestions("G93", MedicalCodeType.ICD10)
            
            assert isinstance(suggestions, list)
            assert len(suggestions) == 2
            assert suggestions[0]["code"] == "G93.1"
            assert suggestions[0]["similarity"] == 0.9
    
    @pytest.mark.asyncio

    
    async def test_get_code_suggestions_no_matches(self, validator):
        """Test getting code suggestions when no similar codes found."""
        with patch.object(validator, 'code_repository') as mock_repo:
            mock_repo.find_similar_codes.return_value = []
            
            suggestions = await validator.get_code_suggestions("INVALID", MedicalCodeType.ICD10)
            
            assert isinstance(suggestions, list)
            assert len(suggestions) == 0
    
    @pytest.mark.asyncio

    
    async def test_validate_code_with_caching(self, validator):
        """Test code validation with caching."""
        with patch.object(validator, 'cache') as mock_cache, \
             patch.object(validator, '_check_code_database') as mock_db:
            
            # First call - cache miss
            mock_cache.get.return_value = None
            mock_db.return_value = {"valid": True, "description": "Valid code"}
            
            result1 = await validator.validate_code("G93.1", MedicalCodeType.ICD10)
            
            # Verify cache was checked and set
            mock_cache.get.assert_called_once()
            mock_cache.set.assert_called_once()
            
            # Second call - cache hit
            mock_cache.get.return_value = result1
            result2 = await validator.validate_code("G93.1", MedicalCodeType.ICD10)
            
            assert result1.code == result2.code
            assert result1.is_valid == result2.is_valid
    
    @pytest.mark.asyncio

    
    async def test_validate_code_with_version_check(self, validator):
        """Test code validation with version checking."""
        with patch.object(validator, '_check_code_version') as mock_version, \
             patch.object(validator, '_check_code_database') as mock_db:
            
            mock_version.return_value = {"current": True, "effective_date": "2024-01-01"}
            mock_db.return_value = {"valid": True, "description": "Valid code"}
            
            result = await validator.validate_code("G93.1", MedicalCodeType.ICD10, check_version=True)
            
            assert result.is_valid is True
            mock_version.assert_called_once_with("G93.1", MedicalCodeType.ICD10)
    
    @pytest.mark.asyncio

    
    async def test_validate_code_outdated_version(self, validator):
        """Test code validation with outdated version."""
        with patch.object(validator, '_check_code_version') as mock_version, \
             patch.object(validator, '_check_code_database') as mock_db:
            
            mock_version.return_value = {"current": False, "effective_date": "2020-01-01"}
            mock_db.return_value = {"valid": True, "description": "Valid code"}
            
            result = await validator.validate_code("G93.1", MedicalCodeType.ICD10, check_version=True)
            
            assert result.is_valid is False
            assert "outdated" in result.error_message.lower()
    
    def test_normalize_code_icd10(self, validator):
        """Test code normalization for ICD-10 codes."""
        test_cases = [
            ("g93.1", "G93.1"),
            ("G93.1", "G93.1"),
            ("g93.1a", "G93.1A"),
            ("G93.1A", "G93.1A")
        ]
        
        for input_code, expected in test_cases:
            result = validator._normalize_code(input_code, MedicalCodeType.ICD10)
            assert result == expected
    
    def test_normalize_code_cpt(self, validator):
        """Test code normalization for CPT codes."""
        test_cases = [
            ("70551", "70551"),
            ("7055", "07055"),  # Pad with leading zero
            ("99213", "99213")
        ]
        
        for input_code, expected in test_cases:
            result = validator._normalize_code(input_code, MedicalCodeType.CPT)
            assert result == expected
    
    def test_normalize_code_hcpcs(self, validator):
        """Test code normalization for HCPCS codes."""
        test_cases = [
            ("a9576", "A9576"),
            ("A9576", "A9576"),
            ("j1234", "J1234")
        ]
        
        for input_code, expected in test_cases:
            result = validator._normalize_code(input_code, MedicalCodeType.HCPCS)
            assert result == expected


class TestCodeValidationResult:
    """Test CodeValidationResult model."""
    
    def test_validation_result_valid(self):
        """Test CodeValidationResult for valid code."""
        result = CodeValidationResult(
            code="G93.1",
            code_type=MedicalCodeType.ICD10,
            is_valid=True,
            description="Anoxic brain damage",
            category="Nervous system"
        )
        
        assert result.code == "G93.1"
        assert result.code_type == MedicalCodeType.ICD10
        assert result.is_valid is True
        assert result.description == "Anoxic brain damage"
        assert result.error_message is None
    
    def test_validation_result_invalid(self):
        """Test CodeValidationResult for invalid code."""
        result = CodeValidationResult(
            code="INVALID",
            code_type=MedicalCodeType.ICD10,
            is_valid=False,
            error_message="Invalid code format"
        )
        
        assert result.code == "INVALID"
        assert result.code_type == MedicalCodeType.ICD10
        assert result.is_valid is False
        assert result.error_message == "Invalid code format"
        assert result.description is None
    
    def test_validation_result_serialization(self):
        """Test CodeValidationResult serialization."""
        result = CodeValidationResult(
            code="G93.1",
            code_type=MedicalCodeType.ICD10,
            is_valid=True,
            description="Anoxic brain damage"
        )
        
        serialized = result.dict()
        
        assert isinstance(serialized, dict)
        assert serialized["code"] == "G93.1"
        assert serialized["code_type"] == MedicalCodeType.ICD10
        assert serialized["is_valid"] is True
        assert serialized["description"] == "Anoxic brain damage"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
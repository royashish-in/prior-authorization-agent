"""
Unit tests for medical code validation engine.

Tests comprehensive medical code validation including caching,
external database integration, and suggestion functionality.
"""

import pytest
import asyncio
from datetime import datetime, timezone

from src.services.medical_code_validator import (
    MedicalCodeValidator, 
    ValidationResult, 
    CodeValidationResult,
    CacheEntry
)
from src.models.medical_codes import ICD10Code, CPTCode, HCPCSCode


class TestMedicalCodeValidator:
    """Test cases for MedicalCodeValidator."""
    
    @pytest.fixture
    def validator(self):
        """Create medical code validator instance."""
        return MedicalCodeValidator()
    
    @pytest.mark.asyncio
    async def test_validate_valid_icd10_codes(self, validator):
        """Test validation of valid ICD-10 codes."""
        valid_codes = [
            ICD10Code(code="M25.511", description="Pain in right shoulder"),
            ICD10Code(code="S72.001A", description="Fracture of unspecified part of neck of right femur, initial encounter"),
            ICD10Code(code="G93.1", description="Anoxic brain damage, not elsewhere classified")
        ]
        
        for code in valid_codes:
            result = await validator.validate_icd10_code(code)
            assert result.result == CodeValidationResult.VALID
            assert result.code == code.code
            assert result.description is not None
            assert result.effective_date is not None
    
    @pytest.mark.asyncio
    async def test_validate_invalid_icd10_codes(self, validator):
        """Test validation of invalid ICD-10 codes."""
        # Test codes that pass Pydantic validation but fail business validation
        invalid_codes = [
            ICD10Code(code="Z99.999", description="Non-existent code"),
            ICD10Code(code="X99.999", description="Non-existent code")
        ]
        
        for code in invalid_codes:
            result = await validator.validate_icd10_code(code)
            assert result.result in [CodeValidationResult.INVALID, CodeValidationResult.NOT_FOUND]
            assert result.code == code.code
            assert len(result.suggestions) > 0
    
    @pytest.mark.asyncio
    async def test_validate_valid_cpt_codes(self, validator):
        """Test validation of valid CPT codes."""
        valid_codes = [
            CPTCode(code="70551", description="MRI brain without contrast"),
            CPTCode(code="73221", description="MRI upper extremity without contrast"),
            CPTCode(code="72148", description="MRI lumbar spine without contrast")
        ]
        
        for code in valid_codes:
            result = await validator.validate_cpt_code(code)
            assert result.result == CodeValidationResult.VALID
            assert result.code == code.code
            assert result.description is not None
            assert result.effective_date is not None
    
    @pytest.mark.asyncio
    async def test_validate_invalid_cpt_codes(self, validator):
        """Test validation of invalid CPT codes."""
        # Test codes that pass Pydantic validation but fail business validation
        invalid_codes = [
            CPTCode(code="79999", description="Non-existent code"),  # Valid format, not in database
            CPTCode(code="70000", description="Non-existent code")   # Valid format, not in database
        ]
        
        for code in invalid_codes:
            result = await validator.validate_cpt_code(code)
            assert result.result in [CodeValidationResult.INVALID, CodeValidationResult.NOT_FOUND]
            assert result.code == code.code
            assert len(result.suggestions) > 0
    
    @pytest.mark.asyncio
    async def test_validate_valid_hcpcs_codes(self, validator):
        """Test validation of valid HCPCS codes."""
        valid_codes = [
            HCPCSCode(code="A0425", description="Ground mileage"),
            HCPCSCode(code="E0100", description="Cane"),
            HCPCSCode(code="L3000", description="Foot insert")
        ]
        
        for code in valid_codes:
            result = await validator.validate_hcpcs_code(code)
            assert result.result == CodeValidationResult.VALID
            assert result.code == code.code
            assert result.description is not None
            assert result.effective_date is not None
    
    @pytest.mark.asyncio
    async def test_validate_invalid_hcpcs_codes(self, validator):
        """Test validation of invalid HCPCS codes."""
        # Test codes that pass Pydantic validation but fail business validation
        invalid_codes = [
            HCPCSCode(code="Z9999", description="Non-existent code"),
            HCPCSCode(code="X1234", description="Non-existent code")
        ]
        
        for code in invalid_codes:
            result = await validator.validate_hcpcs_code(code)
            assert result.result in [CodeValidationResult.INVALID, CodeValidationResult.NOT_FOUND]
            assert result.code == code.code
            assert len(result.suggestions) > 0


class TestCachingFunctionality:
    """Test cases for caching functionality."""
    
    @pytest.fixture
    def validator(self):
        """Create medical code validator instance."""
        return MedicalCodeValidator()
    
    @pytest.mark.asyncio
    async def test_cache_hit_on_repeated_validation(self, validator):
        """Test that repeated validations use cache."""
        code = ICD10Code(code="M25.511", description="Pain in right shoulder")
        
        # First validation - should be cache miss
        result1 = await validator.validate_icd10_code(code)
        stats1 = validator.get_cache_stats()
        
        # Second validation - should be cache hit
        result2 = await validator.validate_icd10_code(code)
        stats2 = validator.get_cache_stats()
        
        assert result1.result == result2.result == CodeValidationResult.VALID
        assert stats2["cache_hits"] > stats1["cache_hits"]
        assert stats2["cache_size"] > 0
    
    @pytest.mark.asyncio
    async def test_batch_validation_performance(self, validator):
        """Test batch validation performance."""
        codes = [
            ("icd10", "M25.511"),
            ("cpt", "70551"),
            ("hcpcs", "A0425"),
            ("icd10", "G93.1"),
            ("cpt", "73221")
        ]
        
        results = await validator.validate_codes_batch(codes)
        
        assert len(results) == len(codes)
        for code_value in [code[1] for code in codes]:
            assert code_value in results
            assert results[code_value].result == CodeValidationResult.VALID
    
    def test_cache_expiration(self, validator):
        """Test cache entry expiration."""
        # Create an expired cache entry
        result = ValidationResult(
            code="TEST123",
            result=CodeValidationResult.VALID,
            description="Test code"
        )
        
        entry = CacheEntry(
            result=result,
            cached_at=datetime.now(timezone.utc),
            ttl_seconds=0  # Immediate expiration
        )
        
        assert entry.is_expired is True
        
        # Create a non-expired entry
        entry_valid = CacheEntry(
            result=result,
            cached_at=datetime.now(timezone.utc),
            ttl_seconds=3600  # 1 hour
        )
        
        assert entry_valid.is_expired is False
    
    def test_cache_statistics(self, validator):
        """Test cache statistics tracking."""
        stats = validator.get_cache_stats()
        
        assert "cache_hits" in stats
        assert "cache_misses" in stats
        assert "external_lookups" in stats
        assert "validation_requests" in stats
        assert "cache_size" in stats
        assert "frequent_cache_size" in stats
        assert "cache_hit_rate" in stats
        
        assert all(isinstance(value, (int, float)) for value in stats.values())
    
    def test_cache_clearing(self, validator):
        """Test cache clearing functionality."""
        # Add something to cache first
        validator._add_to_cache("test_key", ValidationResult(
            code="TEST",
            result=CodeValidationResult.VALID
        ))
        
        assert validator.get_cache_stats()["cache_size"] > 0
        
        validator.clear_cache()
        
        stats = validator.get_cache_stats()
        assert stats["cache_size"] == 0
        assert stats["frequent_cache_size"] == 0


class TestCodeSuggestions:
    """Test cases for code suggestion functionality."""
    
    @pytest.fixture
    def validator(self):
        """Create medical code validator instance."""
        return MedicalCodeValidator()
    
    def test_icd10_code_suggestions(self, validator):
        """Test ICD-10 code suggestions."""
        # Test suggestions for musculoskeletal codes
        suggestions = validator.get_code_suggestions("M25", "icd10", limit=3)
        assert len(suggestions) <= 3
        assert all("M25" in suggestion for suggestion in suggestions)
        
        # Test suggestions for invalid input
        suggestions = validator.get_code_suggestions("INVALID", "icd10", limit=5)
        assert len(suggestions) > 0
        assert all(" - " in suggestion for suggestion in suggestions)  # Format: "CODE - Description"
    
    def test_cpt_code_suggestions(self, validator):
        """Test CPT code suggestions."""
        # Test suggestions for brain MRI codes
        suggestions = validator.get_code_suggestions("705", "cpt", limit=3)
        assert len(suggestions) <= 3
        assert all("705" in suggestion for suggestion in suggestions)
        
        # Test suggestions for invalid input
        suggestions = validator.get_code_suggestions("99999", "cpt", limit=5)
        assert len(suggestions) > 0
        assert all(" - " in suggestion for suggestion in suggestions)
    
    def test_hcpcs_code_suggestions(self, validator):
        """Test HCPCS code suggestions."""
        # Test suggestions for ambulance codes
        suggestions = validator.get_code_suggestions("A04", "hcpcs", limit=3)
        assert len(suggestions) <= 3
        
        # Test suggestions for invalid input
        suggestions = validator.get_code_suggestions("INVALID", "hcpcs", limit=5)
        assert len(suggestions) > 0
        assert all(" - " in suggestion for suggestion in suggestions)
    
    def test_invalid_code_type_suggestions(self, validator):
        """Test suggestions for invalid code type."""
        suggestions = validator.get_code_suggestions("12345", "invalid_type", limit=5)
        assert len(suggestions) == 0


class TestFormatValidation:
    """Test cases for code format validation."""
    
    @pytest.fixture
    def validator(self):
        """Create medical code validator instance."""
        return MedicalCodeValidator()
    
    def test_icd10_format_validation(self, validator):
        """Test ICD-10 format validation."""
        # Valid formats
        valid_formats = ["A00", "A00.1", "A00.12", "A00.123", "A00.1234", "M25.511", "S72.001A"]
        for code in valid_formats:
            assert validator._validate_icd10_format(code) is True
        
        # Invalid formats
        invalid_formats = ["A", "A0", "A001", "A00.", "A00.12345", "AA0.1", "A0A.1", "INVALID"]
        for code in invalid_formats:
            assert validator._validate_icd10_format(code) is False
    
    def test_cpt_format_validation(self, validator):
        """Test CPT format validation."""
        # Valid formats
        valid_formats = ["70551", "73221", "12345", "99999"]
        for code in valid_formats:
            assert validator._validate_cpt_format(code) is True
        
        # Invalid formats
        invalid_formats = ["7055", "705511", "ABCDE", "7055A", ""]
        for code in invalid_formats:
            assert validator._validate_cpt_format(code) is False
    
    def test_hcpcs_format_validation(self, validator):
        """Test HCPCS format validation."""
        # Valid formats
        valid_formats = ["A0425", "E0100", "L3000", "Z1234"]
        for code in valid_formats:
            assert validator._validate_hcpcs_format(code) is True
        
        # Invalid formats
        invalid_formats = ["A042", "A04255", "0425", "AA425", "INVALID", ""]
        for code in invalid_formats:
            assert validator._validate_hcpcs_format(code) is False


class TestExternalDatabaseIntegration:
    """Test cases for external database integration simulation."""
    
    @pytest.fixture
    def validator(self):
        """Create medical code validator instance."""
        return MedicalCodeValidator()
    
    @pytest.mark.asyncio
    async def test_external_lookup_simulation(self, validator):
        """Test external database lookup simulation."""
        # Test ICD-10 lookup
        code = ICD10Code(code="M25.511", description="Pain in right shoulder")
        result = await validator._lookup_icd10_external(code)
        
        assert result.result == CodeValidationResult.VALID
        assert result.description is not None
        assert result.effective_date is not None
        
        # Test non-existent code
        invalid_code = ICD10Code(code="Z99.999", description="Non-existent")
        result = await validator._lookup_icd10_external(invalid_code)
        
        assert result.result == CodeValidationResult.NOT_FOUND
        assert len(result.suggestions) > 0
    
    @pytest.mark.asyncio
    async def test_external_lookup_statistics(self, validator):
        """Test that external lookups are tracked in statistics."""
        initial_stats = validator.get_cache_stats()
        initial_lookups = initial_stats["external_lookups"]
        
        # Perform validation that should trigger external lookup
        code = ICD10Code(code="M25.511", description="Pain in right shoulder")
        await validator.validate_icd10_code(code)
        
        final_stats = validator.get_cache_stats()
        assert final_stats["external_lookups"] > initial_lookups
    
    @pytest.mark.asyncio
    async def test_network_delay_simulation(self, validator):
        """Test that external lookups include simulated network delay."""
        import time
        
        start_time = time.time()
        
        code = CPTCode(code="70551", description="MRI brain without contrast")
        await validator._lookup_cpt_external(code)
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        # Should have at least 0.01 seconds delay (simulated network call)
        assert elapsed >= 0.01


class TestPerformanceAndScalability:
    """Test cases for performance and scalability."""
    
    @pytest.fixture
    def validator(self):
        """Create medical code validator instance."""
        return MedicalCodeValidator()
    
    @pytest.mark.asyncio
    async def test_concurrent_validations(self, validator):
        """Test concurrent validation requests."""
        codes = [
            ICD10Code(code="M25.511", description="Pain in right shoulder"),
            CPTCode(code="70551", description="MRI brain without contrast"),
            HCPCSCode(code="A0425", description="Ground mileage"),
            ICD10Code(code="G93.1", description="Anoxic brain damage"),
            CPTCode(code="73221", description="MRI upper extremity without contrast")
        ]
        
        # Run validations concurrently
        tasks = []
        for code in codes:
            if isinstance(code, ICD10Code):
                tasks.append(validator.validate_icd10_code(code))
            elif isinstance(code, CPTCode):
                tasks.append(validator.validate_cpt_code(code))
            elif isinstance(code, HCPCSCode):
                tasks.append(validator.validate_hcpcs_code(code))
        
        results = await asyncio.gather(*tasks)
        
        assert len(results) == len(codes)
        assert all(result.result == CodeValidationResult.VALID for result in results)
    
    @pytest.mark.asyncio
    async def test_large_batch_validation(self, validator):
        """Test validation of large batch of codes."""
        # Create a batch of unique codes to avoid deduplication
        batch_codes = [
            ("icd10", "M25.511"),
            ("icd10", "M25.512"), 
            ("icd10", "G93.1"),
            ("cpt", "70551"),
            ("cpt", "70552"),
            ("cpt", "73221"),
            ("hcpcs", "A0425"),
            ("hcpcs", "E0100"),
            ("hcpcs", "L3000")
        ]
        
        results = await validator.validate_codes_batch(batch_codes)
        
        assert len(results) == len(batch_codes)
        
        # All should be valid
        for result in results.values():
            assert result.result == CodeValidationResult.VALID
        
        # Check cache effectiveness after running multiple times
        for _ in range(5):
            await validator.validate_codes_batch(batch_codes)
        
        stats = validator.get_cache_stats()
        assert stats["cache_hit_rate"] > 0.5  # Should have good cache hit rate
    
    def test_frequent_cache_lru_behavior(self, validator):
        """Test LRU behavior of frequent cache."""
        # Fill up the frequent cache beyond its limit
        max_size = validator._frequent_cache_max_size
        
        for i in range(max_size + 10):
            cache_key = f"test_key_{i}"
            result = ValidationResult(code=f"TEST{i}", result=CodeValidationResult.VALID)
            entry = CacheEntry(result=result, cached_at=datetime.now(timezone.utc))
            validator._add_to_frequent_cache(cache_key, entry)
        
        # Frequent cache should not exceed max size
        assert len(validator._frequent_cache) <= max_size
    
    @pytest.mark.asyncio
    async def test_validation_performance_benchmark(self, validator):
        """Test validation performance benchmark."""
        import time
        
        code = ICD10Code(code="M25.511", description="Pain in right shoulder")
        
        # Warm up cache
        await validator.validate_icd10_code(code)
        
        # Benchmark cached validation
        start_time = time.time()
        for _ in range(100):
            await validator.validate_icd10_code(code)
        end_time = time.time()
        
        avg_time = (end_time - start_time) / 100
        
        # Cached validations should be very fast (< 1ms each)
        assert avg_time < 0.001
"""
Medical code caching service for the Prior Authorization Agent.

This module provides specialized caching for ICD-10, CPT, and HCPCS medical codes
with validation results and code suggestion caching.
"""

import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
import hashlib

from src.services.cache import cache_manager, CacheKey, CacheTTL

logger = logging.getLogger(__name__)


class MedicalCodeType:
    """Medical code type constants."""
    ICD10 = "icd10"
    CPT = "cpt"
    HCPCS = "hcpcs"


class ValidationStatus:
    """Code validation status constants."""
    VALID = "valid"
    INVALID = "invalid"
    DEPRECATED = "deprecated"
    UNKNOWN = "unknown"


class MedicalCodeCacheService:
    """
    Specialized caching service for medical codes and validation results.
    
    Provides caching for ICD-10, CPT, and HCPCS codes with validation status,
    suggestions for invalid codes, and frequently accessed code warming.
    """
    
    def __init__(self):
        self.cache = cache_manager
    
    async def get_code_validation(
        self, 
        code: str, 
        code_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached validation result for a medical code.
        
        Args:
            code: Medical code to validate
            code_type: Type of code (icd10, cpt, hcpcs)
            
        Returns:
            Validation result or None if not cached
        """
        key = self._get_code_key(code, code_type)
        return await self.cache.get(key)
    
    async def cache_code_validation(
        self,
        code: str,
        code_type: str,
        validation_result: Dict[str, Any],
        is_valid: bool = True
    ) -> bool:
        """
        Cache medical code validation result.
        
        Args:
            code: Medical code
            code_type: Type of code (icd10, cpt, hcpcs)
            validation_result: Validation result data
            is_valid: Whether the code is valid
            
        Returns:
            True if cached successfully, False otherwise
        """
        key = self._get_code_key(code, code_type)
        
        # Use different TTL based on validation status
        ttl = CacheTTL.MEDICAL_CODE_VALID if is_valid else CacheTTL.MEDICAL_CODE_INVALID
        
        # Add metadata to validation result
        enhanced_result = {
            **validation_result,
            'code': code,
            'code_type': code_type,
            'is_valid': is_valid,
            'cached_at': datetime.now(timezone.utc).isoformat(),
            'ttl': ttl
        }
        
        success = await self.cache.set(key, enhanced_result, ttl=ttl)
        
        if success:
            logger.debug(f"Cached {code_type} code {code} validation (valid: {is_valid})")
        else:
            logger.warning(f"Failed to cache {code_type} code {code} validation")
        
        return success
    
    async def get_code_suggestions(
        self, 
        invalid_code: str, 
        code_type: str
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached code suggestions for an invalid code.
        
        Args:
            invalid_code: Invalid medical code
            code_type: Type of code (icd10, cpt, hcpcs)
            
        Returns:
            List of suggested codes or None if not cached
        """
        key = f"{self._get_code_key(invalid_code, code_type)}:suggestions"
        return await self.cache.get(key)
    
    async def cache_code_suggestions(
        self,
        invalid_code: str,
        code_type: str,
        suggestions: List[Dict[str, Any]]
    ) -> bool:
        """
        Cache code suggestions for an invalid code.
        
        Args:
            invalid_code: Invalid medical code
            code_type: Type of code (icd10, cpt, hcpcs)
            suggestions: List of suggested valid codes
            
        Returns:
            True if cached successfully, False otherwise
        """
        key = f"{self._get_code_key(invalid_code, code_type)}:suggestions"
        
        # Cache suggestions with shorter TTL since they might change
        success = await self.cache.set(
            key, 
            suggestions, 
            ttl=CacheTTL.MEDICAL_CODE_INVALID
        )
        
        if success:
            logger.debug(f"Cached {len(suggestions)} suggestions for {code_type} code {invalid_code}")
        else:
            logger.warning(f"Failed to cache suggestions for {code_type} code {invalid_code}")
        
        return success
    
    async def batch_get_validations(
        self, 
        codes: List[Tuple[str, str]]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Get validation results for multiple codes in batch.
        
        Args:
            codes: List of (code, code_type) tuples
            
        Returns:
            Dictionary mapping code to validation result
        """
        results = {}
        
        # Process codes in parallel
        tasks = []
        for code, code_type in codes:
            task = self.get_code_validation(code, code_type)
            tasks.append((code, task))
        
        # Wait for all tasks to complete
        for code, task in tasks:
            try:
                result = await task
                results[code] = result
            except Exception as e:
                logger.error(f"Failed to get validation for code {code}: {e}")
                results[code] = None
        
        return results
    
    async def batch_cache_validations(
        self, 
        validations: List[Dict[str, Any]]
    ) -> Dict[str, bool]:
        """
        Cache multiple validation results in batch.
        
        Args:
            validations: List of validation result dictionaries
            
        Returns:
            Dictionary mapping code to cache success status
        """
        results = {}
        
        # Process validations in parallel
        tasks = []
        for validation in validations:
            code = validation.get('code')
            code_type = validation.get('code_type')
            is_valid = validation.get('is_valid', True)
            
            if code and code_type:
                task = self.cache_code_validation(code, code_type, validation, is_valid)
                tasks.append((code, task))
        
        # Wait for all tasks to complete
        for code, task in tasks:
            try:
                result = await task
                results[code] = result
            except Exception as e:
                logger.error(f"Failed to cache validation for code {code}: {e}")
                results[code] = False
        
        return results
    
    async def warm_frequently_used_codes(
        self, 
        codes: List[Tuple[str, str]]
    ) -> Dict[str, bool]:
        """
        Warm cache with frequently used medical codes.
        
        Args:
            codes: List of (code, code_type) tuples to warm
            
        Returns:
            Dictionary mapping code to warming success status
        """
        results = {}
        
        for code, code_type in codes:
            key = self._get_code_key(code, code_type)
            
            # Check if already cached
            if await self.cache.exists(key):
                # Extend TTL for frequently used codes
                extended = await self.cache.extend_ttl(key, CacheTTL.MEDICAL_CODE_VALID)
                results[code] = extended
            else:
                # In a real implementation, this would fetch validation from external service
                # and then cache the result
                results[code] = False
        
        warmed_count = sum(1 for success in results.values() if success)
        logger.info(f"Warmed {warmed_count}/{len(codes)} frequently used medical codes")
        
        return results
    
    async def invalidate_code_type(self, code_type: str) -> int:
        """
        Invalidate all cached codes of a specific type.
        
        Args:
            code_type: Type of codes to invalidate (icd10, cpt, hcpcs)
            
        Returns:
            Number of cache entries invalidated
        """
        pattern = f"{CacheKey.MEDICAL_CODE_PREFIX}:{code_type}:*"
        deleted_count = await self.cache.delete_pattern(pattern)
        
        logger.info(f"Invalidated {deleted_count} {code_type} code cache entries")
        return deleted_count
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get medical code cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        stats = {
            'total_codes': 0,
            'icd10_codes': 0,
            'cpt_codes': 0,
            'hcpcs_codes': 0,
            'valid_codes': 0,
            'invalid_codes': 0,
            'suggestions_cached': 0
        }
        
        try:
            async with self.cache.get_client() as client:
                # Get all medical code keys
                all_keys = await asyncio.get_event_loop().run_in_executor(
                    None, client.keys, f"{CacheKey.MEDICAL_CODE_PREFIX}:*"
                )
                
                stats['total_codes'] = len([k for k in all_keys if ':suggestions' not in k])
                stats['suggestions_cached'] = len([k for k in all_keys if ':suggestions' in k])
                
                for key in all_keys:
                    if ':suggestions' in key:
                        continue
                        
                    if ':icd10:' in key:
                        stats['icd10_codes'] += 1
                    elif ':cpt:' in key:
                        stats['cpt_codes'] += 1
                    elif ':hcpcs:' in key:
                        stats['hcpcs_codes'] += 1
                    
                    # Check validation status
                    cached_data = await self.cache.get(key)
                    if cached_data and cached_data.get('is_valid'):
                        stats['valid_codes'] += 1
                    else:
                        stats['invalid_codes'] += 1
        
        except Exception as e:
            logger.error(f"Failed to get medical code cache stats: {e}")
        
        return stats
    
    def _get_code_key(self, code: str, code_type: str) -> str:
        """
        Generate cache key for a medical code.
        
        Args:
            code: Medical code
            code_type: Type of code (icd10, cpt, hcpcs)
            
        Returns:
            Cache key string
        """
        if code_type == MedicalCodeType.ICD10:
            return CacheKey.generate_key(CacheKey.ICD10_CODE, code=code)
        elif code_type == MedicalCodeType.CPT:
            return CacheKey.generate_key(CacheKey.CPT_CODE, code=code)
        elif code_type == MedicalCodeType.HCPCS:
            return CacheKey.generate_key(CacheKey.HCPCS_CODE, code=code)
        else:
            raise ValueError(f"Unsupported code type: {code_type}")


# Global medical code cache service instance
medical_code_cache_service = MedicalCodeCacheService()
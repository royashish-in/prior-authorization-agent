"""
Medical code validation engine with external database integration.

This module provides comprehensive validation for ICD-10, CPT, and HCPCS codes
with caching, suggestion functionality, and external database integration.
"""

import asyncio
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum

from src.models.medical_codes import ICD10Code, CPTCode, HCPCSCode
from src.core.logging import get_logger

logger = get_logger(__name__)


class CodeValidationResult(Enum):
    """Result of code validation."""
    VALID = "valid"
    INVALID = "invalid"
    DEPRECATED = "deprecated"
    NOT_FOUND = "not_found"


@dataclass
class ValidationResult:
    """Result of medical code validation."""
    code: str
    result: CodeValidationResult
    description: Optional[str] = None
    suggestions: List[str] = None
    effective_date: Optional[datetime] = None
    expiration_date: Optional[datetime] = None
    
    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []


@dataclass
class CacheEntry:
    """Cache entry for medical code validation results."""
    result: ValidationResult
    cached_at: datetime
    ttl_seconds: int = 3600  # 1 hour default TTL
    
    @property
    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        return datetime.now(timezone.utc) > self.cached_at + timedelta(seconds=self.ttl_seconds)


class MedicalCodeValidator:
    """
    Medical code validation engine with caching and external database integration.
    
    Provides validation for:
    - ICD-10 diagnosis codes
    - CPT procedure codes  
    - HCPCS codes
    
    Features:
    - External database integration (simulated)
    - Intelligent code suggestions
    - Multi-level caching
    - Performance optimization
    """
    
    def __init__(self):
        """Initialize the medical code validator."""
        self.logger = get_logger(self.__class__.__name__)
        
        # In-memory cache for validated codes
        self._cache: Dict[str, CacheEntry] = {}
        
        # Frequently accessed codes cache (LRU-style)
        self._frequent_cache: Dict[str, CacheEntry] = {}
        self._frequent_cache_max_size = 1000
        
        # Load initial code databases (simulated external databases)
        self._load_code_databases()
        
        # Statistics for monitoring
        self._stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "external_lookups": 0,
            "validation_requests": 0
        }
    
    def _load_code_databases(self):
        """Load medical code databases (simulated external integration)."""
        # ICD-10 codes database (subset for demo)
        self._icd10_db = {
            "A00": {"description": "Cholera", "effective": "2015-10-01", "status": "active"},
            "A00.0": {"description": "Cholera due to Vibrio cholerae 01, biovar cholerae", "effective": "2015-10-01", "status": "active"},
            "A00.1": {"description": "Cholera due to Vibrio cholerae 01, biovar eltor", "effective": "2015-10-01", "status": "active"},
            "A00.9": {"description": "Cholera, unspecified", "effective": "2015-10-01", "status": "active"},
            
            # Musculoskeletal codes
            "M25.511": {"description": "Pain in right shoulder", "effective": "2015-10-01", "status": "active"},
            "M25.512": {"description": "Pain in left shoulder", "effective": "2015-10-01", "status": "active"},
            "M25.519": {"description": "Pain in unspecified shoulder", "effective": "2015-10-01", "status": "active"},
            "M25.50": {"description": "Pain in unspecified joint", "effective": "2015-10-01", "status": "active"},
            "M25.521": {"description": "Pain in right elbow", "effective": "2015-10-01", "status": "active"},
            "M25.522": {"description": "Pain in left elbow", "effective": "2015-10-01", "status": "active"},
            
            # Injury codes
            "S72.001A": {"description": "Fracture of unspecified part of neck of right femur, initial encounter", "effective": "2015-10-01", "status": "active"},
            "S72.001D": {"description": "Fracture of unspecified part of neck of right femur, subsequent encounter", "effective": "2015-10-01", "status": "active"},
            "S72.002A": {"description": "Fracture of unspecified part of neck of left femur, initial encounter", "effective": "2015-10-01", "status": "active"},
            
            # Neurological codes
            "G93.1": {"description": "Anoxic brain damage, not elsewhere classified", "effective": "2015-10-01", "status": "active"},
            "G93.2": {"description": "Benign intracranial hypertension", "effective": "2015-10-01", "status": "active"},
            
            # Cardiovascular codes
            "I25.10": {"description": "Atherosclerotic heart disease of native coronary artery without angina pectoris", "effective": "2015-10-01", "status": "active"},
            "I25.110": {"description": "Atherosclerotic heart disease of native coronary artery with unstable angina pectoris", "effective": "2015-10-01", "status": "active"},
        }
        
        # CPT codes database (imaging procedures subset)
        self._cpt_db = {
            # Brain MRI
            "70551": {"description": "MRI brain without contrast", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            "70552": {"description": "MRI brain with contrast", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            "70553": {"description": "MRI brain without and with contrast", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            
            # Spine MRI
            "72148": {"description": "MRI lumbar spine without contrast", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            "72149": {"description": "MRI lumbar spine with contrast", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            "72158": {"description": "MRI lumbar spine without and with contrast", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            "72141": {"description": "MRI cervical spine without contrast", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            "72142": {"description": "MRI cervical spine with contrast", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            
            # Extremity MRI
            "73221": {"description": "MRI upper extremity without contrast", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            "73222": {"description": "MRI upper extremity with contrast", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            "73223": {"description": "MRI upper extremity without and with contrast", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            "73721": {"description": "MRI lower extremity without contrast", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            "73722": {"description": "MRI lower extremity with contrast", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            "73723": {"description": "MRI lower extremity without and with contrast", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            
            # CT Scans
            "70450": {"description": "CT head without contrast", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            "70460": {"description": "CT head with contrast", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            "70470": {"description": "CT head without and with contrast", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            "71250": {"description": "CT chest without contrast", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            "71260": {"description": "CT chest with contrast", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            "71270": {"description": "CT chest without and with contrast", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            
            # X-rays
            "71020": {"description": "Chest X-ray, 2 views", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            "71030": {"description": "Chest X-ray, complete", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            "73060": {"description": "Knee X-ray, 2 or 3 views", "effective": "2023-01-01", "status": "active", "category": "radiology"},
            "73070": {"description": "Knee X-ray, complete", "effective": "2023-01-01", "status": "active", "category": "radiology"},
        }
        
        # HCPCS codes database (subset)
        self._hcpcs_db = {
            "A0425": {"description": "Ground mileage, per statute mile", "effective": "2023-01-01", "status": "active", "category": "ambulance"},
            "A0426": {"description": "Ambulance service, advanced life support, non-emergency transport", "effective": "2023-01-01", "status": "active", "category": "ambulance"},
            "A0427": {"description": "Ambulance service, advanced life support, emergency transport", "effective": "2023-01-01", "status": "active", "category": "ambulance"},
            "A0428": {"description": "Ambulance service, basic life support, non-emergency transport", "effective": "2023-01-01", "status": "active", "category": "ambulance"},
            "A0429": {"description": "Ambulance service, basic life support, emergency transport", "effective": "2023-01-01", "status": "active", "category": "ambulance"},
            
            # Durable medical equipment
            "E0100": {"description": "Cane, includes canes of all materials", "effective": "2023-01-01", "status": "active", "category": "dme"},
            "E0110": {"description": "Crutches, forearm, includes crutches of various materials", "effective": "2023-01-01", "status": "active", "category": "dme"},
            "E0130": {"description": "Walker, rigid (pickup), adjustable or fixed height", "effective": "2023-01-01", "status": "active", "category": "dme"},
            
            # Prosthetics
            "L3000": {"description": "Foot insert, removable, molded to patient model", "effective": "2023-01-01", "status": "active", "category": "prosthetics"},
            "L3001": {"description": "Foot insert, removable, molded to patient model, longitudinal arch support", "effective": "2023-01-01", "status": "active", "category": "prosthetics"},
        }
        
        self.logger.info(
            "Medical code databases loaded",
            icd10_codes=len(self._icd10_db),
            cpt_codes=len(self._cpt_db),
            hcpcs_codes=len(self._hcpcs_db)
        )
    
    async def validate_icd10_code(self, code: ICD10Code) -> ValidationResult:
        """
        Validate an ICD-10 diagnosis code.
        
        Args:
            code: ICD-10 code to validate
            
        Returns:
            Validation result with suggestions if invalid
        """
        self._stats["validation_requests"] += 1
        
        # Check cache first
        cache_key = f"icd10:{code.code}"
        cached_result = self._get_from_cache(cache_key)
        if cached_result:
            self._stats["cache_hits"] += 1
            return cached_result
        
        self._stats["cache_misses"] += 1
        
        # Validate format first
        if not self._validate_icd10_format(code.code):
            result = ValidationResult(
                code=code.code,
                result=CodeValidationResult.INVALID,
                suggestions=self._suggest_icd10_codes(code.code)
            )
            self._add_to_cache(cache_key, result)
            return result
        
        # Check external database
        result = await self._lookup_icd10_external(code)
        self._add_to_cache(cache_key, result)
        
        return result
    
    async def validate_cpt_code(self, code: CPTCode) -> ValidationResult:
        """
        Validate a CPT procedure code.
        
        Args:
            code: CPT code to validate
            
        Returns:
            Validation result with suggestions if invalid
        """
        self._stats["validation_requests"] += 1
        
        # Check cache first
        cache_key = f"cpt:{code.code}"
        cached_result = self._get_from_cache(cache_key)
        if cached_result:
            self._stats["cache_hits"] += 1
            return cached_result
        
        self._stats["cache_misses"] += 1
        
        # Validate format first
        if not self._validate_cpt_format(code.code):
            result = ValidationResult(
                code=code.code,
                result=CodeValidationResult.INVALID,
                suggestions=self._suggest_cpt_codes(code.code)
            )
            self._add_to_cache(cache_key, result)
            return result
        
        # Check external database
        result = await self._lookup_cpt_external(code)
        self._add_to_cache(cache_key, result)
        
        return result
    
    async def validate_hcpcs_code(self, code: HCPCSCode) -> ValidationResult:
        """
        Validate an HCPCS code.
        
        Args:
            code: HCPCS code to validate
            
        Returns:
            Validation result with suggestions if invalid
        """
        self._stats["validation_requests"] += 1
        
        # Check cache first
        cache_key = f"hcpcs:{code.code}"
        cached_result = self._get_from_cache(cache_key)
        if cached_result:
            self._stats["cache_hits"] += 1
            return cached_result
        
        self._stats["cache_misses"] += 1
        
        # Validate format first
        if not self._validate_hcpcs_format(code.code):
            result = ValidationResult(
                code=code.code,
                result=CodeValidationResult.INVALID,
                suggestions=self._suggest_hcpcs_codes(code.code)
            )
            self._add_to_cache(cache_key, result)
            return result
        
        # Check external database
        result = await self._lookup_hcpcs_external(code)
        self._add_to_cache(cache_key, result)
        
        return result
    
    async def validate_codes_batch(self, codes: List[Tuple[str, str]]) -> Dict[str, ValidationResult]:
        """
        Validate multiple codes in batch for better performance.
        
        Args:
            codes: List of (code_type, code_value) tuples
            
        Returns:
            Dictionary mapping code values to validation results
        """
        tasks = []
        code_map = {}
        
        for code_type, code_value in codes:
            if code_type.lower() == "icd10":
                task = self.validate_icd10_code(ICD10Code(code=code_value))
            elif code_type.lower() == "cpt":
                task = self.validate_cpt_code(CPTCode(code=code_value))
            elif code_type.lower() == "hcpcs":
                task = self.validate_hcpcs_code(HCPCSCode(code=code_value))
            else:
                continue
            
            tasks.append(task)
            code_map[len(tasks) - 1] = code_value
        
        results = await asyncio.gather(*tasks)
        
        return {code_map[i]: result for i, result in enumerate(results)}
    
    def get_code_suggestions(self, partial_code: str, code_type: str, limit: int = 10) -> List[str]:
        """
        Get code suggestions based on partial input.
        
        Args:
            partial_code: Partial code input
            code_type: Type of code (icd10, cpt, hcpcs)
            limit: Maximum number of suggestions
            
        Returns:
            List of suggested codes
        """
        if code_type.lower() == "icd10":
            return self._suggest_icd10_codes(partial_code, limit)
        elif code_type.lower() == "cpt":
            return self._suggest_cpt_codes(partial_code, limit)
        elif code_type.lower() == "hcpcs":
            return self._suggest_hcpcs_codes(partial_code, limit)
        else:
            return []
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache and validation statistics."""
        cache_hit_rate = 0.0
        if self._stats["validation_requests"] > 0:
            cache_hit_rate = self._stats["cache_hits"] / self._stats["validation_requests"]
        
        return {
            **self._stats,
            "cache_size": len(self._cache),
            "frequent_cache_size": len(self._frequent_cache),
            "cache_hit_rate": round(cache_hit_rate, 3)
        }
    
    def clear_cache(self):
        """Clear all cached validation results."""
        self._cache.clear()
        self._frequent_cache.clear()
        self.logger.info("Medical code validation cache cleared")
    
    def _get_from_cache(self, cache_key: str) -> Optional[ValidationResult]:
        """Get validation result from cache."""
        # Check frequent cache first
        if cache_key in self._frequent_cache:
            entry = self._frequent_cache[cache_key]
            if not entry.is_expired:
                return entry.result
            else:
                del self._frequent_cache[cache_key]
        
        # Check main cache
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if not entry.is_expired:
                # Move to frequent cache if accessed again
                self._add_to_frequent_cache(cache_key, entry)
                return entry.result
            else:
                del self._cache[cache_key]
        
        return None
    
    def _add_to_cache(self, cache_key: str, result: ValidationResult, ttl_seconds: int = 3600):
        """Add validation result to cache."""
        entry = CacheEntry(
            result=result,
            cached_at=datetime.now(timezone.utc),
            ttl_seconds=ttl_seconds
        )
        self._cache[cache_key] = entry
    
    def _add_to_frequent_cache(self, cache_key: str, entry: CacheEntry):
        """Add entry to frequent access cache with LRU eviction."""
        if len(self._frequent_cache) >= self._frequent_cache_max_size:
            # Remove oldest entry (simple FIFO for demo)
            oldest_key = next(iter(self._frequent_cache))
            del self._frequent_cache[oldest_key]
        
        self._frequent_cache[cache_key] = entry
    
    def _validate_icd10_format(self, code: str) -> bool:
        """Validate ICD-10 code format."""
        # ICD-10 format: Letter + 2 digits + optional decimal + up to 4 more characters
        pattern = r'^[A-Z][0-9]{2}(\.[A-Z0-9]{1,4})?$'
        return bool(re.match(pattern, code.upper()))
    
    def _validate_cpt_format(self, code: str) -> bool:
        """Validate CPT code format."""
        # CPT codes are 5-digit numeric
        return bool(re.match(r'^\d{5}$', code))
    
    def _validate_hcpcs_format(self, code: str) -> bool:
        """Validate HCPCS code format."""
        # HCPCS codes: Letter + 4 digits
        return bool(re.match(r'^[A-Z]\d{4}$', code.upper()))
    
    async def _lookup_icd10_external(self, code: ICD10Code) -> ValidationResult:
        """Simulate external ICD-10 database lookup."""
        self._stats["external_lookups"] += 1
        
        # Simulate network delay
        await asyncio.sleep(0.01)
        
        code_upper = code.code.upper()
        if code_upper in self._icd10_db:
            db_entry = self._icd10_db[code_upper]
            return ValidationResult(
                code=code.code,
                result=CodeValidationResult.VALID,
                description=db_entry["description"],
                effective_date=datetime.fromisoformat(db_entry["effective"] + "T00:00:00+00:00")
            )
        else:
            return ValidationResult(
                code=code.code,
                result=CodeValidationResult.NOT_FOUND,
                suggestions=self._suggest_icd10_codes(code.code)
            )
    
    async def _lookup_cpt_external(self, code: CPTCode) -> ValidationResult:
        """Simulate external CPT database lookup."""
        self._stats["external_lookups"] += 1
        
        # Simulate network delay
        await asyncio.sleep(0.01)
        
        if code.code in self._cpt_db:
            db_entry = self._cpt_db[code.code]
            return ValidationResult(
                code=code.code,
                result=CodeValidationResult.VALID,
                description=db_entry["description"],
                effective_date=datetime.fromisoformat(db_entry["effective"] + "T00:00:00+00:00")
            )
        else:
            return ValidationResult(
                code=code.code,
                result=CodeValidationResult.NOT_FOUND,
                suggestions=self._suggest_cpt_codes(code.code)
            )
    
    async def _lookup_hcpcs_external(self, code: HCPCSCode) -> ValidationResult:
        """Simulate external HCPCS database lookup."""
        self._stats["external_lookups"] += 1
        
        # Simulate network delay
        await asyncio.sleep(0.01)
        
        code_upper = code.code.upper()
        if code_upper in self._hcpcs_db:
            db_entry = self._hcpcs_db[code_upper]
            return ValidationResult(
                code=code.code,
                result=CodeValidationResult.VALID,
                description=db_entry["description"],
                effective_date=datetime.fromisoformat(db_entry["effective"] + "T00:00:00+00:00")
            )
        else:
            return ValidationResult(
                code=code.code,
                result=CodeValidationResult.NOT_FOUND,
                suggestions=self._suggest_hcpcs_codes(code.code)
            )
    
    def _suggest_icd10_codes(self, invalid_code: str, limit: int = 5) -> List[str]:
        """Generate ICD-10 code suggestions."""
        suggestions = []
        invalid_upper = invalid_code.upper()
        
        # Find codes with similar prefixes
        for code in self._icd10_db.keys():
            if len(suggestions) >= limit:
                break
            
            # Exact prefix match
            if code.startswith(invalid_upper[:3]):
                suggestions.append(f"{code} - {self._icd10_db[code]['description']}")
            # Similar pattern match
            elif len(invalid_upper) >= 3 and code[:1] == invalid_upper[:1]:
                suggestions.append(f"{code} - {self._icd10_db[code]['description']}")
        
        # Add common codes for the category if no matches
        if not suggestions:
            if invalid_upper.startswith('M'):
                suggestions.extend([
                    "M25.511 - Pain in right shoulder",
                    "M25.512 - Pain in left shoulder",
                    "M25.50 - Pain in unspecified joint"
                ])
            elif invalid_upper.startswith('S'):
                suggestions.extend([
                    "S72.001A - Fracture of unspecified part of neck of right femur, initial encounter"
                ])
            else:
                suggestions.extend([
                    "M25.511 - Pain in right shoulder",
                    "G93.1 - Anoxic brain damage, not elsewhere classified"
                ])
        
        return suggestions[:limit]
    
    def _suggest_cpt_codes(self, invalid_code: str, limit: int = 5) -> List[str]:
        """Generate CPT code suggestions."""
        suggestions = []
        
        # Find codes with similar prefixes or in same range
        for code in self._cpt_db.keys():
            if len(suggestions) >= limit:
                break
            
            # Similar numeric range
            if len(invalid_code) >= 2 and code[:2] == invalid_code[:2]:
                suggestions.append(f"{code} - {self._cpt_db[code]['description']}")
        
        # Add common imaging codes if no matches
        if not suggestions:
            if invalid_code.startswith('70'):
                suggestions.extend([
                    "70551 - MRI brain without contrast",
                    "70552 - MRI brain with contrast"
                ])
            elif invalid_code.startswith('72'):
                suggestions.extend([
                    "72148 - MRI lumbar spine without contrast",
                    "72141 - MRI cervical spine without contrast"
                ])
            elif invalid_code.startswith('73'):
                suggestions.extend([
                    "73221 - MRI upper extremity without contrast",
                    "73721 - MRI lower extremity without contrast"
                ])
            else:
                suggestions.extend([
                    "70551 - MRI brain without contrast",
                    "73221 - MRI upper extremity without contrast",
                    "72148 - MRI lumbar spine without contrast"
                ])
        
        return suggestions[:limit]
    
    def _suggest_hcpcs_codes(self, invalid_code: str, limit: int = 5) -> List[str]:
        """Generate HCPCS code suggestions."""
        suggestions = []
        invalid_upper = invalid_code.upper()
        
        # Find codes with similar prefixes
        for code in self._hcpcs_db.keys():
            if len(suggestions) >= limit:
                break
            
            # Same letter prefix
            if code[0] == invalid_upper[0]:
                suggestions.append(f"{code} - {self._hcpcs_db[code]['description']}")
        
        # Add common codes if no matches
        if not suggestions:
            suggestions.extend([
                "A0425 - Ground mileage, per statute mile",
                "E0100 - Cane, includes canes of all materials",
                "L3000 - Foot insert, removable, molded to patient model"
            ])
        
        return suggestions[:limit]
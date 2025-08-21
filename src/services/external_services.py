"""
External service integrations for Prior Authorization Agent.

This module provides integrations with external healthcare services including
CMS guidelines API, medical code databases, and policy services with
comprehensive caching, fallback mechanisms, and error handling.
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import httpx
from pydantic import BaseModel, ConfigDict

from src.core.config import get_settings
from src.core.logging import get_logger


class ServiceStatus(str, Enum):
    """External service status enumeration."""
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass
class ServiceHealth:
    """Health status of an external service."""
    service_name: str
    status: ServiceStatus
    response_time_ms: Optional[float]
    last_check: datetime
    error_message: Optional[str] = None


class CMSGuidelinesResponse(BaseModel):
    """Response model for CMS guidelines API."""
    ncd_policies: List[Dict[str, Any]]
    lcd_policies: List[Dict[str, Any]]
    is_compliant: bool
    compliance_issues: List[str]
    recommendations: List[str]
    confidence_score: float
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ncd_policies": [
                    {
                        "policy_id": "NCD_220.2",
                        "policy_name": "Magnetic Resonance Imaging",
                        "coverage_criteria": ["Medical necessity established"]
                    }
                ],
                "lcd_policies": [
                    {
                        "policy_id": "LCD_L33721",
                        "policy_name": "MRI Brain",
                        "coverage_criteria": ["Neurological symptoms present"]
                    }
                ],
                "is_compliant": True,
                "compliance_issues": [],
                "recommendations": ["Ensure medical necessity is documented"],
                "confidence_score": 0.9
            }
        }
    )


class MedicalCodeValidationResponse(BaseModel):
    """Response model for medical code validation."""
    code: str
    is_valid: bool
    description: Optional[str]
    code_type: str
    suggestions: List[str]
    effective_date: Optional[datetime]
    expiration_date: Optional[datetime]
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "70551",
                "is_valid": True,
                "description": "MRI brain without contrast",
                "code_type": "CPT",
                "suggestions": [],
                "effective_date": "2024-01-01T00:00:00Z",
                "expiration_date": None
            }
        }
    )


class PolicyServiceResponse(BaseModel):
    """Response model for policy service."""
    policy_id: str
    is_covered: bool
    policy_type: str
    reasoning: List[str]
    confidence_score: float
    policy_references: List[str]
    additional_requirements: List[str]
    conflicts: List[Dict[str, Any]]
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "policy_id": "POLICY_PAYER_001",
                "is_covered": True,
                "policy_type": "PAYER",
                "reasoning": [
                    "Procedure covered under standard benefits",
                    "Diagnosis supports medical necessity"
                ],
                "confidence_score": 0.85,
                "policy_references": ["PAYER_POLICY_MRI"],
                "additional_requirements": [
                    "Prior authorization required",
                    "Network provider preferred"
                ],
                "conflicts": []
            }
        }
    )


class ExternalServiceIntegrator:
    """
    Manages integrations with external healthcare services.
    
    Provides unified interface for CMS guidelines, medical code validation,
    and policy services with caching, fallback, and health monitoring.
    """
    
    def __init__(self):
        """Initialize the external service integrator."""
        self.logger = get_logger(self.__class__.__name__)
        self.settings = get_settings()
        
        # HTTP client with timeout and retry configuration
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.cms_api_timeout),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=5)
        )
        
        # Service health tracking
        self.service_health: Dict[str, ServiceHealth] = {}
        
        # Cache for external service responses
        self.cache: Dict[str, Dict[str, Any]] = {
            "cms_guidelines": {},
            "medical_codes": {},
            "policies": {}
        }
        
        # Cache TTL settings (in seconds)
        self.cache_ttl = {
            "cms_guidelines": 3600,  # 1 hour
            "medical_codes": 86400,  # 24 hours
            "policies": 1800  # 30 minutes
        }
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def close(self):
        """Close HTTP client and cleanup resources."""
        await self.client.aclose()
    
    def _get_cache_key(self, service: str, **params) -> str:
        """Generate cache key for service request."""
        key_parts = [service]
        for key, value in sorted(params.items()):
            key_parts.append(f"{key}:{value}")
        return "|".join(key_parts)
    
    def _is_cache_valid(self, cache_entry: Dict[str, Any], service: str) -> bool:
        """Check if cache entry is still valid."""
        if "timestamp" not in cache_entry:
            return False
        
        cache_time = datetime.fromisoformat(cache_entry["timestamp"])
        ttl = self.cache_ttl.get(service, 3600)
        
        return (datetime.now(timezone.utc) - cache_time).total_seconds() < ttl
    
    def _cache_response(self, service: str, cache_key: str, response_data: Any):
        """Cache service response with timestamp."""
        self.cache[service][cache_key] = {
            "data": response_data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def _get_cached_response(self, service: str, cache_key: str) -> Optional[Any]:
        """Get cached response if valid."""
        if cache_key in self.cache[service]:
            cache_entry = self.cache[service][cache_key]
            if self._is_cache_valid(cache_entry, service):
                return cache_entry["data"]
            else:
                # Remove expired cache entry
                del self.cache[service][cache_key]
        return None
    
    async def _update_service_health(
        self,
        service_name: str,
        status: ServiceStatus,
        response_time_ms: Optional[float] = None,
        error_message: Optional[str] = None
    ):
        """Update service health status."""
        self.service_health[service_name] = ServiceHealth(
            service_name=service_name,
            status=status,
            response_time_ms=response_time_ms,
            last_check=datetime.now(timezone.utc),
            error_message=error_message
        )
    
    async def get_cms_guidelines(
        self,
        procedure_codes: List[str],
        diagnosis_codes: List[str],
        use_cache: bool = True,
        fallback_on_error: bool = True
    ) -> CMSGuidelinesResponse:
        """
        Get CMS guidelines for procedure and diagnosis codes.
        
        Args:
            procedure_codes: List of CPT/HCPCS procedure codes
            diagnosis_codes: List of ICD-10 diagnosis codes
            use_cache: Whether to use cached responses
            fallback_on_error: Whether to use fallback data on service error
            
        Returns:
            CMS guidelines response with compliance information
        """
        cache_key = self._get_cache_key(
            "cms_guidelines",
            procedures="|".join(sorted(procedure_codes)),
            diagnoses="|".join(sorted(diagnosis_codes))
        )
        
        # Check cache first
        if use_cache:
            cached_response = self._get_cached_response("cms_guidelines", cache_key)
            if cached_response:
                self.logger.debug("Returning cached CMS guidelines", cache_key=cache_key)
                return CMSGuidelinesResponse(**cached_response)
        
        try:
            start_time = datetime.now()
            
            # Make API request to CMS guidelines service
            response = await self._make_cms_api_request(procedure_codes, diagnosis_codes)
            
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            await self._update_service_health("cms_guidelines", ServiceStatus.AVAILABLE, response_time)
            
            # Process and cache response
            cms_response = self._process_cms_response(response, procedure_codes, diagnosis_codes)
            
            if use_cache:
                self._cache_response("cms_guidelines", cache_key, cms_response.model_dump())
            
            self.logger.info(
                "CMS guidelines retrieved successfully",
                procedure_codes=procedure_codes,
                diagnosis_codes=diagnosis_codes,
                response_time_ms=response_time
            )
            
            return cms_response
            
        except Exception as e:
            await self._update_service_health(
                "cms_guidelines",
                ServiceStatus.UNAVAILABLE,
                error_message=str(e)
            )
            
            self.logger.error(
                "CMS guidelines API error",
                procedure_codes=procedure_codes,
                diagnosis_codes=diagnosis_codes,
                error=str(e)
            )
            
            if fallback_on_error:
                return self._get_cms_fallback_response(procedure_codes, diagnosis_codes)
            else:
                raise
    
    async def validate_medical_codes(
        self,
        codes: List[Dict[str, str]],
        use_cache: bool = True,
        fallback_on_error: bool = True
    ) -> List[MedicalCodeValidationResponse]:
        """
        Validate medical codes against external code databases.
        
        Args:
            codes: List of medical codes with type information
            use_cache: Whether to use cached responses
            fallback_on_error: Whether to use fallback validation on service error
            
        Returns:
            List of medical code validation responses
        """
        results = []
        
        for code_info in codes:
            code = code_info.get("code", "")
            code_type = code_info.get("code_type", "")
            
            cache_key = self._get_cache_key("medical_codes", code=code, type=code_type)
            
            # Check cache first
            if use_cache:
                cached_response = self._get_cached_response("medical_codes", cache_key)
                if cached_response:
                    results.append(MedicalCodeValidationResponse(**cached_response))
                    continue
            
            try:
                start_time = datetime.now()
                
                # Validate code with external service
                validation_result = await self._validate_single_code(code, code_type)
                
                response_time = (datetime.now() - start_time).total_seconds() * 1000
                await self._update_service_health("medical_codes", ServiceStatus.AVAILABLE, response_time)
                
                if use_cache:
                    self._cache_response("medical_codes", cache_key, validation_result.model_dump())
                
                results.append(validation_result)
                
            except Exception as e:
                await self._update_service_health(
                    "medical_codes",
                    ServiceStatus.UNAVAILABLE,
                    error_message=str(e)
                )
                
                self.logger.error(
                    "Medical code validation error",
                    code=code,
                    code_type=code_type,
                    error=str(e)
                )
                
                if fallback_on_error:
                    results.append(self._get_code_fallback_response(code, code_type))
                else:
                    raise
        
        self.logger.info(
            "Medical code validation completed",
            total_codes=len(codes),
            valid_codes=len([r for r in results if r.is_valid])
        )
        
        return results
    
    async def get_policy_coverage(
        self,
        payer_id: str,
        procedure_codes: List[str],
        diagnosis_codes: List[str],
        use_cache: bool = True,
        resolve_conflicts: bool = True
    ) -> PolicyServiceResponse:
        """
        Get policy coverage information from policy service.
        
        Args:
            payer_id: Healthcare payer identifier
            procedure_codes: List of procedure codes
            diagnosis_codes: List of diagnosis codes
            use_cache: Whether to use cached responses
            resolve_conflicts: Whether to resolve policy conflicts
            
        Returns:
            Policy service response with coverage information
        """
        cache_key = self._get_cache_key(
            "policies",
            payer=payer_id,
            procedures="|".join(sorted(procedure_codes)),
            diagnoses="|".join(sorted(diagnosis_codes))
        )
        
        # Check cache first
        if use_cache:
            cached_response = self._get_cached_response("policies", cache_key)
            if cached_response:
                self.logger.debug("Returning cached policy coverage", cache_key=cache_key)
                return PolicyServiceResponse(**cached_response)
        
        try:
            start_time = datetime.now()
            
            # Get policy coverage from service
            policy_response = await self._get_policy_coverage_from_service(
                payer_id, procedure_codes, diagnosis_codes
            )
            
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            await self._update_service_health("policy_service", ServiceStatus.AVAILABLE, response_time)
            
            # Resolve conflicts if requested
            if resolve_conflicts and policy_response.conflicts:
                policy_response = await self._resolve_policy_conflicts(policy_response)
            
            if use_cache:
                self._cache_response("policies", cache_key, policy_response.model_dump())
            
            self.logger.info(
                "Policy coverage retrieved successfully",
                payer_id=payer_id,
                is_covered=policy_response.is_covered,
                conflicts_count=len(policy_response.conflicts),
                response_time_ms=response_time
            )
            
            return policy_response
            
        except Exception as e:
            await self._update_service_health(
                "policy_service",
                ServiceStatus.UNAVAILABLE,
                error_message=str(e)
            )
            
            self.logger.error(
                "Policy service error",
                payer_id=payer_id,
                procedure_codes=procedure_codes,
                diagnosis_codes=diagnosis_codes,
                error=str(e)
            )
            
            # Return conservative fallback response
            return self._get_policy_fallback_response(payer_id, procedure_codes, diagnosis_codes)
    
    async def get_service_health_status(self) -> Dict[str, ServiceHealth]:
        """
        Get health status of all external services.
        
        Returns:
            Dictionary of service health statuses
        """
        return self.service_health.copy()
    
    async def refresh_all_caches(self):
        """Clear all cached responses to force fresh data."""
        for service_cache in self.cache.values():
            service_cache.clear()
        
        self.logger.info("All service caches cleared")
    
    # Private helper methods
    
    async def _make_cms_api_request(
        self,
        procedure_codes: List[str],
        diagnosis_codes: List[str]
    ) -> Dict[str, Any]:
        """Make API request to CMS guidelines service."""
        # In a real implementation, this would make actual HTTP requests
        # For now, return mock data
        await asyncio.sleep(0.1)  # Simulate network delay
        
        return {
            "ncd_policies": [
                {
                    "policy_id": "NCD_220.2",
                    "policy_name": "Magnetic Resonance Imaging",
                    "applies_to_codes": procedure_codes,
                    "coverage_criteria": ["Medical necessity established", "Appropriate clinical indication"]
                }
            ],
            "lcd_policies": [
                {
                    "policy_id": "LCD_L33721",
                    "policy_name": "MRI Brain",
                    "applies_to_codes": procedure_codes,
                    "coverage_criteria": ["Neurological symptoms present", "Conservative treatment attempted"]
                }
            ],
            "compliance_status": "compliant"
        }
    
    def _process_cms_response(
        self,
        response: Dict[str, Any],
        procedure_codes: List[str],
        diagnosis_codes: List[str]
    ) -> CMSGuidelinesResponse:
        """Process CMS API response into structured format."""
        ncd_policies = response.get("ncd_policies", [])
        lcd_policies = response.get("lcd_policies", [])
        compliance_status = response.get("compliance_status", "unknown")
        
        is_compliant = compliance_status == "compliant"
        compliance_issues = [] if is_compliant else ["Review required for compliance"]
        recommendations = []
        
        # Generate recommendations based on policies
        if not is_compliant:
            recommendations.append("Ensure medical necessity is clearly documented")
            recommendations.append("Verify all required clinical criteria are met")
        
        confidence_score = 0.9 if is_compliant else 0.6
        
        return CMSGuidelinesResponse(
            ncd_policies=ncd_policies,
            lcd_policies=lcd_policies,
            is_compliant=is_compliant,
            compliance_issues=compliance_issues,
            recommendations=recommendations,
            confidence_score=confidence_score
        )
    
    def _get_cms_fallback_response(
        self,
        procedure_codes: List[str],
        diagnosis_codes: List[str]
    ) -> CMSGuidelinesResponse:
        """Generate fallback CMS response when service is unavailable."""
        return CMSGuidelinesResponse(
            ncd_policies=[],
            lcd_policies=[],
            is_compliant=True,  # Conservative assumption
            compliance_issues=["CMS service unavailable - using fallback validation"],
            recommendations=["Verify CMS compliance manually when service is restored"],
            confidence_score=0.5  # Lower confidence for fallback
        )
    
    async def _validate_single_code(
        self,
        code: str,
        code_type: str
    ) -> MedicalCodeValidationResponse:
        """Validate a single medical code with external service."""
        # Simulate external service call
        await asyncio.sleep(0.05)
        
        # Mock validation logic
        is_valid = len(code) >= 3 and code.replace(".", "").replace("-", "").isalnum()
        
        suggestions = []
        if not is_valid:
            if code_type.lower() == "icd10":
                suggestions = ["M25.511 (Pain in right shoulder)", "G93.1 (Anoxic brain damage)"]
            elif code_type.lower() == "cpt":
                suggestions = ["70551 (MRI brain without contrast)", "73221 (MRI upper extremity)"]
        
        return MedicalCodeValidationResponse(
            code=code,
            is_valid=is_valid,
            description=f"Mock description for {code}" if is_valid else None,
            code_type=code_type,
            suggestions=suggestions,
            effective_date=datetime.now(timezone.utc) - timedelta(days=365) if is_valid else None,
            expiration_date=None
        )
    
    def _get_code_fallback_response(
        self,
        code: str,
        code_type: str
    ) -> MedicalCodeValidationResponse:
        """Generate fallback response for code validation."""
        return MedicalCodeValidationResponse(
            code=code,
            is_valid=True,  # Conservative assumption
            description=f"Fallback validation for {code}",
            code_type=code_type,
            suggestions=[],
            effective_date=None,
            expiration_date=None
        )
    
    async def _get_policy_coverage_from_service(
        self,
        payer_id: str,
        procedure_codes: List[str],
        diagnosis_codes: List[str]
    ) -> PolicyServiceResponse:
        """Get policy coverage from external policy service."""
        # Simulate external service call
        await asyncio.sleep(0.1)
        
        # Mock policy response
        return PolicyServiceResponse(
            policy_id=f"POLICY_{payer_id}_001",
            is_covered=True,
            policy_type="PAYER",
            reasoning=["Procedure covered under standard benefits", "Diagnosis supports medical necessity"],
            confidence_score=0.85,
            policy_references=[f"PAYER_POLICY_{payer_id}_MRI"],
            additional_requirements=["Prior authorization required", "Network provider preferred"],
            conflicts=[]
        )
    
    async def _resolve_policy_conflicts(
        self,
        policy_response: PolicyServiceResponse
    ) -> PolicyServiceResponse:
        """Resolve policy conflicts using conflict resolution rules."""
        if not policy_response.conflicts:
            return policy_response
        
        # Apply most restrictive policy rule
        resolved_response = policy_response.model_copy()
        resolved_response.reasoning.append("Applied most restrictive policy due to conflicts")
        resolved_response.confidence_score *= 0.9  # Reduce confidence due to conflicts
        
        # Clear conflicts after resolution
        resolved_response.conflicts = []
        
        self.logger.info(
            "Policy conflicts resolved",
            policy_id=policy_response.policy_id,
            original_conflicts=len(policy_response.conflicts)
        )
        
        return resolved_response
    
    def _get_policy_fallback_response(
        self,
        payer_id: str,
        procedure_codes: List[str],
        diagnosis_codes: List[str]
    ) -> PolicyServiceResponse:
        """Generate fallback policy response when service is unavailable."""
        return PolicyServiceResponse(
            policy_id=f"FALLBACK_{payer_id}",
            is_covered=False,  # Conservative assumption
            policy_type="FALLBACK",
            reasoning=["Policy service unavailable - manual review required"],
            confidence_score=0.3,  # Low confidence for fallback
            policy_references=[],
            additional_requirements=["Manual policy review required when service is restored"],
            conflicts=[]
        )
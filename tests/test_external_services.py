"""
Tests for external service integrations.

This module provides comprehensive tests for external service integrations
including CMS guidelines, medical code validation, and policy services
with mock responses and error handling scenarios.
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from tests.utils.async_helpers import (
    async_test_with_timeout,
    reliable_async_test,
    AsyncResourceManager
)

from src.services.external_services import (
    ExternalServiceIntegrator,
    ServiceStatus,
    CMSGuidelinesResponse,
    MedicalCodeValidationResponse,
    PolicyServiceResponse
)


class TestExternalServiceIntegrator:
    """Test cases for external service integrator."""
    
    @pytest_asyncio.fixture
    async def integrator(self):
        """Create external service integrator for testing."""
        integrator = ExternalServiceIntegrator()
        yield integrator
        await integrator.close()
    
    @pytest.mark.asyncio
    @async_test_with_timeout(timeout=15.0)
    @pytest.mark.asyncio
    async def test_cms_guidelines_success(self, integrator):
        """Test successful CMS guidelines retrieval."""
        procedure_codes = ["70551"]
        diagnosis_codes = ["G93.1"]
        
        # Mock the CMS API request
        with patch.object(integrator, '_make_cms_api_request') as mock_request:
            mock_request.return_value = {
                "ncd_policies": [
                    {
                        "policy_id": "NCD_220.2",
                        "policy_name": "Magnetic Resonance Imaging",
                        "applies_to_codes": procedure_codes,
                        "coverage_criteria": ["Medical necessity established"]
                    }
                ],
                "lcd_policies": [],
                "compliance_status": "compliant"
            }
            
            response = await integrator.get_cms_guidelines(
                procedure_codes=procedure_codes,
                diagnosis_codes=diagnosis_codes,
                use_cache=False
            )
            
            assert isinstance(response, CMSGuidelinesResponse)
            assert response.is_compliant is True
            assert len(response.ncd_policies) == 1
            assert response.confidence_score > 0.8
            
            # Verify service health was updated
            health = await integrator.get_service_health_status()
            assert "cms_guidelines" in health
            assert health["cms_guidelines"].status == ServiceStatus.AVAILABLE
    
    @pytest.mark.asyncio

    
    async def test_cms_guidelines_caching(self, integrator):
        """Test CMS guidelines caching functionality."""
        procedure_codes = ["70551"]
        diagnosis_codes = ["G93.1"]
        
        with patch.object(integrator, '_make_cms_api_request') as mock_request:
            mock_request.return_value = {
                "ncd_policies": [],
                "lcd_policies": [],
                "compliance_status": "compliant"
            }
            
            # First request should call the API
            response1 = await integrator.get_cms_guidelines(
                procedure_codes=procedure_codes,
                diagnosis_codes=diagnosis_codes,
                use_cache=True
            )
            
            # Second request should use cache
            response2 = await integrator.get_cms_guidelines(
                procedure_codes=procedure_codes,
                diagnosis_codes=diagnosis_codes,
                use_cache=True
            )
            
            # API should only be called once
            assert mock_request.call_count == 1
            
            # Responses should be identical
            assert response1.model_dump() == response2.model_dump()
    
    @pytest.mark.asyncio

    
    async def test_cms_guidelines_fallback(self, integrator):
        """Test CMS guidelines fallback on service error."""
        procedure_codes = ["70551"]
        diagnosis_codes = ["G93.1"]
        
        with patch.object(integrator, '_make_cms_api_request') as mock_request:
            mock_request.side_effect = Exception("Service unavailable")
            
            response = await integrator.get_cms_guidelines(
                procedure_codes=procedure_codes,
                diagnosis_codes=diagnosis_codes,
                use_cache=False,
                fallback_on_error=True
            )
            
            assert isinstance(response, CMSGuidelinesResponse)
            assert response.is_compliant is True  # Conservative fallback
            assert "CMS service unavailable" in response.compliance_issues[0]
            assert response.confidence_score == 0.5  # Lower confidence
            
            # Verify service health shows unavailable
            health = await integrator.get_service_health_status()
            assert health["cms_guidelines"].status == ServiceStatus.UNAVAILABLE
    
    @pytest.mark.asyncio

    
    async def test_medical_code_validation_success(self, integrator):
        """Test successful medical code validation."""
        codes = [
            {"code": "70551", "code_type": "cpt"},
            {"code": "G93.1", "code_type": "icd10"}
        ]
        
        responses = await integrator.validate_medical_codes(
            codes=codes,
            use_cache=False
        )
        
        assert len(responses) == 2
        
        for response in responses:
            assert isinstance(response, MedicalCodeValidationResponse)
            assert response.is_valid is True
            assert response.code in ["70551", "G93.1"]
            assert response.code_type in ["cpt", "icd10"]
    
    @pytest.mark.asyncio

    
    async def test_medical_code_validation_invalid_codes(self, integrator):
        """Test medical code validation with invalid codes."""
        codes = [
            {"code": "INVALID", "code_type": "cpt"},
            {"code": "X", "code_type": "icd10"}
        ]
        
        responses = await integrator.validate_medical_codes(
            codes=codes,
            use_cache=False
        )
        
        assert len(responses) == 2
        
        for response in responses:
            assert isinstance(response, MedicalCodeValidationResponse)
            assert response.is_valid is False
            assert len(response.suggestions) > 0
    
    @pytest.mark.asyncio

    
    async def test_medical_code_validation_caching(self, integrator):
        """Test medical code validation caching."""
        codes = [{"code": "70551", "code_type": "cpt"}]
        
        with patch.object(integrator, '_validate_single_code') as mock_validate:
            mock_validate.return_value = MedicalCodeValidationResponse(
                code="70551",
                is_valid=True,
                description="MRI brain without contrast",
                code_type="cpt",
                suggestions=[],
                effective_date=datetime.now(timezone.utc),
                expiration_date=None
            )
            
            # First request
            responses1 = await integrator.validate_medical_codes(codes, use_cache=True)
            
            # Second request should use cache
            responses2 = await integrator.validate_medical_codes(codes, use_cache=True)
            
            # Validation should only be called once
            assert mock_validate.call_count == 1
            
            # Responses should be identical
            assert responses1[0].model_dump() == responses2[0].model_dump()
    
    @pytest.mark.asyncio

    
    async def test_medical_code_validation_fallback(self, integrator):
        """Test medical code validation fallback on service error."""
        codes = [{"code": "70551", "code_type": "cpt"}]
        
        with patch.object(integrator, '_validate_single_code') as mock_validate:
            mock_validate.side_effect = Exception("Validation service error")
            
            responses = await integrator.validate_medical_codes(
                codes=codes,
                use_cache=False,
                fallback_on_error=True
            )
            
            assert len(responses) == 1
            response = responses[0]
            
            assert isinstance(response, MedicalCodeValidationResponse)
            assert response.is_valid is True  # Conservative fallback
            assert "Fallback validation" in response.description
    
    @pytest.mark.asyncio

    
    async def test_policy_coverage_success(self, integrator):
        """Test successful policy coverage retrieval."""
        payer_id = "PAYER_001"
        procedure_codes = ["70551"]
        diagnosis_codes = ["G93.1"]
        
        with patch.object(integrator, '_get_policy_coverage_from_service') as mock_policy:
            mock_policy.return_value = PolicyServiceResponse(
                policy_id="POLICY_001",
                is_covered=True,
                policy_type="PAYER",
                reasoning=["Procedure covered"],
                confidence_score=0.9,
                policy_references=["PAYER_POLICY_MRI"],
                additional_requirements=[],
                conflicts=[]
            )
            
            response = await integrator.get_policy_coverage(
                payer_id=payer_id,
                procedure_codes=procedure_codes,
                diagnosis_codes=diagnosis_codes,
                use_cache=False
            )
            
            assert isinstance(response, PolicyServiceResponse)
            assert response.is_covered is True
            assert response.confidence_score == 0.9
            assert len(response.policy_references) > 0
    
    @pytest.mark.asyncio

    
    async def test_policy_coverage_conflict_resolution(self, integrator):
        """Test policy coverage conflict resolution."""
        payer_id = "PAYER_001"
        procedure_codes = ["70551"]
        diagnosis_codes = ["G93.1"]
        
        with patch.object(integrator, '_get_policy_coverage_from_service') as mock_policy:
            mock_policy.return_value = PolicyServiceResponse(
                policy_id="POLICY_001",
                is_covered=True,
                policy_type="PAYER",
                reasoning=["Procedure covered"],
                confidence_score=0.9,
                policy_references=["PAYER_POLICY_MRI"],
                additional_requirements=[],
                conflicts=[
                    {"type": "coverage_conflict", "description": "Conflicting policies found"}
                ]
            )
            
            response = await integrator.get_policy_coverage(
                payer_id=payer_id,
                procedure_codes=procedure_codes,
                diagnosis_codes=diagnosis_codes,
                use_cache=False,
                resolve_conflicts=True
            )
            
            assert isinstance(response, PolicyServiceResponse)
            assert len(response.conflicts) == 0  # Conflicts should be resolved
            assert response.confidence_score < 0.9  # Reduced due to conflicts
            assert "most restrictive policy" in " ".join(response.reasoning)
    
    @pytest.mark.asyncio

    
    async def test_policy_coverage_caching(self, integrator):
        """Test policy coverage caching."""
        payer_id = "PAYER_001"
        procedure_codes = ["70551"]
        diagnosis_codes = ["G93.1"]
        
        with patch.object(integrator, '_get_policy_coverage_from_service') as mock_policy:
            mock_policy.return_value = PolicyServiceResponse(
                policy_id="POLICY_001",
                is_covered=True,
                policy_type="PAYER",
                reasoning=["Procedure covered"],
                confidence_score=0.9,
                policy_references=["PAYER_POLICY_MRI"],
                additional_requirements=[],
                conflicts=[]
            )
            
            # First request
            response1 = await integrator.get_policy_coverage(
                payer_id=payer_id,
                procedure_codes=procedure_codes,
                diagnosis_codes=diagnosis_codes,
                use_cache=True
            )
            
            # Second request should use cache
            response2 = await integrator.get_policy_coverage(
                payer_id=payer_id,
                procedure_codes=procedure_codes,
                diagnosis_codes=diagnosis_codes,
                use_cache=True
            )
            
            # Service should only be called once
            assert mock_policy.call_count == 1
            
            # Responses should be identical
            assert response1.model_dump() == response2.model_dump()
    
    @pytest.mark.asyncio

    
    async def test_policy_coverage_fallback(self, integrator):
        """Test policy coverage fallback on service error."""
        payer_id = "PAYER_001"
        procedure_codes = ["70551"]
        diagnosis_codes = ["G93.1"]
        
        with patch.object(integrator, '_get_policy_coverage_from_service') as mock_policy:
            mock_policy.side_effect = Exception("Policy service error")
            
            response = await integrator.get_policy_coverage(
                payer_id=payer_id,
                procedure_codes=procedure_codes,
                diagnosis_codes=diagnosis_codes,
                use_cache=False
            )
            
            assert isinstance(response, PolicyServiceResponse)
            assert response.is_covered is False  # Conservative fallback
            assert response.policy_type == "FALLBACK"
            assert response.confidence_score == 0.3  # Low confidence
            assert "Manual policy review required" in response.additional_requirements[0]
    
    @pytest.mark.asyncio

    
    async def test_service_health_monitoring(self, integrator):
        """Test service health monitoring functionality."""
        # Initially no health data
        health = await integrator.get_service_health_status()
        assert len(health) == 0
        
        # Make some service calls to populate health data
        await integrator.get_cms_guidelines(["70551"], ["G93.1"], use_cache=False)
        await integrator.validate_medical_codes([{"code": "70551", "code_type": "cpt"}], use_cache=False)
        
        # Check health status
        health = await integrator.get_service_health_status()
        
        assert "cms_guidelines" in health
        assert "medical_codes" in health
        
        for service_health in health.values():
            assert service_health.status in [ServiceStatus.AVAILABLE, ServiceStatus.UNAVAILABLE]
            assert service_health.last_check is not None
    
    @pytest.mark.asyncio
    @async_test_with_timeout(timeout=20.0)
    async def test_cache_expiration(self, integrator):
        """Test cache expiration functionality."""
        # Set very short TTL for testing
        integrator.cache_ttl["cms_guidelines"] = 1  # 1 second
        
        procedure_codes = ["70551"]
        diagnosis_codes = ["G93.1"]
        
        with patch.object(integrator, '_make_cms_api_request') as mock_request:
            mock_request.return_value = {
                "ncd_policies": [],
                "lcd_policies": [],
                "compliance_status": "compliant"
            }
            
            # First request
            await integrator.get_cms_guidelines(
                procedure_codes=procedure_codes,
                diagnosis_codes=diagnosis_codes,
                use_cache=True
            )
            
            # Wait for cache to expire with proper timeout handling
            await asyncio.sleep(1.1)
            
            # Second request should call API again due to expired cache
            await integrator.get_cms_guidelines(
                procedure_codes=procedure_codes,
                diagnosis_codes=diagnosis_codes,
                use_cache=True
            )
            
            # API should be called twice
            assert mock_request.call_count == 2
    
    @pytest.mark.asyncio

    
    async def test_cache_refresh(self, integrator):
        """Test cache refresh functionality."""
        # Add some data to cache
        await integrator.get_cms_guidelines(["70551"], ["G93.1"], use_cache=True)
        await integrator.validate_medical_codes([{"code": "70551", "code_type": "cpt"}], use_cache=True)
        
        # Verify cache has data
        assert len(integrator.cache["cms_guidelines"]) > 0
        assert len(integrator.cache["medical_codes"]) > 0
        
        # Refresh all caches
        await integrator.refresh_all_caches()
        
        # Verify caches are empty
        assert len(integrator.cache["cms_guidelines"]) == 0
        assert len(integrator.cache["medical_codes"]) == 0
        assert len(integrator.cache["policies"]) == 0
    
    @pytest.mark.asyncio
    @reliable_async_test(timeout=30.0, retries=1)
    async def test_concurrent_requests(self, integrator):
        """Test handling of concurrent requests to external services."""
        procedure_codes = ["70551"]
        diagnosis_codes = ["G93.1"]
        
        # Make multiple concurrent requests
        tasks = []
        for i in range(5):
            task = integrator.get_cms_guidelines(
                procedure_codes=procedure_codes,
                diagnosis_codes=diagnosis_codes,
                use_cache=False
            )
            tasks.append(task)
        
        responses = await asyncio.gather(*tasks)
        
        # All requests should succeed
        assert len(responses) == 5
        for response in responses:
            assert isinstance(response, CMSGuidelinesResponse)
    
    @pytest.mark.asyncio
    @async_test_with_timeout(timeout=10.0)
    async def test_context_manager(self):
        """Test async context manager functionality."""
        async with ExternalServiceIntegrator() as integrator:
            # Should be able to use integrator normally
            response = await integrator.get_cms_guidelines(["70551"], ["G93.1"])
            assert isinstance(response, CMSGuidelinesResponse)
        
        # Client should be closed after context exit
        assert integrator.client.is_closed


class TestExternalServiceIntegration:
    """Integration tests with mock external services."""
    
    @pytest.mark.asyncio

    
    async def test_full_workflow_integration(self):
        """Test complete workflow with all external services."""
        async with ExternalServiceIntegrator() as integrator:
            payer_id = "PAYER_001"
            procedure_codes = ["70551"]
            diagnosis_codes = ["G93.1"]
            
            # Get CMS guidelines
            cms_response = await integrator.get_cms_guidelines(
                procedure_codes=procedure_codes,
                diagnosis_codes=diagnosis_codes
            )
            
            # Validate medical codes
            codes_to_validate = [
                {"code": "70551", "code_type": "cpt"},
                {"code": "G93.1", "code_type": "icd10"}
            ]
            validation_responses = await integrator.validate_medical_codes(codes_to_validate)
            
            # Get policy coverage
            policy_response = await integrator.get_policy_coverage(
                payer_id=payer_id,
                procedure_codes=procedure_codes,
                diagnosis_codes=diagnosis_codes
            )
            
            # Verify all responses
            assert isinstance(cms_response, CMSGuidelinesResponse)
            assert len(validation_responses) == 2
            assert all(isinstance(r, MedicalCodeValidationResponse) for r in validation_responses)
            assert isinstance(policy_response, PolicyServiceResponse)
            
            # Check service health
            health = await integrator.get_service_health_status()
            assert len(health) >= 3  # Should have health data for all services
    
    @pytest.mark.asyncio

    
    async def test_error_recovery_workflow(self):
        """Test error recovery and fallback mechanisms."""
        async with ExternalServiceIntegrator() as integrator:
            # Simulate service failures
            with patch.object(integrator, '_make_cms_api_request') as mock_cms:
                mock_cms.side_effect = Exception("CMS service down")
                
                with patch.object(integrator, '_validate_single_code') as mock_validate:
                    mock_validate.side_effect = Exception("Validation service down")
                    
                    # Services should fall back gracefully
                    cms_response = await integrator.get_cms_guidelines(
                        ["70551"], ["G93.1"], fallback_on_error=True
                    )
                    
                    validation_responses = await integrator.validate_medical_codes(
                        [{"code": "70551", "code_type": "cpt"}], fallback_on_error=True
                    )
                    
                    # Verify fallback responses
                    assert cms_response.confidence_score == 0.5  # Lower confidence
                    assert "CMS service unavailable" in cms_response.compliance_issues[0]
                    
                    assert validation_responses[0].is_valid is True  # Conservative fallback
                    assert "Fallback validation" in validation_responses[0].description


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
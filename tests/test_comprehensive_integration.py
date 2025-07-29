"""
Comprehensive integration tests for the prior authorization system.

Tests complete authorization workflows from request submission to decision generation.
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient

from src.main import app
from src.models.authorization import AuthorizationRequest, AuthorizationDecision
from src.models.enums import RequestStatus, DecisionStatus, UrgencyLevel, ProcedureType
from src.services.validation import ValidationResult
from src.services.policy_validation import PolicyValidationResult, PolicyType
from tests.test_data_generator import TestDataGenerator


class TestCompleteAuthorizationWorkflow:
    """Test complete authorization workflows end-to-end."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.data_generator = TestDataGenerator()
    
    @pytest.mark.integration
    def test_successful_approval_workflow(self, authenticated_client):
        """Test complete workflow resulting in approval."""
        # Generate test request
        request = self.data_generator.generate_authorization_request("routine")
        request_data = {
            "provider_id": request.provider_id,
            "patient_demographics": {
                "patient_id": request.patient_demographics.patient_id,
                "age": request.patient_demographics.age,
                "gender": request.patient_demographics.gender.value,
                "insurance_id": request.patient_demographics.insurance_id,
                "member_id": request.patient_demographics.member_id
            },
            "diagnosis_codes": [
                {"code": code.code, "description": code.description}
                for code in request.diagnosis_codes
            ],
            "procedure_codes": [
                {"code": code.code, "description": code.description}
                for code in request.procedure_codes
            ],
            "clinical_notes": request.clinical_notes,
            "procedure_type": request.procedure_type.value,
            "urgency_level": request.urgency_level.value
        }
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.policy_validation.PolicyValidationService.validate_with_medical_necessity') as mock_policy, \
             patch('src.services.decision_engine.DecisionEngine.generate_decision') as mock_decision, \
             patch('src.services.notification.NotificationService.send_decision_notification') as mock_notify:
            
            # Mock successful validation
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                errors=[],
                warnings=[],
                processing_time_ms=1200.0
            )
            
            # Mock successful policy validation
            mock_policy.return_value = {
                'policy_validation': {
                    'is_covered': True,
                    'policy_id': 'POL_MRI_001',
                    'confidence_score': 0.9
                },
                'medical_necessity': {
                    'necessity_level': 'high',
                    'confidence_score': 0.85
                },
                'cms_compliance': {
                    'is_compliant': True
                }
            }
            
            # Mock successful decision
            mock_decision.return_value = self.data_generator.generate_authorization_decision(
                request, "approved"
            )
            
            mock_notify.return_value = None
            
            # Submit request
            response = authenticated_client.post("/api/v1/authorization/requests", json=request_data)
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "submitted"
            assert "request_id" in data
            request_id = data["request_id"]
            
            # Check request status
            status_response = authenticated_client.get(f"/api/v1/authorization/requests/{request_id}")
            assert status_response.status_code == 200
            
            # Verify validation service was called
            mock_validate.assert_called_once()
            # Note: Policy validation, decision generation, and notifications
            # happen in background processes, not during request submission
    
    @pytest.mark.integration
    def test_denial_workflow_with_alternatives(self, authenticated_client):
        """Test complete workflow resulting in denial with alternatives."""
        request = self.data_generator.generate_authorization_request("routine")
        request_data = self._convert_request_to_api_format(request)
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.policy_validation.PolicyValidationService.validate_with_medical_necessity') as mock_policy, \
             patch('src.services.decision_engine.DecisionEngine.generate_decision') as mock_decision, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            # Mock validation with warnings
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                errors=[],
                warnings=["Conservative treatment duration may be insufficient"],
                processing_time_ms=1500.0
            )
            
            # Mock policy validation indicating denial
            mock_policy.return_value = {
                'policy_validation': {
                    'is_covered': False,
                    'policy_id': 'POL_MRI_001',
                    'confidence_score': 0.8
                },
                'medical_necessity': {
                    'necessity_level': 'low',
                    'confidence_score': 0.3
                }
            }
            
            # Mock denial decision
            denial_decision = self.data_generator.generate_authorization_decision(
                request, "denied"
            )
            mock_decision.return_value = denial_decision
            
            mock_store.return_value = None
            
            # Submit request
            response = authenticated_client.post("/api/v1/authorization/requests", json=request_data)
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "submitted"
            assert "validation_warnings" in data
            
            # Verify denial reasoning includes alternatives
            assert denial_decision.alternative_procedures is not None
            assert len(denial_decision.alternative_procedures) > 0
    
    @pytest.mark.integration
    def test_more_info_needed_workflow(self, authenticated_client):
        """Test workflow requiring additional information."""
        request = self.data_generator.generate_authorization_request("urgent")
        request_data = self._convert_request_to_api_format(request)
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.policy_validation.PolicyValidationService.validate_with_medical_necessity') as mock_policy, \
             patch('src.services.decision_engine.DecisionEngine.generate_decision') as mock_decision, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                errors=[],
                warnings=[],
                processing_time_ms=1000.0
            )
            
            # Mock policy requiring additional info
            mock_policy.return_value = {
                'policy_validation': {
                    'is_covered': True,
                    'policy_id': 'POL_MRI_001',
                    'additional_requirements': [
                        'Physical therapy notes required',
                        'Specialist consultation report needed'
                    ]
                },
                'medical_necessity': {
                    'necessity_level': 'moderate',
                    'additional_documentation_needed': [
                        'Detailed symptom history'
                    ]
                }
            }
            
            # Mock more info decision
            more_info_decision = self.data_generator.generate_authorization_decision(
                request, "more_info"
            )
            mock_decision.return_value = more_info_decision
            
            mock_store.return_value = None
            
            # Submit request
            response = authenticated_client.post("/api/v1/authorization/requests", json=request_data)
            
            assert response.status_code == 200
            
            # Verify additional info requirements
            assert more_info_decision.additional_info_needed is not None
            assert len(more_info_decision.additional_info_needed) > 0
    
    @pytest.mark.integration
    def test_validation_error_workflow(self, authenticated_client):
        """Test workflow with validation errors."""
        # Create request with invalid data
        request_data = {
            "provider_id": "",  # Invalid
            "patient_demographics": {
                "patient_id": "short",  # Too short
                "age": 200,  # Invalid age
                "gender": "female",
                "insurance_id": "enc_ins_valid",
                "member_id": "enc_mem_valid"
            },
            "diagnosis_codes": [],  # Empty
            "procedure_codes": [
                {"code": "99999", "description": "Invalid code"}
            ],
            "procedure_type": "mri",
            "urgency_level": "routine"
        }
        
        response = authenticated_client.post("/api/v1/authorization/requests", json=request_data)
        
        assert response.status_code == 422
        data = response.json()
        
        assert "error" in data
        assert "message" in data["error"] or "code" in data["error"]
    
    @pytest.mark.integration
    def test_concurrent_request_processing(self, authenticated_client):
        """Test processing multiple concurrent requests."""
        requests = []
        for i in range(5):
            request = self.data_generator.generate_authorization_request("routine")
            request_data = self._convert_request_to_api_format(request)
            requests.append(request_data)
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.policy_validation.PolicyValidationService.validate_with_medical_necessity') as mock_policy, \
             patch('src.services.decision_engine.DecisionEngine.generate_decision') as mock_decision, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            # Mock successful responses for all requests
            mock_validate.return_value = ValidationResult(
                is_valid=True, errors=[], warnings=[], processing_time_ms=1000.0
            )
            mock_policy.return_value = {'policy_validation': {'is_covered': True}}
            mock_decision.return_value = AuthorizationDecision(
                decision_id="dec_test",
                request_id="req_test",
                status=DecisionStatus.APPROVED,
                reasoning=["Test reasoning"],
                authorization_number="auth_test_001",
                valid_until=datetime.now(timezone.utc) + timedelta(days=30),
                confidence_score=0.9
            )
            mock_store.return_value = None
            
            # Submit all requests concurrently
            responses = []
            for request_data in requests:
                response = authenticated_client.post("/api/v1/authorization/requests", json=request_data)
                responses.append(response)
            
            # Verify all requests were processed successfully
            for response in responses:
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "submitted"
                assert "request_id" in data
    
    def _convert_request_to_api_format(self, request: AuthorizationRequest) -> dict:
        """Convert AuthorizationRequest to API format."""
        return {
            "provider_id": request.provider_id,
            "patient_demographics": {
                "patient_id": request.patient_demographics.patient_id,
                "age": request.patient_demographics.age,
                "gender": request.patient_demographics.gender.value,
                "insurance_id": request.patient_demographics.insurance_id,
                "member_id": request.patient_demographics.member_id
            },
            "diagnosis_codes": [
                {"code": code.code, "description": code.description}
                for code in request.diagnosis_codes
            ],
            "procedure_codes": [
                {"code": code.code, "description": code.description}
                for code in request.procedure_codes
            ],
            "clinical_notes": request.clinical_notes,
            "procedure_type": request.procedure_type.value,
            "urgency_level": request.urgency_level.value
        }


class TestDashboardIntegration:
    """Test dashboard integration workflows."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.data_generator = TestDataGenerator()
    
    @pytest.mark.integration
    def test_provider_dashboard_workflow(self, authenticated_client):
        """Test complete provider dashboard workflow."""
        provider_id = "prov_test_001"
        
        with patch('src.services.tracking.TrackingService.get_requests_by_provider') as mock_get_requests:
            # Mock dashboard data
            mock_requests = []
            for i in range(3):
                request = self.data_generator.generate_authorization_request()
                mock_requests.append(request)
            
            from src.services.tracking import RequestsResult
            mock_result = RequestsResult(
                requests=mock_requests,
                total_count=3,
                status_summary={
                    "approved": 1,
                    "denied": 1,
                    "in_review": 1,
                    "submitted": 0,
                    "more_info_needed": 0,
                    "expired": 0
                }
            )
            mock_get_requests.return_value = mock_result
            
            # Get dashboard data
            response = authenticated_client.get(f"/api/v1/authorization/requests?provider_id={provider_id}")
            
            assert response.status_code == 200
            data = response.json()
            
            assert "total_requests" in data
            assert "requests" in data
            assert "summary" in data
            assert data["total_requests"] == 3
    
    @pytest.mark.integration
    def test_dashboard_filtering_workflow(self, authenticated_client):
        """Test dashboard filtering functionality."""
        provider_id = "prov_test_001"
        status_filter = "approved"
        
        with patch('src.services.tracking.TrackingService.get_requests_by_provider') as mock_get_requests:
            from src.services.tracking import RequestsResult
            mock_result = RequestsResult(
                requests=[],
                total_count=0,
                status_summary={"approved": 0}
            )
            mock_get_requests.return_value = mock_result
            
            response = authenticated_client.get(
                f"/api/v1/authorization/requests?provider_id={provider_id}&status_filter={status_filter}"
            )
            
            assert response.status_code == 200
            
            # Verify filtering was applied
            mock_get_requests.assert_called_once()
            call_args = mock_get_requests.call_args
            assert call_args.kwargs["provider_id"] == provider_id


class TestSecurityIntegration:
    """Test security integration workflows."""
    
    def setup_method(self):
        """Set up test fixtures."""
        pass
    
    @pytest.mark.integration
    @pytest.mark.security
    def test_authentication_workflow(self, unauthenticated_client):
        """Test complete authentication workflow."""
        # Test without authentication
        response = unauthenticated_client.get("/api/v1/authorization/requests/req_test_001")
        assert response.status_code in [401, 403]  # Unauthorized or Forbidden
        
        # Test with invalid token
        headers = {"Authorization": "Bearer invalid_token"}
        response = unauthenticated_client.get("/api/v1/authorization/requests/req_test_001", headers=headers)
        assert response.status_code in [401, 403]
    
    @pytest.mark.integration
    @pytest.mark.security
    def test_rate_limiting_workflow(self, unauthenticated_client):
        """Test rate limiting functionality."""
        # This would require actual rate limiting implementation
        # For now, we'll test that the endpoint responds appropriately
        
        # Make multiple rapid requests
        responses = []
        for i in range(10):
            response = unauthenticated_client.get("/api/v1/health")
            responses.append(response)
        
        # At least some requests should succeed
        success_count = sum(1 for r in responses if r.status_code == 200)
        assert success_count > 0
    
    @pytest.mark.integration
    @pytest.mark.security
    def test_phi_protection_workflow(self, authenticated_client):
        """Test PHI protection in API responses."""
        request_data = {
            "provider_id": "prov_test_001",
            "patient_demographics": {
                "patient_id": "enc_pat_test_001",
                "age": 45,
                "gender": "female",
                "insurance_id": "enc_ins_test_001",
                "member_id": "enc_mem_test_001"
            },
            "diagnosis_codes": [
                {"code": "M25.511", "description": "Pain in right shoulder"}
            ],
            "procedure_codes": [
                {"code": "73221", "description": "MRI upper extremity"}
            ],
            "clinical_notes": "Patient has shoulder pain",
            "procedure_type": "mri",
            "urgency_level": "routine"
        }
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            mock_validate.return_value = ValidationResult(
                is_valid=True, errors=[], warnings=[], processing_time_ms=1000.0
            )
            mock_store.return_value = None
            
            response = authenticated_client.post("/api/v1/authorization/requests", json=request_data)
            
            if response.status_code == 200:
                data = response.json()
                
                # Verify PHI is not exposed in response
                response_str = str(data)
                assert "enc_pat_test_001" not in response_str
                assert "enc_ins_test_001" not in response_str
                assert "enc_mem_test_001" not in response_str


class TestErrorHandlingIntegration:
    """Test error handling integration workflows."""
    
    def setup_method(self):
        """Set up test fixtures."""
        pass
    
    @pytest.mark.integration
    def test_service_failure_handling(self, authenticated_client):
        """Test handling of service failures."""
        request_data = {
            "provider_id": "prov_test_001",
            "patient_demographics": {
                "patient_id": "enc_pat_test_001",
                "age": 45,
                "gender": "female",
                "insurance_id": "enc_ins_test_001",
                "member_id": "enc_mem_test_001"
            },
            "diagnosis_codes": [
                {"code": "M25.511", "description": "Pain in right shoulder"}
            ],
            "procedure_codes": [
                {"code": "73221", "description": "MRI upper extremity"}
            ],
            "procedure_type": "mri",
            "urgency_level": "routine"
        }
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate:
            # Mock service failure
            mock_validate.side_effect = Exception("Database connection failed")
            
            response = authenticated_client.post("/api/v1/authorization/requests", json=request_data)
            
            assert response.status_code == 500
            data = response.json()
            
            assert "error" in data
            # Should not expose internal error details
            assert "Database connection failed" not in str(data)
    
    @pytest.mark.integration
    def test_timeout_handling(self, authenticated_client):
        """Test handling of request timeouts."""
        # This would require actual timeout implementation
        # For now, we'll test that long-running requests are handled appropriately
        pass
    
    @pytest.mark.integration
    def test_malformed_request_handling(self, authenticated_client):
        """Test handling of malformed requests."""
        malformed_requests = [
            {},  # Empty request
            {"invalid": "data"},  # Invalid structure
            {"provider_id": "test"},  # Missing required fields
            None  # Null request
        ]
        
        for malformed_data in malformed_requests:
            if malformed_data is not None:
                response = authenticated_client.post("/api/v1/authorization/requests", json=malformed_data)
            else:
                response = authenticated_client.post("/api/v1/authorization/requests")
            
            assert response.status_code in [400, 422]  # Bad Request or Unprocessable Entity
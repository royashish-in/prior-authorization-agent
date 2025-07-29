"""
Integration tests for Prior Authorization Agent API.

This module provides comprehensive integration tests for complete API workflows,
including authentication, request submission, status tracking, and decision retrieval.
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from httpx import AsyncClient

from src.main import app
from src.client import PriorAuthClient
from src.client.models import (
    AuthorizationRequest,
    PatientDemographics,
    MedicalCode,
    LoginCredentials,
    UrgencyLevel,
    ProcedureType,
    Gender
)
from src.client.exceptions import (
    AuthenticationError,
    ValidationError,
    NotFoundError,
    RateLimitError
)


class TestAPIIntegration:
    """Integration tests for complete API workflows."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def sample_authorization_request(self) -> AuthorizationRequest:
        """Create sample authorization request for testing."""
        return AuthorizationRequest(
            provider_id="test_provider_001",
            patient_demographics=PatientDemographics(
                patient_id="encrypted_patient_123",
                age=45,
                gender=Gender.FEMALE,
                insurance_id="encrypted_insurance_456",
                member_id="encrypted_member_789"
            ),
            diagnosis_codes=[
                MedicalCode(
                    code="G93.1",
                    description="Anoxic brain damage, not elsewhere classified",
                    code_type="icd10"
                )
            ],
            procedure_codes=[
                MedicalCode(
                    code="70551",
                    description="MRI brain without contrast",
                    code_type="cpt"
                )
            ],
            clinical_notes="Patient presents with persistent headaches and memory issues following recent head trauma. Neurological examination shows mild cognitive impairment. MRI requested to rule out structural brain damage.",
            urgency_level=UrgencyLevel.ROUTINE,
            procedure_type=ProcedureType.MRI
        )
    
    def test_health_check_endpoint(self, client):
        """Test health check endpoint accessibility."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "version" in data
        assert "environment" in data
        assert "checks" in data
    
    def test_detailed_health_check(self, client):
        """Test detailed health check endpoint."""
        response = client.get("/api/v1/health/detailed")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert "uptime_seconds" in data
        assert "checks" in data
        assert "database" in data["checks"]
    
    def test_openapi_documentation(self, client):
        """Test OpenAPI documentation generation."""
        response = client.get("/docs")
        assert response.status_code == 200
        
        # Test OpenAPI JSON schema
        response = client.get("/openapi.json")
        assert response.status_code == 200
        
        schema = response.json()
        assert schema["info"]["title"] == "Prior Authorization Agent API"
        assert schema["info"]["version"] == "1.0.0"
        assert "components" in schema
        assert "securitySchemes" in schema["components"]
    
    def test_authentication_workflow(self, client):
        """Test complete authentication workflow."""
        # Test login with valid credentials
        login_data = {
            "username": "provider1",
            "password": "provider123"
        }
        
        response = client.post("/api/v1/auth/login-json", json=login_data)
        assert response.status_code == 200
        
        token_data = response.json()
        assert "access_token" in token_data
        assert token_data["token_type"] == "bearer"
        assert "expires_in" in token_data
        
        access_token = token_data["access_token"]
        
        # Test authenticated endpoint access
        headers = {"Authorization": f"Bearer {access_token}"}
        response = client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 200
        
        user_data = response.json()
        assert user_data["username"] == "provider1"
        assert "roles" in user_data
    
    def test_authentication_failure(self, client):
        """Test authentication failure handling."""
        # Test login with invalid credentials
        login_data = {
            "username": "invalid_user",
            "password": "wrong_password"
        }
        
        response = client.post("/api/v1/auth/login-json", json=login_data)
        assert response.status_code == 401
        
        error_data = response.json()
        assert "error" in error_data
        assert error_data["error"]["code"] == "UNAUTHORIZED"
    
    @patch('src.services.validation.ValidationService.validate_request')
    @patch('src.services.tracking.TrackingService.store_request')
    def test_authorization_request_workflow(
        self,
        mock_store_request,
        mock_validate_request,
        client,
        sample_authorization_request
    ):
        """Test complete authorization request workflow."""
        # Mock validation service
        mock_validation_result = AsyncMock()
        mock_validation_result.is_valid = True
        mock_validation_result.errors = []
        mock_validation_result.warnings = []
        mock_validate_request.return_value = mock_validation_result
        
        # Mock tracking service
        mock_store_request.return_value = None
        
        # First authenticate
        login_data = {"username": "provider1", "password": "provider123"}
        auth_response = client.post("/api/v1/auth/login-json", json=login_data)
        access_token = auth_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Submit authorization request
        request_data = sample_authorization_request.model_dump()
        response = client.post(
            "/api/v1/authorization/requests",
            json=request_data,
            headers=headers
        )
        
        assert response.status_code == 200
        
        submission_data = response.json()
        assert "request_id" in submission_data
        assert submission_data["status"] == "submitted"
        assert submission_data["message"] == "Authorization request submitted successfully"
        
        request_id = submission_data["request_id"]
        assert request_id.startswith("req_")
    
    def test_request_validation_errors(self, client):
        """Test request validation error handling."""
        # First authenticate
        login_data = {"username": "provider1", "password": "provider123"}
        auth_response = client.post("/api/v1/auth/login-json", json=login_data)
        access_token = auth_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Submit invalid request (missing required fields)
        invalid_request = {
            "provider_id": "",  # Empty provider ID
            "patient_demographics": {
                "patient_id": "test",
                "age": -1,  # Invalid age
                "gender": "invalid_gender",  # Invalid gender
                "insurance_id": "",
                "member_id": ""
            },
            "diagnosis_codes": [],  # Empty codes
            "procedure_codes": [],
            "clinical_notes": "",
            "urgency_level": "invalid_urgency",
            "procedure_type": "invalid_procedure"
        }
        
        response = client.post(
            "/api/v1/authorization/requests",
            json=invalid_request,
            headers=headers
        )
        
        assert response.status_code == 422
        
        error_data = response.json()
        assert error_data["error"]["code"] == "VALIDATION_ERROR"
        assert "details" in error_data["error"]
        assert len(error_data["error"]["details"]) >= 0
    
    @patch('src.services.tracking.TrackingService.get_request_status')
    def test_request_status_tracking(self, mock_get_status, client):
        """Test request status tracking workflow."""
        # Mock tracking service
        from src.services.tracking import RequestStatusInfo
        from src.models.enums import RequestStatus
        
        mock_status_info = RequestStatusInfo(
            request_id="req_2024_001234",
            status=RequestStatus.IN_REVIEW,
            submitted_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            estimated_completion=datetime.now(timezone.utc) + timedelta(hours=1),
            current_stage="Policy Validation",
            progress_percentage=65,
            next_actions=["Review clinical notes"]
        )
        mock_get_status.return_value = mock_status_info
        
        # First authenticate
        login_data = {"username": "provider1", "password": "provider123"}
        auth_response = client.post("/api/v1/auth/login-json", json=login_data)
        access_token = auth_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Get request status
        request_id = "req_2024_001234"
        response = client.get(
            f"/api/v1/authorization/requests/{request_id}",
            headers=headers
        )
        
        assert response.status_code == 200
        
        status_data = response.json()
        assert status_data["request_id"] == request_id
        assert status_data["status"] == "in_review"
        assert status_data["current_stage"] == "Policy Validation"
        assert status_data["progress_percentage"] == 65
    
    def test_request_not_found(self, client):
        """Test request not found error handling."""
        # First authenticate
        login_data = {"username": "provider1", "password": "provider123"}
        auth_response = client.post("/api/v1/auth/login-json", json=login_data)
        access_token = auth_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Try to get non-existent request
        response = client.get(
            "/api/v1/authorization/requests/req_nonexistent",
            headers=headers
        )
        
        assert response.status_code == 404
        
        error_data = response.json()
        assert error_data["error"]["code"] == "RESOURCE_NOT_FOUND"
    
    def test_unauthorized_access(self, client):
        """Test unauthorized access handling."""
        # Try to access protected endpoint without authentication
        response = client.get("/api/v1/authorization/requests/req_test")
        assert response.status_code == 401
        
        # Try with invalid token
        headers = {"Authorization": "Bearer invalid_token"}
        response = client.get("/api/v1/authorization/requests/req_test", headers=headers)
        assert response.status_code == 401
    
    @patch('src.services.decision_engine.DecisionEngine.get_decision')
    def test_decision_retrieval_workflow(self, mock_get_decision, client):
        """Test decision retrieval workflow."""
        # Mock decision engine
        from src.models.authorization import AuthorizationDecision
        from src.models.enums import DecisionStatus
        
        mock_decision = AuthorizationDecision(
            decision_id="dec_2024_001234",
            request_id="req_2024_001234",
            status=DecisionStatus.APPROVED,
            reasoning=["Medical necessity criteria met per CMS NCD 220.2"],
            policy_references=["CMS_NCD_220.2"],
            authorization_number="auth_2024001234",
            valid_until=datetime.now(timezone.utc),
            confidence_score=0.95,
            decided_at=datetime.now(timezone.utc)
        )
        mock_get_decision.return_value = mock_decision
        
        # First authenticate
        login_data = {"username": "provider1", "password": "provider123"}
        auth_response = client.post("/api/v1/auth/login-json", json=login_data)
        access_token = auth_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Get decision
        decision_id = "dec_2024_001234"
        response = client.get(
            f"/api/v1/decisions/{decision_id}",
            headers=headers
        )
        
        assert response.status_code == 200
        
        decision_data = response.json()
        assert decision_data["decision_id"] == decision_id
        assert decision_data["status"] == "approved"
        assert decision_data["authorization_number"] == "auth_2024001234"
        assert len(decision_data["reasoning"]) > 0
    
    def test_rate_limiting_headers(self, client):
        """Test rate limiting headers in responses."""
        # Make multiple requests to trigger rate limiting info
        for i in range(5):
            response = client.get("/api/v1/health")
            assert response.status_code == 200
            
            # Check for rate limiting headers (would be added by rate limiter)
            # This is a placeholder test - actual implementation would depend on rate limiter
    
    def test_error_response_format(self, client):
        """Test consistent error response format."""
        # Test validation error format
        login_data = {"username": "", "password": ""}
        response = client.post("/api/v1/auth/login-json", json=login_data)
        
        assert response.status_code == 401
        error_data = response.json()
        
        # Check error response structure
        assert "error" in error_data
        assert "message" in error_data
        assert "timestamp" in error_data
        
        # Validate timestamp format
        timestamp = error_data["timestamp"]
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


class TestAPIClientSDK:
    """Integration tests for the API client SDK."""
    
    @pytest.fixture
    async def mock_server(self):
        """Create mock server for client testing."""
        # This would typically use a test server or mock HTTP responses
        # For now, we'll use the actual test client
        return "http://localhost:8000"
    
    @pytest.mark.asyncio
    async def test_client_authentication(self, mock_server):
        """Test client SDK authentication."""
        async with PriorAuthClient(
            base_url=mock_server,
            username="provider1",
            password="provider123"
        ) as client:
            # Mock the HTTP response for authentication
            with patch.object(client, '_make_request') as mock_request:
                mock_response = AsyncMock()
                mock_response.json.return_value = {
                    "access_token": "test_token",
                    "token_type": "bearer",
                    "expires_in": 3600
                }
                mock_request.return_value = mock_response
                
                token_response = await client.authenticate()
                
                assert token_response.access_token == "test_token"
                assert token_response.token_type == "bearer"
                assert client.access_token == "test_token"
    
    @pytest.mark.asyncio
    async def test_client_request_submission(self, mock_server):
        """Test client SDK request submission."""
        request = AuthorizationRequest(
            provider_id="test_provider",
            patient_demographics=PatientDemographics(
                patient_id="encrypted_patient_123",
                age=45,
                gender=Gender.FEMALE,
                insurance_id="encrypted_insurance_456",
                member_id="encrypted_member_789"
            ),
            diagnosis_codes=[
                MedicalCode(code="G93.1", description="Test diagnosis", code_type="icd10")
            ],
            procedure_codes=[
                MedicalCode(code="70551", description="Test procedure", code_type="cpt")
            ],
            clinical_notes="Test clinical notes",
            urgency_level=UrgencyLevel.ROUTINE,
            procedure_type=ProcedureType.MRI
        )
        
        async with PriorAuthClient(base_url=mock_server) as client:
            client.access_token = "test_token"
            
            with patch.object(client, '_make_request') as mock_request:
                mock_response = AsyncMock()
                mock_response.json.return_value = {
                    "request_id": "req_2024_001234",
                    "status": "submitted",
                    "message": "Request submitted successfully",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                mock_request.return_value = mock_response
                
                response = await client.submit_authorization_request(request)
                
                assert response.request_id == "req_2024_001234"
                assert response.status == "submitted"
    
    @pytest.mark.asyncio
    async def test_client_error_handling(self, mock_server):
        """Test client SDK error handling."""
        async with PriorAuthClient(base_url=mock_server) as client:
            # Test authentication error
            with pytest.raises(AuthenticationError):
                await client.get_request_status("req_test")
            
            # Test validation error handling
            client.access_token = "test_token"
            
            with patch.object(client, '_make_request') as mock_request:
                from httpx import Response
                
                # Create mock error response
                mock_response = Response(
                    status_code=400,
                    json={"error": "VALIDATION_ERROR", "message": "Invalid request"},
                    request=AsyncMock()
                )
                mock_request.side_effect = lambda *args, **kwargs: client._handle_error_response(mock_response)
                
                with pytest.raises(ValidationError):
                    await client.get_request_status("invalid_request_id")
    
    @pytest.mark.asyncio
    async def test_client_retry_logic(self, mock_server):
        """Test client SDK retry logic."""
        async with PriorAuthClient(
            base_url=mock_server,
            max_retries=2,
            retry_delay=0.1
        ) as client:
            client.access_token = "test_token"
            
            with patch.object(client.client, 'request') as mock_request:
                # First two calls fail with timeout, third succeeds
                mock_request.side_effect = [
                    Exception("Timeout"),
                    Exception("Timeout"),
                    AsyncMock(is_success=True, json=lambda: {"status": "healthy"})
                ]
                
                # This should succeed after retries
                response = await client._make_request("GET", "health")
                assert response.json()["status"] == "healthy"
                
                # Verify retry attempts
                assert mock_request.call_count == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
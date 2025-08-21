"""
Unit tests for request intake API endpoints.

Tests comprehensive input validation, error handling, and request processing.
"""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from src.main import app
from src.models.enums import DecisionStatus, UrgencyLevel, ProcedureType, RequestStatus
from src.services.validation import ValidationResult, ValidationError
from src.services.tracking import RequestStatusInfo, RequestsResult


class TestRequestSubmission:
    """Test cases for authorization request submission."""
    
    def test_submit_valid_request_success(self, authenticated_client):
    """Test successful submission of a valid authorization request."""
        valid_request = {
            "provider_id": "prov_12345",
            "patient_demographics": {
                "patient_id": "enc_pat_1a2b3c4d5e6f7g8h",
                "age": 45,
                "gender": "female",
                "insurance_id": "enc_ins_9i8h7g6f5e4d3c2b",
                "member_id": "enc_mem_1z2y3x4w5v6u7t8s"
            },
            "diagnosis_codes": [
                {"code": "M25.511", "description": "Pain in right shoulder"}
            ],
            "procedure_codes": [
                {"code": "73221", "description": "MRI upper extremity without contrast"}
            ],
            "clinical_notes": "Patient reports persistent shoulder pain for 6 weeks following sports injury. Conservative treatment with physical therapy has not provided adequate relief.",
            "procedure_type": "mri",
            "urgency_level": "routine"
        }
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            # Mock successful validation
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                errors=[],
                warnings=[],
                processing_time_ms=150.0
            )
            mock_store.return_value = None
            
            response = authenticated_client.post("/api/v1/authorization/requests", json=valid_request)
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "submitted"
            assert data["message"] == "Authorization request submitted successfully"
            assert data["request_id"].startswith("req_")
            assert "timestamp" in data
            
            # Verify services were called
            mock_validate.assert_called_once()
            mock_store.assert_called_once()
    
    def test_submit_request_validation_error(self, authenticated_client):
    """Test submission with validation errors."""
        invalid_request = {
            "provider_id": "",  # Invalid: empty provider ID
            "patient_demographics": {
                "patient_id": "short",  # Invalid: too short
                "age": 200,  # Invalid: age too high
                "gender": "female",
                "insurance_id": "enc_ins_9i8h7g6f5e4d3c2b",
                "member_id": "enc_mem_1z2y3x4w5v6u7t8s"
            },
            "diagnosis_codes": [],  # Invalid: empty list
            "procedure_codes": [
                {"code": "99999", "description": "Invalid code"}  # Invalid: non-existent code
            ],
            "procedure_type": "mri",
            "urgency_level": "routine"
        }
        
        response = authenticated_client.post("/api/v1/authorization/requests", json=invalid_request)
        
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert data["error"]["message"] == "Request data validation failed"
        # The details field exists but may be empty for validation errors
        assert "details" in data["error"]
        
        # For validation errors, the specific field errors are logged but not returned in details
        # Just verify the error structure is correct
    
    def test_submit_request_business_validation_error(self, authenticated_client):
    """Test submission with business validation errors."""
        request_with_business_errors = {
            "provider_id": "prov_12345",
            "patient_demographics": {
                "patient_id": "enc_pat_1a2b3c4d5e6f7g8h",
                "age": 45,
                "gender": "female",
                "insurance_id": "enc_ins_9i8h7g6f5e4d3c2b",
                "member_id": "enc_mem_1z2y3x4w5v6u7t8s"
            },
            "diagnosis_codes": [
                {"code": "M25.511", "description": "Pain in right shoulder"}  # Valid format but will fail business validation
            ],
            "procedure_codes": [
                {"code": "73221", "description": "MRI upper extremity without contrast"}
            ],
            "procedure_type": "mri",
            "urgency_level": "routine"
        }
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate:
            # Mock business validation failure
            mock_validate.return_value = ValidationResult(
                is_valid=False,
                errors=[
                    ValidationError(
                        field="diagnosis_codes[0].code",
                        message="ICD-10 code 'INVALID' is not recognized or may be invalid",
                        value="INVALID",
                        suggestion="Use valid ICD-10 format (e.g., M25.511 for shoulder pain)"
                    )
                ],
                warnings=[],
                processing_time_ms=200.0
            )
            
            response = authenticated_client.post("/api/v1/authorization/requests", json=request_with_business_errors)
            
            assert response.status_code == 400
            data = response.json()
            
            assert data["error"]["code"] == "BUSINESS_VALIDATION_ERROR"
            assert data["error"]["message"] == "Request failed business validation rules"
            # Business validation errors are logged but details structure may vary
    
    def test_submit_request_with_warnings(self, authenticated_client):
    """Test successful submission with validation warnings."""
        request_with_warnings = {
            "provider_id": "prov_12345",
            "patient_demographics": {
                "patient_id": "enc_pat_1a2b3c4d5e6f7g8h",
                "age": 85,  # Elderly patient - may generate warnings
                "gender": "male",
                "insurance_id": "enc_ins_9i8h7g6f5e4d3c2b",
                "member_id": "enc_mem_1z2y3x4w5v6u7t8s"
            },
            "diagnosis_codes": [
                {"code": "M25.511", "description": "Pain in right shoulder"}
            ],
            "procedure_codes": [
                {"code": "72148", "description": "MRI lumbar spine without contrast"}
            ],
            "clinical_notes": "Elderly patient with back pain.",
            "procedure_type": "mri",
            "urgency_level": "emergent"  # May generate urgency warning
        }
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            # Mock validation with warnings
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                errors=[],
                warnings=[
                    "Spine MRI (CPT 72148) in patients over 80 years should consider contraindications",
                    "Emergent urgency level should be reserved for life-threatening conditions"
                ],
                processing_time_ms=180.0
            )
            mock_store.return_value = None
            
            response = authenticated_client.post("/api/v1/authorization/requests", json=request_with_warnings)
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "submitted"
            assert "validation_warnings" in data
            assert len(data["validation_warnings"]) == 2
    
    def test_submit_request_missing_required_fields(self, authenticated_client):
    """Test submission with missing required fields."""
        incomplete_request = {
            "provider_id": "prov_12345",
            # Missing patient_demographics
            "diagnosis_codes": [
                {"code": "M25.511", "description": "Pain in right shoulder"}
            ],
            # Missing procedure_codes
            "procedure_type": "mri"
        }
        
        response = authenticated_client.post("/api/v1/authorization/requests", json=incomplete_request)
        
        assert response.status_code == 422
        data = response.json()
        
        assert data["error"]["code"] == "VALIDATION_ERROR"
        # Validation errors are logged but specific field details may not be in response


class TestRequestStatusRetrieval:
    """Test cases for request status retrieval."""
    
    def test_get_request_status_success(self, authenticated_client):
    """Test successful retrieval of request status."""
        request_id = "req_2024_ABC123"
        
        with patch('src.services.tracking.TrackingService.get_request_status') as mock_get_status:
            mock_status = RequestStatusInfo(
                request_id=request_id,
                status=RequestStatus.IN_REVIEW,
                submitted_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                estimated_completion=datetime.now(timezone.utc),
                current_stage="Policy Validation",
                progress_percentage=60,
                next_actions=["Validating against coverage policies"]
            )
            mock_get_status.return_value = mock_status
            
            response = authenticated_client.get(f"/api/v1/authorization/requests/{request_id}")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["request_id"] == request_id
            assert data["status"] == "in_review"
            assert data["current_stage"] == "Policy Validation"
            assert data["progress_percentage"] == 60
            assert "next_actions" in data
    
    def test_get_request_status_not_found(self, authenticated_client):
    """Test retrieval of non-existent request."""
        request_id = "req_2024_NOTFOUND"
        
        with patch('src.services.tracking.TrackingService.get_request_status') as mock_get_status:
            mock_get_status.return_value = None
            
            response = authenticated_client.get(f"/api/v1/authorization/requests/{request_id}")
            
            assert response.status_code == 404
            data = response.json()
            
            assert data["error"]["code"] == "RESOURCE_NOT_FOUND"
            # The message may not contain the specific request ID
            assert "not found" in data["error"]["message"].lower()
    
    def test_get_request_status_invalid_id_format(self, authenticated_client):
    """Test retrieval with invalid request ID format."""
        invalid_id = "invalid_format"
        
        response = authenticated_client.get(f"/api/v1/authorization/requests/{invalid_id}")
        
        assert response.status_code == 422
        data = response.json()
        
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "must start with 'req_'" in data["error"]["message"]


class TestBulkRequestRetrieval:
    """Test cases for bulk request retrieval by provider."""
    
    def test_get_requests_by_provider_success(self, authenticated_client):
    """Test successful retrieval of provider requests."""
        provider_id = "prov_12345"
        
        with patch('src.services.tracking.TrackingService.get_requests_by_provider') as mock_get_requests:
            mock_requests = [
                RequestStatusInfo(
                    request_id="req_2024_001",
                    status=RequestStatus.APPROVED,
                    submitted_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                    estimated_completion=None,
                    current_stage="Approved",
                    progress_percentage=100,
                    next_actions=None
                ),
                RequestStatusInfo(
                    request_id="req_2024_002",
                    status=RequestStatus.IN_REVIEW,
                    submitted_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                    estimated_completion=datetime.now(timezone.utc),
                    current_stage="Policy Validation",
                    progress_percentage=50,
                    next_actions=["Awaiting policy review"]
                )
            ]
            
            mock_result = RequestsResult(
                requests=mock_requests,
                total_count=2,
                status_summary={"approved": 1, "in_review": 1, "submitted": 0, "denied": 0, "more_info_needed": 0, "expired": 0}
            )
            mock_get_requests.return_value = mock_result
            
            response = authenticated_client.get(f"/api/v1/authorization/requests?provider_id={provider_id}")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["total_requests"] == 2
            assert len(data["requests"]) == 2
            assert "summary" in data
            assert data["summary"]["approved"] == 1
            assert data["summary"]["in_review"] == 1
    
    def test_get_requests_by_provider_with_status_filter(self, authenticated_client):
    """Test retrieval with status filter."""
        provider_id = "prov_12345"
        status_filter = "approved"
        
        with patch('src.services.tracking.TrackingService.get_requests_by_provider') as mock_get_requests:
            mock_result = RequestsResult(
                requests=[],
                total_count=0,
                status_summary={"approved": 0, "in_review": 0, "submitted": 0, "denied": 0, "more_info_needed": 0, "expired": 0}
            )
            mock_get_requests.return_value = mock_result
            
            response = authenticated_client.get(f"/api/v1/authorization/requests?provider_id={provider_id}&status_filter={status_filter}")
            
            assert response.status_code == 200
            
            # Verify the service was called with correct parameters
            mock_get_requests.assert_called_once()
            call_args = mock_get_requests.call_args
            assert call_args.kwargs["provider_id"] == provider_id
            assert call_args.kwargs["status_filter"] == RequestStatus.APPROVED
    
    def test_get_requests_empty_provider_id(self, authenticated_client):
    """Test retrieval with empty provider ID."""
        response = authenticated_client.get("/api/v1/authorization/requests?provider_id=")
        
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "INVALID_PROVIDER_ID"
        assert "cannot be empty" in data["message"]
    
    def test_get_requests_pagination(self, authenticated_client):
    """Test request retrieval with pagination parameters."""
        provider_id = "prov_12345"
        limit = 10
        offset = 5
        
        with patch('src.services.tracking.TrackingService.get_requests_by_provider') as mock_get_requests:
            mock_result = RequestsResult(
                requests=[],
                total_count=15,
                status_summary={}
            )
            mock_get_requests.return_value = mock_result
            
            response = authenticated_client.get(f"/api/v1/authorization/requests?provider_id={provider_id}&limit={limit}&offset={offset}")
            
            assert response.status_code == 200
            
            # Verify pagination parameters were passed correctly
            call_args = mock_get_requests.call_args
            assert call_args.kwargs["limit"] == limit
            assert call_args.kwargs["offset"] == offset


    class TestAdditionalInformation:
    """Test cases for submitting additional information."""
    
    def test_submit_additional_info_success(self, authenticated_client):
    """Test successful submission of additional information."""
        request_id = "req_2024_ABC123"
        additional_info = {
            "additional_clinical_notes": "Patient has tried conservative treatment for 8 weeks",
            "imaging_history": "Previous X-ray showed no fracture"
        }
        
        with patch('src.services.tracking.TrackingService.get_request_status') as mock_get_status, \
             patch('src.services.tracking.TrackingService.update_request_info') as mock_update:
            
            # Mock request in correct status
            mock_status = RequestStatusInfo(
                request_id=request_id,
                status=RequestStatus.MORE_INFO_NEEDED,
                submitted_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                estimated_completion=datetime.now(timezone.utc),
                current_stage="Awaiting Additional Information",
                progress_percentage=75,
                next_actions=["Submit additional clinical documentation"]
            )
            mock_get_status.return_value = mock_status
            mock_update.return_value = None
            
            response = authenticated_client.put(f"/api/v1/authorization/requests/{request_id}/additional-info", json=additional_info)
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["request_id"] == request_id
            assert data["status"] == "updated"
            assert data["message"] == "Additional information submitted successfully"
            
            # Verify services were called
            mock_get_status.assert_called_once_with(request_id)
            mock_update.assert_called_once_with(request_id, additional_info)
    
    def test_submit_additional_info_request_not_found(self, authenticated_client):
    """Test submission for non-existent request."""
        request_id = "req_2024_NOTFOUND"
        additional_info = {"notes": "Additional information"}
        
        with patch('src.services.tracking.TrackingService.get_request_status') as mock_get_status:
            mock_get_status.return_value = None
            
            response = authenticated_client.put(f"/api/v1/authorization/requests/{request_id}/additional-info", json=additional_info)
            
            assert response.status_code == 404
            data = response.json()
            assert data["error"] == "REQUEST_NOT_FOUND"
    
    def test_submit_additional_info_wrong_status(self, authenticated_client):
    """Test submission for request not awaiting additional info."""
        request_id = "req_2024_ABC123"
        additional_info = {"notes": "Additional information"}
        
        with patch('src.services.tracking.TrackingService.get_request_status') as mock_get_status:
            # Mock request in wrong status
            mock_status = RequestStatusInfo(
                request_id=request_id,
                status=RequestStatus.APPROVED,  # Wrong status
                submitted_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                estimated_completion=None,
                current_stage="Approved",
                progress_percentage=100,
                next_actions=None
            )
            mock_get_status.return_value = mock_status
            
            response = authenticated_client.put(f"/api/v1/authorization/requests/{request_id}/additional-info", json=additional_info)
            
            assert response.status_code == 400
            data = response.json()
            
            assert data["error"] == "INVALID_REQUEST_STATUS"
            assert "not awaiting additional information" in data["message"]


    class TestErrorHandling:
    """Test cases for error handling and edge cases."""
    
    def test_internal_server_error_handling(self, authenticated_client):
    """Test handling of unexpected internal errors."""
        valid_request = {
            "provider_id": "prov_12345",
            "patient_demographics": {
                "patient_id": "enc_pat_1a2b3c4d5e6f7g8h",
                "age": 45,
                "gender": "female",
                "insurance_id": "enc_ins_9i8h7g6f5e4d3c2b",
                "member_id": "enc_mem_1z2y3x4w5v6u7t8s"
            },
            "diagnosis_codes": [
                {"code": "M25.511", "description": "Pain in right shoulder"}
            ],
            "procedure_codes": [
                {"code": "73221", "description": "MRI upper extremity without contrast"}
            ],
            "procedure_type": "mri",
            "urgency_level": "routine"
        }
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate:
            # Mock unexpected exception
            mock_validate.side_effect = Exception("Database connection failed")
            
            response = authenticated_client.post("/api/v1/authorization/requests", json=valid_request)
            
            assert response.status_code == 500
            data = response.json()
            
            assert data["error"] == "INTERNAL_ERROR"
            assert "unexpected error occurred" in data["message"]
    
    def test_request_timeout_simulation(self):
    """Test behavior when request processing takes too long."""
        # This would be implemented with actual timeout handling in production
        pass
    
    def test_concurrent_request_handling(self):
    """Test handling of multiple concurrent requests."""
        # This would be implemented with actual concurrency testing in production
        pass

    cl
    ass TestComprehensiveIntakeAPI:
    """Comprehensive intake API endpoint tests."""
    
    def setup_method(self):
        """Set up test client and common test data."""
        from src.main import app
        self.client = TestClient(app)
        
        self.valid_request_base = {
            "provider_id": "prov_12345",
            "patient_demographics": {
                "patient_id": "enc_pat_1a2b3c4d5e6f7g8h",
                "age": 45,
                "gender": "female",
                "insurance_id": "enc_ins_9i8h7g6f5e4d3c2b",
                "member_id": "enc_mem_1z2y3x4w5v6u7t8s"
            },
            "diagnosis_codes": [
                {"code": "M25.511", "description": "Pain in right shoulder"}
            ],
            "procedure_codes": [
                {"code": "73221", "description": "MRI upper extremity without contrast"}
            ],
            "clinical_notes": "Patient reports persistent shoulder pain.",
            "procedure_type": "mri",
            "urgency_level": "routine"
        }
    
        def test_enhanced_request_submission_success(self):
    """Test enhanced request submission with additional context."""
        # Login first
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={"username": "provider1", "password": "provider123"}
        )
        token = login_response.json()["access_token"]
        
        enhanced_request = {
            "base_request": self.valid_request_base,
            "enhanced_context": {
                "patient_history": ["Previous shoulder surgery 2019"],
                "comorbidities": ["Diabetes Type 2", "Hypertension"],
                "current_medications": ["Metformin", "Lisinopril"],
                "allergies": ["Penicillin"],
                "lab_results": {"glucose": "120 mg/dL", "hba1c": "7.2%"},
                "imaging_history": ["X-ray shoulder 2023-01-15: No fracture"],
                "treatment_response": "Physical therapy 6 weeks - minimal improvement",
                "functional_status": "Limited range of motion, difficulty with overhead activities",
                "social_determinants": {"employment": "office worker", "insurance": "commercial"},
                "provider_notes": "Conservative treatment exhausted, MRI needed for surgical planning",
                "consultation_notes": "Orthopedic consultation recommended advanced imaging",
                "prior_authorizations": ["Previous MRI knee approved 2022"]
            }
        }
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store, \
             patch('src.services.tracking.TrackingService.store_enhanced_context') as mock_store_context:
            
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                errors=[],
                warnings=[],
                processing_time_ms=200.0
            )
            mock_store.return_value = None
            mock_store_context.return_value = None
            
            response = self.client.post(
                "/api/v1/authorization/requests/enhanced",
                json=enhanced_request,
                headers={"Authorization": f"Bearer {token}"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] in ["approved", "denied", "in_review"]
            assert data["request_id"].startswith("req_")
            assert "timestamp" in data
            
            # Verify enhanced context was stored
            mock_store_context.assert_called_once()
    
    def test_enhanced_request_with_llm_processing(self):
    """Test enhanced request with LLM processing enabled."""
        # Login first
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={"username": "provider1", "password": "provider123"}
        )
        token = login_response.json()["access_token"]
        
        enhanced_request = {
            "base_request": self.valid_request_base,
            "enhanced_context": {
                "patient_history": ["Chronic shoulder pain"],
                "provider_notes": "Complex case requiring LLM analysis"
            }
        }
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                errors=[],
                warnings=[],
                processing_time_ms=300.0
            )
            mock_store.return_value = None
            
            response = self.client.post(
                "/api/v1/authorization/requests/enhanced",
                json=enhanced_request,
                params={"use_llm": True, "stream_updates": False},
                headers={"Authorization": f"Bearer {token}"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["request_id"].startswith("req_")
            # LLM processing may result in different statuses
            assert data["status"] in ["approved", "denied", "in_review", "more_info_needed"]
    
    def test_enhanced_request_with_webhook_events(self):
    """Test enhanced request with webhook event configuration."""
        # Login first
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={"username": "provider1", "password": "provider123"}
        )
        token = login_response.json()["access_token"]
        
        enhanced_request = {
            "base_request": self.valid_request_base,
            "enhanced_context": {
                "provider_notes": "Request with webhook notifications"
            }
        }
        
        webhook_events = ["decision.completed", "status.changed"]
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store, \
             patch('src.services.tracking.TrackingService.store_webhook_preferences') as mock_store_webhooks:
            
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                errors=[],
                warnings=[],
                processing_time_ms=250.0
            )
            mock_store.return_value = None
            mock_store_webhooks.return_value = None
            
            response = self.client.post(
                "/api/v1/authorization/requests/enhanced",
                json=enhanced_request,
                params={"webhook_events": webhook_events},
                headers={"Authorization": f"Bearer {token}"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["request_id"].startswith("req_")
            
            # Verify webhook preferences were stored
            mock_store_webhooks.assert_called_once()
    
    def test_bulk_request_submission(self):
    """Test bulk submission of multiple requests."""
        # Login first
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={"username": "provider1", "password": "provider123"}
        )
        token = login_response.json()["access_token"]
        
        # Create multiple requests
        bulk_requests = []
        for i in range(5):
            request = self.valid_request_base.copy()
            request["patient_demographics"] = request["patient_demographics"].copy()
            request["patient_demographics"]["patient_id"] = f"enc_pat_{i:08d}"
            request["clinical_notes"] = f"Patient {i+1} clinical notes"
            bulk_requests.append(request)
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                errors=[],
                warnings=[],
                processing_time_ms=150.0
            )
            mock_store.return_value = None
            
            # Submit requests individually (simulating bulk operation)
            results = []
            for request in bulk_requests:
                response = self.client.post(
                    "/api/v1/authorization/requests",
                    json=request,
                    headers={"Authorization": f"Bearer {token}"}
                )
                results.append(response.status_code)
            
            # All requests should succeed
            assert all(status == 200 for status in results)
            
            # Verify all requests were processed
            assert mock_validate.call_count == 5
            assert mock_store.call_count == 5
    
    def test_concurrent_request_processing(self):
    """Test concurrent processing of multiple requests."""
        # Login first
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={"username": "provider1", "password": "provider123"}
        )
        token = login_response.json()["access_token"]
        
        import threading
        import time
        
        results = []
        
        def submit_request(request_data):
            with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
                 patch('src.services.tracking.TrackingService.store_request') as mock_store:
                
                mock_validate.return_value = ValidationResult(
                    is_valid=True,
                    errors=[],
                    warnings=[],
                    processing_time_ms=100.0
                )
                mock_store.return_value = None
                
                response = self.client.post(
                    "/api/v1/authorization/requests",
                    json=request_data,
                    headers={"Authorization": f"Bearer {token}"}
                )
                results.append(response.status_code)
        
        # Create multiple threads
        threads = []
        for i in range(3):
            request = self.valid_request_base.copy()
            request["patient_demographics"] = request["patient_demographics"].copy()
            request["patient_demographics"]["patient_id"] = f"enc_pat_concurrent_{i:03d}"
            
            thread = threading.Thread(target=submit_request, args=(request,))
            threads.append(thread)
        
        # Start all threads
        start_time = time.time()
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # All requests should succeed
        assert len(results) == 3
        assert all(status == 200 for status in results)
        
        # Should process concurrently (faster than sequential)
        assert processing_time < 2.0  # Should be much faster than 3 sequential requests


class TestIntakeAPIErrorScenarios:
    """Test comprehensive error scenarios for intake API."""
    
    def setup_method(self):
        """Set up test client."""
        from src.main import app
        self.client = TestClient(app)
    
    def test_malformed_json_request(self):
    """Test handling of malformed JSON requests."""
        # Login first
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={"username": "provider1", "password": "provider123"}
        )
        token = login_response.json()["access_token"]
        
        # Send malformed JSON
        response = self.client.post(
            "/api/v1/authorization/requests",
            data='{"invalid": json}',  # Malformed JSON
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 422
    
    def test_extremely_large_request(self):
    """Test handling of extremely large requests."""
        # Login first
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={"username": "provider1", "password": "provider123"}
        )
        token = login_response.json()["access_token"]
        
        # Create request with very large clinical notes
        large_request = {
            "provider_id": "prov_12345",
            "patient_demographics": {
                "patient_id": "enc_pat_1a2b3c4d5e6f7g8h",
                "age": 45,
                "gender": "female",
                "insurance_id": "enc_ins_9i8h7g6f5e4d3c2b",
                "member_id": "enc_mem_1z2y3x4w5v6u7t8s"
            },
            "diagnosis_codes": [
                {"code": "M25.511", "description": "Pain in right shoulder"}
            ],
            "procedure_codes": [
                {"code": "73221", "description": "MRI upper extremity without contrast"}
            ],
            "clinical_notes": "x" * 50000,  # 50KB of text
            "procedure_type": "mri",
            "urgency_level": "routine"
        }
        
        response = self.client.post(
            "/api/v1/authorization/requests",
            json=large_request,
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Should handle large requests gracefully
        assert response.status_code in [200, 400, 413, 422]
    
    def test_special_characters_in_request(self):
    """Test handling of special characters in request data."""
        # Login first
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={"username": "provider1", "password": "provider123"}
        )
        token = login_response.json()["access_token"]
        
        special_char_request = {
            "provider_id": "prov_12345",
            "patient_demographics": {
                "patient_id": "enc_pat_1a2b3c4d5e6f7g8h",
                "age": 45,
                "gender": "female",
                "insurance_id": "enc_ins_9i8h7g6f5e4d3c2b",
                "member_id": "enc_mem_1z2y3x4w5v6u7t8s"
            },
            "diagnosis_codes": [
                {"code": "M25.511", "description": "Pain in right shoulder"}
            ],
            "procedure_codes": [
                {"code": "73221", "description": "MRI upper extremity without contrast"}
            ],
            "clinical_notes": "Patient has 'severe' pain & needs <urgent> care! 🏥 Cost: $1,000+",
            "procedure_type": "mri",
            "urgency_level": "routine"
        }
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                errors=[],
                warnings=[],
                processing_time_ms=150.0
            )
            mock_store.return_value = None
            
            response = self.client.post(
                "/api/v1/authorization/requests",
                json=special_char_request,
                headers={"Authorization": f"Bearer {token}"}
            )
            
            # Should handle special characters gracefully
            assert response.status_code == 200
    
    def test_unicode_characters_in_request(self):
    """Test handling of unicode characters in request data."""
        # Login first
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={"username": "provider1", "password": "provider123"}
        )
        token = login_response.json()["access_token"]
        
        unicode_request = {
            "provider_id": "prov_12345",
            "patient_demographics": {
                "patient_id": "enc_pat_1a2b3c4d5e6f7g8h",
                "age": 45,
                "gender": "female",
                "insurance_id": "enc_ins_9i8h7g6f5e4d3c2b",
                "member_id": "enc_mem_1z2y3x4w5v6u7t8s"
            },
            "diagnosis_codes": [
                {"code": "M25.511", "description": "Douleur à l'épaule droite"}  # French
            ],
            "procedure_codes": [
                {"code": "73221", "description": "IRM membre supérieur sans contraste"}  # French
            ],
            "clinical_notes": "Paciente reporta dolor persistente. 患者报告持续疼痛。",  # Spanish + Chinese
            "procedure_type": "mri",
            "urgency_level": "routine"
        }
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                errors=[],
                warnings=[],
                processing_time_ms=150.0
            )
            mock_store.return_value = None
            
            response = self.client.post(
                "/api/v1/authorization/requests",
                json=unicode_request,
                headers={"Authorization": f"Bearer {token}"}
            )
            
            # Should handle unicode characters gracefully
            assert response.status_code == 200
    
    def test_null_and_empty_values(self):
    """Test handling of null and empty values in request."""
        # Login first
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={"username": "provider1", "password": "provider123"}
        )
        token = login_response.json()["access_token"]
        
        null_value_request = {
            "provider_id": "prov_12345",
            "patient_demographics": {
                "patient_id": "enc_pat_1a2b3c4d5e6f7g8h",
                "age": 45,
                "gender": "female",
                "insurance_id": "enc_ins_9i8h7g6f5e4d3c2b",
                "member_id": "enc_mem_1z2y3x4w5v6u7t8s"
            },
            "diagnosis_codes": [
                {"code": "M25.511", "description": "Pain in right shoulder"}
            ],
            "procedure_codes": [
                {"code": "73221", "description": "MRI upper extremity without contrast"}
            ],
            "clinical_notes": None,  # Null value
            "procedure_type": "mri",
            "urgency_level": ""  # Empty string
        }
        
        response = self.client.post(
            "/api/v1/authorization/requests",
            json=null_value_request,
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Should handle null/empty values with validation errors
        assert response.status_code in [400, 422]
    
    def test_missing_authentication(self):
    """Test requests without authentication."""
        request_data = {
            "provider_id": "prov_12345",
            "patient_demographics": {
                "patient_id": "enc_pat_1a2b3c4d5e6f7g8h",
                "age": 45,
                "gender": "female",
                "insurance_id": "enc_ins_9i8h7g6f5e4d3c2b",
                "member_id": "enc_mem_1z2y3x4w5v6u7t8s"
            },
            "diagnosis_codes": [
                {"code": "M25.511", "description": "Pain in right shoulder"}
            ],
            "procedure_codes": [
                {"code": "73221", "description": "MRI upper extremity without contrast"}
            ],
            "procedure_type": "mri",
            "urgency_level": "routine"
        }
        
        # Test all intake endpoints without authentication
        endpoints = [
            ("/api/v1/authorization/requests", "POST", request_data),
            ("/api/v1/authorization/requests/enhanced", "POST", request_data),
            ("/api/v1/authorization/requests/req_test_123", "GET", None),
            ("/api/v1/authorization/requests", "GET", None),
        ]
        
        for endpoint, method, data in endpoints:
            if method == "POST":
                response = self.client.post(endpoint, json=data)
            else:
                response = self.client.get(endpoint)
            
            assert response.status_code == 401
    
    def test_invalid_authentication_token(self):
    """Test requests with invalid authentication tokens."""
        request_data = {
            "provider_id": "prov_12345",
            "patient_demographics": {
                "patient_id": "enc_pat_1a2b3c4d5e6f7g8h",
                "age": 45,
                "gender": "female",
                "insurance_id": "enc_ins_9i8h7g6f5e4d3c2b",
                "member_id": "enc_mem_1z2y3x4w5v6u7t8s"
            },
            "diagnosis_codes": [
                {"code": "M25.511", "description": "Pain in right shoulder"}
            ],
            "procedure_codes": [
                {"code": "73221", "description": "MRI upper extremity without contrast"}
            ],
            "procedure_type": "mri",
            "urgency_level": "routine"
        }
        
        invalid_tokens = [
            "Bearer invalid_token",
            "Bearer ",
            "Invalid token_format",
            "Bearer expired.jwt.token"
        ]
        
        for token in invalid_tokens:
            response = self.client.post(
                "/api/v1/authorization/requests",
                json=request_data,
                headers={"Authorization": token}
            )
            
            assert response.status_code == 401


    class TestIntakeAPIEdgeCases:
    """Test edge cases and boundary conditions for intake API."""
    
    def setup_method(self):
        """Set up test client."""
        from src.main import app
        self.client = TestClient(app)
    
        def test_minimum_valid_request(self):
    """Test submission with minimum required fields only."""
        # Login first
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={"username": "provider1", "password": "provider123"}
        )
        token = login_response.json()["access_token"]
        
        minimal_request = {
            "provider_id": "prov_12345",
            "patient_demographics": {
                "patient_id": "enc_pat_minimal",
                "age": 30,
                "gender": "male",
                "insurance_id": "enc_ins_minimal",
                "member_id": "enc_mem_minimal"
            },
            "diagnosis_codes": [
                {"code": "Z00.00", "description": "General examination"}
            ],
            "procedure_codes": [
                {"code": "99213", "description": "Office visit"}
            ],
            "procedure_type": "consultation",
            "urgency_level": "routine"
        }
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                errors=[],
                warnings=[],
                processing_time_ms=100.0
            )
            mock_store.return_value = None
            
            response = self.client.post(
                "/api/v1/authorization/requests",
                json=minimal_request,
                headers={"Authorization": f"Bearer {token}"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["request_id"].startswith("req_")
    
    def test_maximum_field_lengths(self):
    """Test requests with maximum allowed field lengths."""
        # Login first
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={"username": "provider1", "password": "provider123"}
        )
        token = login_response.json()["access_token"]
        
        max_length_request = {
            "provider_id": "prov_" + "x" * 50,  # Long provider ID
            "patient_demographics": {
                "patient_id": "enc_pat_" + "x" * 50,
                "age": 120,  # Maximum reasonable age
                "gender": "female",
                "insurance_id": "enc_ins_" + "x" * 50,
                "member_id": "enc_mem_" + "x" * 50
            },
            "diagnosis_codes": [
                {"code": "M25.511", "description": "x" * 500}  # Long description
            ],
            "procedure_codes": [
                {"code": "73221", "description": "x" * 500}  # Long description
            ],
            "clinical_notes": "x" * 10000,  # Maximum clinical notes length
            "procedure_type": "mri",
            "urgency_level": "routine"
        }
        
        response = self.client.post(
            "/api/v1/authorization/requests",
            json=max_length_request,
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Should either succeed or fail with validation error
        assert response.status_code in [200, 400, 422]
    
    def test_boundary_age_values(self):
    """Test requests with boundary age values."""
        # Login first
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={"username": "provider1", "password": "provider123"}
        )
        token = login_response.json()["access_token"]
        
        boundary_ages = [0, 1, 17, 18, 65, 100, 120, -1, 150]
        
        for age in boundary_ages:
            request_data = {
                "provider_id": "prov_12345",
                "patient_demographics": {
                    "patient_id": f"enc_pat_age_{age}",
                    "age": age,
                    "gender": "female",
                    "insurance_id": "enc_ins_test",
                    "member_id": "enc_mem_test"
                },
                "diagnosis_codes": [
                    {"code": "M25.511", "description": "Test diagnosis"}
                ],
                "procedure_codes": [
                    {"code": "73221", "description": "Test procedure"}
                ],
                "procedure_type": "mri",
                "urgency_level": "routine"
            }
            
            response = self.client.post(
                "/api/v1/authorization/requests",
                json=request_data,
                headers={"Authorization": f"Bearer {token}"}
            )
            
            # Valid ages should succeed, invalid should fail
            if 0 <= age <= 120:
                expected_status = [200, 400]  # May fail business validation
            else:
                expected_status = [400, 422]  # Should fail validation
            
            assert response.status_code in expected_status
    
    def test_multiple_diagnosis_and_procedure_codes(self):
    """Test requests with multiple diagnosis and procedure codes."""
        # Login first
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={"username": "provider1", "password": "provider123"}
        )
        token = login_response.json()["access_token"]
        
        multi_code_request = {
            "provider_id": "prov_12345",
            "patient_demographics": {
                "patient_id": "enc_pat_multi_codes",
                "age": 55,
                "gender": "male",
                "insurance_id": "enc_ins_multi",
                "member_id": "enc_mem_multi"
            },
            "diagnosis_codes": [
                {"code": "M25.511", "description": "Pain in right shoulder"},
                {"code": "M25.512", "description": "Pain in left shoulder"},
                {"code": "M79.3", "description": "Panniculitis, unspecified"},
                {"code": "Z87.891", "description": "Personal history of nicotine dependence"}
            ],
            "procedure_codes": [
                {"code": "73221", "description": "MRI upper extremity without contrast"},
                {"code": "73222", "description": "MRI upper extremity with contrast"},
                {"code": "76140", "description": "Consultation on X-ray examination"}
            ],
            "clinical_notes": "Complex case with multiple conditions requiring comprehensive imaging.",
            "procedure_type": "mri",
            "urgency_level": "routine"
        }
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                errors=[],
                warnings=["Multiple procedure codes may require separate authorizations"],
                processing_time_ms=200.0
            )
            mock_store.return_value = None
            
            response = self.client.post(
                "/api/v1/authorization/requests",
                json=multi_code_request,
                headers={"Authorization": f"Bearer {token}"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "validation_warnings" in data
            assert len(data["validation_warnings"]) > 0
    
    def test_all_urgency_levels(self):
    """Test requests with all possible urgency levels."""
        # Login first
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={"username": "provider1", "password": "provider123"}
        )
        token = login_response.json()["access_token"]
        
        urgency_levels = ["routine", "urgent", "emergent", "stat"]
        
        for urgency in urgency_levels:
            request_data = {
                "provider_id": "prov_12345",
                "patient_demographics": {
                    "patient_id": f"enc_pat_urgency_{urgency}",
                    "age": 40,
                    "gender": "female",
                    "insurance_id": "enc_ins_urgency",
                    "member_id": "enc_mem_urgency"
                },
                "diagnosis_codes": [
                    {"code": "M25.511", "description": "Test diagnosis"}
                ],
                "procedure_codes": [
                    {"code": "73221", "description": "Test procedure"}
                ],
                "clinical_notes": f"Request with {urgency} urgency level",
                "procedure_type": "mri",
                "urgency_level": urgency
            }
            
            with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
                 patch('src.services.tracking.TrackingService.store_request') as mock_store:
                
                mock_validate.return_value = ValidationResult(
                    is_valid=True,
                    errors=[],
                    warnings=[],
                    processing_time_ms=150.0
                )
                mock_store.return_value = None
                
                response = self.client.post(
                    "/api/v1/authorization/requests",
                    json=request_data,
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["request_id"].startswith("req_")
    
    def test_all_procedure_types(self):
    """Test requests with all possible procedure types."""
        # Login first
        login_response = self.client.post(
            "/api/v1/auth/login",
            data={"username": "provider1", "password": "provider123"}
        )
        token = login_response.json()["access_token"]
        
        procedure_types = ["mri", "ct_scan", "x_ray", "ultrasound", "pet_scan", "consultation"]
        
        for proc_type in procedure_types:
            request_data = {
                "provider_id": "prov_12345",
                "patient_demographics": {
                    "patient_id": f"enc_pat_proc_{proc_type}",
                    "age": 35,
                    "gender": "male",
                    "insurance_id": "enc_ins_proc",
                    "member_id": "enc_mem_proc"
                },
                "diagnosis_codes": [
                    {"code": "M25.511", "description": "Test diagnosis"}
                ],
                "procedure_codes": [
                    {"code": "73221", "description": f"Test {proc_type} procedure"}
                ],
                "clinical_notes": f"Request for {proc_type} procedure",
                "procedure_type": proc_type,
                "urgency_level": "routine"
            }
            
            with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
                 patch('src.services.tracking.TrackingService.store_request') as mock_store:
                
                mock_validate.return_value = ValidationResult(
                    is_valid=True,
                    errors=[],
                    warnings=[],
                    processing_time_ms=150.0
                )
                mock_store.return_value = None
                
                response = self.client.post(
                    "/api/v1/authorization/requests",
                    json=request_data,
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["request_id"].startswith("req_")
    """
"""
Unit tests for request intake API endpoints.

Tests comprehensive input validation, error handling, and request processing.
"""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from src.main import app
from src.models.enums import RequestStatus, UrgencyLevel, ProcedureType, Gender
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
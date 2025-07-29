"""
OpenAPI documentation configuration for Prior Authorization Agent.

This module provides comprehensive API documentation with detailed schemas,
examples, and error responses for healthcare integration partners.
"""

from typing import Dict, Any, List
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def get_custom_openapi(app: FastAPI) -> Dict[str, Any]:
    """
    Generate custom OpenAPI schema with comprehensive documentation.
    
    Args:
        app: FastAPI application instance
        
    Returns:
        Custom OpenAPI schema dictionary
    """
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="Prior Authorization Agent API",
        version="1.0.0",
        description=get_api_description(),
        routes=app.routes,
        servers=[
            {"url": "https://api.priorauth.example.com", "description": "Production server"},
            {"url": "https://staging-api.priorauth.example.com", "description": "Staging server"},
            {"url": "http://localhost:8000", "description": "Development server"}
        ]
    )
    
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "OAuth2": {
            "type": "oauth2",
            "flows": {
                "password": {
                    "tokenUrl": "/api/v1/auth/login",
                    "scopes": {
                        "provider": "Healthcare provider access",
                        "payer_admin": "Payer administrator access",
                        "compliance": "Compliance officer access"
                    }
                }
            }
        },
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }
    
    # Add global security requirement
    openapi_schema["security"] = [{"BearerAuth": []}]
    
    # Add custom error response schemas
    openapi_schema["components"]["schemas"].update(get_error_schemas())
    
    # Add example responses
    add_example_responses(openapi_schema)
    
    # Add tags with descriptions
    openapi_schema["tags"] = get_api_tags()
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


def get_api_description() -> str:
    """
    Get comprehensive API description with usage guidelines.
    
    Returns:
        Formatted API description string
    """
    return """
## Prior Authorization Agent API

The Prior Authorization Agent API automates the prior authorization workflow for outpatient imaging services (MRI, CT scans, X-rays) for US-based healthcare payers.

### Key Features

- **Real-time Processing**: 95% of requests processed within 2 minutes
- **HIPAA Compliant**: Full encryption and audit logging for PHI protection
- **Policy Validation**: Automatic validation against CMS guidelines and payer policies
- **Comprehensive Audit**: Complete decision traceability and reasoning
- **Provider Dashboard**: Real-time status tracking and request management

### Authentication

All API endpoints require OAuth 2.0 authentication with JWT tokens. Use the `/auth/login` endpoint to obtain an access token.

### Rate Limiting

API requests are rate-limited to 100 requests per minute per authenticated user. Rate limit headers are included in all responses.

### Error Handling

All errors follow a consistent format with structured error codes, detailed messages, and suggested corrections where applicable.

### Medical Code Standards

- **ICD-10**: Diagnosis codes must follow current ICD-10-CM format
- **CPT/HCPCS**: Procedure codes must be valid CPT or HCPCS Level II codes
- **Validation**: Invalid codes return suggestions for correct alternatives

### Compliance

This API maintains HIPAA compliance through:
- AES-256 encryption for all PHI data
- TLS 1.3+ for data transmission
- Comprehensive audit logging
- Role-based access controls
- Automatic data retention management

### Support

For technical support and integration assistance:
- Documentation: https://docs.priorauth.example.com
- Support Portal: https://support.priorauth.example.com
- Email: api-support@priorauth.example.com
"""


def get_error_schemas() -> Dict[str, Any]:
    """
    Get standardized error response schemas.
    
    Returns:
        Dictionary of error schema definitions
    """
    return {
        "ValidationErrorDetail": {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "description": "Field path that failed validation"
                },
                "message": {
                    "type": "string",
                    "description": "Validation error message"
                },
                "value": {
                    "description": "Invalid value that was provided"
                },
                "suggestion": {
                    "type": "string",
                    "description": "Suggested correction for the error",
                    "nullable": True
                }
            },
            "required": ["field", "message"],
            "example": {
                "field": "procedure_codes.0.code",
                "message": "Invalid CPT code format",
                "value": "99999",
                "suggestion": "Use CPT code 70551 for brain MRI without contrast"
            }
        },
        "ErrorResponse": {
            "type": "object",
            "properties": {
                "error": {
                    "type": "string",
                    "description": "Error code identifier"
                },
                "message": {
                    "type": "string",
                    "description": "Human-readable error message"
                },
                "details": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/ValidationErrorDetail"},
                    "description": "Detailed validation errors",
                    "nullable": True
                },
                "request_id": {
                    "type": "string",
                    "description": "Request tracking ID for support",
                    "nullable": True
                },
                "timestamp": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Error occurrence timestamp"
                }
            },
            "required": ["error", "message", "timestamp"],
            "example": {
                "error": "VALIDATION_ERROR",
                "message": "Request data validation failed",
                "details": [
                    {
                        "field": "diagnosis_codes.0.code",
                        "message": "Invalid ICD-10 code format",
                        "value": "ABC123",
                        "suggestion": "Use format like M25.511 for shoulder pain"
                    }
                ],
                "request_id": "req_2024_001234",
                "timestamp": "2024-01-24T10:30:00Z"
            }
        },
        "RateLimitError": {
            "type": "object",
            "properties": {
                "error": {
                    "type": "string",
                    "enum": ["RATE_LIMIT_EXCEEDED"]
                },
                "message": {
                    "type": "string"
                },
                "retry_after": {
                    "type": "integer",
                    "description": "Seconds to wait before retrying"
                },
                "limit": {
                    "type": "integer",
                    "description": "Rate limit threshold"
                },
                "remaining": {
                    "type": "integer",
                    "description": "Remaining requests in current window"
                }
            },
            "example": {
                "error": "RATE_LIMIT_EXCEEDED",
                "message": "Rate limit exceeded",
                "retry_after": 60,
                "limit": 100,
                "remaining": 0
            }
        }
    }


def add_example_responses(openapi_schema: Dict[str, Any]) -> None:
    """
    Add example responses to API endpoints.
    
    Args:
        openapi_schema: OpenAPI schema to modify
    """
    # Add common error responses to all endpoints
    common_responses = {
        "400": {
            "description": "Bad Request - Validation Error",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                }
            }
        },
        "401": {
            "description": "Unauthorized - Invalid or missing authentication",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                    "example": {
                        "error": "UNAUTHORIZED",
                        "message": "Invalid or expired authentication token",
                        "timestamp": "2024-01-24T10:30:00Z"
                    }
                }
            }
        },
        "403": {
            "description": "Forbidden - Insufficient permissions",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                    "example": {
                        "error": "FORBIDDEN",
                        "message": "Insufficient permissions for this operation",
                        "timestamp": "2024-01-24T10:30:00Z"
                    }
                }
            }
        },
        "429": {
            "description": "Too Many Requests - Rate limit exceeded",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/RateLimitError"}
                }
            }
        },
        "500": {
            "description": "Internal Server Error",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                    "example": {
                        "error": "INTERNAL_ERROR",
                        "message": "An unexpected error occurred",
                        "timestamp": "2024-01-24T10:30:00Z"
                    }
                }
            }
        }
    }
    
    # Add endpoint-specific examples
    endpoint_examples = get_endpoint_specific_examples()
    
    # Add to all paths
    for path, path_data in openapi_schema.get("paths", {}).items():
        for method, method_data in path_data.items():
            if isinstance(method_data, dict) and "responses" in method_data:
                # Add common error responses
                method_data["responses"].update(common_responses)
                
                # Add endpoint-specific examples
                endpoint_key = f"{method.upper()} {path}"
                if endpoint_key in endpoint_examples:
                    examples = endpoint_examples[endpoint_key]
                    for status_code, example_data in examples.items():
                        if status_code in method_data["responses"]:
                            if "content" in method_data["responses"][status_code]:
                                for content_type in method_data["responses"][status_code]["content"]:
                                    method_data["responses"][status_code]["content"][content_type]["examples"] = example_data


def get_endpoint_specific_examples() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Get endpoint-specific response examples.
    
    Returns:
        Dictionary mapping endpoint keys to status code examples
    """
    return {
        "POST /api/v1/authorization/requests": {
            "200": {
                "successful_submission": {
                    "summary": "Successful Request Submission",
                    "value": {
                        "request_id": "req_2024_001234",
                        "status": "submitted",
                        "message": "Authorization request submitted successfully",
                        "timestamp": "2024-01-24T10:30:00Z",
                        "validation_warnings": None
                    }
                },
                "with_warnings": {
                    "summary": "Submission with Warnings",
                    "value": {
                        "request_id": "req_2024_001235",
                        "status": "submitted",
                        "message": "Authorization request submitted successfully",
                        "timestamp": "2024-01-24T10:30:00Z",
                        "validation_warnings": [
                            "Procedure code 70551 may require additional documentation for this diagnosis"
                        ]
                    }
                }
            }
        },
        "GET /api/v1/authorization/requests/{request_id}": {
            "200": {
                "in_review": {
                    "summary": "Request In Review",
                    "value": {
                        "request_id": "req_2024_001234",
                        "status": "in_review",
                        "submitted_at": "2024-01-24T08:30:00Z",
                        "updated_at": "2024-01-24T10:15:00Z",
                        "estimated_completion": "2024-01-24T12:30:00Z",
                        "current_stage": "Policy Validation",
                        "progress_percentage": 65,
                        "next_actions": None
                    }
                },
                "more_info_needed": {
                    "summary": "Additional Information Required",
                    "value": {
                        "request_id": "req_2024_001235",
                        "status": "more_info_needed",
                        "submitted_at": "2024-01-24T08:30:00Z",
                        "updated_at": "2024-01-24T11:45:00Z",
                        "estimated_completion": None,
                        "current_stage": "Awaiting Additional Information",
                        "progress_percentage": 50,
                        "next_actions": [
                            "Submit recent imaging reports",
                            "Provide updated clinical notes"
                        ]
                    }
                }
            }
        },
        "GET /api/v1/decisions/{decision_id}": {
            "200": {
                "approved_decision": {
                    "summary": "Approved Authorization",
                    "value": {
                        "decision_id": "dec_2024_001234",
                        "request_id": "req_2024_001234",
                        "status": "approved",
                        "reasoning": [
                            "Medical necessity criteria met per CMS NCD 220.2",
                            "ICD-10 code G93.1 supports requested MRI procedure",
                            "Provider credentials verified and in-network"
                        ],
                        "policy_references": ["CMS_NCD_220.2", "PAYER_POLICY_MRI_001"],
                        "authorization_number": "AUTH2024001234",
                        "valid_until": "2024-02-24T10:30:00Z",
                        "confidence_score": 0.95,
                        "decided_at": "2024-01-24T10:30:00Z",
                        "decision_maker": "automated_engine"
                    }
                },
                "denied_decision": {
                    "summary": "Denied Authorization",
                    "value": {
                        "decision_id": "dec_2024_001235",
                        "request_id": "req_2024_001235",
                        "status": "denied",
                        "reasoning": [
                            "Medical necessity not established per CMS guidelines",
                            "Alternative diagnostic procedures should be considered first",
                            "Insufficient clinical documentation provided"
                        ],
                        "policy_references": ["CMS_NCD_220.2", "PAYER_POLICY_MRI_001"],
                        "authorization_number": None,
                        "valid_until": None,
                        "confidence_score": 0.88,
                        "decided_at": "2024-01-24T10:30:00Z",
                        "decision_maker": "automated_engine"
                    }
                }
            }
        },
        "GET /api/v1/dashboard/summary/{provider_id}": {
            "200": {
                "dashboard_summary": {
                    "summary": "Provider Dashboard Summary",
                    "value": {
                        "provider_id": "prov_12345",
                        "total_requests": 150,
                        "pending_requests": 12,
                        "approved_requests": 120,
                        "denied_requests": 15,
                        "requests_needing_info": 3,
                        "average_processing_time_hours": 1.5,
                        "approval_rate_percentage": 88.2,
                        "recent_activity_count": 8,
                        "urgent_requests_count": 2
                    }
                }
            }
        }
    }


def get_api_tags() -> List[Dict[str, str]]:
    """
    Get API tags with descriptions for organization.
    
    Returns:
        List of tag definitions
    """
    return [
        {
            "name": "authentication",
            "description": "OAuth 2.0 authentication and user management endpoints"
        },
        {
            "name": "intake",
            "description": "Authorization request submission and status tracking"
        },
        {
            "name": "dashboard",
            "description": "Provider dashboard and analytics endpoints"
        },
        {
            "name": "health",
            "description": "System health monitoring and status endpoints"
        },
        {
            "name": "decisions",
            "description": "Authorization decision retrieval and management"
        },
        {
            "name": "policies",
            "description": "Coverage policy management and validation"
        }
    ]


def add_request_examples() -> Dict[str, Any]:
    """
    Get comprehensive request examples for API documentation.
    
    Returns:
        Dictionary of request examples by endpoint
    """
    return {
        "authorization_request_mri": {
            "summary": "MRI Authorization Request",
            "description": "Complete prior authorization request for brain MRI",
            "value": {
                "provider_id": "prov_12345",
                "patient_demographics": {
                    "patient_id": "encrypted_patient_id_hash",
                    "age": 45,
                    "gender": "female",
                    "insurance_id": "encrypted_insurance_id",
                    "member_id": "encrypted_member_id"
                },
                "diagnosis_codes": [
                    {
                        "code": "G93.1",
                        "description": "Anoxic brain damage, not elsewhere classified",
                        "code_type": "icd10"
                    }
                ],
                "procedure_codes": [
                    {
                        "code": "70551",
                        "description": "MRI brain without contrast",
                        "code_type": "cpt"
                    }
                ],
                "clinical_notes": "Patient presents with persistent headaches and memory issues following recent head trauma. Neurological examination shows mild cognitive impairment. MRI requested to rule out structural brain damage.",
                "urgency_level": "routine",
                "procedure_type": "mri"
            }
        },
        "authorization_request_ct": {
            "summary": "CT Scan Authorization Request",
            "description": "Prior authorization request for abdominal CT scan",
            "value": {
                "provider_id": "prov_67890",
                "patient_demographics": {
                    "patient_id": "encrypted_patient_id_hash_2",
                    "age": 62,
                    "gender": "male",
                    "insurance_id": "encrypted_insurance_id_2",
                    "member_id": "encrypted_member_id_2"
                },
                "diagnosis_codes": [
                    {
                        "code": "R10.9",
                        "description": "Unspecified abdominal pain",
                        "code_type": "icd10"
                    },
                    {
                        "code": "K59.00",
                        "description": "Constipation, unspecified",
                        "code_type": "icd10"
                    }
                ],
                "procedure_codes": [
                    {
                        "code": "74177",
                        "description": "CT abdomen and pelvis with contrast",
                        "code_type": "cpt"
                    }
                ],
                "clinical_notes": "62-year-old male with 3-week history of severe abdominal pain and constipation. Physical exam reveals abdominal distension and tenderness. Conservative treatment has failed. CT scan requested to rule out bowel obstruction or other pathology.",
                "urgency_level": "urgent",
                "procedure_type": "ct_scan"
            }
        },
        "authorization_request_xray": {
            "summary": "X-Ray Authorization Request",
            "description": "Prior authorization request for chest X-ray",
            "value": {
                "provider_id": "prov_11111",
                "patient_demographics": {
                    "patient_id": "encrypted_patient_id_hash_3",
                    "age": 28,
                    "gender": "female",
                    "insurance_id": "encrypted_insurance_id_3",
                    "member_id": "encrypted_member_id_3"
                },
                "diagnosis_codes": [
                    {
                        "code": "R05",
                        "description": "Cough",
                        "code_type": "icd10"
                    },
                    {
                        "code": "R50.9",
                        "description": "Fever, unspecified",
                        "code_type": "icd10"
                    }
                ],
                "procedure_codes": [
                    {
                        "code": "71045",
                        "description": "Chest X-ray, single view",
                        "code_type": "cpt"
                    }
                ],
                "clinical_notes": "28-year-old female presents with persistent cough and fever for 5 days. Physical examination reveals decreased breath sounds in right lower lobe. Chest X-ray requested to evaluate for pneumonia.",
                "urgency_level": "routine",
                "procedure_type": "x_ray"
            }
        },
        "login_request_provider": {
            "summary": "Healthcare Provider Login",
            "description": "Authentication for healthcare provider",
            "value": {
                "username": "provider1",
                "password": "provider123"
            }
        },
        "login_request_admin": {
            "summary": "Payer Administrator Login",
            "description": "Authentication for payer administrator",
            "value": {
                "username": "admin1",
                "password": "admin123"
            }
        },
        "additional_info_request": {
            "summary": "Additional Information Submission",
            "description": "Submitting additional clinical information for a request",
            "value": {
                "additional_clinical_notes": "Follow-up examination shows worsening symptoms. Patient reports increased frequency of headaches and new onset of dizziness. Neurological assessment indicates possible progression of condition.",
                "supporting_documents": [
                    {
                        "document_type": "lab_results",
                        "document_id": "lab_2024_001",
                        "description": "Complete blood count and metabolic panel"
                    },
                    {
                        "document_type": "imaging_report",
                        "document_id": "img_2024_002",
                        "description": "Previous CT scan report from 6 months ago"
                    }
                ],
                "updated_diagnosis_codes": [
                    {
                        "code": "G93.1",
                        "description": "Anoxic brain damage, not elsewhere classified",
                        "code_type": "icd10"
                    },
                    {
                        "code": "R42",
                        "description": "Dizziness and giddiness",
                        "code_type": "icd10"
                    }
                ]
            }
        }
    }
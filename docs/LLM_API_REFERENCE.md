# LLM-Enhanced Decision Engine API Reference

## Overview

This document provides comprehensive API documentation for the LLM-enhanced endpoints in the Prior Authorization Agent. These endpoints leverage Large Language Models from Hugging Face to provide AI-powered medical decision-making with enhanced reasoning capabilities.

### Enhanced Features
- **Enhanced Medical Context**: Support for additional clinical data including patient history, comorbidities, medications, and social determinants
- **LLM Decision Explanations**: Detailed explanations of AI-powered decisions with medical reasoning and confidence analysis
- **Alternative Recommendations**: Clinically appropriate alternative procedures with rationale and appropriateness scores
- **Streaming Responses**: Real-time decision processing updates via Server-Sent Events
- **Webhook Notifications**: Automated notifications to external systems for decision events

## Base URL

```
https://api.priorauth.example.com/v2
```

## Authentication

All endpoints require OAuth 2.0 Bearer token authentication:

```http
Authorization: Bearer <your_access_token>
```

## LLM Decision Endpoints

### 1. Enhanced Authorization Request

Submit a prior authorization request for LLM-powered decision-making.

**Endpoint:** `POST /llm/authorization`

**Request Body:**
```json
{
  "request_id": "string (optional)",
  "patient_info": {
    "patient_id": "string",
    "age": "integer",
    "gender": "string",
    "member_id": "string"
  },
  "provider_info": {
    "provider_id": "string",
    "npi": "string",
    "facility_name": "string"
  },
  "procedure_info": {
    "cpt_code": "string",
    "procedure_name": "string",
    "urgency": "routine|urgent|emergent",
    "requested_date": "string (ISO 8601)"
  },
  "clinical_context": {
    "primary_diagnosis": {
      "icd10_code": "string",
      "description": "string",
      "onset_date": "string (ISO 8601)"
    },
    "secondary_diagnoses": [
      {
        "icd10_code": "string",
        "description": "string"
      }
    ],
    "clinical_notes": "string",
    "treatment_history": [
      {
        "procedure": "string",
        "date": "string (ISO 8601)",
        "outcome": "string"
      }
    ],
    "lab_results": [
      {
        "test_name": "string",
        "value": "string",
        "date": "string (ISO 8601)",
        "normal_range": "string"
      }
    ]
  },
  "policy_context": {
    "payer_id": "string",
    "plan_type": "string",
    "coverage_effective_date": "string (ISO 8601)"
  }
}
```

**Response:**
```json
{
  "request_id": "string",
  "decision": "APPROVE|DENY|PENDING",
  "confidence_score": "number (0.0-1.0)",
  "medical_reasoning": "string",
  "policy_compliance": {
    "compliant": "boolean",
    "violated_policies": ["string"],
    "compliance_score": "number (0.0-1.0)",
    "policy_references": ["string"]
  },
  "required_documentation": ["string"],
  "alternative_procedures": [
    {
      "cpt_code": "string",
      "procedure_name": "string",
      "justification": "string",
      "likelihood_of_approval": "number (0.0-1.0)"
    }
  ],
  "risk_factors": [
    {
      "factor": "string",
      "severity": "low|medium|high",
      "description": "string"
    }
  ],
  "contraindications": ["string"],
  "model_used": "string",
  "processing_time": "number (seconds)",
  "timestamp": "string (ISO 8601)",
  "expires_at": "string (ISO 8601)"
}
```

**Status Codes:**
- `200 OK`: Decision successfully generated
- `400 Bad Request`: Invalid request format or missing required fields
- `401 Unauthorized`: Invalid or missing authentication token
- `422 Unprocessable Entity`: Valid format but business logic validation failed
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: LLM service unavailable or internal error
- `503 Service Unavailable`: System maintenance or overload

### 2. Get Decision Explanation

Retrieve detailed explanation for a previous decision.

**Endpoint:** `GET /llm/decisions/{decision_id}/explanation`

**Response:**
```json
{
  "decision_id": "string",
  "detailed_reasoning": {
    "medical_analysis": "string",
    "policy_analysis": "string",
    "risk_assessment": "string",
    "clinical_guidelines_referenced": ["string"],
    "literature_references": ["string"]
  },
  "decision_factors": [
    {
      "factor": "string",
      "weight": "number (0.0-1.0)",
      "impact": "positive|negative|neutral",
      "description": "string"
    }
  ],
  "similar_cases": [
    {
      "case_id": "string",
      "similarity_score": "number (0.0-1.0)",
      "decision": "string",
      "key_differences": ["string"]
    }
  ],
  "model_confidence_breakdown": {
    "medical_necessity": "number (0.0-1.0)",
    "policy_compliance": "number (0.0-1.0)",
    "clinical_appropriateness": "number (0.0-1.0)",
    "overall_confidence": "number (0.0-1.0)"
  }
}
```

### 3. Get Alternative Recommendations

Get alternative procedure recommendations for denied requests.

**Endpoint:** `GET /llm/decisions/{decision_id}/alternatives`

**Response:**
```json
{
  "decision_id": "string",
  "alternatives": [
    {
      "cpt_code": "string",
      "procedure_name": "string",
      "medical_justification": "string",
      "cost_comparison": {
        "original_procedure_cost": "number",
        "alternative_cost": "number",
        "cost_savings": "number"
      },
      "approval_likelihood": "number (0.0-1.0)",
      "clinical_effectiveness": "number (0.0-1.0)",
      "required_documentation": ["string"],
      "contraindications": ["string"]
    }
  ],
  "step_therapy_options": [
    {
      "step": "integer",
      "procedures": ["string"],
      "duration": "string",
      "success_criteria": ["string"]
    }
  ]
}
```

### 4. Batch Authorization Processing

Process multiple authorization requests in a single API call.

**Endpoint:** `POST /llm/authorization/batch`

**Request Body:**
```json
{
  "requests": [
    {
      "batch_id": "string",
      "request": {
        // Same structure as single authorization request
      }
    }
  ],
  "processing_options": {
    "parallel_processing": "boolean",
    "priority": "low|normal|high",
    "callback_url": "string (optional)"
  }
}
```

**Response:**
```json
{
  "batch_id": "string",
  "status": "processing|completed|failed",
  "total_requests": "integer",
  "completed_requests": "integer",
  "results": [
    {
      "batch_id": "string",
      "status": "completed|failed|pending",
      "decision": {
        // Same structure as single authorization response
      },
      "error": "string (if failed)"
    }
  ],
  "processing_time": "number (seconds)",
  "estimated_completion": "string (ISO 8601, if still processing)"
}
```

## Medical Codes Endpoints

### 1. Validate Medical Code

Validate ICD-10 or CPT codes with AI-enhanced suggestions.

**Endpoint:** `POST /llm/codes/validate`

**Request Body:**
```json
{
  "codes": [
    {
      "code": "string",
      "type": "icd10|cpt|hcpcs"
    }
  ],
  "context": {
    "patient_age": "integer (optional)",
    "patient_gender": "string (optional)",
    "clinical_context": "string (optional)"
  }
}
```

**Response:**
```json
{
  "validation_results": [
    {
      "code": "string",
      "type": "string",
      "valid": "boolean",
      "description": "string",
      "category": "string",
      "billable": "boolean",
      "age_restrictions": {
        "min_age": "integer",
        "max_age": "integer"
      },
      "gender_restrictions": ["M|F"],
      "suggestions": [
        {
          "code": "string",
          "description": "string",
          "similarity_score": "number (0.0-1.0)",
          "reason": "string"
        }
      ],
      "contraindications": [
        {
          "code": "string",
          "description": "string",
          "severity": "warning|error"
        }
      ]
    }
  ]
}
```

### 2. Search Medical Codes

Search for medical codes using natural language or partial codes.

**Endpoint:** `GET /llm/codes/search`

**Query Parameters:**
- `q`: Search query (required)
- `type`: Code type (icd10|cpt|hcpcs) (optional)
- `limit`: Maximum results (default: 20, max: 100)
- `include_deprecated`: Include deprecated codes (default: false)

**Response:**
```json
{
  "query": "string",
  "results": [
    {
      "code": "string",
      "type": "string",
      "description": "string",
      "category": "string",
      "relevance_score": "number (0.0-1.0)",
      "valid_from": "string (ISO 8601)",
      "valid_to": "string (ISO 8601, nullable)",
      "billable": "boolean",
      "related_codes": [
        {
          "code": "string",
          "relationship": "parent|child|related|alternative",
          "description": "string"
        }
      ]
    }
  ],
  "total_results": "integer",
  "search_time": "number (seconds)"
}
```

## Model Management Endpoints

### 1. Get Available Models

List available LLM models and their capabilities.

**Endpoint:** `GET /llm/models`

**Response:**
```json
{
  "models": [
    {
      "model_id": "string",
      "name": "string",
      "description": "string",
      "type": "medical|general",
      "capabilities": ["decision_making", "code_validation", "reasoning"],
      "performance_metrics": {
        "accuracy": "number (0.0-1.0)",
        "avg_response_time": "number (seconds)",
        "availability": "number (0.0-1.0)"
      },
      "cost_per_request": "number",
      "max_context_length": "integer",
      "supported_languages": ["string"],
      "status": "active|maintenance|deprecated"
    }
  ]
}
```

### 2. Get Model Health

Check the health status of LLM models.

**Endpoint:** `GET /llm/models/{model_id}/health`

**Response:**
```json
{
  "model_id": "string",
  "status": "healthy|degraded|unhealthy",
  "response_time": "number (seconds)",
  "error_rate": "number (0.0-1.0)",
  "last_health_check": "string (ISO 8601)",
  "issues": [
    {
      "type": "performance|availability|accuracy",
      "severity": "low|medium|high|critical",
      "description": "string",
      "detected_at": "string (ISO 8601)"
    }
  ],
  "performance_metrics": {
    "requests_per_minute": "number",
    "avg_response_time_24h": "number (seconds)",
    "success_rate_24h": "number (0.0-1.0)"
  }
}
```

## Configuration Endpoints

### 1. Get AI Configuration

Retrieve current AI model configuration and parameters.

**Endpoint:** `GET /llm/config`

**Response:**
```json
{
  "primary_model": "string",
  "fallback_models": ["string"],
  "decision_thresholds": {
    "approval_threshold": "number (0.0-1.0)",
    "denial_threshold": "number (0.0-1.0)",
    "human_review_threshold": "number (0.0-1.0)"
  },
  "prompt_templates": {
    "decision_making": "string",
    "code_validation": "string",
    "explanation_generation": "string"
  },
  "performance_settings": {
    "max_response_time": "number (seconds)",
    "parallel_requests": "integer",
    "cache_ttl": "number (seconds)"
  }
}
```

### 2. Update AI Configuration

Update AI model configuration (Admin only).

**Endpoint:** `PUT /llm/config`

**Request Body:**
```json
{
  "primary_model": "string (optional)",
  "fallback_models": ["string"] (optional),
  "decision_thresholds": {
    "approval_threshold": "number (0.0-1.0)",
    "denial_threshold": "number (0.0-1.0)",
    "human_review_threshold": "number (0.0-1.0)"
  } (optional),
  "performance_settings": {
    "max_response_time": "number (seconds)",
    "parallel_requests": "integer",
    "cache_ttl": "number (seconds)"
  } (optional)
}
```

## Error Handling

### Standard Error Response Format

```json
{
  "error": {
    "code": "string",
    "message": "string",
    "details": "string (optional)",
    "timestamp": "string (ISO 8601)",
    "request_id": "string"
  },
  "suggestions": [
    {
      "action": "string",
      "description": "string"
    }
  ]
}
```

### Common Error Codes

- `INVALID_REQUEST`: Request format or required fields are invalid
- `MODEL_UNAVAILABLE`: Selected LLM model is not available
- `CONFIDENCE_TOO_LOW`: LLM confidence below threshold, human review required
- `RATE_LIMIT_EXCEEDED`: Too many requests in time window
- `MEDICAL_CODE_INVALID`: Provided medical codes are invalid or deprecated
- `POLICY_VIOLATION`: Request violates configured policies
- `PROCESSING_TIMEOUT`: Request processing exceeded time limit
- `INSUFFICIENT_CONTEXT`: Not enough clinical information for decision
- `AUTHENTICATION_FAILED`: Invalid or expired authentication token
- `AUTHORIZATION_DENIED`: User lacks permission for requested operation

## Rate Limiting

API endpoints are rate-limited to ensure fair usage:

- **Standard endpoints**: 100 requests per minute per API key
- **Batch processing**: 10 requests per minute per API key
- **Model management**: 20 requests per minute per API key

Rate limit headers are included in all responses:
```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1640995200
```

## Webhooks

Configure webhooks to receive real-time notifications for decision updates:

### Webhook Events

- `decision.completed`: Authorization decision completed
- `decision.updated`: Decision status changed
- `batch.completed`: Batch processing completed
- `model.health_changed`: Model health status changed

### Webhook Payload Example

```json
{
  "event": "decision.completed",
  "timestamp": "string (ISO 8601)",
  "data": {
    "decision_id": "string",
    "request_id": "string",
    "decision": "APPROVE|DENY|PENDING",
    "confidence_score": "number (0.0-1.0)"
  }
}
```

## SDK and Code Examples

### Python SDK Example

```python
from priorauth_llm import LLMClient

client = LLMClient(
    api_key="your_api_key",
    base_url="https://api.priorauth.example.com/v2"
)

# Submit authorization request
response = client.submit_authorization({
    "patient_info": {
        "patient_id": "P123456",
        "age": 45,
        "gender": "F"
    },
    "procedure_info": {
        "cpt_code": "72148",
        "procedure_name": "MRI Lumbar Spine"
    },
    "clinical_context": {
        "primary_diagnosis": {
            "icd10_code": "M54.5",
            "description": "Low back pain"
        },
        "clinical_notes": "Patient reports chronic lower back pain for 6 months"
    }
})

print(f"Decision: {response.decision}")
print(f"Confidence: {response.confidence_score}")
print(f"Reasoning: {response.medical_reasoning}")
```

### JavaScript SDK Example

```javascript
import { LLMClient } from '@priorauth/llm-client';

const client = new LLMClient({
  apiKey: 'your_api_key',
  baseUrl: 'https://api.priorauth.example.com/v2'
});

// Submit authorization request
const response = await client.submitAuthorization({
  patientInfo: {
    patientId: 'P123456',
    age: 45,
    gender: 'F'
  },
  procedureInfo: {
    cptCode: '72148',
    procedureName: 'MRI Lumbar Spine'
  },
  clinicalContext: {
    primaryDiagnosis: {
      icd10Code: 'M54.5',
      description: 'Low back pain'
    },
    clinicalNotes: 'Patient reports chronic lower back pain for 6 months'
  }
});

console.log(`Decision: ${response.decision}`);
console.log(`Confidence: ${response.confidenceScore}`);
console.log(`Reasoning: ${response.medicalReasoning}`);
```

## Testing and Sandbox

A sandbox environment is available for testing:

**Sandbox URL:** `https://sandbox-api.priorauth.example.com/v2`

- Use test API keys (prefix: `test_`)
- No real medical decisions are made
- Rate limits are more relaxed
- Mock data is returned for testing purposes

## Support and Resources

- **API Status**: https://status.priorauth.example.com
- **Developer Portal**: https://developers.priorauth.example.com
- **Support Email**: api-support@priorauth.example.com
- **Documentation Updates**: Subscribe to our developer newsletter for API changes
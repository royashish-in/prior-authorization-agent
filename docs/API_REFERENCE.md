# Prior Authorization Agent - API Reference

## 📚 Complete API Endpoint Reference

### Base URL
```
http://127.0.0.1:8000/api/v1
```

---

## 🔐 Authentication Endpoints

### POST /auth/login
**Description:** Form-based user authentication

**Request:**
```bash
curl -X POST "/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=provider1&password=provider123"
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400,
  "scope": null
}
```

### POST /auth/login-json
**Description:** JSON-based user authentication

**Request:**
```bash
curl -X POST "/api/v1/auth/login-json" \
  -H "Content-Type: application/json" \
  -d '{"username": "provider1", "password": "provider123"}'
```

### GET /auth/me
**Description:** Get current user information

**Headers:** `Authorization: Bearer {token}`

**Response:**
```json
{
  "user_id": "user_001",
  "username": "provider1",
  "email": "provider1@hospital.com",
  "full_name": "Dr. John Provider",
  "roles": ["provider"],
  "organization_id": "org_hospital_001",
  "is_active": true
}
```

### POST /auth/refresh
**Description:** Refresh access token

**Headers:** `Authorization: Bearer {token}`

### POST /auth/logout
**Description:** Logout and invalidate token

**Headers:** `Authorization: Bearer {token}`

---

## 📝 Authorization Request Endpoints

### POST /authorization/requests
**Description:** Submit new authorization request

**Headers:** `Authorization: Bearer {token}`

**Request Body:**
```json
{
  "request_id": "req_2024_001234",
  "provider_id": "prov_12345",
  "patient_demographics": {
    "patient_id": "enc_pat_1a2b3c4d5e6f7g8h",
    "age": 45,
    "gender": "female",
    "insurance_id": "enc_ins_9z8y7x6w5v4u3t2s",
    "member_id": "enc_mem_a1b2c3d4e5f6g7h8"
  },
  "diagnosis_codes": [
    {
      "code": "M25.511",
      "description": "Pain in right shoulder",
      "category": "musculoskeletal"
    }
  ],
  "procedure_codes": [
    {
      "code": "73221",
      "description": "MRI upper extremity without contrast",
      "category": "radiology"
    }
  ],
  "clinical_notes": "Patient presents with chronic right shoulder pain...",
  "procedure_type": "mri",
  "urgency_level": "routine"
}
```

**Response:**
```json
{
  "request_id": "req_2025_732009",
  "status": "submitted",
  "message": "Authorization request submitted successfully",
  "timestamp": "2025-07-28T04:42:11.715703Z",
  "validation_warnings": null
}
```

### GET /authorization/requests
**Description:** Get requests by provider

**Headers:** `Authorization: Bearer {token}`

**Query Parameters:**
- `provider_id` (required): Provider identifier
- `status` (optional): Filter by status
- `page` (optional): Page number (default: 1)
- `page_size` (optional): Items per page (default: 20)

### GET /authorization/requests/{request_id}
**Description:** Get specific request status

**Headers:** `Authorization: Bearer {token}`

**Response:**
```json
{
  "request_id": "req_2025_732009",
  "status": "submitted",
  "submitted_at": "2025-07-28T04:42:11.715703Z",
  "updated_at": "2025-07-28T04:42:27.393283Z",
  "estimated_completion": "2025-07-28T06:42:11.715703Z",
  "current_stage": "Initial Review",
  "progress_percentage": 10,
  "next_actions": [
    "Awaiting medical code validation",
    "Awaiting policy review"
  ]
}
```

### PUT /authorization/requests/{request_id}/additional-info
**Description:** Submit additional information for a request

**Headers:** `Authorization: Bearer {token}`

**Request Body:**
```json
{
  "additional_notes": "Updated clinical notes with recent test results",
  "supporting_documents": ["lab_results.pdf", "imaging_report.pdf"]
}
```

---

## 🎯 Decision Endpoints

### GET /decisions/{decision_id}
**Description:** Get specific authorization decision

**Headers:** `Authorization: Bearer {token}`

**Response:**
```json
{
  "decision_id": "dec_2024_001234",
  "request_id": "req_2024_001234",
  "status": "approved",
  "reasoning": [
    "Medical necessity criteria met per CMS NCD 220.2",
    "ICD-10 code M25.511 supports requested MRI procedure"
  ],
  "policy_references": ["CMS_NCD_220.2", "PAYER_POLICY_MRI_001"],
  "authorization_number": "auth_2024_001234",
  "valid_until": "2025-01-28T04:42:11.715703Z",
  "confidence_score": 0.95,
  "decided_at": "2025-07-28T04:45:11.715703Z"
}
```

### GET /decisions/request/{request_id}
**Description:** Get decision by request ID

**Headers:** `Authorization: Bearer {token}`

### GET /decisions/provider/{provider_id}/history
**Description:** Get provider's decision history

**Headers:** `Authorization: Bearer {token}`

**Query Parameters:**
- `page` (optional): Page number
- `page_size` (optional): Items per page
- `status` (optional): Filter by decision status
- `date_from` (optional): Start date filter
- `date_to` (optional): End date filter

### GET /decisions/provider/{provider_id}/summary
**Description:** Get provider's decision summary statistics

**Headers:** `Authorization: Bearer {token}`

**Response:**
```json
{
  "provider_id": "prov_12345",
  "total_decisions": 150,
  "approved_count": 120,
  "denied_count": 25,
  "pending_count": 5,
  "approval_rate_percentage": 80.0,
  "average_processing_time_hours": 1.5,
  "last_30_days": {
    "total_decisions": 45,
    "approval_rate": 82.2
  }
}
```

---

## 📊 Dashboard Endpoints

### GET /dashboard/summary/{provider_id}
**Description:** Get provider dashboard summary

**Headers:** `Authorization: Bearer {token}`

**Response:**
```json
{
  "provider_id": "prov_12345",
  "total_requests": 150,
  "pending_requests": 5,
  "approved_requests": 120,
  "denied_requests": 25,
  "requests_needing_info": 3,
  "average_processing_time_hours": 1.5,
  "approval_rate_percentage": 80.0,
  "recent_activity_count": 12,
  "urgent_requests_count": 2
}
```

### GET /dashboard/requests/{provider_id}
**Description:** Get filtered requests for provider

**Headers:** `Authorization: Bearer {token}`

**Query Parameters:**
- `status` (optional): Filter by status
- `procedure_type` (optional): Filter by procedure type
- `urgency_level` (optional): Filter by urgency
- `date_from` (optional): Start date filter
- `date_to` (optional): End date filter
- `page` (optional): Page number
- `page_size` (optional): Items per page

**Response:**
```json
{
  "requests": [
    {
      "request_id": "req_2024_001234",
      "status": "approved",
      "procedure_type": "mri",
      "submitted_at": "2025-07-28T04:42:11.715703Z",
      "estimated_completion": "2025-07-28T06:42:11.715703Z"
    }
  ],
  "total_count": 150,
  "page": 1,
  "page_size": 20,
  "total_pages": 8,
  "filters_applied": {
    "status": "approved"
  }
}
```

### GET /dashboard/metrics/{provider_id}
**Description:** Get activity metrics for provider

**Headers:** `Authorization: Bearer {token}`

**Query Parameters:**
- `time_range` (optional): Time range (7d, 30d, 90d, 1y)

**Response:**
```json
{
  "provider_id": "prov_12345",
  "time_range": "30d",
  "metrics": {
    "total_requests": 45,
    "approval_rate": 82.2,
    "average_processing_time": 1.3,
    "requests_by_status": {
      "approved": 37,
      "denied": 6,
      "pending": 2
    },
    "requests_by_procedure": {
      "mri": 25,
      "ct": 15,
      "xray": 5
    },
    "daily_activity": [
      {"date": "2025-07-01", "requests": 3, "approvals": 2},
      {"date": "2025-07-02", "requests": 5, "approvals": 4}
    ]
  }
}
```

---

## 🏥 Health Check Endpoints

### GET /health
**Description:** Basic health check

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-07-28T04:26:47.646148Z",
  "version": "1.0.0",
  "environment": "development",
  "checks": {
    "database": "healthy"
  }
}
```

### GET /health/detailed
**Description:** Detailed health check with all subsystems

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-07-28T04:26:47.646148Z",
  "version": "1.0.0",
  "environment": "development",
  "uptime_seconds": 3600.5,
  "checks": {
    "database": {
      "status": "healthy",
      "response_time_ms": 5,
      "details": "Database connection successful"
    },
    "external_services": {
      "cms_api": {
        "status": "healthy",
        "url": "https://api.cms.gov",
        "response_time_ms": 150,
        "details": "CMS API accessible"
      }
    }
  }
}
```

### GET /health/ready
**Description:** Kubernetes readiness probe

**Response:**
```json
{
  "status": "ready"
}
```

### GET /health/live
**Description:** Kubernetes liveness probe

**Response:**
```json
{
  "status": "alive"
}
```

---

## 📋 Data Models

### AuthorizationRequest
```json
{
  "request_id": "string",
  "provider_id": "string",
  "patient_demographics": {
    "patient_id": "string (encrypted)",
    "age": "integer",
    "gender": "string",
    "insurance_id": "string (encrypted)",
    "member_id": "string (encrypted)"
  },
  "diagnosis_codes": [
    {
      "code": "string",
      "description": "string",
      "category": "string"
    }
  ],
  "procedure_codes": [
    {
      "code": "string",
      "description": "string",
      "category": "string"
    }
  ],
  "clinical_notes": "string (encrypted)",
  "procedure_type": "mri|ct|xray|ultrasound",
  "urgency_level": "routine|urgent|stat",
  "status": "submitted|in_review|approved|denied|more_info_needed",
  "submitted_at": "datetime",
  "updated_at": "datetime"
}
```

### AuthorizationDecision
```json
{
  "decision_id": "string",
  "request_id": "string",
  "status": "approved|denied|more_info_needed",
  "reasoning": ["string"],
  "policy_references": ["string"],
  "authorization_number": "string",
  "valid_until": "datetime",
  "confidence_score": "float",
  "decided_at": "datetime",
  "decision_maker": "string"
}
```

---

## 🚨 Error Responses

### Standard Error Format
```json
{
  "error": "ERROR_CODE",
  "message": "Human readable error message",
  "details": {
    "field": "field_name",
    "value": "invalid_value",
    "suggestion": "Use valid format"
  },
  "request_id": "req_id_if_applicable",
  "timestamp": "2025-07-28T04:42:11.715703Z"
}
```

### Common HTTP Status Codes
- `200` - Success
- `201` - Created
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `422` - Validation Error
- `429` - Rate Limited
- `500` - Internal Server Error
- `503` - Service Unavailable

---

## 🔒 Authentication

All endpoints (except health checks) require authentication using JWT Bearer tokens:

```bash
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Token Lifecycle
- **Expiration**: 24 hours
- **Refresh**: Use `/auth/refresh` endpoint
- **Logout**: Use `/auth/logout` to invalidate

---

## 📊 Rate Limiting

- **Limit**: 100 requests per minute per user
- **Headers**: Rate limit info included in response headers
- **Exceeded**: Returns 429 status with retry information

---

## 🎯 Best Practices

1. **Always check response status codes**
2. **Handle authentication errors gracefully**
3. **Implement proper retry logic for rate limits**
4. **Use pagination for large result sets**
5. **Store and reuse tokens until expiration**
6. **Include proper error handling for all API calls**

This API reference provides complete technical details for integrating with the Prior Authorization Agent system.
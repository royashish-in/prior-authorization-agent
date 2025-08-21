# Medical Codes API Documentation

This document provides comprehensive documentation for the enhanced medical codes API endpoints implemented in Task 9.

## Overview

The Medical Codes API provides comprehensive functionality for managing, validating, and searching medical codes (ICD-10, CPT, and HCPCS) with advanced features including:

- Real-time code validation with caching
- Fuzzy search and intelligent suggestions
- Bulk import/export capabilities
- Code relationship management
- Administrative functions

## Base URL

All endpoints are prefixed with: `/api/v1/medical-codes`

## Authentication

All endpoints require proper authentication. Include your authentication token in the request headers.

## Endpoints

### 1. Code Validation Endpoints

#### Validate Single Code
**POST** `/validate`

Validates a single medical code and provides suggestions if invalid.

**Request Body:**
```json
{
  "code": "70551",
  "code_type": "CPT"
}
```

**Response:**
```json
{
  "code": "70551",
  "code_type": "CPT",
  "valid": true,
  "description": "MRI brain without contrast",
  "suggestions": [],
  "effective_date": "2023-01-01",
  "expiration_date": null,
  "error_message": null
}
```

#### Batch Validate Codes
**POST** `/validate/batch`

Validates multiple codes in a single request for better performance.

**Request Body:**
```json
[
  {"code": "70551", "code_type": "CPT"},
  {"code": "M25.511", "code_type": "ICD10"}
]
```

**Response:**
```json
{
  "70551": {
    "code": "70551",
    "code_type": "CPT",
    "valid": true,
    "description": "MRI brain without contrast"
  },
  "M25.511": {
    "code": "M25.511",
    "code_type": "ICD10",
    "valid": true,
    "description": "Pain in right shoulder"
  }
}
```

### 2. Search Endpoints

#### Search Medical Codes
**GET** `/search`

Search medical codes with advanced filtering and fuzzy matching.

**Query Parameters:**
- `query` (required): Search query string
- `code_type` (required): ICD10, CPT, or HCPCS
- `category` (optional): Filter by category
- `billable_only` (optional): Only billable codes (ICD-10)
- `prior_auth_only` (optional): Only codes requiring prior auth (CPT)
- `valid_only` (optional): Only currently valid codes (default: true)
- `limit` (optional): Max results (default: 50, max: 100)
- `offset` (optional): Pagination offset (default: 0)

**Example:**
```
GET /search?query=MRI%20brain&code_type=CPT&limit=10
```

**Response:**
```json
{
  "results": [
    {
      "id": 1,
      "code": "70551",
      "description": "MRI brain without contrast",
      "category": "radiology",
      "is_currently_valid": true
    }
  ],
  "total_count": 1,
  "query": "MRI brain",
  "code_type": "CPT",
  "limit": 10,
  "offset": 0
}
```

### 3. Code Suggestions

#### Get Code Suggestions
**GET** `/suggestions`

Get real-time code suggestions with enhanced fuzzy matching.

**Query Parameters:**
- `partial_code` (required): Partial code input
- `code_type` (required): ICD10, CPT, or HCPCS
- `limit` (optional): Max suggestions (default: 10, max: 50)
- `fuzzy_match` (optional): Enable fuzzy matching (default: true)
- `include_descriptions` (optional): Include descriptions (default: true)
- `category_filter` (optional): Filter by category

**Example:**
```
GET /suggestions?partial_code=705&code_type=CPT&fuzzy_match=true
```

**Response:**
```json
{
  "suggestions": [
    {
      "id": 1,
      "code": "70551",
      "description": "MRI brain without contrast",
      "relevance_score": 1.0,
      "match_type": "code_prefix"
    }
  ],
  "partial_code": "705",
  "code_type": "CPT"
}
```

### 4. Bulk Management Endpoints

#### Bulk Import Codes
**POST** `/bulk/import`

Import multiple codes for administrative functions.

**Request Body:**
```json
{
  "codes": [
    {
      "code": "99999",
      "description": "Test procedure",
      "category": "test",
      "valid_from": "2025-01-01"
    }
  ],
  "code_type": "CPT",
  "overwrite_existing": false
}
```

**Response:**
```json
{
  "successful_count": 1,
  "failed_count": 0,
  "errors": [],
  "total_processed": 1
}
```

#### Bulk Import from File
**POST** `/bulk/import/file`

Import codes from uploaded CSV or JSON file.

**Form Data:**
- `file`: CSV or JSON file
- `code_type`: ICD10 or CPT
- `overwrite_existing`: boolean (optional)

**Response:** Same as bulk import

#### Bulk Export Codes
**POST** `/bulk/export`

Export codes in JSON or CSV format.

**Query Parameters:**
- `code_type` (required): ICD10 or CPT
- `format` (optional): json or csv (default: json)
- `category` (optional): Filter by category
- `valid_only` (optional): Only valid codes (default: true)

**Response:**
```json
{
  "format": "json",
  "codes": [...],
  "total_exported": 100,
  "export_timestamp": "2025-07-30T10:00:00"
}
```

#### Bulk Update Codes
**PUT** `/bulk/update`

Update multiple codes simultaneously.

**Query Parameters:**
- `code_type` (required): ICD10 or CPT

**Request Body:**
```json
[
  {
    "id": 1,
    "description": "Updated description",
    "category": "updated_category"
  }
]
```

#### Bulk Delete Codes
**DELETE** `/bulk/delete`

Delete multiple codes by ID.

**Query Parameters:**
- `code_type` (required): ICD10 or CPT

**Request Body:**
```json
[1, 2, 3]
```

### 5. Code Relationship Endpoints

#### Get Code Relationships
**GET** `/relationships/{code_id}`

Get all relationships for a specific code.

**Query Parameters:**
- `code_type` (required): ICD10 or CPT
- `relationship_type` (optional): Filter by type
- `active_only` (optional): Only active relationships (default: true)
- `include_details` (optional): Include detailed code info (default: true)

**Response:**
```json
{
  "relationships": [
    {
      "id": 1,
      "primary_code_id": 1,
      "related_code_id": 2,
      "relationship_type": "contraindicated",
      "strength": 0.9,
      "confidence": 0.95,
      "clinical_rationale": "May cause adverse interactions"
    }
  ],
  "code_id": 1,
  "code_type": "CPT"
}
```

#### Get Contraindications
**GET** `/contraindications/{code_id}`

Get contraindicated codes for a specific code.

**Query Parameters:**
- `code_type` (required): ICD10 or CPT
- `severity_threshold` (optional): Min severity (0.0-1.0, default: 0.5)

**Response:**
```json
{
  "code_id": 1,
  "code_type": "CPT",
  "contraindications": [...],
  "total_count": 5,
  "severity_threshold": 0.5
}
```

#### Get Alternatives
**GET** `/alternatives/{code_id}`

Get alternative codes for a specific code.

**Query Parameters:**
- `code_type` (required): ICD10 or CPT
- `min_confidence` (optional): Min confidence (0.0-1.0, default: 0.7)
- `limit` (optional): Max alternatives (default: 10, max: 50)

**Response:**
```json
{
  "code_id": 1,
  "code_type": "CPT",
  "alternatives": [...],
  "total_count": 3,
  "min_confidence": 0.7,
  "limit": 10
}
```

#### Create Code Relationship
**POST** `/relationships`

Create a new relationship between codes.

**Request Body:**
```json
{
  "primary_code_id": 1,
  "primary_code_type": "ICD10",
  "related_code_id": 2,
  "related_code_type": "CPT",
  "relationship_type": "contraindicated",
  "strength": 0.9,
  "clinical_rationale": "Clinical reasoning for relationship"
}
```

### 6. Administrative Endpoints

#### Get Statistics
**GET** `/stats`

Get medical codes database and cache statistics.

**Response:**
```json
{
  "cache_statistics": {
    "cache_hits": 150,
    "cache_misses": 25,
    "cache_hit_rate": 0.857
  },
  "database_statistics": {
    "icd10_codes": "Available via search endpoint",
    "cpt_codes": "Available via search endpoint"
  }
}
```

#### Clear Cache
**DELETE** `/cache`

Clear the medical code validation cache.

**Response:**
```json
{
  "message": "Validation cache cleared successfully"
}
```

## Error Handling

All endpoints return structured error responses:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid code format",
    "details": {},
    "request_id": "req_123",
    "timestamp": "2025-07-30T10:00:00Z"
  }
}
```

### Common Error Codes

- `VALIDATION_ERROR`: Invalid input data
- `NOT_FOUND_ERROR`: Resource not found
- `DATABASE_ERROR`: Database operation failed
- `DUPLICATE_ERROR`: Resource already exists

## Rate Limiting

API endpoints are rate-limited to ensure fair usage:
- Validation endpoints: 100 requests/minute
- Search endpoints: 50 requests/minute
- Bulk operations: 10 requests/minute

## Examples

### Complete Workflow Example

```python
import requests

base_url = "http://localhost:8000/api/v1/medical-codes"
headers = {"Authorization": "Bearer your-token"}

# 1. Validate a code
response = requests.post(f"{base_url}/validate", 
    json={"code": "70551", "code_type": "CPT"},
    headers=headers
)
print(f"Valid: {response.json()['valid']}")

# 2. Search for codes
response = requests.get(f"{base_url}/search",
    params={"query": "MRI brain", "code_type": "CPT"},
    headers=headers
)
print(f"Found {response.json()['total_count']} codes")

# 3. Get suggestions
response = requests.get(f"{base_url}/suggestions",
    params={"partial_code": "705", "code_type": "CPT"},
    headers=headers
)
print(f"Suggestions: {len(response.json()['suggestions'])}")

# 4. Bulk import
codes_data = [
    {"code": "99999", "description": "Test code", "valid_from": "2025-01-01"}
]
response = requests.post(f"{base_url}/bulk/import",
    json={"codes": codes_data, "code_type": "CPT"},
    headers=headers
)
print(f"Imported: {response.json()['successful_count']}")
```

## Performance Considerations

- Use batch validation for multiple codes
- Enable caching for frequently accessed codes
- Use pagination for large search results
- Consider fuzzy matching performance impact

## Security

- All endpoints require authentication
- Input validation prevents injection attacks
- Rate limiting prevents abuse
- Audit logging tracks all operations

## Support

For technical support or questions about the Medical Codes API, please contact the development team or refer to the main API documentation.
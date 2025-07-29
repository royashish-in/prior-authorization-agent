# Prior Authorization Agent - Troubleshooting Guide

## 🔧 Common Issues and Solutions

This guide helps you diagnose and resolve common issues when using the Prior Authorization Agent.

---

## 🚀 Application Startup Issues

### Issue: Server Won't Start
**Symptoms:**
- `Address already in use` error
- Port 8000 is occupied
- Application crashes on startup

**Solutions:**
```bash
# Check what's using port 8000
lsof -i :8000

# Kill existing process
pkill -f "python -m src.main"

# Or kill by PID
kill -9 <PID>

# Start on different port
PA_PORT=8001 python -m src.main
```

### Issue: Virtual Environment Not Activated
**Symptoms:**
- `ModuleNotFoundError` for installed packages
- Wrong Python version

**Solutions:**
```bash
# Activate virtual environment
source venv/bin/activate

# Verify activation
which python
python --version

# Reinstall dependencies if needed
pip install -r requirements.txt
```

### Issue: Database Connection Errors
**Symptoms:**
- `Database connection failed` in health check
- SQLite file permission errors

**Solutions:**
```bash
# Check database file permissions
ls -la prior_auth.db

# Fix permissions
chmod 664 prior_auth.db

# Recreate database if corrupted
rm prior_auth.db
python -m alembic upgrade head
```

---

## 🔐 Authentication Issues

### Issue: Login Fails with Valid Credentials
**Symptoms:**
- 401 Unauthorized with correct username/password
- "Authentication failed" messages

**Debugging Steps:**
```bash
# Test with curl
curl -v -X POST "http://127.0.0.1:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=provider1&password=provider123"

# Check server logs for detailed error
tail -f logs/application.log
```

**Common Causes:**
- Typo in username/password
- Rate limiting active
- Server not running
- Wrong content type header

### Issue: Token Expired Errors
**Symptoms:**
- `Could not validate credentials`
- 401 errors on authenticated endpoints

**Solutions:**
```python
# Python: Check token expiration
from datetime import datetime
if datetime.now() >= client.token_expires:
    client.login("provider1", "provider123")

# JavaScript: Auto-refresh token
if (new Date() >= api.tokenExpires) {
    await api.login('provider1', 'provider123');
}
```

```bash
# Bash: Get fresh token
TOKEN=$(curl -s -X POST "http://127.0.0.1:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=provider1&password=provider123" | \
  python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
```

### Issue: Rate Limiting
**Symptoms:**
- 429 Too Many Requests
- "Rate limit exceeded" messages

**Solutions:**
```python
import time
import requests

def make_request_with_backoff(url, headers, max_retries=3):
    for attempt in range(max_retries):
        response = requests.get(url, headers=headers)
        
        if response.status_code == 429:
            wait_time = 2 ** attempt  # Exponential backoff
            print(f"Rate limited, waiting {wait_time} seconds...")
            time.sleep(wait_time)
            continue
        
        return response
    
    raise Exception("Max retries exceeded")
```

---

## 📝 Request Submission Issues

### Issue: Validation Errors
**Symptoms:**
- 422 Unprocessable Entity
- Field validation error messages

**Common Validation Errors:**

#### Invalid Medical Codes
```json
{
  "error": "VALIDATION_ERROR",
  "message": "Invalid procedure code",
  "details": {
    "field": "procedure_codes[0].code",
    "value": "99999",
    "suggestion": "Use valid CPT code like 73221 for MRI"
  }
}
```

**Solution:**
```python
# Use valid medical codes
valid_diagnosis_codes = [
    {"code": "M25.511", "description": "Pain in right shoulder", "category": "musculoskeletal"},
    {"code": "M79.3", "description": "Panniculitis, unspecified", "category": "musculoskeletal"}
]

valid_procedure_codes = [
    {"code": "73221", "description": "MRI upper extremity without contrast", "category": "radiology"},
    {"code": "70551", "description": "MRI brain without contrast", "category": "radiology"}
]
```

#### Missing Required Fields
```json
{
  "error": "VALIDATION_ERROR",
  "message": "Field required",
  "details": {
    "field": "patient_demographics.age",
    "value": null
  }
}
```

**Solution:**
```python
# Ensure all required fields are present
required_fields = {
    "request_id": "req_2024_001234",
    "provider_id": "prov_12345",
    "patient_demographics": {
        "patient_id": "enc_pat_1a2b3c4d5e6f7g8h",
        "age": 45,  # Required
        "gender": "female",  # Required
        "insurance_id": "enc_ins_9z8y7x6w5v4u3t2s",
        "member_id": "enc_mem_a1b2c3d4e5f6g7h8"
    },
    "diagnosis_codes": [...],  # At least one required
    "procedure_codes": [...],  # At least one required
    "procedure_type": "mri",  # Required
    "urgency_level": "routine"  # Required
}
```

### Issue: Request ID Conflicts
**Symptoms:**
- Duplicate request ID errors
- 409 Conflict responses

**Solutions:**
```python
import uuid
from datetime import datetime

# Generate unique request IDs
def generate_request_id():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    return f"req_{timestamp}_{unique_id}"

# Usage
request_data["request_id"] = generate_request_id()
```

### Issue: Large Clinical Notes
**Symptoms:**
- Request payload too large
- Clinical notes validation errors

**Solutions:**
```python
def truncate_clinical_notes(notes, max_length=10000):
    """Truncate clinical notes to maximum allowed length"""
    if len(notes) <= max_length:
        return notes
    
    # Truncate and add indicator
    truncated = notes[:max_length-50]
    return truncated + "... [Note truncated due to length limit]"

# Usage
request_data["clinical_notes"] = truncate_clinical_notes(long_notes)
```

---

## 📊 Status and Decision Issues

### Issue: Request Status Not Updating
**Symptoms:**
- Status stuck at "submitted"
- No progress updates

**Debugging Steps:**
```bash
# Check request status
curl -X GET "http://127.0.0.1:8000/api/v1/authorization/requests/{request_id}" \
  -H "Authorization: Bearer $TOKEN"

# Check server logs for processing errors
grep "request_id" logs/application.log | tail -20

# Check health status
curl http://127.0.0.1:8000/api/v1/health/detailed
```

### Issue: Decision Not Available
**Symptoms:**
- 404 Not Found when checking decision
- Long processing times

**Solutions:**
```python
import time

def wait_for_decision(client, request_id, timeout_minutes=30):
    """Wait for decision with timeout"""
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60
    
    while time.time() - start_time < timeout_seconds:
        try:
            response = requests.get(
                f"{client.base_url}/decisions/request/{request_id}",
                headers=client.get_headers()
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                print("Decision not ready, waiting...")
                time.sleep(30)
            else:
                print(f"Error: {response.status_code}")
                break
                
        except Exception as e:
            print(f"Error checking decision: {e}")
            time.sleep(30)
    
    print("Timeout waiting for decision")
    return None
```

---

## 🌐 Network and Connectivity Issues

### Issue: Connection Refused
**Symptoms:**
- `Connection refused` errors
- Cannot reach server

**Solutions:**
```bash
# Check if server is running
ps aux | grep "python -m src.main"

# Check port availability
netstat -an | grep 8000

# Test local connectivity
curl -v http://127.0.0.1:8000/api/v1/health

# Check firewall settings (macOS)
sudo pfctl -sr | grep 8000
```

### Issue: Slow Response Times
**Symptoms:**
- Requests taking too long
- Timeout errors

**Solutions:**
```python
# Increase timeout in requests
response = requests.get(
    url,
    headers=headers,
    timeout=60  # Increase from default 30 seconds
)

# Use connection pooling
session = requests.Session()
session.mount('http://', requests.adapters.HTTPAdapter(pool_connections=10))
```

### Issue: SSL/TLS Errors (Production)
**Symptoms:**
- Certificate verification errors
- SSL handshake failures

**Solutions:**
```python
# For development only - disable SSL verification
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

response = requests.get(url, verify=False)

# For production - use proper certificates
response = requests.get(url, verify='/path/to/ca-bundle.crt')
```

---

## 📱 API Integration Issues

### Issue: CORS Errors (Browser)
**Symptoms:**
- `Access-Control-Allow-Origin` errors
- Preflight request failures

**Solutions:**
```javascript
// Ensure proper headers
const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
};

// For development, server should allow localhost origins
// Check server CORS configuration in src/main.py
```

### Issue: Content-Type Errors
**Symptoms:**
- 415 Unsupported Media Type
- Request body parsing errors

**Solutions:**
```bash
# Correct content type for JSON
curl -X POST "http://127.0.0.1:8000/api/v1/authorization/requests" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"request_id": "req_123"}'

# Correct content type for form login
curl -X POST "http://127.0.0.1:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=provider1&password=provider123"
```

---

## 🔍 Debugging Tools and Techniques

### Enable Debug Logging
```bash
# Set debug environment variable
export PA_DEBUG=true
export PA_LOG_LEVEL=DEBUG

# Start server with debug logging
python -m src.main
```

### API Response Debugging
```python
import requests
import json

def debug_api_call(method, url, **kwargs):
    """Debug API calls with detailed logging"""
    print(f"Making {method} request to: {url}")
    print(f"Headers: {kwargs.get('headers', {})}")
    
    if 'json' in kwargs:
        print(f"Request body: {json.dumps(kwargs['json'], indent=2)}")
    
    response = requests.request(method, url, **kwargs)
    
    print(f"Response status: {response.status_code}")
    print(f"Response headers: {dict(response.headers)}")
    
    try:
        response_json = response.json()
        print(f"Response body: {json.dumps(response_json, indent=2)}")
    except:
        print(f"Response text: {response.text}")
    
    return response

# Usage
debug_api_call("POST", "http://127.0.0.1:8000/api/v1/auth/login", 
               data={"username": "provider1", "password": "provider123"})
```

### Health Check Script
```bash
#!/bin/bash

echo "=== Prior Authorization Agent Health Check ==="

# Basic connectivity
echo "1. Testing basic connectivity..."
if curl -s http://127.0.0.1:8000/api/v1/health > /dev/null; then
    echo "✅ Server is responding"
else
    echo "❌ Server is not responding"
    exit 1
fi

# Detailed health
echo "2. Checking detailed health..."
curl -s http://127.0.0.1:8000/api/v1/health/detailed | python -m json.tool

# Authentication test
echo "3. Testing authentication..."
TOKEN=$(curl -s -X POST "http://127.0.0.1:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=provider1&password=provider123" | \
  python -c "import sys, json; print(json.load(sys.stdin).get('access_token', 'ERROR'))")

if [ "$TOKEN" != "ERROR" ]; then
    echo "✅ Authentication working"
else
    echo "❌ Authentication failed"
fi

echo "=== Health check complete ==="
```

---

## 📞 Getting Help

### Log Analysis
```bash
# View recent application logs
tail -f logs/application.log

# Search for specific errors
grep -i "error" logs/application.log | tail -10

# Filter by request ID
grep "req_2024_001234" logs/application.log
```

### Performance Monitoring
```bash
# Monitor system resources
top -p $(pgrep -f "python -m src.main")

# Check memory usage
ps aux | grep "python -m src.main"

# Monitor network connections
netstat -an | grep 8000
```

### Common Error Patterns

| Error Pattern | Likely Cause | Solution |
|---------------|--------------|----------|
| `Connection refused` | Server not running | Start the server |
| `401 Unauthorized` | Invalid/expired token | Re-authenticate |
| `422 Validation Error` | Invalid request data | Check request format |
| `429 Rate Limited` | Too many requests | Implement backoff |
| `500 Internal Error` | Server-side issue | Check server logs |

### Support Checklist

Before seeking help, gather this information:

1. **Environment Details:**
   - Python version: `python --version`
   - OS: `uname -a` (Linux/macOS) or `systeminfo` (Windows)
   - Virtual environment active: `which python`

2. **Error Information:**
   - Exact error message
   - HTTP status code
   - Request that caused the error
   - Server logs around the time of error

3. **Reproduction Steps:**
   - Minimal code to reproduce the issue
   - Sample request data
   - Expected vs actual behavior

4. **System Status:**
   - Health check results
   - Server startup logs
   - Resource usage (CPU, memory)

This troubleshooting guide should help you resolve most common issues with the Prior Authorization Agent system.
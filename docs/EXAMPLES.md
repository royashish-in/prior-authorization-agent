# Prior Authorization Agent - Code Examples

## 📝 Practical Code Examples

This document provides ready-to-use code examples for common tasks with the Prior Authorization Agent.

---

## 🔐 Authentication Examples

### Python - Login and Token Management
```python
import requests
import json
from datetime import datetime, timedelta

class PriorAuthClient:
    def __init__(self, base_url="http://127.0.0.1:8000/api/v1"):
        self.base_url = base_url
        self.token = None
        self.token_expires = None
    
    def login(self, username, password):
        """Login and store token"""
        response = requests.post(
            f"{self.base_url}/auth/login",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"username": username, "password": password}
        )
        
        if response.status_code == 200:
            data = response.json()
            self.token = data["access_token"]
            # Token expires in 24 hours
            self.token_expires = datetime.now() + timedelta(seconds=data["expires_in"])
            return True
        return False
    
    def get_headers(self):
        """Get authorization headers"""
        if not self.token or datetime.now() >= self.token_expires:
            raise Exception("Token expired or not available")
        return {"Authorization": f"Bearer {self.token}"}

# Usage
client = PriorAuthClient()
if client.login("provider1", "provider123"):
    print("Login successful!")
    headers = client.get_headers()
```

### JavaScript - Fetch API Authentication
```javascript
class PriorAuthAPI {
    constructor(baseUrl = 'http://127.0.0.1:8000/api/v1') {
        this.baseUrl = baseUrl;
        this.token = null;
        this.tokenExpires = null;
    }
    
    async login(username, password) {
        const response = await fetch(`${this.baseUrl}/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `username=${username}&password=${password}`
        });
        
        if (response.ok) {
            const data = await response.json();
            this.token = data.access_token;
            this.tokenExpires = new Date(Date.now() + data.expires_in * 1000);
            return true;
        }
        return false;
    }
    
    getHeaders() {
        if (!this.token || new Date() >= this.tokenExpires) {
            throw new Error('Token expired or not available');
        }
        return {
            'Authorization': `Bearer ${this.token}`,
            'Content-Type': 'application/json'
        };
    }
}

// Usage
const api = new PriorAuthAPI();
await api.login('provider1', 'provider123');
```

### cURL - Token Management Script
```bash
#!/bin/bash

# Configuration
BASE_URL="http://127.0.0.1:8000/api/v1"
USERNAME="provider1"
PASSWORD="provider123"

# Function to get token
get_token() {
    curl -s -X POST "$BASE_URL/auth/login" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=$USERNAME&password=$PASSWORD" | \
        python -c "import sys, json; print(json.load(sys.stdin)['access_token'])"
}

# Function to make authenticated requests
auth_request() {
    local method=$1
    local endpoint=$2
    local data=$3
    
    TOKEN=$(get_token)
    
    if [ -n "$data" ]; then
        curl -X "$method" "$BASE_URL$endpoint" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "$data"
    else
        curl -X "$method" "$BASE_URL$endpoint" \
            -H "Authorization: Bearer $TOKEN"
    fi
}

# Usage examples
# auth_request "GET" "/auth/me"
# auth_request "POST" "/authorization/requests" "@request.json"
```

---

## 📝 Authorization Request Examples

### Python - Submit Authorization Request
```python
import requests
import json
from datetime import datetime

def submit_authorization_request(client, request_data):
    """Submit authorization request"""
    response = requests.post(
        f"{client.base_url}/authorization/requests",
        headers=client.get_headers(),
        json=request_data
    )
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code}")
        print(response.json())
        return None

# Sample request data
request_data = {
    "request_id": f"req_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    "provider_id": "prov_12345",
    "patient_demographics": {
        "patient_id": "enc_pat_demo_001",
        "age": 45,
        "gender": "female",
        "insurance_id": "enc_ins_demo_001",
        "member_id": "enc_mem_demo_001"
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
    "clinical_notes": "Patient presents with chronic right shoulder pain lasting 6 months. Conservative treatment with physical therapy has failed. MRI needed to evaluate for rotator cuff tear.",
    "procedure_type": "mri",
    "urgency_level": "routine"
}

# Submit request
result = submit_authorization_request(client, request_data)
if result:
    print(f"Request submitted: {result['request_id']}")
    print(f"Status: {result['status']}")
```

### JavaScript - Submit Request with Error Handling
```javascript
async function submitAuthorizationRequest(api, requestData) {
    try {
        const response = await fetch(`${api.baseUrl}/authorization/requests`, {
            method: 'POST',
            headers: api.getHeaders(),
            body: JSON.stringify(requestData)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            console.log('Request submitted successfully:', result.request_id);
            return result;
        } else {
            console.error('Submission failed:', result);
            return null;
        }
    } catch (error) {
        console.error('Network error:', error);
        return null;
    }
}

// Sample request data
const requestData = {
    request_id: `req_${Date.now()}`,
    provider_id: 'prov_12345',
    patient_demographics: {
        patient_id: 'enc_pat_demo_001',
        age: 45,
        gender: 'female',
        insurance_id: 'enc_ins_demo_001',
        member_id: 'enc_mem_demo_001'
    },
    diagnosis_codes: [{
        code: 'M25.511',
        description: 'Pain in right shoulder',
        category: 'musculoskeletal'
    }],
    procedure_codes: [{
        code: '73221',
        description: 'MRI upper extremity without contrast',
        category: 'radiology'
    }],
    clinical_notes: 'Patient presents with chronic right shoulder pain...',
    procedure_type: 'mri',
    urgency_level: 'routine'
};

// Submit request
const result = await submitAuthorizationRequest(api, requestData);
```

### cURL - Batch Request Submission
```bash
#!/bin/bash

# Submit multiple requests from JSON files
submit_batch_requests() {
    local request_dir=$1
    
    for request_file in "$request_dir"/*.json; do
        echo "Submitting: $request_file"
        
        response=$(auth_request "POST" "/authorization/requests" "@$request_file")
        request_id=$(echo "$response" | python -c "import sys, json; print(json.load(sys.stdin).get('request_id', 'ERROR'))")
        
        echo "Request ID: $request_id"
        echo "---"
    done
}

# Usage
# submit_batch_requests "./sample_requests"
```

---

## 📊 Status Monitoring Examples

### Python - Request Status Polling
```python
import time
import requests

def poll_request_status(client, request_id, max_wait_minutes=30):
    """Poll request status until completion"""
    start_time = time.time()
    max_wait_seconds = max_wait_minutes * 60
    
    while time.time() - start_time < max_wait_seconds:
        response = requests.get(
            f"{client.base_url}/authorization/requests/{request_id}",
            headers=client.get_headers()
        )
        
        if response.status_code == 200:
            status_data = response.json()
            status = status_data['status']
            progress = status_data.get('progress_percentage', 0)
            
            print(f"Status: {status} ({progress}%)")
            
            if status in ['approved', 'denied', 'more_info_needed']:
                return status_data
            
            time.sleep(30)  # Wait 30 seconds before next check
        else:
            print(f"Error checking status: {response.status_code}")
            break
    
    print("Timeout waiting for decision")
    return None

# Usage
final_status = poll_request_status(client, "req_2025_123456")
if final_status:
    print(f"Final status: {final_status['status']}")
```

### JavaScript - Real-time Status Updates
```javascript
class RequestMonitor {
    constructor(api) {
        this.api = api;
        this.activePolls = new Map();
    }
    
    async startMonitoring(requestId, callback, intervalMs = 30000) {
        const poll = async () => {
            try {
                const response = await fetch(
                    `${this.api.baseUrl}/authorization/requests/${requestId}`,
                    { headers: this.api.getHeaders() }
                );
                
                if (response.ok) {
                    const status = await response.json();
                    callback(status);
                    
                    // Stop polling if request is complete
                    if (['approved', 'denied', 'more_info_needed'].includes(status.status)) {
                        this.stopMonitoring(requestId);
                        return;
                    }
                }
            } catch (error) {
                console.error('Polling error:', error);
            }
        };
        
        // Start immediate poll and set interval
        await poll();
        const intervalId = setInterval(poll, intervalMs);
        this.activePolls.set(requestId, intervalId);
    }
    
    stopMonitoring(requestId) {
        const intervalId = this.activePolls.get(requestId);
        if (intervalId) {
            clearInterval(intervalId);
            this.activePolls.delete(requestId);
        }
    }
}

// Usage
const monitor = new RequestMonitor(api);
monitor.startMonitoring('req_2025_123456', (status) => {
    console.log(`Status update: ${status.status} (${status.progress_percentage}%)`);
    
    if (status.status === 'approved') {
        console.log('Authorization approved!');
    }
});
```

---

## 📋 Dashboard Integration Examples

### Python - Provider Dashboard
```python
def get_provider_dashboard(client, provider_id):
    """Get comprehensive provider dashboard data"""
    
    # Get summary
    summary_response = requests.get(
        f"{client.base_url}/dashboard/summary/{provider_id}",
        headers=client.get_headers()
    )
    
    # Get recent requests
    requests_response = requests.get(
        f"{client.base_url}/dashboard/requests/{provider_id}",
        headers=client.get_headers(),
        params={"page_size": 10}
    )
    
    # Get metrics
    metrics_response = requests.get(
        f"{client.base_url}/dashboard/metrics/{provider_id}",
        headers=client.get_headers(),
        params={"time_range": "30d"}
    )
    
    if all(r.status_code == 200 for r in [summary_response, requests_response, metrics_response]):
        return {
            "summary": summary_response.json(),
            "recent_requests": requests_response.json(),
            "metrics": metrics_response.json()
        }
    
    return None

# Usage
dashboard_data = get_provider_dashboard(client, "prov_12345")
if dashboard_data:
    summary = dashboard_data["summary"]
    print(f"Total Requests: {summary['total_requests']}")
    print(f"Approval Rate: {summary['approval_rate_percentage']}%")
    print(f"Pending: {summary['pending_requests']}")
```

### React Component - Dashboard Widget
```jsx
import React, { useState, useEffect } from 'react';

const DashboardWidget = ({ api, providerId }) => {
    const [dashboardData, setDashboardData] = useState(null);
    const [loading, setLoading] = useState(true);
    
    useEffect(() => {
        const fetchDashboardData = async () => {
            try {
                const response = await fetch(
                    `${api.baseUrl}/dashboard/summary/${providerId}`,
                    { headers: api.getHeaders() }
                );
                
                if (response.ok) {
                    const data = await response.json();
                    setDashboardData(data);
                }
            } catch (error) {
                console.error('Dashboard fetch error:', error);
            } finally {
                setLoading(false);
            }
        };
        
        fetchDashboardData();
        
        // Refresh every 5 minutes
        const interval = setInterval(fetchDashboardData, 5 * 60 * 1000);
        return () => clearInterval(interval);
    }, [api, providerId]);
    
    if (loading) return <div>Loading dashboard...</div>;
    if (!dashboardData) return <div>Error loading dashboard</div>;
    
    return (
        <div className="dashboard-widget">
            <h3>Authorization Dashboard</h3>
            <div className="stats-grid">
                <div className="stat">
                    <label>Total Requests</label>
                    <value>{dashboardData.total_requests}</value>
                </div>
                <div className="stat">
                    <label>Approval Rate</label>
                    <value>{dashboardData.approval_rate_percentage}%</value>
                </div>
                <div className="stat">
                    <label>Pending</label>
                    <value>{dashboardData.pending_requests}</value>
                </div>
                <div className="stat">
                    <label>Avg Processing Time</label>
                    <value>{dashboardData.average_processing_time_hours}h</value>
                </div>
            </div>
        </div>
    );
};

export default DashboardWidget;
```

---

## 🎯 Decision Processing Examples

### Python - Decision Retrieval and Processing
```python
def get_authorization_decision(client, request_id):
    """Get authorization decision with full details"""
    response = requests.get(
        f"{client.base_url}/decisions/request/{request_id}",
        headers=client.get_headers()
    )
    
    if response.status_code == 200:
        return response.json()
    elif response.status_code == 404:
        print("Decision not yet available")
        return None
    else:
        print(f"Error retrieving decision: {response.status_code}")
        return None

def process_decision(decision_data):
    """Process authorization decision"""
    if not decision_data:
        return
    
    status = decision_data['status']
    
    if status == 'approved':
        print(f"✅ APPROVED - Auth #: {decision_data['authorization_number']}")
        print(f"Valid until: {decision_data['valid_until']}")
        
    elif status == 'denied':
        print("❌ DENIED")
        print("Reasons:")
        for reason in decision_data['reasoning']:
            print(f"  - {reason}")
            
    elif status == 'more_info_needed':
        print("ℹ️ MORE INFORMATION NEEDED")
        print("Required information:")
        for reason in decision_data['reasoning']:
            print(f"  - {reason}")
    
    print(f"Confidence Score: {decision_data['confidence_score']}")
    print(f"Policy References: {', '.join(decision_data['policy_references'])}")

# Usage
decision = get_authorization_decision(client, "req_2025_123456")
process_decision(decision)
```

---

## 🔄 Error Handling Examples

### Python - Comprehensive Error Handling
```python
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

class PriorAuthError(Exception):
    """Custom exception for Prior Auth API errors"""
    def __init__(self, message, status_code=None, response_data=None):
        self.message = message
        self.status_code = status_code
        self.response_data = response_data
        super().__init__(self.message)

def safe_api_request(client, method, endpoint, **kwargs):
    """Make API request with comprehensive error handling"""
    try:
        response = requests.request(
            method=method,
            url=f"{client.base_url}{endpoint}",
            headers=client.get_headers(),
            timeout=30,
            **kwargs
        )
        
        # Handle different status codes
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            raise PriorAuthError("Authentication failed - token may be expired", 401)
        elif response.status_code == 403:
            raise PriorAuthError("Access forbidden - insufficient permissions", 403)
        elif response.status_code == 404:
            raise PriorAuthError("Resource not found", 404)
        elif response.status_code == 422:
            error_data = response.json()
            raise PriorAuthError(f"Validation error: {error_data.get('message', 'Unknown validation error')}", 422, error_data)
        elif response.status_code == 429:
            raise PriorAuthError("Rate limit exceeded - please wait before retrying", 429)
        else:
            raise PriorAuthError(f"API error: {response.status_code}", response.status_code)
            
    except ConnectionError:
        raise PriorAuthError("Connection error - check if server is running")
    except Timeout:
        raise PriorAuthError("Request timeout - server may be overloaded")
    except RequestException as e:
        raise PriorAuthError(f"Request failed: {str(e)}")

# Usage with retry logic
def submit_request_with_retry(client, request_data, max_retries=3):
    """Submit request with automatic retry on certain errors"""
    for attempt in range(max_retries):
        try:
            return safe_api_request(client, "POST", "/authorization/requests", json=request_data)
        except PriorAuthError as e:
            if e.status_code == 429 and attempt < max_retries - 1:
                print(f"Rate limited, retrying in {2 ** attempt} seconds...")
                time.sleep(2 ** attempt)
                continue
            elif e.status_code == 401 and attempt < max_retries - 1:
                print("Token expired, re-authenticating...")
                client.login("provider1", "provider123")
                continue
            else:
                raise
    
    raise PriorAuthError("Max retries exceeded")
```

---

## 🧪 Testing Examples

### Python - Unit Tests
```python
import unittest
from unittest.mock import Mock, patch
import requests

class TestPriorAuthClient(unittest.TestCase):
    def setUp(self):
        self.client = PriorAuthClient()
        self.client.token = "mock_token"
        self.client.token_expires = datetime.now() + timedelta(hours=1)
    
    @patch('requests.post')
    def test_login_success(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_token",
            "expires_in": 86400
        }
        mock_post.return_value = mock_response
        
        result = self.client.login("test_user", "test_pass")
        
        self.assertTrue(result)
        self.assertEqual(self.client.token, "test_token")
    
    @patch('requests.post')
    def test_submit_request(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "request_id": "req_test_123",
            "status": "submitted"
        }
        mock_post.return_value = mock_response
        
        request_data = {"request_id": "req_test_123", "provider_id": "prov_test"}
        result = submit_authorization_request(self.client, request_data)
        
        self.assertIsNotNone(result)
        self.assertEqual(result["request_id"], "req_test_123")

if __name__ == '__main__':
    unittest.main()
```

### JavaScript - Jest Tests
```javascript
import { PriorAuthAPI } from './prior-auth-api';

describe('PriorAuthAPI', () => {
    let api;
    
    beforeEach(() => {
        api = new PriorAuthAPI();
        global.fetch = jest.fn();
    });
    
    afterEach(() => {
        jest.resetAllMocks();
    });
    
    test('login success', async () => {
        fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({
                access_token: 'test_token',
                expires_in: 86400
            })
        });
        
        const result = await api.login('test_user', 'test_pass');
        
        expect(result).toBe(true);
        expect(api.token).toBe('test_token');
    });
    
    test('submit authorization request', async () => {
        api.token = 'test_token';
        api.tokenExpires = new Date(Date.now() + 3600000);
        
        fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({
                request_id: 'req_test_123',
                status: 'submitted'
            })
        });
        
        const requestData = { request_id: 'req_test_123' };
        const result = await submitAuthorizationRequest(api, requestData);
        
        expect(result).toBeTruthy();
        expect(result.request_id).toBe('req_test_123');
    });
});
```

These examples provide practical, ready-to-use code for integrating with the Prior Authorization Agent system in various programming languages and scenarios.
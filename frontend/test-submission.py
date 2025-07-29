#!/usr/bin/env python3
"""
Test script to verify request submission is working properly.
"""

import requests
import json
import time

API_BASE = "http://127.0.0.1:8000/api/v1"

def test_submission():
    print("🧪 Testing Request Submission")
    print("=" * 40)
    
    # Login
    print("1. Logging in...")
    try:
        response = requests.post(
            f"{API_BASE}/auth/login",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data="username=provider1&password=provider123",
            timeout=10
        )
        token = response.json()["access_token"]
        print("✅ Login successful")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return
    
    # Submit request
    print("\n2. Submitting request...")
    request_data = {
        "request_id": f"req_frontend_test_{int(time.time())}",
        "provider_id": "prov_12345",
        "patient_demographics": {
            "patient_id": f"enc_pat_{int(time.time())}",
            "age": 45,
            "gender": "female",
            "insurance_id": f"enc_ins_{int(time.time())}",
            "member_id": f"enc_mem_{int(time.time())}"
        },
        "diagnosis_codes": [{
            "code": "M25.511",
            "description": "Pain in right shoulder",
            "category": "general"
        }],
        "procedure_codes": [{
            "code": "73221",
            "description": "MRI upper extremity without contrast",
            "category": "radiology"
        }],
        "clinical_notes": "Patient presents with chronic right shoulder pain lasting 6 months. Conservative treatment with physical therapy has failed. MRI needed to evaluate for rotator cuff tear and determine appropriate treatment plan.",
        "procedure_type": "mri",
        "urgency_level": "routine"
    }
    
    try:
        response = requests.post(
            f"{API_BASE}/authorization/requests",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json=request_data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            request_id = result["request_id"]
            print(f"✅ Request submitted successfully: {request_id}")
            
            # Test individual request retrieval
            print(f"\n3. Testing request retrieval...")
            status_response = requests.get(
                f"{API_BASE}/authorization/requests/{request_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                print(f"✅ Request status: {status_data['status']}")
                print(f"   Progress: {status_data.get('progress_percentage', 0)}%")
            else:
                print(f"❌ Status check failed: {status_response.status_code}")
            
        else:
            print(f"❌ Request submission failed: {response.status_code}")
            print(f"   Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Request submission error: {e}")
    
    # Test dashboard endpoints
    print(f"\n4. Testing dashboard endpoints...")
    try:
        dashboard_response = requests.get(
            f"{API_BASE}/dashboard/summary/prov_12345",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if dashboard_response.status_code == 200:
            dashboard_data = dashboard_response.json()
            print(f"✅ Dashboard accessible")
            print(f"   Total requests: {dashboard_data.get('total_requests', 0)}")
        else:
            print(f"⚠️  Dashboard issue: {dashboard_response.status_code}")
            
        requests_response = requests.get(
            f"{API_BASE}/dashboard/requests/prov_12345",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if requests_response.status_code == 200:
            requests_data = requests_response.json()
            print(f"✅ Requests endpoint accessible")
            print(f"   Found requests: {len(requests_data.get('requests', []))}")
        else:
            print(f"⚠️  Requests endpoint issue: {requests_response.status_code}")
            
    except Exception as e:
        print(f"⚠️  Dashboard test error: {e}")
    
    print("\n" + "=" * 40)
    print("✅ Test completed!")
    print("\n💡 Note: If dashboard shows 0 requests but individual")
    print("   request retrieval works, there may be a database")
    print("   query issue in the dashboard endpoints.")

if __name__ == "__main__":
    test_submission()
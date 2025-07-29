#!/usr/bin/env python3
"""
Test script to verify automatic decision generation is working.
"""
import requests
import json
import time

API_BASE = "http://127.0.0.1:8000/api/v1"

def test_automatic_decision():
    print("🧪 Testing Automatic Decision Generation")
    print("=" * 50)
    
    # Login first
    print("1. Logging in...")
    try:
        response = requests.post(
            f"{API_BASE}/auth/login",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data="username=provider1&password=provider123",
            timeout=10
        )
        if response.status_code == 200:
            token = response.json()["access_token"]
            print("✅ Login successful")
        else:
            print(f"❌ Login failed: {response.status_code}")
            return
    except Exception as e:
        print(f"❌ Login error: {e}")
        return
    
    # Submit a test request
    print("\n2. Submitting authorization request...")
    test_request = {
        "provider_id": "prov_12345",
        "patient_demographics": {
            "patient_id": "encrypted_patient_123",
            "age": 45,
            "gender": "female",
            "insurance_id": "encrypted_insurance_456",
            "member_id": "encrypted_member_789"
        },
        "diagnosis_codes": [
            {
                "code": "M25.511",
                "description": "Pain in right shoulder"
            }
        ],
        "procedure_codes": [
            {
                "code": "73221",
                "description": "MRI upper extremity without contrast"
            }
        ],
        "clinical_notes": "Patient presents with chronic right shoulder pain lasting 6 months. Conservative treatment with physical therapy has failed. MRI needed to evaluate for rotator cuff tear.",
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
            json=test_request,
            timeout=30
        )
        
        print(f"Response status: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            request_id = result["request_id"]
            status = result["status"]
            message = result["message"]
            
            print(f"✅ Request submitted successfully!")
            print(f"   Request ID: {request_id}")
            print(f"   Status: {status}")
            print(f"   Message: {message}")
            
            # Check if decision was made automatically
            if status in ["approved", "denied", "more_info_needed"]:
                print(f"🎉 Automatic decision generated: {status.upper()}")
                
                # Try to get the decision details
                print("\n3. Checking decision details...")
                time.sleep(1)
                
                # Check request status
                status_response = requests.get(
                    f"{API_BASE}/authorization/requests/{request_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10
                )
                
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    print(f"   Current status: {status_data.get('status', 'unknown')}")
                    print(f"   Updated at: {status_data.get('updated_at', 'unknown')}")
                else:
                    print(f"⚠️  Could not retrieve status: {status_response.status_code}")
                
            elif status == "in_review":
                print("⚠️  Request marked for manual review (automatic decision failed)")
            else:
                print(f"⚠️  Unexpected status: {status}")
                
        else:
            print(f"❌ Request submission failed: {response.status_code}")
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"❌ Request submission error: {e}")
    
    print("\n" + "=" * 50)
    print("Test completed!")

if __name__ == "__main__":
    test_automatic_decision()
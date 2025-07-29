#!/usr/bin/env python3
"""
Test script to submit a request via frontend and check if decision appears.
"""
import requests
import json
import time

API_BASE = "http://127.0.0.1:8000/api/v1"

def test_frontend_decision():
    print("🧪 Testing Frontend Decision Display")
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
    
    # Submit a test request that should get approved
    print("\n2. Submitting authorization request (should be approved)...")
    approved_request = {
        "provider_id": "prov_12345",
        "patient_demographics": {
            "patient_id": "encrypted_patient_456",
            "age": 35,
            "gender": "male",
            "insurance_id": "encrypted_insurance_789",
            "member_id": "encrypted_member_012"
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
        "clinical_notes": "Patient sustained shoulder injury during sports activity. Physical examination reveals limited range of motion and pain. MRI needed to assess for rotator cuff tear and other soft tissue injuries. Conservative treatment with rest and physical therapy for 4 weeks has not provided adequate improvement.",
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
            json=approved_request,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            request_id = result["request_id"]
            status = result["status"]
            
            print(f"✅ Request submitted successfully!")
            print(f"   Request ID: {request_id}")
            print(f"   Status: {status}")
            
            # Wait a moment for processing
            time.sleep(2)
            
            # Check dashboard to see if request appears
            print("\n3. Checking dashboard for the request...")
            dashboard_response = requests.get(
                f"{API_BASE}/dashboard/requests/prov_12345",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )
            
            if dashboard_response.status_code == 200:
                dashboard_data = dashboard_response.json()
                requests_list = dashboard_data.get('requests', [])
                
                # Find our request
                our_request = None
                for req in requests_list:
                    if req['request_id'] == request_id:
                        our_request = req
                        break
                
                if our_request:
                    print(f"✅ Request found in dashboard!")
                    print(f"   Status: {our_request['status']}")
                    print(f"   Submitted: {our_request['submitted_at']}")
                    print(f"   Updated: {our_request['updated_at']}")
                    
                    if our_request['status'] in ['approved', 'denied']:
                        print(f"🎉 Decision made: {our_request['status'].upper()}")
                        
                        # Try to get decision details
                        print("\n4. Checking for decision details...")
                        decisions_response = requests.get(
                            f"{API_BASE}/decisions/by-request/{request_id}",
                            headers={"Authorization": f"Bearer {token}"},
                            timeout=10
                        )
                        
                        if decisions_response.status_code == 200:
                            decision_data = decisions_response.json()
                            print(f"✅ Decision details found!")
                            print(f"   Decision ID: {decision_data.get('decision_id', 'N/A')}")
                            print(f"   Status: {decision_data.get('status', 'N/A')}")
                            print(f"   Reasoning: {decision_data.get('reasoning', 'N/A')}")
                            print(f"   Confidence: {decision_data.get('confidence_score', 'N/A')}")
                        else:
                            print(f"⚠️  Could not get decision details: {decisions_response.status_code}")
                    else:
                        print(f"⚠️  Request still pending: {our_request['status']}")
                else:
                    print("❌ Request not found in dashboard")
            else:
                print(f"❌ Could not get dashboard: {dashboard_response.status_code}")
                
        else:
            print(f"❌ Request submission failed: {response.status_code}")
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"❌ Request submission error: {e}")
    
    print("\n" + "=" * 50)
    print("✅ Frontend decision test completed!")
    print("\n📱 To see in browser:")
    print("   1. Open http://localhost:8080/simple-dashboard.html")
    print("   2. Login as provider1/provider123")
    print("   3. Check 'My Requests' tab for submitted requests")
    print("   4. Check 'Recent Decisions' tab for decision details")

if __name__ == "__main__":
    test_frontend_decision()
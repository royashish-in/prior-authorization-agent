#!/usr/bin/env python3
"""
Test script to check if decisions can be retrieved properly.
"""
import requests
import json

API_BASE = "http://127.0.0.1:8000/api/v1"

def test_decision_retrieval():
    print("🧪 Testing Decision Retrieval")
    print("=" * 40)
    
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
    
    # Get the latest request ID
    print("\n2. Getting latest request...")
    try:
        response = requests.get(
            f"{API_BASE}/authorization/requests?provider_id=prov_12345",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            requests_list = data.get('requests', [])
            
            if requests_list:
                latest_request = requests_list[0]  # Should be sorted by newest first
                request_id = latest_request['request_id']
                status = latest_request['status']
                
                print(f"✅ Found latest request: {request_id} (status: {status})")
                
                # Try to get decision for this request
                print(f"\n3. Getting decision for request {request_id}...")
                
                decision_response = requests.get(
                    f"{API_BASE}/decisions/by-request/{request_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10
                )
                
                print(f"Decision API status: {decision_response.status_code}")
                if decision_response.status_code == 200:
                    decision_data = decision_response.json()
                    print(f"✅ Decision found!")
                    print(f"   Decision ID: {decision_data.get('decision_id', 'N/A')}")
                    print(f"   Status: {decision_data.get('status', 'N/A')}")
                    print(f"   Reasoning: {decision_data.get('reasoning', 'N/A')}")
                    print(f"   Confidence: {decision_data.get('confidence_score', 'N/A')}")
                    print(f"   Decided at: {decision_data.get('decided_at', 'N/A')}")
                else:
                    print(f"⚠️  Decision not found: {decision_response.text}")
                    
                    # Try the decisions list endpoint
                    print(f"\n4. Trying decisions list endpoint...")
                    decisions_response = requests.get(
                        f"{API_BASE}/decisions",
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=10
                    )
                    
                    print(f"Decisions list status: {decisions_response.status_code}")
                    if decisions_response.status_code == 200:
                        decisions_data = decisions_response.json()
                        print(f"Decisions response: {json.dumps(decisions_data, indent=2)}")
                    else:
                        print(f"Decisions list failed: {decisions_response.text}")
                
            else:
                print("❌ No requests found")
        else:
            print(f"❌ Failed to get requests: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_decision_retrieval()
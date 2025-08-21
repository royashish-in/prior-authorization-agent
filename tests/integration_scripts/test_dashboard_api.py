#!/usr/bin/env python3
"""
Test script to check if the dashboard API is returning the submitted requests.
"""
import requests
import json

API_BASE = "http://127.0.0.1:8000/api/v1"

def test_dashboard_api():
    print("🧪 Testing Dashboard API")
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
    
    # Test dashboard requests endpoint
    print("\n2. Testing dashboard requests endpoint...")
    try:
        response = requests.get(
            f"{API_BASE}/dashboard/requests/prov_12345",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            
            requests_list = data.get('requests', [])
            print(f"\n✅ Found {len(requests_list)} requests")
            
            for req in requests_list:
                print(f"   - {req['request_id']}: {req['status']} (submitted: {req['submitted_at']})")
        else:
            print(f"❌ Dashboard API failed: {response.text}")
            
    except Exception as e:
        print(f"❌ Dashboard API error: {e}")
    
    # Test intake requests endpoint
    print("\n3. Testing intake requests endpoint...")
    try:
        response = requests.get(
            f"{API_BASE}/authorization/requests?provider_id=prov_12345",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            
            requests_list = data.get('requests', [])
            print(f"\n✅ Found {len(requests_list)} requests via intake API")
            
            for req in requests_list:
                print(f"   - {req['request_id']}: {req['status']} (submitted: {req['submitted_at']})")
        else:
            print(f"❌ Intake API failed: {response.text}")
            
    except Exception as e:
        print(f"❌ Intake API error: {e}")

if __name__ == "__main__":
    test_dashboard_api()
#!/usr/bin/env python3
"""
Quick test to verify the Prior Authorization Agent is working end-to-end.
"""

import requests
import json
import time

API_BASE = "http://127.0.0.1:8000/api/v1"


def main():
    print("🧪 Quick End-to-End Test")
    print("=" * 40)

    # Step 1: Login
    print("1. Testing login...")
    try:
        response = requests.post(
            f"{API_BASE}/auth/login",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data="username=provider1&password=provider123",
            timeout=10,
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

    # Step 2: Submit request
    print("\n2. Testing request submission...")
    request_data = {
        "request_id": f"req_test_{int(time.time())}",
        "provider_id": "prov_12345",
        "patient_demographics": {
            "patient_id": f"enc_pat_{int(time.time())}",
            "age": 45,
            "gender": "female",
            "insurance_id": f"enc_ins_{int(time.time())}",
            "member_id": f"enc_mem_{int(time.time())}",
        },
        "diagnosis_codes": [
            {
                "code": "M25.511",
                "description": "Pain in right shoulder",
                "category": "general",
            }
        ],
        "procedure_codes": [
            {
                "code": "73221",
                "description": "MRI upper extremity without contrast",
                "category": "radiology",
            }
        ],
        "clinical_notes": "Patient presents with chronic right shoulder pain lasting 6 months. Conservative treatment with physical therapy has failed. MRI needed to evaluate for rotator cuff tear and determine appropriate treatment plan.",
        "procedure_type": "mri",
        "urgency_level": "routine",
    }

    try:
        response = requests.post(
            f"{API_BASE}/authorization/requests",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=request_data,
            timeout=30,
        )

        if response.status_code == 200:
            result = response.json()
            request_id = result["request_id"]
            print(f"✅ Request submitted: {request_id}")
        else:
            print(f"❌ Request failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return
    except Exception as e:
        print(f"❌ Request error: {e}")
        return

    # Step 3: Check status
    print("\n3. Testing status check...")
    try:
        response = requests.get(
            f"{API_BASE}/authorization/requests/{request_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )

        if response.status_code == 200:
            status = response.json()
            print(f"✅ Status retrieved: {status['status']}")
            print(f"   Progress: {status.get('progress_percentage', 0)}%")
        else:
            print(f"❌ Status check failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Status error: {e}")

    print("\n" + "=" * 40)
    print("✅ End-to-end test completed!")
    print("\n🌐 Frontend is available at:")
    print("   http://localhost:8080/simple-dashboard.html")
    print("\n📝 Login with:")
    print("   Username: provider1")
    print("   Password: provider123")


if __name__ == "__main__":
    main()

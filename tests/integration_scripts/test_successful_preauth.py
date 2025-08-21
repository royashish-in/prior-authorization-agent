#!/usr/bin/env python3
"""
Test script with values that should result in successful pre-authorization approval.
"""
import requests
import json
import time

API_BASE = "http://127.0.0.1:8000/api/v1"


def test_successful_preauth():
    print("🧪 Testing Successful Pre-Authorization")
    print("=" * 50)

    # Login first
    print("1. Logging in...")
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

    # Submit a request that should get APPROVED
    print("\n2. Submitting request that should be APPROVED...")

    # These specific values are designed to trigger approval in the mock policy service
    approved_request = {
        "provider_id": "prov_12345",
        "patient_demographics": {
            "patient_id": "encrypted_patient_approved_001",
            "age": 45,
            "gender": "female",
            "insurance_id": "encrypted_insurance_approved_001",
            "member_id": "encrypted_member_approved_001",
        },
        "diagnosis_codes": [
            {
                "code": "M25.511",  # Pain in right shoulder - this triggers approval
                "description": "Pain in right shoulder",
            }
        ],
        "procedure_codes": [
            {
                "code": "73221",  # MRI upper extremity - this is in the approved list
                "description": "MRI upper extremity without contrast",
            }
        ],
        "clinical_notes": "Patient presents with chronic right shoulder pain lasting 6 months. Conservative treatment with physical therapy and NSAIDs has been attempted for 8 weeks without significant improvement. Physical examination reveals limited range of motion and positive impingement signs. MRI is needed to evaluate for rotator cuff tear and guide treatment planning. Patient has documented failed conservative therapy and meets medical necessity criteria for advanced imaging.",
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
            json=approved_request,
            timeout=30,
        )

        print(f"Response status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            request_id = result["request_id"]
            status = result["status"]
            message = result["message"]

            print(f"✅ Request submitted successfully!")
            print(f"   Request ID: {request_id}")
            print(f"   Status: {status}")
            print(f"   Message: {message}")

            if status == "approved":
                print(f"🎉 SUCCESS! Request was APPROVED!")

                # Get the decision details
                print("\n3. Getting approval details...")
                time.sleep(1)

                decision_response = requests.get(
                    f"{API_BASE}/decisions/by-request/{request_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )

                if decision_response.status_code == 200:
                    decision_data = decision_response.json()
                    print(f"✅ Approval details:")
                    print(f"   Decision ID: {decision_data.get('decision_id', 'N/A')}")
                    print(f"   Status: {decision_data.get('status', 'N/A')}")
                    print(
                        f"   Authorization Number: {decision_data.get('authorization_number', 'N/A')}"
                    )
                    print(f"   Valid Until: {decision_data.get('valid_until', 'N/A')}")
                    print(f"   Reasoning:")
                    reasoning = decision_data.get("reasoning", [])
                    if isinstance(reasoning, list):
                        for reason in reasoning:
                            print(f"     • {reason}")
                    else:
                        print(f"     • {reasoning}")
                    print(
                        f"   Confidence: {decision_data.get('confidence_score', 'N/A')}"
                    )
                else:
                    print(
                        f"⚠️  Could not get decision details: {decision_response.status_code}"
                    )
            else:
                print(f"⚠️  Request was not approved. Status: {status}")
                print("   This might indicate the approval logic needs adjustment.")

        else:
            print(f"❌ Request submission failed: {response.status_code}")
            print(f"Error: {response.text}")

    except Exception as e:
        print(f"❌ Request submission error: {e}")

    print("\n" + "=" * 50)
    print("✅ Test completed!")

    print("\n📋 VALUES THAT SHOULD GET APPROVED:")
    print("   Diagnosis Code: M25.511 (Pain in right shoulder)")
    print("   Procedure Code: 73221 (MRI upper extremity)")
    print("   Patient Age: 45")
    print("   Clinical Notes: Must document failed conservative treatment")
    print("   Procedure Type: mri")
    print("   Urgency Level: routine")


if __name__ == "__main__":
    test_successful_preauth()

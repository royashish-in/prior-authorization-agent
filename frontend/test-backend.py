#!/usr/bin/env python3
"""
Test script to verify the Prior Authorization Agent backend is working.
Run this before using the frontend to ensure everything is set up correctly.
"""

import requests
import json
import sys

API_BASE = "http://127.0.0.1:8000/api/v1"

def test_health():
    """Test basic health endpoint"""
    print("🔍 Testing health endpoint...")
    try:
        response = requests.get(f"{API_BASE}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Health check passed: {data['status']}")
            return True
        else:
            print(f"❌ Health check failed: HTTP {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to backend server")
        print("   Make sure the server is running: python -m src.main")
        return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False

def test_login():
    """Test authentication endpoint"""
    print("\n🔐 Testing authentication...")
    try:
        response = requests.post(
            f"{API_BASE}/auth/login",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data="username=provider1&password=provider123",
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Authentication successful")
            print(f"   Token type: {data['token_type']}")
            print(f"   Expires in: {data['expires_in']} seconds")
            return data['access_token']
        else:
            print(f"❌ Authentication failed: HTTP {response.status_code}")
            print(f"   Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Authentication error: {e}")
        return None

def test_user_info(token):
    """Test user info endpoint"""
    print("\n👤 Testing user info...")
    try:
        response = requests.get(
            f"{API_BASE}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✅ User info retrieved successfully")
            print(f"   User: {data.get('username', 'Unknown')}")
            print(f"   Role: {', '.join(data.get('roles', []))}")
            print(f"   Organization: {data.get('organization_id', 'Unknown')}")
            return True
        else:
            print(f"❌ User info failed: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ User info error: {e}")
        return False

def test_cors():
    """Test CORS configuration"""
    print("\n🌐 Testing CORS configuration...")
    try:
        # Make an OPTIONS request to check CORS
        response = requests.options(
            f"{API_BASE}/auth/login",
            headers={
                "Origin": "http://localhost:8080",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type"
            },
            timeout=5
        )
        
        cors_headers = {
            'Access-Control-Allow-Origin': response.headers.get('Access-Control-Allow-Origin'),
            'Access-Control-Allow-Methods': response.headers.get('Access-Control-Allow-Methods'),
            'Access-Control-Allow-Headers': response.headers.get('Access-Control-Allow-Headers'),
        }
        
        if any(cors_headers.values()):
            print("✅ CORS is configured")
            for header, value in cors_headers.items():
                if value:
                    print(f"   {header}: {value}")
        else:
            print("⚠️  CORS headers not found - may cause frontend issues")
            
    except Exception as e:
        print(f"⚠️  CORS test error: {e}")

def main():
    print("🧪 Prior Authorization Agent - Backend Test")
    print("=" * 50)
    
    # Test health
    if not test_health():
        print("\n❌ Backend server is not running or not healthy")
        print("\nTo start the backend:")
        print("1. cd to project directory")
        print("2. source venv/bin/activate")
        print("3. python -m src.main")
        sys.exit(1)
    
    # Test authentication
    token = test_login()
    if not token:
        print("\n❌ Authentication is not working")
        sys.exit(1)
    
    # Test user info
    if not test_user_info(token):
        print("\n❌ User info endpoint is not working")
        sys.exit(1)
    
    # Test CORS
    test_cors()
    
    print("\n" + "=" * 50)
    print("✅ All backend tests passed!")
    print("\n🚀 You can now use the frontend:")
    print("   python frontend/serve.py")
    print("   Then open: http://localhost:8080/simple-dashboard.html")
    print("\n📚 Or open the HTML file directly in your browser:")
    print("   frontend/simple-dashboard.html")

if __name__ == "__main__":
    main()
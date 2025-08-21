"""
Test configuration settings and constants.
"""

import os
from typing import Dict, Any

# Test environment configuration
TEST_CONFIG = {
    "database": {
        "url": "sqlite:///:memory:",
        "echo": False,
        "pool_pre_ping": True
    },
    "redis": {
        "url": "redis://localhost:6379/1",
        "decode_responses": True
    },
    "external_services": {
        "cms_api": {
            "base_url": "https://api.cms.gov/test",
            "timeout": 30,
            "retry_attempts": 3
        },
        "medical_codes_api": {
            "base_url": "https://api.medicalcodes.com/test",
            "timeout": 15,
            "retry_attempts": 2
        }
    },
    "performance": {
        "max_response_time": 2.0,  # seconds
        "concurrent_requests": 100,
        "load_test_duration": 30  # seconds
    },
    "security": {
        "test_encryption_key": "test-encryption-key-32-chars-long",
        "test_phi_key": "test-phi-master-key-for-testing-purposes-2024",
        "test_secret_key": "test-secret-key-for-testing-12345678901234567890"
    }
}

# Environment-specific overrides
if os.getenv("CI"):
    # CI/CD environment adjustments
    TEST_CONFIG["performance"]["concurrent_requests"] = 50
    TEST_CONFIG["performance"]["load_test_duration"] = 15

def get_test_config() -> Dict[str, Any]:
    """Get the current test configuration."""
    return TEST_CONFIG.copy()

def get_database_url() -> str:
    """Get the test database URL."""
    return TEST_CONFIG["database"]["url"]

def get_redis_url() -> str:
    """Get the test Redis URL."""
    return TEST_CONFIG["redis"]["url"]
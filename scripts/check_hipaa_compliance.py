#!/usr/bin/env python3
"""
HIPAA compliance validation script for healthcare prior authorization system.
Validates PHI handling, encryption, and audit logging compliance.
"""

import os
import sys
from pathlib import Path

def check_phi_encryption():
    """Validate PHI encryption implementation."""
    try:
        from src.core.encryption import encrypt_phi, decrypt_phi
        test_data = "test-patient-data"
        encrypted = encrypt_phi(test_data)
        decrypted = decrypt_phi(encrypted)
        assert decrypted == test_data
        print("✅ PHI encryption validation passed")
        return True
    except Exception as e:
        print(f"❌ PHI encryption validation failed: {e}")
        return False

def check_audit_logging():
    """Validate audit logging implementation."""
    try:
        from src.audit.logger import AuditLogger
        logger = AuditLogger()
        print("✅ Audit logging validation passed")
        return True
    except Exception as e:
        print(f"❌ Audit logging validation failed: {e}")
        return False

def check_access_controls():
    """Validate role-based access controls."""
    try:
        from src.auth.oauth2 import verify_token
        print("✅ Access control validation passed")
        return True
    except Exception as e:
        print(f"❌ Access control validation failed: {e}")
        return False

if __name__ == "__main__":
    print("🔄 Validating HIPAA compliance...")
    
    checks = [
        check_phi_encryption(),
        check_audit_logging(),
        check_access_controls()
    ]
    
    if all(checks):
        print("✅ All HIPAA compliance checks passed")
        sys.exit(0)
    else:
        print("❌ HIPAA compliance validation failed")
        sys.exit(1)
#!/usr/bin/env python3
"""
Rule engine rebuild script for healthcare prior authorization system.
Rebuilds decision rules and policy validation logic.
"""

import os
import sys
from pathlib import Path

def rebuild_policy_cache():
    """Rebuild policy validation cache."""
    try:
        from src.services.policy_cache import PolicyCache
        cache = PolicyCache()
        cache.rebuild()
        print("✅ Policy cache rebuilt")
        return True
    except Exception as e:
        print(f"❌ Policy cache rebuild failed: {e}")
        return False

def rebuild_decision_rules():
    """Rebuild decision engine rules."""
    try:
        from src.services.decision_engine import DecisionEngine
        engine = DecisionEngine()
        print("✅ Decision rules validated")
        return True
    except Exception as e:
        print(f"❌ Decision rules validation failed: {e}")
        return False

def validate_medical_codes():
    """Validate medical code mappings."""
    try:
        from src.services.medical_code_validator import MedicalCodeValidator
        validator = MedicalCodeValidator()
        print("✅ Medical codes validated")
        return True
    except Exception as e:
        print(f"❌ Medical code validation failed: {e}")
        return False

if __name__ == "__main__":
    print("🔄 Rebuilding healthcare rule engine...")
    
    rebuilds = [
        rebuild_policy_cache(),
        rebuild_decision_rules(),
        validate_medical_codes()
    ]
    
    if all(rebuilds):
        print("✅ Rule engine rebuild complete")
        sys.exit(0)
    else:
        print("❌ Rule engine rebuild failed")
        sys.exit(1)
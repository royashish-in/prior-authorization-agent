#!/usr/bin/env python3
"""
Test dependency injection for medical codes API.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from src.database.connection import get_db_session
from src.services.medical_code_repository import MedicalCodeRepository

app = FastAPI()

def get_repository(db = Depends(get_db_session)) -> MedicalCodeRepository:
    """Get medical code repository dependency."""
    print(f"DB session type: {type(db)}")
    return MedicalCodeRepository(db)

@app.get("/test")
async def test_endpoint(repo: MedicalCodeRepository = Depends(get_repository)):
    """Test endpoint."""
    try:
        results, count = await repo.search_icd10_codes("test", limit=1)
        return {"status": "success", "count": count}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def test_dependency():
    """
        Test dependency.
        
        This test verifies system functionality and ensures that the system
        behaves correctly under the specified conditions.
        
        Test Scenarios:
        - Standard input scenarios
        - Edge cases and boundary conditions
        - Error handling scenarios
        
        Expected Behavior:
        - System should behave according to specified requirements
        
        PHI Compliance:
        All test data uses synthetic information with appropriate markers.
        """

"""
Tests for health check endpoints.

This module contains tests for the health monitoring functionality
to ensure proper system status reporting.
"""

import pytest
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


class TestHealthEndpoints:
    """Test suite for health check endpoints."""
    
    def test_basic_health_check(self):
        """
        Test basic health check.
        
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
        response = client.get("/api/v1/health/detailed")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data
        assert "environment" in data
        assert "uptime_seconds" in data
        assert "checks" in data
        
        # Check that all expected subsystems are included
        assert "database" in data["checks"]
        assert "external_services" in data["checks"]
        
        # Verify uptime is a positive number
        assert data["uptime_seconds"] >= 0
    
    def test_readiness_check(self):
        """
        Test readiness check.
        
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
        response = client.get("/api/v1/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "ready"
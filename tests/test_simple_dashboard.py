"""
Simple test for dashboard functionality.
"""

import pytest


def test_simple():
    """Simple test to verify pytest works."""
    assert True


class TestSimpleDashboard:
    """Simple dashboard test class."""
    
    def test_dashboard_exists(self):
        """Test that dashboard module can be imported."""
        from src.api.dashboard import router
        assert router is not None
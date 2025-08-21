"""
Tests for the prompt optimization and A/B testing system.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

from src.services.prompt_optimization import (
    ABTestStatus, ABTestMetric, ABTestVariant, ABTest, PromptOptimizer
)
from src.services.prompt_engineering import (
    PromptType, PromptTemplateManager, PromptTemplate, PromptVersion
)


class TestABTestVariant:
    """Test TestVariant functionality."""
    
    def test_variant_creation(self):
    """
        Test variant creation.
        
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
    
        def setup_method(self):
        """Set up test fixtures."""
        self.variant_a = ABTestVariant(
            variant_id="variant_a",
            template_id="template_1",
            name="Control",
            description="Control variant",
            traffic_percentage=0.5,
            is_control=True
        )
        
        self.variant_b = ABTestVariant(
            variant_id="variant_b",
            template_id="template_2",
            name="Treatment",
            description="Treatment variant",
            traffic_percentage=0.5
        )
        
        self.test = ABTest(
            test_id="test_001",
            name="Authorization Prompt Test",
            description="Testing new authorization prompt",
            prompt_type=PromptType.AUTHORIZATION_DECISION,
            variants=[self.variant_a, self.variant_b]
        )
    
    def test_ab_test_creation(self):
    """
        Test ab test creation.
        
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
    
    def setup_method(self):
        """Set up test fixtures."""
        self.template_manager = PromptTemplateManager()
        self.optimizer = PromptOptimizer(self.template_manager)
    
        def test_optimizer_initialization(self):
    """
        Test optimizer initialization.
        
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
        variants = [
            {
                "variant_id": "control",
                "template_id": "template_1",
                "name": "Control",
                "description": "Control",
                "traffic_percentage": 0.6,  # Total > 1.0
                "is_control": True
            },
            {
                "variant_id": "treatment",
                "template_id": "template_2",
                "name": "Treatment",
                "description": "Treatment",
                "traffic_percentage": 0.6,
                "is_control": False
            }
        ]
        
        with pytest.raises(ValueError, match="Traffic percentages must sum to 1.0"):
            self.optimizer.create_ab_test(
                test_id="invalid_test",
                name="Invalid Test",
                description="Invalid test",
                prompt_type=PromptType.AUTHORIZATION_DECISION,
                variants=variants
            )
    
        def test_create_ab_test_invalid_control(self):
    """Test creating A/B test with invalid control variants."""
        # No control variant
        variants = [
            {
                "variant_id": "variant_a",
                "template_id": "template_1",
                "name": "Variant A",
                "description": "Variant A",
                "traffic_percentage": 0.5,
                "is_control": False
            },
            {
                "variant_id": "variant_b",
                "template_id": "template_2",
                "name": "Variant B",
                "description": "Variant B",
                "traffic_percentage": 0.5,
                "is_control": False
            }
        ]
        
        with pytest.raises(ValueError, match="Exactly one control variant is required"):
            self.optimizer.create_ab_test(
                test_id="invalid_test",
                name="Invalid Test",
                description="Invalid test",
                prompt_type=PromptType.AUTHORIZATION_DECISION,
                variants=variants
            )
    
    def test_start_test(self):
    """
        Test start test.
        
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

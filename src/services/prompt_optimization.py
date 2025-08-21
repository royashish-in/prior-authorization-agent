"""
Prompt Optimization System with A/B Testing

This module provides A/B testing capabilities for prompt templates
and optimization based on performance metrics.
"""

import json
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import logging
import asyncio
from collections import defaultdict

from .prompt_engineering import PromptTemplate, PromptType, PromptVersion, PromptTemplateManager

logger = logging.getLogger(__name__)


class ABTestStatus(str, Enum):
    """A/B test status."""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ABTestMetric(str, Enum):
    """Metrics for A/B test evaluation."""
    SUCCESS_RATE = "success_rate"
    CONFIDENCE_SCORE = "confidence_score"
    RESPONSE_TIME = "response_time"
    USER_SATISFACTION = "user_satisfaction"
    CLINICAL_ACCURACY = "clinical_accuracy"


@dataclass
class ABTestVariant:
    """A/B test variant configuration."""
    variant_id: str
    template_id: str
    name: str
    description: str
    traffic_percentage: float  # 0.0 to 1.0
    is_control: bool = False
    
    # Performance metrics
    total_requests: int = 0
    successful_requests: int = 0
    total_confidence: float = 0.0
    total_response_time: float = 0.0
    user_ratings: List[float] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests
    
    @property
    def avg_confidence(self) -> float:
        """Calculate average confidence score."""
        if self.total_requests == 0:
            return 0.0
        return self.total_confidence / self.total_requests
    
    @property
    def avg_response_time(self) -> float:
        """Calculate average response time."""
        if self.total_requests == 0:
            return 0.0
        return self.total_response_time / self.total_requests
    
    @property
    def avg_user_rating(self) -> float:
        """Calculate average user rating."""
        if not self.user_ratings:
            return 0.0
        return sum(self.user_ratings) / len(self.user_ratings)


@dataclass
class ABTest:
    """A/B test configuration and results."""
    test_id: str
    name: str
    description: str
    prompt_type: PromptType
    variants: List[ABTestVariant]
    status: ABTestStatus = ABTestStatus.DRAFT
    
    # Test configuration
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    min_sample_size: int = 100
    confidence_level: float = 0.95
    primary_metric: ABTestMetric = ABTestMetric.SUCCESS_RATE
    
    # Test results
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    winner_variant_id: Optional[str] = None
    statistical_significance: Optional[float] = None
    
    def get_variant_by_id(self, variant_id: str) -> Optional[ABTestVariant]:
        """Get variant by ID."""
        return next((v for v in self.variants if v.variant_id == variant_id), None)
    
    def get_control_variant(self) -> Optional[ABTestVariant]:
        """Get the control variant."""
        return next((v for v in self.variants if v.is_control), None)
    
    def is_active(self) -> bool:
        """Check if test is currently active."""
        if self.status != ABTestStatus.ACTIVE:
            return False
        
        now = datetime.now(timezone.utc)
        if self.start_date and now < self.start_date:
            return False
        
        if self.end_date and now > self.end_date:
            return False
        
        return True
    
    def has_sufficient_data(self) -> bool:
        """Check if test has sufficient data for analysis."""
        return all(v.total_requests >= self.min_sample_size for v in self.variants)


class PromptOptimizer:
    """Manages A/B testing and optimization of prompt templates."""
    
    def __init__(self, template_manager: PromptTemplateManager):
        self.template_manager = template_manager
        self._active_tests: Dict[str, ABTest] = {}
        self._test_history: List[ABTest] = []
        self._variant_assignments: Dict[str, str] = {}  # request_id -> variant_id
    
    def create_ab_test(
        self,
        test_id: str,
        name: str,
        description: str,
        prompt_type: PromptType,
        variants: List[Dict[str, Any]],
        duration_days: int = 30,
        min_sample_size: int = 100,
        primary_metric: ABTestMetric = ABTestMetric.SUCCESS_RATE
    ) -> ABTest:
        """Create a new A/B test."""
        
        # Validate traffic percentages sum to 1.0
        total_traffic = sum(v.get('traffic_percentage', 0) for v in variants)
        if abs(total_traffic - 1.0) > 0.01:
            raise ValueError("Traffic percentages must sum to 1.0")
        
        # Create test variants
        test_variants = []
        for variant_data in variants:
            variant = ABTestVariant(
                variant_id=variant_data['variant_id'],
                template_id=variant_data['template_id'],
                name=variant_data['name'],
                description=variant_data['description'],
                traffic_percentage=variant_data['traffic_percentage'],
                is_control=variant_data.get('is_control', False)
            )
            test_variants.append(variant)
        
        # Ensure exactly one control variant
        control_variants = [v for v in test_variants if v.is_control]
        if len(control_variants) != 1:
            raise ValueError("Exactly one control variant is required")
        
        # Create test
        test = ABTest(
            test_id=test_id,
            name=name,
            description=description,
            prompt_type=prompt_type,
            variants=test_variants,
            min_sample_size=min_sample_size,
            primary_metric=primary_metric,
            end_date=datetime.now(timezone.utc) + timedelta(days=duration_days)
        )
        
        self._active_tests[test_id] = test
        logger.info(f"Created A/B test: {test_id}")
        
        return test
    
    def start_test(self, test_id: str) -> bool:
        """Start an A/B test."""
        if test_id not in self._active_tests:
            logger.error(f"Test not found: {test_id}")
            return False
        
        test = self._active_tests[test_id]
        if test.status != ABTestStatus.DRAFT:
            logger.error(f"Test {test_id} cannot be started from status {test.status}")
            return False
        
        test.status = ABTestStatus.ACTIVE
        test.start_date = datetime.now(timezone.utc)
        test.updated_at = datetime.now(timezone.utc)
        
        logger.info(f"Started A/B test: {test_id}")
        return True
    
    def pause_test(self, test_id: str) -> bool:
        """Pause an active A/B test."""
        if test_id not in self._active_tests:
            return False
        
        test = self._active_tests[test_id]
        if test.status == ABTestStatus.ACTIVE:
            test.status = ABTestStatus.PAUSED
            test.updated_at = datetime.now(timezone.utc)
            logger.info(f"Paused A/B test: {test_id}")
            return True
        
        return False
    
    def resume_test(self, test_id: str) -> bool:
        """Resume a paused A/B test."""
        if test_id not in self._active_tests:
            return False
        
        test = self._active_tests[test_id]
        if test.status == ABTestStatus.PAUSED:
            test.status = ABTestStatus.ACTIVE
            test.updated_at = datetime.now(timezone.utc)
            logger.info(f"Resumed A/B test: {test_id}")
            return True
        
        return False
    
    def get_variant_for_request(self, request_id: str, prompt_type: PromptType) -> Optional[str]:
        """Get the variant template ID for a specific request."""
        
        # Find active test for this prompt type
        active_test = None
        for test in self._active_tests.values():
            if test.prompt_type == prompt_type and test.is_active():
                active_test = test
                break
        
        if not active_test:
            # No active test, return default template
            templates = self.template_manager.get_templates_by_type(prompt_type)
            if templates:
                return templates[0].template_id
            return None
        
        # Check if request already has variant assignment
        if request_id in self._variant_assignments:
            variant_id = self._variant_assignments[request_id]
            variant = active_test.get_variant_by_id(variant_id)
            if variant:
                return variant.template_id
        
        # Assign new variant based on traffic allocation
        variant = self._assign_variant(active_test)
        if variant:
            self._variant_assignments[request_id] = variant.variant_id
            return variant.template_id
        
        return None
    
    def _assign_variant(self, test: ABTest) -> Optional[ABTestVariant]:
        """Assign a variant based on traffic allocation."""
        rand_value = random.random()
        cumulative_percentage = 0.0
        
        for variant in test.variants:
            cumulative_percentage += variant.traffic_percentage
            if rand_value <= cumulative_percentage:
                return variant
        
        # Fallback to first variant
        return test.variants[0] if test.variants else None
    
    def record_result(
        self,
        request_id: str,
        success: bool,
        confidence_score: float,
        response_time: float,
        user_rating: Optional[float] = None
    ) -> None:
        """Record test result for a request."""
        
        if request_id not in self._variant_assignments:
            return
        
        variant_id = self._variant_assignments[request_id]
        
        # Find the test and variant
        test = None
        variant = None
        for t in self._active_tests.values():
            v = t.get_variant_by_id(variant_id)
            if v:
                test = t
                variant = v
                break
        
        if not test or not variant:
            return
        
        # Update variant metrics
        variant.total_requests += 1
        if success:
            variant.successful_requests += 1
        
        variant.total_confidence += confidence_score
        variant.total_response_time += response_time
        
        if user_rating is not None:
            variant.user_ratings.append(user_rating)
        
        # Update template metrics
        self.template_manager.update_template_metrics(
            variant.template_id, success, confidence_score
        )
        
        test.updated_at = datetime.now(timezone.utc)
        
        # Check if test should be completed
        if test.has_sufficient_data() and not test.winner_variant_id:
            self._analyze_test_results(test)
    
    def _analyze_test_results(self, test: ABTest) -> None:
        """Analyze test results and determine winner."""
        
        if not test.variants or len(test.variants) < 2:
            return
        
        control_variant = test.get_control_variant()
        if not control_variant:
            return
        
        # Find best performing variant based on primary metric
        best_variant = control_variant
        best_score = self._get_metric_value(control_variant, test.primary_metric)
        
        for variant in test.variants:
            if variant.is_control:
                continue
            
            score = self._get_metric_value(variant, test.primary_metric)
            if score > best_score:
                best_variant = variant
                best_score = score
        
        # Simple statistical significance check (placeholder for more sophisticated analysis)
        if best_variant != control_variant:
            control_score = self._get_metric_value(control_variant, test.primary_metric)
            improvement = (best_score - control_score) / control_score if control_score > 0 else 0
            
            # Require at least 5% improvement for significance
            if improvement >= 0.05:
                test.winner_variant_id = best_variant.variant_id
                test.statistical_significance = improvement
                logger.info(f"Test {test.test_id} winner: {best_variant.variant_id} with {improvement:.2%} improvement")
    
    def _get_metric_value(self, variant: ABTestVariant, metric: ABTestMetric) -> float:
        """Get metric value for a variant."""
        if metric == ABTestMetric.SUCCESS_RATE:
            return variant.success_rate
        elif metric == ABTestMetric.CONFIDENCE_SCORE:
            return variant.avg_confidence
        elif metric == ABTestMetric.RESPONSE_TIME:
            return -variant.avg_response_time  # Negative because lower is better
        elif metric == ABTestMetric.USER_SATISFACTION:
            return variant.avg_user_rating
        else:
            return 0.0
    
    def complete_test(self, test_id: str) -> bool:
        """Complete an A/B test and promote winner."""
        if test_id not in self._active_tests:
            return False
        
        test = self._active_tests[test_id]
        
        # Analyze results if not done
        if not test.winner_variant_id and test.has_sufficient_data():
            self._analyze_test_results(test)
        
        test.status = ABTestStatus.COMPLETED
        test.updated_at = datetime.now(timezone.utc)
        
        # Move to history
        self._test_history.append(test)
        del self._active_tests[test_id]
        
        # Promote winner template if available
        if test.winner_variant_id:
            winner_variant = test.get_variant_by_id(test.winner_variant_id)
            if winner_variant:
                self._promote_winning_template(winner_variant.template_id, test.prompt_type)
        
        logger.info(f"Completed A/B test: {test_id}")
        return True
    
    def _promote_winning_template(self, template_id: str, prompt_type: PromptType) -> None:
        """Promote winning template as the default for its type."""
        
        # Deactivate other templates of the same type
        for template in self.template_manager.get_templates_by_type(prompt_type):
            if template.template_id != template_id:
                template.is_active = False
        
        # Activate winning template
        winning_template = self.template_manager.get_template(template_id)
        if winning_template:
            winning_template.is_active = True
            logger.info(f"Promoted template {template_id} as default for {prompt_type}")
    
    def get_test_results(self, test_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed test results."""
        test = self._active_tests.get(test_id)
        if not test:
            # Check history
            test = next((t for t in self._test_history if t.test_id == test_id), None)
        
        if not test:
            return None
        
        results = {
            "test_id": test.test_id,
            "name": test.name,
            "status": test.status,
            "prompt_type": test.prompt_type,
            "primary_metric": test.primary_metric,
            "start_date": test.start_date.isoformat() if test.start_date else None,
            "end_date": test.end_date.isoformat() if test.end_date else None,
            "winner_variant_id": test.winner_variant_id,
            "statistical_significance": test.statistical_significance,
            "variants": []
        }
        
        for variant in test.variants:
            variant_data = {
                "variant_id": variant.variant_id,
                "template_id": variant.template_id,
                "name": variant.name,
                "is_control": variant.is_control,
                "traffic_percentage": variant.traffic_percentage,
                "total_requests": variant.total_requests,
                "success_rate": variant.success_rate,
                "avg_confidence": variant.avg_confidence,
                "avg_response_time": variant.avg_response_time,
                "avg_user_rating": variant.avg_user_rating
            }
            results["variants"].append(variant_data)
        
        return results
    
    def list_active_tests(self) -> List[Dict[str, Any]]:
        """List all active tests."""
        return [
            {
                "test_id": test.test_id,
                "name": test.name,
                "status": test.status,
                "prompt_type": test.prompt_type,
                "start_date": test.start_date.isoformat() if test.start_date else None,
                "variants_count": len(test.variants)
            }
            for test in self._active_tests.values()
        ]


# Global optimizer instance
prompt_optimizer = PromptOptimizer(None)  # Will be initialized with template manager
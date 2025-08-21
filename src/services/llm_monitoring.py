"""
LLM Performance Monitoring and Analytics Service

This service provides comprehensive monitoring for LLM response times, accuracy,
confidence score distributions, and model performance tracking with A/B testing capabilities.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict, deque
from enum import Enum
import statistics
import json
import threading
from concurrent.futures import ThreadPoolExecutor

from ..core.logging import get_logger
from ..core.config import get_settings
from .llm_decision_service import LLMDecisionResponse, LLMDecisionStatus
from .huggingface_client import ModelHealthStatus

logger = get_logger(__name__)


class ModelPerformanceMetric(str, Enum):
    """Model performance metric types."""
    RESPONSE_TIME = "response_time"
    ACCURACY = "accuracy"
    CONFIDENCE = "confidence"
    SUCCESS_RATE = "success_rate"
    THROUGHPUT = "throughput"


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class LLMPerformanceMetrics:
    """LLM performance metrics snapshot."""
    timestamp: datetime
    model_id: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_response_time_ms: float
    p95_response_time_ms: float
    p99_response_time_ms: float
    avg_confidence_score: float
    confidence_distribution: Dict[str, int]  # confidence ranges -> count
    decision_distribution: Dict[str, int]  # decision types -> count
    accuracy_score: Optional[float] = None
    throughput_per_minute: float = 0.0
    error_rate: float = 0.0
    fallback_rate: float = 0.0


@dataclass
class ModelComparisonMetrics:
    """A/B testing metrics for model comparison."""
    model_a_id: str
    model_b_id: str
    test_start_time: datetime
    test_duration_hours: float
    model_a_metrics: LLMPerformanceMetrics
    model_b_metrics: LLMPerformanceMetrics
    statistical_significance: Dict[str, float]  # metric -> p-value
    winner: Optional[str] = None
    confidence_interval: Dict[str, Tuple[float, float]] = field(default_factory=dict)


@dataclass
class LLMAlert:
    """LLM monitoring alert."""
    alert_id: str
    alert_type: str
    severity: AlertSeverity
    model_id: str
    metric_name: str
    current_value: float
    threshold_value: float
    message: str
    timestamp: datetime
    resolved: bool = False
    resolution_time: Optional[datetime] = None
    suggested_actions: List[str] = field(default_factory=list)


@dataclass
class DecisionAccuracyMetrics:
    """Decision accuracy tracking metrics."""
    total_decisions: int
    expert_reviewed: int
    accuracy_rate: float
    precision_by_decision: Dict[str, float]  # APPROVE/DENY/PENDING -> precision
    recall_by_decision: Dict[str, float]
    f1_score_by_decision: Dict[str, float]
    confidence_accuracy_correlation: float
    timestamp: datetime


class LLMRequestTracker:
    """Tracks individual LLM requests for performance analysis."""
    
    def __init__(self, max_history: int = 10000):
        self.max_history = max_history
        self.request_history = deque(maxlen=max_history)
        self.model_metrics = defaultdict(lambda: {
            'response_times': deque(maxlen=1000),
            'confidence_scores': deque(maxlen=1000),
            'decisions': deque(maxlen=1000),
            'success_count': 0,
            'failure_count': 0,
            'fallback_count': 0
        })
        self.lock = threading.Lock()
    
    def record_request(
        self,
        model_id: str,
        response_time_ms: float,
        decision_response: Optional[LLMDecisionResponse] = None,
        success: bool = True,
        fallback_used: bool = False
    ):
        """Record an LLM request for tracking."""
        with self.lock:
            timestamp = datetime.now(timezone.utc)
            
            # Record in history
            self.request_history.append({
                'timestamp': timestamp,
                'model_id': model_id,
                'response_time_ms': response_time_ms,
                'success': success,
                'fallback_used': fallback_used,
                'decision': decision_response.decision.value if decision_response else None,
                'confidence_score': decision_response.confidence_score if decision_response else None
            })
            
            # Update model-specific metrics
            metrics = self.model_metrics[model_id]
            metrics['response_times'].append(response_time_ms)
            
            if success:
                metrics['success_count'] += 1
                if decision_response:
                    metrics['confidence_scores'].append(decision_response.confidence_score)
                    metrics['decisions'].append(decision_response.decision.value)
            else:
                metrics['failure_count'] += 1
            
            if fallback_used:
                metrics['fallback_count'] += 1
    
    def get_model_metrics(self, model_id: str, hours: int = 1) -> Optional[LLMPerformanceMetrics]:
        """Get performance metrics for a specific model."""
        with self.lock:
            if model_id not in self.model_metrics:
                return None
            
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            # Filter recent requests
            recent_requests = [
                req for req in self.request_history
                if req['model_id'] == model_id and req['timestamp'] > cutoff_time
            ]
            
            if not recent_requests:
                return None
            
            # Calculate metrics
            total_requests = len(recent_requests)
            successful_requests = sum(1 for req in recent_requests if req['success'])
            failed_requests = total_requests - successful_requests
            
            response_times = [req['response_time_ms'] for req in recent_requests if req['success']]
            confidence_scores = [req['confidence_score'] for req in recent_requests 
                               if req['confidence_score'] is not None]
            decisions = [req['decision'] for req in recent_requests if req['decision']]
            
            # Response time statistics
            avg_response_time = statistics.mean(response_times) if response_times else 0.0
            p95_response_time = self._percentile(response_times, 95) if response_times else 0.0
            p99_response_time = self._percentile(response_times, 99) if response_times else 0.0
            
            # Confidence distribution
            confidence_distribution = self._calculate_confidence_distribution(confidence_scores)
            
            # Decision distribution
            decision_distribution = {}
            for decision in ['APPROVE', 'DENY', 'PENDING']:
                decision_distribution[decision] = decisions.count(decision)
            
            # Calculate rates
            error_rate = (failed_requests / total_requests) * 100 if total_requests > 0 else 0.0
            fallback_count = sum(1 for req in recent_requests if req['fallback_used'])
            fallback_rate = (fallback_count / total_requests) * 100 if total_requests > 0 else 0.0
            
            # Throughput (requests per minute)
            throughput_per_minute = total_requests / (hours * 60) if hours > 0 else 0.0
            
            return LLMPerformanceMetrics(
                timestamp=datetime.now(timezone.utc),
                model_id=model_id,
                total_requests=total_requests,
                successful_requests=successful_requests,
                failed_requests=failed_requests,
                avg_response_time_ms=avg_response_time,
                p95_response_time_ms=p95_response_time,
                p99_response_time_ms=p99_response_time,
                avg_confidence_score=statistics.mean(confidence_scores) if confidence_scores else 0.0,
                confidence_distribution=confidence_distribution,
                decision_distribution=decision_distribution,
                throughput_per_minute=throughput_per_minute,
                error_rate=error_rate,
                fallback_rate=fallback_rate
            )
    
    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile of data."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = int((percentile / 100) * len(sorted_data))
        return sorted_data[min(index, len(sorted_data) - 1)]
    
    def _calculate_confidence_distribution(self, confidence_scores: List[float]) -> Dict[str, int]:
        """Calculate confidence score distribution."""
        distribution = {
            '0.0-0.2': 0,
            '0.2-0.4': 0,
            '0.4-0.6': 0,
            '0.6-0.8': 0,
            '0.8-1.0': 0
        }
        
        for score in confidence_scores:
            if score < 0.2:
                distribution['0.0-0.2'] += 1
            elif score < 0.4:
                distribution['0.2-0.4'] += 1
            elif score < 0.6:
                distribution['0.4-0.6'] += 1
            elif score < 0.8:
                distribution['0.6-0.8'] += 1
            else:
                distribution['0.8-1.0'] += 1
        
        return distribution


class ABTestManager:
    """Manages A/B testing for model performance comparison."""
    
    def __init__(self):
        self.active_tests = {}
        self.completed_tests = []
        self.lock = threading.Lock()
        self.logger = get_logger(f"{__name__}.ABTestManager")
    
    def start_ab_test(
        self,
        test_id: str,
        model_a_id: str,
        model_b_id: str,
        duration_hours: float = 24.0,
        traffic_split: float = 0.5
    ) -> bool:
        """Start an A/B test between two models."""
        with self.lock:
            if test_id in self.active_tests:
                return False
            
            self.active_tests[test_id] = {
                'model_a_id': model_a_id,
                'model_b_id': model_b_id,
                'start_time': datetime.now(timezone.utc),
                'duration_hours': duration_hours,
                'traffic_split': traffic_split,
                'model_a_requests': 0,
                'model_b_requests': 0
            }
            
            self.logger.info(f"Started A/B test {test_id}: {model_a_id} vs {model_b_id}")
            return True
    
    def get_model_for_request(self, test_id: str, request_hash: int) -> Optional[str]:
        """Get which model to use for a request in an A/B test."""
        with self.lock:
            if test_id not in self.active_tests:
                return None
            
            test = self.active_tests[test_id]
            
            # Check if test has expired
            elapsed = datetime.now(timezone.utc) - test['start_time']
            if elapsed.total_seconds() / 3600 > test['duration_hours']:
                self._complete_test(test_id)
                return None
            
            # Determine model based on hash and traffic split
            use_model_a = (request_hash % 100) < (test['traffic_split'] * 100)
            
            if use_model_a:
                test['model_a_requests'] += 1
                return test['model_a_id']
            else:
                test['model_b_requests'] += 1
                return test['model_b_id']
    
    def _complete_test(self, test_id: str):
        """Complete an A/B test and move to completed tests."""
        if test_id in self.active_tests:
            test = self.active_tests.pop(test_id)
            test['end_time'] = datetime.now(timezone.utc)
            self.completed_tests.append(test)
            self.logger.info(f"Completed A/B test {test_id}")
    
    def get_test_results(self, test_id: str, request_tracker: LLMRequestTracker) -> Optional[ModelComparisonMetrics]:
        """Get results for a completed A/B test."""
        # Find test in completed tests
        test = None
        for completed_test in self.completed_tests:
            if completed_test.get('test_id') == test_id:
                test = completed_test
                break
        
        if not test:
            return None
        
        # Get metrics for both models during test period
        test_duration = test['duration_hours']
        model_a_metrics = request_tracker.get_model_metrics(test['model_a_id'], int(test_duration))
        model_b_metrics = request_tracker.get_model_metrics(test['model_b_id'], int(test_duration))
        
        if not model_a_metrics or not model_b_metrics:
            return None
        
        # Calculate statistical significance (simplified)
        statistical_significance = self._calculate_statistical_significance(
            model_a_metrics, model_b_metrics
        )
        
        # Determine winner
        winner = self._determine_winner(model_a_metrics, model_b_metrics, statistical_significance)
        
        return ModelComparisonMetrics(
            model_a_id=test['model_a_id'],
            model_b_id=test['model_b_id'],
            test_start_time=test['start_time'],
            test_duration_hours=test_duration,
            model_a_metrics=model_a_metrics,
            model_b_metrics=model_b_metrics,
            statistical_significance=statistical_significance,
            winner=winner
        )
    
    def _calculate_statistical_significance(
        self,
        metrics_a: LLMPerformanceMetrics,
        metrics_b: LLMPerformanceMetrics
    ) -> Dict[str, float]:
        """Calculate statistical significance for key metrics."""
        # Simplified statistical significance calculation
        # In production, would use proper statistical tests
        
        significance = {}
        
        # Response time significance
        if metrics_a.total_requests > 30 and metrics_b.total_requests > 30:
            response_time_diff = abs(metrics_a.avg_response_time_ms - metrics_b.avg_response_time_ms)
            avg_response_time = (metrics_a.avg_response_time_ms + metrics_b.avg_response_time_ms) / 2
            
            if avg_response_time > 0:
                relative_diff = response_time_diff / avg_response_time
                # Simplified p-value estimation
                significance['response_time'] = max(0.01, 1.0 - relative_diff)
        
        # Confidence score significance
        confidence_diff = abs(metrics_a.avg_confidence_score - metrics_b.avg_confidence_score)
        significance['confidence'] = max(0.01, 1.0 - (confidence_diff * 2))
        
        # Error rate significance
        error_rate_diff = abs(metrics_a.error_rate - metrics_b.error_rate)
        significance['error_rate'] = max(0.01, 1.0 - (error_rate_diff / 100))
        
        return significance
    
    def _determine_winner(
        self,
        metrics_a: LLMPerformanceMetrics,
        metrics_b: LLMPerformanceMetrics,
        significance: Dict[str, float]
    ) -> Optional[str]:
        """Determine the winner of an A/B test."""
        
        # Score each model based on key metrics
        score_a = 0
        score_b = 0
        
        # Response time (lower is better)
        if metrics_a.avg_response_time_ms < metrics_b.avg_response_time_ms:
            score_a += 1
        else:
            score_b += 1
        
        # Confidence score (higher is better)
        if metrics_a.avg_confidence_score > metrics_b.avg_confidence_score:
            score_a += 1
        else:
            score_b += 1
        
        # Error rate (lower is better)
        if metrics_a.error_rate < metrics_b.error_rate:
            score_a += 1
        else:
            score_b += 1
        
        # Throughput (higher is better)
        if metrics_a.throughput_per_minute > metrics_b.throughput_per_minute:
            score_a += 1
        else:
            score_b += 1
        
        # Check if difference is statistically significant
        significant_metrics = sum(1 for p_val in significance.values() if p_val < 0.05)
        
        if significant_metrics >= 2:  # At least 2 metrics show significant difference
            if score_a > score_b:
                return metrics_a.model_id
            elif score_b > score_a:
                return metrics_b.model_id
        
        return None  # No clear winner


class LLMAlertManager:
    """Manages alerts for LLM performance issues."""
    
    def __init__(self):
        self.active_alerts = {}
        self.alert_history = deque(maxlen=1000)
        self.thresholds = {
            'response_time_ms': 5000,  # 5 seconds
            'error_rate_percent': 10.0,
            'confidence_score_min': 0.6,
            'throughput_min': 1.0,  # requests per minute
            'fallback_rate_max': 20.0  # percent
        }
        self.lock = threading.Lock()
        self.logger = get_logger(f"{__name__}.LLMAlertManager")
    
    def check_metrics_for_alerts(self, metrics: LLMPerformanceMetrics):
        """Check metrics against thresholds and generate alerts."""
        with self.lock:
            alerts_to_create = []
            alerts_to_resolve = []
            
            # Check response time
            if metrics.avg_response_time_ms > self.thresholds['response_time_ms']:
                alert_key = f"{metrics.model_id}_response_time"
                if alert_key not in self.active_alerts:
                    alerts_to_create.append(self._create_alert(
                        alert_key, "response_time", AlertSeverity.HIGH,
                        metrics.model_id, "avg_response_time_ms",
                        metrics.avg_response_time_ms, self.thresholds['response_time_ms'],
                        f"Average response time ({metrics.avg_response_time_ms:.0f}ms) exceeds threshold"
                    ))
            else:
                alert_key = f"{metrics.model_id}_response_time"
                if alert_key in self.active_alerts:
                    alerts_to_resolve.append(alert_key)
            
            # Check error rate
            if metrics.error_rate > self.thresholds['error_rate_percent']:
                alert_key = f"{metrics.model_id}_error_rate"
                if alert_key not in self.active_alerts:
                    severity = AlertSeverity.CRITICAL if metrics.error_rate > 25 else AlertSeverity.HIGH
                    alerts_to_create.append(self._create_alert(
                        alert_key, "error_rate", severity,
                        metrics.model_id, "error_rate",
                        metrics.error_rate, self.thresholds['error_rate_percent'],
                        f"Error rate ({metrics.error_rate:.1f}%) exceeds threshold"
                    ))
            else:
                alert_key = f"{metrics.model_id}_error_rate"
                if alert_key in self.active_alerts:
                    alerts_to_resolve.append(alert_key)
            
            # Check confidence score
            if metrics.avg_confidence_score < self.thresholds['confidence_score_min']:
                alert_key = f"{metrics.model_id}_low_confidence"
                if alert_key not in self.active_alerts:
                    alerts_to_create.append(self._create_alert(
                        alert_key, "low_confidence", AlertSeverity.MEDIUM,
                        metrics.model_id, "avg_confidence_score",
                        metrics.avg_confidence_score, self.thresholds['confidence_score_min'],
                        f"Average confidence score ({metrics.avg_confidence_score:.2f}) below threshold"
                    ))
            else:
                alert_key = f"{metrics.model_id}_low_confidence"
                if alert_key in self.active_alerts:
                    alerts_to_resolve.append(alert_key)
            
            # Check throughput
            if metrics.throughput_per_minute < self.thresholds['throughput_min']:
                alert_key = f"{metrics.model_id}_low_throughput"
                if alert_key not in self.active_alerts:
                    alerts_to_create.append(self._create_alert(
                        alert_key, "low_throughput", AlertSeverity.MEDIUM,
                        metrics.model_id, "throughput_per_minute",
                        metrics.throughput_per_minute, self.thresholds['throughput_min'],
                        f"Throughput ({metrics.throughput_per_minute:.1f} req/min) below threshold"
                    ))
            else:
                alert_key = f"{metrics.model_id}_low_throughput"
                if alert_key in self.active_alerts:
                    alerts_to_resolve.append(alert_key)
            
            # Check fallback rate
            if metrics.fallback_rate > self.thresholds['fallback_rate_max']:
                alert_key = f"{metrics.model_id}_high_fallback"
                if alert_key not in self.active_alerts:
                    alerts_to_create.append(self._create_alert(
                        alert_key, "high_fallback_rate", AlertSeverity.HIGH,
                        metrics.model_id, "fallback_rate",
                        metrics.fallback_rate, self.thresholds['fallback_rate_max'],
                        f"Fallback rate ({metrics.fallback_rate:.1f}%) exceeds threshold"
                    ))
            else:
                alert_key = f"{metrics.model_id}_high_fallback"
                if alert_key in self.active_alerts:
                    alerts_to_resolve.append(alert_key)
            
            # Create new alerts
            for alert in alerts_to_create:
                self.active_alerts[alert.alert_id] = alert
                self.alert_history.append(alert)
                self.logger.warning(f"LLM Alert created: {alert.message}")
            
            # Resolve alerts
            for alert_key in alerts_to_resolve:
                if alert_key in self.active_alerts:
                    alert = self.active_alerts[alert_key]
                    alert.resolved = True
                    alert.resolution_time = datetime.now(timezone.utc)
                    del self.active_alerts[alert_key]
                    self.logger.info(f"LLM Alert resolved: {alert.message}")
    
    def _create_alert(
        self,
        alert_id: str,
        alert_type: str,
        severity: AlertSeverity,
        model_id: str,
        metric_name: str,
        current_value: float,
        threshold_value: float,
        message: str
    ) -> LLMAlert:
        """Create a new LLM alert."""
        
        suggested_actions = self._get_suggested_actions(alert_type, model_id)
        
        return LLMAlert(
            alert_id=alert_id,
            alert_type=alert_type,
            severity=severity,
            model_id=model_id,
            metric_name=metric_name,
            current_value=current_value,
            threshold_value=threshold_value,
            message=message,
            timestamp=datetime.now(timezone.utc),
            suggested_actions=suggested_actions
        )
    
    def _get_suggested_actions(self, alert_type: str, model_id: str) -> List[str]:
        """Get suggested actions for different alert types."""
        
        actions = {
            'response_time': [
                f"Check {model_id} model health and availability",
                "Consider switching to a faster model",
                "Review request complexity and optimize prompts",
                "Scale up model infrastructure if using local deployment"
            ],
            'error_rate': [
                f"Investigate {model_id} model errors and logs",
                "Check Hugging Face API status and quotas",
                "Verify model configuration and parameters",
                "Enable fallback models if not already active"
            ],
            'low_confidence': [
                f"Review prompt templates for {model_id}",
                "Consider using a more specialized medical model",
                "Implement additional validation rules",
                "Route low-confidence cases to human review"
            ],
            'low_throughput': [
                f"Check {model_id} rate limits and quotas",
                "Scale up model infrastructure",
                "Optimize request batching",
                "Consider load balancing across multiple models"
            ],
            'high_fallback_rate': [
                f"Investigate primary model {model_id} reliability",
                "Review fallback trigger conditions",
                "Consider upgrading to more reliable model tier",
                "Implement circuit breaker patterns"
            ]
        }
        
        return actions.get(alert_type, ["Contact system administrator"])
    
    def get_active_alerts(self) -> List[LLMAlert]:
        """Get all active alerts."""
        with self.lock:
            return list(self.active_alerts.values())
    
    def get_alert_history(self, hours: int = 24) -> List[LLMAlert]:
        """Get alert history for specified time period."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        with self.lock:
            return [
                alert for alert in self.alert_history
                if alert.timestamp > cutoff_time
            ]


class LLMMonitoringService:
    """Main LLM monitoring service that coordinates all monitoring components."""
    
    def __init__(self):
        self.request_tracker = LLMRequestTracker()
        self.ab_test_manager = ABTestManager()
        self.alert_manager = LLMAlertManager()
        self.accuracy_tracker = {}  # model_id -> accuracy metrics
        self.monitoring_active = False
        self.monitoring_thread = None
        self.logger = get_logger(__name__)
    
    def start_monitoring(self):
        """Start background monitoring."""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        self.logger.info("Started LLM monitoring service")
    
    def stop_monitoring(self):
        """Stop background monitoring."""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        self.logger.info("Stopped LLM monitoring service")
    
    def _monitoring_loop(self):
        """Background monitoring loop."""
        while self.monitoring_active:
            try:
                # Get all active models
                active_models = self._get_active_models()
                
                # Check metrics for each model
                for model_id in active_models:
                    metrics = self.request_tracker.get_model_metrics(model_id, hours=1)
                    if metrics:
                        self.alert_manager.check_metrics_for_alerts(metrics)
                
                # Sleep for 5 minutes
                time.sleep(300)
                
            except Exception as e:
                self.logger.error(f"Error in LLM monitoring loop: {e}")
                time.sleep(300)
    
    def _get_active_models(self) -> List[str]:
        """Get list of active model IDs."""
        # This would integrate with the LLM config service
        # For now, return models that have recent activity
        active_models = []
        for model_id in self.request_tracker.model_metrics.keys():
            metrics = self.request_tracker.get_model_metrics(model_id, hours=1)
            if metrics and metrics.total_requests > 0:
                active_models.append(model_id)
        return active_models
    
    def record_llm_request(
        self,
        model_id: str,
        response_time_ms: float,
        decision_response: Optional[LLMDecisionResponse] = None,
        success: bool = True,
        fallback_used: bool = False
    ):
        """Record an LLM request for monitoring."""
        self.request_tracker.record_request(
            model_id, response_time_ms, decision_response, success, fallback_used
        )
    
    def record_decision_accuracy(
        self,
        model_id: str,
        decision_id: str,
        predicted_decision: str,
        actual_decision: str,
        confidence_score: float
    ):
        """Record decision accuracy for model performance tracking."""
        if model_id not in self.accuracy_tracker:
            self.accuracy_tracker[model_id] = {
                'correct_predictions': 0,
                'total_predictions': 0,
                'confidence_scores': [],
                'accuracy_by_decision': defaultdict(lambda: {'correct': 0, 'total': 0})
            }
        
        tracker = self.accuracy_tracker[model_id]
        tracker['total_predictions'] += 1
        tracker['confidence_scores'].append(confidence_score)
        
        is_correct = predicted_decision == actual_decision
        if is_correct:
            tracker['correct_predictions'] += 1
        
        # Track accuracy by decision type
        decision_tracker = tracker['accuracy_by_decision'][predicted_decision]
        decision_tracker['total'] += 1
        if is_correct:
            decision_tracker['correct'] += 1
    
    def get_model_performance_metrics(
        self,
        model_id: str,
        hours: int = 24
    ) -> Optional[LLMPerformanceMetrics]:
        """Get comprehensive performance metrics for a model."""
        metrics = self.request_tracker.get_model_metrics(model_id, hours)
        
        if metrics and model_id in self.accuracy_tracker:
            # Add accuracy information
            accuracy_data = self.accuracy_tracker[model_id]
            if accuracy_data['total_predictions'] > 0:
                metrics.accuracy_score = accuracy_data['correct_predictions'] / accuracy_data['total_predictions']
        
        return metrics
    
    def get_decision_accuracy_metrics(self, model_id: str) -> Optional[DecisionAccuracyMetrics]:
        """Get decision accuracy metrics for a model."""
        if model_id not in self.accuracy_tracker:
            return None
        
        tracker = self.accuracy_tracker[model_id]
        
        if tracker['total_predictions'] == 0:
            return None
        
        # Calculate overall accuracy
        accuracy_rate = tracker['correct_predictions'] / tracker['total_predictions']
        
        # Calculate precision, recall, F1 for each decision type
        precision_by_decision = {}
        recall_by_decision = {}
        f1_score_by_decision = {}
        
        for decision_type, data in tracker['accuracy_by_decision'].items():
            if data['total'] > 0:
                precision = data['correct'] / data['total']
                precision_by_decision[decision_type] = precision
                
                # For recall, we'd need true positives vs false negatives
                # Simplified calculation for now
                recall_by_decision[decision_type] = precision  # Approximation
                
                # F1 score
                if precision > 0:
                    f1_score_by_decision[decision_type] = 2 * precision / (1 + precision)
                else:
                    f1_score_by_decision[decision_type] = 0.0
        
        # Calculate confidence-accuracy correlation
        confidence_accuracy_correlation = self._calculate_confidence_accuracy_correlation(
            tracker['confidence_scores'], tracker['correct_predictions'], tracker['total_predictions']
        )
        
        return DecisionAccuracyMetrics(
            total_decisions=tracker['total_predictions'],
            expert_reviewed=tracker['total_predictions'],  # Assuming all are reviewed
            accuracy_rate=accuracy_rate,
            precision_by_decision=precision_by_decision,
            recall_by_decision=recall_by_decision,
            f1_score_by_decision=f1_score_by_decision,
            confidence_accuracy_correlation=confidence_accuracy_correlation,
            timestamp=datetime.now(timezone.utc)
        )
    
    def _calculate_confidence_accuracy_correlation(
        self,
        confidence_scores: List[float],
        correct_predictions: int,
        total_predictions: int
    ) -> float:
        """Calculate correlation between confidence scores and accuracy."""
        if len(confidence_scores) < 2:
            return 0.0
        
        # Simplified correlation calculation
        avg_confidence = statistics.mean(confidence_scores)
        accuracy_rate = correct_predictions / total_predictions
        
        # This is a simplified correlation - in production would use proper statistical correlation
        return min(1.0, abs(avg_confidence - accuracy_rate))
    
    def start_ab_test(
        self,
        test_id: str,
        model_a_id: str,
        model_b_id: str,
        duration_hours: float = 24.0
    ) -> bool:
        """Start an A/B test between two models."""
        return self.ab_test_manager.start_ab_test(
            test_id, model_a_id, model_b_id, duration_hours
        )
    
    def get_ab_test_results(self, test_id: str) -> Optional[ModelComparisonMetrics]:
        """Get A/B test results."""
        return self.ab_test_manager.get_test_results(test_id, self.request_tracker)
    
    def get_active_alerts(self) -> List[LLMAlert]:
        """Get active LLM alerts."""
        return self.alert_manager.get_active_alerts()
    
    def get_alert_history(self, hours: int = 24) -> List[LLMAlert]:
        """Get LLM alert history."""
        return self.alert_manager.get_alert_history(hours)
    
    def get_monitoring_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive monitoring data for dashboard."""
        active_models = self._get_active_models()
        
        dashboard_data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'active_models': len(active_models),
            'model_metrics': {},
            'accuracy_metrics': {},
            'active_alerts': len(self.get_active_alerts()),
            'alert_summary': self._get_alert_summary(),
            'performance_summary': {}
        }
        
        # Get metrics for each active model
        for model_id in active_models:
            metrics = self.get_model_performance_metrics(model_id, hours=1)
            if metrics:
                dashboard_data['model_metrics'][model_id] = asdict(metrics)
            
            accuracy_metrics = self.get_decision_accuracy_metrics(model_id)
            if accuracy_metrics:
                dashboard_data['accuracy_metrics'][model_id] = asdict(accuracy_metrics)
        
        # Calculate performance summary
        if dashboard_data['model_metrics']:
            all_metrics = list(dashboard_data['model_metrics'].values())
            dashboard_data['performance_summary'] = {
                'avg_response_time_ms': statistics.mean([m['avg_response_time_ms'] for m in all_metrics]),
                'avg_confidence_score': statistics.mean([m['avg_confidence_score'] for m in all_metrics]),
                'total_requests': sum([m['total_requests'] for m in all_metrics]),
                'overall_error_rate': statistics.mean([m['error_rate'] for m in all_metrics])
            }
        
        return dashboard_data
    
    def _get_alert_summary(self) -> Dict[str, int]:
        """Get summary of alerts by severity."""
        active_alerts = self.get_active_alerts()
        
        summary = {
            'critical': 0,
            'high': 0,
            'medium': 0,
            'low': 0
        }
        
        for alert in active_alerts:
            summary[alert.severity.value] += 1
        
        return summary


# Global monitoring service instance
llm_monitoring_service = LLMMonitoringService()
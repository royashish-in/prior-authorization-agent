"""
Intelligent Model Selection Service

This service provides intelligent model selection based on request complexity,
performance requirements, and current model health status.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import statistics

from ..models.authorization import AuthorizationRequest
from ..models.enums import UrgencyLevel
from .llm_config import llm_config, ModelConfig, ModelType
from .llm_model_manager import model_manager, ModelHealth, ModelStatus
from .cache import cache_manager

logger = logging.getLogger(__name__)


class ComplexityLevel(str, Enum):
    """Request complexity levels."""
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    VERY_COMPLEX = "very_complex"


class PerformanceRequirement(str, Enum):
    """Performance requirement levels."""
    FAST = "fast"          # < 10 seconds
    STANDARD = "standard"  # < 30 seconds
    THOROUGH = "thorough"  # < 60 seconds
    COMPREHENSIVE = "comprehensive"  # > 60 seconds acceptable


@dataclass
class RequestComplexity:
    """Analysis of request complexity."""
    level: ComplexityLevel
    score: float  # 0.0 to 1.0
    factors: Dict[str, float] = field(default_factory=dict)
    reasoning: str = ""


@dataclass
class ModelPerformanceMetrics:
    """Performance metrics for a model."""
    model_id: str
    average_response_time_ms: float = 0.0
    success_rate: float = 1.0
    confidence_score_avg: float = 0.0
    complexity_handling: Dict[ComplexityLevel, float] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    request_count: int = 0
    error_count: int = 0


@dataclass
class ModelSelection:
    """Result of model selection process."""
    selected_model: ModelConfig
    reasoning: str
    confidence: float
    fallback_models: List[ModelConfig] = field(default_factory=list)
    complexity_analysis: Optional[RequestComplexity] = None
    performance_requirement: Optional[PerformanceRequirement] = None


class IntelligentModelSelectionService:
    """
    Service for intelligent model selection based on request characteristics
    and performance requirements.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.cache = cache_manager
        
        # Model performance tracking
        self._model_metrics: Dict[str, ModelPerformanceMetrics] = {}
        self._performance_history: Dict[str, List[Tuple[datetime, float, float]]] = {}
        
        # Selection parameters
        self.complexity_weights = {
            'diagnosis_count': 0.15,
            'procedure_count': 0.15,
            'clinical_text_length': 0.20,
            'urgency_level': 0.10,
            'comorbidities': 0.15,
            'prior_authorizations': 0.10,
            'specialty_complexity': 0.15
        }
        
        # Performance thresholds
        self.performance_thresholds = {
            PerformanceRequirement.FAST: 10000,      # 10 seconds
            PerformanceRequirement.STANDARD: 30000,  # 30 seconds
            PerformanceRequirement.THOROUGH: 60000,  # 60 seconds
            PerformanceRequirement.COMPREHENSIVE: 120000  # 2 minutes
        }
        
    async def initialize(self):
        """Initialize the intelligent model selection service."""
        self.logger.info("Initializing Intelligent Model Selection Service")
        
        # Initialize metrics for all configured models
        for model_config in llm_config.list_models():
            if model_config.enabled:
                self._model_metrics[model_config.model_id] = ModelPerformanceMetrics(
                    model_id=model_config.model_id
                )
                self._performance_history[model_config.model_id] = []
        
        # Load cached metrics
        await self._load_cached_metrics()
        
        self.logger.info("Intelligent Model Selection Service initialized")
    
    async def select_optimal_model(
        self,
        request: AuthorizationRequest,
        performance_requirement: Optional[PerformanceRequirement] = None,
        exclude_models: Optional[List[str]] = None
    ) -> ModelSelection:
        """
        Select the optimal model for processing an authorization request.
        
        Args:
            request: Authorization request to analyze
            performance_requirement: Required performance level
            exclude_models: Models to exclude from selection
            
        Returns:
            Model selection result with reasoning
        """
        # Analyze request complexity
        complexity = await self._analyze_request_complexity(request)
        
        # Determine performance requirement if not specified
        if not performance_requirement:
            performance_requirement = self._determine_performance_requirement(request, complexity)
        
        # Get available models
        available_models = await self._get_available_models(exclude_models)
        
        if not available_models:
            raise Exception("No available models for processing")
        
        # Score models based on suitability
        model_scores = await self._score_models(
            available_models, complexity, performance_requirement
        )
        
        # Select best model
        best_model_id, best_score = max(model_scores.items(), key=lambda x: x[1])
        selected_model = llm_config.get_model_config(best_model_id)
        
        # Prepare fallback models
        fallback_models = []
        sorted_models = sorted(model_scores.items(), key=lambda x: x[1], reverse=True)
        for model_id, score in sorted_models[1:4]:  # Top 3 alternatives
            fallback_model = llm_config.get_model_config(model_id)
            if fallback_model:
                fallback_models.append(fallback_model)
        
        # Generate reasoning
        reasoning = self._generate_selection_reasoning(
            selected_model, complexity, performance_requirement, best_score
        )
        
        selection = ModelSelection(
            selected_model=selected_model,
            reasoning=reasoning,
            confidence=best_score,
            fallback_models=fallback_models,
            complexity_analysis=complexity,
            performance_requirement=performance_requirement
        )
        
        self.logger.debug(f"Selected model {selected_model.model_id} for request "
                         f"(complexity: {complexity.level.value}, score: {best_score:.3f})")
        
        return selection
    
    async def update_model_performance(
        self,
        model_id: str,
        response_time_ms: float,
        success: bool,
        confidence_score: float,
        complexity_level: ComplexityLevel
    ):
        """
        Update performance metrics for a model based on processing results.
        
        Args:
            model_id: Model identifier
            response_time_ms: Response time in milliseconds
            success: Whether the processing was successful
            confidence_score: Confidence score of the result
            complexity_level: Complexity level of the processed request
        """
        if model_id not in self._model_metrics:
            self._model_metrics[model_id] = ModelPerformanceMetrics(model_id=model_id)
        
        metrics = self._model_metrics[model_id]
        
        # Update basic metrics
        metrics.request_count += 1
        if not success:
            metrics.error_count += 1
        
        # Update success rate
        metrics.success_rate = (metrics.request_count - metrics.error_count) / metrics.request_count
        
        # Update average response time (exponential moving average)
        alpha = 0.1  # Smoothing factor
        if metrics.average_response_time_ms == 0:
            metrics.average_response_time_ms = response_time_ms
        else:
            metrics.average_response_time_ms = (
                alpha * response_time_ms + (1 - alpha) * metrics.average_response_time_ms
            )
        
        # Update average confidence score
        if success:
            if metrics.confidence_score_avg == 0:
                metrics.confidence_score_avg = confidence_score
            else:
                metrics.confidence_score_avg = (
                    alpha * confidence_score + (1 - alpha) * metrics.confidence_score_avg
                )
        
        # Update complexity handling metrics
        if complexity_level not in metrics.complexity_handling:
            metrics.complexity_handling[complexity_level] = confidence_score if success else 0.0
        else:
            current_score = metrics.complexity_handling[complexity_level]
            metrics.complexity_handling[complexity_level] = (
                alpha * (confidence_score if success else 0.0) + (1 - alpha) * current_score
            )
        
        metrics.last_updated = datetime.now(timezone.utc)
        
        # Add to performance history
        if model_id not in self._performance_history:
            self._performance_history[model_id] = []
        
        self._performance_history[model_id].append((
            datetime.now(timezone.utc),
            response_time_ms,
            confidence_score if success else 0.0
        ))
        
        # Keep only recent history (last 1000 entries)
        if len(self._performance_history[model_id]) > 1000:
            self._performance_history[model_id] = self._performance_history[model_id][-1000:]
        
        # Cache updated metrics periodically
        if metrics.request_count % 10 == 0:
            await self._cache_metrics()
    
    async def get_model_performance_report(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed performance report for a model."""
        if model_id not in self._model_metrics:
            return None
        
        metrics = self._model_metrics[model_id]
        history = self._performance_history.get(model_id, [])
        
        # Calculate recent performance (last 24 hours)
        recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_history = [
            (timestamp, response_time, confidence)
            for timestamp, response_time, confidence in history
            if timestamp > recent_cutoff
        ]
        
        recent_response_times = [rt for _, rt, _ in recent_history]
        recent_confidences = [conf for _, _, conf in recent_history if conf > 0]
        
        report = {
            'model_id': model_id,
            'overall_metrics': {
                'request_count': metrics.request_count,
                'success_rate': metrics.success_rate,
                'error_count': metrics.error_count,
                'average_response_time_ms': metrics.average_response_time_ms,
                'average_confidence_score': metrics.confidence_score_avg,
                'last_updated': metrics.last_updated.isoformat()
            },
            'complexity_handling': dict(metrics.complexity_handling),
            'recent_performance': {
                'request_count_24h': len(recent_history),
                'average_response_time_24h': statistics.mean(recent_response_times) if recent_response_times else 0,
                'median_response_time_24h': statistics.median(recent_response_times) if recent_response_times else 0,
                'average_confidence_24h': statistics.mean(recent_confidences) if recent_confidences else 0,
                'p95_response_time_24h': (
                    statistics.quantiles(recent_response_times, n=20)[18] 
                    if len(recent_response_times) > 20 else 0
                )
            }
        }
        
        return report
    
    async def get_all_model_performance(self) -> Dict[str, Dict[str, Any]]:
        """Get performance reports for all models."""
        reports = {}
        for model_id in self._model_metrics.keys():
            report = await self.get_model_performance_report(model_id)
            if report:
                reports[model_id] = report
        return reports
    
    async def _analyze_request_complexity(self, request: AuthorizationRequest) -> RequestComplexity:
        """Analyze the complexity of an authorization request."""
        factors = {}
        total_score = 0.0
        
        # Diagnosis count complexity
        diagnosis_count = len(getattr(request, 'diagnosis_codes', []))
        diagnosis_factor = min(diagnosis_count / 5.0, 1.0)  # Normalize to 0-1
        factors['diagnosis_count'] = diagnosis_factor
        total_score += diagnosis_factor * self.complexity_weights['diagnosis_count']
        
        # Procedure count complexity
        procedure_count = len(getattr(request, 'procedure_codes', []))
        procedure_factor = min(procedure_count / 3.0, 1.0)  # Normalize to 0-1
        factors['procedure_count'] = procedure_factor
        total_score += procedure_factor * self.complexity_weights['procedure_count']
        
        # Clinical text length complexity
        clinical_text = ""
        if hasattr(request, 'clinical_notes') and request.clinical_notes:
            clinical_text += request.clinical_notes
        if hasattr(request, 'provider_justification') and request.provider_justification:
            clinical_text += " " + request.provider_justification
        
        text_length = len(clinical_text)
        text_factor = min(text_length / 2000.0, 1.0)  # Normalize to 0-1 (2000 chars = complex)
        factors['clinical_text_length'] = text_factor
        total_score += text_factor * self.complexity_weights['clinical_text_length']
        
        # Urgency level complexity
        urgency_factor = 0.0
        if hasattr(request, 'urgency_level'):
            if request.urgency_level == UrgencyLevel.URGENT:
                urgency_factor = 1.0
            elif request.urgency_level == UrgencyLevel.ROUTINE:
                urgency_factor = 0.3
        factors['urgency_level'] = urgency_factor
        total_score += urgency_factor * self.complexity_weights['urgency_level']
        
        # Comorbidities complexity (if available)
        comorbidities_factor = 0.0
        if hasattr(request, 'comorbidities') and request.comorbidities:
            comorbidities_factor = min(len(request.comorbidities) / 5.0, 1.0)
        factors['comorbidities'] = comorbidities_factor
        total_score += comorbidities_factor * self.complexity_weights['comorbidities']
        
        # Prior authorizations complexity
        prior_auth_factor = 0.0
        if hasattr(request, 'prior_authorizations') and request.prior_authorizations:
            prior_auth_factor = min(len(request.prior_authorizations) / 3.0, 1.0)
        factors['prior_authorizations'] = prior_auth_factor
        total_score += prior_auth_factor * self.complexity_weights['prior_authorizations']
        
        # Specialty complexity
        specialty_factor = 0.0
        if hasattr(request, 'provider_info') and request.provider_info:
            specialty = getattr(request.provider_info, 'specialty', '').lower()
            # High complexity specialties
            high_complexity_specialties = [
                'oncology', 'neurosurgery', 'cardiothoracic', 'transplant',
                'interventional_cardiology', 'radiation_oncology'
            ]
            if any(spec in specialty for spec in high_complexity_specialties):
                specialty_factor = 1.0
            elif specialty:
                specialty_factor = 0.5
        factors['specialty_complexity'] = specialty_factor
        total_score += specialty_factor * self.complexity_weights['specialty_complexity']
        
        # Determine complexity level
        if total_score < 0.25:
            level = ComplexityLevel.SIMPLE
        elif total_score < 0.5:
            level = ComplexityLevel.MODERATE
        elif total_score < 0.75:
            level = ComplexityLevel.COMPLEX
        else:
            level = ComplexityLevel.VERY_COMPLEX
        
        # Generate reasoning
        reasoning_parts = []
        for factor_name, factor_value in factors.items():
            if factor_value > 0.5:
                reasoning_parts.append(f"{factor_name}: {factor_value:.2f}")
        
        reasoning = f"Complexity factors: {', '.join(reasoning_parts)}" if reasoning_parts else "Simple request"
        
        return RequestComplexity(
            level=level,
            score=total_score,
            factors=factors,
            reasoning=reasoning
        )
    
    def _determine_performance_requirement(
        self,
        request: AuthorizationRequest,
        complexity: RequestComplexity
    ) -> PerformanceRequirement:
        """Determine performance requirement based on request characteristics."""
        
        # Urgent requests need fast processing
        if hasattr(request, 'urgency_level') and request.urgency_level == UrgencyLevel.URGENT:
            return PerformanceRequirement.FAST
        
        # Simple requests can use fast processing
        if complexity.level == ComplexityLevel.SIMPLE:
            return PerformanceRequirement.FAST
        
        # Moderate complexity uses standard processing
        if complexity.level == ComplexityLevel.MODERATE:
            return PerformanceRequirement.STANDARD
        
        # Complex requests need thorough processing
        if complexity.level == ComplexityLevel.COMPLEX:
            return PerformanceRequirement.THOROUGH
        
        # Very complex requests get comprehensive processing
        return PerformanceRequirement.COMPREHENSIVE
    
    async def _get_available_models(self, exclude_models: Optional[List[str]] = None) -> List[ModelConfig]:
        """Get list of available and healthy models."""
        available_models = []
        exclude_models = exclude_models or []
        
        for model_config in llm_config.get_enabled_models():
            if model_config.model_id in exclude_models:
                continue
            
            # Check model health
            model_health = model_manager.get_model_health(model_config.model_id)
            if model_health and model_health.status == ModelStatus.HEALTHY:
                available_models.append(model_config)
            elif not model_health:
                # If no health info, assume available (will be checked during processing)
                available_models.append(model_config)
        
        return available_models
    
    async def _score_models(
        self,
        models: List[ModelConfig],
        complexity: RequestComplexity,
        performance_requirement: PerformanceRequirement
    ) -> Dict[str, float]:
        """Score models based on suitability for the request."""
        scores = {}
        
        for model in models:
            score = 0.0
            
            # Base score from model priority (lower priority number = higher score)
            priority_score = (11 - model.priority) / 10.0  # Normalize to 0-1
            score += priority_score * 0.2
            
            # Performance metrics score
            if model.model_id in self._model_metrics:
                metrics = self._model_metrics[model.model_id]
                
                # Success rate score
                score += metrics.success_rate * 0.3
                
                # Confidence score
                score += metrics.confidence_score_avg * 0.2
                
                # Complexity handling score
                complexity_score = metrics.complexity_handling.get(complexity.level, 0.5)
                score += complexity_score * 0.2
                
                # Performance requirement score
                required_time = self.performance_thresholds[performance_requirement]
                if metrics.average_response_time_ms > 0:
                    time_score = max(0, 1 - (metrics.average_response_time_ms / required_time))
                    score += time_score * 0.1
                else:
                    score += 0.05  # Default for models without timing data
            else:
                # Default score for models without metrics
                score += 0.5
            
            scores[model.model_id] = min(1.0, score)  # Cap at 1.0
        
        return scores
    
    def _generate_selection_reasoning(
        self,
        selected_model: ModelConfig,
        complexity: RequestComplexity,
        performance_requirement: PerformanceRequirement,
        score: float
    ) -> str:
        """Generate human-readable reasoning for model selection."""
        reasoning_parts = [
            f"Selected {selected_model.name} (score: {score:.3f})",
            f"Request complexity: {complexity.level.value} ({complexity.score:.2f})",
            f"Performance requirement: {performance_requirement.value}"
        ]
        
        # Add performance metrics if available
        if selected_model.model_id in self._model_metrics:
            metrics = self._model_metrics[selected_model.model_id]
            reasoning_parts.append(
                f"Model metrics: {metrics.success_rate:.1%} success rate, "
                f"{metrics.average_response_time_ms:.0f}ms avg response time"
            )
        
        # Add complexity handling info
        if (selected_model.model_id in self._model_metrics and 
            complexity.level in self._model_metrics[selected_model.model_id].complexity_handling):
            complexity_score = self._model_metrics[selected_model.model_id].complexity_handling[complexity.level]
            reasoning_parts.append(f"Complexity handling score: {complexity_score:.2f}")
        
        return "; ".join(reasoning_parts)
    
    async def _cache_metrics(self):
        """Cache model performance metrics."""
        try:
            cache_data = {
                'metrics': {
                    model_id: {
                        'model_id': metrics.model_id,
                        'average_response_time_ms': metrics.average_response_time_ms,
                        'success_rate': metrics.success_rate,
                        'confidence_score_avg': metrics.confidence_score_avg,
                        'complexity_handling': dict(metrics.complexity_handling),
                        'request_count': metrics.request_count,
                        'error_count': metrics.error_count,
                        'last_updated': metrics.last_updated.isoformat()
                    }
                    for model_id, metrics in self._model_metrics.items()
                },
                'cached_at': datetime.now(timezone.utc).isoformat()
            }
            
            await self.cache.set(
                'model_selection:performance_metrics',
                cache_data,
                ttl=3600 * 24  # 24 hours
            )
            
        except Exception as e:
            self.logger.error(f"Error caching model metrics: {str(e)}")
    
    async def _load_cached_metrics(self):
        """Load cached model performance metrics."""
        try:
            cache_data = await self.cache.get('model_selection:performance_metrics')
            if not cache_data:
                return
            
            metrics_data = cache_data.get('metrics', {})
            for model_id, data in metrics_data.items():
                metrics = ModelPerformanceMetrics(
                    model_id=data['model_id'],
                    average_response_time_ms=data['average_response_time_ms'],
                    success_rate=data['success_rate'],
                    confidence_score_avg=data['confidence_score_avg'],
                    request_count=data['request_count'],
                    error_count=data['error_count'],
                    last_updated=datetime.fromisoformat(data['last_updated'])
                )
                
                # Restore complexity handling
                for complexity_str, score in data['complexity_handling'].items():
                    try:
                        complexity_level = ComplexityLevel(complexity_str)
                        metrics.complexity_handling[complexity_level] = score
                    except ValueError:
                        continue
                
                self._model_metrics[model_id] = metrics
            
            self.logger.info(f"Loaded cached metrics for {len(metrics_data)} models")
            
        except Exception as e:
            self.logger.error(f"Error loading cached metrics: {str(e)}")


# Global intelligent model selection service instance
intelligent_model_selection_service = IntelligentModelSelectionService()
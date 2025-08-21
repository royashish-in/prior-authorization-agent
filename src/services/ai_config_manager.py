"""
AI Configuration Management Service

This service manages AI configuration including LLM model selection,
decision thresholds, escalation rules, and clinical guidelines.
"""

import json
import logging
from datetime import date, datetime, timezone
from typing import List, Dict, Optional, Any, Tuple
from uuid import uuid4

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

from src.database.models import (
    AIConfigurationDB, ModelPerformanceMetricsDB, 
    ConfigurationAuditLogDB, AIFeedbackDB
)
from src.models.ai_config import (
    ConfigurationType, LLMModelConfiguration, DecisionThresholdConfig,
    EscalationRuleConfig, ClinicalGuidelineConfig, FeedbackConfig,
    AIConfigurationRequest, AIConfigurationResponse,
    ConfigurationValidationResult, ModelPerformanceMetrics,
    ModelSelectionStrategy
)
from src.services.llm_config import LLMConfigManager
from src.services.medical_code_validator import MedicalCodeValidator


logger = logging.getLogger(__name__)


class AIConfigurationManager:
    """
    Service for managing AI configuration with version control and validation.
    
    Provides functionality for creating, updating, and managing AI configurations
    including LLM models, decision thresholds, escalation rules, and clinical guidelines.
    """
    
    def __init__(self, db_session: Session):
        """Initialize the AI configuration manager."""
        self.db_session = db_session
        self.logger = logging.getLogger(__name__)
        self.llm_config_manager = LLMConfigManager()
        self.medical_code_validator = MedicalCodeValidator()
    
    async def create_configuration(
        self,
        config_request: AIConfigurationRequest,
        created_by: str
    ) -> str:
        """
        Create a new AI configuration with validation.
        
        Args:
            config_request: Configuration request data
            created_by: User ID who created the configuration
            
        Returns:
            Configuration ID of the created configuration
        """
        try:
            # Validate configuration data
            validation_result = await self._validate_configuration_data(
                config_request.configuration_type,
                config_request.configuration_data
            )
            if not validation_result.is_valid:
                raise ValueError(f"Configuration validation failed: {validation_result.validation_errors}")
            
            # Generate configuration ID
            config_id = f"cfg_{config_request.configuration_type.value}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
            
            # Create configuration record
            config = AIConfigurationDB(
                config_id=config_id,
                configuration_type=config_request.configuration_type.value,
                configuration_name=config_request.configuration_data.get('name', f"Configuration {config_id}"),
                configuration_version="1.0",
                configuration_data=config_request.configuration_data,
                effective_date=config_request.effective_date or date.today(),
                expiration_date=config_request.expiration_date,
                is_active=config_request.is_active,
                created_by=created_by,
                updated_by=created_by
            )
            
            self.db_session.add(config)
            self.db_session.commit()
            
            # Create audit log
            await self._create_audit_log(
                configuration_type=config_request.configuration_type.value,
                config_id=config_id,
                action="CREATE",
                new_values=config_request.configuration_data,
                user_id=created_by,
                reason="Configuration created"
            )
            
            # Apply configuration if it's currently effective
            if config.is_currently_effective():
                await self._apply_configuration(config)
            
            self.logger.info(f"AI configuration created successfully: {config_id}")
            return config_id
            
        except Exception as e:
            self.db_session.rollback()
            self.logger.error(f"Failed to create AI configuration: {str(e)}")
            raise
    
    async def update_configuration(
        self,
        config_id: str,
        update_data: Dict[str, Any],
        updated_by: str,
        update_reason: str
    ) -> Optional[AIConfigurationDB]:
        """
        Update an existing configuration with version control.
        
        Args:
            config_id: Configuration identifier
            update_data: Fields to update
            updated_by: User ID who updated the configuration
            update_reason: Reason for the update
            
        Returns:
            Updated configuration record or None if not found
        """
        try:
            # Get existing configuration
            config = self.get_configuration_by_id(config_id)
            if not config:
                return None
            
            # Store old values for audit
            old_values = config.configuration_data.copy()
            
            # Validate update data
            if 'configuration_data' in update_data:
                validation_result = await self._validate_configuration_data(
                    ConfigurationType(config.configuration_type),
                    update_data['configuration_data']
                )
                if not validation_result.is_valid:
                    raise ValueError(f"Configuration validation failed: {validation_result.validation_errors}")
            
            # Update configuration fields
            for field, value in update_data.items():
                if hasattr(config, field) and field not in ['config_id', 'created_at', 'created_by']:
                    setattr(config, field, value)
            
            # Update metadata
            config.updated_by = updated_by
            config.updated_at = datetime.now(timezone.utc)
            
            # Increment version
            current_version = float(config.configuration_version)
            new_version = f"{current_version + 0.1:.1f}"
            config.configuration_version = new_version
            
            self.db_session.commit()
            
            # Create audit log
            await self._create_audit_log(
                configuration_type=config.configuration_type,
                config_id=config_id,
                action="UPDATE",
                old_values=old_values,
                new_values=config.configuration_data,
                user_id=updated_by,
                reason=update_reason
            )
            
            # Apply updated configuration if it's currently effective
            if config.is_currently_effective():
                await self._apply_configuration(config)
            
            self.logger.info(f"AI configuration updated successfully: {config_id} to version {new_version}")
            return config
            
        except Exception as e:
            self.db_session.rollback()
            self.logger.error(f"Failed to update AI configuration {config_id}: {str(e)}")
            raise
    
    async def deactivate_configuration(
        self,
        config_id: str,
        deactivated_by: str
    ) -> bool:
        """
        Deactivate a configuration (soft delete).
        
        Args:
            config_id: Configuration identifier
            deactivated_by: User ID who deactivated the configuration
            
        Returns:
            True if successful, False if configuration not found
        """
        try:
            config = self.get_configuration_by_id(config_id)
            if not config:
                return False
            
            old_values = {"is_active": config.is_active}
            
            config.is_active = False
            config.updated_by = deactivated_by
            config.updated_at = datetime.now(timezone.utc)
            
            self.db_session.commit()
            
            # Create audit log
            await self._create_audit_log(
                configuration_type=config.configuration_type,
                config_id=config_id,
                action="DEACTIVATE",
                old_values=old_values,
                new_values={"is_active": False},
                user_id=deactivated_by,
                reason="Configuration deactivated"
            )
            
            self.logger.info(f"AI configuration deactivated successfully: {config_id}")
            return True
            
        except Exception as e:
            self.db_session.rollback()
            self.logger.error(f"Failed to deactivate AI configuration {config_id}: {str(e)}")
            raise
    
    def get_configuration_by_id(self, config_id: str) -> Optional[AIConfigurationDB]:
        """
        Retrieve a configuration by its ID.
        
        Args:
            config_id: Configuration identifier
            
        Returns:
            Configuration record or None if not found
        """
        return self.db_session.query(AIConfigurationDB).filter(
            AIConfigurationDB.config_id == config_id
        ).first()
    
    def list_configurations(
        self,
        configuration_type: Optional[ConfigurationType] = None,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0
    ) -> List[AIConfigurationDB]:
        """
        List configurations with filtering options.
        
        Args:
            configuration_type: Filter by configuration type
            active_only: Whether to return only active configurations
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of configuration records
        """
        query = self.db_session.query(AIConfigurationDB)
        
        # Apply filters
        if configuration_type:
            query = query.filter(AIConfigurationDB.configuration_type == configuration_type.value)
        
        if active_only:
            query = query.filter(
                and_(
                    AIConfigurationDB.is_active == True,
                    AIConfigurationDB.effective_date <= date.today(),
                    or_(
                        AIConfigurationDB.expiration_date.is_(None),
                        AIConfigurationDB.expiration_date >= date.today()
                    )
                )
            )
        
        # Apply pagination and ordering
        query = query.order_by(desc(AIConfigurationDB.updated_at))
        query = query.offset(offset).limit(limit)
        
        return query.all()
    
    async def get_effective_configuration(
        self,
        configuration_type: ConfigurationType,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[AIConfigurationDB]:
        """
        Get the currently effective configuration of a specific type.
        
        Args:
            configuration_type: Type of configuration to retrieve
            context: Additional context for configuration selection
            
        Returns:
            Effective configuration or None if not found
        """
        query = self.db_session.query(AIConfigurationDB).filter(
            and_(
                AIConfigurationDB.configuration_type == configuration_type.value,
                AIConfigurationDB.is_active == True,
                AIConfigurationDB.effective_date <= date.today(),
                or_(
                    AIConfigurationDB.expiration_date.is_(None),
                    AIConfigurationDB.expiration_date >= date.today()
                )
            )
        ).order_by(desc(AIConfigurationDB.effective_date))
        
        return query.first()
    
    async def select_optimal_model(
        self,
        strategy: ModelSelectionStrategy = ModelSelectionStrategy.PRIORITY_BASED,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Select the optimal LLM model based on strategy and context.
        
        Args:
            strategy: Model selection strategy
            context: Request context for model selection
            
        Returns:
            Selected model ID or None if no suitable model found
        """
        try:
            # Get active LLM model configurations
            model_configs = self.list_configurations(
                configuration_type=ConfigurationType.LLM_MODEL,
                active_only=True
            )
            
            if not model_configs:
                return None
            
            if strategy == ModelSelectionStrategy.PRIORITY_BASED:
                # Select based on configured priority
                best_config = min(
                    model_configs,
                    key=lambda c: c.configuration_data.get('priority', 999)
                )
                return best_config.configuration_data.get('model_id')
            
            elif strategy == ModelSelectionStrategy.PERFORMANCE_BASED:
                # Select based on performance metrics
                return await self._select_by_performance(model_configs)
            
            elif strategy == ModelSelectionStrategy.COST_OPTIMIZED:
                # Select based on cost efficiency
                return await self._select_by_cost(model_configs)
            
            elif strategy == ModelSelectionStrategy.COMPLEXITY_BASED:
                # Select based on request complexity
                return await self._select_by_complexity(model_configs, context)
            
            else:
                # Default to priority-based
                best_config = min(
                    model_configs,
                    key=lambda c: c.configuration_data.get('priority', 999)
                )
                return best_config.configuration_data.get('model_id')
                
        except Exception as e:
            self.logger.error(f"Failed to select optimal model: {str(e)}")
            return None
    
    async def record_model_performance(
        self,
        model_id: str,
        performance_data: Dict[str, Any]
    ) -> str:
        """
        Record performance metrics for a model.
        
        Args:
            model_id: Model identifier
            performance_data: Performance metrics data
            
        Returns:
            Metric record ID
        """
        try:
            metric_id = f"metric_{model_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
            
            metrics = ModelPerformanceMetricsDB(
                metric_id=metric_id,
                model_id=model_id,
                model_name=performance_data.get('model_name', model_id),
                accuracy_score=performance_data.get('accuracy_score', 0.0),
                precision_score=performance_data.get('precision_score', 0.0),
                recall_score=performance_data.get('recall_score', 0.0),
                f1_score=performance_data.get('f1_score', 0.0),
                average_response_time_ms=performance_data.get('average_response_time_ms', 0.0),
                success_rate=performance_data.get('success_rate', 0.0),
                error_rate=performance_data.get('error_rate', 0.0),
                total_requests=performance_data.get('total_requests', 0),
                successful_requests=performance_data.get('successful_requests', 0),
                failed_requests=performance_data.get('failed_requests', 0),
                total_cost=performance_data.get('total_cost', 0.0),
                cost_per_request=performance_data.get('cost_per_request', 0.0),
                measurement_start=performance_data.get('measurement_start', datetime.now(timezone.utc)),
                measurement_end=performance_data.get('measurement_end', datetime.now(timezone.utc))
            )
            
            self.db_session.add(metrics)
            self.db_session.commit()
            
            self.logger.info(f"Model performance recorded: {model_id}")
            return metric_id
            
        except Exception as e:
            self.db_session.rollback()
            self.logger.error(f"Failed to record model performance for {model_id}: {str(e)}")
            raise
    
    async def record_feedback(
        self,
        decision_id: str,
        request_id: str,
        feedback_data: Dict[str, Any],
        source_user_id: str
    ) -> str:
        """
        Record feedback on an AI decision.
        
        Args:
            decision_id: Decision identifier
            request_id: Request identifier
            feedback_data: Feedback data
            source_user_id: User providing feedback
            
        Returns:
            Feedback record ID
        """
        try:
            feedback_id = f"feedback_{decision_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
            
            feedback = AIFeedbackDB(
                feedback_id=feedback_id,
                decision_id=decision_id,
                request_id=request_id,
                feedback_type=feedback_data.get('feedback_type', 'decision_accuracy'),
                feedback_score=feedback_data.get('feedback_score', 0.0),
                feedback_text=feedback_data.get('feedback_text'),
                feedback_source=feedback_data.get('feedback_source', 'PROVIDER'),
                source_user_id=source_user_id,
                source_role=feedback_data.get('source_role'),
                model_id=feedback_data.get('model_id', ''),
                model_version=feedback_data.get('model_version'),
                original_confidence=feedback_data.get('original_confidence', 0.0)
            )
            
            self.db_session.add(feedback)
            self.db_session.commit()
            
            # Process feedback if auto-processing is enabled
            await self._process_feedback_if_enabled(feedback)
            
            self.logger.info(f"AI feedback recorded: {feedback_id}")
            return feedback_id
            
        except Exception as e:
            self.db_session.rollback()
            self.logger.error(f"Failed to record AI feedback: {str(e)}")
            raise
    
    async def validate_configuration(
        self,
        config_id: str
    ) -> ConfigurationValidationResult:
        """
        Validate a configuration and check for conflicts.
        
        Args:
            config_id: Configuration identifier
            
        Returns:
            Validation result
        """
        try:
            config = self.get_configuration_by_id(config_id)
            if not config:
                return ConfigurationValidationResult(
                    is_valid=False,
                    validation_errors=['Configuration not found'],
                    warnings=[],
                    recommendations=[]
                )
            
            return await self._validate_configuration_data(
                ConfigurationType(config.configuration_type),
                config.configuration_data
            )
            
        except Exception as e:
            self.logger.error(f"Configuration validation failed for {config_id}: {str(e)}")
            return ConfigurationValidationResult(
                is_valid=False,
                validation_errors=[f"Validation error: {str(e)}"],
                warnings=[],
                recommendations=[]
            )
    
    async def _validate_configuration_data(
        self,
        config_type: ConfigurationType,
        config_data: Dict[str, Any]
    ) -> ConfigurationValidationResult:
        """Validate configuration data based on type."""
        errors = []
        warnings = []
        recommendations = []
        
        try:
            if config_type == ConfigurationType.LLM_MODEL:
                # Validate LLM model configuration
                errors.extend(await self._validate_llm_model_config(config_data))
            
            elif config_type == ConfigurationType.DECISION_THRESHOLD:
                # Validate decision threshold configuration
                errors.extend(await self._validate_decision_threshold_config(config_data))
            
            elif config_type == ConfigurationType.ESCALATION_RULE:
                # Validate escalation rule configuration
                errors.extend(await self._validate_escalation_rule_config(config_data))
            
            elif config_type == ConfigurationType.CLINICAL_GUIDELINE:
                # Validate clinical guideline configuration
                errors.extend(await self._validate_clinical_guideline_config(config_data))
            
            elif config_type == ConfigurationType.FEEDBACK_RULE:
                # Validate feedback configuration
                errors.extend(await self._validate_feedback_config(config_data))
            
        except Exception as e:
            errors.append(f"Validation error: {str(e)}")
        
        return ConfigurationValidationResult(
            is_valid=len(errors) == 0,
            validation_errors=errors,
            warnings=warnings,
            recommendations=recommendations
        )
    
    async def _validate_llm_model_config(self, config_data: Dict[str, Any]) -> List[str]:
        """Validate LLM model configuration."""
        errors = []
        
        # Required fields
        required_fields = ['model_id', 'model_name', 'deployment_type', 'model_type']
        for field in required_fields:
            if field not in config_data or not config_data[field]:
                errors.append(f"Missing required field: {field}")
        
        # Validate numeric ranges
        if 'temperature' in config_data:
            temp = config_data['temperature']
            if not isinstance(temp, (int, float)) or not 0.0 <= temp <= 2.0:
                errors.append("Temperature must be between 0.0 and 2.0")
        
        if 'confidence_threshold' in config_data:
            threshold = config_data['confidence_threshold']
            if not isinstance(threshold, (int, float)) or not 0.0 <= threshold <= 1.0:
                errors.append("Confidence threshold must be between 0.0 and 1.0")
        
        return errors
    
    async def _validate_decision_threshold_config(self, config_data: Dict[str, Any]) -> List[str]:
        """Validate decision threshold configuration."""
        errors = []
        
        # Required fields
        required_fields = ['auto_approve_threshold', 'auto_deny_threshold', 'manual_review_threshold']
        for field in required_fields:
            if field not in config_data:
                errors.append(f"Missing required field: {field}")
        
        # Validate threshold relationships
        if all(field in config_data for field in required_fields):
            approve = config_data['auto_approve_threshold']
            deny = config_data['auto_deny_threshold']
            review = config_data['manual_review_threshold']
            
            if deny >= approve:
                errors.append("Auto deny threshold must be less than auto approve threshold")
            if review >= deny:
                errors.append("Manual review threshold must be less than auto deny threshold")
        
        return errors
    
    async def _validate_escalation_rule_config(self, config_data: Dict[str, Any]) -> List[str]:
        """Validate escalation rule configuration."""
        errors = []
        
        # Required fields
        required_fields = ['triggers', 'escalation_queue']
        for field in required_fields:
            if field not in config_data or not config_data[field]:
                errors.append(f"Missing required field: {field}")
        
        return errors
    
    async def _validate_clinical_guideline_config(self, config_data: Dict[str, Any]) -> List[str]:
        """Validate clinical guideline configuration."""
        errors = []
        
        # Required fields
        required_fields = ['guideline_name', 'guideline_text']
        for field in required_fields:
            if field not in config_data or not config_data[field]:
                errors.append(f"Missing required field: {field}")
        
        # Validate medical codes if present
        if 'applicable_procedures' in config_data:
            for code in config_data['applicable_procedures']:
                if not self.medical_code_validator.validate_cpt_code(code):
                    errors.append(f"Invalid CPT code: {code}")
        
        if 'applicable_diagnoses' in config_data:
            for code in config_data['applicable_diagnoses']:
                if not self.medical_code_validator.validate_icd10_code(code):
                    errors.append(f"Invalid ICD-10 code: {code}")
        
        return errors
    
    async def _validate_feedback_config(self, config_data: Dict[str, Any]) -> List[str]:
        """Validate feedback configuration."""
        errors = []
        
        # Required fields
        required_fields = ['feedback_types']
        for field in required_fields:
            if field not in config_data or not config_data[field]:
                errors.append(f"Missing required field: {field}")
        
        return errors
    
    async def _apply_configuration(self, config: AIConfigurationDB) -> None:
        """Apply a configuration to the system."""
        try:
            if config.configuration_type == 'llm_model':
                # Update LLM configuration manager
                await self._apply_llm_model_config(config)
            
            # Add other configuration type applications as needed
            
        except Exception as e:
            self.logger.error(f"Failed to apply configuration {config.config_id}: {str(e)}")
    
    async def _apply_llm_model_config(self, config: AIConfigurationDB) -> None:
        """Apply LLM model configuration."""
        # This would integrate with the LLM configuration manager
        # to update active model configurations
        pass
    
    async def _create_audit_log(
        self,
        configuration_type: str,
        config_id: str,
        action: str,
        user_id: str,
        reason: str,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create an audit log entry."""
        try:
            audit_id = f"audit_{config_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
            
            audit_log = ConfigurationAuditLogDB(
                audit_id=audit_id,
                configuration_type=configuration_type,
                config_id=config_id,
                action=action,
                old_values=old_values,
                new_values=new_values,
                user_id=user_id,
                user_role="",  # This would be populated from user context
                reason=reason
            )
            
            self.db_session.add(audit_log)
            self.db_session.commit()
            
        except Exception as e:
            self.logger.error(f"Failed to create audit log: {str(e)}")
    
    async def _select_by_performance(self, model_configs: List[AIConfigurationDB]) -> Optional[str]:
        """Select model based on performance metrics."""
        # Get recent performance metrics for each model
        best_model = None
        best_score = 0.0
        
        for config in model_configs:
            model_id = config.configuration_data.get('model_id')
            if not model_id:
                continue
            
            # Get latest performance metrics
            metrics = self.db_session.query(ModelPerformanceMetricsDB).filter(
                ModelPerformanceMetricsDB.model_id == model_id
            ).order_by(desc(ModelPerformanceMetricsDB.measurement_end)).first()
            
            if metrics:
                # Calculate composite performance score
                score = (
                    metrics.accuracy_score * 0.4 +
                    metrics.f1_score * 0.3 +
                    metrics.success_rate * 0.2 +
                    (1.0 - min(metrics.average_response_time_ms / 10000.0, 1.0)) * 0.1
                )
                
                if score > best_score:
                    best_score = score
                    best_model = model_id
        
        return best_model
    
    async def _select_by_cost(self, model_configs: List[AIConfigurationDB]) -> Optional[str]:
        """Select model based on cost efficiency."""
        best_model = None
        best_efficiency = 0.0
        
        for config in model_configs:
            model_id = config.configuration_data.get('model_id')
            if not model_id:
                continue
            
            # Get latest performance metrics
            metrics = self.db_session.query(ModelPerformanceMetricsDB).filter(
                ModelPerformanceMetricsDB.model_id == model_id
            ).order_by(desc(ModelPerformanceMetricsDB.measurement_end)).first()
            
            if metrics and metrics.cost_per_request > 0:
                # Calculate cost efficiency (accuracy per dollar)
                efficiency = metrics.accuracy_score / metrics.cost_per_request
                
                if efficiency > best_efficiency:
                    best_efficiency = efficiency
                    best_model = model_id
        
        return best_model
    
    async def _select_by_complexity(
        self,
        model_configs: List[AIConfigurationDB],
        context: Optional[Dict[str, Any]]
    ) -> Optional[str]:
        """Select model based on request complexity."""
        if not context:
            # Default to priority-based if no context
            best_config = min(
                model_configs,
                key=lambda c: c.configuration_data.get('priority', 999)
            )
            return best_config.configuration_data.get('model_id')
        
        # Analyze request complexity (simplified)
        complexity_score = 0
        
        # Add complexity based on number of diagnoses
        if 'diagnosis_codes' in context:
            complexity_score += len(context['diagnosis_codes']) * 0.1
        
        # Add complexity based on clinical notes length
        if 'clinical_notes' in context and context['clinical_notes']:
            complexity_score += min(len(context['clinical_notes']) / 1000.0, 1.0)
        
        # Select model based on complexity
        if complexity_score > 0.7:
            # High complexity - use most capable model
            best_config = min(
                model_configs,
                key=lambda c: c.configuration_data.get('priority', 999)
            )
        elif complexity_score > 0.3:
            # Medium complexity - use balanced model
            medium_priority_configs = [
                c for c in model_configs
                if 2 <= c.configuration_data.get('priority', 999) <= 4
            ]
            if medium_priority_configs:
                best_config = min(
                    medium_priority_configs,
                    key=lambda c: c.configuration_data.get('priority', 999)
                )
            else:
                best_config = min(
                    model_configs,
                    key=lambda c: c.configuration_data.get('priority', 999)
                )
        else:
            # Low complexity - use fastest/cheapest model
            fast_configs = [
                c for c in model_configs
                if c.configuration_data.get('priority', 999) >= 5
            ]
            if fast_configs:
                best_config = min(
                    fast_configs,
                    key=lambda c: c.configuration_data.get('priority', 999)
                )
            else:
                best_config = min(
                    model_configs,
                    key=lambda c: c.configuration_data.get('priority', 999)
                )
        
        return best_config.configuration_data.get('model_id')
    
    async def _process_feedback_if_enabled(self, feedback: AIFeedbackDB) -> None:
        """Process feedback if auto-processing is enabled."""
        try:
            # Get feedback configuration
            feedback_config = await self.get_effective_configuration(
                ConfigurationType.FEEDBACK_RULE
            )
            
            if (feedback_config and 
                feedback_config.configuration_data.get('auto_process_feedback', False)):
                
                # Mark feedback as processed
                feedback.processed = True
                feedback.processed_at = datetime.now(timezone.utc)
                feedback.processing_notes = "Auto-processed based on configuration"
                
                self.db_session.commit()
                
                # Here you would implement the actual learning logic
                # This could involve updating model parameters, retraining, etc.
                
        except Exception as e:
            self.logger.error(f"Failed to process feedback {feedback.feedback_id}: {str(e)}")


# Global configuration manager instance
ai_config_manager = None

def get_ai_config_manager(db_session: Session) -> AIConfigurationManager:
    """Get or create AI configuration manager instance."""
    global ai_config_manager
    if ai_config_manager is None:
        ai_config_manager = AIConfigurationManager(db_session)
    return ai_config_manager
"""
LLM Audit Logger Service

This service provides comprehensive audit logging specifically for LLM operations,
AI decisions, and data access in the enhanced decision engine. It extends the
base audit logger with LLM-specific event types and detailed tracking.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum

from src.audit.logger import get_audit_logger
from src.audit.models import AuditEventType, SecurityLevel
from src.models.authorization import AuthorizationRequest, AuthorizationDecision
from src.services.llm_decision_service import LLMDecisionResponse
from src.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMAuditEventType(str, Enum):
    """Extended audit event types specific to LLM operations."""
    # LLM Model Operations
    LLM_MODEL_LOADED = "llm_model_loaded"
    LLM_MODEL_UNLOADED = "llm_model_unloaded"
    LLM_MODEL_CONFIGURED = "llm_model_configured"
    LLM_MODEL_HEALTH_CHECK = "llm_model_health_check"
    LLM_MODEL_FALLBACK = "llm_model_fallback"
    
    # LLM Decision Process
    LLM_DECISION_INITIATED = "llm_decision_initiated"
    LLM_DECISION_COMPLETED = "llm_decision_completed"
    LLM_DECISION_FAILED = "llm_decision_failed"
    LLM_DECISION_OVERRIDDEN = "llm_decision_overridden"
    LLM_DECISION_EXPLAINED = "llm_decision_explained"
    
    # LLM Data Processing
    LLM_DATA_PREPARED = "llm_data_prepared"
    LLM_PHI_DEIDENTIFIED = "llm_phi_deidentified"
    LLM_PROMPT_GENERATED = "llm_prompt_generated"
    LLM_RESPONSE_PARSED = "llm_response_parsed"
    LLM_RESPONSE_VALIDATED = "llm_response_validated"
    
    # LLM External Communications
    LLM_API_CALL_INITIATED = "llm_api_call_initiated"
    LLM_API_CALL_COMPLETED = "llm_api_call_completed"
    LLM_API_CALL_FAILED = "llm_api_call_failed"
    LLM_API_RATE_LIMITED = "llm_api_rate_limited"
    
    # LLM Configuration Changes
    LLM_CONFIG_UPDATED = "llm_config_updated"
    LLM_THRESHOLD_CHANGED = "llm_threshold_changed"
    LLM_PROMPT_TEMPLATE_UPDATED = "llm_prompt_template_updated"
    LLM_FEEDBACK_PROCESSED = "llm_feedback_processed"
    
    # LLM Performance and Monitoring
    LLM_PERFORMANCE_DEGRADED = "llm_performance_degraded"
    LLM_CONFIDENCE_LOW = "llm_confidence_low"
    LLM_VALIDATION_FAILED = "llm_validation_failed"
    LLM_ANOMALY_DETECTED = "llm_anomaly_detected"


@dataclass
class LLMDecisionAuditData:
    """Comprehensive audit data for LLM decisions."""
    # Request information
    request_id: str
    authorization_request: Dict[str, Any]
    
    # LLM processing details
    model_used: str
    model_version: Optional[str] = None
    prompt_template: str = ""
    prompt_version: str = ""
    processing_time_ms: float = 0.0
    
    # Decision details
    decision: str = ""
    confidence_score: float = 0.0
    medical_reasoning: str = ""
    policy_compliance: Dict[str, Any] = field(default_factory=dict)
    
    # Data handling
    phi_involved: bool = True
    data_deidentified: bool = False
    external_api_used: bool = False
    
    # Quality metrics
    validation_errors: List[str] = field(default_factory=list)
    fallback_used: bool = False
    human_review_required: bool = False
    
    # Additional context
    alternative_procedures: List[Dict[str, Any]] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)
    contraindications: List[str] = field(default_factory=list)


@dataclass
class LLMModelAuditData:
    """Audit data for LLM model operations."""
    model_id: str
    model_name: str
    model_type: str
    deployment_type: str
    
    # Configuration
    model_config: Dict[str, Any] = field(default_factory=dict)
    performance_metrics: Dict[str, Any] = field(default_factory=dict)
    
    # Health and status
    health_status: str = ""
    error_message: Optional[str] = None
    resource_usage: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMDataProcessingAuditData:
    """Audit data for LLM data processing operations."""
    operation_type: str
    data_types_processed: List[str]
    
    # PHI handling
    phi_fields_identified: List[str] = field(default_factory=list)
    deidentification_method: Optional[str] = None
    deidentification_success: bool = False
    
    # Data transformation
    input_data_size: int = 0
    output_data_size: int = 0
    transformation_applied: List[str] = field(default_factory=list)
    
    # Security
    encryption_used: bool = False
    secure_transmission: bool = False
    data_retention_policy: Optional[str] = None


class LLMAuditLogger:
    """
    Comprehensive audit logger for LLM operations and AI decisions.
    
    Provides detailed audit logging for all LLM-related activities including
    decision making, data processing, model operations, and compliance tracking.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.base_audit_logger = get_audit_logger()
        self.settings = get_settings()
    
    async def log_llm_decision_initiated(
        self,
        request_id: str,
        authorization_request: AuthorizationRequest,
        user_id: str,
        client_ip: str = "unknown",
        **kwargs
    ) -> str:
        """Log the initiation of an LLM decision process."""
        try:
            audit_data = {
                "request_id": request_id,
                "patient_id": authorization_request.patient_id,
                "procedure_codes": authorization_request.procedure_codes,
                "diagnosis_codes": authorization_request.diagnosis_codes,
                "urgency_level": authorization_request.urgency_level.value if authorization_request.urgency_level else None,
                "provider_id": authorization_request.provider_id,
                "payer_id": authorization_request.payer_id,
                "clinical_notes_length": len(authorization_request.clinical_notes or ""),
                "has_supporting_docs": bool(authorization_request.supporting_documents),
                **kwargs
            }
            
            return self.base_audit_logger.log_event(
                event_type=AuditEventType.LLM_REQUEST_INITIATED,
                action="llm_decision_initiated",
                outcome="initiated",
                user_id=user_id,
                client_ip=client_ip,
                resource_type="llm_decision",
                resource_id=request_id,
                security_level=SecurityLevel.HIGH,
                phi_involved=True,
                compliance_flags=["HIPAA", "AI_DECISION"],
                details=audit_data
            )
            
        except Exception as e:
            self.logger.error(f"Failed to log LLM decision initiation: {str(e)}")
            raise
    
    async def log_llm_decision_completed(
        self,
        request_id: str,
        llm_response: LLMDecisionResponse,
        user_id: str,
        client_ip: str = "unknown",
        **kwargs
    ) -> str:
        """Log the completion of an LLM decision process."""
        try:
            audit_data = LLMDecisionAuditData(
                request_id=request_id,
                authorization_request={},  # Populated from context if needed
                model_used=llm_response.model_used,
                prompt_template=llm_response.template_used,
                processing_time_ms=llm_response.processing_time_ms,
                decision=llm_response.decision.value,
                confidence_score=llm_response.confidence_score,
                medical_reasoning=llm_response.medical_reasoning[:500],  # Truncate for audit
                policy_compliance={
                    "compliant": llm_response.policy_compliance.compliant,
                    "analysis": llm_response.policy_compliance.analysis[:200],
                    "violated_criteria": llm_response.policy_compliance.violated_criteria
                },
                validation_errors=llm_response.validation_errors,
                fallback_used=llm_response.fallback_used,
                human_review_required=llm_response.confidence_score < 0.7,
                alternative_procedures=[
                    {"procedure": alt.procedure, "rationale": alt.rationale[:100]}
                    for alt in llm_response.alternative_procedures
                ],
                risk_factors=llm_response.risk_assessment.risk_factors,
                contraindications=llm_response.risk_assessment.contraindications
            )
            
            return self.base_audit_logger.log_event(
                event_type=AuditEventType.LLM_REQUEST_COMPLETED,
                action="llm_decision_completed",
                outcome="success",
                user_id=user_id,
                client_ip=client_ip,
                resource_type="llm_decision",
                resource_id=request_id,
                security_level=SecurityLevel.HIGH,
                phi_involved=True,
                compliance_flags=["HIPAA", "AI_DECISION"],
                duration_ms=int(llm_response.processing_time_ms),
                details=audit_data.__dict__,
                **kwargs
            )
            
        except Exception as e:
            self.logger.error(f"Failed to log LLM decision completion: {str(e)}")
            raise
    
    async def log_llm_decision_failed(
        self,
        request_id: str,
        error_message: str,
        model_id: str,
        user_id: str,
        client_ip: str = "unknown",
        **kwargs
    ) -> str:
        """Log a failed LLM decision process."""
        try:
            audit_data = {
                "request_id": request_id,
                "model_id": model_id,
                "error_message": error_message,
                "fallback_attempted": kwargs.get("fallback_attempted", False),
                "fallback_successful": kwargs.get("fallback_successful", False),
                **kwargs
            }
            
            return self.base_audit_logger.log_event(
                event_type=AuditEventType.LLM_REQUEST_FAILED,
                action="llm_decision_failed",
                outcome="failure",
                user_id=user_id,
                client_ip=client_ip,
                resource_type="llm_decision",
                resource_id=request_id,
                security_level=SecurityLevel.HIGH,
                phi_involved=True,
                compliance_flags=["HIPAA", "AI_DECISION"],
                error_message=error_message,
                details=audit_data
            )
            
        except Exception as e:
            self.logger.error(f"Failed to log LLM decision failure: {str(e)}")
            raise
    
    async def log_llm_model_operation(
        self,
        operation: str,
        model_audit_data: LLMModelAuditData,
        user_id: str,
        outcome: str = "success",
        client_ip: str = "unknown",
        **kwargs
    ) -> str:
        """Log LLM model operations (load, unload, configure, etc.)."""
        try:
            event_type_map = {
                "load": AuditEventType.LLM_MODEL_LOADED,
                "unload": AuditEventType.LLM_MODEL_UNLOADED,
                "configure": LLMAuditEventType.LLM_MODEL_CONFIGURED,
                "health_check": LLMAuditEventType.LLM_MODEL_HEALTH_CHECK,
                "fallback": AuditEventType.LLM_FALLBACK_TRIGGERED
            }
            
            event_type = event_type_map.get(operation, AuditEventType.LLM_MODEL_LOADED)
            
            return self.base_audit_logger.log_event(
                event_type=event_type,
                action=f"llm_model_{operation}",
                outcome=outcome,
                user_id=user_id,
                client_ip=client_ip,
                resource_type="llm_model",
                resource_id=model_audit_data.model_id,
                security_level=SecurityLevel.MEDIUM,
                details=model_audit_data.__dict__,
                **kwargs
            )
            
        except Exception as e:
            self.logger.error(f"Failed to log LLM model operation: {str(e)}")
            raise
    
    async def log_llm_data_processing(
        self,
        processing_audit_data: LLMDataProcessingAuditData,
        user_id: str,
        request_id: Optional[str] = None,
        client_ip: str = "unknown",
        **kwargs
    ) -> str:
        """Log LLM data processing operations."""
        try:
            # Determine event type based on operation
            event_type_map = {
                "deidentification": AuditEventType.PHI_DEIDENTIFICATION,
                "prompt_generation": LLMAuditEventType.LLM_PROMPT_GENERATED,
                "response_parsing": LLMAuditEventType.LLM_RESPONSE_PARSED,
                "data_preparation": AuditEventType.LLM_DATA_PREPARATION
            }
            
            event_type = event_type_map.get(
                processing_audit_data.operation_type,
                AuditEventType.LLM_DATA_PREPARATION
            )
            
            return self.base_audit_logger.log_event(
                event_type=event_type,
                action=f"llm_data_{processing_audit_data.operation_type}",
                outcome="success",
                user_id=user_id,
                client_ip=client_ip,
                resource_type="llm_data",
                resource_id=request_id or str(uuid.uuid4()),
                security_level=SecurityLevel.HIGH,
                phi_involved=bool(processing_audit_data.phi_fields_identified),
                compliance_flags=["HIPAA", "DATA_PROCESSING"],
                details=processing_audit_data.__dict__,
                **kwargs
            )
            
        except Exception as e:
            self.logger.error(f"Failed to log LLM data processing: {str(e)}")
            raise
    
    async def log_llm_external_api_call(
        self,
        api_endpoint: str,
        request_data_size: int,
        response_data_size: int,
        response_time_ms: float,
        success: bool,
        user_id: str,
        request_id: Optional[str] = None,
        error_message: Optional[str] = None,
        **kwargs
    ) -> str:
        """Log external API calls to LLM services."""
        try:
            audit_data = {
                "api_endpoint": api_endpoint,
                "request_data_size": request_data_size,
                "response_data_size": response_data_size,
                "response_time_ms": response_time_ms,
                "success": success,
                "error_message": error_message,
                "data_encrypted": kwargs.get("data_encrypted", True),
                "phi_transmitted": kwargs.get("phi_transmitted", False),
                **kwargs
            }
            
            event_type = (AuditEventType.LLM_EXTERNAL_CALL if success 
                         else LLMAuditEventType.LLM_API_CALL_FAILED)
            
            return self.base_audit_logger.log_event(
                event_type=event_type,
                action="llm_external_api_call",
                outcome="success" if success else "failure",
                user_id=user_id,
                resource_type="llm_api",
                resource_id=request_id or str(uuid.uuid4()),
                security_level=SecurityLevel.HIGH,
                phi_involved=kwargs.get("phi_transmitted", False),
                compliance_flags=["HIPAA", "EXTERNAL_API"],
                duration_ms=int(response_time_ms),
                error_message=error_message,
                details=audit_data
            )
            
        except Exception as e:
            self.logger.error(f"Failed to log LLM external API call: {str(e)}")
            raise
    
    async def log_llm_configuration_change(
        self,
        config_type: str,
        config_id: str,
        old_config: Dict[str, Any],
        new_config: Dict[str, Any],
        user_id: str,
        client_ip: str = "unknown",
        **kwargs
    ) -> str:
        """Log LLM configuration changes."""
        try:
            # Calculate configuration differences
            config_changes = self._calculate_config_changes(old_config, new_config)
            
            audit_data = {
                "config_type": config_type,
                "config_id": config_id,
                "changes": config_changes,
                "old_config_hash": hash(str(sorted(old_config.items()))),
                "new_config_hash": hash(str(sorted(new_config.items()))),
                "change_count": len(config_changes),
                **kwargs
            }
            
            return self.base_audit_logger.log_event(
                event_type=AuditEventType.CONFIG_CHANGED,
                action=f"llm_config_{config_type}_updated",
                outcome="success",
                user_id=user_id,
                client_ip=client_ip,
                resource_type="llm_config",
                resource_id=config_id,
                security_level=SecurityLevel.HIGH,
                compliance_flags=["AI_CONFIG"],
                details=audit_data
            )
            
        except Exception as e:
            self.logger.error(f"Failed to log LLM configuration change: {str(e)}")
            raise
    
    async def log_llm_performance_event(
        self,
        event_type: str,
        model_id: str,
        performance_metrics: Dict[str, Any],
        user_id: Optional[str] = None,
        **kwargs
    ) -> str:
        """Log LLM performance-related events."""
        try:
            audit_data = {
                "model_id": model_id,
                "event_type": event_type,
                "performance_metrics": performance_metrics,
                "threshold_breached": kwargs.get("threshold_breached", False),
                "alert_triggered": kwargs.get("alert_triggered", False),
                **kwargs
            }
            
            event_type_map = {
                "performance_degraded": LLMAuditEventType.LLM_PERFORMANCE_DEGRADED,
                "low_confidence": AuditEventType.AI_CONFIDENCE_LOW,
                "validation_failed": AuditEventType.AI_VALIDATION_FAILED,
                "anomaly_detected": LLMAuditEventType.LLM_ANOMALY_DETECTED
            }
            
            audit_event_type = event_type_map.get(event_type, AuditEventType.ERROR_OCCURRED)
            
            return self.base_audit_logger.log_event(
                event_type=audit_event_type,
                action=f"llm_performance_{event_type}",
                outcome="detected",
                user_id=user_id or "system",
                resource_type="llm_model",
                resource_id=model_id,
                security_level=SecurityLevel.MEDIUM,
                details=audit_data
            )
            
        except Exception as e:
            self.logger.error(f"Failed to log LLM performance event: {str(e)}")
            raise
    
    async def log_llm_decision_override(
        self,
        request_id: str,
        original_decision: str,
        override_decision: str,
        override_reason: str,
        user_id: str,
        client_ip: str = "unknown",
        **kwargs
    ) -> str:
        """Log manual override of LLM decisions."""
        try:
            audit_data = {
                "request_id": request_id,
                "original_decision": original_decision,
                "override_decision": override_decision,
                "override_reason": override_reason,
                "override_timestamp": datetime.now(timezone.utc).isoformat(),
                **kwargs
            }
            
            return self.base_audit_logger.log_event(
                event_type=LLMAuditEventType.LLM_DECISION_OVERRIDDEN,
                action="llm_decision_override",
                outcome="success",
                user_id=user_id,
                client_ip=client_ip,
                resource_type="llm_decision",
                resource_id=request_id,
                security_level=SecurityLevel.HIGH,
                phi_involved=True,
                compliance_flags=["HIPAA", "AI_DECISION", "MANUAL_OVERRIDE"],
                details=audit_data
            )
            
        except Exception as e:
            self.logger.error(f"Failed to log LLM decision override: {str(e)}")
            raise
    
    def _calculate_config_changes(
        self, 
        old_config: Dict[str, Any], 
        new_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Calculate the differences between old and new configuration."""
        changes = []
        
        # Find added keys
        for key in new_config:
            if key not in old_config:
                changes.append({
                    "type": "added",
                    "key": key,
                    "new_value": new_config[key]
                })
        
        # Find removed keys
        for key in old_config:
            if key not in new_config:
                changes.append({
                    "type": "removed",
                    "key": key,
                    "old_value": old_config[key]
                })
        
        # Find modified keys
        for key in old_config:
            if key in new_config and old_config[key] != new_config[key]:
                changes.append({
                    "type": "modified",
                    "key": key,
                    "old_value": old_config[key],
                    "new_value": new_config[key]
                })
        
        return changes
    
    async def get_llm_audit_summary(
        self,
        start_time: datetime,
        end_time: datetime,
        model_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get audit summary for LLM operations."""
        try:
            # This would query the audit database for LLM-specific events
            # For now, return a placeholder summary
            return {
                "period": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat()
                },
                "model_id": model_id,
                "summary": {
                    "total_decisions": 0,
                    "successful_decisions": 0,
                    "failed_decisions": 0,
                    "overridden_decisions": 0,
                    "average_confidence": 0.0,
                    "average_processing_time_ms": 0.0,
                    "phi_access_events": 0,
                    "external_api_calls": 0,
                    "configuration_changes": 0
                }
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get LLM audit summary: {str(e)}")
            raise


# Global LLM audit logger instance
llm_audit_logger = LLMAuditLogger()
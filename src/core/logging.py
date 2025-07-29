"""
Logging configuration for Prior Authorization Agent.

This module sets up structured logging with HIPAA compliance considerations,
ensuring no PHI is logged while maintaining comprehensive audit trails.
"""

import logging
import logging.config
import sys
from typing import Any, Dict

import structlog


def setup_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """
    Configure structured logging for the application.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Log format (json or text)
    """
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper())
    )
    
    # Configure structlog
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    
    if log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.extend([
            structlog.dev.ConsoleRenderer(colors=True),
        ])
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)


def sanitize_log_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize log data to remove PHI and sensitive information.
    
    This function ensures HIPAA compliance by removing or masking
    patient identifiable information from log entries.
    
    Args:
        data: Dictionary containing log data
        
    Returns:
        Sanitized dictionary safe for logging
    """
    sensitive_fields = {
        "patient_id", "ssn", "phone", "email", "address",
        "member_id", "insurance_id", "authorization_number",
        "clinical_notes", "patient_demographics"
    }
    
    sanitized = {}
    for key, value in data.items():
        if key.lower() in sensitive_fields:
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_log_data(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_log_data(item) if isinstance(item, dict) else "[REDACTED]"
                for item in value
            ]
        else:
            sanitized[key] = value
    
    return sanitized


class AuditLogger:
    """
    Specialized logger for audit events with HIPAA compliance.
    
    This logger ensures all audit events are properly formatted
    and contain necessary information for compliance reporting.
    """
    
    def __init__(self):
        self.logger = get_logger("audit")
    
    def log_request_received(self, request_id: str, provider_id: str, 
                           procedure_codes: list, diagnosis_codes: list) -> None:
        """Log authorization request received."""
        self.logger.info(
            "Authorization request received",
            event_type="request_received",
            request_id=request_id,
            provider_id=provider_id,
            procedure_codes=procedure_codes,
            diagnosis_codes=diagnosis_codes
        )
    
    def log_decision_made(self, request_id: str, decision: str, 
                         reasoning: list, confidence_score: float) -> None:
        """Log authorization decision made."""
        self.logger.info(
            "Authorization decision made",
            event_type="decision_made",
            request_id=request_id,
            decision=decision,
            reasoning=reasoning,
            confidence_score=confidence_score
        )
    
    def log_security_event(self, event_type: str, user_id: str = None, 
                          ip_address: str = None, details: dict = None) -> None:
        """Log security-related events."""
        self.logger.warning(
            "Security event detected",
            event_type=f"security_{event_type}",
            user_id=user_id,
            ip_address=ip_address,
            details=sanitize_log_data(details or {})
        )
    
    def log_policy_validation(self, request_id: str, policy_id: str, 
                            result: str, details: dict = None) -> None:
        """Log policy validation results."""
        self.logger.info(
            "Policy validation completed",
            event_type="policy_validation",
            request_id=request_id,
            policy_id=policy_id,
            result=result,
            details=sanitize_log_data(details or {})
        )
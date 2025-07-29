"""
Audit logging data models for Prior Authorization Agent.

This module defines audit event structures and types for
HIPAA-compliant logging and security monitoring.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


class AuditEventType(str, Enum):
    """
    Types of audit events for comprehensive system monitoring.
    
    Covers all HIPAA-required audit categories and security events.
    """
    # Authentication and authorization events
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    AUTH_FAILURE = "auth_failure"
    TOKEN_REFRESH = "token_refresh"
    ACCESS_DENIED = "access_denied"
    
    # Data access events
    PHI_ACCESS = "phi_access"
    PHI_CREATE = "phi_create"
    PHI_UPDATE = "phi_update"
    PHI_DELETE = "phi_delete"
    PHI_EXPORT = "phi_export"
    
    # Authorization request events
    REQUEST_SUBMITTED = "request_submitted"
    REQUEST_VIEWED = "request_viewed"
    REQUEST_UPDATED = "request_updated"
    DECISION_GENERATED = "decision_generated"
    DECISION_VIEWED = "decision_viewed"
    
    # Policy and configuration events
    POLICY_CREATED = "policy_created"
    POLICY_UPDATED = "policy_updated"
    POLICY_DELETED = "policy_deleted"
    CONFIG_CHANGED = "config_changed"
    
    # Security events
    SECURITY_VIOLATION = "security_violation"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    BRUTE_FORCE_DETECTED = "brute_force_detected"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    
    # System events
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    ERROR_OCCURRED = "error_occurred"
    BACKUP_CREATED = "backup_created"
    DATA_PURGED = "data_purged"


class SecurityLevel(str, Enum):
    """Security levels for audit events."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuditEvent(BaseModel):
    """
    Comprehensive audit event model for HIPAA compliance.
    
    Captures all necessary information for audit trails and
    security monitoring in healthcare systems.
    """
    event_id: str = Field(..., description="Unique event identifier")
    event_type: AuditEventType = Field(..., description="Type of audit event")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")
    
    # User and session information
    user_id: Optional[str] = Field(None, description="User identifier (if authenticated)")
    username: Optional[str] = Field(None, description="Username (if authenticated)")
    session_id: Optional[str] = Field(None, description="Session identifier")
    organization_id: Optional[str] = Field(None, description="Organization identifier")
    
    # Request and network information
    client_ip: str = Field(..., description="Client IP address")
    user_agent: Optional[str] = Field(None, description="User agent string")
    request_id: Optional[str] = Field(None, description="Request identifier")
    endpoint: Optional[str] = Field(None, description="API endpoint accessed")
    http_method: Optional[str] = Field(None, description="HTTP method used")
    
    # Event details
    resource_type: Optional[str] = Field(None, description="Type of resource accessed")
    resource_id: Optional[str] = Field(None, description="Identifier of resource accessed")
    action: str = Field(..., description="Action performed")
    outcome: str = Field(..., description="Outcome of the action (success/failure)")
    
    # Security and compliance
    security_level: SecurityLevel = Field(default=SecurityLevel.LOW, description="Security level of event")
    phi_involved: bool = Field(default=False, description="Whether PHI was involved")
    compliance_flags: List[str] = Field(default_factory=list, description="Compliance-related flags")
    
    # Additional context
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional event details")
    error_message: Optional[str] = Field(None, description="Error message if applicable")
    duration_ms: Optional[int] = Field(None, description="Operation duration in milliseconds")
    
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat()
        }
    )


class SecurityEvent(BaseModel):
    """
    Specialized security event model for threat detection.
    
    Extends audit events with security-specific information
    for incident response and threat monitoring.
    """
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")
    
    # Security event classification
    threat_type: str = Field(..., description="Type of security threat")
    severity: SecurityLevel = Field(..., description="Severity level")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0-1)")
    
    # Source information
    source_ip: str = Field(..., description="Source IP address")
    source_country: Optional[str] = Field(None, description="Source country (if available)")
    user_id: Optional[str] = Field(None, description="User ID (if authenticated)")
    
    # Attack details
    attack_vector: str = Field(..., description="Attack vector used")
    target_resource: Optional[str] = Field(None, description="Target resource")
    payload: Optional[str] = Field(None, description="Attack payload (sanitized)")
    
    # Response information
    blocked: bool = Field(default=False, description="Whether attack was blocked")
    response_action: Optional[str] = Field(None, description="Response action taken")
    
    # Context
    related_events: List[str] = Field(default_factory=list, description="Related event IDs")
    indicators: Dict[str, Any] = Field(default_factory=dict, description="Threat indicators")
    
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat()
        }
    )


class AuditQuery(BaseModel):
    """
    Query model for audit log searches and filtering.
    
    Supports comprehensive filtering for compliance reporting
    and security investigations.
    """
    # Time range
    start_time: Optional[datetime] = Field(None, description="Start time for query")
    end_time: Optional[datetime] = Field(None, description="End time for query")
    
    # Event filtering
    event_types: Optional[List[AuditEventType]] = Field(None, description="Event types to include")
    security_levels: Optional[List[SecurityLevel]] = Field(None, description="Security levels to include")
    outcomes: Optional[List[str]] = Field(None, description="Outcomes to include (success/failure)")
    
    # User and organization filtering
    user_ids: Optional[List[str]] = Field(None, description="User IDs to include")
    organization_ids: Optional[List[str]] = Field(None, description="Organization IDs to include")
    
    # Resource filtering
    resource_types: Optional[List[str]] = Field(None, description="Resource types to include")
    resource_ids: Optional[List[str]] = Field(None, description="Resource IDs to include")
    
    # Network filtering
    client_ips: Optional[List[str]] = Field(None, description="Client IPs to include")
    
    # PHI and compliance filtering
    phi_only: Optional[bool] = Field(None, description="Include only PHI-related events")
    compliance_flags: Optional[List[str]] = Field(None, description="Compliance flags to include")
    
    # Pagination and sorting
    limit: int = Field(default=100, ge=1, le=1000, description="Maximum number of results")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")
    sort_by: str = Field(default="timestamp", description="Field to sort by")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$", description="Sort order")
    
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat()
        }
    )


class AuditSummary(BaseModel):
    """
    Audit summary model for reporting and dashboards.
    
    Provides aggregated audit statistics for compliance
    and security monitoring.
    """
    # Time period
    start_time: datetime = Field(..., description="Summary start time")
    end_time: datetime = Field(..., description="Summary end time")
    
    # Event counts
    total_events: int = Field(..., description="Total number of events")
    event_type_counts: Dict[str, int] = Field(..., description="Count by event type")
    security_level_counts: Dict[str, int] = Field(..., description="Count by security level")
    
    # User activity
    unique_users: int = Field(..., description="Number of unique users")
    top_users: List[Dict[str, Any]] = Field(..., description="Most active users")
    
    # Security metrics
    security_events: int = Field(..., description="Number of security events")
    failed_logins: int = Field(..., description="Number of failed login attempts")
    blocked_requests: int = Field(..., description="Number of blocked requests")
    
    # PHI access metrics
    phi_access_events: int = Field(..., description="Number of PHI access events")
    phi_users: int = Field(..., description="Number of users accessing PHI")
    
    # System metrics
    error_rate: float = Field(..., description="Error rate percentage")
    avg_response_time: Optional[float] = Field(None, description="Average response time in ms")
    
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat()
        }
    )
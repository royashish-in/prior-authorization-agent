"""
Audit logging implementation for Prior Authorization Agent.

This module provides HIPAA-compliant audit logging functionality
with secure storage and comprehensive event tracking.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.core.config import get_settings
from src.core.encryption import encrypt_data, decrypt_data
from .models import AuditEvent, AuditEventType, SecurityEvent, SecurityLevel

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    HIPAA-compliant audit logger for healthcare systems.
    
    Provides secure, encrypted audit logging with comprehensive
    event tracking and security monitoring capabilities.
    """
    
    def __init__(self):
        """Initialize audit logger with database connection."""
        self.settings = get_settings()
        self._setup_database()
        self._setup_encryption()
    
    def _setup_database(self) -> None:
        """Set up database connection for audit logging."""
        try:
            self.engine = create_engine(
                self.settings.database_url,
                pool_size=5,
                max_overflow=10,
                echo=False  # Never echo audit queries for security
            )
            self.SessionLocal = sessionmaker(bind=self.engine)
            
            # Create audit tables if they don't exist
            self._create_audit_tables()
            
            logger.info("Audit database connection established")
            
        except Exception as e:
            logger.error(f"Failed to setup audit database: {e}")
            raise
    
    def _setup_encryption(self) -> None:
        """Set up encryption for sensitive audit data."""
        # In production, use proper key management (AWS KMS, HashiCorp Vault, etc.)
        self.encryption_key = self.settings.encryption_key.encode()[:32]  # AES-256 requires 32 bytes
    
    def _create_audit_tables(self) -> None:
        """Create audit tables if they don't exist."""
        create_audit_table_sql = """
        CREATE TABLE IF NOT EXISTS audit_events (
            event_id VARCHAR(36) PRIMARY KEY,
            event_type VARCHAR(50) NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            user_id VARCHAR(50),
            username VARCHAR(100),
            session_id VARCHAR(100),
            organization_id VARCHAR(50),
            client_ip VARCHAR(45) NOT NULL,
            user_agent TEXT,
            request_id VARCHAR(36),
            endpoint VARCHAR(200),
            http_method VARCHAR(10),
            resource_type VARCHAR(50),
            resource_id VARCHAR(100),
            action VARCHAR(100) NOT NULL,
            outcome VARCHAR(20) NOT NULL,
            security_level VARCHAR(20) DEFAULT 'low',
            phi_involved BOOLEAN DEFAULT FALSE,
            compliance_flags TEXT,
            details_encrypted TEXT,
            error_message TEXT,
            duration_ms INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        create_security_events_table_sql = """
        CREATE TABLE IF NOT EXISTS security_events (
            event_id VARCHAR(36) PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            threat_type VARCHAR(50) NOT NULL,
            severity VARCHAR(20) NOT NULL,
            confidence DECIMAL(3,2) NOT NULL,
            source_ip VARCHAR(45) NOT NULL,
            source_country VARCHAR(2),
            user_id VARCHAR(50),
            attack_vector VARCHAR(100) NOT NULL,
            target_resource VARCHAR(200),
            payload_encrypted TEXT,
            blocked BOOLEAN DEFAULT FALSE,
            response_action VARCHAR(100),
            related_events TEXT,
            indicators_encrypted TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        # Index creation statements (separate from table creation for SQLite compatibility)
        audit_indexes = [
            "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events (timestamp);",
            "CREATE INDEX IF NOT EXISTS idx_audit_user_id ON audit_events (user_id);",
            "CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_events (event_type);",
            "CREATE INDEX IF NOT EXISTS idx_audit_phi_involved ON audit_events (phi_involved);",
            "CREATE INDEX IF NOT EXISTS idx_audit_security_level ON audit_events (security_level);",
            "CREATE INDEX IF NOT EXISTS idx_audit_organization_id ON audit_events (organization_id);"
        ]
        
        security_indexes = [
            "CREATE INDEX IF NOT EXISTS idx_security_timestamp ON security_events (timestamp);",
            "CREATE INDEX IF NOT EXISTS idx_security_severity ON security_events (severity);",
            "CREATE INDEX IF NOT EXISTS idx_security_source_ip ON security_events (source_ip);",
            "CREATE INDEX IF NOT EXISTS idx_security_threat_type ON security_events (threat_type);",
            "CREATE INDEX IF NOT EXISTS idx_security_blocked ON security_events (blocked);"
        ]
        
        try:
            with self.engine.connect() as conn:
                # Create tables
                conn.execute(text(create_audit_table_sql))
                conn.execute(text(create_security_events_table_sql))
                
                # Create indexes
                for index_sql in audit_indexes + security_indexes:
                    conn.execute(text(index_sql))
                
                conn.commit()
                
            logger.info("Audit tables and indexes created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create audit tables: {e}")
            raise
    
    def log_event(
        self,
        event_type: AuditEventType,
        action: str,
        outcome: str,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        client_ip: str = "unknown",
        **kwargs
    ) -> str:
        """
        Log an audit event with comprehensive details.
        
        Args:
            event_type: Type of audit event
            action: Action performed
            outcome: Outcome of the action
            user_id: User identifier (if authenticated)
            username: Username (if authenticated)
            client_ip: Client IP address
            **kwargs: Additional event details
            
        Returns:
            Event ID of the logged event
            
        Raises:
            Exception: If logging fails
        """
        try:
            event_id = str(uuid.uuid4())
            
            # Create audit event
            audit_event = AuditEvent(
                event_id=event_id,
                event_type=event_type,
                action=action,
                outcome=outcome,
                user_id=user_id,
                username=username,
                client_ip=client_ip,
                **kwargs
            )
            
            # Encrypt sensitive details
            details_encrypted = None
            if audit_event.details:
                details_json = json.dumps(audit_event.details)
                details_encrypted = encrypt_data(details_json, self.encryption_key)
            
            # Prepare compliance flags
            compliance_flags_str = ",".join(audit_event.compliance_flags) if audit_event.compliance_flags else None
            
            # Insert into database
            insert_sql = """
            INSERT INTO audit_events (
                event_id, event_type, timestamp, user_id, username, session_id,
                organization_id, client_ip, user_agent, request_id, endpoint,
                http_method, resource_type, resource_id, action, outcome,
                security_level, phi_involved, compliance_flags, details_encrypted,
                error_message, duration_ms
            ) VALUES (
                :event_id, :event_type, :timestamp, :user_id, :username, :session_id,
                :organization_id, :client_ip, :user_agent, :request_id, :endpoint,
                :http_method, :resource_type, :resource_id, :action, :outcome,
                :security_level, :phi_involved, :compliance_flags, :details_encrypted,
                :error_message, :duration_ms
            )
            """
            
            with self.engine.connect() as conn:
                conn.execute(text(insert_sql), {
                    "event_id": audit_event.event_id,
                    "event_type": audit_event.event_type.value,
                    "timestamp": audit_event.timestamp,
                    "user_id": audit_event.user_id,
                    "username": audit_event.username,
                    "session_id": audit_event.session_id,
                    "organization_id": audit_event.organization_id,
                    "client_ip": audit_event.client_ip,
                    "user_agent": audit_event.user_agent,
                    "request_id": audit_event.request_id,
                    "endpoint": audit_event.endpoint,
                    "http_method": audit_event.http_method,
                    "resource_type": audit_event.resource_type,
                    "resource_id": audit_event.resource_id,
                    "action": audit_event.action,
                    "outcome": audit_event.outcome,
                    "security_level": audit_event.security_level.value,
                    "phi_involved": audit_event.phi_involved,
                    "compliance_flags": compliance_flags_str,
                    "details_encrypted": details_encrypted,
                    "error_message": audit_event.error_message,
                    "duration_ms": audit_event.duration_ms
                })
                conn.commit()
            
            # Log to application logger as well (without sensitive details)
            logger.info(
                f"Audit event logged: {event_type.value}",
                extra={
                    "event_id": event_id,
                    "action": action,
                    "outcome": outcome,
                    "user_id": user_id,
                    "client_ip": client_ip,
                    "phi_involved": audit_event.phi_involved
                }
            )
            
            return event_id
            
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")
            # In production, this should never fail silently
            # Consider using a fallback logging mechanism
            raise
    
    def log_security_event(
        self,
        threat_type: str,
        severity: SecurityLevel,
        confidence: float,
        source_ip: str,
        attack_vector: str,
        **kwargs
    ) -> str:
        """
        Log a security event for threat monitoring.
        
        Args:
            threat_type: Type of security threat
            severity: Severity level
            confidence: Confidence score (0-1)
            source_ip: Source IP address
            attack_vector: Attack vector used
            **kwargs: Additional security event details
            
        Returns:
            Event ID of the logged security event
        """
        try:
            event_id = str(uuid.uuid4())
            
            # Create security event
            security_event = SecurityEvent(
                event_id=event_id,
                threat_type=threat_type,
                severity=severity,
                confidence=confidence,
                source_ip=source_ip,
                attack_vector=attack_vector,
                **kwargs
            )
            
            # Encrypt sensitive payload and indicators
            payload_encrypted = None
            if security_event.payload:
                payload_encrypted = encrypt_data(security_event.payload, self.encryption_key)
            
            indicators_encrypted = None
            if security_event.indicators:
                indicators_json = json.dumps(security_event.indicators)
                indicators_encrypted = encrypt_data(indicators_json, self.encryption_key)
            
            # Prepare related events
            related_events_str = ",".join(security_event.related_events) if security_event.related_events else None
            
            # Insert into database
            insert_sql = """
            INSERT INTO security_events (
                event_id, timestamp, threat_type, severity, confidence,
                source_ip, source_country, user_id, attack_vector,
                target_resource, payload_encrypted, blocked, response_action,
                related_events, indicators_encrypted
            ) VALUES (
                :event_id, :timestamp, :threat_type, :severity, :confidence,
                :source_ip, :source_country, :user_id, :attack_vector,
                :target_resource, :payload_encrypted, :blocked, :response_action,
                :related_events, :indicators_encrypted
            )
            """
            
            with self.engine.connect() as conn:
                conn.execute(text(insert_sql), {
                    "event_id": security_event.event_id,
                    "timestamp": security_event.timestamp,
                    "threat_type": security_event.threat_type,
                    "severity": security_event.severity.value,
                    "confidence": security_event.confidence,
                    "source_ip": security_event.source_ip,
                    "source_country": security_event.source_country,
                    "user_id": security_event.user_id,
                    "attack_vector": security_event.attack_vector,
                    "target_resource": security_event.target_resource,
                    "payload_encrypted": payload_encrypted,
                    "blocked": security_event.blocked,
                    "response_action": security_event.response_action,
                    "related_events": related_events_str,
                    "indicators_encrypted": indicators_encrypted
                })
                conn.commit()
            
            # Log to application logger
            logger.warning(
                f"Security event logged: {threat_type}",
                extra={
                    "event_id": event_id,
                    "severity": severity.value,
                    "confidence": confidence,
                    "source_ip": source_ip,
                    "attack_vector": attack_vector,
                    "blocked": security_event.blocked
                }
            )
            
            # Also log as audit event
            self.log_event(
                event_type=AuditEventType.SECURITY_VIOLATION,
                action=f"security_threat_{threat_type}",
                outcome="detected",
                client_ip=source_ip,
                security_level=severity,
                details={
                    "threat_type": threat_type,
                    "attack_vector": attack_vector,
                    "confidence": confidence,
                    "blocked": security_event.blocked
                }
            )
            
            return event_id
            
        except Exception as e:
            logger.error(f"Failed to log security event: {e}")
            raise
    
    def log_phi_access(
        self,
        user_id: str,
        username: str,
        resource_type: str,
        resource_id: str,
        action: str,
        client_ip: str,
        **kwargs
    ) -> str:
        """
        Log PHI access event for HIPAA compliance.
        
        Args:
            user_id: User identifier
            username: Username
            resource_type: Type of PHI resource
            resource_id: PHI resource identifier
            action: Action performed on PHI
            client_ip: Client IP address
            **kwargs: Additional details
            
        Returns:
            Event ID of the logged PHI access event
        """
        return self.log_event(
            event_type=AuditEventType.PHI_ACCESS,
            action=action,
            outcome="success",
            user_id=user_id,
            username=username,
            client_ip=client_ip,
            resource_type=resource_type,
            resource_id=resource_id,
            phi_involved=True,
            security_level=SecurityLevel.HIGH,
            compliance_flags=["HIPAA"],
            **kwargs
        )
    
    def log_authentication(
        self,
        username: str,
        outcome: str,
        client_ip: str,
        user_agent: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Log authentication event.
        
        Args:
            username: Username attempting authentication
            outcome: Authentication outcome (success/failure)
            client_ip: Client IP address
            user_agent: User agent string
            **kwargs: Additional details
            
        Returns:
            Event ID of the logged authentication event
        """
        event_type = AuditEventType.USER_LOGIN if outcome == "success" else AuditEventType.AUTH_FAILURE
        security_level = SecurityLevel.LOW if outcome == "success" else SecurityLevel.MEDIUM
        
        return self.log_event(
            event_type=event_type,
            action="authenticate",
            outcome=outcome,
            username=username,
            client_ip=client_ip,
            user_agent=user_agent,
            security_level=security_level,
            **kwargs
        )
    
    def get_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[AuditEventType]] = None,
        user_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve audit events with filtering.
        
        Args:
            start_time: Start time for query
            end_time: End time for query
            event_types: Event types to include
            user_id: User ID to filter by
            limit: Maximum number of results
            
        Returns:
            List of audit events
        """
        try:
            # Build query
            where_conditions = []
            params = {}
            
            if start_time:
                where_conditions.append("timestamp >= :start_time")
                params["start_time"] = start_time
            
            if end_time:
                where_conditions.append("timestamp <= :end_time")
                params["end_time"] = end_time
            
            if event_types:
                event_type_values = [et.value for et in event_types]
                placeholders = ",".join([f":event_type_{i}" for i in range(len(event_type_values))])
                where_conditions.append(f"event_type IN ({placeholders})")
                for i, et in enumerate(event_type_values):
                    params[f"event_type_{i}"] = et
            
            if user_id:
                where_conditions.append("user_id = :user_id")
                params["user_id"] = user_id
            
            where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
            
            query_sql = f"""
            SELECT event_id, event_type, timestamp, user_id, username,
                   client_ip, action, outcome, security_level, phi_involved,
                   resource_type, resource_id, error_message, duration_ms
            FROM audit_events
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT :limit
            """
            
            params["limit"] = limit
            
            with self.engine.connect() as conn:
                result = conn.execute(text(query_sql), params)
                events = []
                
                for row in result:
                    events.append({
                        "event_id": row.event_id,
                        "event_type": row.event_type,
                        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                        "user_id": row.user_id,
                        "username": row.username,
                        "client_ip": row.client_ip,
                        "action": row.action,
                        "outcome": row.outcome,
                        "security_level": row.security_level,
                        "phi_involved": row.phi_involved,
                        "resource_type": row.resource_type,
                        "resource_id": row.resource_id,
                        "error_message": row.error_message,
                        "duration_ms": row.duration_ms
                    })
                
                return events
                
        except Exception as e:
            logger.error(f"Failed to retrieve audit events: {e}")
            raise


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """
    Get the global audit logger instance.
    
    Returns:
        AuditLogger instance
    """
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
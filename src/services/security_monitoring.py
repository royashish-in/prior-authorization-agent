"""
Security monitoring and incident response system.

This module provides real-time security event monitoring, automated incident
response workflows, and anomaly detection for the Prior Authorization Agent.
"""

import logging
import asyncio
import time
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
from enum import Enum
import threading
import ipaddress
import re

from src.core.logging import get_logger, AuditLogger
from src.core.config import get_settings
from src.services.notification import NotificationService

logger = get_logger(__name__)
audit_logger = AuditLogger()

# Module-level notification service for testing
notification_service = NotificationService()


class SecurityEventType(Enum):
    """Types of security events."""

    UNAUTHORIZED_ACCESS = "unauthorized_access"
    FAILED_LOGIN = "failed_login"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    DATA_BREACH = "data_breach"
    MALICIOUS_REQUEST = "malicious_request"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    ANOMALOUS_BEHAVIOR = "anomalous_behavior"
    POLICY_VIOLATION = "policy_violation"
    SYSTEM_COMPROMISE = "system_compromise"


class IncidentSeverity(Enum):
    """Incident severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(Enum):
    """Incident status values."""

    OPEN = "open"
    INVESTIGATING = "investigating"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    CLOSED = "closed"


@dataclass
class SecurityEvent:
    """Security event data structure."""

    event_id: str
    event_type: SecurityEventType
    timestamp: datetime
    source_ip: str
    user_id: Optional[str]
    resource: str
    details: Dict[str, Any]
    severity: IncidentSeverity
    risk_score: float
    indicators: List[str]
    raw_data: Dict[str, Any]


@dataclass
class SecurityIncident:
    """Security incident data structure."""

    incident_id: str
    title: str
    description: str
    severity: IncidentSeverity
    status: IncidentStatus
    created_at: datetime
    updated_at: datetime
    assigned_to: Optional[str]
    events: List[str]  # Event IDs
    indicators_of_compromise: List[str]
    response_actions: List[str]
    resolution_notes: Optional[str]
    closed_at: Optional[datetime]


@dataclass
class AnomalyPattern:
    """Anomaly detection pattern."""

    pattern_id: str
    pattern_type: str
    description: str
    threshold: float
    time_window_minutes: int
    indicators: List[str]
    severity: IncidentSeverity
    enabled: bool


@dataclass
class ThreatIntelligence:
    """Threat intelligence data."""

    indicator: str
    indicator_type: str  # ip, domain, hash, etc.
    threat_type: str
    confidence: float
    source: str
    first_seen: datetime
    last_seen: datetime
    description: str


class SecurityMonitoringService:
    """
    Comprehensive security monitoring and incident response service.

    Provides real-time security event monitoring, automated incident response,
    and anomaly detection for healthcare data protection.
    """

    def __init__(self):
        self.settings = get_settings()
        self.notification_service = NotificationService()

        # Event storage
        self.security_events = deque(maxlen=100000)
        self.incidents = {}
        self.event_index = {}  # For fast event lookup

        # Monitoring state
        self.failed_login_attempts = defaultdict(list)
        self.request_patterns = defaultdict(list)
        self.user_activity = defaultdict(list)
        self.ip_activity = defaultdict(list)

        # Threat intelligence
        self.threat_indicators = {}
        self.blocked_ips = set()
        self.suspicious_patterns = set()

        # Anomaly detection patterns
        self.anomaly_patterns = self._initialize_anomaly_patterns()

        # Response automation
        self.response_handlers = self._initialize_response_handlers()

        # Monitoring thread
        self._monitoring_active = False
        self._monitoring_thread = None

        # Rate limiting for alerts
        self.alert_rate_limiter = defaultdict(list)

    def start_monitoring(self):
        """Start security monitoring background processes."""
        if self._monitoring_active:
            return

        self._monitoring_active = True
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop, daemon=True
        )
        self._monitoring_thread.start()
        logger.info("Started security monitoring")

    def stop_monitoring(self):
        """Stop security monitoring."""
        self._monitoring_active = False
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=5)
        logger.info("Stopped security monitoring")

    def _monitoring_loop(self):
        """Main monitoring loop."""
        while self._monitoring_active:
            try:
                # Clean up old data
                self._cleanup_old_data()

                # Check for anomalies
                self._detect_anomalies()

                # Update threat intelligence
                self._update_threat_intelligence()

                # Process incident escalations
                self._process_incident_escalations()

                # Sleep for monitoring interval
                time.sleep(30)  # Check every 30 seconds

            except Exception as e:
                logger.error(f"Error in security monitoring loop: {e}")
                time.sleep(30)

    def record_security_event(
        self,
        event_type: SecurityEventType,
        source_ip: str,
        user_id: Optional[str] = None,
        resource: str = "",
        details: Dict[str, Any] = None,
        raw_data: Dict[str, Any] = None,
    ) -> str:
        """
        Record a security event.

        Args:
            event_type: Type of security event
            source_ip: Source IP address
            user_id: User ID if applicable
            resource: Resource being accessed
            details: Additional event details
            raw_data: Raw event data

        Returns:
            Event ID
        """
        event_id = self._generate_event_id()
        timestamp = datetime.now(timezone.utc)

        # Calculate risk score
        risk_score = self._calculate_risk_score(
            event_type, source_ip, user_id, details or {}
        )

        # Determine severity
        severity = self._determine_severity(event_type, risk_score)

        # Extract indicators
        indicators = self._extract_indicators(
            event_type, source_ip, user_id, details or {}
        )

        event = SecurityEvent(
            event_id=event_id,
            event_type=event_type,
            timestamp=timestamp,
            source_ip=source_ip,
            user_id=user_id,
            resource=resource,
            details=details or {},
            severity=severity,
            risk_score=risk_score,
            indicators=indicators,
            raw_data=raw_data or {},
        )

        # Store event
        self.security_events.append(event)
        self.event_index[event_id] = event

        # Update tracking data
        self._update_tracking_data(event)

        # Check for immediate response triggers
        self._check_immediate_response(event)

        # Log the event
        audit_logger.log_security_event(
            event_type.value,
            user_id=user_id,
            ip_address=source_ip,
            details={
                "event_id": event_id,
                "resource": resource,
                "risk_score": risk_score,
                "severity": severity.value,
            },
        )

        logger.info(
            "Recorded security event",
            event_id=event_id,
            event_type=event_type.value,
            severity=severity.value,
            risk_score=risk_score,
        )

        return event_id

    def create_incident(
        self,
        title: str,
        description: str,
        severity: IncidentSeverity,
        event_ids: List[str] = None,
        assigned_to: str = None,
    ) -> str:
        """
        Create a security incident.

        Args:
            title: Incident title
            description: Incident description
            severity: Incident severity
            event_ids: Related event IDs
            assigned_to: User assigned to handle incident

        Returns:
            Incident ID
        """
        incident_id = self._generate_incident_id()
        timestamp = datetime.now(timezone.utc)

        # Extract indicators of compromise from related events
        iocs = []
        if event_ids:
            for event_id in event_ids:
                if event_id in self.event_index:
                    event = self.event_index[event_id]
                    iocs.extend(event.indicators)

        incident = SecurityIncident(
            incident_id=incident_id,
            title=title,
            description=description,
            severity=severity,
            status=IncidentStatus.OPEN,
            created_at=timestamp,
            updated_at=timestamp,
            assigned_to=assigned_to,
            events=event_ids or [],
            indicators_of_compromise=list(set(iocs)),
            response_actions=[],
            resolution_notes=None,
            closed_at=None,
        )

        self.incidents[incident_id] = incident

        # Trigger automated response (only if in async context)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._trigger_incident_response(incident))
        except RuntimeError:
            # No event loop running, skip async response
            logger.debug("No event loop running, skipping async incident response")

        logger.warning(
            "Created security incident",
            incident_id=incident_id,
            title=title,
            severity=severity.value,
        )

        return incident_id

    def update_incident_status(
        self,
        incident_id: str,
        status: IncidentStatus,
        notes: str = None,
        assigned_to: str = None,
    ) -> bool:
        """
        Update incident status.

        Args:
            incident_id: Incident ID
            status: New status
            notes: Update notes
            assigned_to: New assignee

        Returns:
            Success status
        """
        if incident_id not in self.incidents:
            return False

        incident = self.incidents[incident_id]
        incident.status = status
        incident.updated_at = datetime.now(timezone.utc)

        if assigned_to:
            incident.assigned_to = assigned_to

        if notes:
            incident.response_actions.append(
                f"{datetime.now(timezone.utc).isoformat()}: {notes}"
            )

        if status == IncidentStatus.CLOSED:
            incident.closed_at = datetime.now(timezone.utc)
            incident.resolution_notes = notes

        logger.info(
            "Updated incident status",
            incident_id=incident_id,
            status=status.value,
            assigned_to=assigned_to,
        )

        return True

    def get_security_events(
        self,
        hours: int = 24,
        event_type: SecurityEventType = None,
        severity: IncidentSeverity = None,
    ) -> List[SecurityEvent]:
        """
        Get security events with optional filtering.

        Args:
            hours: Hours of history to retrieve
            event_type: Filter by event type
            severity: Filter by severity

        Returns:
            List of security events
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

        events = []
        for event in self.security_events:
            if event.timestamp < cutoff_time:
                continue

            if event_type and event.event_type != event_type:
                continue

            if severity and event.severity != severity:
                continue

            events.append(event)

        return sorted(events, key=lambda x: x.timestamp, reverse=True)

    def get_incidents(
        self, status: IncidentStatus = None, severity: IncidentSeverity = None
    ) -> List[SecurityIncident]:
        """
        Get security incidents with optional filtering.

        Args:
            status: Filter by status
            severity: Filter by severity

        Returns:
            List of security incidents
        """
        incidents = []
        for incident in self.incidents.values():
            if status and incident.status != status:
                continue

            if severity and incident.severity != severity:
                continue

            incidents.append(incident)

        return sorted(incidents, key=lambda x: x.created_at, reverse=True)

    def get_threat_intelligence_report(self) -> Dict[str, Any]:
        """
        Generate threat intelligence report.

        Returns:
            Threat intelligence summary
        """
        now = datetime.now(timezone.utc)
        last_24h = now - timedelta(hours=24)

        # Recent events by type
        recent_events = self.get_security_events(hours=24)
        events_by_type = defaultdict(int)
        for event in recent_events:
            events_by_type[event.event_type.value] += 1

        # Top source IPs
        ip_counts = defaultdict(int)
        for event in recent_events:
            ip_counts[event.source_ip] += 1

        top_ips = sorted(ip_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        # Active incidents
        active_incidents = len(
            [
                i
                for i in self.incidents.values()
                if i.status not in [IncidentStatus.RESOLVED, IncidentStatus.CLOSED]
            ]
        )

        # Threat indicators
        active_threats = len(
            [t for t in self.threat_indicators.values() if t.last_seen > last_24h]
        )

        return {
            "generated_at": now.isoformat(),
            "summary": {
                "total_events_24h": len(recent_events),
                "active_incidents": active_incidents,
                "blocked_ips": len(self.blocked_ips),
                "active_threats": active_threats,
            },
            "events_by_type": dict(events_by_type),
            "top_source_ips": top_ips,
            "recent_incidents": [
                {
                    "incident_id": i.incident_id,
                    "title": i.title,
                    "severity": i.severity.value,
                    "status": i.status.value,
                    "created_at": i.created_at.isoformat(),
                }
                for i in sorted(
                    self.incidents.values(), key=lambda x: x.created_at, reverse=True
                )[:5]
            ],
            "threat_indicators": [
                {
                    "indicator": t.indicator,
                    "type": t.indicator_type,
                    "threat_type": t.threat_type,
                    "confidence": t.confidence,
                    "last_seen": t.last_seen.isoformat(),
                }
                for t in sorted(
                    self.threat_indicators.values(),
                    key=lambda x: x.last_seen,
                    reverse=True,
                )[:10]
            ],
        }

    def check_threat_indicators(
        self, ip: str = None, domain: str = None, hash_value: str = None
    ) -> List[ThreatIntelligence]:
        """
        Check if indicators match known threats.

        Args:
            ip: IP address to check
            domain: Domain to check
            hash_value: Hash to check

        Returns:
            List of matching threat indicators
        """
        matches = []

        indicators_to_check = []
        if ip:
            indicators_to_check.append(("ip", ip))
        if domain:
            indicators_to_check.append(("domain", domain))
        if hash_value:
            indicators_to_check.append(("hash", hash_value))

        for indicator_type, indicator_value in indicators_to_check:
            if indicator_value in self.threat_indicators:
                threat = self.threat_indicators[indicator_value]
                if threat.indicator_type == indicator_type:
                    matches.append(threat)

        return matches

    def add_threat_indicator(
        self,
        indicator: str,
        indicator_type: str,
        threat_type: str,
        confidence: float,
        source: str,
        description: str = "",
    ) -> None:
        """
        Add a threat intelligence indicator.

        Args:
            indicator: The indicator value (IP, domain, hash, etc.)
            indicator_type: Type of indicator
            threat_type: Type of threat
            confidence: Confidence score (0.0-1.0)
            source: Source of the intelligence
            description: Description of the threat
        """
        now = datetime.now(timezone.utc)

        if indicator in self.threat_indicators:
            # Update existing indicator
            threat = self.threat_indicators[indicator]
            threat.last_seen = now
            threat.confidence = max(threat.confidence, confidence)
        else:
            # Create new indicator
            threat = ThreatIntelligence(
                indicator=indicator,
                indicator_type=indicator_type,
                threat_type=threat_type,
                confidence=confidence,
                source=source,
                first_seen=now,
                last_seen=now,
                description=description,
            )
            self.threat_indicators[indicator] = threat

        logger.info(
            "Added threat indicator",
            indicator=indicator,
            indicator_type=indicator_type,
            threat_type=threat_type,
            confidence=confidence,
        )

    def block_ip(self, ip: str, reason: str, duration_hours: int = 24) -> None:
        """
        Block an IP address.

        Args:
            ip: IP address to block
            reason: Reason for blocking
            duration_hours: Block duration in hours
        """
        self.blocked_ips.add(ip)

        # Record the blocking action
        self.record_security_event(
            SecurityEventType.SYSTEM_COMPROMISE,
            source_ip=ip,
            resource="ip_blocking",
            details={
                "action": "ip_blocked",
                "reason": reason,
                "duration_hours": duration_hours,
            },
        )

        logger.warning(
            "Blocked IP address", ip=ip, reason=reason, duration_hours=duration_hours
        )

    def is_ip_blocked(self, ip: str) -> bool:
        """Check if an IP address is blocked."""
        return ip in self.blocked_ips

    # Private methods

    def _initialize_anomaly_patterns(self) -> Dict[str, AnomalyPattern]:
        """Initialize anomaly detection patterns."""
        patterns = {}

        # Failed login pattern
        patterns["failed_login_burst"] = AnomalyPattern(
            pattern_id="failed_login_burst",
            pattern_type="rate_limit",
            description="Multiple failed login attempts from same IP",
            threshold=5.0,
            time_window_minutes=5,
            indicators=["failed_login", "brute_force"],
            severity=IncidentSeverity.HIGH,
            enabled=True,
        )

        # Unusual access pattern
        patterns["unusual_access_time"] = AnomalyPattern(
            pattern_id="unusual_access_time",
            pattern_type="temporal",
            description="Access outside normal business hours",
            threshold=0.8,
            time_window_minutes=60,
            indicators=["after_hours_access"],
            severity=IncidentSeverity.MEDIUM,
            enabled=True,
        )

        # High volume requests
        patterns["request_flood"] = AnomalyPattern(
            pattern_id="request_flood",
            pattern_type="volume",
            description="Unusually high request volume from single source",
            threshold=100.0,
            time_window_minutes=1,
            indicators=["ddos", "abuse"],
            severity=IncidentSeverity.HIGH,
            enabled=True,
        )

        # PHI access anomaly
        patterns["phi_access_anomaly"] = AnomalyPattern(
            pattern_id="phi_access_anomaly",
            pattern_type="behavioral",
            description="Unusual PHI access pattern",
            threshold=10.0,
            time_window_minutes=60,
            indicators=["phi_abuse", "data_exfiltration"],
            severity=IncidentSeverity.CRITICAL,
            enabled=True,
        )

        return patterns

    def _initialize_response_handlers(self) -> Dict[str, callable]:
        """Initialize automated response handlers."""
        return {
            SecurityEventType.UNAUTHORIZED_ACCESS.value: self._handle_unauthorized_access,
            SecurityEventType.FAILED_LOGIN.value: self._handle_failed_login,
            SecurityEventType.SUSPICIOUS_ACTIVITY.value: self._handle_suspicious_activity,
            SecurityEventType.DATA_BREACH.value: self._handle_data_breach,
            SecurityEventType.MALICIOUS_REQUEST.value: self._handle_malicious_request,
        }

    def _generate_event_id(self) -> str:
        """Generate unique event ID."""
        timestamp = str(int(time.time() * 1000000))
        return f"evt_{timestamp}_{hashlib.md5(timestamp.encode()).hexdigest()[:8]}"

    def _generate_incident_id(self) -> str:
        """Generate unique incident ID."""
        timestamp = str(int(time.time() * 1000000))
        return f"inc_{timestamp}_{hashlib.md5(timestamp.encode()).hexdigest()[:8]}"

    def _calculate_risk_score(
        self,
        event_type: SecurityEventType,
        source_ip: str,
        user_id: Optional[str],
        details: Dict[str, Any],
    ) -> float:
        """Calculate risk score for an event."""
        base_scores = {
            SecurityEventType.UNAUTHORIZED_ACCESS: 8.0,
            SecurityEventType.FAILED_LOGIN: 3.0,
            SecurityEventType.SUSPICIOUS_ACTIVITY: 6.0,
            SecurityEventType.DATA_BREACH: 10.0,
            SecurityEventType.MALICIOUS_REQUEST: 7.0,
            SecurityEventType.PRIVILEGE_ESCALATION: 9.0,
            SecurityEventType.ANOMALOUS_BEHAVIOR: 5.0,
            SecurityEventType.POLICY_VIOLATION: 4.0,
            SecurityEventType.SYSTEM_COMPROMISE: 10.0,
        }

        score = base_scores.get(event_type, 5.0)

        # Adjust based on source IP reputation
        if source_ip in self.blocked_ips:
            score += 3.0

        # Check threat intelligence
        threats = self.check_threat_indicators(ip=source_ip)
        if threats:
            max_confidence = max(t.confidence for t in threats)
            score += max_confidence * 5.0

        # Adjust based on user context
        if user_id:
            # Check for repeated violations
            recent_events = [
                e
                for e in self.security_events
                if e.user_id == user_id
                and e.timestamp > datetime.now(timezone.utc) - timedelta(hours=24)
            ]
            if len(recent_events) > 5:
                score += 2.0

        # Adjust based on details
        if details.get("phi_involved"):
            score += 3.0

        if details.get("admin_access"):
            score += 2.0

        return min(score, 10.0)  # Cap at 10.0

    def _determine_severity(
        self, event_type: SecurityEventType, risk_score: float
    ) -> IncidentSeverity:
        """Determine incident severity based on event type and risk score."""
        if risk_score >= 9.0 or event_type in [
            SecurityEventType.DATA_BREACH,
            SecurityEventType.SYSTEM_COMPROMISE,
        ]:
            return IncidentSeverity.CRITICAL
        elif risk_score >= 7.0 or event_type in [
            SecurityEventType.UNAUTHORIZED_ACCESS,
            SecurityEventType.MALICIOUS_REQUEST,
        ]:
            return IncidentSeverity.HIGH
        elif risk_score >= 5.0:
            return IncidentSeverity.MEDIUM
        else:
            return IncidentSeverity.LOW

    def _extract_indicators(
        self,
        event_type: SecurityEventType,
        source_ip: str,
        user_id: Optional[str],
        details: Dict[str, Any],
    ) -> List[str]:
        """Extract indicators of compromise from event data."""
        indicators = []

        # Always include source IP
        indicators.append(f"ip:{source_ip}")

        # Add user ID if available
        if user_id:
            indicators.append(f"user:{user_id}")

        # Add event-specific indicators
        if event_type == SecurityEventType.FAILED_LOGIN:
            indicators.append("failed_auth")
        elif event_type == SecurityEventType.UNAUTHORIZED_ACCESS:
            indicators.append("unauthorized_access")
        elif event_type == SecurityEventType.DATA_BREACH:
            indicators.extend(["data_breach", "phi_exposure"])

        # Add indicators from details
        if details.get("user_agent"):
            indicators.append(f"user_agent:{details['user_agent']}")

        if details.get("request_path"):
            indicators.append(f"path:{details['request_path']}")

        return indicators

    def _update_tracking_data(self, event: SecurityEvent) -> None:
        """Update tracking data structures."""
        current_time = time.time()

        # Track failed logins by IP
        if event.event_type == SecurityEventType.FAILED_LOGIN:
            self.failed_login_attempts[event.source_ip].append(current_time)

        # Track request patterns
        self.request_patterns[event.source_ip].append(current_time)

        # Track user activity
        if event.user_id:
            self.user_activity[event.user_id].append(current_time)

        # Track IP activity
        self.ip_activity[event.source_ip].append(current_time)

    def _check_immediate_response(self, event: SecurityEvent) -> None:
        """Check if event requires immediate automated response."""
        handler = self.response_handlers.get(event.event_type.value)
        if handler:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in immediate response handler: {e}")

    def _cleanup_old_data(self) -> None:
        """Clean up old tracking data."""
        current_time = time.time()
        cutoff_time = current_time - 86400  # 24 hours

        # Clean failed login attempts
        for ip in list(self.failed_login_attempts.keys()):
            self.failed_login_attempts[ip] = [
                t for t in self.failed_login_attempts[ip] if t > cutoff_time
            ]
            if not self.failed_login_attempts[ip]:
                del self.failed_login_attempts[ip]

        # Clean request patterns
        for ip in list(self.request_patterns.keys()):
            self.request_patterns[ip] = [
                t for t in self.request_patterns[ip] if t > cutoff_time
            ]
            if not self.request_patterns[ip]:
                del self.request_patterns[ip]

        # Clean user activity
        for user_id in list(self.user_activity.keys()):
            self.user_activity[user_id] = [
                t for t in self.user_activity[user_id] if t > cutoff_time
            ]
            if not self.user_activity[user_id]:
                del self.user_activity[user_id]

        # Clean IP activity
        for ip in list(self.ip_activity.keys()):
            self.ip_activity[ip] = [t for t in self.ip_activity[ip] if t > cutoff_time]
            if not self.ip_activity[ip]:
                del self.ip_activity[ip]

    def _detect_anomalies(self) -> None:
        """Detect anomalous patterns in security events."""
        current_time = time.time()

        for pattern in self.anomaly_patterns.values():
            if not pattern.enabled:
                continue

            try:
                if pattern.pattern_type == "rate_limit":
                    self._detect_rate_limit_anomaly(pattern, current_time)
                elif pattern.pattern_type == "volume":
                    self._detect_volume_anomaly(pattern, current_time)
                elif pattern.pattern_type == "behavioral":
                    self._detect_behavioral_anomaly(pattern, current_time)
                elif pattern.pattern_type == "temporal":
                    self._detect_temporal_anomaly(pattern, current_time)
            except Exception as e:
                logger.error(f"Error detecting anomaly {pattern.pattern_id}: {e}")

    def _detect_rate_limit_anomaly(
        self, pattern: AnomalyPattern, current_time: float
    ) -> None:
        """Detect rate limit anomalies."""
        window_start = current_time - (pattern.time_window_minutes * 60)

        if pattern.pattern_id == "failed_login_burst":
            for ip, attempts in self.failed_login_attempts.items():
                recent_attempts = [t for t in attempts if t > window_start]
                if len(recent_attempts) >= pattern.threshold:
                    self._create_anomaly_incident(
                        f"Failed login burst from {ip}",
                        f"Detected {len(recent_attempts)} failed login attempts from {ip} "
                        f"in {pattern.time_window_minutes} minutes",
                        pattern.severity,
                        pattern.indicators,
                    )

    def _detect_volume_anomaly(
        self, pattern: AnomalyPattern, current_time: float
    ) -> None:
        """Detect volume anomalies."""
        window_start = current_time - (pattern.time_window_minutes * 60)

        if pattern.pattern_id == "request_flood":
            for ip, requests in self.request_patterns.items():
                recent_requests = [t for t in requests if t > window_start]
                if len(recent_requests) >= pattern.threshold:
                    self._create_anomaly_incident(
                        f"Request flood from {ip}",
                        f"Detected {len(recent_requests)} requests from {ip} "
                        f"in {pattern.time_window_minutes} minutes",
                        pattern.severity,
                        pattern.indicators,
                    )

    def _detect_behavioral_anomaly(
        self, pattern: AnomalyPattern, current_time: float
    ) -> None:
        """Detect behavioral anomalies."""
        # Implementation would analyze user behavior patterns
        # This is a simplified version
        pass

    def _detect_temporal_anomaly(
        self, pattern: AnomalyPattern, current_time: float
    ) -> None:
        """Detect temporal anomalies."""
        # Implementation would check for access outside normal hours
        # This is a simplified version
        pass

    def _create_anomaly_incident(
        self,
        title: str,
        description: str,
        severity: IncidentSeverity,
        indicators: List[str],
    ) -> None:
        """Create incident from detected anomaly."""
        # Rate limit incident creation
        incident_key = hashlib.md5(title.encode()).hexdigest()
        now = time.time()

        if incident_key in self.alert_rate_limiter:
            recent_alerts = [
                t for t in self.alert_rate_limiter[incident_key] if t > now - 3600
            ]
            if len(recent_alerts) >= 3:  # Max 3 incidents per hour for same anomaly
                return

        self.alert_rate_limiter[incident_key].append(now)

        # Create incident
        incident_id = self.create_incident(title, description, severity)

        logger.warning(
            "Created anomaly incident",
            incident_id=incident_id,
            title=title,
            severity=severity.value,
        )

    def _update_threat_intelligence(self) -> None:
        """Update threat intelligence from external sources."""
        # This would integrate with external threat intelligence feeds
        # For now, it's a placeholder
        pass

    def _process_incident_escalations(self) -> None:
        """Process incident escalations based on age and severity."""
        now = datetime.now(timezone.utc)

        for incident in self.incidents.values():
            if incident.status in [IncidentStatus.RESOLVED, IncidentStatus.CLOSED]:
                continue

            age_hours = (now - incident.created_at).total_seconds() / 3600

            # Escalate based on severity and age
            if incident.severity == IncidentSeverity.CRITICAL and age_hours > 1:
                self._escalate_incident(
                    incident, "Critical incident open for over 1 hour"
                )
            elif incident.severity == IncidentSeverity.HIGH and age_hours > 4:
                self._escalate_incident(
                    incident, "High severity incident open for over 4 hours"
                )
            elif incident.severity == IncidentSeverity.MEDIUM and age_hours > 24:
                self._escalate_incident(
                    incident, "Medium severity incident open for over 24 hours"
                )

    def _escalate_incident(self, incident: SecurityIncident, reason: str) -> None:
        """Escalate an incident."""
        incident.response_actions.append(
            f"{datetime.now(timezone.utc).isoformat()}: ESCALATED - {reason}"
        )

        # Send escalation notification (placeholder - would implement security alert method)
        logger.warning(
            "Incident escalation notification would be sent here",
            incident_id=incident.incident_id,
            reason=reason,
        )

        logger.warning(
            "Escalated security incident",
            incident_id=incident.incident_id,
            reason=reason,
        )

    async def _trigger_incident_response(self, incident: SecurityIncident) -> None:
        """Trigger automated incident response."""
        try:
            # Send immediate notification (placeholder - would implement security alert method)
            logger.warning(
                "Security incident notification would be sent here",
                incident_id=incident.incident_id,
                title=incident.title,
                severity=incident.severity.value,
            )

            # Execute automated response based on severity
            if incident.severity == IncidentSeverity.CRITICAL:
                await self._execute_critical_response(incident)
            elif incident.severity == IncidentSeverity.HIGH:
                await self._execute_high_response(incident)

        except Exception as e:
            logger.error(f"Error in incident response for {incident.incident_id}: {e}")

    async def _execute_critical_response(self, incident: SecurityIncident) -> None:
        """Execute critical incident response."""
        # Block suspicious IPs
        for ioc in incident.indicators_of_compromise:
            if ioc.startswith("ip:"):
                ip = ioc[3:]
                self.block_ip(ip, f"Critical incident {incident.incident_id}", 24)

        # Additional critical response actions would go here
        incident.response_actions.append(
            f"{datetime.now(timezone.utc).isoformat()}: Executed critical response"
        )

    async def _execute_high_response(self, incident: SecurityIncident) -> None:
        """Execute high severity incident response."""
        # Enhanced monitoring for related indicators
        incident.response_actions.append(
            f"{datetime.now(timezone.utc).isoformat()}: Enhanced monitoring activated"
        )

    # Response handlers

    def _handle_unauthorized_access(self, event: SecurityEvent) -> None:
        """Handle unauthorized access events."""
        # Check if this is part of a pattern
        recent_events = [
            e
            for e in self.security_events
            if e.source_ip == event.source_ip
            and e.timestamp > datetime.now(timezone.utc) - timedelta(minutes=10)
        ]

        if len(recent_events) >= 3:
            self.create_incident(
                f"Multiple unauthorized access attempts from {event.source_ip}",
                f"Detected {len(recent_events)} unauthorized access attempts",
                IncidentSeverity.HIGH,
                [e.event_id for e in recent_events],
            )

    def _handle_failed_login(self, event: SecurityEvent) -> None:
        """Handle failed login events."""
        # Already handled in anomaly detection
        pass

    def _handle_suspicious_activity(self, event: SecurityEvent) -> None:
        """Handle suspicious activity events."""
        if event.risk_score >= 8.0:
            self.create_incident(
                f"High-risk suspicious activity from {event.source_ip}",
                f"Suspicious activity with risk score {event.risk_score}",
                IncidentSeverity.HIGH,
                [event.event_id],
            )

    def _handle_data_breach(self, event: SecurityEvent) -> None:
        """Handle data breach events."""
        self.create_incident(
            f"Data breach detected: {event.resource}",
            f"Potential data breach involving {event.resource}",
            IncidentSeverity.CRITICAL,
            [event.event_id],
        )

    def _handle_malicious_request(self, event: SecurityEvent) -> None:
        """Handle malicious request events."""
        # Block IP if confidence is high
        if event.risk_score >= 8.0:
            self.block_ip(event.source_ip, f"Malicious request: {event.event_id}", 12)


# Global security monitoring service instance
security_monitoring_service = SecurityMonitoringService()

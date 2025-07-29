"""
Notification and alert system for Prior Authorization Agent.

This module provides email notifications, real-time dashboard alerts,
and escalation notifications for authorization request status changes.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Set
from pydantic import BaseModel, Field, ConfigDict

from src.models.enums import RequestStatus, DecisionStatus, UrgencyLevel
from src.models.authorization import AuthorizationRequest, AuthorizationDecision
from src.core.logging import get_logger

logger = get_logger(__name__)


class NotificationPreferences(BaseModel):
    """Provider notification preferences."""
    provider_id: str
    email_address: str
    enable_email_notifications: bool = True
    enable_dashboard_alerts: bool = True
    enable_escalation_notifications: bool = True
    notification_frequency: str = "immediate"  # immediate, hourly, daily
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "provider_id": "prov_12345",
                "email_address": "provider@hospital.com",
                "enable_email_notifications": True,
                "enable_dashboard_alerts": True,
                "enable_escalation_notifications": True,
                "notification_frequency": "immediate"
            }
        }
    )


class NotificationEvent(BaseModel):
    """Notification event data."""
    event_id: str
    event_type: str  # decision_made, status_change, escalation, info_needed
    request_id: str
    provider_id: str
    title: str
    message: str
    priority: str = "normal"  # low, normal, high, urgent
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sent_at: Optional[datetime] = None
    delivery_status: str = "pending"  # pending, sent, failed, delivered
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "event_id": "evt_2024_001234",
                "event_type": "decision_made",
                "request_id": "req_2024_001234",
                "provider_id": "prov_12345",
                "title": "Authorization Approved",
                "message": "Your authorization request has been approved.",
                "priority": "normal",
                "delivery_status": "pending"
            }
        }
    )


class DashboardAlert(BaseModel):
    """Real-time dashboard alert."""
    alert_id: str
    provider_id: str
    alert_type: str  # success, info, warning, error
    title: str
    message: str
    request_id: Optional[str] = None
    action_required: bool = False
    action_url: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    is_read: bool = False
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "alert_id": "alert_2024_001234",
                "provider_id": "prov_12345",
                "alert_type": "success",
                "title": "Authorization Approved",
                "message": "Request req_2024_001234 has been approved.",
                "request_id": "req_2024_001234",
                "action_required": False,
                "is_read": False
            }
        }
    )


class EscalationRule(BaseModel):
    """Escalation rule configuration."""
    rule_id: str
    name: str
    condition: str  # time_threshold, status_change, urgency_level
    threshold_hours: Optional[int] = None
    target_status: Optional[List[RequestStatus]] = None
    urgency_levels: Optional[List[UrgencyLevel]] = None
    escalation_actions: List[str]  # email_supervisor, priority_queue, manual_review
    is_active: bool = True
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rule_id": "esc_001",
                "name": "Urgent Request Delay",
                "condition": "time_threshold",
                "threshold_hours": 2,
                "urgency_levels": ["urgent", "emergent"],
                "escalation_actions": ["email_supervisor", "priority_queue"],
                "is_active": True
            }
        }
    )


class NotificationService:
    """
    Service for handling notifications, alerts, and escalations.
    
    Provides email notifications, real-time dashboard alerts,
    and escalation notifications for delayed requests.
    """
    
    def __init__(self):
        """Initialize notification service."""
        self._notification_preferences: Dict[str, NotificationPreferences] = {}
        self._dashboard_alerts: Dict[str, List[DashboardAlert]] = {}
        self._escalation_rules: List[EscalationRule] = []
        self._notification_queue: List[NotificationEvent] = []
        self._email_config = self._load_email_config()
        
        # Initialize default escalation rules
        self._initialize_default_escalation_rules()
        
        logger.info("Notification service initialized")
    
    async def send_decision_notification(
        self,
        request: AuthorizationRequest,
        decision: AuthorizationDecision
    ) -> bool:
        """
        Send notification when a decision is made.
        
        Args:
            request: Authorization request
            decision: Authorization decision
            
        Returns:
            True if notification sent successfully
        """
        try:
            # Get provider preferences
            preferences = await self._get_provider_preferences(request.provider_id)
            if not preferences:
                logger.warning(
                    "No notification preferences found for provider",
                    provider_id=request.provider_id
                )
                return False
            
            # Create notification event
            event = await self._create_decision_notification_event(request, decision)
            
            # Send email notification if enabled
            email_sent = False
            if preferences.enable_email_notifications:
                email_sent = await self._send_email_notification(preferences, event)
            
            # Create dashboard alert if enabled
            alert_created = False
            if preferences.enable_dashboard_alerts:
                alert_created = await self._create_dashboard_alert(request, decision)
            
            # Log notification activity
            logger.info(
                "Decision notification processed",
                request_id=request.request_id,
                provider_id=request.provider_id,
                decision_status=decision.status.value,
                email_sent=email_sent,
                alert_created=alert_created
            )
            
            return email_sent or alert_created
            
        except Exception as e:
            logger.error(
                "Error sending decision notification",
                request_id=request.request_id,
                provider_id=request.provider_id,
                error=str(e),
                exc_info=True
            )
            return False
    
    async def send_status_update_notification(
        self,
        request: AuthorizationRequest,
        old_status: RequestStatus,
        new_status: RequestStatus,
        message: Optional[str] = None
    ) -> bool:
        """
        Send notification for status changes.
        
        Args:
            request: Authorization request
            old_status: Previous status
            new_status: New status
            message: Optional custom message
            
        Returns:
            True if notification sent successfully
        """
        try:
            # Get provider preferences
            preferences = await self._get_provider_preferences(request.provider_id)
            if not preferences:
                return False
            
            # Create status update event
            event = await self._create_status_update_event(
                request, old_status, new_status, message
            )
            
            # Send notifications based on preferences
            email_sent = False
            if preferences.enable_email_notifications:
                email_sent = await self._send_email_notification(preferences, event)
            
            alert_created = False
            if preferences.enable_dashboard_alerts:
                alert_created = await self._create_status_alert(
                    request, old_status, new_status, message
                )
            
            logger.info(
                "Status update notification processed",
                request_id=request.request_id,
                provider_id=request.provider_id,
                old_status=old_status.value,
                new_status=new_status.value,
                email_sent=email_sent,
                alert_created=alert_created
            )
            
            return email_sent or alert_created
            
        except Exception as e:
            logger.error(
                "Error sending status update notification",
                request_id=request.request_id,
                provider_id=request.provider_id,
                error=str(e),
                exc_info=True
            )
            return False
    
    async def send_escalation_notification(
        self,
        request: AuthorizationRequest,
        escalation_reason: str,
        escalation_actions: List[str]
    ) -> bool:
        """
        Send escalation notification for delayed requests.
        
        Args:
            request: Authorization request
            escalation_reason: Reason for escalation
            escalation_actions: Actions being taken
            
        Returns:
            True if notification sent successfully
        """
        try:
            # Get provider preferences
            preferences = await self._get_provider_preferences(request.provider_id)
            if not preferences or not preferences.enable_escalation_notifications:
                return False
            
            # Create escalation event
            event = await self._create_escalation_event(
                request, escalation_reason, escalation_actions
            )
            
            # Send high-priority email notification
            email_sent = await self._send_email_notification(preferences, event)
            
            # Create urgent dashboard alert
            alert_created = await self._create_escalation_alert(
                request, escalation_reason, escalation_actions
            )
            
            logger.warning(
                "Escalation notification sent",
                request_id=request.request_id,
                provider_id=request.provider_id,
                escalation_reason=escalation_reason,
                email_sent=email_sent,
                alert_created=alert_created
            )
            
            return email_sent or alert_created
            
        except Exception as e:
            logger.error(
                "Error sending escalation notification",
                request_id=request.request_id,
                provider_id=request.provider_id,
                error=str(e),
                exc_info=True
            )
            return False
    
    async def get_dashboard_alerts(
        self,
        provider_id: str,
        include_read: bool = False,
        limit: int = 50
    ) -> List[DashboardAlert]:
        """
        Get dashboard alerts for a provider.
        
        Args:
            provider_id: Provider identifier
            include_read: Whether to include read alerts
            limit: Maximum number of alerts to return
            
        Returns:
            List of dashboard alerts
        """
        try:
            provider_alerts = self._dashboard_alerts.get(provider_id, [])
            
            # Filter alerts
            filtered_alerts = []
            for alert in provider_alerts:
                # Skip read alerts if not requested
                if not include_read and alert.is_read:
                    continue
                
                # Skip expired alerts
                if alert.expires_at and alert.expires_at < datetime.now(timezone.utc):
                    continue
                
                filtered_alerts.append(alert)
            
            # Sort by creation time (newest first) and limit
            filtered_alerts.sort(key=lambda x: x.created_at, reverse=True)
            
            return filtered_alerts[:limit]
            
        except Exception as e:
            logger.error(
                "Error retrieving dashboard alerts",
                provider_id=provider_id,
                error=str(e),
                exc_info=True
            )
            return []
    
    async def mark_alert_as_read(self, provider_id: str, alert_id: str) -> bool:
        """
        Mark a dashboard alert as read.
        
        Args:
            provider_id: Provider identifier
            alert_id: Alert identifier
            
        Returns:
            True if alert was marked as read
        """
        try:
            provider_alerts = self._dashboard_alerts.get(provider_id, [])
            
            for alert in provider_alerts:
                if alert.alert_id == alert_id:
                    alert.is_read = True
                    logger.info(
                        "Alert marked as read",
                        provider_id=provider_id,
                        alert_id=alert_id
                    )
                    return True
            
            logger.warning(
                "Alert not found",
                provider_id=provider_id,
                alert_id=alert_id
            )
            return False
            
        except Exception as e:
            logger.error(
                "Error marking alert as read",
                provider_id=provider_id,
                alert_id=alert_id,
                error=str(e),
                exc_info=True
            )
            return False
    
    async def check_escalation_rules(self, request: AuthorizationRequest) -> List[str]:
        """
        Check if request meets escalation criteria.
        
        Args:
            request: Authorization request to check
            
        Returns:
            List of escalation actions to take
        """
        try:
            escalation_actions = []
            current_time = datetime.now(timezone.utc)
            
            for rule in self._escalation_rules:
                if not rule.is_active:
                    continue
                
                should_escalate = False
                
                # Check time threshold
                if rule.condition == "time_threshold" and rule.threshold_hours:
                    time_since_submission = current_time - request.submitted_at
                    hours_elapsed = time_since_submission.total_seconds() / 3600
                    
                    if hours_elapsed >= rule.threshold_hours:
                        # If urgency levels are specified, check if request matches
                        if rule.urgency_levels:
                            if request.urgency_level in rule.urgency_levels:
                                should_escalate = True
                        else:
                            # No urgency filter, escalate based on time alone
                            should_escalate = True
                
                # Check status conditions
                elif rule.condition == "status_change" and rule.target_status:
                    if request.status in rule.target_status:
                        should_escalate = True
                
                if should_escalate:
                    escalation_actions.extend(rule.escalation_actions)
                    logger.info(
                        "Escalation rule triggered",
                        request_id=request.request_id,
                        rule_id=rule.rule_id,
                        rule_name=rule.name
                    )
            
            return list(set(escalation_actions))  # Remove duplicates
            
        except Exception as e:
            logger.error(
                "Error checking escalation rules",
                request_id=request.request_id,
                error=str(e),
                exc_info=True
            )
            return []
    
    async def update_notification_preferences(
        self,
        provider_id: str,
        preferences: NotificationPreferences
    ) -> bool:
        """
        Update notification preferences for a provider.
        
        Args:
            provider_id: Provider identifier
            preferences: New notification preferences
            
        Returns:
            True if preferences updated successfully
        """
        try:
            self._notification_preferences[provider_id] = preferences
            
            logger.info(
                "Notification preferences updated",
                provider_id=provider_id,
                email_enabled=preferences.enable_email_notifications,
                alerts_enabled=preferences.enable_dashboard_alerts
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "Error updating notification preferences",
                provider_id=provider_id,
                error=str(e),
                exc_info=True
            )
            return False
    
    # Private helper methods
    
    async def _get_provider_preferences(self, provider_id: str) -> Optional[NotificationPreferences]:
        """Get notification preferences for a provider."""
        # Return existing preferences or create default ones
        if provider_id not in self._notification_preferences:
            # Create default preferences (in production, this would be from database)
            default_prefs = NotificationPreferences(
                provider_id=provider_id,
                email_address=f"provider_{provider_id}@hospital.com",
                enable_email_notifications=True,
                enable_dashboard_alerts=True,
                enable_escalation_notifications=True
            )
            self._notification_preferences[provider_id] = default_prefs
        
        return self._notification_preferences.get(provider_id)
    
    async def _create_decision_notification_event(
        self,
        request: AuthorizationRequest,
        decision: AuthorizationDecision
    ) -> NotificationEvent:
        """Create notification event for decision."""
        event_id = f"evt_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{request.request_id}"
        
        # Create title and message based on decision status
        if decision.status == DecisionStatus.APPROVED:
            title = "Authorization Approved"
            message = f"Your authorization request {request.request_id} has been approved."
            if decision.authorization_number:
                message += f" Authorization number: {decision.authorization_number}"
        elif decision.status == DecisionStatus.DENIED:
            title = "Authorization Denied"
            message = f"Your authorization request {request.request_id} has been denied."
        else:  # MORE_INFO_NEEDED
            title = "Additional Information Required"
            message = f"Your authorization request {request.request_id} requires additional information."
        
        return NotificationEvent(
            event_id=event_id,
            event_type="decision_made",
            request_id=request.request_id,
            provider_id=request.provider_id,
            title=title,
            message=message,
            priority="high" if request.urgency_level == UrgencyLevel.URGENT else "normal"
        )
    
    async def _create_status_update_event(
        self,
        request: AuthorizationRequest,
        old_status: RequestStatus,
        new_status: RequestStatus,
        message: Optional[str]
    ) -> NotificationEvent:
        """Create notification event for status update."""
        event_id = f"evt_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{request.request_id}"
        
        title = f"Status Update: {new_status.value.replace('_', ' ').title()}"
        default_message = f"Request {request.request_id} status changed from {old_status.value} to {new_status.value}."
        
        return NotificationEvent(
            event_id=event_id,
            event_type="status_change",
            request_id=request.request_id,
            provider_id=request.provider_id,
            title=title,
            message=message or default_message,
            priority="normal"
        )
    
    async def _create_escalation_event(
        self,
        request: AuthorizationRequest,
        escalation_reason: str,
        escalation_actions: List[str]
    ) -> NotificationEvent:
        """Create notification event for escalation."""
        event_id = f"evt_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{request.request_id}"
        
        title = "Request Escalated"
        message = f"Request {request.request_id} has been escalated. Reason: {escalation_reason}"
        
        return NotificationEvent(
            event_id=event_id,
            event_type="escalation",
            request_id=request.request_id,
            provider_id=request.provider_id,
            title=title,
            message=message,
            priority="urgent"
        )
    
    async def _send_email_notification(
        self,
        preferences: NotificationPreferences,
        event: NotificationEvent
    ) -> bool:
        """Send email notification."""
        try:
            # In production, this would use a proper email service
            # For now, we'll simulate email sending
            
            logger.info(
                "Email notification sent (simulated)",
                provider_id=preferences.provider_id,
                email=preferences.email_address,
                event_type=event.event_type,
                title=event.title
            )
            
            # Update event status
            event.sent_at = datetime.now(timezone.utc)
            event.delivery_status = "sent"
            
            return True
            
        except Exception as e:
            logger.error(
                "Error sending email notification",
                provider_id=preferences.provider_id,
                error=str(e),
                exc_info=True
            )
            
            event.delivery_status = "failed"
            return False
    
    async def _create_dashboard_alert(
        self,
        request: AuthorizationRequest,
        decision: AuthorizationDecision
    ) -> bool:
        """Create dashboard alert for decision."""
        try:
            alert_id = f"alert_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{request.request_id}"
            
            # Determine alert type and message
            if decision.status == DecisionStatus.APPROVED:
                alert_type = "success"
                title = "Authorization Approved"
                message = f"Request {request.request_id} has been approved."
            elif decision.status == DecisionStatus.DENIED:
                alert_type = "error"
                title = "Authorization Denied"
                message = f"Request {request.request_id} has been denied."
            else:  # MORE_INFO_NEEDED
                alert_type = "warning"
                title = "Additional Information Required"
                message = f"Request {request.request_id} requires additional information."
            
            alert = DashboardAlert(
                alert_id=alert_id,
                provider_id=request.provider_id,
                alert_type=alert_type,
                title=title,
                message=message,
                request_id=request.request_id,
                action_required=(decision.status == DecisionStatus.MORE_INFO_NEEDED),
                expires_at=datetime.now(timezone.utc) + timedelta(days=7)
            )
            
            # Add to provider's alerts
            if request.provider_id not in self._dashboard_alerts:
                self._dashboard_alerts[request.provider_id] = []
            
            self._dashboard_alerts[request.provider_id].append(alert)
            
            return True
            
        except Exception as e:
            logger.error(
                "Error creating dashboard alert",
                request_id=request.request_id,
                error=str(e),
                exc_info=True
            )
            return False
    
    async def _create_status_alert(
        self,
        request: AuthorizationRequest,
        old_status: RequestStatus,
        new_status: RequestStatus,
        message: Optional[str]
    ) -> bool:
        """Create dashboard alert for status change."""
        try:
            alert_id = f"alert_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{request.request_id}"
            
            alert = DashboardAlert(
                alert_id=alert_id,
                provider_id=request.provider_id,
                alert_type="info",
                title="Status Update",
                message=message or f"Request {request.request_id} status updated to {new_status.value}.",
                request_id=request.request_id,
                action_required=False,
                expires_at=datetime.now(timezone.utc) + timedelta(days=3)
            )
            
            # Add to provider's alerts
            if request.provider_id not in self._dashboard_alerts:
                self._dashboard_alerts[request.provider_id] = []
            
            self._dashboard_alerts[request.provider_id].append(alert)
            
            return True
            
        except Exception as e:
            logger.error(
                "Error creating status alert",
                request_id=request.request_id,
                error=str(e),
                exc_info=True
            )
            return False
    
    async def _create_escalation_alert(
        self,
        request: AuthorizationRequest,
        escalation_reason: str,
        escalation_actions: List[str]
    ) -> bool:
        """Create dashboard alert for escalation."""
        try:
            alert_id = f"alert_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{request.request_id}"
            
            alert = DashboardAlert(
                alert_id=alert_id,
                provider_id=request.provider_id,
                alert_type="warning",
                title="Request Escalated",
                message=f"Request {request.request_id} has been escalated: {escalation_reason}",
                request_id=request.request_id,
                action_required=True,
                expires_at=datetime.now(timezone.utc) + timedelta(days=14)
            )
            
            # Add to provider's alerts
            if request.provider_id not in self._dashboard_alerts:
                self._dashboard_alerts[request.provider_id] = []
            
            self._dashboard_alerts[request.provider_id].append(alert)
            
            return True
            
        except Exception as e:
            logger.error(
                "Error creating escalation alert",
                request_id=request.request_id,
                error=str(e),
                exc_info=True
            )
            return False
    
    def _load_email_config(self) -> Dict[str, Any]:
        """Load email configuration."""
        # In production, this would load from environment variables or config file
        return {
            "smtp_server": "smtp.hospital.com",
            "smtp_port": 587,
            "username": "noreply@hospital.com",
            "password": "secure_password",
            "use_tls": True
        }
    
    def _initialize_default_escalation_rules(self):
        """Initialize default escalation rules."""
        self._escalation_rules = [
            EscalationRule(
                rule_id="esc_001",
                name="Urgent Request Delay",
                condition="time_threshold",
                threshold_hours=2,
                urgency_levels=[UrgencyLevel.URGENT, UrgencyLevel.EMERGENT],
                escalation_actions=["email_supervisor", "priority_queue"]
            ),
            EscalationRule(
                rule_id="esc_002",
                name="Routine Request Delay",
                condition="time_threshold",
                threshold_hours=24,
                urgency_levels=[UrgencyLevel.ROUTINE],
                escalation_actions=["email_provider", "status_update"]
            ),
            EscalationRule(
                rule_id="esc_003",
                name="Info Needed Timeout",
                condition="status_change",
                target_status=[RequestStatus.MORE_INFO_NEEDED],
                escalation_actions=["reminder_email", "follow_up_call"]
            )
        ]
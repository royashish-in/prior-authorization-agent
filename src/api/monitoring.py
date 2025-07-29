"""
API endpoints for monitoring and dashboard data.

This module provides REST endpoints for accessing system metrics,
dashboard data, and alert information.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import logging

from src.services.monitoring import metrics_collector
from src.services.dashboard_metrics import dashboard_metrics_service
from src.services.database_monitoring import db_monitoring_service
from src.services.security_monitoring import security_monitoring_service, SecurityEventType, IncidentSeverity, IncidentStatus
from src.auth.oauth2 import get_current_user
from src.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])


@router.get("/metrics/current")
async def get_current_metrics(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get current system metrics snapshot.
    
    Returns:
        Current metrics for all categories (application, business, infrastructure, compliance)
    """
    try:
        metrics = metrics_collector.get_current_metrics()
        
        logger.info("Retrieved current metrics", 
                   user_id=current_user.get('user_id'),
                   metrics_timestamp=metrics.get('timestamp'))
        
        return {
            "status": "success",
            "data": metrics,
            "retrieved_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get current metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve current metrics")


@router.get("/metrics/history")
async def get_metrics_history(
    hours: int = Query(default=24, ge=1, le=168, description="Hours of history to retrieve (1-168)"),
    metric_type: Optional[str] = Query(default=None, description="Filter by metric type"),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get historical metrics data.
    
    Args:
        hours: Number of hours of history to retrieve (1-168)
        metric_type: Optional filter by metric type (application, business, infrastructure, compliance)
        
    Returns:
        Historical metrics data
    """
    try:
        history = metrics_collector.get_metrics_history(hours=hours)
        
        # Filter by metric type if specified
        if metric_type:
            if metric_type not in history:
                raise HTTPException(status_code=400, detail=f"Invalid metric type: {metric_type}")
            history = {metric_type: history[metric_type]}
        
        logger.info("Retrieved metrics history", 
                   user_id=current_user.get('user_id'),
                   hours=hours,
                   metric_type=metric_type,
                   total_points=sum(len(data) for data in history.values()))
        
        return {
            "status": "success",
            "data": history,
            "time_range_hours": hours,
            "retrieved_at": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get metrics history: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve metrics history")


@router.get("/alerts/active")
async def get_active_alerts(
    severity: Optional[str] = Query(default=None, description="Filter by severity"),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get currently active alerts.
    
    Args:
        severity: Optional filter by severity (LOW, MEDIUM, HIGH, CRITICAL)
        
    Returns:
        List of active alerts
    """
    try:
        current_metrics = metrics_collector.get_current_metrics()
        active_alerts = current_metrics.get('active_alerts', [])
        
        # Filter by severity if specified
        if severity:
            severity = severity.upper()
            if severity not in ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']:
                raise HTTPException(status_code=400, detail="Invalid severity level")
            
            active_alerts = [alert for alert in active_alerts if alert.get('severity') == severity]
        
        logger.info("Retrieved active alerts", 
                   user_id=current_user.get('user_id'),
                   total_alerts=len(active_alerts),
                   severity_filter=severity)
        
        return {
            "status": "success",
            "data": {
                "alerts": active_alerts,
                "total_count": len(active_alerts),
                "severity_counts": _count_alerts_by_severity(active_alerts)
            },
            "retrieved_at": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get active alerts: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve active alerts")


@router.get("/alerts/history")
async def get_alert_history(
    hours: int = Query(default=24, ge=1, le=168, description="Hours of history to retrieve"),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get alert history.
    
    Args:
        hours: Number of hours of history to retrieve
        
    Returns:
        Historical alert data
    """
    try:
        alert_history = metrics_collector.get_alert_history(hours=hours)
        
        logger.info("Retrieved alert history", 
                   user_id=current_user.get('user_id'),
                   hours=hours,
                   total_alerts=len(alert_history))
        
        return {
            "status": "success",
            "data": {
                "alerts": alert_history,
                "total_count": len(alert_history),
                "time_range_hours": hours
            },
            "retrieved_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get alert history: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve alert history")


@router.get("/dashboards")
async def get_available_dashboards(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get list of available dashboards.
    
    Returns:
        List of available dashboards with metadata
    """
    try:
        dashboards = dashboard_metrics_service.get_available_dashboards()
        
        # Filter dashboards based on user roles (if role information is available)
        user_roles = current_user.get('roles', ['admin'])  # Default to admin if no roles
        accessible_dashboards = []
        
        for dashboard in dashboards:
            dashboard_roles = dashboard.get('access_roles', [])
            if any(role in user_roles for role in dashboard_roles):
                accessible_dashboards.append(dashboard)
        
        logger.info("Retrieved available dashboards", 
                   user_id=current_user.get('user_id'),
                   total_dashboards=len(accessible_dashboards))
        
        return {
            "status": "success",
            "data": {
                "dashboards": accessible_dashboards,
                "total_count": len(accessible_dashboards)
            },
            "retrieved_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get available dashboards: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve dashboards")


@router.get("/dashboards/{dashboard_id}")
async def get_dashboard_data(
    dashboard_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get complete dashboard data including all widget data.
    
    Args:
        dashboard_id: ID of the dashboard to retrieve
        
    Returns:
        Complete dashboard data with widget information
    """
    try:
        # Check if user has access to this dashboard
        available_dashboards = dashboard_metrics_service.get_available_dashboards()
        user_roles = current_user.get('roles', ['admin'])
        
        dashboard_info = next((d for d in available_dashboards if d['dashboard_id'] == dashboard_id), None)
        if not dashboard_info:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        
        dashboard_roles = dashboard_info.get('access_roles', [])
        if not any(role in user_roles for role in dashboard_roles):
            raise HTTPException(status_code=403, detail="Access denied to this dashboard")
        
        dashboard_data = await dashboard_metrics_service.get_dashboard_data(dashboard_id)
        
        logger.info("Retrieved dashboard data", 
                   user_id=current_user.get('user_id'),
                   dashboard_id=dashboard_id,
                   widget_count=len(dashboard_data.get('widget_data', {})))
        
        return {
            "status": "success",
            "data": dashboard_data,
            "retrieved_at": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get dashboard data for {dashboard_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve dashboard data")


@router.post("/dashboards")
async def create_custom_dashboard(
    dashboard_config: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Create a custom dashboard.
    
    Args:
        dashboard_config: Dashboard configuration including widgets
        
    Returns:
        Created dashboard information
    """
    try:
        # Validate required fields
        required_fields = ['dashboard_id', 'title', 'widgets']
        for field in required_fields:
            if field not in dashboard_config:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Add creator information
        dashboard_config['created_by'] = current_user.get('user_id')
        dashboard_config['created_at'] = datetime.now(timezone.utc).isoformat()
        
        dashboard_id = dashboard_metrics_service.create_custom_dashboard(dashboard_config)
        
        logger.info("Created custom dashboard", 
                   user_id=current_user.get('user_id'),
                   dashboard_id=dashboard_id)
        
        return {
            "status": "success",
            "data": {
                "dashboard_id": dashboard_id,
                "message": "Dashboard created successfully"
            },
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create custom dashboard: {e}")
        raise HTTPException(status_code=500, detail="Failed to create dashboard")


@router.get("/database/performance")
async def get_database_performance(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get database performance metrics and analysis.
    
    Returns:
        Database performance report
    """
    try:
        # Check if user has database monitoring permissions
        user_roles = current_user.get('roles', [])
        if not any(role in ['admin', 'dba', 'developer'] for role in user_roles):
            raise HTTPException(status_code=403, detail="Access denied to database metrics")
        
        performance_report = await db_monitoring_service.generate_performance_report()
        
        logger.info("Retrieved database performance report", 
                   user_id=current_user.get('user_id'),
                   report_timestamp=performance_report.get('generated_at'))
        
        return {
            "status": "success",
            "data": performance_report,
            "retrieved_at": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get database performance: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve database performance")


@router.get("/health")
async def get_system_health() -> Dict[str, Any]:
    """
    Get overall system health status.
    
    Returns:
        System health summary
    """
    try:
        current_metrics = metrics_collector.get_current_metrics()
        active_alerts = current_metrics.get('active_alerts', [])
        
        # Calculate health score based on alerts
        critical_alerts = len([a for a in active_alerts if a.get('severity') == 'CRITICAL'])
        high_alerts = len([a for a in active_alerts if a.get('severity') == 'HIGH'])
        
        if critical_alerts > 0:
            health_status = "critical"
        elif high_alerts > 2:
            health_status = "degraded"
        elif len(active_alerts) > 5:
            health_status = "warning"
        else:
            health_status = "healthy"
        
        # Get key metrics
        app_metrics = current_metrics.get('application', {})
        infra_metrics = current_metrics.get('infrastructure', {})
        
        health_summary = {
            "overall_status": health_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "key_metrics": {
                "requests_per_second": app_metrics.get('requests_per_second', 0),
                "avg_response_time": app_metrics.get('avg_response_time', 0),
                "error_rate": app_metrics.get('error_rate', 0),
                "cpu_usage": infra_metrics.get('cpu_usage_percent', 0),
                "memory_usage": infra_metrics.get('memory_usage_percent', 0)
            },
            "alert_summary": {
                "total_alerts": len(active_alerts),
                "critical": critical_alerts,
                "high": high_alerts,
                "medium": len([a for a in active_alerts if a.get('severity') == 'MEDIUM']),
                "low": len([a for a in active_alerts if a.get('severity') == 'LOW'])
            }
        }
        
        return {
            "status": "success",
            "data": health_summary
        }
        
    except Exception as e:
        logger.error(f"Failed to get system health: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve system health")


@router.post("/metrics/record")
async def record_custom_metric(
    metric_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Record a custom metric event.
    
    Args:
        metric_data: Custom metric data to record
        
    Returns:
        Confirmation of metric recording
    """
    try:
        metric_type = metric_data.get('type')
        if not metric_type:
            raise HTTPException(status_code=400, detail="Metric type is required")
        
        # Record different types of metrics
        if metric_type == 'request':
            duration = metric_data.get('duration_ms', 0)
            error = metric_data.get('error', False)
            metrics_collector.record_request(duration, error)
            
        elif metric_type == 'authorization_decision':
            decision = metric_data.get('decision', '')
            processing_time = metric_data.get('processing_time_seconds', 0)
            metrics_collector.record_authorization_decision(decision, processing_time)
            
        elif metric_type == 'session':
            session_id = metric_data.get('session_id', '')
            active = metric_data.get('active', True)
            metrics_collector.record_session(session_id, active)
            
        elif metric_type == 'phi_access':
            user_id = metric_data.get('user_id', current_user.get('user_id'))
            resource = metric_data.get('resource', '')
            metrics_collector.record_phi_access(user_id, resource)
            
        elif metric_type == 'security_incident':
            incident_type = metric_data.get('incident_type', '')
            details = metric_data.get('details', {})
            metrics_collector.record_security_incident(incident_type, details)
            
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported metric type: {metric_type}")
        
        logger.info("Recorded custom metric", 
                   user_id=current_user.get('user_id'),
                   metric_type=metric_type)
        
        return {
            "status": "success",
            "message": f"Metric '{metric_type}' recorded successfully",
            "recorded_at": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to record custom metric: {e}")
        raise HTTPException(status_code=500, detail="Failed to record metric")


def _count_alerts_by_severity(alerts: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count alerts by severity level."""
    counts = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
    
    for alert in alerts:
        severity = alert.get('severity', 'LOW')
        if severity in counts:
            counts[severity] += 1
    
    return counts


# Security Monitoring Endpoints

@router.get("/security/events")
async def get_security_events(
    hours: int = Query(default=24, ge=1, le=168, description="Hours of history to retrieve"),
    event_type: Optional[str] = Query(default=None, description="Filter by event type"),
    severity: Optional[str] = Query(default=None, description="Filter by severity"),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get security events with optional filtering.
    
    Args:
        hours: Number of hours of history to retrieve
        event_type: Optional filter by event type
        severity: Optional filter by severity
        
    Returns:
        List of security events
    """
    try:
        # Check if user has security monitoring permissions
        user_roles = current_user.get('roles', [])
        if not any(role in ['admin', 'security_analyst', 'compliance_officer'] for role in user_roles):
            raise HTTPException(status_code=403, detail="Access denied to security events")
        
        # Parse filters
        event_type_filter = None
        if event_type:
            try:
                event_type_filter = SecurityEventType(event_type.lower())
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid event type: {event_type}")
        
        severity_filter = None
        if severity:
            try:
                severity_filter = IncidentSeverity(severity.lower())
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")
        
        events = security_monitoring_service.get_security_events(
            hours=hours,
            event_type=event_type_filter,
            severity=severity_filter
        )
        
        # Convert events to dict format
        events_data = []
        for event in events:
            event_dict = {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "timestamp": event.timestamp.isoformat(),
                "source_ip": event.source_ip,
                "user_id": event.user_id,
                "resource": event.resource,
                "severity": event.severity.value,
                "risk_score": event.risk_score,
                "indicators": event.indicators
            }
            # Only include details for authorized users
            if 'admin' in user_roles or 'security_analyst' in user_roles:
                event_dict["details"] = event.details
            events_data.append(event_dict)
        
        logger.info("Retrieved security events", 
                   user_id=current_user.get('user_id'),
                   hours=hours,
                   event_count=len(events_data))
        
        return {
            "status": "success",
            "data": {
                "events": events_data,
                "total_count": len(events_data),
                "time_range_hours": hours,
                "filters": {
                    "event_type": event_type,
                    "severity": severity
                }
            },
            "retrieved_at": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get security events: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve security events")


@router.post("/security/events")
async def record_security_event(
    event_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Record a security event.
    
    Args:
        event_data: Security event data
        
    Returns:
        Event ID and confirmation
    """
    try:
        # Validate required fields
        required_fields = ['event_type', 'source_ip']
        for field in required_fields:
            if field not in event_data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Parse event type
        try:
            event_type = SecurityEventType(event_data['event_type'].lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid event type: {event_data['event_type']}")
        
        # Record the event
        event_id = security_monitoring_service.record_security_event(
            event_type=event_type,
            source_ip=event_data['source_ip'],
            user_id=event_data.get('user_id'),
            resource=event_data.get('resource', ''),
            details=event_data.get('details', {}),
            raw_data=event_data.get('raw_data', {})
        )
        
        logger.info("Recorded security event", 
                   user_id=current_user.get('user_id'),
                   event_id=event_id,
                   event_type=event_type.value)
        
        return {
            "status": "success",
            "data": {
                "event_id": event_id,
                "message": "Security event recorded successfully"
            },
            "recorded_at": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to record security event: {e}")
        raise HTTPException(status_code=500, detail="Failed to record security event")


@router.get("/security/incidents")
async def get_security_incidents(
    status: Optional[str] = Query(default=None, description="Filter by status"),
    severity: Optional[str] = Query(default=None, description="Filter by severity"),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get security incidents with optional filtering.
    
    Args:
        status: Optional filter by status
        severity: Optional filter by severity
        
    Returns:
        List of security incidents
    """
    try:
        # Check permissions
        user_roles = current_user.get('roles', [])
        if not any(role in ['admin', 'security_analyst', 'compliance_officer'] for role in user_roles):
            raise HTTPException(status_code=403, detail="Access denied to security incidents")
        
        # Parse filters
        status_filter = None
        if status:
            try:
                status_filter = IncidentStatus(status.lower())
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        severity_filter = None
        if severity:
            try:
                severity_filter = IncidentSeverity(severity.lower())
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")
        
        incidents = security_monitoring_service.get_incidents(
            status=status_filter,
            severity=severity_filter
        )
        
        # Convert incidents to dict format
        incidents_data = []
        for incident in incidents:
            incident_dict = {
                "incident_id": incident.incident_id,
                "title": incident.title,
                "description": incident.description,
                "severity": incident.severity.value,
                "status": incident.status.value,
                "created_at": incident.created_at.isoformat(),
                "updated_at": incident.updated_at.isoformat(),
                "assigned_to": incident.assigned_to,
                "event_count": len(incident.events),
                "indicators_of_compromise": incident.indicators_of_compromise,
                "response_actions_count": len(incident.response_actions)
            }
            
            if incident.closed_at:
                incident_dict["closed_at"] = incident.closed_at.isoformat()
            
            # Include detailed information for authorized users
            if 'admin' in user_roles or 'security_analyst' in user_roles:
                incident_dict["events"] = incident.events
                incident_dict["response_actions"] = incident.response_actions
                incident_dict["resolution_notes"] = incident.resolution_notes
            
            incidents_data.append(incident_dict)
        
        logger.info("Retrieved security incidents", 
                   user_id=current_user.get('user_id'),
                   incident_count=len(incidents_data))
        
        return {
            "status": "success",
            "data": {
                "incidents": incidents_data,
                "total_count": len(incidents_data),
                "filters": {
                    "status": status,
                    "severity": severity
                }
            },
            "retrieved_at": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get security incidents: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve security incidents")


@router.post("/security/incidents")
async def create_security_incident(
    incident_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Create a security incident.
    
    Args:
        incident_data: Incident creation data
        
    Returns:
        Incident ID and confirmation
    """
    try:
        # Check permissions
        user_roles = current_user.get('roles', [])
        if not any(role in ['admin', 'security_analyst'] for role in user_roles):
            raise HTTPException(status_code=403, detail="Access denied to create incidents")
        
        # Validate required fields
        required_fields = ['title', 'description', 'severity']
        for field in required_fields:
            if field not in incident_data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Parse severity
        try:
            severity = IncidentSeverity(incident_data['severity'].lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid severity: {incident_data['severity']}")
        
        # Create incident
        incident_id = security_monitoring_service.create_incident(
            title=incident_data['title'],
            description=incident_data['description'],
            severity=severity,
            event_ids=incident_data.get('event_ids', []),
            assigned_to=incident_data.get('assigned_to', current_user.get('user_id'))
        )
        
        logger.info("Created security incident", 
                   user_id=current_user.get('user_id'),
                   incident_id=incident_id,
                   severity=severity.value)
        
        return {
            "status": "success",
            "data": {
                "incident_id": incident_id,
                "message": "Security incident created successfully"
            },
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create security incident: {e}")
        raise HTTPException(status_code=500, detail="Failed to create security incident")


@router.put("/security/incidents/{incident_id}")
async def update_security_incident(
    incident_id: str,
    update_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Update a security incident.
    
    Args:
        incident_id: Incident ID to update
        update_data: Update data
        
    Returns:
        Update confirmation
    """
    try:
        # Check permissions
        user_roles = current_user.get('roles', [])
        if not any(role in ['admin', 'security_analyst'] for role in user_roles):
            raise HTTPException(status_code=403, detail="Access denied to update incidents")
        
        # Parse status if provided
        status = None
        if 'status' in update_data:
            try:
                status = IncidentStatus(update_data['status'].lower())
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {update_data['status']}")
        
        # Update incident
        success = security_monitoring_service.update_incident_status(
            incident_id=incident_id,
            status=status,
            notes=update_data.get('notes'),
            assigned_to=update_data.get('assigned_to')
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Incident not found")
        
        logger.info("Updated security incident", 
                   user_id=current_user.get('user_id'),
                   incident_id=incident_id,
                   status=status.value if status else None)
        
        return {
            "status": "success",
            "data": {
                "incident_id": incident_id,
                "message": "Security incident updated successfully"
            },
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update security incident: {e}")
        raise HTTPException(status_code=500, detail="Failed to update security incident")


@router.get("/security/threat-intelligence")
async def get_threat_intelligence_report(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get threat intelligence report.
    
    Returns:
        Comprehensive threat intelligence summary
    """
    try:
        # Check permissions
        user_roles = current_user.get('roles', [])
        if not any(role in ['admin', 'security_analyst', 'compliance_officer'] for role in user_roles):
            raise HTTPException(status_code=403, detail="Access denied to threat intelligence")
        
        report = security_monitoring_service.get_threat_intelligence_report()
        
        logger.info("Retrieved threat intelligence report", 
                   user_id=current_user.get('user_id'))
        
        return {
            "status": "success",
            "data": report,
            "retrieved_at": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get threat intelligence report: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve threat intelligence report")


@router.post("/security/threat-indicators")
async def add_threat_indicator(
    indicator_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Add a threat intelligence indicator.
    
    Args:
        indicator_data: Threat indicator data
        
    Returns:
        Confirmation of indicator addition
    """
    try:
        # Check permissions
        user_roles = current_user.get('roles', [])
        if not any(role in ['admin', 'security_analyst'] for role in user_roles):
            raise HTTPException(status_code=403, detail="Access denied to add threat indicators")
        
        # Validate required fields
        required_fields = ['indicator', 'indicator_type', 'threat_type', 'confidence', 'source']
        for field in required_fields:
            if field not in indicator_data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Validate confidence score
        confidence = indicator_data['confidence']
        if not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
            raise HTTPException(status_code=400, detail="Confidence must be a number between 0.0 and 1.0")
        
        # Add threat indicator
        security_monitoring_service.add_threat_indicator(
            indicator=indicator_data['indicator'],
            indicator_type=indicator_data['indicator_type'],
            threat_type=indicator_data['threat_type'],
            confidence=confidence,
            source=indicator_data['source'],
            description=indicator_data.get('description', '')
        )
        
        logger.info("Added threat indicator", 
                   user_id=current_user.get('user_id'),
                   indicator=indicator_data['indicator'],
                   indicator_type=indicator_data['indicator_type'])
        
        return {
            "status": "success",
            "data": {
                "message": "Threat indicator added successfully",
                "indicator": indicator_data['indicator']
            },
            "added_at": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add threat indicator: {e}")
        raise HTTPException(status_code=500, detail="Failed to add threat indicator")


@router.post("/security/check-threats")
async def check_threat_indicators(
    check_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Check indicators against threat intelligence.
    
    Args:
        check_data: Indicators to check (ip, domain, hash)
        
    Returns:
        Matching threat indicators
    """
    try:
        # Check permissions
        user_roles = current_user.get('roles', [])
        if not any(role in ['admin', 'security_analyst', 'developer'] for role in user_roles):
            raise HTTPException(status_code=403, detail="Access denied to check threat indicators")
        
        matches = security_monitoring_service.check_threat_indicators(
            ip=check_data.get('ip'),
            domain=check_data.get('domain'),
            hash_value=check_data.get('hash')
        )
        
        # Convert matches to dict format
        matches_data = []
        for match in matches:
            matches_data.append({
                "indicator": match.indicator,
                "indicator_type": match.indicator_type,
                "threat_type": match.threat_type,
                "confidence": match.confidence,
                "source": match.source,
                "first_seen": match.first_seen.isoformat(),
                "last_seen": match.last_seen.isoformat(),
                "description": match.description
            })
        
        logger.info("Checked threat indicators", 
                   user_id=current_user.get('user_id'),
                   matches_found=len(matches_data))
        
        return {
            "status": "success",
            "data": {
                "matches": matches_data,
                "match_count": len(matches_data),
                "checked_indicators": {k: v for k, v in check_data.items() if v is not None}
            },
            "checked_at": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check threat indicators: {e}")
        raise HTTPException(status_code=500, detail="Failed to check threat indicators")


@router.post("/security/block-ip")
async def block_ip_address(
    block_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Block an IP address.
    
    Args:
        block_data: IP blocking data
        
    Returns:
        Confirmation of IP blocking
    """
    try:
        # Check permissions
        user_roles = current_user.get('roles', [])
        if not any(role in ['admin', 'security_analyst'] for role in user_roles):
            raise HTTPException(status_code=403, detail="Access denied to block IP addresses")
        
        # Validate required fields
        if 'ip' not in block_data:
            raise HTTPException(status_code=400, detail="Missing required field: ip")
        
        if 'reason' not in block_data:
            raise HTTPException(status_code=400, detail="Missing required field: reason")
        
        # Block IP
        security_monitoring_service.block_ip(
            ip=block_data['ip'],
            reason=block_data['reason'],
            duration_hours=block_data.get('duration_hours', 24)
        )
        
        logger.warning("Blocked IP address", 
                      user_id=current_user.get('user_id'),
                      ip=block_data['ip'],
                      reason=block_data['reason'])
        
        return {
            "status": "success",
            "data": {
                "message": f"IP address {block_data['ip']} blocked successfully",
                "ip": block_data['ip'],
                "reason": block_data['reason'],
                "duration_hours": block_data.get('duration_hours', 24)
            },
            "blocked_at": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to block IP address: {e}")
        raise HTTPException(status_code=500, detail="Failed to block IP address")


@router.get("/security/blocked-ips")
async def get_blocked_ips(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get list of blocked IP addresses.
    
    Returns:
        List of blocked IPs
    """
    try:
        # Check permissions
        user_roles = current_user.get('roles', [])
        if not any(role in ['admin', 'security_analyst'] for role in user_roles):
            raise HTTPException(status_code=403, detail="Access denied to view blocked IPs")
        
        blocked_ips = list(security_monitoring_service.blocked_ips)
        
        logger.info("Retrieved blocked IPs list", 
                   user_id=current_user.get('user_id'),
                   blocked_count=len(blocked_ips))
        
        return {
            "status": "success",
            "data": {
                "blocked_ips": blocked_ips,
                "total_count": len(blocked_ips)
            },
            "retrieved_at": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get blocked IPs: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve blocked IPs")
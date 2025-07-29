"""
Comprehensive monitoring system for the Prior Authorization Agent.

This module provides application metrics collection, infrastructure monitoring,
and custom dashboards for system health and compliance metrics.
"""

import logging
import asyncio
import psutil
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import json
import threading
from concurrent.futures import ThreadPoolExecutor

from src.core.logging import get_logger, AuditLogger
from src.services.database_monitoring import db_monitoring_service
from src.core.config import get_settings

logger = get_logger(__name__)
audit_logger = AuditLogger()


@dataclass
class ApplicationMetrics:
    """Application-level performance metrics."""
    timestamp: datetime
    requests_per_second: float
    avg_response_time: float
    error_rate: float
    active_sessions: int
    authorization_decisions_per_minute: float
    approval_rate: float
    denial_rate: float
    pending_requests: int
    cache_hit_rate: float
    memory_usage_mb: float
    cpu_usage_percent: float


@dataclass
class BusinessMetrics:
    """Business KPI metrics."""
    timestamp: datetime
    total_requests_today: int
    total_approvals_today: int
    total_denials_today: int
    avg_processing_time_minutes: float
    sla_compliance_rate: float  # % of requests processed within 2 minutes
    provider_satisfaction_score: float
    policy_hit_rate: float
    medical_necessity_pass_rate: float
    audit_compliance_score: float


@dataclass
class InfrastructureMetrics:
    """Infrastructure performance metrics."""
    timestamp: datetime
    cpu_usage_percent: float
    memory_usage_percent: float
    disk_usage_percent: float
    network_io_mbps: float
    disk_io_mbps: float
    load_average: Tuple[float, float, float]
    process_count: int
    thread_count: int
    file_descriptors_used: int


@dataclass
class ComplianceMetrics:
    """HIPAA and regulatory compliance metrics."""
    timestamp: datetime
    phi_access_events: int
    unauthorized_access_attempts: int
    audit_log_completeness: float
    encryption_compliance_rate: float
    data_retention_compliance: float
    security_incidents: int
    policy_violations: int
    backup_success_rate: float


@dataclass
class SystemAlert:
    """System monitoring alert."""
    alert_id: str
    alert_type: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    title: str
    message: str
    metric_name: str
    current_value: float
    threshold_value: float
    timestamp: datetime
    resolved: bool
    resolution_time: Optional[datetime]
    suggested_actions: List[str]


class MetricsCollector:
    """
    Collects and aggregates various system metrics.
    
    Provides real-time monitoring of application performance,
    business KPIs, infrastructure health, and compliance status.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.metrics_history = {
            'application': deque(maxlen=1440),  # 24 hours at 1-minute intervals
            'business': deque(maxlen=1440),
            'infrastructure': deque(maxlen=1440),
            'compliance': deque(maxlen=1440)
        }
        
        # Request tracking
        self.request_times = deque(maxlen=10000)
        self.request_errors = deque(maxlen=1000)
        self.active_sessions = set()
        self.authorization_decisions = deque(maxlen=1000)
        
        # Performance counters
        self.counters = defaultdict(int)
        self.timers = defaultdict(list)
        
        # Alert management
        self.active_alerts = {}
        self.alert_history = deque(maxlen=10000)
        
        # Thresholds
        self.thresholds = {
            'response_time_ms': 2000,  # 2 seconds
            'error_rate_percent': 5.0,
            'cpu_usage_percent': 80.0,
            'memory_usage_percent': 85.0,
            'disk_usage_percent': 90.0,
            'sla_compliance_rate': 95.0,
            'cache_hit_rate': 85.0,
            'approval_rate_min': 60.0,
            'approval_rate_max': 95.0
        }
        
        # Background monitoring thread
        self._monitoring_active = False
        self._monitoring_thread = None
    
    def start_monitoring(self):
        """Start background monitoring collection."""
        if self._monitoring_active:
            return
        
        self._monitoring_active = True
        self._monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._monitoring_thread.start()
        logger.info("Started background monitoring collection")
    
    def stop_monitoring(self):
        """Stop background monitoring collection."""
        self._monitoring_active = False
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=5)
        logger.info("Stopped background monitoring collection")
    
    def _monitoring_loop(self):
        """Background monitoring collection loop."""
        while self._monitoring_active:
            try:
                # Collect all metrics
                asyncio.run(self._collect_all_metrics())
                
                # Check for alerts
                self._check_alert_conditions()
                
                # Sleep for 1 minute
                time.sleep(60)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(60)  # Continue monitoring even if there's an error
    
    async def _collect_all_metrics(self):
        """Collect all types of metrics."""
        timestamp = datetime.now(timezone.utc)
        
        # Collect metrics concurrently
        with ThreadPoolExecutor(max_workers=4) as executor:
            app_future = executor.submit(self._collect_application_metrics, timestamp)
            business_future = executor.submit(self._collect_business_metrics, timestamp)
            infra_future = executor.submit(self._collect_infrastructure_metrics, timestamp)
            compliance_future = executor.submit(self._collect_compliance_metrics, timestamp)
            
            # Wait for all collections to complete
            app_metrics = app_future.result()
            business_metrics = business_future.result()
            infra_metrics = infra_future.result()
            compliance_metrics = compliance_future.result()
        
        # Store metrics
        self.metrics_history['application'].append(app_metrics)
        self.metrics_history['business'].append(business_metrics)
        self.metrics_history['infrastructure'].append(infra_metrics)
        self.metrics_history['compliance'].append(compliance_metrics)
        
        logger.debug("Collected all metrics", 
                    app_rps=app_metrics.requests_per_second,
                    cpu_usage=infra_metrics.cpu_usage_percent,
                    memory_usage=infra_metrics.memory_usage_percent)
    
    def _collect_application_metrics(self, timestamp: datetime) -> ApplicationMetrics:
        """Collect application performance metrics."""
        try:
            # Calculate requests per second
            recent_requests = [t for t in self.request_times if t > time.time() - 60]
            rps = len(recent_requests)
            
            # Calculate average response time
            recent_times = [t for t in self.timers.get('request_duration', []) if t > 0]
            avg_response_time = sum(recent_times[-100:]) / len(recent_times[-100:]) if recent_times else 0
            
            # Calculate error rate
            recent_errors = [e for e in self.request_errors if e > time.time() - 300]  # 5 minutes
            total_recent_requests = len([t for t in self.request_times if t > time.time() - 300])
            error_rate = (len(recent_errors) / max(total_recent_requests, 1)) * 100
            
            # Authorization decisions per minute
            recent_decisions = [d for d in self.authorization_decisions if d > time.time() - 60]
            decisions_per_minute = len(recent_decisions)
            
            # Calculate approval/denial rates
            approval_count = self.counters.get('approvals_today', 0)
            denial_count = self.counters.get('denials_today', 0)
            total_decisions = approval_count + denial_count
            
            approval_rate = (approval_count / max(total_decisions, 1)) * 100
            denial_rate = (denial_count / max(total_decisions, 1)) * 100
            
            # Get cache hit rate (placeholder - would integrate with actual cache)
            cache_hit_rate = 85.0  # Would get from cache service
            
            # System resource usage
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_usage_mb = memory_info.rss / 1024 / 1024
            cpu_usage = process.cpu_percent()
            
            return ApplicationMetrics(
                timestamp=timestamp,
                requests_per_second=rps,
                avg_response_time=avg_response_time,
                error_rate=error_rate,
                active_sessions=len(self.active_sessions),
                authorization_decisions_per_minute=decisions_per_minute,
                approval_rate=approval_rate,
                denial_rate=denial_rate,
                pending_requests=self.counters.get('pending_requests', 0),
                cache_hit_rate=cache_hit_rate,
                memory_usage_mb=memory_usage_mb,
                cpu_usage_percent=cpu_usage
            )
            
        except Exception as e:
            logger.error(f"Failed to collect application metrics: {e}")
            return ApplicationMetrics(
                timestamp=timestamp,
                requests_per_second=0,
                avg_response_time=0,
                error_rate=0,
                active_sessions=0,
                authorization_decisions_per_minute=0,
                approval_rate=0,
                denial_rate=0,
                pending_requests=0,
                cache_hit_rate=0,
                memory_usage_mb=0,
                cpu_usage_percent=0
            )
    
    def _collect_business_metrics(self, timestamp: datetime) -> BusinessMetrics:
        """Collect business KPI metrics."""
        try:
            # Daily totals
            total_requests = self.counters.get('requests_today', 0)
            total_approvals = self.counters.get('approvals_today', 0)
            total_denials = self.counters.get('denials_today', 0)
            
            # Average processing time
            processing_times = self.timers.get('processing_time', [])
            avg_processing_time = sum(processing_times[-100:]) / len(processing_times[-100:]) if processing_times else 0
            avg_processing_minutes = avg_processing_time / 60
            
            # SLA compliance (requests processed within 2 minutes)
            sla_compliant = self.counters.get('sla_compliant_requests', 0)
            sla_compliance_rate = (sla_compliant / max(total_requests, 1)) * 100
            
            # Provider satisfaction (placeholder - would come from surveys)
            provider_satisfaction = 4.2  # Out of 5
            
            # Policy hit rate
            policy_hits = self.counters.get('policy_hits', 0)
            policy_checks = self.counters.get('policy_checks', 0)
            policy_hit_rate = (policy_hits / max(policy_checks, 1)) * 100
            
            # Medical necessity pass rate
            necessity_passes = self.counters.get('medical_necessity_passes', 0)
            necessity_checks = self.counters.get('medical_necessity_checks', 0)
            necessity_pass_rate = (necessity_passes / max(necessity_checks, 1)) * 100
            
            # Audit compliance score (placeholder)
            audit_compliance = 98.5
            
            return BusinessMetrics(
                timestamp=timestamp,
                total_requests_today=total_requests,
                total_approvals_today=total_approvals,
                total_denials_today=total_denials,
                avg_processing_time_minutes=avg_processing_minutes,
                sla_compliance_rate=sla_compliance_rate,
                provider_satisfaction_score=provider_satisfaction,
                policy_hit_rate=policy_hit_rate,
                medical_necessity_pass_rate=necessity_pass_rate,
                audit_compliance_score=audit_compliance
            )
            
        except Exception as e:
            logger.error(f"Failed to collect business metrics: {e}")
            return BusinessMetrics(
                timestamp=timestamp,
                total_requests_today=0,
                total_approvals_today=0,
                total_denials_today=0,
                avg_processing_time_minutes=0,
                sla_compliance_rate=0,
                provider_satisfaction_score=0,
                policy_hit_rate=0,
                medical_necessity_pass_rate=0,
                audit_compliance_score=0
            )
    
    def _collect_infrastructure_metrics(self, timestamp: datetime) -> InfrastructureMetrics:
        """Collect infrastructure performance metrics."""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            
            # Network I/O
            net_io = psutil.net_io_counters()
            # Calculate network throughput (simplified)
            network_mbps = 0.0  # Would need historical data for proper calculation
            
            # Disk I/O
            disk_io = psutil.disk_io_counters()
            disk_mbps = 0.0  # Would need historical data for proper calculation
            
            # Load average (Unix-like systems)
            try:
                load_avg = psutil.getloadavg()
            except AttributeError:
                load_avg = (0.0, 0.0, 0.0)  # Windows doesn't have load average
            
            # Process and thread counts
            process_count = len(psutil.pids())
            
            # Current process thread count
            current_process = psutil.Process()
            thread_count = current_process.num_threads()
            
            # File descriptors (Unix-like systems)
            try:
                fd_count = current_process.num_fds()
            except AttributeError:
                fd_count = 0  # Windows doesn't have file descriptors
            
            return InfrastructureMetrics(
                timestamp=timestamp,
                cpu_usage_percent=cpu_percent,
                memory_usage_percent=memory_percent,
                disk_usage_percent=disk_percent,
                network_io_mbps=network_mbps,
                disk_io_mbps=disk_mbps,
                load_average=load_avg,
                process_count=process_count,
                thread_count=thread_count,
                file_descriptors_used=fd_count
            )
            
        except Exception as e:
            logger.error(f"Failed to collect infrastructure metrics: {e}")
            return InfrastructureMetrics(
                timestamp=timestamp,
                cpu_usage_percent=0,
                memory_usage_percent=0,
                disk_usage_percent=0,
                network_io_mbps=0,
                disk_io_mbps=0,
                load_average=(0.0, 0.0, 0.0),
                process_count=0,
                thread_count=0,
                file_descriptors_used=0
            )
    
    def _collect_compliance_metrics(self, timestamp: datetime) -> ComplianceMetrics:
        """Collect HIPAA and regulatory compliance metrics."""
        try:
            # PHI access events (from audit logs)
            phi_access = self.counters.get('phi_access_events_today', 0)
            
            # Unauthorized access attempts
            unauthorized_attempts = self.counters.get('unauthorized_access_attempts', 0)
            
            # Audit log completeness (placeholder)
            audit_completeness = 99.8
            
            # Encryption compliance rate (placeholder)
            encryption_compliance = 100.0
            
            # Data retention compliance (placeholder)
            retention_compliance = 98.5
            
            # Security incidents
            security_incidents = self.counters.get('security_incidents_today', 0)
            
            # Policy violations
            policy_violations = self.counters.get('policy_violations_today', 0)
            
            # Backup success rate (placeholder)
            backup_success = 99.5
            
            return ComplianceMetrics(
                timestamp=timestamp,
                phi_access_events=phi_access,
                unauthorized_access_attempts=unauthorized_attempts,
                audit_log_completeness=audit_completeness,
                encryption_compliance_rate=encryption_compliance,
                data_retention_compliance=retention_compliance,
                security_incidents=security_incidents,
                policy_violations=policy_violations,
                backup_success_rate=backup_success
            )
            
        except Exception as e:
            logger.error(f"Failed to collect compliance metrics: {e}")
            return ComplianceMetrics(
                timestamp=timestamp,
                phi_access_events=0,
                unauthorized_access_attempts=0,
                audit_log_completeness=0,
                encryption_compliance_rate=0,
                data_retention_compliance=0,
                security_incidents=0,
                policy_violations=0,
                backup_success_rate=0
            )
    
    def record_request(self, duration_ms: float, error: bool = False):
        """Record a request for metrics tracking."""
        current_time = time.time()
        self.request_times.append(current_time)
        self.timers['request_duration'].append(duration_ms)
        
        if error:
            self.request_errors.append(current_time)
        
        # Check SLA compliance (2 minutes = 120,000 ms)
        if duration_ms <= 120000:
            self.counters['sla_compliant_requests'] += 1
        
        self.counters['requests_today'] += 1
    
    def record_authorization_decision(self, decision: str, processing_time_seconds: float):
        """Record an authorization decision for metrics tracking."""
        current_time = time.time()
        self.authorization_decisions.append(current_time)
        self.timers['processing_time'].append(processing_time_seconds)
        
        if decision.upper() == 'APPROVED':
            self.counters['approvals_today'] += 1
        elif decision.upper() == 'DENIED':
            self.counters['denials_today'] += 1
    
    def record_session(self, session_id: str, active: bool = True):
        """Record session activity."""
        if active:
            self.active_sessions.add(session_id)
        else:
            self.active_sessions.discard(session_id)
    
    def record_policy_check(self, hit: bool = True):
        """Record policy cache hit/miss."""
        self.counters['policy_checks'] += 1
        if hit:
            self.counters['policy_hits'] += 1
    
    def record_medical_necessity_check(self, passed: bool = True):
        """Record medical necessity evaluation result."""
        self.counters['medical_necessity_checks'] += 1
        if passed:
            self.counters['medical_necessity_passes'] += 1
    
    def record_phi_access(self, user_id: str, resource: str):
        """Record PHI access for compliance tracking."""
        self.counters['phi_access_events_today'] += 1
        audit_logger.log_security_event('phi_access', user_id=user_id, 
                                       details={'resource': resource})
    
    def record_security_incident(self, incident_type: str, details: Dict[str, Any]):
        """Record security incident."""
        self.counters['security_incidents_today'] += 1
        audit_logger.log_security_event(incident_type, details=details)
    
    def _check_alert_conditions(self):
        """Check current metrics against thresholds and generate alerts."""
        if not self.metrics_history['application'] or not self.metrics_history['infrastructure']:
            return
        
        current_app = self.metrics_history['application'][-1]
        current_infra = self.metrics_history['infrastructure'][-1]
        current_business = self.metrics_history['business'][-1]
        
        alerts_to_check = [
            ('response_time', current_app.avg_response_time, self.thresholds['response_time_ms'], 
             'HIGH', 'Average response time exceeded threshold'),
            ('error_rate', current_app.error_rate, self.thresholds['error_rate_percent'], 
             'HIGH', 'Error rate exceeded threshold'),
            ('cpu_usage', current_infra.cpu_usage_percent, self.thresholds['cpu_usage_percent'], 
             'MEDIUM', 'CPU usage exceeded threshold'),
            ('memory_usage', current_infra.memory_usage_percent, self.thresholds['memory_usage_percent'], 
             'HIGH', 'Memory usage exceeded threshold'),
            ('disk_usage', current_infra.disk_usage_percent, self.thresholds['disk_usage_percent'], 
             'CRITICAL', 'Disk usage exceeded threshold'),
            ('sla_compliance', current_business.sla_compliance_rate, self.thresholds['sla_compliance_rate'], 
             'HIGH', 'SLA compliance below threshold'),
            ('cache_hit_rate', current_app.cache_hit_rate, self.thresholds['cache_hit_rate'], 
             'MEDIUM', 'Cache hit rate below threshold')
        ]
        
        for alert_type, current_value, threshold, severity, message in alerts_to_check:
            alert_id = f"{alert_type}_{int(time.time())}"
            
            # Check if threshold is exceeded
            threshold_exceeded = (
                (alert_type in ['sla_compliance', 'cache_hit_rate'] and current_value < threshold) or
                (alert_type not in ['sla_compliance', 'cache_hit_rate'] and current_value > threshold)
            )
            
            if threshold_exceeded and alert_type not in self.active_alerts:
                # Create new alert
                alert = SystemAlert(
                    alert_id=alert_id,
                    alert_type=alert_type,
                    severity=severity,
                    title=f"{alert_type.replace('_', ' ').title()} Alert",
                    message=f"{message}: {current_value:.2f} (threshold: {threshold})",
                    metric_name=alert_type,
                    current_value=current_value,
                    threshold_value=threshold,
                    timestamp=datetime.now(timezone.utc),
                    resolved=False,
                    resolution_time=None,
                    suggested_actions=self._get_suggested_actions(alert_type)
                )
                
                self.active_alerts[alert_type] = alert
                self.alert_history.append(alert)
                
                logger.warning(f"Alert triggered: {alert.title}", 
                             alert_type=alert_type,
                             current_value=current_value,
                             threshold=threshold,
                             severity=severity)
            
            elif not threshold_exceeded and alert_type in self.active_alerts:
                # Resolve existing alert
                alert = self.active_alerts[alert_type]
                alert.resolved = True
                alert.resolution_time = datetime.now(timezone.utc)
                
                del self.active_alerts[alert_type]
                
                logger.info(f"Alert resolved: {alert.title}", 
                          alert_type=alert_type,
                          resolution_time=alert.resolution_time)
    
    def _get_suggested_actions(self, alert_type: str) -> List[str]:
        """Get suggested actions for different alert types."""
        actions = {
            'response_time': [
                'Check database query performance',
                'Review application bottlenecks',
                'Consider scaling resources'
            ],
            'error_rate': [
                'Check application logs for errors',
                'Review recent deployments',
                'Validate external service connectivity'
            ],
            'cpu_usage': [
                'Scale up CPU resources',
                'Optimize CPU-intensive operations',
                'Check for runaway processes'
            ],
            'memory_usage': [
                'Scale up memory resources',
                'Check for memory leaks',
                'Optimize memory-intensive operations'
            ],
            'disk_usage': [
                'Clean up old log files',
                'Archive historical data',
                'Scale up disk storage'
            ],
            'sla_compliance': [
                'Optimize request processing pipeline',
                'Scale application resources',
                'Review policy validation performance'
            ],
            'cache_hit_rate': [
                'Review cache configuration',
                'Increase cache TTL',
                'Implement cache warming'
            ]
        }
        
        return actions.get(alert_type, ['Contact system administrator'])
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current metrics snapshot."""
        return {
            'application': asdict(self.metrics_history['application'][-1]) if self.metrics_history['application'] else None,
            'business': asdict(self.metrics_history['business'][-1]) if self.metrics_history['business'] else None,
            'infrastructure': asdict(self.metrics_history['infrastructure'][-1]) if self.metrics_history['infrastructure'] else None,
            'compliance': asdict(self.metrics_history['compliance'][-1]) if self.metrics_history['compliance'] else None,
            'active_alerts': [asdict(alert) for alert in self.active_alerts.values()],
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def get_metrics_history(self, hours: int = 24) -> Dict[str, List[Dict[str, Any]]]:
        """Get historical metrics for specified time period."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        history = {}
        for metric_type, metrics_list in self.metrics_history.items():
            history[metric_type] = [
                asdict(metric) for metric in metrics_list 
                if metric.timestamp > cutoff_time
            ]
        
        return history
    
    def get_alert_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get alert history for specified time period."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        return [
            asdict(alert) for alert in self.alert_history 
            if alert.timestamp > cutoff_time
        ]
    
    def reset_daily_counters(self):
        """Reset daily counters (should be called at midnight)."""
        daily_counters = [
            'requests_today', 'approvals_today', 'denials_today',
            'sla_compliant_requests', 'phi_access_events_today',
            'security_incidents_today', 'policy_violations_today'
        ]
        
        for counter in daily_counters:
            self.counters[counter] = 0
        
        logger.info("Reset daily counters")


# Global metrics collector instance
metrics_collector = MetricsCollector()
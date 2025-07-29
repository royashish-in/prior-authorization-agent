"""
Integration tests for the complete monitoring system.

This module tests the integration between monitoring components,
security monitoring, and dashboard services.
"""

import pytest
import asyncio
from datetime import datetime

from src.services.monitoring import MetricsCollector
from src.services.security_monitoring import SecurityMonitoringService, SecurityEventType, IncidentSeverity
from src.services.dashboard_metrics import DashboardMetricsService


class TestMonitoringIntegration:
    """Integration tests for monitoring system."""
    
    @pytest.mark.asyncio
    async def test_complete_monitoring_workflow(self):
        """Test complete monitoring workflow from events to dashboards."""
        # Initialize services
        metrics_collector = MetricsCollector()
        security_service = SecurityMonitoringService()
        dashboard_service = DashboardMetricsService()
        
        # Simulate application activity
        metrics_collector.record_request(1200.0, error=False)
        metrics_collector.record_request(1800.0, error=False)
        metrics_collector.record_authorization_decision('APPROVED', 45.0)
        metrics_collector.record_authorization_decision('DENIED', 30.0)
        
        # Simulate security events
        event_id1 = security_service.record_security_event(
            SecurityEventType.FAILED_LOGIN,
            source_ip="192.168.1.100",
            user_id="test_user"
        )
        
        event_id2 = security_service.record_security_event(
            SecurityEventType.UNAUTHORIZED_ACCESS,
            source_ip="192.168.1.101",
            resource="/admin"
        )
        
        # Create security incident
        incident_id = security_service.create_incident(
            "Test security incident",
            "Multiple security events detected",
            IncidentSeverity.HIGH,
            [event_id1, event_id2]
        )
        
        # Verify metrics collection
        current_metrics = metrics_collector.get_current_metrics()
        assert 'timestamp' in current_metrics
        
        # Verify security events
        security_events = security_service.get_security_events(hours=1)
        assert len(security_events) >= 2
        
        # Verify incidents
        incidents = security_service.get_incidents()
        assert len(incidents) >= 1
        assert incidents[0].incident_id == incident_id
        
        # Verify dashboard functionality
        dashboards = dashboard_service.get_available_dashboards()
        assert len(dashboards) >= 4
        
        # Test dashboard data retrieval
        dashboard_data = await dashboard_service.get_dashboard_data('system_health')
        assert 'dashboard' in dashboard_data
        assert 'widget_data' in dashboard_data
        
        # Verify threat intelligence report
        threat_report = security_service.get_threat_intelligence_report()
        assert 'summary' in threat_report
        assert threat_report['summary']['total_events_24h'] >= 2
        
        print("Complete monitoring workflow test passed!")
    
    def test_monitoring_system_initialization(self):
        """Test that all monitoring components initialize correctly."""
        # Test metrics collector
        metrics_collector = MetricsCollector()
        assert hasattr(metrics_collector, 'counters')
        assert hasattr(metrics_collector, 'timers')
        assert hasattr(metrics_collector, 'thresholds')
        
        # Test security monitoring
        security_service = SecurityMonitoringService()
        assert hasattr(security_service, 'security_events')
        assert hasattr(security_service, 'incidents')
        assert hasattr(security_service, 'anomaly_patterns')
        assert len(security_service.anomaly_patterns) > 0
        
        # Test dashboard service
        dashboard_service = DashboardMetricsService()
        assert hasattr(dashboard_service, 'dashboards')
        assert len(dashboard_service.dashboards) > 0
        
        print("All monitoring components initialized successfully!")
    
    def test_cross_component_data_flow(self):
        """Test data flow between monitoring components."""
        metrics_collector = MetricsCollector()
        security_service = SecurityMonitoringService()
        
        # Record metrics that should trigger security monitoring
        for i in range(10):
            metrics_collector.record_request(3000.0, error=True)  # Slow requests with errors
        
        # Record security events that should affect metrics
        for i in range(5):
            security_service.record_security_event(
                SecurityEventType.FAILED_LOGIN,
                source_ip="192.168.1.100",
                user_id=f"user_{i}"
            )
        
        # Verify metrics were recorded
        current_metrics = metrics_collector.get_current_metrics()
        assert current_metrics is not None
        
        # Verify security events were recorded
        security_events = security_service.get_security_events(hours=1)
        assert len(security_events) >= 5
        
        # Verify failed login tracking
        assert "192.168.1.100" in security_service.failed_login_attempts
        assert len(security_service.failed_login_attempts["192.168.1.100"]) >= 5
        
        print("Cross-component data flow test passed!")


if __name__ == "__main__":
    pytest.main([__file__])
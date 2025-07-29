"""
Tests for the comprehensive monitoring system.

This module tests application metrics collection, infrastructure monitoring,
dashboard functionality, and alert validation.
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock
import psutil

from src.services.monitoring import (
    MetricsCollector, ApplicationMetrics, BusinessMetrics, 
    InfrastructureMetrics, ComplianceMetrics, SystemAlert,
    metrics_collector
)
from src.services.dashboard_metrics import (
    DashboardMetricsService, DashboardWidget, DashboardLayout,
    dashboard_metrics_service
)


class TestMetricsCollector:
    """Test cases for MetricsCollector class."""
    
    @pytest.fixture
    def collector(self):
        """Create a fresh metrics collector for testing."""
        collector = MetricsCollector()
        collector.counters.clear()
        collector.timers.clear()
        collector.request_times.clear()
        collector.request_errors.clear()
        collector.active_sessions.clear()
        collector.authorization_decisions.clear()
        collector.active_alerts.clear()
        return collector
    
    def test_record_request(self, collector):
        """Test request recording functionality."""
        # Record successful request
        collector.record_request(1500.0, error=False)
        
        assert len(collector.request_times) == 1
        assert len(collector.timers['request_duration']) == 1
        assert collector.timers['request_duration'][0] == 1500.0
        assert collector.counters['requests_today'] == 1
        assert collector.counters['sla_compliant_requests'] == 1
        assert len(collector.request_errors) == 0
    
    def test_record_request_with_error(self, collector):
        """Test request recording with error."""
        collector.record_request(3000.0, error=True)
        
        assert len(collector.request_errors) == 1
        assert collector.counters['requests_today'] == 1
        assert collector.counters['sla_compliant_requests'] == 0  # Over 2 minutes
    
    def test_record_authorization_decision(self, collector):
        """Test authorization decision recording."""
        collector.record_authorization_decision('APPROVED', 45.0)
        
        assert len(collector.authorization_decisions) == 1
        assert collector.counters['approvals_today'] == 1
        assert collector.counters['denials_today'] == 0
        assert len(collector.timers['processing_time']) == 1
        assert collector.timers['processing_time'][0] == 45.0
    
    def test_record_session_management(self, collector):
        """Test session management."""
        session_id = "session_123"
        
        # Add active session
        collector.record_session(session_id, active=True)
        assert session_id in collector.active_sessions
        
        # Remove session
        collector.record_session(session_id, active=False)
        assert session_id not in collector.active_sessions
    
    def test_record_policy_check(self, collector):
        """Test policy check recording."""
        collector.record_policy_check(hit=True)
        collector.record_policy_check(hit=False)
        
        assert collector.counters['policy_checks'] == 2
        assert collector.counters['policy_hits'] == 1
    
    def test_record_medical_necessity_check(self, collector):
        """Test medical necessity check recording."""
        collector.record_medical_necessity_check(passed=True)
        collector.record_medical_necessity_check(passed=False)
        
        assert collector.counters['medical_necessity_checks'] == 2
        assert collector.counters['medical_necessity_passes'] == 1
    
    @patch('src.services.monitoring.audit_logger')
    def test_record_phi_access(self, mock_audit_logger, collector):
        """Test PHI access recording."""
        collector.record_phi_access("user_123", "patient_data")
        
        assert collector.counters['phi_access_events_today'] == 1
        mock_audit_logger.log_security_event.assert_called_once()
    
    @patch('src.services.monitoring.audit_logger')
    def test_record_security_incident(self, mock_audit_logger, collector):
        """Test security incident recording."""
        collector.record_security_incident("unauthorized_access", {"ip": "192.168.1.1"})
        
        assert collector.counters['security_incidents_today'] == 1
        mock_audit_logger.log_security_event.assert_called_once()
    
    @patch('psutil.Process')
    def test_collect_application_metrics(self, mock_process, collector):
        """Test application metrics collection."""
        # Mock process information
        mock_process_instance = Mock()
        mock_process_instance.memory_info.return_value = Mock(rss=100 * 1024 * 1024)  # 100MB
        mock_process_instance.cpu_percent.return_value = 25.0
        mock_process.return_value = mock_process_instance
        
        # Add some test data
        current_time = time.time()
        collector.request_times.extend([current_time - 30, current_time - 15])
        collector.timers['request_duration'] = [1000.0, 1500.0, 800.0]
        collector.counters['approvals_today'] = 10
        collector.counters['denials_today'] = 2
        
        timestamp = datetime.now(timezone.utc)
        metrics = collector._collect_application_metrics(timestamp)
        
        assert isinstance(metrics, ApplicationMetrics)
        assert metrics.timestamp == timestamp
        assert metrics.requests_per_second == 2  # 2 requests in last 60 seconds
        assert metrics.approval_rate > 0
        assert metrics.memory_usage_mb == 100.0
        assert metrics.cpu_usage_percent == 25.0
    
    def test_collect_business_metrics(self, collector):
        """Test business metrics collection."""
        # Add test data
        collector.counters['requests_today'] = 100
        collector.counters['approvals_today'] = 80
        collector.counters['denials_today'] = 15
        collector.counters['sla_compliant_requests'] = 95
        collector.timers['processing_time'] = [30.0, 45.0, 60.0]
        
        timestamp = datetime.now(timezone.utc)
        metrics = collector._collect_business_metrics(timestamp)
        
        assert isinstance(metrics, BusinessMetrics)
        assert metrics.total_requests_today == 100
        assert metrics.total_approvals_today == 80
        assert metrics.total_denials_today == 15
        assert metrics.sla_compliance_rate == 95.0
        assert metrics.avg_processing_time_minutes > 0
    
    @patch('psutil.cpu_percent')
    @patch('psutil.virtual_memory')
    @patch('psutil.disk_usage')
    @patch('psutil.net_io_counters')
    @patch('psutil.disk_io_counters')
    @patch('psutil.getloadavg')
    @patch('psutil.pids')
    @patch('psutil.Process')
    def test_collect_infrastructure_metrics(self, mock_process, mock_pids, mock_loadavg,
                                          mock_disk_io, mock_net_io, mock_disk_usage,
                                          mock_memory, mock_cpu, collector):
        """Test infrastructure metrics collection."""
        # Mock system information
        mock_cpu.return_value = 45.0
        mock_memory.return_value = Mock(percent=60.0)
        mock_disk_usage.return_value = Mock(used=50*1024**3, total=100*1024**3)
        mock_net_io.return_value = Mock()
        mock_disk_io.return_value = Mock()
        mock_loadavg.return_value = (1.5, 1.2, 1.0)
        mock_pids.return_value = list(range(100))
        
        mock_process_instance = Mock()
        mock_process_instance.num_threads.return_value = 10
        mock_process_instance.num_fds.return_value = 50
        mock_process.return_value = mock_process_instance
        
        timestamp = datetime.now(timezone.utc)
        metrics = collector._collect_infrastructure_metrics(timestamp)
        
        assert isinstance(metrics, InfrastructureMetrics)
        assert metrics.cpu_usage_percent == 45.0
        assert metrics.memory_usage_percent == 60.0
        assert metrics.disk_usage_percent == 50.0
        assert metrics.load_average == (1.5, 1.2, 1.0)
        assert metrics.process_count == 100
        assert metrics.thread_count == 10
        assert metrics.file_descriptors_used == 50
    
    def test_collect_compliance_metrics(self, collector):
        """Test compliance metrics collection."""
        # Add test data
        collector.counters['phi_access_events_today'] = 25
        collector.counters['unauthorized_access_attempts'] = 2
        collector.counters['security_incidents_today'] = 1
        collector.counters['policy_violations_today'] = 0
        
        timestamp = datetime.now(timezone.utc)
        metrics = collector._collect_compliance_metrics(timestamp)
        
        assert isinstance(metrics, ComplianceMetrics)
        assert metrics.phi_access_events == 25
        assert metrics.unauthorized_access_attempts == 2
        assert metrics.security_incidents == 1
        assert metrics.policy_violations == 0
        assert metrics.audit_log_completeness > 0
        assert metrics.encryption_compliance_rate > 0
    
    def test_alert_generation(self, collector):
        """Test alert generation based on thresholds."""
        # Create metrics that exceed thresholds
        timestamp = datetime.now(timezone.utc)
        
        # Mock high error rate
        collector.request_times.extend([time.time()] * 100)
        collector.request_errors.extend([time.time()] * 10)  # 10% error rate
        
        app_metrics = collector._collect_application_metrics(timestamp)
        collector.metrics_history['application'].append(app_metrics)
        
        # Mock high CPU usage
        with patch('psutil.cpu_percent', return_value=85.0):
            infra_metrics = collector._collect_infrastructure_metrics(timestamp)
            collector.metrics_history['infrastructure'].append(infra_metrics)
        
        # Check for alerts
        collector._check_alert_conditions()
        
        # Should have alerts for error rate and CPU usage
        assert len(collector.active_alerts) >= 1
        
        # Check alert properties
        for alert in collector.active_alerts.values():
            assert isinstance(alert, SystemAlert)
            assert alert.severity in ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
            assert alert.timestamp is not None
            assert len(alert.suggested_actions) > 0
    
    def test_reset_daily_counters(self, collector):
        """Test daily counter reset functionality."""
        # Set some counter values
        collector.counters['requests_today'] = 100
        collector.counters['approvals_today'] = 80
        collector.counters['phi_access_events_today'] = 25
        
        collector.reset_daily_counters()
        
        assert collector.counters['requests_today'] == 0
        assert collector.counters['approvals_today'] == 0
        assert collector.counters['phi_access_events_today'] == 0
    
    def test_get_current_metrics(self, collector):
        """Test current metrics retrieval."""
        # Add some test metrics
        timestamp = datetime.now(timezone.utc)
        app_metrics = ApplicationMetrics(
            timestamp=timestamp,
            requests_per_second=10.0,
            avg_response_time=1500.0,
            error_rate=2.0,
            active_sessions=5,
            authorization_decisions_per_minute=8.0,
            approval_rate=85.0,
            denial_rate=15.0,
            pending_requests=3,
            cache_hit_rate=90.0,
            memory_usage_mb=150.0,
            cpu_usage_percent=35.0
        )
        collector.metrics_history['application'].append(app_metrics)
        
        current = collector.get_current_metrics()
        
        assert 'application' in current
        assert 'timestamp' in current
        assert current['application']['requests_per_second'] == 10.0
    
    def test_get_metrics_history(self, collector):
        """Test metrics history retrieval."""
        # Add test metrics with different timestamps
        now = datetime.now(timezone.utc)
        old_timestamp = now - timedelta(hours=25)  # Outside 24-hour window
        recent_timestamp = now - timedelta(hours=1)
        
        old_metrics = ApplicationMetrics(
            timestamp=old_timestamp,
            requests_per_second=5.0,
            avg_response_time=2000.0,
            error_rate=1.0,
            active_sessions=2,
            authorization_decisions_per_minute=4.0,
            approval_rate=80.0,
            denial_rate=20.0,
            pending_requests=1,
            cache_hit_rate=85.0,
            memory_usage_mb=100.0,
            cpu_usage_percent=25.0
        )
        
        recent_metrics = ApplicationMetrics(
            timestamp=recent_timestamp,
            requests_per_second=10.0,
            avg_response_time=1500.0,
            error_rate=2.0,
            active_sessions=5,
            authorization_decisions_per_minute=8.0,
            approval_rate=85.0,
            denial_rate=15.0,
            pending_requests=3,
            cache_hit_rate=90.0,
            memory_usage_mb=150.0,
            cpu_usage_percent=35.0
        )
        
        collector.metrics_history['application'].extend([old_metrics, recent_metrics])
        
        # Get 24-hour history
        history = collector.get_metrics_history(hours=24)
        
        assert 'application' in history
        assert len(history['application']) == 1  # Only recent metrics
        assert history['application'][0]['requests_per_second'] == 10.0


class TestDashboardMetricsService:
    """Test cases for DashboardMetricsService class."""
    
    @pytest.fixture
    def dashboard_service(self):
        """Create a fresh dashboard service for testing."""
        return DashboardMetricsService()
    
    def test_initialize_default_dashboards(self, dashboard_service):
        """Test default dashboard initialization."""
        assert 'system_health' in dashboard_service.dashboards
        assert 'business_kpi' in dashboard_service.dashboards
        assert 'compliance' in dashboard_service.dashboards
        assert 'database_performance' in dashboard_service.dashboards
        
        # Check system health dashboard
        system_health = dashboard_service.dashboards['system_health']
        assert system_health.title == "System Health Dashboard"
        assert len(system_health.widgets) > 0
        assert 'admin' in system_health.access_roles
    
    def test_get_available_dashboards(self, dashboard_service):
        """Test available dashboards listing."""
        dashboards = dashboard_service.get_available_dashboards()
        
        assert len(dashboards) >= 4  # At least the default dashboards
        
        for dashboard in dashboards:
            assert 'dashboard_id' in dashboard
            assert 'title' in dashboard
            assert 'description' in dashboard
            assert 'access_roles' in dashboard
    
    @pytest.mark.asyncio
    async def test_get_dashboard_data(self, dashboard_service):
        """Test dashboard data retrieval."""
        # Mock metrics collector
        with patch.object(metrics_collector, 'get_current_metrics') as mock_metrics:
            mock_metrics.return_value = {
                'application': {
                    'requests_per_second': 10.0,
                    'avg_response_time': 1500.0,
                    'error_rate': 2.0,
                    'active_sessions': 5
                },
                'active_alerts': []
            }
            
            dashboard_data = await dashboard_service.get_dashboard_data('system_health')
            
            assert 'dashboard' in dashboard_data
            assert 'widget_data' in dashboard_data
            assert 'generated_at' in dashboard_data
            
            # Check dashboard structure
            dashboard = dashboard_data['dashboard']
            assert dashboard['dashboard_id'] == 'system_health'
            assert dashboard['title'] == "System Health Dashboard"
            
            # Check widget data
            widget_data = dashboard_data['widget_data']
            assert len(widget_data) > 0
    
    @pytest.mark.asyncio
    async def test_get_widget_data_application_metrics(self, dashboard_service):
        """Test application metrics widget data."""
        widget = DashboardWidget(
            widget_id="test_kpi",
            title="Test KPI",
            widget_type="kpi_card",
            data_source="application_metrics",
            refresh_interval=30,
            config={
                "metrics": ["requests_per_second", "avg_response_time"],
                "thresholds": {"avg_response_time": 2000}
            }
        )
        
        with patch.object(metrics_collector, 'get_current_metrics') as mock_metrics:
            mock_metrics.return_value = {
                'application': {
                    'requests_per_second': 10.0,
                    'avg_response_time': 1500.0
                }
            }
            
            data = await dashboard_service._get_widget_data(widget)
            
            assert 'metrics' in data
            assert 'requests_per_second' in data['metrics']
            assert 'avg_response_time' in data['metrics']
            assert data['metrics']['avg_response_time']['value'] == 1500.0
            assert data['metrics']['avg_response_time']['threshold'] == 2000
    
    @pytest.mark.asyncio
    async def test_get_widget_data_chart(self, dashboard_service):
        """Test chart widget data."""
        widget = DashboardWidget(
            widget_id="test_chart",
            title="Test Chart",
            widget_type="chart",
            data_source="application_metrics",
            refresh_interval=60,
            config={
                "chart_type": "line",
                "metric": "requests_per_second",
                "time_range": "1h",
                "y_axis_label": "Requests/sec"
            }
        )
        
        # Mock historical data
        history_data = {
            'application': [
                {
                    'timestamp': '2025-01-24T10:00:00Z',
                    'requests_per_second': 8.0
                },
                {
                    'timestamp': '2025-01-24T10:01:00Z',
                    'requests_per_second': 10.0
                }
            ]
        }
        
        with patch.object(metrics_collector, 'get_metrics_history') as mock_history:
            mock_history.return_value = history_data
            
            data = await dashboard_service._get_widget_data(widget)
            
            assert data['chart_type'] == 'line'
            assert data['metric'] == 'requests_per_second'
            assert data['y_axis_label'] == 'Requests/sec'
            assert len(data['data']) == 2
            assert data['data'][0]['value'] == 8.0
    
    @pytest.mark.asyncio
    async def test_get_widget_data_alerts(self, dashboard_service):
        """Test alerts widget data."""
        widget = DashboardWidget(
            widget_id="test_alerts",
            title="Test Alerts",
            widget_type="alert_list",
            data_source="alerts",
            refresh_interval=30,
            config={
                "max_items": 5,
                "severity_filter": ["HIGH", "CRITICAL"]
            }
        )
        
        mock_alerts = [
            {
                'alert_id': 'alert_1',
                'severity': 'HIGH',
                'alert_type': 'response_time',
                'timestamp': '2025-01-24T10:00:00Z'
            },
            {
                'alert_id': 'alert_2',
                'severity': 'MEDIUM',
                'alert_type': 'cpu_usage',
                'timestamp': '2025-01-24T10:01:00Z'
            }
        ]
        
        with patch.object(metrics_collector, 'get_current_metrics') as mock_metrics:
            mock_metrics.return_value = {'active_alerts': mock_alerts}
            
            data = await dashboard_service._get_widget_data(widget)
            
            assert 'alerts' in data
            # Should only include HIGH severity alert due to filter
            assert len(data['alerts']) == 1
            assert data['alerts'][0]['severity'] == 'HIGH'
    
    def test_create_custom_dashboard(self, dashboard_service):
        """Test custom dashboard creation."""
        dashboard_config = {
            "dashboard_id": "custom_test",
            "title": "Custom Test Dashboard",
            "description": "Test dashboard",
            "refresh_interval": 120,
            "access_roles": ["admin", "test_user"],
            "widgets": [
                {
                    "widget_id": "custom_widget",
                    "title": "Custom Widget",
                    "widget_type": "kpi_card",
                    "data_source": "application_metrics",
                    "refresh_interval": 60,
                    "config": {"metrics": ["requests_per_second"]}
                }
            ]
        }
        
        dashboard_id = dashboard_service.create_custom_dashboard(dashboard_config)
        
        assert dashboard_id == "custom_test"
        assert "custom_test" in dashboard_service.dashboards
        
        dashboard = dashboard_service.dashboards["custom_test"]
        assert dashboard.title == "Custom Test Dashboard"
        assert len(dashboard.widgets) == 1
        assert dashboard.widgets[0].widget_id == "custom_widget"
    
    def test_create_duplicate_dashboard_error(self, dashboard_service):
        """Test error when creating duplicate dashboard."""
        dashboard_config = {
            "dashboard_id": "system_health",  # Already exists
            "title": "Duplicate Dashboard"
        }
        
        with pytest.raises(ValueError, match="already exists"):
            dashboard_service.create_custom_dashboard(dashboard_config)
    
    def test_get_nonexistent_dashboard_error(self, dashboard_service):
        """Test error when getting nonexistent dashboard."""
        with pytest.raises(ValueError, match="not found"):
            asyncio.run(dashboard_service.get_dashboard_data('nonexistent'))
    
    def test_metric_status_calculation(self, dashboard_service):
        """Test metric status calculation."""
        # Normal status
        assert dashboard_service._get_metric_status(50.0, 100.0) == "normal"
        
        # Caution status (80% of threshold)
        assert dashboard_service._get_metric_status(85.0, 100.0) == "caution"
        
        # Warning status (above threshold)
        assert dashboard_service._get_metric_status(110.0, 100.0) == "warning"
        
        # No threshold
        assert dashboard_service._get_metric_status(50.0, None) == "normal"
    
    def test_threshold_status_calculation(self, dashboard_service):
        """Test threshold status calculation."""
        # Normal status
        assert dashboard_service._get_threshold_status(50.0, 80.0, 90.0) == "normal"
        
        # Warning status
        assert dashboard_service._get_threshold_status(85.0, 80.0, 90.0) == "warning"
        
        # Critical status
        assert dashboard_service._get_threshold_status(95.0, 80.0, 90.0) == "critical"
    
    def test_time_range_parsing(self, dashboard_service):
        """Test time range string parsing."""
        assert dashboard_service._parse_time_range("1h") == 1
        assert dashboard_service._parse_time_range("24h") == 24
        assert dashboard_service._parse_time_range("2d") == 48
        assert dashboard_service._parse_time_range("30m") == 1  # Minimum 1 hour
        assert dashboard_service._parse_time_range("invalid") == 1  # Default


class TestMonitoringIntegration:
    """Integration tests for monitoring system."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_monitoring_flow(self):
        """Test complete monitoring flow from metrics collection to dashboard."""
        collector = MetricsCollector()
        dashboard_service = DashboardMetricsService()
        
        # Simulate some application activity
        collector.record_request(1200.0, error=False)
        collector.record_request(1800.0, error=False)
        collector.record_request(3000.0, error=True)  # Slow request with error
        
        collector.record_authorization_decision('APPROVED', 45.0)
        collector.record_authorization_decision('DENIED', 30.0)
        
        collector.record_session('session_1', active=True)
        collector.record_session('session_2', active=True)
        
        # Collect metrics
        with patch('psutil.Process'), patch('psutil.cpu_percent'), \
             patch('psutil.virtual_memory'), patch('psutil.disk_usage'):
            
            await collector._collect_all_metrics()
        
        # Get dashboard data
        with patch.object(metrics_collector, 'get_current_metrics') as mock_metrics:
            mock_metrics.return_value = collector.get_current_metrics()
            
            dashboard_data = await dashboard_service.get_dashboard_data('system_health')
            
            assert 'dashboard' in dashboard_data
            assert 'widget_data' in dashboard_data
            
            # Verify some widget data is present
            widget_data = dashboard_data['widget_data']
            assert len(widget_data) > 0
    
    def test_monitoring_thread_lifecycle(self):
        """Test monitoring thread start/stop lifecycle."""
        collector = MetricsCollector()
        
        # Start monitoring
        collector.start_monitoring()
        assert collector._monitoring_active is True
        assert collector._monitoring_thread is not None
        assert collector._monitoring_thread.is_alive()
        
        # Stop monitoring
        collector.stop_monitoring()
        assert collector._monitoring_active is False
        
        # Thread should stop within timeout
        time.sleep(0.1)  # Give thread time to stop
        assert not collector._monitoring_thread.is_alive()


if __name__ == "__main__":
    pytest.main([__file__])
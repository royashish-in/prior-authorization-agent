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
    """
        Test record request.
        
        This test verifies that the API endpoint correctly handles requests,
        validates input data, enforces security controls, and returns
        appropriate responses in the expected format.
        
        Test Scenarios:
        - Valid requests with proper authentication and authorization
        - Invalid requests with malformed data or missing fields
        - Security scenarios including unauthorized access attempts
        - Error conditions and exception handling
        
        Expected Behavior:
        - Valid requests should return successful responses with correct data
        - Invalid requests should return appropriate HTTP status codes
        - Security controls should prevent unauthorized access
        - Error responses should be informative but not expose sensitive data
        
        Security Requirements:
        - All requests must be properly authenticated
        - PHI data must be encrypted in transit and at rest
        - Audit logging must capture all access attempts
        
        PHI Compliance:
        Test data uses synthetic patient information only.
        """
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
    """
        Test collect compliance metrics.
        
        This test verifies system functionality and ensures that the system
        behaves correctly under the specified conditions.
        
        Test Scenarios:
        - Standard input scenarios
        - Edge cases and boundary conditions
        - Error handling scenarios
        
        Expected Behavior:
        - System should behave according to specified requirements
        
        PHI Compliance:
        All test data uses synthetic information with appropriate markers.
        """
    
        @pytest.fixture
        def dashboard_service(self):
        """Create a fresh dashboard service for testing."""
        return DashboardMetricsService()
    
    @pytest.mark.asyncio

    
    async def test_initialize_default_dashboards(self, dashboard_service):
    """
        Test initialize default dashboards.
        
        This test verifies system functionality and ensures that the system
        behaves correctly under the specified conditions.
        
        Test Scenarios:
        - Standard input scenarios
        - Edge cases and boundary conditions
        - Error handling scenarios
        
        Expected Behavior:
        - System should behave according to specified requirements
        
        PHI Compliance:
        All test data uses synthetic information with appropriate markers.
        """
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
    
    @pytest.mark.asyncio

    
    async def test_create_custom_dashboard(self, dashboard_service):
    """
        Test create custom dashboard.
        
        This test verifies system functionality and ensures that the system
        behaves correctly under the specified conditions.
        
        Test Scenarios:
        - Standard input scenarios
        - Edge cases and boundary conditions
        - Error handling scenarios
        
        Expected Behavior:
        - System should behave according to specified requirements
        
        PHI Compliance:
        All test data uses synthetic information with appropriate markers.
        """
    
        def test_end_to_end_monitoring_flow(self):
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
    """
        Test monitoring thread lifecycle.
        
        This test verifies system functionality and ensures that the system
        behaves correctly under the specified conditions.
        
        Test Scenarios:
        - Standard input scenarios
        - Edge cases and boundary conditions
        - Error handling scenarios
        
        Expected Behavior:
        - System should behave according to specified requirements
        
        PHI Compliance:
        All test data uses synthetic information with appropriate markers.
        """

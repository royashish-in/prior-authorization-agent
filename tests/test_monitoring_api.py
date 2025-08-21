"""
Comprehensive tests for Monitoring API endpoints.

This module provides comprehensive testing for all monitoring endpoints
including metrics collection, alerts, dashboards, database performance,
health checks, and security monitoring.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException, status

from src.api.monitoring import router
from src.auth.models import UserRole


@pytest.fixture
def client():
    """Create test client."""
    from src.main import app
    return TestClient(app)


@pytest.fixture
def mock_metrics_collector():
    """Create mock metrics collector."""
    collector = Mock()
    collector.get_current_metrics = Mock(return_value={
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "application": {
            "requests_per_second": 45.2,
            "response_time_avg": 120.5,
            "error_rate": 0.02
        },
        "business": {
            "authorization_requests": 1250,
            "approval_rate": 0.85,
            "processing_time_avg": 95.3
        },
        "infrastructure": {
            "cpu_usage": 0.65,
            "memory_usage": 0.72,
            "disk_usage": 0.45
        },
        "compliance": {
            "phi_access_events": 45,
            "audit_log_entries": 1200,
            "security_violations": 0
        }
    })
    collector.get_metrics_history = Mock(return_value={
        "application": [
            {"timestamp": "2024-01-01T10:00:00Z", "requests_per_second": 42.1},
            {"timestamp": "2024-01-01T11:00:00Z", "requests_per_second": 45.2}
        ],
        "business": [
            {"timestamp": "2024-01-01T10:00:00Z", "authorization_requests": 1200},
            {"timestamp": "2024-01-01T11:00:00Z", "authorization_requests": 1250}
        ]
    })
    collector.record_custom_metric = Mock(return_value=True)
    return collector


@pytest.fixture
def mock_dashboard_metrics_service():
    """Create mock dashboard metrics service."""
    service = Mock()
    service.get_available_dashboards = Mock(return_value=[
        {
            "id": "main_dashboard",
            "name": "Main Dashboard",
            "description": "Primary system dashboard",
            "widgets": ["metrics", "alerts", "performance"]
        },
        {
            "id": "security_dashboard",
            "name": "Security Dashboard", 
            "description": "Security monitoring dashboard",
            "widgets": ["security_events", "incidents", "threats"]
        }
    ])
    service.get_dashboard_data = Mock(return_value={
        "dashboard_id": "main_dashboard",
        "data": {
            "metrics": {"active_requests": 150},
            "alerts": {"active_count": 2},
            "performance": {"avg_response_time": 120.5}
        },
        "last_updated": datetime.now(timezone.utc).isoformat()
    })
    service.create_custom_dashboard = Mock(return_value={
        "dashboard_id": "custom_123",
        "status": "created"
    })
    return service


@pytest.fixture
def mock_db_monitoring_service():
    """Create mock database monitoring service."""
    service = Mock()
    service.get_performance_metrics = Mock(return_value={
        "connection_pool": {
            "active_connections": 15,
            "idle_connections": 5,
            "max_connections": 100
        },
        "query_performance": {
            "avg_query_time": 25.3,
            "slow_queries": 2,
            "total_queries": 15420
        },
        "database_size": {
            "total_size_mb": 2048,
            "table_count": 25,
            "index_count": 45
        }
    })
    return service


@pytest.fixture
def mock_security_monitoring_service():
    """Create mock security monitoring service."""
    service = Mock()
    service.get_security_events = Mock(return_value=[
        {
            "event_id": "sec_001",
            "event_type": "AUTHENTICATION_FAILURE",
            "severity": "MEDIUM",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": {"ip_address": "192.168.1.100", "username": "test_user"}
        },
        {
            "event_id": "sec_002",
            "event_type": "UNAUTHORIZED_ACCESS",
            "severity": "HIGH",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": {"resource": "/api/v1/admin", "user_id": "user_123"}
        }
    ])
    service.record_security_event = AsyncMock(return_value={"event_id": "sec_003"})
    service.get_security_incidents = Mock(return_value=[
        {
            "incident_id": "inc_001",
            "title": "Multiple Failed Login Attempts",
            "severity": "HIGH",
            "status": "OPEN",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    ])
    service.create_security_incident = AsyncMock(return_value={"incident_id": "inc_002"})
    service.update_security_incident = AsyncMock(return_value={"status": "updated"})
    service.get_threat_intelligence_report = AsyncMock(return_value={
        "threat_level": "MEDIUM",
        "active_threats": 3,
        "blocked_ips": 15,
        "indicators": ["malicious_ip", "suspicious_user_agent"]
    })
    service.add_threat_indicator = AsyncMock(return_value={"indicator_id": "threat_001"})
    service.check_threat_indicators = AsyncMock(return_value={
        "threats_detected": 1,
        "indicators_matched": ["192.168.1.100"]
    })
    service.block_ip_address = AsyncMock(return_value={"status": "blocked"})
    service.get_blocked_ips = Mock(return_value=[
        {"ip_address": "192.168.1.100", "blocked_at": datetime.now(timezone.utc).isoformat()}
    ])
    return service


@pytest.fixture
def authenticated_user():
    """Create authenticated user."""
    return {
        "user_id": "user_123",
        "username": "test_user",
        "roles": [UserRole.SYSTEM_ADMIN],
        "organization_id": "org_123"
    }


class TestMetricsEndpoints:
    """Test metrics collection endpoints."""
    
    def test_get_current_metrics_success(
        self, 
        client, 
        mock_metrics_collector,
        authenticated_user
    ):
        """Test successful current metrics retrieval."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        with patch('src.api.monitoring.metrics_collector', mock_metrics_collector):
            try:
                response = client.get("/api/v1/monitoring/metrics/current")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert "data" in data
                assert "application" in data["data"]
                assert "business" in data["data"]
                assert "infrastructure" in data["data"]
                assert "compliance" in data["data"]
                assert "retrieved_at" in data
                
                mock_metrics_collector.get_current_metrics.assert_called_once()
                
            finally:
                app.dependency_overrides.clear()
    
    def test_get_metrics_history_success(
        self, 
        client, 
        mock_metrics_collector,
        authenticated_user
    ):
        """Test successful metrics history retrieval."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        with patch('src.api.monitoring.metrics_collector', mock_metrics_collector):
            try:
                response = client.get("/api/v1/monitoring/metrics/history?hours=24")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert "data" in data
                assert data["time_range_hours"] == 24
                assert "retrieved_at" in data
                
                mock_metrics_collector.get_metrics_history.assert_called_once_with(hours=24)
                
            finally:
                app.dependency_overrides.clear()
    
    def test_get_metrics_history_with_filter(
        self, 
        client, 
        mock_metrics_collector,
        authenticated_user
    ):
        """Test metrics history retrieval with metric type filter."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        with patch('src.api.monitoring.metrics_collector', mock_metrics_collector):
            try:
                response = client.get("/api/v1/monitoring/metrics/history?hours=12&metric_type=application")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert "application" in data["data"]
                assert len(data["data"]) == 1  # Only application metrics
                
            finally:
                app.dependency_overrides.clear()
    
    def test_get_metrics_history_invalid_hours(self, client, authenticated_user):
        """Test metrics history with invalid hours parameter."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        try:
            response = client.get("/api/v1/monitoring/metrics/history?hours=200")  # > 168
            
            assert response.status_code == 422  # Validation error
            
        finally:
            app.dependency_overrides.clear()
    
    def test_record_custom_metric_success(
        self, 
        client, 
        mock_metrics_collector,
        authenticated_user
    ):
        """Test successful custom metric recording."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        with patch('src.api.monitoring.metrics_collector', mock_metrics_collector):
            try:
                metric_data = {
                    "metric_name": "custom_metric",
                    "metric_value": 42.5,
                    "metric_type": "gauge",
                    "tags": {"service": "test", "environment": "dev"}
                }
                
                response = client.post("/api/v1/monitoring/metrics/record", json=metric_data)
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["message"] == "Custom metric recorded successfully"
                
                mock_metrics_collector.record_custom_metric.assert_called_once()
                
            finally:
                app.dependency_overrides.clear()


class TestAlertsEndpoints:
    """Test alerts management endpoints."""
    
    def test_get_active_alerts_success(self, client, authenticated_user):
        """Test successful active alerts retrieval."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        with patch('src.api.monitoring.metrics_collector') as mock_collector:
            mock_collector.get_active_alerts = Mock(return_value=[
                {
                    "alert_id": "alert_001",
                    "severity": "HIGH",
                    "message": "High CPU usage detected",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            ])
            
            try:
                response = client.get("/api/v1/monitoring/alerts/active")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert "alerts" in data
                assert len(data["alerts"]) >= 0
                
            finally:
                app.dependency_overrides.clear()
    
    def test_get_alert_history_success(self, client, authenticated_user):
        """Test successful alert history retrieval."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        with patch('src.api.monitoring.metrics_collector') as mock_collector:
            mock_collector.get_alert_history = Mock(return_value=[
                {
                    "alert_id": "alert_001",
                    "severity": "MEDIUM",
                    "message": "Database connection pool exhausted",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "resolved_at": datetime.now(timezone.utc).isoformat()
                }
            ])
            
            try:
                response = client.get("/api/v1/monitoring/alerts/history?hours=24")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert "alerts" in data
                
            finally:
                app.dependency_overrides.clear()


class TestDashboardEndpoints:
    """Test dashboard management endpoints."""
    
    def test_get_available_dashboards_success(
        self, 
        client, 
        mock_dashboard_metrics_service,
        authenticated_user
    ):
        """Test successful dashboard listing."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        with patch('src.api.monitoring.dashboard_metrics_service', mock_dashboard_metrics_service):
            try:
                response = client.get("/api/v1/monitoring/dashboards")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert "dashboards" in data
                assert len(data["dashboards"]) == 2
                assert data["dashboards"][0]["id"] == "main_dashboard"
                
                mock_dashboard_metrics_service.get_available_dashboards.assert_called_once()
                
            finally:
                app.dependency_overrides.clear()
    
    def test_get_dashboard_data_success(
        self, 
        client, 
        mock_dashboard_metrics_service,
        authenticated_user
    ):
        """Test successful dashboard data retrieval."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        with patch('src.api.monitoring.dashboard_metrics_service', mock_dashboard_metrics_service):
            try:
                response = client.get("/api/v1/monitoring/dashboards/main_dashboard")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["dashboard_id"] == "main_dashboard"
                assert "data" in data
                assert "last_updated" in data
                
                mock_dashboard_metrics_service.get_dashboard_data.assert_called_once_with("main_dashboard")
                
            finally:
                app.dependency_overrides.clear()
    
    def test_create_custom_dashboard_success(
        self, 
        client, 
        mock_dashboard_metrics_service,
        authenticated_user
    ):
        """Test successful custom dashboard creation."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        with patch('src.api.monitoring.dashboard_metrics_service', mock_dashboard_metrics_service):
            try:
                dashboard_config = {
                    "name": "Custom Dashboard",
                    "description": "My custom dashboard",
                    "widgets": [
                        {"type": "metric", "config": {"metric": "cpu_usage"}},
                        {"type": "chart", "config": {"chart_type": "line"}}
                    ]
                }
                
                response = client.post("/api/v1/monitoring/dashboards", json=dashboard_config)
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["dashboard_id"] == "custom_123"
                
                mock_dashboard_metrics_service.create_custom_dashboard.assert_called_once()
                
            finally:
                app.dependency_overrides.clear()


class TestDatabasePerformanceEndpoints:
    """Test database performance monitoring endpoints."""
    
    def test_get_database_performance_success(
        self, 
        client, 
        mock_db_monitoring_service,
        authenticated_user
    ):
        """Test successful database performance retrieval."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        with patch('src.api.monitoring.db_monitoring_service', mock_db_monitoring_service):
            try:
                response = client.get("/api/v1/monitoring/database/performance")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert "performance_data" in data
                assert "connection_pool" in data["performance_data"]
                assert "query_performance" in data["performance_data"]
                assert "database_size" in data["performance_data"]
                
                mock_db_monitoring_service.get_performance_metrics.assert_called_once()
                
            finally:
                app.dependency_overrides.clear()


class TestHealthEndpoints:
    """Test system health endpoints."""
    
    def test_get_system_health_success(self, client):
        """Test successful system health check."""
        with patch('src.api.monitoring.metrics_collector') as mock_collector, \
             patch('src.api.monitoring.db_monitoring_service') as mock_db_service:
            
            mock_collector.get_current_metrics = Mock(return_value={
                "infrastructure": {"cpu_usage": 0.65, "memory_usage": 0.72}
            })
            mock_db_service.get_performance_metrics = Mock(return_value={
                "connection_pool": {"active_connections": 15}
            })
            
            response = client.get("/api/v1/monitoring/health")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "system_info" in data
            assert "timestamp" in data


class TestSecurityMonitoringEndpoints:
    """Test security monitoring endpoints."""
    
    def test_get_security_events_success(
        self, 
        client, 
        mock_security_monitoring_service,
        authenticated_user
    ):
        """Test successful security events retrieval."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        with patch('src.api.monitoring.security_monitoring_service', mock_security_monitoring_service):
            try:
                response = client.get("/api/v1/monitoring/security/events?hours=24")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert "events" in data
                assert len(data["events"]) == 2
                assert data["events"][0]["event_type"] == "AUTHENTICATION_FAILURE"
                
                mock_security_monitoring_service.get_security_events.assert_called_once()
                
            finally:
                app.dependency_overrides.clear()
    
    def test_record_security_event_success(
        self, 
        client, 
        mock_security_monitoring_service,
        authenticated_user
    ):
        """Test successful security event recording."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        with patch('src.api.monitoring.security_monitoring_service', mock_security_monitoring_service):
            try:
                event_data = {
                    "event_type": "UNAUTHORIZED_ACCESS",
                    "severity": "HIGH",
                    "details": {
                        "ip_address": "192.168.1.100",
                        "resource": "/api/v1/admin",
                        "user_id": "user_123"
                    }
                }
                
                response = client.post("/api/v1/monitoring/security/events", json=event_data)
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["event_id"] == "sec_003"
                
                mock_security_monitoring_service.record_security_event.assert_called_once()
                
            finally:
                app.dependency_overrides.clear()
    
    def test_get_security_incidents_success(
        self, 
        client, 
        mock_security_monitoring_service,
        authenticated_user
    ):
        """Test successful security incidents retrieval."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        with patch('src.api.monitoring.security_monitoring_service', mock_security_monitoring_service):
            try:
                response = client.get("/api/v1/monitoring/security/incidents")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert "incidents" in data
                assert len(data["incidents"]) == 1
                assert data["incidents"][0]["incident_id"] == "inc_001"
                
                mock_security_monitoring_service.get_security_incidents.assert_called_once()
                
            finally:
                app.dependency_overrides.clear()
    
    def test_create_security_incident_success(
        self, 
        client, 
        mock_security_monitoring_service,
        authenticated_user
    ):
        """Test successful security incident creation."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        with patch('src.api.monitoring.security_monitoring_service', mock_security_monitoring_service):
            try:
                incident_data = {
                    "title": "Suspicious Activity Detected",
                    "description": "Multiple failed login attempts from same IP",
                    "severity": "HIGH",
                    "affected_systems": ["authentication_service"],
                    "initial_response": "Blocked IP address"
                }
                
                response = client.post("/api/v1/monitoring/security/incidents", json=incident_data)
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["incident_id"] == "inc_002"
                
                mock_security_monitoring_service.create_security_incident.assert_called_once()
                
            finally:
                app.dependency_overrides.clear()
    
    def test_get_threat_intelligence_report_success(
        self, 
        client, 
        mock_security_monitoring_service,
        authenticated_user
    ):
        """Test successful threat intelligence report retrieval."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        with patch('src.api.monitoring.security_monitoring_service', mock_security_monitoring_service):
            try:
                response = client.get("/api/v1/monitoring/security/threat-intelligence")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert "report" in data
                assert data["report"]["threat_level"] == "MEDIUM"
                assert data["report"]["active_threats"] == 3
                
                mock_security_monitoring_service.get_threat_intelligence_report.assert_called_once()
                
            finally:
                app.dependency_overrides.clear()
    
    def test_block_ip_address_success(
        self, 
        client, 
        mock_security_monitoring_service,
        authenticated_user
    ):
        """Test successful IP address blocking."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        with patch('src.api.monitoring.security_monitoring_service', mock_security_monitoring_service):
            try:
                block_data = {
                    "ip_address": "192.168.1.100",
                    "reason": "Multiple failed login attempts",
                    "duration_hours": 24,
                    "block_type": "temporary"
                }
                
                response = client.post("/api/v1/monitoring/security/block-ip", json=block_data)
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["message"] == "IP address blocked successfully"
                
                mock_security_monitoring_service.block_ip_address.assert_called_once()
                
            finally:
                app.dependency_overrides.clear()


class TestErrorHandling:
    """Test error handling scenarios."""
    
    def test_metrics_service_error(self, client, authenticated_user):
        """Test metrics endpoint with service error."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        with patch('src.api.monitoring.metrics_collector') as mock_collector:
            mock_collector.get_current_metrics.side_effect = Exception("Service error")
            
            try:
                response = client.get("/api/v1/monitoring/metrics/current")
                
                assert response.status_code == 500
                data = response.json()
                assert "Failed to retrieve current metrics" in data["detail"]
                
            finally:
                app.dependency_overrides.clear()
    
    def test_unauthorized_access(self, client):
        """Test endpoint access without authentication."""
        response = client.get("/api/v1/monitoring/metrics/current")
        
        assert response.status_code == 401  # Unauthorized


class TestImportAndBasicFunctionality:
    """Test basic import and functionality."""
    
    def test_router_import(self):
        """Test that the router can be imported."""
        from src.api.monitoring import router
        assert router is not None
        assert hasattr(router, 'routes')
    
    def test_endpoint_count(self):
        """Test that all expected endpoints are registered."""
        from src.api.monitoring import router
        
        # Should have 19 endpoints based on our analysis
        routes = [route for route in router.routes if hasattr(route, 'methods')]
        assert len(routes) >= 19
    
    def test_service_imports(self):
        """Test that all required services can be imported."""
        from src.services.monitoring import metrics_collector
        from src.services.dashboard_metrics import dashboard_metrics_service
        from src.services.database_monitoring import db_monitoring_service
        from src.services.security_monitoring import security_monitoring_service
        
        assert metrics_collector is not None
        assert dashboard_metrics_service is not None
        assert db_monitoring_service is not None
        assert security_monitoring_service is not None
    
    def test_logger_initialization(self):
        """Test that logger is properly initialized."""
        from src.api.monitoring import logger
        assert logger is not None
    
    def test_dependencies_import(self):
        """Test that all dependencies can be imported."""
        from src.auth.oauth2 import get_current_user
        from src.core.logging import get_logger
        
        assert get_current_user is not None
        assert get_logger is not None
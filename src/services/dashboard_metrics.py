"""
Dashboard metrics service for system health and compliance monitoring.

This module provides custom dashboards and visualizations for monitoring
system performance, business KPIs, and compliance metrics.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import json
import asyncio

from src.services.monitoring import metrics_collector
from src.services.database_monitoring import db_monitoring_service
from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DashboardWidget:
    """Dashboard widget configuration."""
    widget_id: str
    title: str
    widget_type: str  # chart, gauge, table, alert_list, kpi_card
    data_source: str
    refresh_interval: int  # seconds
    config: Dict[str, Any]


@dataclass
class DashboardLayout:
    """Dashboard layout configuration."""
    dashboard_id: str
    title: str
    description: str
    widgets: List[DashboardWidget]
    refresh_interval: int
    access_roles: List[str]


class DashboardMetricsService:
    """
    Service for generating dashboard data and managing custom dashboards.
    
    Provides real-time data for system health monitoring, business KPIs,
    and compliance dashboards with customizable layouts and widgets.
    """
    
    def __init__(self):
        self.dashboards = {}
        self._initialize_default_dashboards()
    
    def _initialize_default_dashboards(self):
        """Initialize default dashboard configurations."""
        
        # System Health Dashboard
        system_health_widgets = [
            DashboardWidget(
                widget_id="system_overview",
                title="System Overview",
                widget_type="kpi_card",
                data_source="application_metrics",
                refresh_interval=30,
                config={
                    "metrics": ["requests_per_second", "avg_response_time", "error_rate", "active_sessions"],
                    "thresholds": {"error_rate": 5.0, "avg_response_time": 2000}
                }
            ),
            DashboardWidget(
                widget_id="infrastructure_status",
                title="Infrastructure Status",
                widget_type="gauge",
                data_source="infrastructure_metrics",
                refresh_interval=60,
                config={
                    "metrics": ["cpu_usage_percent", "memory_usage_percent", "disk_usage_percent"],
                    "warning_threshold": 80,
                    "critical_threshold": 90
                }
            ),
            DashboardWidget(
                widget_id="response_time_chart",
                title="Response Time Trend",
                widget_type="chart",
                data_source="application_metrics",
                refresh_interval=60,
                config={
                    "chart_type": "line",
                    "metric": "avg_response_time",
                    "time_range": "1h",
                    "y_axis_label": "Response Time (ms)"
                }
            ),
            DashboardWidget(
                widget_id="active_alerts",
                title="Active Alerts",
                widget_type="alert_list",
                data_source="alerts",
                refresh_interval=30,
                config={
                    "max_items": 10,
                    "severity_filter": ["HIGH", "CRITICAL"]
                }
            )
        ]
        
        self.dashboards["system_health"] = DashboardLayout(
            dashboard_id="system_health",
            title="System Health Dashboard",
            description="Real-time system performance and infrastructure monitoring",
            widgets=system_health_widgets,
            refresh_interval=30,
            access_roles=["admin", "operator"]
        )
        
        # Business KPI Dashboard
        business_kpi_widgets = [
            DashboardWidget(
                widget_id="daily_summary",
                title="Daily Summary",
                widget_type="kpi_card",
                data_source="business_metrics",
                refresh_interval=300,
                config={
                    "metrics": ["total_requests_today", "total_approvals_today", "total_denials_today"],
                    "show_trends": True
                }
            ),
            DashboardWidget(
                widget_id="approval_rate_gauge",
                title="Approval Rate",
                widget_type="gauge",
                data_source="business_metrics",
                refresh_interval=300,
                config={
                    "metric": "approval_rate",
                    "min_value": 0,
                    "max_value": 100,
                    "warning_threshold": 60,
                    "target_threshold": 80
                }
            ),
            DashboardWidget(
                widget_id="sla_compliance",
                title="SLA Compliance",
                widget_type="gauge",
                data_source="business_metrics",
                refresh_interval=300,
                config={
                    "metric": "sla_compliance_rate",
                    "min_value": 0,
                    "max_value": 100,
                    "warning_threshold": 95,
                    "target_threshold": 98
                }
            ),
            DashboardWidget(
                widget_id="processing_time_trend",
                title="Processing Time Trend",
                widget_type="chart",
                data_source="business_metrics",
                refresh_interval=300,
                config={
                    "chart_type": "line",
                    "metric": "avg_processing_time_minutes",
                    "time_range": "24h",
                    "y_axis_label": "Processing Time (minutes)"
                }
            )
        ]
        
        self.dashboards["business_kpi"] = DashboardLayout(
            dashboard_id="business_kpi",
            title="Business KPI Dashboard",
            description="Business performance metrics and key indicators",
            widgets=business_kpi_widgets,
            refresh_interval=300,
            access_roles=["admin", "business_analyst", "manager"]
        )
        
        # Compliance Dashboard
        compliance_widgets = [
            DashboardWidget(
                widget_id="compliance_overview",
                title="Compliance Overview",
                widget_type="kpi_card",
                data_source="compliance_metrics",
                refresh_interval=300,
                config={
                    "metrics": ["audit_compliance_score", "encryption_compliance_rate", "data_retention_compliance"],
                    "thresholds": {"audit_compliance_score": 95.0}
                }
            ),
            DashboardWidget(
                widget_id="security_incidents",
                title="Security Incidents",
                widget_type="table",
                data_source="compliance_metrics",
                refresh_interval=300,
                config={
                    "columns": ["timestamp", "incident_type", "severity", "status"],
                    "max_rows": 20,
                    "sort_by": "timestamp",
                    "sort_order": "desc"
                }
            ),
            DashboardWidget(
                widget_id="phi_access_chart",
                title="PHI Access Events",
                widget_type="chart",
                data_source="compliance_metrics",
                refresh_interval=300,
                config={
                    "chart_type": "bar",
                    "metric": "phi_access_events",
                    "time_range": "24h",
                    "y_axis_label": "Access Events"
                }
            ),
            DashboardWidget(
                widget_id="audit_alerts",
                title="Compliance Alerts",
                widget_type="alert_list",
                data_source="alerts",
                refresh_interval=60,
                config={
                    "max_items": 10,
                    "category_filter": ["compliance", "security"]
                }
            )
        ]
        
        self.dashboards["compliance"] = DashboardLayout(
            dashboard_id="compliance",
            title="Compliance Dashboard",
            description="HIPAA compliance and security monitoring",
            widgets=compliance_widgets,
            refresh_interval=300,
            access_roles=["admin", "compliance_officer", "security_analyst"]
        )
        
        # Database Performance Dashboard
        db_performance_widgets = [
            DashboardWidget(
                widget_id="db_overview",
                title="Database Overview",
                widget_type="kpi_card",
                data_source="database_metrics",
                refresh_interval=60,
                config={
                    "metrics": ["queries_per_second", "avg_query_time", "connections_active", "cache_hit_rate"],
                    "thresholds": {"avg_query_time": 0.5, "cache_hit_rate": 85.0}
                }
            ),
            DashboardWidget(
                widget_id="query_performance",
                title="Query Performance",
                widget_type="chart",
                data_source="database_metrics",
                refresh_interval=60,
                config={
                    "chart_type": "line",
                    "metrics": ["avg_query_time", "slow_queries_count"],
                    "time_range": "2h",
                    "y_axis_label": "Time (seconds) / Count"
                }
            ),
            DashboardWidget(
                widget_id="table_metrics",
                title="Table Metrics",
                widget_type="table",
                data_source="database_metrics",
                refresh_interval=300,
                config={
                    "columns": ["table_name", "row_count", "table_size_mb", "fragmentation_percent"],
                    "sort_by": "table_size_mb",
                    "sort_order": "desc"
                }
            ),
            DashboardWidget(
                widget_id="db_recommendations",
                title="Performance Recommendations",
                widget_type="table",
                data_source="database_metrics",
                refresh_interval=300,
                config={
                    "columns": ["category", "recommendation", "priority"],
                    "max_rows": 10
                }
            )
        ]
        
        self.dashboards["database_performance"] = DashboardLayout(
            dashboard_id="database_performance",
            title="Database Performance Dashboard",
            description="Database performance monitoring and optimization",
            widgets=db_performance_widgets,
            refresh_interval=60,
            access_roles=["admin", "dba", "developer"]
        )
    
    async def get_dashboard_data(self, dashboard_id: str) -> Dict[str, Any]:
        """
        Get complete dashboard data including all widget data.
        
        Args:
            dashboard_id: ID of the dashboard to retrieve
            
        Returns:
            Dictionary containing dashboard layout and widget data
        """
        if dashboard_id not in self.dashboards:
            raise ValueError(f"Dashboard {dashboard_id} not found")
        
        dashboard = self.dashboards[dashboard_id]
        
        # Collect data for all widgets
        widget_data = {}
        for widget in dashboard.widgets:
            try:
                data = await self._get_widget_data(widget)
                widget_data[widget.widget_id] = data
            except Exception as e:
                logger.error(f"Failed to get data for widget {widget.widget_id}: {e}")
                widget_data[widget.widget_id] = {"error": str(e)}
        
        return {
            "dashboard": asdict(dashboard),
            "widget_data": widget_data,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    
    async def _get_widget_data(self, widget: DashboardWidget) -> Dict[str, Any]:
        """Get data for a specific widget."""
        if widget.data_source == "application_metrics":
            return await self._get_application_metrics_data(widget)
        elif widget.data_source == "business_metrics":
            return await self._get_business_metrics_data(widget)
        elif widget.data_source == "infrastructure_metrics":
            return await self._get_infrastructure_metrics_data(widget)
        elif widget.data_source == "compliance_metrics":
            return await self._get_compliance_metrics_data(widget)
        elif widget.data_source == "database_metrics":
            return await self._get_database_metrics_data(widget)
        elif widget.data_source == "alerts":
            return await self._get_alerts_data(widget)
        else:
            raise ValueError(f"Unknown data source: {widget.data_source}")
    
    async def _get_application_metrics_data(self, widget: DashboardWidget) -> Dict[str, Any]:
        """Get application metrics data for widget."""
        current_metrics = metrics_collector.get_current_metrics()
        app_metrics = current_metrics.get('application')
        
        if not app_metrics:
            return {"error": "No application metrics available"}
        
        if widget.widget_type == "kpi_card":
            metrics = widget.config.get("metrics", [])
            data = {}
            for metric in metrics:
                if metric in app_metrics:
                    data[metric] = {
                        "value": app_metrics[metric],
                        "threshold": widget.config.get("thresholds", {}).get(metric),
                        "status": self._get_metric_status(app_metrics[metric], 
                                                        widget.config.get("thresholds", {}).get(metric))
                    }
            return {"metrics": data}
        
        elif widget.widget_type == "chart":
            time_range = widget.config.get("time_range", "1h")
            hours = self._parse_time_range(time_range)
            history = metrics_collector.get_metrics_history(hours)
            
            metric = widget.config.get("metric")
            chart_data = []
            
            for item in history.get('application', []):
                if metric in item:
                    chart_data.append({
                        "timestamp": item["timestamp"],
                        "value": item[metric]
                    })
            
            return {
                "chart_type": widget.config.get("chart_type", "line"),
                "data": chart_data,
                "metric": metric,
                "y_axis_label": widget.config.get("y_axis_label", metric)
            }
        
        return {"data": app_metrics}
    
    async def _get_business_metrics_data(self, widget: DashboardWidget) -> Dict[str, Any]:
        """Get business metrics data for widget."""
        current_metrics = metrics_collector.get_current_metrics()
        business_metrics = current_metrics.get('business')
        
        if not business_metrics:
            return {"error": "No business metrics available"}
        
        if widget.widget_type == "kpi_card":
            metrics = widget.config.get("metrics", [])
            data = {}
            for metric in metrics:
                if metric in business_metrics:
                    data[metric] = {
                        "value": business_metrics[metric],
                        "trend": self._calculate_trend(metric, "business") if widget.config.get("show_trends") else None
                    }
            return {"metrics": data}
        
        elif widget.widget_type == "gauge":
            metric = widget.config.get("metric")
            if metric in business_metrics:
                return {
                    "value": business_metrics[metric],
                    "min_value": widget.config.get("min_value", 0),
                    "max_value": widget.config.get("max_value", 100),
                    "warning_threshold": widget.config.get("warning_threshold"),
                    "target_threshold": widget.config.get("target_threshold")
                }
        
        elif widget.widget_type == "chart":
            time_range = widget.config.get("time_range", "24h")
            hours = self._parse_time_range(time_range)
            history = metrics_collector.get_metrics_history(hours)
            
            metric = widget.config.get("metric")
            chart_data = []
            
            for item in history.get('business', []):
                if metric in item:
                    chart_data.append({
                        "timestamp": item["timestamp"],
                        "value": item[metric]
                    })
            
            return {
                "chart_type": widget.config.get("chart_type", "line"),
                "data": chart_data,
                "metric": metric,
                "y_axis_label": widget.config.get("y_axis_label", metric)
            }
        
        return {"data": business_metrics}
    
    async def _get_infrastructure_metrics_data(self, widget: DashboardWidget) -> Dict[str, Any]:
        """Get infrastructure metrics data for widget."""
        current_metrics = metrics_collector.get_current_metrics()
        infra_metrics = current_metrics.get('infrastructure')
        
        if not infra_metrics:
            return {"error": "No infrastructure metrics available"}
        
        if widget.widget_type == "gauge":
            metrics = widget.config.get("metrics", [])
            data = {}
            for metric in metrics:
                if metric in infra_metrics:
                    data[metric] = {
                        "value": infra_metrics[metric],
                        "warning_threshold": widget.config.get("warning_threshold"),
                        "critical_threshold": widget.config.get("critical_threshold"),
                        "status": self._get_threshold_status(
                            infra_metrics[metric],
                            widget.config.get("warning_threshold"),
                            widget.config.get("critical_threshold")
                        )
                    }
            return {"gauges": data}
        
        return {"data": infra_metrics}
    
    async def _get_compliance_metrics_data(self, widget: DashboardWidget) -> Dict[str, Any]:
        """Get compliance metrics data for widget."""
        current_metrics = metrics_collector.get_current_metrics()
        compliance_metrics = current_metrics.get('compliance')
        
        if not compliance_metrics:
            return {"error": "No compliance metrics available"}
        
        if widget.widget_type == "kpi_card":
            metrics = widget.config.get("metrics", [])
            data = {}
            for metric in metrics:
                if metric in compliance_metrics:
                    data[metric] = {
                        "value": compliance_metrics[metric],
                        "threshold": widget.config.get("thresholds", {}).get(metric),
                        "status": self._get_metric_status(compliance_metrics[metric], 
                                                        widget.config.get("thresholds", {}).get(metric))
                    }
            return {"metrics": data}
        
        elif widget.widget_type == "chart":
            time_range = widget.config.get("time_range", "24h")
            hours = self._parse_time_range(time_range)
            history = metrics_collector.get_metrics_history(hours)
            
            metric = widget.config.get("metric")
            chart_data = []
            
            for item in history.get('compliance', []):
                if metric in item:
                    chart_data.append({
                        "timestamp": item["timestamp"],
                        "value": item[metric]
                    })
            
            return {
                "chart_type": widget.config.get("chart_type", "bar"),
                "data": chart_data,
                "metric": metric,
                "y_axis_label": widget.config.get("y_axis_label", metric)
            }
        
        return {"data": compliance_metrics}
    
    async def _get_database_metrics_data(self, widget: DashboardWidget) -> Dict[str, Any]:
        """Get database metrics data for widget."""
        try:
            if widget.widget_type == "kpi_card":
                current_metrics = await db_monitoring_service.collect_database_metrics()
                metrics = widget.config.get("metrics", [])
                data = {}
                
                metrics_dict = asdict(current_metrics)
                for metric in metrics:
                    if metric in metrics_dict:
                        data[metric] = {
                            "value": metrics_dict[metric],
                            "threshold": widget.config.get("thresholds", {}).get(metric),
                            "status": self._get_metric_status(metrics_dict[metric], 
                                                            widget.config.get("thresholds", {}).get(metric))
                        }
                return {"metrics": data}
            
            elif widget.widget_type == "table" and "table_metrics" in widget.widget_id:
                table_metrics = await db_monitoring_service.analyze_table_performance()
                
                table_data = []
                for table_name, metrics in table_metrics.items():
                    table_data.append({
                        "table_name": table_name,
                        "row_count": metrics.row_count,
                        "table_size_mb": metrics.table_size_mb,
                        "fragmentation_percent": metrics.fragmentation_percent
                    })
                
                return {"table_data": table_data}
            
            elif widget.widget_type == "table" and "recommendations" in widget.widget_id:
                recommendations = await db_monitoring_service.get_performance_recommendations()
                
                rec_data = []
                for category, recs in recommendations.items():
                    for rec in recs:
                        rec_data.append({
                            "category": category,
                            "recommendation": rec,
                            "priority": "HIGH" if "critical" in rec.lower() else "MEDIUM"
                        })
                
                return {"recommendations": rec_data}
            
            return {"error": "Unsupported widget type for database metrics"}
            
        except Exception as e:
            logger.error(f"Failed to get database metrics: {e}")
            return {"error": str(e)}
    
    async def _get_alerts_data(self, widget: DashboardWidget) -> Dict[str, Any]:
        """Get alerts data for widget."""
        current_metrics = metrics_collector.get_current_metrics()
        active_alerts = current_metrics.get('active_alerts', [])
        
        # Filter alerts based on widget configuration
        severity_filter = widget.config.get("severity_filter", [])
        category_filter = widget.config.get("category_filter", [])
        max_items = widget.config.get("max_items", 10)
        
        filtered_alerts = []
        for alert in active_alerts:
            if severity_filter and alert.get("severity") not in severity_filter:
                continue
            if category_filter and alert.get("alert_type") not in category_filter:
                continue
            filtered_alerts.append(alert)
        
        # Sort by timestamp (most recent first) and limit
        filtered_alerts.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        filtered_alerts = filtered_alerts[:max_items]
        
        return {"alerts": filtered_alerts}
    
    def _get_metric_status(self, value: float, threshold: Optional[float]) -> str:
        """Get status based on metric value and threshold."""
        if threshold is None:
            return "normal"
        
        if value > threshold:
            return "warning"
        elif value > threshold * 0.8:
            return "caution"
        else:
            return "normal"
    
    def _get_threshold_status(self, value: float, warning_threshold: Optional[float], 
                            critical_threshold: Optional[float]) -> str:
        """Get status based on warning and critical thresholds."""
        if critical_threshold and value >= critical_threshold:
            return "critical"
        elif warning_threshold and value >= warning_threshold:
            return "warning"
        else:
            return "normal"
    
    def _calculate_trend(self, metric: str, metric_type: str) -> Optional[str]:
        """Calculate trend for a metric (up, down, stable)."""
        history = metrics_collector.get_metrics_history(hours=2)
        metric_history = history.get(metric_type, [])
        
        if len(metric_history) < 2:
            return None
        
        recent_values = [item.get(metric, 0) for item in metric_history[-10:]]
        older_values = [item.get(metric, 0) for item in metric_history[-20:-10]]
        
        if not older_values:
            return None
        
        recent_avg = sum(recent_values) / len(recent_values)
        older_avg = sum(older_values) / len(older_values)
        
        if recent_avg > older_avg * 1.05:
            return "up"
        elif recent_avg < older_avg * 0.95:
            return "down"
        else:
            return "stable"
    
    def _parse_time_range(self, time_range: str) -> int:
        """Parse time range string to hours."""
        if time_range.endswith('h'):
            return int(time_range[:-1])
        elif time_range.endswith('d'):
            return int(time_range[:-1]) * 24
        elif time_range.endswith('m'):
            return max(1, int(time_range[:-1]) // 60)
        else:
            return 1  # Default to 1 hour
    
    def get_available_dashboards(self) -> List[Dict[str, Any]]:
        """Get list of available dashboards."""
        return [
            {
                "dashboard_id": dashboard.dashboard_id,
                "title": dashboard.title,
                "description": dashboard.description,
                "access_roles": dashboard.access_roles
            }
            for dashboard in self.dashboards.values()
        ]
    
    def create_custom_dashboard(self, dashboard_config: Dict[str, Any]) -> str:
        """Create a custom dashboard from configuration."""
        dashboard_id = dashboard_config.get("dashboard_id")
        if not dashboard_id:
            raise ValueError("Dashboard ID is required")
        
        if dashboard_id in self.dashboards:
            raise ValueError(f"Dashboard {dashboard_id} already exists")
        
        # Convert widget configs to DashboardWidget objects
        widgets = []
        for widget_config in dashboard_config.get("widgets", []):
            widget = DashboardWidget(**widget_config)
            widgets.append(widget)
        
        dashboard = DashboardLayout(
            dashboard_id=dashboard_id,
            title=dashboard_config.get("title", "Custom Dashboard"),
            description=dashboard_config.get("description", ""),
            widgets=widgets,
            refresh_interval=dashboard_config.get("refresh_interval", 60),
            access_roles=dashboard_config.get("access_roles", ["admin"])
        )
        
        self.dashboards[dashboard_id] = dashboard
        logger.info(f"Created custom dashboard: {dashboard_id}")
        
        return dashboard_id


# Global dashboard metrics service instance
dashboard_metrics_service = DashboardMetricsService()
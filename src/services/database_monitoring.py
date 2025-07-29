"""
Database performance monitoring service for the Prior Authorization Agent.

This module provides real-time database performance monitoring, alerting,
and automated optimization recommendations.
"""

import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict
import json

from sqlalchemy import text, func
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from src.database.connection import get_database_manager
from src.services.database_optimization import db_optimization_service
from src.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class DatabaseMetrics:
    """Database performance metrics."""
    timestamp: datetime
    connections_active: int
    connections_idle: int
    queries_per_second: float
    avg_query_time: float
    slow_queries_count: int
    cache_hit_rate: float
    disk_usage_mb: float
    memory_usage_mb: float


@dataclass
class TableMetrics:
    """Table-specific performance metrics."""
    table_name: str
    row_count: int
    table_size_mb: float
    index_size_mb: float
    avg_row_length: int
    fragmentation_percent: float
    last_analyzed: Optional[datetime]


@dataclass
class QueryAnalysis:
    """Query performance analysis."""
    query_pattern: str
    execution_count: int
    total_time: float
    avg_time: float
    max_time: float
    rows_examined_avg: int
    rows_sent_avg: int
    optimization_suggestions: List[str]


@dataclass
class PerformanceAlert:
    """Performance alert information."""
    alert_type: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    message: str
    metric_value: float
    threshold: float
    timestamp: datetime
    suggested_actions: List[str]


class DatabaseMonitoringService:
    """
    Service for monitoring database performance and generating alerts.
    
    Provides real-time monitoring, performance analysis, and automated
    optimization recommendations for the database layer.
    """
    
    def __init__(self):
        self.db_manager = get_database_manager()
        self.settings = get_settings()
        self.metrics_history: List[DatabaseMetrics] = []
        self.table_metrics: Dict[str, TableMetrics] = {}
        self.query_analysis: Dict[str, QueryAnalysis] = {}
        self.active_alerts: List[PerformanceAlert] = []
        
        # Performance thresholds
        self.thresholds = {
            'slow_query_time': 2.0,  # seconds
            'connection_utilization': 0.8,  # 80%
            'cache_hit_rate_min': 0.85,  # 85%
            'queries_per_second_max': 1000,
            'avg_query_time_max': 0.5,  # seconds
            'disk_usage_warning': 80.0,  # 80% full
            'memory_usage_warning': 85.0  # 85% full
        }
    
    async def collect_database_metrics(self) -> DatabaseMetrics:
        """
        Collect comprehensive database performance metrics.
        
        Returns:
            DatabaseMetrics object with current performance data
        """
        try:
            with self.db_manager.get_session() as session:
                metrics = DatabaseMetrics(
                    timestamp=datetime.now(timezone.utc),
                    connections_active=await self._get_active_connections(session),
                    connections_idle=await self._get_idle_connections(session),
                    queries_per_second=await self._get_queries_per_second(session),
                    avg_query_time=await self._get_avg_query_time(session),
                    slow_queries_count=await self._get_slow_queries_count(session),
                    cache_hit_rate=await self._get_cache_hit_rate(session),
                    disk_usage_mb=await self._get_disk_usage(session),
                    memory_usage_mb=await self._get_memory_usage(session)
                )
                
                # Store metrics in history
                self.metrics_history.append(metrics)
                
                # Keep only last 24 hours of metrics
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
                self.metrics_history = [
                    m for m in self.metrics_history 
                    if m.timestamp > cutoff_time
                ]
                
                # Check for performance alerts
                await self._check_performance_alerts(metrics)
                
                logger.debug(f"Collected database metrics: {metrics.queries_per_second:.1f} QPS, "
                           f"{metrics.avg_query_time:.3f}s avg query time")
                
                return metrics
                
        except Exception as e:
            logger.error(f"Failed to collect database metrics: {e}")
            raise
    
    async def analyze_table_performance(self) -> Dict[str, TableMetrics]:
        """
        Analyze performance metrics for all tables.
        
        Returns:
            Dictionary mapping table names to their metrics
        """
        tables = ['authorization_requests', 'authorization_decisions', 'coverage_policies']
        
        try:
            with self.db_manager.get_session() as session:
                for table_name in tables:
                    metrics = await self._get_table_metrics(session, table_name)
                    self.table_metrics[table_name] = metrics
                
                logger.info(f"Analyzed performance for {len(tables)} tables")
                return self.table_metrics
                
        except Exception as e:
            logger.error(f"Failed to analyze table performance: {e}")
            raise
    
    async def analyze_query_patterns(self) -> Dict[str, QueryAnalysis]:
        """
        Analyze query patterns and performance.
        
        Returns:
            Dictionary mapping query patterns to their analysis
        """
        try:
            # Get query performance data from optimization service
            query_stats = db_optimization_service.get_query_performance_stats(hours=24)
            
            if query_stats.get('status') == 'no_data':
                logger.warning("No query performance data available for analysis")
                return {}
            
            # Analyze each query type
            for query_type, stats in query_stats.get('by_query_type', {}).items():
                analysis = QueryAnalysis(
                    query_pattern=query_type,
                    execution_count=stats['count'],
                    total_time=stats['avg_execution_time'] * stats['count'],
                    avg_time=stats['avg_execution_time'],
                    max_time=stats['max_execution_time'],
                    rows_examined_avg=stats.get('total_rows', 0) // max(stats['count'], 1),
                    rows_sent_avg=stats.get('total_rows', 0) // max(stats['count'], 1),
                    optimization_suggestions=self._generate_query_optimizations(stats)
                )
                
                self.query_analysis[query_type] = analysis
            
            logger.info(f"Analyzed {len(self.query_analysis)} query patterns")
            return self.query_analysis
            
        except Exception as e:
            logger.error(f"Failed to analyze query patterns: {e}")
            raise
    
    async def get_performance_recommendations(self) -> Dict[str, List[str]]:
        """
        Generate performance optimization recommendations.
        
        Returns:
            Dictionary with categorized recommendations
        """
        recommendations = {
            'indexing': [],
            'queries': [],
            'configuration': [],
            'maintenance': [],
            'caching': []
        }
        
        try:
            # Analyze recent metrics
            if self.metrics_history:
                recent_metrics = self.metrics_history[-10:]  # Last 10 measurements
                
                # Connection pool recommendations
                avg_active = sum(m.connections_active for m in recent_metrics) / len(recent_metrics)
                pool_size = self.settings.db_pool_size
                
                if avg_active > pool_size * 0.8:
                    recommendations['configuration'].append(
                        f"Consider increasing connection pool size from {pool_size} "
                        f"(current utilization: {avg_active/pool_size:.1%})"
                    )
                
                # Query performance recommendations
                avg_query_time = sum(m.avg_query_time for m in recent_metrics) / len(recent_metrics)
                if avg_query_time > self.thresholds['avg_query_time_max']:
                    recommendations['queries'].append(
                        f"Average query time ({avg_query_time:.3f}s) exceeds threshold "
                        f"({self.thresholds['avg_query_time_max']}s)"
                    )
                
                # Cache hit rate recommendations
                avg_cache_hit = sum(m.cache_hit_rate for m in recent_metrics) / len(recent_metrics)
                if avg_cache_hit < self.thresholds['cache_hit_rate_min']:
                    recommendations['caching'].append(
                        f"Cache hit rate ({avg_cache_hit:.1%}) is below optimal "
                        f"({self.thresholds['cache_hit_rate_min']:.1%})"
                    )
            
            # Table-specific recommendations
            for table_name, metrics in self.table_metrics.items():
                if metrics.fragmentation_percent > 10:
                    recommendations['maintenance'].append(
                        f"Table {table_name} has {metrics.fragmentation_percent:.1f}% "
                        "fragmentation - consider OPTIMIZE TABLE"
                    )
                
                if metrics.table_size_mb > 1000 and not metrics.last_analyzed:
                    recommendations['maintenance'].append(
                        f"Large table {table_name} ({metrics.table_size_mb:.1f}MB) "
                        "needs statistics update - run ANALYZE TABLE"
                    )
            
            # Query pattern recommendations
            for pattern, analysis in self.query_analysis.items():
                if analysis.avg_time > self.thresholds['slow_query_time']:
                    recommendations['queries'].extend(analysis.optimization_suggestions)
            
            logger.info(f"Generated {sum(len(recs) for recs in recommendations.values())} recommendations")
            return recommendations
            
        except Exception as e:
            logger.error(f"Failed to generate performance recommendations: {e}")
            return recommendations
    
    async def get_active_alerts(self) -> List[PerformanceAlert]:
        """
        Get currently active performance alerts.
        
        Returns:
            List of active performance alerts
        """
        # Remove expired alerts (older than 1 hour)
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=1)
        self.active_alerts = [
            alert for alert in self.active_alerts 
            if alert.timestamp > cutoff_time
        ]
        
        return self.active_alerts
    
    async def generate_performance_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive performance report.
        
        Returns:
            Dictionary with complete performance analysis
        """
        try:
            # Collect current metrics
            current_metrics = await self.collect_database_metrics()
            
            # Analyze tables and queries
            table_metrics = await self.analyze_table_performance()
            query_analysis = await self.analyze_query_patterns()
            
            # Get recommendations and alerts
            recommendations = await self.get_performance_recommendations()
            active_alerts = await self.get_active_alerts()
            
            # Calculate trends
            trends = self._calculate_performance_trends()
            
            report = {
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'current_metrics': asdict(current_metrics),
                'table_metrics': {name: asdict(metrics) for name, metrics in table_metrics.items()},
                'query_analysis': {pattern: asdict(analysis) for pattern, analysis in query_analysis.items()},
                'recommendations': recommendations,
                'active_alerts': [asdict(alert) for alert in active_alerts],
                'performance_trends': trends,
                'summary': {
                    'overall_health': self._calculate_overall_health(),
                    'critical_issues': len([a for a in active_alerts if a.severity == 'CRITICAL']),
                    'total_recommendations': sum(len(recs) for recs in recommendations.values())
                }
            }
            
            logger.info("Generated comprehensive performance report")
            return report
            
        except Exception as e:
            logger.error(f"Failed to generate performance report: {e}")
            raise
    
    # Private helper methods
    
    async def _get_active_connections(self, session) -> int:
        """Get number of active database connections."""
        try:
            if self.db_manager.engine.dialect.name == 'mysql':
                result = session.execute(text("SHOW STATUS LIKE 'Threads_connected'"))
                row = result.fetchone()
                return int(row[1]) if row else 0
            else:
                # SQLite or other databases
                return 1
        except Exception:
            return 0
    
    async def _get_idle_connections(self, session) -> int:
        """Get number of idle database connections."""
        try:
            if self.db_manager.engine.dialect.name == 'mysql':
                result = session.execute(text("SHOW STATUS LIKE 'Threads_running'"))
                row = result.fetchone()
                active = int(row[1]) if row else 0
                
                result = session.execute(text("SHOW STATUS LIKE 'Threads_connected'"))
                row = result.fetchone()
                total = int(row[1]) if row else 0
                
                return max(0, total - active)
            else:
                return 0
        except Exception:
            return 0
    
    async def _get_queries_per_second(self, session) -> float:
        """Calculate queries per second."""
        try:
            if self.db_manager.engine.dialect.name == 'mysql':
                result = session.execute(text("SHOW STATUS LIKE 'Questions'"))
                row = result.fetchone()
                questions = int(row[1]) if row else 0
                
                result = session.execute(text("SHOW STATUS LIKE 'Uptime'"))
                row = result.fetchone()
                uptime = int(row[1]) if row else 1
                
                return questions / uptime
            else:
                return 0.0
        except Exception:
            return 0.0
    
    async def _get_avg_query_time(self, session) -> float:
        """Get average query execution time."""
        # Use optimization service data if available
        stats = db_optimization_service.get_query_performance_stats(hours=1)
        if stats.get('status') != 'no_data':
            total_time = 0
            total_queries = 0
            
            for query_stats in stats.get('by_query_type', {}).values():
                total_time += query_stats['avg_execution_time'] * query_stats['count']
                total_queries += query_stats['count']
            
            return total_time / max(total_queries, 1)
        
        return 0.0
    
    async def _get_slow_queries_count(self, session) -> int:
        """Get count of slow queries."""
        slow_queries = db_optimization_service.get_slow_queries(threshold_seconds=self.thresholds['slow_query_time'])
        return len(slow_queries)
    
    async def _get_cache_hit_rate(self, session) -> float:
        """Get cache hit rate."""
        # This would integrate with the caching system
        # For now, return a placeholder value
        return 0.85
    
    async def _get_disk_usage(self, session) -> float:
        """Get database disk usage in MB."""
        try:
            if self.db_manager.engine.dialect.name == 'mysql':
                result = session.execute(text("""
                    SELECT ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) as size_mb
                    FROM information_schema.tables 
                    WHERE table_schema = DATABASE()
                """))
                row = result.fetchone()
                return float(row[0]) if row and row[0] else 0.0
            else:
                return 0.0
        except Exception:
            return 0.0
    
    async def _get_memory_usage(self, session) -> float:
        """Get database memory usage in MB."""
        try:
            if self.db_manager.engine.dialect.name == 'mysql':
                result = session.execute(text("SHOW STATUS LIKE 'Innodb_buffer_pool_bytes_data'"))
                row = result.fetchone()
                return float(row[1]) / 1024 / 1024 if row else 0.0
            else:
                return 0.0
        except Exception:
            return 0.0
    
    async def _get_table_metrics(self, session, table_name: str) -> TableMetrics:
        """Get metrics for a specific table."""
        try:
            if self.db_manager.engine.dialect.name == 'mysql':
                result = session.execute(text(f"""
                    SELECT 
                        table_rows,
                        ROUND((data_length) / 1024 / 1024, 2) as table_size_mb,
                        ROUND((index_length) / 1024 / 1024, 2) as index_size_mb,
                        avg_row_length,
                        ROUND((data_free / (data_length + index_length)) * 100, 2) as fragmentation
                    FROM information_schema.tables 
                    WHERE table_schema = DATABASE() AND table_name = '{table_name}'
                """))
                
                row = result.fetchone()
                if row:
                    return TableMetrics(
                        table_name=table_name,
                        row_count=int(row[0]) if row[0] else 0,
                        table_size_mb=float(row[1]) if row[1] else 0.0,
                        index_size_mb=float(row[2]) if row[2] else 0.0,
                        avg_row_length=int(row[3]) if row[3] else 0,
                        fragmentation_percent=float(row[4]) if row[4] else 0.0,
                        last_analyzed=None  # Would need to check statistics tables
                    )
            
            # Fallback for other databases
            result = session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            row_count = result.scalar()
            
            return TableMetrics(
                table_name=table_name,
                row_count=row_count,
                table_size_mb=0.0,
                index_size_mb=0.0,
                avg_row_length=0,
                fragmentation_percent=0.0,
                last_analyzed=None
            )
            
        except Exception as e:
            logger.error(f"Failed to get metrics for table {table_name}: {e}")
            return TableMetrics(
                table_name=table_name,
                row_count=0,
                table_size_mb=0.0,
                index_size_mb=0.0,
                avg_row_length=0,
                fragmentation_percent=0.0,
                last_analyzed=None
            )
    
    async def _check_performance_alerts(self, metrics: DatabaseMetrics) -> None:
        """Check metrics against thresholds and generate alerts."""
        alerts = []
        
        # Check connection utilization
        pool_utilization = metrics.connections_active / self.settings.db_pool_size
        if pool_utilization > self.thresholds['connection_utilization']:
            alerts.append(PerformanceAlert(
                alert_type='connection_pool',
                severity='HIGH' if pool_utilization > 0.9 else 'MEDIUM',
                message=f'Connection pool utilization at {pool_utilization:.1%}',
                metric_value=pool_utilization,
                threshold=self.thresholds['connection_utilization'],
                timestamp=datetime.now(timezone.utc),
                suggested_actions=['Increase connection pool size', 'Optimize query performance']
            ))
        
        # Check cache hit rate
        if metrics.cache_hit_rate < self.thresholds['cache_hit_rate_min']:
            alerts.append(PerformanceAlert(
                alert_type='cache_performance',
                severity='MEDIUM',
                message=f'Cache hit rate at {metrics.cache_hit_rate:.1%}',
                metric_value=metrics.cache_hit_rate,
                threshold=self.thresholds['cache_hit_rate_min'],
                timestamp=datetime.now(timezone.utc),
                suggested_actions=['Review caching strategy', 'Increase cache TTL', 'Warm frequently accessed data']
            ))
        
        # Check slow queries
        if metrics.slow_queries_count > 10:
            alerts.append(PerformanceAlert(
                alert_type='slow_queries',
                severity='HIGH' if metrics.slow_queries_count > 50 else 'MEDIUM',
                message=f'{metrics.slow_queries_count} slow queries detected',
                metric_value=metrics.slow_queries_count,
                threshold=10,
                timestamp=datetime.now(timezone.utc),
                suggested_actions=['Optimize slow queries', 'Add missing indexes', 'Review query patterns']
            ))
        
        # Add new alerts to active list
        self.active_alerts.extend(alerts)
    
    def _generate_query_optimizations(self, stats: Dict[str, Any]) -> List[str]:
        """Generate optimization suggestions for query stats."""
        suggestions = []
        
        if stats['avg_execution_time'] > 1.0:
            suggestions.append("Consider adding indexes for frequently filtered columns")
        
        if stats['max_execution_time'] > 5.0:
            suggestions.append("Review query for potential optimization opportunities")
        
        if stats['cache_hit_rate'] < 0.8:
            suggestions.append("Increase cache TTL or improve cache warming strategy")
        
        return suggestions
    
    def _calculate_performance_trends(self) -> Dict[str, Any]:
        """Calculate performance trends from historical data."""
        if len(self.metrics_history) < 2:
            return {'status': 'insufficient_data'}
        
        recent = self.metrics_history[-10:]  # Last 10 measurements
        older = self.metrics_history[-20:-10] if len(self.metrics_history) >= 20 else self.metrics_history[:-10]
        
        if not older:
            return {'status': 'insufficient_data'}
        
        def avg_metric(metrics_list, attr):
            return sum(getattr(m, attr) for m in metrics_list) / len(metrics_list)
        
        trends = {}
        for attr in ['queries_per_second', 'avg_query_time', 'cache_hit_rate', 'connections_active']:
            recent_avg = avg_metric(recent, attr)
            older_avg = avg_metric(older, attr)
            
            if older_avg > 0:
                change_percent = ((recent_avg - older_avg) / older_avg) * 100
                trends[attr] = {
                    'recent_avg': recent_avg,
                    'older_avg': older_avg,
                    'change_percent': change_percent,
                    'trend': 'improving' if change_percent < 0 and attr == 'avg_query_time' else 
                            'improving' if change_percent > 0 and attr in ['cache_hit_rate', 'queries_per_second'] else
                            'degrading' if abs(change_percent) > 5 else 'stable'
                }
        
        return trends
    
    def _calculate_overall_health(self) -> str:
        """Calculate overall database health score."""
        if not self.metrics_history:
            return 'unknown'
        
        recent_metrics = self.metrics_history[-5:] if len(self.metrics_history) >= 5 else self.metrics_history
        
        # Score based on various factors
        score = 100
        
        for metrics in recent_metrics:
            # Connection utilization penalty
            pool_util = metrics.connections_active / self.settings.db_pool_size
            if pool_util > 0.9:
                score -= 20
            elif pool_util > 0.8:
                score -= 10
            
            # Query performance penalty
            if metrics.avg_query_time > 1.0:
                score -= 15
            elif metrics.avg_query_time > 0.5:
                score -= 5
            
            # Cache hit rate penalty
            if metrics.cache_hit_rate < 0.8:
                score -= 10
            elif metrics.cache_hit_rate < 0.9:
                score -= 5
            
            # Slow queries penalty
            if metrics.slow_queries_count > 20:
                score -= 15
            elif metrics.slow_queries_count > 10:
                score -= 5
        
        # Average the score
        score = score / len(recent_metrics)
        
        if score >= 90:
            return 'excellent'
        elif score >= 80:
            return 'good'
        elif score >= 70:
            return 'fair'
        elif score >= 60:
            return 'poor'
        else:
            return 'critical'


# Global database monitoring service instance
db_monitoring_service = DatabaseMonitoringService()
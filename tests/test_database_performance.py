"""
Performance tests for database operations and optimization.

This module tests database query performance, connection pooling,
and optimization effectiveness under various load conditions.
"""

import pytest
import asyncio
import time
import random
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from unittest.mock import Mock, patch, AsyncMock

from src.services.database_optimization import db_optimization_service, QueryPerformanceMetrics
from src.services.database_monitoring import db_monitoring_service, DatabaseMetrics
from src.database.models import AuthorizationRequestDB, AuthorizationDecisionDB, CoveragePolicyDB
from src.models.enums import RequestStatus, DecisionStatus


class TestDatabaseOptimization:
    """Test database optimization service performance."""
    
    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        """Setup mocks for database operations."""
        with patch('src.services.database_optimization.get_session') as mock_session:
            # Mock session context manager
            mock_session_instance = Mock()
            mock_session_instance.__enter__ = Mock(return_value=mock_session_instance)
            mock_session_instance.__exit__ = Mock(return_value=None)
            mock_session.return_value = mock_session_instance
            
            # Mock query results with proper return values
            mock_session_instance.query.return_value.filter.return_value.count.return_value = 100
            
            # Create mock request objects
            mock_requests = [Mock() for _ in range(10)]
            mock_session_instance.query.return_value.filter.return_value.options.return_value.order_by.return_value.limit.return_value.offset.return_value.all.return_value = mock_requests
            mock_session_instance.query.return_value.filter.return_value.all.return_value = mock_requests
            mock_session_instance.query.return_value.all.return_value = mock_requests
            
            yield mock_session_instance
    
    @pytest.mark.asyncio
    async def test_optimized_provider_requests_performance(self, setup_mocks):
        """Test performance of optimized provider request queries."""
        provider_id = "provider_123"
        
        # Test query performance
        start_time = time.time()
        
        requests, total_count = await db_optimization_service.get_requests_by_provider_optimized(
            provider_id=provider_id,
            status=RequestStatus.SUBMITTED.value,
            limit=50,
            offset=0,
            use_cache=False  # Test raw database performance
        )
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Verify performance requirements
        assert execution_time < 0.5, f"Provider request query took {execution_time:.3f}s, should be < 0.5s"
        assert total_count == 100  # Mocked count
        
        # Verify metrics were recorded
        assert len(db_optimization_service.query_metrics) > 0
        latest_metric = db_optimization_service.query_metrics[-1]
        assert latest_metric.query_type == "get_requests_by_provider"
        assert latest_metric.execution_time == execution_time
    
    @pytest.mark.asyncio
    async def test_concurrent_database_queries(self, setup_mocks):
        """Test database performance under concurrent load."""
        num_concurrent_queries = 20
        
        async def run_query(query_id: int):
            """Run a single query with unique parameters."""
            return await db_optimization_service.get_requests_by_provider_optimized(
                provider_id=f"provider_{query_id}",
                status=RequestStatus.SUBMITTED.value,
                limit=25,
                use_cache=False
            )
        
        # Execute concurrent queries
        start_time = time.time()
        
        tasks = [run_query(i) for i in range(num_concurrent_queries)]
        results = await asyncio.gather(*tasks)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Verify concurrent performance
        assert total_time < 2.0, f"20 concurrent queries took {total_time:.3f}s, should be < 2s"
        assert len(results) == num_concurrent_queries
        
        # Verify all queries completed successfully
        for requests, count in results:
            assert count == 100  # Mocked count
    
    @pytest.mark.asyncio
    async def test_policy_query_optimization(self, setup_mocks):
        """Test optimized policy query performance."""
        procedure_code = "70551"  # MRI brain
        payer_id = "payer_123"
        
        # Mock policy results
        setup_mocks.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            Mock(spec=CoveragePolicyDB) for _ in range(5)
        ]
        
        start_time = time.time()
        
        policies = await db_optimization_service.get_active_policies_by_procedure_optimized(
            procedure_code=procedure_code,
            payer_id=payer_id,
            use_cache=False
        )
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Verify performance
        assert execution_time < 0.3, f"Policy query took {execution_time:.3f}s, should be < 0.3s"
        assert len(policies) == 5
        
        # Verify query metrics
        policy_metrics = [
            m for m in db_optimization_service.query_metrics 
            if m.query_type == "get_active_policies_by_procedure"
        ]
        assert len(policy_metrics) > 0
    
    @pytest.mark.asyncio
    async def test_batch_operations_performance(self, setup_mocks):
        """Test batch operation performance."""
        request_ids = [f"req_{i}" for i in range(100)]
        new_status = RequestStatus.APPROVED.value
        
        # Mock batch update result
        mock_result = Mock()
        mock_result.rowcount = len(request_ids)
        setup_mocks.execute.return_value = mock_result
        
        start_time = time.time()
        
        rows_updated = await db_optimization_service.batch_update_request_status(
            request_ids=request_ids,
            new_status=new_status
        )
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Verify batch performance
        assert execution_time < 1.0, f"Batch update took {execution_time:.3f}s, should be < 1s"
        assert rows_updated == 100
        
        # Verify batch operation was recorded
        batch_metrics = [
            m for m in db_optimization_service.query_metrics 
            if m.query_type == "batch_update_request_status"
        ]
        assert len(batch_metrics) > 0
        assert batch_metrics[-1].rows_affected == 100
    
    @pytest.mark.asyncio
    async def test_cache_integration_performance(self, setup_mocks):
        """Test performance improvement with caching enabled."""
        provider_id = "provider_cache_test"
        
        # Mock cache operations
        with patch.object(db_optimization_service.cache, 'get') as mock_cache_get, \
             patch.object(db_optimization_service.cache, 'set') as mock_cache_set:
            
            # First call - cache miss
            mock_cache_get.return_value = None
            mock_cache_set.return_value = True
            
            start_time = time.time()
            requests1, count1 = await db_optimization_service.get_requests_by_provider_optimized(
                provider_id=provider_id,
                use_cache=True
            )
            first_call_time = time.time() - start_time
            
            # Second call - cache hit
            mock_cache_get.return_value = {
                'requests': [],
                'total_count': 100
            }
            
            start_time = time.time()
            requests2, count2 = await db_optimization_service.get_requests_by_provider_optimized(
                provider_id=provider_id,
                use_cache=True
            )
            second_call_time = time.time() - start_time
            
            # Verify cache improves performance
            assert second_call_time < first_call_time, "Cache should improve query performance"
            assert second_call_time < 0.1, f"Cached query took {second_call_time:.3f}s, should be < 0.1s"
            assert count2 == 100
    
    def test_connection_pool_monitoring(self):
        """Test connection pool performance monitoring."""
        # Mock connection pool
        with patch.object(db_optimization_service.db_manager, 'engine') as mock_engine:
            mock_pool = Mock()
            mock_pool.size.return_value = 10
            mock_pool.checkedout.return_value = 5
            mock_pool.overflow.return_value = 2
            mock_pool.invalid.return_value = 0
            mock_engine.pool = mock_pool
            
            # Get pool status
            metrics = db_optimization_service.get_connection_pool_status()
            
            # Verify metrics
            assert metrics.pool_size == 10
            assert metrics.checked_out == 5
            assert metrics.overflow == 2
            assert metrics.invalid == 0
            
            # Test optimization recommendations
            recommendations = db_optimization_service.optimize_connection_pool()
            
            # Should recommend pool size increase due to 50% utilization + overflow
            assert "pool_size" in str(recommendations)
    
    def test_query_performance_analysis(self):
        """Test query performance statistics analysis."""
        # Add sample metrics
        sample_metrics = [
            QueryPerformanceMetrics(
                query_type="get_requests_by_provider",
                execution_time=0.5,
                rows_affected=50,
                cache_hit=False,
                timestamp=datetime.now(timezone.utc),
                query_hash="abc123"
            ),
            QueryPerformanceMetrics(
                query_type="get_requests_by_provider",
                execution_time=0.3,
                rows_affected=25,
                cache_hit=True,
                timestamp=datetime.now(timezone.utc),
                query_hash="def456"
            ),
            QueryPerformanceMetrics(
                query_type="get_active_policies_by_procedure",
                execution_time=0.8,
                rows_affected=10,
                cache_hit=False,
                timestamp=datetime.now(timezone.utc),
                query_hash="ghi789"
            )
        ]
        
        db_optimization_service.query_metrics.extend(sample_metrics)
        
        # Get performance stats
        stats = db_optimization_service.get_query_performance_stats(hours=24)
        
        # Verify analysis
        assert stats["total_queries"] == 3
        assert "by_query_type" in stats
        assert "get_requests_by_provider" in stats["by_query_type"]
        
        provider_stats = stats["by_query_type"]["get_requests_by_provider"]
        assert provider_stats["count"] == 2
        assert provider_stats["avg_execution_time"] == 0.4  # (0.5 + 0.3) / 2
        assert provider_stats["cache_hit_rate"] == 0.5  # 1 hit out of 2
        
        # Test slow query detection
        slow_queries = db_optimization_service.get_slow_queries(threshold_seconds=0.7)
        assert len(slow_queries) == 1
        assert slow_queries[0].query_type == "get_active_policies_by_procedure"


class TestDatabaseMonitoring:
    """Test database monitoring service performance."""
    
    @pytest.fixture(autouse=True)
    def setup_monitoring_mocks(self):
        """Setup mocks for monitoring operations."""
        with patch('src.services.database_monitoring.get_database_manager') as mock_db_manager:
            mock_manager = Mock()
            mock_session = Mock()
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=None)
            mock_manager.get_session.return_value = mock_session
            mock_manager.engine.dialect.name = 'mysql'
            mock_db_manager.return_value = mock_manager
            
            yield mock_session
    
    @pytest.mark.asyncio
    async def test_metrics_collection_performance(self, setup_monitoring_mocks):
        """Test database metrics collection performance."""
        # Mock database status queries
        setup_monitoring_mocks.execute.side_effect = [
            Mock(fetchone=Mock(return_value=('Threads_connected', '50'))),  # active connections
            Mock(fetchone=Mock(return_value=('Threads_running', '10'))),    # running queries
            Mock(fetchone=Mock(return_value=('Threads_connected', '50'))),  # total connections
            Mock(fetchone=Mock(return_value=('Questions', '10000'))),       # total questions
            Mock(fetchone=Mock(return_value=('Uptime', '3600'))),          # uptime
            Mock(fetchone=Mock(return_value=('Innodb_buffer_pool_bytes_data', str(100 * 1024 * 1024)))),  # memory
            Mock(fetchone=Mock(return_value=(500.0,))),  # disk usage
        ]
        
        start_time = time.time()
        
        metrics = await db_monitoring_service.collect_database_metrics()
        
        end_time = time.time()
        collection_time = end_time - start_time
        
        # Verify collection performance
        assert collection_time < 1.0, f"Metrics collection took {collection_time:.3f}s, should be < 1s"
        
        # Verify metrics structure
        assert isinstance(metrics, DatabaseMetrics)
        assert metrics.connections_active == 50
        assert metrics.connections_idle == 40  # 50 - 10
        assert metrics.queries_per_second == 10000 / 3600  # questions / uptime
        assert metrics.memory_usage_mb == 100.0
        assert metrics.disk_usage_mb == 500.0
    
    @pytest.mark.asyncio
    async def test_table_analysis_performance(self, setup_monitoring_mocks):
        """Test table performance analysis."""
        # Mock table statistics queries
        setup_monitoring_mocks.execute.return_value.fetchone.return_value = (
            1000,    # table_rows
            50.5,    # table_size_mb
            10.2,    # index_size_mb
            512,     # avg_row_length
            5.5      # fragmentation
        )
        
        start_time = time.time()
        
        table_metrics = await db_monitoring_service.analyze_table_performance()
        
        end_time = time.time()
        analysis_time = end_time - start_time
        
        # Verify analysis performance
        assert analysis_time < 2.0, f"Table analysis took {analysis_time:.3f}s, should be < 2s"
        
        # Verify metrics for expected tables
        expected_tables = ['authorization_requests', 'authorization_decisions', 'coverage_policies']
        assert len(table_metrics) == len(expected_tables)
        
        for table_name in expected_tables:
            assert table_name in table_metrics
            metrics = table_metrics[table_name]
            assert metrics.row_count == 1000
            assert metrics.table_size_mb == 50.5
            assert metrics.fragmentation_percent == 5.5
    
    @pytest.mark.asyncio
    async def test_performance_report_generation(self, setup_monitoring_mocks):
        """Test comprehensive performance report generation."""
        # Setup mock data
        setup_monitoring_mocks.execute.side_effect = [
            Mock(fetchone=Mock(return_value=('Threads_connected', '25'))),
            Mock(fetchone=Mock(return_value=('Threads_running', '5'))),
            Mock(fetchone=Mock(return_value=('Threads_connected', '25'))),
            Mock(fetchone=Mock(return_value=('Questions', '5000'))),
            Mock(fetchone=Mock(return_value=('Uptime', '1800'))),
            Mock(fetchone=Mock(return_value=('Innodb_buffer_pool_bytes_data', str(50 * 1024 * 1024)))),
            Mock(fetchone=Mock(return_value=(250.0,))),
        ]
        
        # Mock table metrics for multiple calls
        table_stats = (500, 25.0, 5.0, 256, 2.0)
        setup_monitoring_mocks.execute.return_value.fetchone.return_value = table_stats
        
        start_time = time.time()
        
        report = await db_monitoring_service.generate_performance_report()
        
        end_time = time.time()
        report_time = end_time - start_time
        
        # Verify report generation performance
        assert report_time < 5.0, f"Report generation took {report_time:.3f}s, should be < 5s"
        
        # Verify report structure
        assert 'generated_at' in report
        assert 'current_metrics' in report
        assert 'table_metrics' in report
        assert 'query_analysis' in report
        assert 'recommendations' in report
        assert 'active_alerts' in report
        assert 'performance_trends' in report
        assert 'summary' in report
        
        # Verify summary contains health assessment
        summary = report['summary']
        assert 'overall_health' in summary
        assert 'critical_issues' in summary
        assert 'total_recommendations' in summary
    
    @pytest.mark.asyncio
    async def test_alert_generation_performance(self, setup_monitoring_mocks):
        """Test performance alert generation."""
        # Create metrics that should trigger alerts
        high_utilization_metrics = DatabaseMetrics(
            timestamp=datetime.now(timezone.utc),
            connections_active=45,  # High utilization (90% of 50)
            connections_idle=5,
            queries_per_second=1200,  # Above threshold
            avg_query_time=0.8,  # Above threshold
            slow_queries_count=25,  # Above threshold
            cache_hit_rate=0.75,  # Below threshold
            disk_usage_mb=800,
            memory_usage_mb=200
        )
        
        # Mock settings
        with patch.object(db_monitoring_service, 'settings') as mock_settings:
            mock_settings.db_pool_size = 50
            
            start_time = time.time()
            
            await db_monitoring_service._check_performance_alerts(high_utilization_metrics)
            
            end_time = time.time()
            alert_time = end_time - start_time
            
            # Verify alert generation performance
            assert alert_time < 0.1, f"Alert generation took {alert_time:.3f}s, should be < 0.1s"
            
            # Verify alerts were generated
            active_alerts = await db_monitoring_service.get_active_alerts()
            assert len(active_alerts) > 0
            
            # Check for expected alert types
            alert_types = [alert.alert_type for alert in active_alerts]
            assert 'connection_pool' in alert_types
            assert 'cache_performance' in alert_types
            assert 'slow_queries' in alert_types
    
    def test_performance_trends_calculation(self):
        """Test performance trends calculation."""
        # Add historical metrics
        base_time = datetime.now(timezone.utc) - timedelta(hours=2)
        
        # Older metrics (worse performance)
        for i in range(10):
            metrics = DatabaseMetrics(
                timestamp=base_time + timedelta(minutes=i * 5),
                connections_active=30,
                connections_idle=20,
                queries_per_second=800,
                avg_query_time=0.8,
                slow_queries_count=15,
                cache_hit_rate=0.75,
                disk_usage_mb=400,
                memory_usage_mb=150
            )
            db_monitoring_service.metrics_history.append(metrics)
        
        # Recent metrics (better performance)
        for i in range(10):
            metrics = DatabaseMetrics(
                timestamp=base_time + timedelta(hours=1, minutes=i * 5),
                connections_active=20,
                connections_idle=30,
                queries_per_second=1000,
                avg_query_time=0.4,
                slow_queries_count=5,
                cache_hit_rate=0.90,
                disk_usage_mb=400,
                memory_usage_mb=150
            )
            db_monitoring_service.metrics_history.append(metrics)
        
        # Calculate trends
        trends = db_monitoring_service._calculate_performance_trends()
        
        # Verify trend analysis
        assert trends['avg_query_time']['trend'] == 'improving'  # Lower is better
        assert trends['cache_hit_rate']['trend'] == 'improving'  # Higher is better
        assert trends['queries_per_second']['trend'] == 'improving'  # Higher is better
        
        # Verify trend calculations
        assert trends['avg_query_time']['change_percent'] < 0  # Decreased (improved)
        assert trends['cache_hit_rate']['change_percent'] > 0  # Increased (improved)
    
    def test_health_score_calculation(self):
        """Test overall health score calculation."""
        # Add metrics for health calculation
        good_metrics = DatabaseMetrics(
            timestamp=datetime.now(timezone.utc),
            connections_active=20,  # Low utilization
            connections_idle=30,
            queries_per_second=500,
            avg_query_time=0.2,  # Fast queries
            slow_queries_count=2,  # Few slow queries
            cache_hit_rate=0.95,  # High cache hit rate
            disk_usage_mb=300,
            memory_usage_mb=100
        )
        
        db_monitoring_service.metrics_history = [good_metrics]
        
        with patch.object(db_monitoring_service, 'settings') as mock_settings:
            mock_settings.db_pool_size = 50
            
            health = db_monitoring_service._calculate_overall_health()
            
            # Should be excellent health
            assert health == 'excellent'
        
        # Test poor health metrics
        poor_metrics = DatabaseMetrics(
            timestamp=datetime.now(timezone.utc),
            connections_active=48,  # Very high utilization
            connections_idle=2,
            queries_per_second=1500,
            avg_query_time=2.0,  # Very slow queries
            slow_queries_count=50,  # Many slow queries
            cache_hit_rate=0.60,  # Low cache hit rate
            disk_usage_mb=800,
            memory_usage_mb=400
        )
        
        db_monitoring_service.metrics_history = [poor_metrics]
        
        health = db_monitoring_service._calculate_overall_health()
        
        # Should be poor or critical health
        assert health in ['poor', 'critical']
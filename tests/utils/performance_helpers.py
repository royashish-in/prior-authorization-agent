"""
Performance optimization helpers for test execution.

This module provides utilities for optimizing test performance,
including efficient fixtures, in-memory databases, and fast mocks.
"""

import asyncio
import time
import sqlite3
import threading
from contextlib import contextmanager
from typing import Dict, Any, List, Optional, Callable, Generator
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool, QueuePool

from tests.utils.async_test_config import async_test_config


class PerformanceOptimizedFixtures:
    """High-performance test fixtures optimized for speed."""
    
    def __init__(self):
        self._in_memory_engines = {}
        self._session_pools = {}
        self._mock_cache = {}
        self._fixture_cache = {}
        self._cleanup_callbacks = []
    
    def get_fast_database_engine(self, test_id: str = "default") -> Engine:
        """Get or create a fast in-memory database engine."""
        if test_id not in self._in_memory_engines:
            # Use in-memory SQLite with optimizations for speed
            engine = create_engine(
                "sqlite:///:memory:",
                poolclass=StaticPool,
                connect_args={
                    "check_same_thread": False,
                    "timeout": 1.0  # Fast timeout
                },
                echo=False,  # No SQL logging for performance
                future=True,
                pool_pre_ping=False,  # Skip connection validation
                pool_recycle=-1  # No connection recycling
            )
            
            # Configure SQLite for maximum performance
            @event.listens_for(engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                # Performance optimizations
                cursor.execute("PRAGMA synchronous=OFF")  # Disable fsync
                cursor.execute("PRAGMA journal_mode=MEMORY")  # In-memory journal
                cursor.execute("PRAGMA cache_size=10000")  # Large cache
                cursor.execute("PRAGMA temp_store=MEMORY")  # Memory temp storage
                cursor.execute("PRAGMA mmap_size=268435456")  # 256MB mmap
                cursor.execute("PRAGMA page_size=4096")  # Optimal page size
                cursor.execute("PRAGMA foreign_keys=OFF")  # Disable FK checks for speed
                cursor.close()
            
            self._in_memory_engines[test_id] = engine
        
        return self._in_memory_engines[test_id]
    
    def get_fast_session_factory(self, test_id: str = "default") -> sessionmaker:
        """Get or create a fast session factory."""
        if test_id not in self._session_pools:
            engine = self.get_fast_database_engine(test_id)
            self._session_pools[test_id] = sessionmaker(
                bind=engine,
                autoflush=False,  # Manual flushing for control
                expire_on_commit=False  # Keep objects after commit
            )
        
        return self._session_pools[test_id]
    
    @contextmanager
    def fast_database_session(self, test_id: str = "default") -> Generator[Session, None, None]:
        """Context manager for fast database sessions."""
        session_factory = self.get_fast_session_factory(test_id)
        session = session_factory()
        
        try:
            yield session
        finally:
            session.close()
    
    def create_optimized_mock(self, mock_type: str, **kwargs) -> Mock:
        """Create optimized mocks with caching."""
        cache_key = f"{mock_type}_{hash(frozenset(kwargs.items()))}"
        
        if cache_key in self._mock_cache:
            return self._mock_cache[cache_key]
        
        if mock_type == "database_session":
            mock = self._create_fast_database_mock(**kwargs)
        elif mock_type == "external_service":
            mock = self._create_fast_external_service_mock(**kwargs)
        elif mock_type == "async_client":
            mock = self._create_fast_async_client_mock(**kwargs)
        elif mock_type == "llm_service":
            mock = self._create_fast_llm_service_mock(**kwargs)
        else:
            mock = MagicMock(**kwargs)
        
        self._mock_cache[cache_key] = mock
        return mock
    
    def _create_fast_database_mock(self, **kwargs) -> Mock:
        """Create a fast database session mock."""
        mock_session = Mock()
        
        # Pre-configure common methods for speed
        mock_session.add = Mock()
        mock_session.commit = Mock()
        mock_session.rollback = Mock()
        mock_session.close = Mock()
        mock_session.flush = Mock()
        mock_session.refresh = Mock()
        mock_session.merge = Mock()
        mock_session.delete = Mock()
        
        # Fast query mock
        mock_query = Mock()
        mock_query.filter = Mock(return_value=mock_query)
        mock_query.filter_by = Mock(return_value=mock_query)
        mock_query.order_by = Mock(return_value=mock_query)
        mock_query.limit = Mock(return_value=mock_query)
        mock_query.offset = Mock(return_value=mock_query)
        mock_query.first = Mock(return_value=None)
        mock_query.all = Mock(return_value=[])
        mock_query.count = Mock(return_value=0)
        
        mock_session.query = Mock(return_value=mock_query)
        mock_session.execute = Mock(return_value=Mock(fetchall=Mock(return_value=[])))
        
        # Context manager support
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=None)
        
        return mock_session
    
    def _create_fast_external_service_mock(self, **kwargs) -> Mock:
        """Create a fast external service mock."""
        mock_service = Mock()
        
        # Pre-configure common responses
        mock_service.get = Mock(return_value={"status": "success"})
        mock_service.post = Mock(return_value={"created": True})
        mock_service.put = Mock(return_value={"updated": True})
        mock_service.delete = Mock(return_value={"deleted": True})
        mock_service.is_available = Mock(return_value=True)
        mock_service.health_check = Mock(return_value={"healthy": True})
        
        return mock_service
    
    def _create_fast_async_client_mock(self, **kwargs) -> AsyncMock:
        """Create a fast async client mock."""
        mock_client = AsyncMock()
        
        # Pre-configure async methods with minimal delay
        async def fast_response(*args, **kwargs):
            return {"status": "success", "data": {}}
        
        mock_client.get = AsyncMock(side_effect=fast_response)
        mock_client.post = AsyncMock(side_effect=fast_response)
        mock_client.put = AsyncMock(side_effect=fast_response)
        mock_client.delete = AsyncMock(side_effect=fast_response)
        mock_client.aclose = AsyncMock()
        
        return mock_client
    
    def _create_fast_llm_service_mock(self, **kwargs) -> AsyncMock:
        """Create a fast LLM service mock."""
        mock_llm = AsyncMock()
        
        # Pre-configured fast responses
        async def fast_decision(*args, **kwargs):
            return {
                "decision": "approved",
                "confidence": 0.95,
                "reasoning": ["Fast mock reasoning"],
                "processing_time_ms": 1.0
            }
        
        mock_llm.generate_decision = AsyncMock(side_effect=fast_decision)
        mock_llm.is_available = Mock(return_value=True)
        mock_llm.initialize = AsyncMock()
        mock_llm.cleanup = AsyncMock()
        
        return mock_llm
    
    def create_bulk_test_data(self, count: int = 100) -> List[Dict[str, Any]]:
        """Create bulk test data efficiently."""
        cache_key = f"bulk_data_{count}"
        
        if cache_key in self._fixture_cache:
            return self._fixture_cache[cache_key]
        
        # Generate test data efficiently
        test_data = []
        for i in range(count):
            test_data.append({
                "id": i,
                "request_id": f"req_perf_{i:06d}",
                "provider_id": f"prov_{i % 10}",
                "patient_id": f"pat_{i % 50}",
                "diagnosis_code": f"M25.{(i % 999):03d}",
                "procedure_code": f"7{(i % 9999):04d}",
                "status": "submitted",
                "created_at": time.time() - (i * 60)  # Stagger timestamps
            })
        
        self._fixture_cache[cache_key] = test_data
        return test_data
    
    def register_cleanup(self, callback: Callable):
        """Register a cleanup callback."""
        self._cleanup_callbacks.append(callback)
    
    def cleanup_all(self):
        """Clean up all performance fixtures."""
        # Run cleanup callbacks
        for callback in self._cleanup_callbacks:
            try:
                callback()
            except Exception:
                pass  # Ignore cleanup errors for performance
        
        # Dispose engines
        for engine in self._in_memory_engines.values():
            try:
                engine.dispose()
            except Exception:
                pass
        
        # Clear caches
        self._in_memory_engines.clear()
        self._session_pools.clear()
        self._mock_cache.clear()
        self._fixture_cache.clear()
        self._cleanup_callbacks.clear()


class FastTestTimer:
    """Timer for measuring test performance."""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.duration = None
    
    def start(self):
        """Start timing."""
        self.start_time = time.perf_counter()
    
    def stop(self):
        """Stop timing and calculate duration."""
        self.end_time = time.perf_counter()
        if self.start_time:
            self.duration = self.end_time - self.start_time
        return self.duration
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class PerformanceTestMetrics:
    """Collect and analyze test performance metrics."""
    
    def __init__(self):
        self.test_times = {}
        self.slow_tests = []
        self.fast_tests = []
        self.total_tests = 0
        self.total_time = 0.0
    
    def record_test(self, test_name: str, duration: float, threshold: float = 1.0):
        """Record test execution time."""
        self.test_times[test_name] = duration
        self.total_tests += 1
        self.total_time += duration
        
        if duration > threshold:
            self.slow_tests.append((test_name, duration))
        else:
            self.fast_tests.append((test_name, duration))
    
    def get_summary(self) -> Dict[str, Any]:
        """Get performance summary."""
        if self.total_tests == 0:
            return {"error": "No tests recorded"}
        
        avg_time = self.total_time / self.total_tests
        slow_count = len(self.slow_tests)
        fast_count = len(self.fast_tests)
        
        return {
            "total_tests": self.total_tests,
            "total_time": round(self.total_time, 3),
            "average_time": round(avg_time, 3),
            "slow_tests": slow_count,
            "fast_tests": fast_count,
            "slowest_tests": sorted(self.slow_tests, key=lambda x: x[1], reverse=True)[:10],
            "fastest_tests": sorted(self.fast_tests, key=lambda x: x[1])[:10]
        }
    
    def identify_slow_tests(self, threshold: float = 1.0) -> List[tuple]:
        """Identify tests that exceed the time threshold."""
        return [(name, time) for name, time in self.test_times.items() if time > threshold]


# Global performance fixtures instance
_performance_fixtures = PerformanceOptimizedFixtures()
_performance_metrics = PerformanceTestMetrics()


def get_performance_fixtures() -> PerformanceOptimizedFixtures:
    """Get the global performance fixtures instance."""
    return _performance_fixtures


def get_performance_metrics() -> PerformanceTestMetrics:
    """Get the global performance metrics instance."""
    return _performance_metrics


# Pytest fixtures for performance optimization
@pytest.fixture(scope="function")
def fast_db_session():
    """Provide a fast in-memory database session."""
    with _performance_fixtures.fast_database_session() as session:
        yield session


@pytest.fixture(scope="function")
def optimized_mocks():
    """Provide optimized mocks for common services."""
    return {
        "database": _performance_fixtures.create_optimized_mock("database_session"),
        "external_service": _performance_fixtures.create_optimized_mock("external_service"),
        "async_client": _performance_fixtures.create_optimized_mock("async_client"),
        "llm_service": _performance_fixtures.create_optimized_mock("llm_service")
    }


@pytest.fixture(scope="function")
def bulk_test_data():
    """Provide bulk test data for performance testing."""
    return _performance_fixtures.create_bulk_test_data(100)


@pytest.fixture(scope="function")
def performance_timer():
    """Provide a performance timer."""
    return FastTestTimer()


@pytest.fixture(scope="session", autouse=True)
def cleanup_performance_fixtures():
    """Clean up performance fixtures after all tests."""
    yield
    _performance_fixtures.cleanup_all()


# Decorators for performance testing
def fast_test(timeout: float = 5.0):
    """Decorator for fast unit tests."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with FastTestTimer() as timer:
                result = func(*args, **kwargs)
            
            if timer.duration and timer.duration > timeout:
                pytest.fail(f"Test {func.__name__} took {timer.duration:.3f}s, expected < {timeout}s")
            
            _performance_metrics.record_test(func.__name__, timer.duration or 0.0, timeout)
            return result
        
        return wrapper
    return decorator


def async_fast_test(timeout: float = 5.0):
    """Decorator for fast async tests."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            
            try:
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
                duration = time.perf_counter() - start_time
                _performance_metrics.record_test(func.__name__, duration, timeout)
                return result
            except asyncio.TimeoutError:
                duration = time.perf_counter() - start_time
                pytest.fail(f"Async test {func.__name__} timed out after {duration:.3f}s")
        
        return wrapper
    return decorator


# Context managers for performance testing
@contextmanager
def performance_context(test_name: str, timeout: float = 30.0):
    """Context manager for performance testing."""
    start_time = time.perf_counter()
    
    try:
        yield
    finally:
        duration = time.perf_counter() - start_time
        _performance_metrics.record_test(test_name, duration, timeout)
        
        if duration > timeout:
            pytest.fail(f"Performance test '{test_name}' took {duration:.3f}s, expected < {timeout}s")


@contextmanager
def fast_mock_patches():
    """Context manager for fast mock patches."""
    patches = {
        'database': patch('src.database.connection.get_session'),
        'cache': patch('src.services.cache.CacheService'),
        'external': patch('src.services.external_services.ExternalServiceClient')
    }
    
    started_patches = {}
    try:
        for name, patch_obj in patches.items():
            mock_obj = patch_obj.start()
            
            # Configure fast mocks
            if name == 'database':
                mock_obj.return_value.__enter__ = Mock(
                    return_value=_performance_fixtures.create_optimized_mock("database_session")
                )
                mock_obj.return_value.__exit__ = Mock(return_value=None)
            elif name == 'cache':
                mock_obj.return_value = _performance_fixtures.create_optimized_mock("external_service")
            elif name == 'external':
                mock_obj.return_value = _performance_fixtures.create_optimized_mock("external_service")
            
            started_patches[name] = mock_obj
        
        yield started_patches
    
    finally:
        for patch_obj in patches.values():
            patch_obj.stop()


# Utility functions for performance optimization
def optimize_test_environment():
    """Optimize the test environment for performance."""
    # Configure async test settings for speed
    async_test_config.set_timeout('unit_test', 5.0)
    async_test_config.set_timeout('integration_test', 30.0)
    async_test_config.set_concurrency_limit('database_connections', 3)
    async_test_config.set_concurrency_limit('external_requests', 5)
    
    # Disable debug mode for performance
    async_test_config.debug_mode = False
    async_test_config.strict_mode = False


def create_performance_report() -> Dict[str, Any]:
    """Create a performance report for all tests."""
    summary = _performance_metrics.get_summary()
    
    # Add recommendations
    recommendations = []
    
    if summary.get("slow_tests", 0) > 0:
        recommendations.append("Consider optimizing slow tests or using faster mocks")
    
    if summary.get("average_time", 0) > 0.5:
        recommendations.append("Average test time is high - consider performance optimizations")
    
    slow_tests = summary.get("slowest_tests", [])
    if slow_tests:
        recommendations.append(f"Focus on optimizing: {', '.join([test[0] for test in slow_tests[:3]])}")
    
    summary["recommendations"] = recommendations
    return summary


# Memory optimization utilities
class MemoryOptimizer:
    """Utilities for optimizing memory usage in tests."""
    
    @staticmethod
    def clear_caches():
        """Clear all test caches to free memory."""
        _performance_fixtures._mock_cache.clear()
        _performance_fixtures._fixture_cache.clear()
    
    @staticmethod
    def optimize_garbage_collection():
        """Optimize garbage collection for tests."""
        import gc
        gc.collect()
        gc.set_threshold(700, 10, 10)  # More aggressive GC
    
    @staticmethod
    @contextmanager
    def memory_limit(limit_mb: int = 100):
        """Context manager to monitor memory usage."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        start_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        try:
            yield
        finally:
            end_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_used = end_memory - start_memory
            
            if memory_used > limit_mb:
                pytest.fail(f"Test used {memory_used:.1f}MB, limit was {limit_mb}MB")


# Export commonly used performance utilities
memory_optimizer = MemoryOptimizer()
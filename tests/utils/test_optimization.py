"""
Test execution optimization utilities.

This module provides utilities for optimizing test execution performance,
including fixture caching, parallel execution support, and resource management.
"""

import asyncio
import time
import threading
import multiprocessing
from contextlib import contextmanager
from typing import Dict, Any, List, Optional, Callable, Generator, Union
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import pytest
import logging
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from functools import wraps, lru_cache

logger = logging.getLogger(__name__)


class TestExecutionOptimizer:
    """Optimizes test execution for speed and reliability."""
    
    def __init__(self):
        self.fixture_cache = {}
        self.mock_cache = {}
        self.resource_pools = {}
        self.cleanup_callbacks = []
        self.performance_metrics = {}
        self._thread_pool = None
        self._process_pool = None
        self._lock = threading.Lock()
    
    @property
    def thread_pool(self) -> ThreadPoolExecutor:
        """Get or create thread pool for parallel execution."""
        if self._thread_pool is None:
            max_workers = min(4, multiprocessing.cpu_count())
            self._thread_pool = ThreadPoolExecutor(max_workers=max_workers)
            self.register_cleanup(self._thread_pool.shutdown)
        return self._thread_pool
    
    @property
    def process_pool(self) -> ProcessPoolExecutor:
        """Get or create process pool for CPU-intensive tests."""
        if self._process_pool is None:
            max_workers = min(2, multiprocessing.cpu_count())
            self._process_pool = ProcessPoolExecutor(max_workers=max_workers)
            self.register_cleanup(self._process_pool.shutdown)
        return self._process_pool
    
    def optimize_fixture_setup(self, fixture_name: str, setup_func: Callable, 
                             cache_key: Optional[str] = None) -> Any:
        """Optimize fixture setup with caching."""
        cache_key = cache_key or fixture_name
        
        with self._lock:
            if cache_key in self.fixture_cache:
                logger.debug(f"Using cached fixture: {fixture_name}")
                return self.fixture_cache[cache_key]
            
            start_time = time.perf_counter()
            fixture_value = setup_func()
            setup_time = time.perf_counter() - start_time
            
            self.fixture_cache[cache_key] = fixture_value
            self.performance_metrics[f"fixture_setup_{fixture_name}"] = setup_time
            
            logger.debug(f"Created fixture {fixture_name} in {setup_time:.3f}s")
            return fixture_value
    
    def create_optimized_mock(self, mock_type: str, **kwargs) -> Union[Mock, AsyncMock]:
        """Create optimized mocks with performance enhancements."""
        cache_key = f"{mock_type}_{hash(frozenset(kwargs.items()))}"
        
        if cache_key in self.mock_cache:
            return self.mock_cache[cache_key]
        
        if mock_type == "fast_database":
            mock = self._create_fast_database_mock(**kwargs)
        elif mock_type == "fast_external_service":
            mock = self._create_fast_external_service_mock(**kwargs)
        elif mock_type == "fast_async_client":
            mock = self._create_fast_async_client_mock(**kwargs)
        elif mock_type == "fast_llm_service":
            mock = self._create_fast_llm_service_mock(**kwargs)
        elif mock_type == "fast_file_system":
            mock = self._create_fast_file_system_mock(**kwargs)
        else:
            mock = MagicMock(**kwargs)
        
        self.mock_cache[cache_key] = mock
        return mock
    
    def _create_fast_database_mock(self, **kwargs) -> Mock:
        """Create a high-performance database mock."""
        mock_session = Mock()
        
        # Pre-configure all common database operations
        mock_session.add = Mock()
        mock_session.commit = Mock()
        mock_session.rollback = Mock()
        mock_session.close = Mock()
        mock_session.flush = Mock()
        mock_session.refresh = Mock()
        mock_session.merge = Mock()
        mock_session.delete = Mock()
        mock_session.execute = Mock(return_value=Mock(fetchall=Mock(return_value=[])))
        
        # Fast query mock with method chaining
        mock_query = Mock()
        for method in ['filter', 'filter_by', 'order_by', 'limit', 'offset', 'join', 'outerjoin']:
            setattr(mock_query, method, Mock(return_value=mock_query))
        
        mock_query.first = Mock(return_value=None)
        mock_query.all = Mock(return_value=[])
        mock_query.count = Mock(return_value=0)
        mock_query.one = Mock(return_value=None)
        mock_query.one_or_none = Mock(return_value=None)
        mock_query.scalar = Mock(return_value=None)
        
        mock_session.query = Mock(return_value=mock_query)
        
        # Context manager support
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=None)
        
        return mock_session
    
    def _create_fast_external_service_mock(self, **kwargs) -> Mock:
        """Create a high-performance external service mock."""
        mock_service = Mock()
        
        # Pre-configure HTTP methods with realistic responses
        mock_service.get = Mock(return_value={"status": "success", "data": {}})
        mock_service.post = Mock(return_value={"status": "created", "id": "test_id"})
        mock_service.put = Mock(return_value={"status": "updated"})
        mock_service.delete = Mock(return_value={"status": "deleted"})
        mock_service.patch = Mock(return_value={"status": "patched"})
        
        # Health and availability checks
        mock_service.is_available = Mock(return_value=True)
        mock_service.health_check = Mock(return_value={"healthy": True, "response_time": 0.001})
        
        # Authentication and rate limiting
        mock_service.authenticate = Mock(return_value={"token": "test_token"})
        mock_service.check_rate_limit = Mock(return_value={"allowed": True, "remaining": 100})
        
        return mock_service
    
    def _create_fast_async_client_mock(self, **kwargs) -> AsyncMock:
        """Create a high-performance async client mock."""
        mock_client = AsyncMock()
        
        # Fast async responses with minimal delay
        async def fast_response(*args, **kwargs):
            await asyncio.sleep(0.001)  # Minimal delay for realism
            return {"status": "success", "data": {}, "response_time": 0.001}
        
        mock_client.get = AsyncMock(side_effect=fast_response)
        mock_client.post = AsyncMock(side_effect=fast_response)
        mock_client.put = AsyncMock(side_effect=fast_response)
        mock_client.delete = AsyncMock(side_effect=fast_response)
        mock_client.patch = AsyncMock(side_effect=fast_response)
        mock_client.aclose = AsyncMock()
        
        # Connection management
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.is_connected = Mock(return_value=True)
        
        return mock_client
    
    def _create_fast_llm_service_mock(self, **kwargs) -> AsyncMock:
        """Create a high-performance LLM service mock."""
        mock_llm = AsyncMock()
        
        # Fast decision generation
        async def fast_decision(*args, **kwargs):
            await asyncio.sleep(0.01)  # Minimal delay
            return {
                "decision": "approved",
                "confidence": 0.95,
                "reasoning": ["Mock reasoning for fast testing"],
                "processing_time_ms": 10.0,
                "model_used": "test_model"
            }
        
        async def fast_analysis(*args, **kwargs):
            await asyncio.sleep(0.005)
            return {
                "analysis": "Mock analysis result",
                "confidence": 0.90,
                "key_factors": ["factor1", "factor2"],
                "processing_time_ms": 5.0
            }
        
        mock_llm.generate_decision = AsyncMock(side_effect=fast_decision)
        mock_llm.analyze_request = AsyncMock(side_effect=fast_analysis)
        mock_llm.is_available = Mock(return_value=True)
        mock_llm.initialize = AsyncMock()
        mock_llm.cleanup = AsyncMock()
        mock_llm.health_check = AsyncMock(return_value={"healthy": True})
        
        return mock_llm
    
    def _create_fast_file_system_mock(self, **kwargs) -> Mock:
        """Create a high-performance file system mock."""
        mock_fs = Mock()
        
        # File operations
        mock_fs.read_file = Mock(return_value="mock file content")
        mock_fs.write_file = Mock(return_value=True)
        mock_fs.delete_file = Mock(return_value=True)
        mock_fs.exists = Mock(return_value=True)
        mock_fs.list_files = Mock(return_value=["file1.txt", "file2.txt"])
        
        # Directory operations
        mock_fs.create_directory = Mock(return_value=True)
        mock_fs.delete_directory = Mock(return_value=True)
        mock_fs.list_directories = Mock(return_value=["dir1", "dir2"])
        
        return mock_fs
    
    def run_parallel_tests(self, test_functions: List[Callable], 
                          max_workers: Optional[int] = None) -> List[Any]:
        """Run multiple test functions in parallel."""
        max_workers = max_workers or min(4, len(test_functions))
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(test_func) for test_func in test_functions]
            results = []
            
            for future in futures:
                try:
                    result = future.result(timeout=30.0)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Parallel test failed: {e}")
                    results.append(e)
            
            return results
    
    async def run_concurrent_async_tests(self, async_test_functions: List[Callable],
                                       max_concurrency: int = 10) -> List[Any]:
        """Run multiple async test functions concurrently."""
        semaphore = asyncio.Semaphore(max_concurrency)
        
        async def run_with_semaphore(test_func):
            async with semaphore:
                return await test_func()
        
        tasks = [asyncio.create_task(run_with_semaphore(test_func)) 
                for test_func in async_test_functions]
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results
        except Exception as e:
            logger.error(f"Concurrent async tests failed: {e}")
            # Cancel remaining tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
            raise
    
    def register_cleanup(self, cleanup_func: Callable):
        """Register a cleanup function."""
        self.cleanup_callbacks.append(cleanup_func)
    
    def cleanup_all(self):
        """Clean up all resources."""
        for callback in self.cleanup_callbacks:
            try:
                callback()
            except Exception as e:
                logger.warning(f"Cleanup callback failed: {e}")
        
        # Clean up thread and process pools
        if self._thread_pool:
            self._thread_pool.shutdown(wait=False)
            self._thread_pool = None
        
        if self._process_pool:
            self._process_pool.shutdown(wait=False)
            self._process_pool = None
        
        # Clear caches
        self.fixture_cache.clear()
        self.mock_cache.clear()
        self.resource_pools.clear()
        self.cleanup_callbacks.clear()
        self.performance_metrics.clear()
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Get performance metrics report."""
        return {
            "fixture_cache_size": len(self.fixture_cache),
            "mock_cache_size": len(self.mock_cache),
            "performance_metrics": self.performance_metrics.copy(),
            "active_pools": {
                "thread_pool": self._thread_pool is not None,
                "process_pool": self._process_pool is not None
            }
        }


class TestReliabilityEnhancer:
    """Enhances test reliability through retry mechanisms and error handling."""
    
    def __init__(self):
        self.retry_config = {
            "max_retries": 3,
            "base_delay": 0.1,
            "max_delay": 2.0,
            "exponential_base": 2.0
        }
        self.flaky_test_tracker = {}
        self.error_patterns = {}
    
    def reliable_test(self, max_retries: int = 3, retry_delay: float = 0.1):
        """Decorator for reliable test execution with retry logic."""
        def decorator(test_func):
            @wraps(test_func)
            def wrapper(*args, **kwargs):
                last_exception = None
                
                for attempt in range(max_retries + 1):
                    try:
                        return test_func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e
                        
                        # Track flaky test
                        test_name = test_func.__name__
                        if test_name not in self.flaky_test_tracker:
                            self.flaky_test_tracker[test_name] = 0
                        self.flaky_test_tracker[test_name] += 1
                        
                        if attempt < max_retries:
                            delay = retry_delay * (2 ** attempt)  # Exponential backoff
                            logger.warning(f"Test {test_name} failed on attempt {attempt + 1}, retrying in {delay}s: {e}")
                            time.sleep(delay)
                        else:
                            logger.error(f"Test {test_name} failed after {max_retries + 1} attempts")
                
                if last_exception:
                    raise last_exception
            
            return wrapper
        return decorator
    
    def reliable_async_test(self, max_retries: int = 3, retry_delay: float = 0.1):
        """Decorator for reliable async test execution with retry logic."""
        def decorator(test_func):
            @wraps(test_func)
            async def wrapper(*args, **kwargs):
                last_exception = None
                
                for attempt in range(max_retries + 1):
                    try:
                        return await test_func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e
                        
                        # Track flaky test
                        test_name = test_func.__name__
                        if test_name not in self.flaky_test_tracker:
                            self.flaky_test_tracker[test_name] = 0
                        self.flaky_test_tracker[test_name] += 1
                        
                        if attempt < max_retries:
                            delay = retry_delay * (2 ** attempt)
                            logger.warning(f"Async test {test_name} failed on attempt {attempt + 1}, retrying in {delay}s: {e}")
                            await asyncio.sleep(delay)
                        else:
                            logger.error(f"Async test {test_name} failed after {max_retries + 1} attempts")
                
                if last_exception:
                    raise last_exception
            
            return wrapper
        return decorator
    
    @contextmanager
    def error_handling_context(self, expected_errors: List[type] = None):
        """Context manager for enhanced error handling in tests."""
        expected_errors = expected_errors or []
        
        try:
            yield
        except Exception as e:
            error_type = type(e)
            error_message = str(e)
            
            # Track error patterns
            if error_type not in self.error_patterns:
                self.error_patterns[error_type] = []
            self.error_patterns[error_type].append(error_message)
            
            # Re-raise if not expected
            if error_type not in expected_errors:
                logger.error(f"Unexpected error in test: {error_type.__name__}: {error_message}")
                raise
            else:
                logger.debug(f"Expected error caught: {error_type.__name__}: {error_message}")
    
    def get_flaky_test_report(self) -> Dict[str, Any]:
        """Get report of flaky tests."""
        return {
            "flaky_tests": self.flaky_test_tracker.copy(),
            "error_patterns": {
                error_type.__name__: messages 
                for error_type, messages in self.error_patterns.items()
            },
            "total_flaky_tests": len(self.flaky_test_tracker),
            "most_flaky": max(self.flaky_test_tracker.items(), key=lambda x: x[1]) 
                         if self.flaky_test_tracker else None
        }


class TestResourceManager:
    """Manages test resources for optimal performance and cleanup."""
    
    def __init__(self):
        self.active_resources = {}
        self.resource_pools = {}
        self.cleanup_order = []
        self.resource_limits = {
            "database_connections": 5,
            "file_handles": 10,
            "network_connections": 8,
            "memory_mb": 100
        }
    
    def get_resource(self, resource_type: str, resource_id: str = None) -> Any:
        """Get or create a resource with pooling."""
        resource_id = resource_id or f"{resource_type}_default"
        
        if resource_id in self.active_resources:
            return self.active_resources[resource_id]
        
        # Check resource limits
        current_count = len([r for r in self.active_resources.keys() 
                           if r.startswith(resource_type)])
        limit = self.resource_limits.get(resource_type, 10)
        
        if current_count >= limit:
            # Clean up oldest resource of this type
            self._cleanup_oldest_resource(resource_type)
        
        # Create new resource
        resource = self._create_resource(resource_type, resource_id)
        self.active_resources[resource_id] = resource
        self.cleanup_order.append(resource_id)
        
        return resource
    
    def _create_resource(self, resource_type: str, resource_id: str) -> Any:
        """Create a new resource based on type."""
        if resource_type == "database_connection":
            return self._create_database_connection()
        elif resource_type == "file_handle":
            return self._create_file_handle()
        elif resource_type == "network_connection":
            return self._create_network_connection()
        else:
            return Mock(name=f"mock_{resource_type}_{resource_id}")
    
    def _create_database_connection(self) -> Mock:
        """Create a mock database connection."""
        connection = Mock()
        connection.execute = Mock(return_value=Mock(fetchall=Mock(return_value=[])))
        connection.commit = Mock()
        connection.rollback = Mock()
        connection.close = Mock()
        return connection
    
    def _create_file_handle(self) -> Mock:
        """Create a mock file handle."""
        file_handle = Mock()
        file_handle.read = Mock(return_value="mock file content")
        file_handle.write = Mock()
        file_handle.close = Mock()
        return file_handle
    
    def _create_network_connection(self) -> Mock:
        """Create a mock network connection."""
        connection = Mock()
        connection.send = Mock()
        connection.receive = Mock(return_value="mock response")
        connection.close = Mock()
        return connection
    
    def _cleanup_oldest_resource(self, resource_type: str):
        """Clean up the oldest resource of a specific type."""
        for resource_id in self.cleanup_order:
            if resource_id.startswith(resource_type):
                self.release_resource(resource_id)
                break
    
    def release_resource(self, resource_id: str):
        """Release a specific resource."""
        if resource_id in self.active_resources:
            resource = self.active_resources[resource_id]
            
            # Call cleanup method if available
            if hasattr(resource, 'close'):
                try:
                    resource.close()
                except Exception as e:
                    logger.warning(f"Error closing resource {resource_id}: {e}")
            
            del self.active_resources[resource_id]
            if resource_id in self.cleanup_order:
                self.cleanup_order.remove(resource_id)
    
    def cleanup_all_resources(self):
        """Clean up all active resources."""
        for resource_id in list(self.active_resources.keys()):
            self.release_resource(resource_id)
        
        self.active_resources.clear()
        self.cleanup_order.clear()
    
    def get_resource_stats(self) -> Dict[str, Any]:
        """Get resource usage statistics."""
        resource_counts = {}
        for resource_id in self.active_resources.keys():
            resource_type = resource_id.split('_')[0]
            resource_counts[resource_type] = resource_counts.get(resource_type, 0) + 1
        
        return {
            "active_resources": len(self.active_resources),
            "resource_counts": resource_counts,
            "resource_limits": self.resource_limits.copy(),
            "cleanup_order": self.cleanup_order.copy()
        }


# Global instances
test_optimizer = TestExecutionOptimizer()
reliability_enhancer = TestReliabilityEnhancer()
resource_manager = TestResourceManager()


# Pytest fixtures for optimization
@pytest.fixture(scope="function")
def optimized_test_environment():
    """Provide optimized test environment."""
    return test_optimizer


@pytest.fixture(scope="function")
def reliable_test_environment():
    """Provide reliable test environment."""
    return reliability_enhancer


@pytest.fixture(scope="function")
def test_resource_manager():
    """Provide test resource manager."""
    return resource_manager


@pytest.fixture(scope="function", autouse=True)
def cleanup_test_resources():
    """Auto-cleanup test resources after each test."""
    yield
    resource_manager.cleanup_all_resources()


# Decorators for test optimization
def fast_test(timeout: float = 5.0):
    """Decorator for fast unit tests with timeout."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            
            try:
                result = func(*args, **kwargs)
                duration = time.perf_counter() - start_time
                
                if duration > timeout:
                    pytest.fail(f"Test {func.__name__} took {duration:.3f}s, expected < {timeout}s")
                
                return result
            except Exception as e:
                duration = time.perf_counter() - start_time
                logger.error(f"Fast test {func.__name__} failed after {duration:.3f}s: {e}")
                raise
        
        return wrapper
    return decorator


def parallel_safe_test(func):
    """Decorator to mark tests as safe for parallel execution."""
    func._parallel_safe = True
    return func


def serial_test(func):
    """Decorator to mark tests that must run serially."""
    func._serial_required = True
    return func


# Context managers for test optimization
@contextmanager
def optimized_test_context():
    """Context manager for optimized test execution."""
    start_time = time.perf_counter()
    
    try:
        yield test_optimizer
    finally:
        duration = time.perf_counter() - start_time
        logger.debug(f"Test context completed in {duration:.3f}s")


@contextmanager
def resource_limited_context(resource_limits: Dict[str, int]):
    """Context manager for resource-limited test execution."""
    original_limits = resource_manager.resource_limits.copy()
    resource_manager.resource_limits.update(resource_limits)
    
    try:
        yield resource_manager
    finally:
        resource_manager.resource_limits = original_limits


# Utility functions
def is_parallel_safe(test_func) -> bool:
    """Check if a test function is marked as parallel safe."""
    return getattr(test_func, '_parallel_safe', False)


def requires_serial_execution(test_func) -> bool:
    """Check if a test function requires serial execution."""
    return getattr(test_func, '_serial_required', False)


def optimize_test_collection(test_items: List[Any]) -> Dict[str, List[Any]]:
    """Optimize test collection for parallel vs serial execution."""
    parallel_tests = []
    serial_tests = []
    
    for item in test_items:
        if hasattr(item, 'function'):
            if requires_serial_execution(item.function):
                serial_tests.append(item)
            elif is_parallel_safe(item.function):
                parallel_tests.append(item)
            else:
                # Default to serial for safety
                serial_tests.append(item)
        else:
            serial_tests.append(item)
    
    return {
        "parallel": parallel_tests,
        "serial": serial_tests
    }


# Performance monitoring utilities
class TestPerformanceMonitor:
    """Monitor test performance and identify bottlenecks."""
    
    def __init__(self):
        self.test_times = {}
        self.slow_tests = []
        self.memory_usage = {}
        self.resource_usage = {}
    
    def record_test_performance(self, test_name: str, duration: float, 
                              memory_mb: float = 0, resources_used: Dict[str, int] = None):
        """Record test performance metrics."""
        self.test_times[test_name] = duration
        
        if memory_mb > 0:
            self.memory_usage[test_name] = memory_mb
        
        if resources_used:
            self.resource_usage[test_name] = resources_used
        
        # Track slow tests
        if duration > 1.0:  # Tests taking more than 1 second
            self.slow_tests.append((test_name, duration))
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary and recommendations."""
        if not self.test_times:
            return {"message": "No performance data collected"}
        
        total_time = sum(self.test_times.values())
        avg_time = total_time / len(self.test_times)
        slowest_tests = sorted(self.slow_tests, key=lambda x: x[1], reverse=True)[:10]
        
        recommendations = []
        if len(self.slow_tests) > 0:
            recommendations.append("Consider optimizing slow tests or using faster mocks")
        
        if avg_time > 0.5:
            recommendations.append("Average test time is high - consider performance optimizations")
        
        return {
            "total_tests": len(self.test_times),
            "total_time": round(total_time, 3),
            "average_time": round(avg_time, 3),
            "slow_test_count": len(self.slow_tests),
            "slowest_tests": slowest_tests,
            "memory_usage": self.memory_usage,
            "resource_usage": self.resource_usage,
            "recommendations": recommendations
        }


# Global performance monitor
performance_monitor = TestPerformanceMonitor()


@pytest.fixture(scope="session")
def test_performance_monitor():
    """Provide test performance monitor."""
    return performance_monitor


# Cleanup fixture
@pytest.fixture(scope="session", autouse=True)
def cleanup_optimization_resources():
    """Clean up optimization resources after all tests."""
    yield
    test_optimizer.cleanup_all()
    resource_manager.cleanup_all_resources()
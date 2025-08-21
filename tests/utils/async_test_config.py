"""
Async test configuration and reliability enhancements.

This module provides configuration and utilities for improving async test
reliability, handling timeouts, and managing concurrent operations.
"""

import asyncio
import logging
import pytest
import sys
from typing import Dict, Any, Optional, List, Callable
from unittest.mock import patch, AsyncMock

logger = logging.getLogger(__name__)


class AsyncTestConfig:
    """Configuration for async test behavior."""
    
    # Default timeouts for different operation types
    DEFAULT_TIMEOUTS = {
        'unit_test': 5.0,
        'integration_test': 30.0,
        'external_service': 10.0,
        'database_operation': 5.0,
        'file_operation': 2.0,
        'network_request': 15.0,
        'llm_request': 60.0,
        'batch_operation': 120.0
    }
    
    # Retry configuration
    RETRY_CONFIG = {
        'max_retries': 3,
        'base_delay': 0.1,
        'max_delay': 2.0,
        'exponential_base': 2.0
    }
    
    # Concurrency limits
    CONCURRENCY_LIMITS = {
        'database_connections': 5,
        'external_requests': 10,
        'file_operations': 3,
        'cpu_intensive': 2
    }
    
    # Circuit breaker settings
    CIRCUIT_BREAKER_CONFIG = {
        'failure_threshold': 5,
        'recovery_timeout': 10.0,
        'half_open_max_calls': 3
    }
    
    def __init__(self):
        self.timeouts = self.DEFAULT_TIMEOUTS.copy()
        self.retry_config = self.RETRY_CONFIG.copy()
        self.concurrency_limits = self.CONCURRENCY_LIMITS.copy()
        self.circuit_breaker_config = self.CIRCUIT_BREAKER_CONFIG.copy()
        self.debug_mode = False
        self.strict_mode = True
    
    def set_timeout(self, operation_type: str, timeout: float):
        """Set timeout for a specific operation type."""
        self.timeouts[operation_type] = timeout
    
    def get_timeout(self, operation_type: str, default: float = 30.0) -> float:
        """Get timeout for a specific operation type."""
        return self.timeouts.get(operation_type, default)
    
    def set_concurrency_limit(self, resource_type: str, limit: int):
        """Set concurrency limit for a resource type."""
        self.concurrency_limits[resource_type] = limit
    
    def get_concurrency_limit(self, resource_type: str, default: int = 10) -> int:
        """Get concurrency limit for a resource type."""
        return self.concurrency_limits.get(resource_type, default)
    
    def enable_debug_mode(self):
        """Enable debug mode for verbose async test logging."""
        self.debug_mode = True
        logging.getLogger('asyncio').setLevel(logging.DEBUG)
        logging.getLogger('tests.utils.async_helpers').setLevel(logging.DEBUG)
    
    def enable_strict_mode(self):
        """Enable strict mode for async tests (fail fast on warnings)."""
        self.strict_mode = True
    
    def configure_event_loop_policy(self):
        """Configure event loop policy for optimal test performance."""
        if sys.platform == 'win32':
            # Use ProactorEventLoop on Windows for better performance
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        else:
            # Use default policy on Unix systems
            asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())


# Global configuration instance
async_test_config = AsyncTestConfig()


class AsyncTestEnvironment:
    """Manages async test environment setup and teardown."""
    
    def __init__(self, config: AsyncTestConfig = None):
        self.config = config or async_test_config
        self.active_patches = []
        self.resource_managers = []
        self.cleanup_callbacks = []
    
    async def setup(self):
        """Set up async test environment."""
        # Configure event loop policy
        self.config.configure_event_loop_policy()
        
        # Set up asyncio debugging if in debug mode
        if self.config.debug_mode:
            asyncio.get_event_loop().set_debug(True)
        
        # Configure warnings
        if self.config.strict_mode:
            import warnings
            warnings.filterwarnings('error', category=RuntimeWarning, module='asyncio')
    
    async def teardown(self):
        """Tear down async test environment."""
        # Run cleanup callbacks
        for callback in self.cleanup_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.warning(f"Cleanup callback failed: {e}")
        
        # Clean up resource managers
        for manager in self.resource_managers:
            try:
                await manager.cleanup()
            except Exception as e:
                logger.warning(f"Resource manager cleanup failed: {e}")
        
        # Stop patches
        for patch_obj in self.active_patches:
            try:
                patch_obj.stop()
            except Exception as e:
                logger.warning(f"Patch cleanup failed: {e}")
        
        self.cleanup_callbacks.clear()
        self.resource_managers.clear()
        self.active_patches.clear()
    
    def add_cleanup_callback(self, callback: Callable):
        """Add a cleanup callback."""
        self.cleanup_callbacks.append(callback)
    
    def add_resource_manager(self, manager):
        """Add a resource manager for cleanup."""
        self.resource_managers.append(manager)
    
    def add_patch(self, patch_obj):
        """Add a patch for cleanup."""
        self.active_patches.append(patch_obj)


class AsyncTestMetrics:
    """Collects metrics about async test performance."""
    
    def __init__(self):
        self.test_times = {}
        self.timeout_counts = {}
        self.retry_counts = {}
        self.concurrency_stats = {}
        self.failure_rates = {}
    
    def record_test_time(self, test_name: str, duration: float):
        """Record test execution time."""
        if test_name not in self.test_times:
            self.test_times[test_name] = []
        self.test_times[test_name].append(duration)
    
    def record_timeout(self, test_name: str):
        """Record a timeout occurrence."""
        self.timeout_counts[test_name] = self.timeout_counts.get(test_name, 0) + 1
    
    def record_retry(self, test_name: str, attempt: int):
        """Record a retry attempt."""
        if test_name not in self.retry_counts:
            self.retry_counts[test_name] = []
        self.retry_counts[test_name].append(attempt)
    
    def record_concurrency(self, operation_type: str, concurrent_count: int):
        """Record concurrency statistics."""
        if operation_type not in self.concurrency_stats:
            self.concurrency_stats[operation_type] = []
        self.concurrency_stats[operation_type].append(concurrent_count)
    
    def record_failure(self, test_name: str, failed: bool):
        """Record test failure/success."""
        if test_name not in self.failure_rates:
            self.failure_rates[test_name] = {'total': 0, 'failures': 0}
        
        self.failure_rates[test_name]['total'] += 1
        if failed:
            self.failure_rates[test_name]['failures'] += 1
    
    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        summary = {
            'test_count': len(self.test_times),
            'total_timeouts': sum(self.timeout_counts.values()),
            'total_retries': sum(len(retries) for retries in self.retry_counts.values()),
            'avg_test_times': {},
            'failure_rates': {}
        }
        
        # Calculate average test times
        for test_name, times in self.test_times.items():
            summary['avg_test_times'][test_name] = sum(times) / len(times)
        
        # Calculate failure rates
        for test_name, stats in self.failure_rates.items():
            if stats['total'] > 0:
                summary['failure_rates'][test_name] = stats['failures'] / stats['total']
        
        return summary


# Global metrics instance
async_test_metrics = AsyncTestMetrics()


def configure_async_test_timeouts(**timeouts):
    """Configure async test timeouts."""
    for operation_type, timeout in timeouts.items():
        async_test_config.set_timeout(operation_type, timeout)


def configure_async_test_concurrency(**limits):
    """Configure async test concurrency limits."""
    for resource_type, limit in limits.items():
        async_test_config.set_concurrency_limit(resource_type, limit)


# Pytest configuration hooks
def pytest_configure(config):
    """Configure pytest for async testing."""
    # Add custom markers
    config.addinivalue_line(
        "markers", "async_timeout(timeout): set timeout for async test"
    )
    config.addinivalue_line(
        "markers", "async_retry(retries): set retry count for async test"
    )
    config.addinivalue_line(
        "markers", "async_concurrent(limit): set concurrency limit for async test"
    )


def pytest_runtest_setup(item):
    """Set up individual async test."""
    # Check for async timeout marker
    timeout_marker = item.get_closest_marker("async_timeout")
    if timeout_marker:
        timeout = timeout_marker.args[0]
        async_test_config.set_timeout('current_test', timeout)
    
    # Check for retry marker
    retry_marker = item.get_closest_marker("async_retry")
    if retry_marker:
        retries = retry_marker.args[0]
        async_test_config.retry_config['max_retries'] = retries
    
    # Check for concurrency marker
    concurrent_marker = item.get_closest_marker("async_concurrent")
    if concurrent_marker:
        limit = concurrent_marker.args[0]
        async_test_config.set_concurrency_limit('current_test', limit)


def pytest_runtest_teardown(item):
    """Tear down individual async test."""
    # Reset test-specific configuration
    async_test_config.timeouts.pop('current_test', None)
    async_test_config.concurrency_limits.pop('current_test', None)


# Fixtures for async test configuration
@pytest.fixture(scope="session")
def async_test_config_fixture():
    """Provide async test configuration."""
    return async_test_config


@pytest.fixture(scope="function")
async def async_test_environment():
    """Provide async test environment with setup/teardown."""
    env = AsyncTestEnvironment()
    await env.setup()
    try:
        yield env
    finally:
        await env.teardown()


@pytest.fixture(scope="session")
def async_test_metrics_fixture():
    """Provide async test metrics collector."""
    return async_test_metrics


# Utility functions for test configuration
def get_async_test_timeout(operation_type: str = 'unit_test') -> float:
    """Get timeout for current async test."""
    return async_test_config.get_timeout(operation_type)


def get_async_concurrency_limit(resource_type: str = 'default') -> int:
    """Get concurrency limit for current async test."""
    return async_test_config.get_concurrency_limit(resource_type)


def is_async_debug_enabled() -> bool:
    """Check if async debug mode is enabled."""
    return async_test_config.debug_mode


def is_async_strict_mode() -> bool:
    """Check if async strict mode is enabled."""
    return async_test_config.strict_mode


# Context managers for async test configuration
class async_test_timeout:
    """Context manager for setting async test timeout."""
    
    def __init__(self, timeout: float):
        self.timeout = timeout
        self.original_timeout = None
    
    def __enter__(self):
        self.original_timeout = async_test_config.get_timeout('current_test')
        async_test_config.set_timeout('current_test', self.timeout)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.original_timeout is not None:
            async_test_config.set_timeout('current_test', self.original_timeout)
        else:
            async_test_config.timeouts.pop('current_test', None)


class async_test_concurrency:
    """Context manager for setting async test concurrency limit."""
    
    def __init__(self, limit: int):
        self.limit = limit
        self.original_limit = None
    
    def __enter__(self):
        self.original_limit = async_test_config.get_concurrency_limit('current_test')
        async_test_config.set_concurrency_limit('current_test', self.limit)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.original_limit is not None:
            async_test_config.set_concurrency_limit('current_test', self.original_limit)
        else:
            async_test_config.concurrency_limits.pop('current_test', None)
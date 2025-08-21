"""
Async test reliability helpers.

This module provides utilities for improving async test reliability,
managing timeouts, and ensuring proper cleanup of async resources.
"""

import asyncio
import pytest
import time
import logging
from typing import Any, Callable, Optional, List, Dict, Union, Awaitable
from contextlib import asynccontextmanager
from functools import wraps
from unittest.mock import Mock, AsyncMock
import weakref

logger = logging.getLogger(__name__)


class AsyncTestManager:
    """Manager for async test resources and cleanup."""
    
    def __init__(self):
        self.active_tasks: List[asyncio.Task] = []
        self.cleanup_callbacks: List[Callable] = []
        self.timeouts: Dict[str, float] = {}
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._events: Dict[str, asyncio.Event] = {}
        self._queues: Dict[str, asyncio.Queue] = {}
        self._task_groups: Dict[str, List[asyncio.Task]] = {}
    
    def register_task(self, task: asyncio.Task, name: Optional[str] = None, group: Optional[str] = None) -> asyncio.Task:
        """Register a task for automatic cleanup."""
        self.active_tasks.append(task)
        if name:
            task.set_name(name)
        
        # Add to task group if specified
        if group:
            if group not in self._task_groups:
                self._task_groups[group] = []
            self._task_groups[group].append(task)
        
        # Add weak reference callback for automatic cleanup
        def cleanup_callback(task_ref):
            try:
                self.active_tasks.remove(task_ref)
            except ValueError:
                pass
        
        weakref.ref(task, cleanup_callback)
        return task
    
    def register_cleanup(self, callback: Callable):
        """Register a cleanup callback."""
        self.cleanup_callbacks.append(callback)
    
    def get_semaphore(self, name: str, value: int = 1) -> asyncio.Semaphore:
        """Get or create a named semaphore."""
        if name not in self._semaphores:
            self._semaphores[name] = asyncio.Semaphore(value)
        return self._semaphores[name]
    
    def get_lock(self, name: str) -> asyncio.Lock:
        """Get or create a named lock."""
        if name not in self._locks:
            self._locks[name] = asyncio.Lock()
        return self._locks[name]
    
    def get_event(self, name: str) -> asyncio.Event:
        """Get or create a named event."""
        if name not in self._events:
            self._events[name] = asyncio.Event()
        return self._events[name]
    
    def get_queue(self, name: str, maxsize: int = 0) -> asyncio.Queue:
        """Get or create a named queue."""
        if name not in self._queues:
            self._queues[name] = asyncio.Queue(maxsize=maxsize)
        return self._queues[name]
    
    async def wait_for_task_group(self, group: str, timeout: float = 30.0) -> List[Any]:
        """Wait for all tasks in a group to complete."""
        if group not in self._task_groups:
            return []
        
        tasks = self._task_groups[group]
        if not tasks:
            return []
        
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )
            return results
        except asyncio.TimeoutError:
            logger.warning(f"Task group '{group}' did not complete within {timeout}s")
            # Cancel remaining tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
            raise
    
    async def cleanup_all(self):
        """Clean up all registered resources."""
        cleanup_errors = []
        
        # Cancel active tasks with proper timeout
        if self.active_tasks:
            # First, try to cancel gracefully
            for task in self.active_tasks:
                if not task.done():
                    task.cancel()
            
            # Wait for cancellation with timeout
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.active_tasks, return_exceptions=True),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.warning("Some tasks did not cancel within timeout")
            except Exception as e:
                cleanup_errors.append(f"Task cleanup error: {e}")
        
        self.active_tasks.clear()
        self._task_groups.clear()
        
        # Run cleanup callbacks
        for callback in self.cleanup_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await asyncio.wait_for(callback(), timeout=5.0)
                else:
                    callback()
            except Exception as e:
                cleanup_errors.append(f"Cleanup callback error: {e}")
        
        self.cleanup_callbacks.clear()
        
        # Clear synchronization primitives
        self._semaphores.clear()
        self._locks.clear()
        self._events.clear()
        
        # Clear queues
        for queue in self._queues.values():
            try:
                while not queue.empty():
                    queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self._queues.clear()
        
        # Log cleanup errors if any
        if cleanup_errors:
            logger.warning(f"Cleanup completed with {len(cleanup_errors)} errors: {cleanup_errors}")
    
    def set_timeout(self, name: str, timeout: float):
        """Set a timeout for a named operation."""
        self.timeouts[name] = timeout
    
    def get_timeout(self, name: str, default: float = 30.0) -> float:
        """Get timeout for a named operation."""
        return self.timeouts.get(name, default)
    
    async def run_concurrent_operations(self, operations: List[Awaitable[Any]], 
                                      max_concurrency: int = 10,
                                      timeout: float = 30.0) -> List[Any]:
        """Run multiple operations concurrently with controlled concurrency."""
        semaphore = asyncio.Semaphore(max_concurrency)
        
        async def run_with_semaphore(operation):
            async with semaphore:
                return await operation
        
        tasks = [self.register_task(asyncio.create_task(run_with_semaphore(op))) 
                for op in operations]
        
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )
            return results
        except asyncio.TimeoutError:
            logger.warning(f"Concurrent operations timed out after {timeout}s")
            raise


# Global async test manager instance
_async_manager = AsyncTestManager()


def async_test_with_timeout(timeout: float = 30.0, cleanup: bool = True):
    """Decorator for async tests with timeout and cleanup."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                # Run test with timeout
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
                return result
            except asyncio.TimeoutError:
                execution_time = time.time() - start_time
                pytest.fail(f"Test {func.__name__} timed out after {execution_time:.2f}s (limit: {timeout}s)")
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(f"Test {func.__name__} failed after {execution_time:.2f}s: {e}")
                raise
            finally:
                if cleanup:
                    await _async_manager.cleanup_all()
        
        return wrapper
    return decorator


@asynccontextmanager
async def async_test_context(timeout: float = 30.0):
    """Context manager for async test setup and cleanup."""
    manager = AsyncTestManager()
    
    try:
        yield manager
    finally:
        await manager.cleanup_all()


class AsyncResourceManager:
    """Manager for async resources with automatic cleanup."""
    
    def __init__(self):
        self.resources: List[Any] = []
        self.connections: List[Any] = []
        self.clients: List[Any] = []
    
    def add_resource(self, resource: Any):
        """Add a resource for cleanup."""
        self.resources.append(resource)
    
    def add_connection(self, connection: Any):
        """Add a connection for cleanup."""
        self.connections.append(connection)
    
    def add_client(self, client: Any):
        """Add a client for cleanup."""
        self.clients.append(client)
    
    async def cleanup(self):
        """Clean up all resources."""
        # Close clients
        for client in self.clients:
            try:
                if hasattr(client, 'aclose'):
                    await client.aclose()
                elif hasattr(client, 'close'):
                    if asyncio.iscoroutinefunction(client.close):
                        await client.close()
                    else:
                        client.close()
            except Exception as e:
                logger.warning(f"Error closing client: {e}")
        
        # Close connections
        for connection in self.connections:
            try:
                if hasattr(connection, 'close'):
                    if asyncio.iscoroutinefunction(connection.close):
                        await connection.close()
                    else:
                        connection.close()
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
        
        # Clean up other resources
        for resource in self.resources:
            try:
                if hasattr(resource, 'cleanup'):
                    if asyncio.iscoroutinefunction(resource.cleanup):
                        await resource.cleanup()
                    else:
                        resource.cleanup()
            except Exception as e:
                logger.warning(f"Error cleaning up resource: {e}")
        
        self.resources.clear()
        self.connections.clear()
        self.clients.clear()


def reliable_async_test(timeout: float = 30.0, retries: int = 0):
    """Decorator for reliable async tests with retry capability."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(retries + 1):
                try:
                    async with async_test_context(timeout=timeout) as manager:
                        result = await func(*args, **kwargs)
                        return result
                except asyncio.TimeoutError as e:
                    last_exception = e
                    if attempt < retries:
                        logger.warning(f"Test {func.__name__} timed out on attempt {attempt + 1}, retrying...")
                        await asyncio.sleep(0.1)  # Brief pause before retry
                    else:
                        pytest.fail(f"Test {func.__name__} timed out after {retries + 1} attempts")
                except Exception as e:
                    last_exception = e
                    if attempt < retries:
                        logger.warning(f"Test {func.__name__} failed on attempt {attempt + 1}, retrying: {e}")
                        await asyncio.sleep(0.1)
                    else:
                        raise
            
            if last_exception:
                raise last_exception
        
        return wrapper
    return decorator


class AsyncTestFixtures:
    """Common async test fixtures and utilities."""
    
    @staticmethod
    async def create_mock_async_client():
        """Create a mock async client with proper cleanup."""
        from unittest.mock import AsyncMock
        
        client = AsyncMock()
        client.aclose = AsyncMock()
        
        # Register for cleanup
        _async_manager.register_cleanup(client.aclose)
        
        return client
    
    @staticmethod
    async def create_mock_async_connection():
        """Create a mock async connection with proper cleanup."""
        from unittest.mock import AsyncMock
        
        connection = AsyncMock()
        connection.close = AsyncMock()
        
        # Register for cleanup
        _async_manager.register_cleanup(connection.close)
        
        return connection
    
    @staticmethod
    async def wait_for_condition(
        condition: Callable[[], bool],
        timeout: float = 5.0,
        interval: float = 0.1
    ) -> bool:
        """Wait for a condition to become true with timeout."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if condition():
                return True
            await asyncio.sleep(interval)
        
        return False
    
    @staticmethod
    async def run_with_timeout(
        coro: Awaitable[Any],
        timeout: float,
        default: Any = None
    ) -> Any:
        """Run a coroutine with timeout, returning default on timeout."""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Operation timed out after {timeout}s")
            return default


def configure_async_test_environment():
    """Configure the async test environment for reliability."""
    # Set event loop policy for better test isolation
    if hasattr(asyncio, 'WindowsSelectorEventLoopPolicy'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Configure logging for async operations
    logging.getLogger('asyncio').setLevel(logging.WARNING)


class AsyncTestCase:
    """Base class for async test cases with built-in reliability features."""
    
    def setup_method(self):
        """Set up async test environment."""
        self.async_manager = AsyncTestManager()
        self.resource_manager = AsyncResourceManager()
    
    async def teardown_method(self):
        """Clean up async test environment."""
        await self.async_manager.cleanup_all()
        await self.resource_manager.cleanup()
    
    async def create_task_with_cleanup(self, coro: Awaitable[Any], name: Optional[str] = None) -> asyncio.Task:
        """Create a task with automatic cleanup registration."""
        task = asyncio.create_task(coro)
        return self.async_manager.register_task(task, name)
    
    async def wait_for_tasks(self, timeout: float = 30.0):
        """Wait for all registered tasks to complete."""
        if self.async_manager.active_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.async_manager.active_tasks, return_exceptions=True),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"Some tasks did not complete within {timeout}s")


# Pytest fixtures for async testing
@pytest.fixture
async def async_test_manager():
    """Fixture providing an async test manager."""
    manager = AsyncTestManager()
    try:
        yield manager
    finally:
        await manager.cleanup_all()


@pytest.fixture
async def async_resource_manager():
    """Fixture providing an async resource manager."""
    manager = AsyncResourceManager()
    try:
        yield manager
    finally:
        await manager.cleanup()


@pytest.fixture(scope="session", autouse=True)
def configure_async_environment():
    """Auto-configure async test environment."""
    configure_async_test_environment()


# Enhanced async test patterns and utilities
class AsyncTestPatterns:
    """Common async test patterns for reliable testing."""
    
    @staticmethod
    async def test_concurrent_requests(
        request_func: Callable[..., Awaitable[Any]],
        request_count: int = 10,
        max_concurrency: int = 5,
        timeout: float = 30.0,
        **request_kwargs
    ) -> List[Any]:
        """Test concurrent requests with controlled concurrency."""
        async def make_request():
            return await request_func(**request_kwargs)
        
        operations = [make_request() for _ in range(request_count)]
        
        return await _async_manager.run_concurrent_operations(
            operations, max_concurrency, timeout
        )
    
    @staticmethod
    async def test_retry_pattern(
        operation: Callable[..., Awaitable[Any]],
        max_retries: int = 3,
        retry_delay: float = 0.1,
        timeout_per_attempt: float = 10.0,
        **operation_kwargs
    ) -> Any:
        """Test retry patterns with exponential backoff."""
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                return await asyncio.wait_for(
                    operation(**operation_kwargs),
                    timeout=timeout_per_attempt
                )
            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    delay = retry_delay * (2 ** attempt)  # Exponential backoff
                    await asyncio.sleep(delay)
                else:
                    raise
        
        if last_exception:
            raise last_exception
    
    @staticmethod
    async def test_timeout_behavior(
        operation: Callable[..., Awaitable[Any]],
        expected_timeout: float,
        tolerance: float = 0.5,
        **operation_kwargs
    ):
        """Test that an operation times out within expected timeframe."""
        start_time = time.time()
        
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                operation(**operation_kwargs),
                timeout=expected_timeout + tolerance
            )
        
        elapsed_time = time.time() - start_time
        assert abs(elapsed_time - expected_timeout) <= tolerance, \
            f"Operation timed out in {elapsed_time:.2f}s, expected ~{expected_timeout:.2f}s"
    
    @staticmethod
    async def test_resource_cleanup(
        setup_func: Callable[..., Awaitable[Any]],
        operation_func: Callable[[Any], Awaitable[Any]],
        cleanup_func: Callable[[Any], Awaitable[None]],
        verify_cleanup_func: Callable[[Any], Awaitable[bool]],
        **setup_kwargs
    ):
        """Test that resources are properly cleaned up after operations."""
        resource = await setup_func(**setup_kwargs)
        
        try:
            await operation_func(resource)
        finally:
            await cleanup_func(resource)
        
        # Verify cleanup was successful
        is_cleaned = await verify_cleanup_func(resource)
        assert is_cleaned, "Resource was not properly cleaned up"
    
    @staticmethod
    async def test_race_condition(
        operations: List[Callable[..., Awaitable[Any]]],
        expected_winner: Optional[int] = None,
        timeout: float = 10.0
    ) -> int:
        """Test race conditions between multiple operations."""
        tasks = [asyncio.create_task(op()) for op in operations]
        
        try:
            done, pending = await asyncio.wait(
                tasks,
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel pending tasks
            for task in pending:
                task.cancel()
            
            # Get the winner
            winner_task = list(done)[0]
            winner_index = tasks.index(winner_task)
            
            if expected_winner is not None:
                assert winner_index == expected_winner, \
                    f"Expected operation {expected_winner} to win, but operation {winner_index} won"
            
            return winner_index
            
        except asyncio.TimeoutError:
            # Cancel all tasks
            for task in tasks:
                task.cancel()
            pytest.fail(f"Race condition test timed out after {timeout}s")


class AsyncMockPatterns:
    """Patterns for creating reliable async mocks."""
    
    @staticmethod
    def create_async_mock_with_delay(
        return_value: Any = None,
        side_effect: Optional[Exception] = None,
        delay: float = 0.1
    ) -> AsyncMock:
        """Create an async mock with configurable delay."""
        from unittest.mock import AsyncMock
        
        async def delayed_mock(*args, **kwargs):
            await asyncio.sleep(delay)
            if side_effect:
                raise side_effect
            return return_value
        
        mock = AsyncMock(side_effect=delayed_mock)
        return mock
    
    @staticmethod
    def create_flaky_async_mock(
        return_value: Any = None,
        failure_rate: float = 0.3,
        failure_exception: Exception = Exception("Flaky mock failure")
    ) -> AsyncMock:
        """Create an async mock that fails intermittently."""
        from unittest.mock import AsyncMock
        import random
        
        async def flaky_mock(*args, **kwargs):
            if random.random() < failure_rate:
                raise failure_exception
            return return_value
        
        mock = AsyncMock(side_effect=flaky_mock)
        return mock
    
    @staticmethod
    def create_rate_limited_async_mock(
        return_value: Any = None,
        rate_limit: int = 10,
        time_window: float = 1.0
    ) -> AsyncMock:
        """Create an async mock with rate limiting."""
        from unittest.mock import AsyncMock
        import time
        
        call_times = []
        
        async def rate_limited_mock(*args, **kwargs):
            current_time = time.time()
            
            # Remove old calls outside the time window
            call_times[:] = [t for t in call_times if current_time - t < time_window]
            
            # Check rate limit
            if len(call_times) >= rate_limit:
                raise Exception(f"Rate limit exceeded: {rate_limit} calls per {time_window}s")
            
            call_times.append(current_time)
            return return_value
        
        mock = AsyncMock(side_effect=rate_limited_mock)
        return mock


# Utility functions for common async test patterns
async def assert_eventually(
    condition: Callable[[], Union[bool, Awaitable[bool]]],
    timeout: float = 5.0,
    interval: float = 0.1,
    message: str = "Condition was not met within timeout"
):
    """Assert that a condition becomes true within a timeout."""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            if asyncio.iscoroutinefunction(condition):
                result = await condition()
            else:
                result = condition()
            
            if result:
                return
        except Exception as e:
            logger.debug(f"Condition check failed: {e}")
        
        await asyncio.sleep(interval)
    
    pytest.fail(f"{message} (waited {timeout}s)")


async def assert_async_raises(
    exception_type: type,
    coro: Awaitable[Any],
    timeout: float = 30.0,
    match: Optional[str] = None
):
    """Assert that an async operation raises a specific exception."""
    with pytest.raises(exception_type, match=match):
        await asyncio.wait_for(coro, timeout=timeout)


async def assert_completes_within(
    coro: Awaitable[Any],
    timeout: float,
    tolerance: float = 0.1
) -> Any:
    """Assert that an async operation completes within a specific timeframe."""
    start_time = time.time()
    
    try:
        result = await asyncio.wait_for(coro, timeout=timeout + tolerance)
        elapsed_time = time.time() - start_time
        
        assert elapsed_time <= timeout + tolerance, \
            f"Operation took {elapsed_time:.2f}s, expected <= {timeout:.2f}s"
        
        return result
    except asyncio.TimeoutError:
        elapsed_time = time.time() - start_time
        pytest.fail(f"Operation timed out after {elapsed_time:.2f}s, expected <= {timeout:.2f}s")


async def run_with_circuit_breaker(
    operation: Callable[..., Awaitable[Any]],
    failure_threshold: int = 3,
    recovery_timeout: float = 5.0,
    **operation_kwargs
) -> Any:
    """Run an operation with circuit breaker pattern."""
    failure_count = 0
    last_failure_time = 0
    
    while True:
        current_time = time.time()
        
        # Check if we should attempt recovery
        if failure_count >= failure_threshold:
            if current_time - last_failure_time < recovery_timeout:
                raise Exception("Circuit breaker is open")
            else:
                failure_count = 0  # Reset for recovery attempt
        
        try:
            result = await operation(**operation_kwargs)
            failure_count = 0  # Reset on success
            return result
        except Exception as e:
            failure_count += 1
            last_failure_time = current_time
            
            if failure_count >= failure_threshold:
                logger.warning(f"Circuit breaker opened after {failure_count} failures")
            
            raise


def skip_if_no_async_support():
    """Skip test if async support is not available."""
    try:
        asyncio.get_event_loop()
        return False
    except RuntimeError:
        return pytest.mark.skip("No async support available")


# Enhanced pytest fixtures
@pytest.fixture
async def async_test_patterns():
    """Fixture providing async test patterns."""
    return AsyncTestPatterns()


@pytest.fixture
async def async_mock_patterns():
    """Fixture providing async mock patterns."""
    return AsyncMockPatterns()


@pytest.fixture
async def concurrent_test_runner():
    """Fixture for running concurrent tests."""
    async def run_concurrent(operations, max_concurrency=10, timeout=30.0):
        return await _async_manager.run_concurrent_operations(
            operations, max_concurrency, timeout
        )
    
    return run_concurrent
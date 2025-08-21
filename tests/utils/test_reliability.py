"""
Test reliability and consistency utilities.

This module provides utilities for fixing flaky tests, improving mock consistency,
and ensuring proper test isolation and cleanup.
"""

import asyncio
import time
import threading
import weakref
import gc
import logging
from contextlib import contextmanager, asynccontextmanager
from typing import Dict, Any, List, Optional, Callable, Set, Union
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from functools import wraps
import pytest
import inspect

logger = logging.getLogger(__name__)


class TestReliabilityManager:
    """Manages test reliability through consistent mocking and error handling."""
    
    def __init__(self):
        self.mock_registry = {}
        self.patch_registry = {}
        self.cleanup_callbacks = []
        self.flaky_test_tracker = {}
        self.error_patterns = {}
        self.isolation_contexts = {}
        self._lock = threading.Lock()
    
    def register_consistent_mock(self, mock_name: str, mock_factory: Callable) -> Mock:
        """Register a consistent mock that can be reused across tests."""
        with self._lock:
            if mock_name not in self.mock_registry:
                mock_obj = mock_factory()
                self.mock_registry[mock_name] = mock_obj
                logger.debug(f"Registered consistent mock: {mock_name}")
            
            return self.mock_registry[mock_name]
    
    def get_consistent_mock(self, mock_name: str) -> Optional[Mock]:
        """Get a previously registered consistent mock."""
        return self.mock_registry.get(mock_name)
    
    def create_database_mock(self, mock_name: str = "database") -> Mock:
        """Create a consistent database mock."""
        def factory():
            mock_session = Mock()
            
            # Consistent database operations
            mock_session.add = Mock()
            mock_session.commit = Mock()
            mock_session.rollback = Mock()
            mock_session.close = Mock()
            mock_session.flush = Mock()
            mock_session.refresh = Mock()
            mock_session.merge = Mock()
            mock_session.delete = Mock()
            
            # Consistent query behavior
            mock_query = Mock()
            mock_query.filter = Mock(return_value=mock_query)
            mock_query.filter_by = Mock(return_value=mock_query)
            mock_query.order_by = Mock(return_value=mock_query)
            mock_query.limit = Mock(return_value=mock_query)
            mock_query.offset = Mock(return_value=mock_query)
            mock_query.join = Mock(return_value=mock_query)
            mock_query.outerjoin = Mock(return_value=mock_query)
            mock_query.group_by = Mock(return_value=mock_query)
            mock_query.having = Mock(return_value=mock_query)
            
            # Consistent query results
            mock_query.first = Mock(return_value=None)
            mock_query.all = Mock(return_value=[])
            mock_query.count = Mock(return_value=0)
            mock_query.one = Mock(return_value=None)
            mock_query.one_or_none = Mock(return_value=None)
            mock_query.scalar = Mock(return_value=None)
            
            mock_session.query = Mock(return_value=mock_query)
            mock_session.execute = Mock(return_value=Mock(fetchall=Mock(return_value=[])))
            
            # Context manager support
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=None)
            
            return mock_session
        
        return self.register_consistent_mock(mock_name, factory)
    
    def create_external_service_mock(self, mock_name: str = "external_service") -> Mock:
        """Create a consistent external service mock."""
        def factory():
            mock_service = Mock()
            
            # Consistent HTTP responses
            mock_service.get = Mock(return_value={
                "status": "success",
                "data": {},
                "status_code": 200
            })
            mock_service.post = Mock(return_value={
                "status": "created",
                "data": {"id": "test_id"},
                "status_code": 201
            })
            mock_service.put = Mock(return_value={
                "status": "updated",
                "data": {},
                "status_code": 200
            })
            mock_service.delete = Mock(return_value={
                "status": "deleted",
                "status_code": 204
            })
            
            # Consistent availability checks
            mock_service.is_available = Mock(return_value=True)
            mock_service.health_check = Mock(return_value={
                "healthy": True,
                "response_time": 0.001,
                "timestamp": time.time()
            })
            
            # Consistent authentication
            mock_service.authenticate = Mock(return_value={
                "token": "test_token_123",
                "expires_in": 3600
            })
            
            return mock_service
        
        return self.register_consistent_mock(mock_name, factory)
    
    def create_async_service_mock(self, mock_name: str = "async_service") -> AsyncMock:
        """Create a consistent async service mock."""
        def factory():
            mock_service = AsyncMock()
            
            # Consistent async responses
            async def mock_get(*args, **kwargs):
                await asyncio.sleep(0.001)  # Minimal consistent delay
                return {
                    "status": "success",
                    "data": {},
                    "response_time": 0.001
                }
            
            async def mock_post(*args, **kwargs):
                await asyncio.sleep(0.001)
                return {
                    "status": "created",
                    "data": {"id": "test_id"},
                    "response_time": 0.001
                }
            
            mock_service.get = AsyncMock(side_effect=mock_get)
            mock_service.post = AsyncMock(side_effect=mock_post)
            mock_service.put = AsyncMock(side_effect=mock_get)
            mock_service.delete = AsyncMock(side_effect=mock_get)
            
            # Consistent async health checks
            mock_service.health_check = AsyncMock(return_value={
                "healthy": True,
                "response_time": 0.001
            })
            
            # Consistent cleanup
            mock_service.aclose = AsyncMock()
            mock_service.cleanup = AsyncMock()
            
            return mock_service
        
        return self.register_consistent_mock(mock_name, factory)
    
    def create_llm_service_mock(self, mock_name: str = "llm_service") -> AsyncMock:
        """Create a consistent LLM service mock."""
        def factory():
            mock_llm = AsyncMock()
            
            # Consistent decision generation
            async def mock_generate_decision(*args, **kwargs):
                await asyncio.sleep(0.01)  # Consistent processing time
                return {
                    "decision": "approved",
                    "confidence": 0.95,
                    "reasoning": [
                        "Patient meets medical necessity criteria",
                        "Procedure is covered under policy"
                    ],
                    "processing_time_ms": 10.0,
                    "model_version": "test_model_v1.0"
                }
            
            async def mock_analyze_request(*args, **kwargs):
                await asyncio.sleep(0.005)
                return {
                    "analysis": "Request is valid and complete",
                    "confidence": 0.92,
                    "key_factors": ["diagnosis_valid", "procedure_appropriate"],
                    "processing_time_ms": 5.0
                }
            
            mock_llm.generate_decision = AsyncMock(side_effect=mock_generate_decision)
            mock_llm.analyze_request = AsyncMock(side_effect=mock_analyze_request)
            
            # Consistent availability
            mock_llm.is_available = Mock(return_value=True)
            mock_llm.health_check = AsyncMock(return_value={
                "status": "healthy",
                "model_loaded": True,
                "response_time": 0.001
            })
            
            # Consistent lifecycle
            mock_llm.initialize = AsyncMock()
            mock_llm.cleanup = AsyncMock()
            
            return mock_llm
        
        return self.register_consistent_mock(mock_name, factory)
    
    def apply_consistent_patches(self, patches: Dict[str, str]):
        """Apply consistent patches across tests."""
        active_patches = {}
        
        for patch_name, target_path in patches.items():
            if patch_name in self.mock_registry:
                mock_obj = self.mock_registry[patch_name]
                patch_obj = patch(target_path, mock_obj)
                active_patches[patch_name] = patch_obj.start()
                self.patch_registry[patch_name] = patch_obj
        
        return active_patches
    
    def stop_all_patches(self):
        """Stop all active patches."""
        for patch_name, patch_obj in self.patch_registry.items():
            try:
                patch_obj.stop()
            except Exception as e:
                logger.warning(f"Error stopping patch {patch_name}: {e}")
        
        self.patch_registry.clear()
    
    def track_flaky_test(self, test_name: str, error: Exception):
        """Track flaky test occurrences."""
        if test_name not in self.flaky_test_tracker:
            self.flaky_test_tracker[test_name] = []
        
        self.flaky_test_tracker[test_name].append({
            "timestamp": time.time(),
            "error_type": type(error).__name__,
            "error_message": str(error)
        })
        
        # Track error patterns
        error_type = type(error)
        if error_type not in self.error_patterns:
            self.error_patterns[error_type] = []
        self.error_patterns[error_type].append(str(error))
    
    def get_flaky_test_report(self) -> Dict[str, Any]:
        """Get report of flaky tests and patterns."""
        flaky_summary = {}
        
        for test_name, occurrences in self.flaky_test_tracker.items():
            flaky_summary[test_name] = {
                "occurrence_count": len(occurrences),
                "error_types": list(set(occ["error_type"] for occ in occurrences)),
                "latest_error": occurrences[-1] if occurrences else None
            }
        
        error_summary = {}
        for error_type, messages in self.error_patterns.items():
            error_summary[error_type.__name__] = {
                "count": len(messages),
                "unique_messages": len(set(messages)),
                "sample_message": messages[0] if messages else None
            }
        
        return {
            "flaky_tests": flaky_summary,
            "error_patterns": error_summary,
            "total_flaky_tests": len(self.flaky_test_tracker),
            "most_flaky_test": max(
                flaky_summary.items(),
                key=lambda x: x[1]["occurrence_count"],
                default=(None, {"occurrence_count": 0})
            )[0]
        }
    
    def cleanup_all(self):
        """Clean up all reliability resources."""
        self.stop_all_patches()
        
        # Run cleanup callbacks
        for callback in self.cleanup_callbacks:
            try:
                callback()
            except Exception as e:
                logger.warning(f"Cleanup callback failed: {e}")
        
        # Clear registries
        self.mock_registry.clear()
        self.patch_registry.clear()
        self.cleanup_callbacks.clear()
        self.isolation_contexts.clear()


class TestIsolationManager:
    """Manages test isolation and cleanup to prevent test interference."""
    
    def __init__(self):
        self.active_resources = set()
        self.cleanup_stack = []
        self.isolation_level = "function"  # function, class, module
        self.resource_limits = {
            "max_open_files": 50,
            "max_database_connections": 10,
            "max_network_connections": 20,
            "max_memory_mb": 200
        }
    
    @contextmanager
    def isolated_test_context(self, test_name: str, isolation_level: str = "function"):
        """Context manager for isolated test execution."""
        self.isolation_level = isolation_level
        original_resources = self.active_resources.copy()
        
        try:
            # Set up isolation
            self._setup_isolation(test_name)
            yield self
        except Exception as e:
            logger.error(f"Test {test_name} failed with isolation: {e}")
            raise
        finally:
            # Clean up isolation
            self._cleanup_isolation(test_name, original_resources)
    
    def _setup_isolation(self, test_name: str):
        """Set up test isolation."""
        # Force garbage collection before test
        gc.collect()
        
        # Set up resource monitoring
        self._monitor_resources(test_name)
        
        # Set up environment isolation
        self._isolate_environment(test_name)
    
    def _cleanup_isolation(self, test_name: str, original_resources: Set):
        """Clean up test isolation."""
        # Run cleanup stack in reverse order
        while self.cleanup_stack:
            cleanup_func = self.cleanup_stack.pop()
            try:
                cleanup_func()
            except Exception as e:
                logger.warning(f"Cleanup function failed for {test_name}: {e}")
        
        # Restore original resources
        self.active_resources = original_resources
        
        # Force garbage collection after test
        gc.collect()
    
    def _monitor_resources(self, test_name: str):
        """Monitor resource usage during test."""
        # This would integrate with system monitoring in a real implementation
        pass
    
    def _isolate_environment(self, test_name: str):
        """Isolate test environment."""
        # This would set up environment variable isolation, etc.
        pass
    
    def register_resource(self, resource: Any, cleanup_func: Callable):
        """Register a resource for cleanup."""
        resource_id = id(resource)
        self.active_resources.add(resource_id)
        self.cleanup_stack.append(cleanup_func)
        
        # Create weak reference for automatic cleanup
        def cleanup_callback(ref):
            self.active_resources.discard(resource_id)
        
        weakref.ref(resource, cleanup_callback)
    
    def check_resource_limits(self) -> Dict[str, Any]:
        """Check if resource limits are being exceeded."""
        current_usage = {
            "active_resources": len(self.active_resources),
            "cleanup_stack_size": len(self.cleanup_stack)
        }
        
        warnings = []
        if current_usage["active_resources"] > self.resource_limits.get("max_open_files", 50):
            warnings.append("Too many active resources")
        
        return {
            "current_usage": current_usage,
            "limits": self.resource_limits,
            "warnings": warnings
        }


class MockConsistencyManager:
    """Ensures mock consistency across tests."""
    
    def __init__(self):
        self.mock_behaviors = {}
        self.mock_call_history = {}
        self.mock_state_snapshots = {}
    
    def define_mock_behavior(self, mock_name: str, behavior_config: Dict[str, Any]):
        """Define consistent behavior for a mock."""
        self.mock_behaviors[mock_name] = behavior_config
    
    def apply_mock_behavior(self, mock_obj: Mock, mock_name: str):
        """Apply defined behavior to a mock object."""
        if mock_name not in self.mock_behaviors:
            return
        
        behavior = self.mock_behaviors[mock_name]
        
        # Apply return values
        if "return_values" in behavior:
            for method_name, return_value in behavior["return_values"].items():
                if hasattr(mock_obj, method_name):
                    getattr(mock_obj, method_name).return_value = return_value
        
        # Apply side effects
        if "side_effects" in behavior:
            for method_name, side_effect in behavior["side_effects"].items():
                if hasattr(mock_obj, method_name):
                    getattr(mock_obj, method_name).side_effect = side_effect
        
        # Apply call counts
        if "call_counts" in behavior:
            for method_name, call_count in behavior["call_counts"].items():
                if hasattr(mock_obj, method_name):
                    method_mock = getattr(mock_obj, method_name)
                    method_mock.call_count = call_count
    
    def snapshot_mock_state(self, mock_obj: Mock, mock_name: str):
        """Take a snapshot of mock state for consistency checking."""
        state = {
            "call_count": mock_obj.call_count,
            "called": mock_obj.called,
            "call_args": mock_obj.call_args,
            "call_args_list": mock_obj.call_args_list.copy() if hasattr(mock_obj.call_args_list, 'copy') else list(mock_obj.call_args_list)
        }
        
        self.mock_state_snapshots[mock_name] = state
    
    def verify_mock_consistency(self, mock_obj: Mock, mock_name: str) -> Dict[str, Any]:
        """Verify mock consistency against snapshot."""
        if mock_name not in self.mock_state_snapshots:
            return {"status": "no_snapshot", "message": "No snapshot available for comparison"}
        
        snapshot = self.mock_state_snapshots[mock_name]
        current_state = {
            "call_count": mock_obj.call_count,
            "called": mock_obj.called,
            "call_args": mock_obj.call_args,
            "call_args_list": list(mock_obj.call_args_list)
        }
        
        inconsistencies = []
        
        # Check for unexpected changes
        if current_state["call_count"] < snapshot["call_count"]:
            inconsistencies.append("Call count decreased unexpectedly")
        
        if current_state["called"] != snapshot["called"] and not current_state["called"]:
            inconsistencies.append("Mock was called but now shows as not called")
        
        return {
            "status": "consistent" if not inconsistencies else "inconsistent",
            "inconsistencies": inconsistencies,
            "snapshot": snapshot,
            "current": current_state
        }
    
    def reset_mock_to_snapshot(self, mock_obj: Mock, mock_name: str):
        """Reset mock to snapshot state."""
        if mock_name not in self.mock_state_snapshots:
            return
        
        snapshot = self.mock_state_snapshots[mock_name]
        
        # Reset mock
        mock_obj.reset_mock()
        
        # Restore state
        mock_obj.call_count = snapshot["call_count"]
        mock_obj.called = snapshot["called"]
        mock_obj.call_args = snapshot["call_args"]
        mock_obj.call_args_list = snapshot["call_args_list"].copy()


# Global instances
reliability_manager = TestReliabilityManager()
isolation_manager = TestIsolationManager()
mock_consistency_manager = MockConsistencyManager()


# Decorators for test reliability
def reliable_test(max_retries: int = 3, retry_delay: float = 0.1, 
                 expected_exceptions: List[type] = None):
    """Decorator for reliable test execution with retry logic."""
    expected_exceptions = expected_exceptions or []
    
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
                    reliability_manager.track_flaky_test(test_func.__name__, e)
                    
                    # Check if this is an expected exception
                    if any(isinstance(e, exc_type) for exc_type in expected_exceptions):
                        logger.debug(f"Expected exception in {test_func.__name__}: {e}")
                        raise
                    
                    if attempt < max_retries:
                        delay = retry_delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(f"Test {test_func.__name__} failed on attempt {attempt + 1}, retrying in {delay}s: {e}")
                        time.sleep(delay)
                    else:
                        logger.error(f"Test {test_func.__name__} failed after {max_retries + 1} attempts")
            
            if last_exception:
                raise last_exception
        
        return wrapper
    return decorator


def isolated_test(isolation_level: str = "function"):
    """Decorator for isolated test execution."""
    def decorator(test_func):
        @wraps(test_func)
        def wrapper(*args, **kwargs):
            with isolation_manager.isolated_test_context(test_func.__name__, isolation_level):
                return test_func(*args, **kwargs)
        
        return wrapper
    return decorator


def consistent_mocks(**mock_configs):
    """Decorator for consistent mock application."""
    def decorator(test_func):
        @wraps(test_func)
        def wrapper(*args, **kwargs):
            # Apply consistent mocks
            applied_mocks = {}
            
            for mock_name, config in mock_configs.items():
                if config["type"] == "database":
                    mock_obj = reliability_manager.create_database_mock(mock_name)
                elif config["type"] == "external_service":
                    mock_obj = reliability_manager.create_external_service_mock(mock_name)
                elif config["type"] == "async_service":
                    mock_obj = reliability_manager.create_async_service_mock(mock_name)
                elif config["type"] == "llm_service":
                    mock_obj = reliability_manager.create_llm_service_mock(mock_name)
                else:
                    continue
                
                applied_mocks[mock_name] = mock_obj
                
                # Apply behavior if specified
                if "behavior" in config:
                    mock_consistency_manager.define_mock_behavior(mock_name, config["behavior"])
                    mock_consistency_manager.apply_mock_behavior(mock_obj, mock_name)
            
            try:
                # Take snapshots before test
                for mock_name, mock_obj in applied_mocks.items():
                    mock_consistency_manager.snapshot_mock_state(mock_obj, mock_name)
                
                # Run test
                result = test_func(*args, **kwargs)
                
                # Verify consistency after test
                for mock_name, mock_obj in applied_mocks.items():
                    consistency_result = mock_consistency_manager.verify_mock_consistency(mock_obj, mock_name)
                    if consistency_result["status"] == "inconsistent":
                        logger.warning(f"Mock {mock_name} inconsistency in {test_func.__name__}: {consistency_result['inconsistencies']}")
                
                return result
            
            finally:
                # Clean up mocks
                for mock_obj in applied_mocks.values():
                    if hasattr(mock_obj, 'reset_mock'):
                        mock_obj.reset_mock()
        
        return wrapper
    return decorator


# Pytest fixtures for reliability
@pytest.fixture(scope="function")
def reliable_test_environment():
    """Provide reliable test environment."""
    return reliability_manager


@pytest.fixture(scope="function")
def isolated_test_environment():
    """Provide isolated test environment."""
    return isolation_manager


@pytest.fixture(scope="function")
def consistent_mock_environment():
    """Provide consistent mock environment."""
    return mock_consistency_manager


@pytest.fixture(scope="function")
def reliable_database_mock():
    """Provide reliable database mock."""
    return reliability_manager.create_database_mock("test_database")


@pytest.fixture(scope="function")
def reliable_external_service_mock():
    """Provide reliable external service mock."""
    return reliability_manager.create_external_service_mock("test_external_service")


@pytest.fixture(scope="function")
def reliable_async_service_mock():
    """Provide reliable async service mock."""
    return reliability_manager.create_async_service_mock("test_async_service")


@pytest.fixture(scope="function")
def reliable_llm_service_mock():
    """Provide reliable LLM service mock."""
    return reliability_manager.create_llm_service_mock("test_llm_service")


# Context managers for reliability
@contextmanager
def reliable_test_context(test_name: str):
    """Context manager for reliable test execution."""
    try:
        yield reliability_manager
    except Exception as e:
        reliability_manager.track_flaky_test(test_name, e)
        raise


@asynccontextmanager
async def reliable_async_test_context(test_name: str):
    """Async context manager for reliable test execution."""
    try:
        yield reliability_manager
    except Exception as e:
        reliability_manager.track_flaky_test(test_name, e)
        raise


# Cleanup fixture
@pytest.fixture(scope="session", autouse=True)
def cleanup_reliability_resources():
    """Clean up reliability resources after all tests."""
    yield
    reliability_manager.cleanup_all()


# Utility functions
def fix_flaky_test(test_func: Callable, max_attempts: int = 5) -> Dict[str, Any]:
    """Attempt to fix a flaky test by running it multiple times and analyzing failures."""
    results = []
    exceptions = []
    
    for attempt in range(max_attempts):
        try:
            start_time = time.perf_counter()
            result = test_func()
            duration = time.perf_counter() - start_time
            
            results.append({
                "attempt": attempt + 1,
                "status": "passed",
                "duration": duration,
                "result": result
            })
        except Exception as e:
            duration = time.perf_counter() - start_time
            exceptions.append({
                "attempt": attempt + 1,
                "status": "failed",
                "duration": duration,
                "exception": e,
                "exception_type": type(e).__name__
            })
    
    # Analyze results
    pass_rate = len(results) / max_attempts
    avg_duration = sum(r["duration"] for r in results) / len(results) if results else 0
    
    # Identify common failure patterns
    exception_types = [exc["exception_type"] for exc in exceptions]
    common_exceptions = {}
    for exc_type in exception_types:
        common_exceptions[exc_type] = common_exceptions.get(exc_type, 0) + 1
    
    recommendations = []
    if pass_rate < 0.8:
        recommendations.append("Test is highly flaky - consider rewriting")
    elif pass_rate < 0.9:
        recommendations.append("Test has reliability issues - add retry logic")
    
    if avg_duration > 1.0:
        recommendations.append("Test is slow - consider optimization")
    
    if common_exceptions:
        most_common = max(common_exceptions.items(), key=lambda x: x[1])
        recommendations.append(f"Most common failure: {most_common[0]} - consider specific handling")
    
    return {
        "test_name": test_func.__name__,
        "attempts": max_attempts,
        "passed": len(results),
        "failed": len(exceptions),
        "pass_rate": pass_rate,
        "average_duration": avg_duration,
        "common_exceptions": common_exceptions,
        "recommendations": recommendations,
        "results": results,
        "exceptions": exceptions
    }


def create_test_utilities():
    """Create reusable test utilities for common patterns."""
    utilities = {}
    
    # Database utilities
    utilities["create_test_data"] = lambda count=10: [
        {"id": i, "name": f"test_item_{i}", "value": i * 10}
        for i in range(count)
    ]
    
    # Mock utilities
    utilities["reset_all_mocks"] = lambda *mocks: [
        mock.reset_mock() for mock in mocks if hasattr(mock, 'reset_mock')
    ]
    
    # Async utilities
    utilities["wait_for_condition"] = lambda condition, timeout=5.0: asyncio.wait_for(
        _wait_for_condition_impl(condition), timeout=timeout
    )
    
    # Validation utilities
    utilities["assert_mock_called_with_pattern"] = lambda mock, pattern: any(
        pattern in str(call) for call in mock.call_args_list
    )
    
    return utilities


async def _wait_for_condition_impl(condition: Callable[[], bool], interval: float = 0.1):
    """Implementation for wait_for_condition utility."""
    while not condition():
        await asyncio.sleep(interval)


# Export commonly used utilities
test_utilities = create_test_utilities()
"""
Test cleanup and error handling utilities.

This module provides comprehensive test cleanup mechanisms and error handling
to ensure proper test isolation and prevent resource leaks.
"""

import asyncio
import gc
import logging
import os
import tempfile
import threading
import time
import weakref
from contextlib import contextmanager, asynccontextmanager
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Set, Union
from unittest.mock import Mock, AsyncMock, patch
import pytest

logger = logging.getLogger(__name__)


class TestCleanupManager:
    """Manages comprehensive test cleanup and resource management."""
    
    def __init__(self):
        self.cleanup_callbacks = []
        self.temp_files = set()
        self.temp_directories = set()
        self.active_patches = []
        self.active_threads = []
        self.active_tasks = []
        self.resource_registry = {}
        self.cleanup_stats = {
            "files_cleaned": 0,
            "directories_cleaned": 0,
            "patches_stopped": 0,
            "threads_joined": 0,
            "tasks_cancelled": 0,
            "callbacks_executed": 0
        }
        self._lock = threading.Lock()
    
    def register_temp_file(self, file_path: Union[str, Path]) -> Path:
        """Register a temporary file for cleanup."""
        file_path = Path(file_path)
        with self._lock:
            self.temp_files.add(file_path)
        return file_path
    
    def register_temp_directory(self, dir_path: Union[str, Path]) -> Path:
        """Register a temporary directory for cleanup."""
        dir_path = Path(dir_path)
        with self._lock:
            self.temp_directories.add(dir_path)
        return dir_path
    
    def register_patch(self, patch_obj) -> Any:
        """Register a patch for cleanup."""
        with self._lock:
            self.active_patches.append(patch_obj)
        return patch_obj
    
    def register_thread(self, thread: threading.Thread) -> threading.Thread:
        """Register a thread for cleanup."""
        with self._lock:
            self.active_threads.append(thread)
        return thread
    
    def register_task(self, task: asyncio.Task) -> asyncio.Task:
        """Register an async task for cleanup."""
        with self._lock:
            self.active_tasks.append(task)
        return task
    
    def register_resource(self, resource_name: str, resource: Any, cleanup_func: Callable):
        """Register a generic resource with cleanup function."""
        with self._lock:
            self.resource_registry[resource_name] = {
                "resource": resource,
                "cleanup_func": cleanup_func,
                "registered_at": time.time()
            }
    
    def register_cleanup_callback(self, callback: Callable, priority: int = 0):
        """Register a cleanup callback with optional priority."""
        with self._lock:
            self.cleanup_callbacks.append((priority, callback))
            # Sort by priority (higher priority first)
            self.cleanup_callbacks.sort(key=lambda x: x[0], reverse=True)
    
    def create_temp_file(self, suffix: str = "", prefix: str = "test_", 
                        content: str = None) -> Path:
        """Create and register a temporary file."""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix=suffix, prefix=prefix, delete=False
        ) as temp_file:
            if content:
                temp_file.write(content)
            temp_path = Path(temp_file.name)
        
        return self.register_temp_file(temp_path)
    
    def create_temp_directory(self, suffix: str = "", prefix: str = "test_") -> Path:
        """Create and register a temporary directory."""
        temp_dir = Path(tempfile.mkdtemp(suffix=suffix, prefix=prefix))
        return self.register_temp_directory(temp_dir)
    
    def cleanup_temp_files(self):
        """Clean up all registered temporary files."""
        files_cleaned = 0
        
        for file_path in list(self.temp_files):
            try:
                if file_path.exists():
                    file_path.unlink()
                    files_cleaned += 1
                    logger.debug(f"Cleaned up temp file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp file {file_path}: {e}")
        
        self.temp_files.clear()
        self.cleanup_stats["files_cleaned"] += files_cleaned
    
    def cleanup_temp_directories(self):
        """Clean up all registered temporary directories."""
        directories_cleaned = 0
        
        for dir_path in list(self.temp_directories):
            try:
                if dir_path.exists():
                    # Remove all contents recursively
                    import shutil
                    shutil.rmtree(dir_path)
                    directories_cleaned += 1
                    logger.debug(f"Cleaned up temp directory: {dir_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp directory {dir_path}: {e}")
        
        self.temp_directories.clear()
        self.cleanup_stats["directories_cleaned"] += directories_cleaned
    
    def cleanup_patches(self):
        """Clean up all registered patches."""
        patches_stopped = 0
        
        for patch_obj in list(self.active_patches):
            try:
                patch_obj.stop()
                patches_stopped += 1
                logger.debug(f"Stopped patch: {patch_obj}")
            except Exception as e:
                logger.warning(f"Failed to stop patch {patch_obj}: {e}")
        
        self.active_patches.clear()
        self.cleanup_stats["patches_stopped"] += patches_stopped
    
    def cleanup_threads(self, timeout: float = 5.0):
        """Clean up all registered threads."""
        threads_joined = 0
        
        for thread in list(self.active_threads):
            try:
                if thread.is_alive():
                    thread.join(timeout=timeout)
                    if not thread.is_alive():
                        threads_joined += 1
                        logger.debug(f"Joined thread: {thread.name}")
                    else:
                        logger.warning(f"Thread {thread.name} did not terminate within timeout")
            except Exception as e:
                logger.warning(f"Failed to join thread {thread.name}: {e}")
        
        self.active_threads.clear()
        self.cleanup_stats["threads_joined"] += threads_joined
    
    async def cleanup_tasks(self, timeout: float = 5.0):
        """Clean up all registered async tasks."""
        tasks_cancelled = 0
        
        if not self.active_tasks:
            return
        
        # Cancel all tasks
        for task in self.active_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for cancellation with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*self.active_tasks, return_exceptions=True),
                timeout=timeout
            )
            tasks_cancelled = len(self.active_tasks)
        except asyncio.TimeoutError:
            logger.warning(f"Some tasks did not cancel within {timeout}s timeout")
            tasks_cancelled = sum(1 for task in self.active_tasks if task.done())
        
        self.active_tasks.clear()
        self.cleanup_stats["tasks_cancelled"] += tasks_cancelled
    
    def cleanup_resources(self):
        """Clean up all registered resources."""
        for resource_name, resource_info in list(self.resource_registry.items()):
            try:
                cleanup_func = resource_info["cleanup_func"]
                if asyncio.iscoroutinefunction(cleanup_func):
                    # Handle async cleanup functions
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # Create a task for async cleanup
                            task = loop.create_task(cleanup_func())
                            self.register_task(task)
                        else:
                            loop.run_until_complete(cleanup_func())
                    except RuntimeError:
                        logger.warning(f"Could not run async cleanup for {resource_name}")
                else:
                    cleanup_func()
                
                logger.debug(f"Cleaned up resource: {resource_name}")
            except Exception as e:
                logger.warning(f"Failed to clean up resource {resource_name}: {e}")
        
        self.resource_registry.clear()
    
    def execute_cleanup_callbacks(self):
        """Execute all registered cleanup callbacks."""
        callbacks_executed = 0
        
        for priority, callback in self.cleanup_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    # Handle async callbacks
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            task = loop.create_task(callback())
                            self.register_task(task)
                        else:
                            loop.run_until_complete(callback())
                    except RuntimeError:
                        logger.warning("Could not run async cleanup callback")
                else:
                    callback()
                
                callbacks_executed += 1
                logger.debug(f"Executed cleanup callback (priority: {priority})")
            except Exception as e:
                logger.warning(f"Cleanup callback failed (priority: {priority}): {e}")
        
        self.cleanup_callbacks.clear()
        self.cleanup_stats["callbacks_executed"] += callbacks_executed
    
    def force_garbage_collection(self):
        """Force garbage collection to clean up unreferenced objects."""
        # Run garbage collection multiple times to ensure cleanup
        for _ in range(3):
            collected = gc.collect()
            if collected == 0:
                break
        
        logger.debug(f"Garbage collection completed, collected {collected} objects")
    
    def cleanup_all(self, include_async: bool = True):
        """Perform comprehensive cleanup of all resources."""
        logger.debug("Starting comprehensive test cleanup")
        start_time = time.perf_counter()
        
        try:
            # Execute cleanup callbacks first (highest priority)
            self.execute_cleanup_callbacks()
            
            # Clean up patches
            self.cleanup_patches()
            
            # Clean up threads
            self.cleanup_threads()
            
            # Clean up resources
            self.cleanup_resources()
            
            # Clean up temporary files and directories
            self.cleanup_temp_files()
            self.cleanup_temp_directories()
            
            # Force garbage collection
            self.force_garbage_collection()
            
            # Handle async cleanup if requested
            if include_async and self.active_tasks:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Schedule async cleanup
                        cleanup_task = loop.create_task(self.cleanup_tasks())
                        # Don't wait for it to avoid blocking
                    else:
                        loop.run_until_complete(self.cleanup_tasks())
                except RuntimeError:
                    logger.warning("Could not perform async cleanup")
        
        except Exception as e:
            logger.error(f"Error during comprehensive cleanup: {e}")
        
        finally:
            cleanup_duration = time.perf_counter() - start_time
            logger.debug(f"Comprehensive cleanup completed in {cleanup_duration:.3f}s")
            logger.debug(f"Cleanup stats: {self.cleanup_stats}")
    
    async def async_cleanup_all(self):
        """Perform comprehensive async cleanup of all resources."""
        logger.debug("Starting comprehensive async test cleanup")
        start_time = time.perf_counter()
        
        try:
            # Execute cleanup callbacks first
            self.execute_cleanup_callbacks()
            
            # Clean up async tasks
            await self.cleanup_tasks()
            
            # Clean up other resources
            self.cleanup_patches()
            self.cleanup_threads()
            self.cleanup_resources()
            self.cleanup_temp_files()
            self.cleanup_temp_directories()
            
            # Force garbage collection
            self.force_garbage_collection()
        
        except Exception as e:
            logger.error(f"Error during comprehensive async cleanup: {e}")
        
        finally:
            cleanup_duration = time.perf_counter() - start_time
            logger.debug(f"Comprehensive async cleanup completed in {cleanup_duration:.3f}s")
    
    def get_cleanup_stats(self) -> Dict[str, Any]:
        """Get cleanup statistics."""
        return {
            "cleanup_stats": self.cleanup_stats.copy(),
            "active_resources": {
                "temp_files": len(self.temp_files),
                "temp_directories": len(self.temp_directories),
                "patches": len(self.active_patches),
                "threads": len(self.active_threads),
                "tasks": len(self.active_tasks),
                "resources": len(self.resource_registry),
                "callbacks": len(self.cleanup_callbacks)
            }
        }


class TestErrorHandler:
    """Handles test errors and provides debugging information."""
    
    def __init__(self):
        self.error_history = []
        self.error_patterns = {}
        self.debug_info_collectors = []
    
    def register_debug_info_collector(self, collector: Callable[[], Dict[str, Any]]):
        """Register a function that collects debug information."""
        self.debug_info_collectors.append(collector)
    
    def handle_test_error(self, test_name: str, error: Exception, 
                         collect_debug_info: bool = True) -> Dict[str, Any]:
        """Handle a test error and collect debugging information."""
        error_info = {
            "test_name": test_name,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "timestamp": time.time(),
            "debug_info": {}
        }
        
        # Collect debug information
        if collect_debug_info:
            for collector in self.debug_info_collectors:
                try:
                    debug_data = collector()
                    error_info["debug_info"].update(debug_data)
                except Exception as e:
                    logger.warning(f"Debug info collector failed: {e}")
        
        # Track error patterns
        error_type = type(error)
        if error_type not in self.error_patterns:
            self.error_patterns[error_type] = []
        self.error_patterns[error_type].append(error_info)
        
        # Add to error history
        self.error_history.append(error_info)
        
        # Keep only recent errors (last 100)
        if len(self.error_history) > 100:
            self.error_history = self.error_history[-100:]
        
        return error_info
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of test errors."""
        if not self.error_history:
            return {"message": "No errors recorded"}
        
        # Count errors by type
        error_counts = {}
        for error_info in self.error_history:
            error_type = error_info["error_type"]
            error_counts[error_type] = error_counts.get(error_type, 0) + 1
        
        # Find most common error
        most_common_error = max(error_counts.items(), key=lambda x: x[1])
        
        # Recent errors (last 10)
        recent_errors = self.error_history[-10:]
        
        return {
            "total_errors": len(self.error_history),
            "error_types": error_counts,
            "most_common_error": {
                "type": most_common_error[0],
                "count": most_common_error[1]
            },
            "recent_errors": recent_errors
        }
    
    def suggest_fixes(self, error_type: str) -> List[str]:
        """Suggest fixes for common error types."""
        suggestions = {
            "AssertionError": [
                "Check test expectations and actual values",
                "Verify mock configurations and return values",
                "Ensure test data is set up correctly"
            ],
            "TimeoutError": [
                "Increase timeout values for slow operations",
                "Check for deadlocks or infinite loops",
                "Optimize slow test operations"
            ],
            "ConnectionError": [
                "Verify external service mocks are configured",
                "Check network connectivity in test environment",
                "Ensure proper cleanup of connections"
            ],
            "AttributeError": [
                "Check object initialization and setup",
                "Verify mock object configurations",
                "Ensure proper import statements"
            ],
            "KeyError": [
                "Verify dictionary keys and data structures",
                "Check test data setup and configuration",
                "Ensure proper data initialization"
            ]
        }
        
        return suggestions.get(error_type, [
            "Review test implementation and dependencies",
            "Check for proper setup and teardown",
            "Verify test isolation and cleanup"
        ])


# Global instances
cleanup_manager = TestCleanupManager()
error_handler = TestErrorHandler()


# Pytest fixtures for cleanup and error handling
@pytest.fixture(scope="function")
def test_cleanup_manager():
    """Provide test cleanup manager."""
    return cleanup_manager


@pytest.fixture(scope="function")
def test_error_handler():
    """Provide test error handler."""
    return error_handler


@pytest.fixture(scope="function", autouse=True)
def auto_cleanup():
    """Automatically clean up after each test."""
    yield
    cleanup_manager.cleanup_all()


@pytest.fixture(scope="function")
def temp_file_factory():
    """Factory for creating temporary files."""
    def create_temp_file(content: str = "", suffix: str = ".txt") -> Path:
        return cleanup_manager.create_temp_file(content=content, suffix=suffix)
    
    return create_temp_file


@pytest.fixture(scope="function")
def temp_dir_factory():
    """Factory for creating temporary directories."""
    def create_temp_dir(suffix: str = "") -> Path:
        return cleanup_manager.create_temp_directory(suffix=suffix)
    
    return create_temp_dir


# Context managers for cleanup and error handling
@contextmanager
def managed_test_resources():
    """Context manager for managed test resources."""
    try:
        yield cleanup_manager
    finally:
        cleanup_manager.cleanup_all()


@asynccontextmanager
async def managed_async_test_resources():
    """Async context manager for managed test resources."""
    try:
        yield cleanup_manager
    finally:
        await cleanup_manager.async_cleanup_all()


@contextmanager
def error_handling_context(test_name: str):
    """Context manager for error handling."""
    try:
        yield error_handler
    except Exception as e:
        error_info = error_handler.handle_test_error(test_name, e)
        logger.error(f"Test {test_name} failed: {error_info}")
        raise


# Decorators for cleanup and error handling
def managed_test(cleanup_priority: int = 0):
    """Decorator for managed test execution with cleanup."""
    def decorator(test_func):
        @wraps(test_func)
        def wrapper(*args, **kwargs):
            test_name = test_func.__name__
            
            # Register cleanup callback
            cleanup_manager.register_cleanup_callback(
                lambda: logger.debug(f"Cleaned up after {test_name}"),
                priority=cleanup_priority
            )
            
            try:
                return test_func(*args, **kwargs)
            except Exception as e:
                error_handler.handle_test_error(test_name, e)
                raise
            finally:
                cleanup_manager.cleanup_all()
        
        return wrapper
    return decorator


def error_tracked_test(test_func):
    """Decorator for error tracking in tests."""
    @wraps(test_func)
    def wrapper(*args, **kwargs):
        test_name = test_func.__name__
        
        try:
            return test_func(*args, **kwargs)
        except Exception as e:
            error_info = error_handler.handle_test_error(test_name, e)
            
            # Log suggestions
            suggestions = error_handler.suggest_fixes(type(e).__name__)
            if suggestions:
                logger.info(f"Suggestions for {test_name}: {suggestions}")
            
            raise
    
    return wrapper


# Utility functions
def create_debug_info_collector() -> Callable[[], Dict[str, Any]]:
    """Create a debug info collector for test errors."""
    def collect_debug_info() -> Dict[str, Any]:
        return {
            "timestamp": time.time(),
            "thread_count": threading.active_count(),
            "memory_usage": get_memory_usage(),
            "temp_files": len(cleanup_manager.temp_files),
            "active_patches": len(cleanup_manager.active_patches)
        }
    
    return collect_debug_info


def get_memory_usage() -> Dict[str, float]:
    """Get current memory usage information."""
    try:
        import psutil
        process = psutil.Process()
        memory_info = process.memory_info()
        
        return {
            "rss_mb": memory_info.rss / 1024 / 1024,
            "vms_mb": memory_info.vms / 1024 / 1024,
            "percent": process.memory_percent()
        }
    except ImportError:
        return {"error": "psutil not available"}


def setup_comprehensive_cleanup():
    """Set up comprehensive cleanup for test suite."""
    # Register debug info collector
    error_handler.register_debug_info_collector(create_debug_info_collector())
    
    # Set up cleanup for common resources
    cleanup_manager.register_cleanup_callback(
        lambda: logger.debug("Comprehensive cleanup completed"),
        priority=100
    )


# Initialize comprehensive cleanup
setup_comprehensive_cleanup()
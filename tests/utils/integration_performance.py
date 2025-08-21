"""
Integration test performance optimization utilities.

This module provides specialized utilities for optimizing integration test
performance, including database optimization, service mocking, and resource pooling.
"""

import asyncio
import time
import sqlite3
import threading
from contextlib import contextmanager, asynccontextmanager
from typing import Dict, Any, List, Optional, Callable, Generator, AsyncGenerator
from unittest.mock import Mock, AsyncMock, patch
import pytest
import logging
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool, QueuePool
from concurrent.futures import ThreadPoolExecutor
import weakref

logger = logging.getLogger(__name__)


class IntegrationTestOptimizer:
    """Optimizes integration test performance through resource pooling and caching."""
    
    def __init__(self):
        self.database_engines = {}
        self.session_factories = {}
        self.service_mocks = {}
        self.shared_fixtures = {}
        self.connection_pools = {}
        self.cleanup_callbacks = []
        self._lock = threading.Lock()
        self._thread_pool = None
    
    @property
    def thread_pool(self) -> ThreadPoolExecutor:
        """Get or create thread pool for integration tests."""
        if self._thread_pool is None:
            self._thread_pool = ThreadPoolExecutor(max_workers=3)
            self.register_cleanup(self._thread_pool.shutdown)
        return self._thread_pool
    
    def get_optimized_database_engine(self, test_suite: str = "default") -> Engine:
        """Get or create an optimized database engine for integration tests."""
        if test_suite not in self.database_engines:
            engine = create_engine(
                "sqlite:///:memory:",
                poolclass=StaticPool,
                connect_args={
                    "check_same_thread": False,
                    "timeout": 5.0,
                    "isolation_level": None  # Autocommit mode for speed
                },
                echo=False,
                future=True,
                pool_pre_ping=False,
                pool_recycle=-1,
                # Optimize for integration tests
                execution_options={
                    "isolation_level": "AUTOCOMMIT"
                }
            )
            
            # Configure SQLite for integration test performance
            @event.listens_for(engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                # Performance optimizations for integration tests
                cursor.execute("PRAGMA synchronous=OFF")
                cursor.execute("PRAGMA journal_mode=MEMORY")
                cursor.execute("PRAGMA cache_size=20000")  # Larger cache for integration tests
                cursor.execute("PRAGMA temp_store=MEMORY")
                cursor.execute("PRAGMA mmap_size=536870912")  # 512MB mmap
                cursor.execute("PRAGMA page_size=4096")
                cursor.execute("PRAGMA foreign_keys=ON")  # Enable FK for integration tests
                cursor.execute("PRAGMA auto_vacuum=INCREMENTAL")
                cursor.close()
            
            self.database_engines[test_suite] = engine
        
        return self.database_engines[test_suite]
    
    def get_optimized_session_factory(self, test_suite: str = "default") -> sessionmaker:
        """Get or create an optimized session factory."""
        if test_suite not in self.session_factories:
            engine = self.get_optimized_database_engine(test_suite)
            self.session_factories[test_suite] = sessionmaker(
                bind=engine,
                autoflush=True,  # Enable autoflush for integration tests
                expire_on_commit=False,
                autocommit=False
            )
        
        return self.session_factories[test_suite]
    
    @contextmanager
    def optimized_integration_session(self, test_suite: str = "default") -> Generator[Session, None, None]:
        """Context manager for optimized integration test database sessions."""
        session_factory = self.get_optimized_session_factory(test_suite)
        session = session_factory()
        
        try:
            # Begin transaction for integration test isolation
            session.begin()
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def optimize_database_operations(self, session: Session):
        """Optimize database operations for integration tests."""
        # Batch operations for better performance
        session.execute(text("PRAGMA optimize"))
        
        # Pre-warm commonly used queries
        try:
            # Example: Pre-warm authorization requests table
            session.execute(text("SELECT COUNT(*) FROM authorization_requests LIMIT 1"))
        except Exception:
            pass  # Table might not exist yet
    
    def create_shared_test_fixtures(self, fixture_config: Dict[str, Any]) -> Dict[str, Any]:
        """Create shared fixtures for integration tests."""
        fixtures = {}
        
        # Database connections
        if "database_connections" in fixture_config:
            count = fixture_config["database_connections"]
            fixtures["database_sessions"] = []
            
            for i in range(count):
                session_factory = self.get_optimized_session_factory(f"shared_{i}")
                fixtures["database_sessions"].append(session_factory)
        
        # Mock services
        if "mock_services" in fixture_config:
            services = fixture_config["mock_services"]
            fixtures["mock_services"] = {}
            
            for service_name in services:
                fixtures["mock_services"][service_name] = self.create_optimized_service_mock(service_name)
        
        # Cache shared fixtures
        self.shared_fixtures.update(fixtures)
        return fixtures
    
    def create_optimized_service_mock(self, service_name: str) -> Mock:
        """Create optimized service mocks for integration tests."""
        if service_name in self.service_mocks:
            return self.service_mocks[service_name]
        
        if service_name == "external_api":
            mock = self._create_external_api_mock()
        elif service_name == "llm_service":
            mock = self._create_llm_service_mock()
        elif service_name == "notification_service":
            mock = self._create_notification_service_mock()
        elif service_name == "cache_service":
            mock = self._create_cache_service_mock()
        else:
            mock = Mock(name=f"mock_{service_name}")
        
        self.service_mocks[service_name] = mock
        return mock
    
    def _create_external_api_mock(self) -> Mock:
        """Create external API mock for integration tests."""
        mock_api = Mock()
        
        # CMS API responses
        mock_api.get_cms_guidelines = Mock(return_value={
            "guidelines": ["Test guideline 1", "Test guideline 2"],
            "effective_date": "2024-01-01",
            "version": "1.0"
        })
        
        # Medical code validation
        mock_api.validate_medical_code = Mock(return_value={
            "valid": True,
            "description": "Test medical code description",
            "category": "diagnostic"
        })
        
        # Policy lookup
        mock_api.lookup_policy = Mock(return_value={
            "policy_id": "TEST_POLICY_001",
            "coverage": "covered",
            "requirements": ["Test requirement"]
        })
        
        return mock_api
    
    def _create_llm_service_mock(self) -> AsyncMock:
        """Create LLM service mock for integration tests."""
        mock_llm = AsyncMock()
        
        async def mock_generate_decision(*args, **kwargs):
            # Simulate realistic processing time
            await asyncio.sleep(0.05)
            return {
                "decision": "approved",
                "confidence": 0.92,
                "reasoning": [
                    "Patient meets medical necessity criteria",
                    "Procedure is covered under current policy"
                ],
                "processing_time_ms": 50.0
            }
        
        async def mock_analyze_request(*args, **kwargs):
            await asyncio.sleep(0.03)
            return {
                "analysis": "Request appears valid and complete",
                "risk_factors": [],
                "confidence": 0.95
            }
        
        mock_llm.generate_decision = AsyncMock(side_effect=mock_generate_decision)
        mock_llm.analyze_request = AsyncMock(side_effect=mock_analyze_request)
        mock_llm.is_available = Mock(return_value=True)
        mock_llm.health_check = AsyncMock(return_value={"status": "healthy"})
        
        return mock_llm
    
    def _create_notification_service_mock(self) -> AsyncMock:
        """Create notification service mock for integration tests."""
        mock_notification = AsyncMock()
        
        async def mock_send_notification(*args, **kwargs):
            await asyncio.sleep(0.01)
            return {"sent": True, "message_id": "test_msg_001"}
        
        mock_notification.send_email = AsyncMock(side_effect=mock_send_notification)
        mock_notification.send_sms = AsyncMock(side_effect=mock_send_notification)
        mock_notification.send_dashboard_alert = AsyncMock(side_effect=mock_send_notification)
        
        return mock_notification
    
    def _create_cache_service_mock(self) -> Mock:
        """Create cache service mock for integration tests."""
        mock_cache = Mock()
        cache_storage = {}
        
        def mock_get(key):
            return cache_storage.get(key)
        
        def mock_set(key, value, ttl=None):
            cache_storage[key] = value
            return True
        
        def mock_delete(key):
            return cache_storage.pop(key, None) is not None
        
        mock_cache.get = Mock(side_effect=mock_get)
        mock_cache.set = Mock(side_effect=mock_set)
        mock_cache.delete = Mock(side_effect=mock_delete)
        mock_cache.clear = Mock(side_effect=lambda: cache_storage.clear())
        
        return mock_cache
    
    def create_bulk_test_data_efficiently(self, session: Session, config: Dict[str, Any]) -> Dict[str, List[Any]]:
        """Create bulk test data efficiently for integration tests."""
        test_data = {}
        
        # Create authorization requests
        if "authorization_requests" in config:
            count = config["authorization_requests"]
            requests = []
            
            for i in range(count):
                request_data = {
                    "request_id": f"req_int_{i:06d}",
                    "provider_id": f"prov_{i % 5}",  # Reuse providers
                    "patient_id": f"pat_{i % 20}",   # Reuse patients
                    "diagnosis_code": f"M25.{(i % 999):03d}",
                    "procedure_code": f"7{(i % 9999):04d}",
                    "status": "submitted",
                    "created_at": time.time() - (i * 60)
                }
                requests.append(request_data)
            
            test_data["authorization_requests"] = requests
        
        # Create medical codes
        if "medical_codes" in config:
            count = config["medical_codes"]
            codes = []
            
            for i in range(count):
                code_data = {
                    "code": f"TEST{i:04d}",
                    "description": f"Test medical code {i}",
                    "category": "diagnostic" if i % 2 == 0 else "procedure",
                    "active": True
                }
                codes.append(code_data)
            
            test_data["medical_codes"] = codes
        
        return test_data
    
    def setup_integration_test_environment(self, test_config: Dict[str, Any]):
        """Set up optimized environment for integration tests."""
        # Configure database
        if "database" in test_config:
            db_config = test_config["database"]
            test_suite = db_config.get("test_suite", "default")
            
            # Pre-create database engine
            engine = self.get_optimized_database_engine(test_suite)
            
            # Create tables if schema provided
            if "schema" in db_config:
                with engine.connect() as conn:
                    for table_sql in db_config["schema"]:
                        conn.execute(text(table_sql))
                    conn.commit()
        
        # Configure service mocks
        if "services" in test_config:
            for service_name in test_config["services"]:
                self.create_optimized_service_mock(service_name)
        
        # Set up connection pools
        if "connection_pools" in test_config:
            pool_config = test_config["connection_pools"]
            for pool_name, pool_size in pool_config.items():
                self.connection_pools[pool_name] = []
                for _ in range(pool_size):
                    # Create mock connections
                    conn = Mock()
                    conn.is_active = Mock(return_value=True)
                    conn.close = Mock()
                    self.connection_pools[pool_name].append(conn)
    
    def get_connection_from_pool(self, pool_name: str) -> Optional[Mock]:
        """Get a connection from the pool."""
        if pool_name in self.connection_pools and self.connection_pools[pool_name]:
            return self.connection_pools[pool_name].pop(0)
        return None
    
    def return_connection_to_pool(self, pool_name: str, connection: Mock):
        """Return a connection to the pool."""
        if pool_name in self.connection_pools:
            self.connection_pools[pool_name].append(connection)
    
    def register_cleanup(self, cleanup_func: Callable):
        """Register a cleanup function."""
        self.cleanup_callbacks.append(cleanup_func)
    
    def cleanup_all(self):
        """Clean up all integration test resources."""
        # Run cleanup callbacks
        for callback in self.cleanup_callbacks:
            try:
                callback()
            except Exception as e:
                logger.warning(f"Integration test cleanup callback failed: {e}")
        
        # Dispose database engines
        for engine in self.database_engines.values():
            try:
                engine.dispose()
            except Exception as e:
                logger.warning(f"Database engine disposal failed: {e}")
        
        # Clean up thread pool
        if self._thread_pool:
            self._thread_pool.shutdown(wait=False)
            self._thread_pool = None
        
        # Clear all caches
        self.database_engines.clear()
        self.session_factories.clear()
        self.service_mocks.clear()
        self.shared_fixtures.clear()
        self.connection_pools.clear()
        self.cleanup_callbacks.clear()
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get integration test performance statistics."""
        return {
            "database_engines": len(self.database_engines),
            "session_factories": len(self.session_factories),
            "service_mocks": len(self.service_mocks),
            "shared_fixtures": len(self.shared_fixtures),
            "connection_pools": {
                name: len(pool) for name, pool in self.connection_pools.items()
            },
            "cleanup_callbacks": len(self.cleanup_callbacks)
        }


class AsyncIntegrationTestManager:
    """Manages async resources for integration tests."""
    
    def __init__(self):
        self.async_clients = {}
        self.async_services = {}
        self.event_loops = {}
        self.semaphores = {}
        self.cleanup_tasks = []
    
    async def get_async_client(self, client_type: str, client_id: str = "default") -> AsyncMock:
        """Get or create an async client for integration tests."""
        key = f"{client_type}_{client_id}"
        
        if key not in self.async_clients:
            if client_type == "http_client":
                client = await self._create_http_client()
            elif client_type == "database_client":
                client = await self._create_database_client()
            elif client_type == "message_queue_client":
                client = await self._create_message_queue_client()
            else:
                client = AsyncMock(name=f"async_{client_type}_{client_id}")
            
            self.async_clients[key] = client
        
        return self.async_clients[key]
    
    async def _create_http_client(self) -> AsyncMock:
        """Create async HTTP client mock."""
        client = AsyncMock()
        
        async def mock_request(method, url, **kwargs):
            await asyncio.sleep(0.01)  # Simulate network delay
            return {
                "status_code": 200,
                "json": {"success": True, "data": {}},
                "headers": {"content-type": "application/json"}
            }
        
        client.get = AsyncMock(side_effect=lambda url, **kwargs: mock_request("GET", url, **kwargs))
        client.post = AsyncMock(side_effect=lambda url, **kwargs: mock_request("POST", url, **kwargs))
        client.put = AsyncMock(side_effect=lambda url, **kwargs: mock_request("PUT", url, **kwargs))
        client.delete = AsyncMock(side_effect=lambda url, **kwargs: mock_request("DELETE", url, **kwargs))
        client.aclose = AsyncMock()
        
        return client
    
    async def _create_database_client(self) -> AsyncMock:
        """Create async database client mock."""
        client = AsyncMock()
        
        async def mock_execute(query, *args, **kwargs):
            await asyncio.sleep(0.005)  # Simulate database query time
            return Mock(fetchall=Mock(return_value=[]), rowcount=1)
        
        client.execute = AsyncMock(side_effect=mock_execute)
        client.fetch = AsyncMock(return_value=[])
        client.fetchrow = AsyncMock(return_value=None)
        client.close = AsyncMock()
        
        return client
    
    async def _create_message_queue_client(self) -> AsyncMock:
        """Create async message queue client mock."""
        client = AsyncMock()
        
        async def mock_publish(topic, message, **kwargs):
            await asyncio.sleep(0.002)
            return {"message_id": "test_msg_001", "published": True}
        
        async def mock_subscribe(topic, **kwargs):
            await asyncio.sleep(0.001)
            return AsyncMock()  # Mock subscription
        
        client.publish = AsyncMock(side_effect=mock_publish)
        client.subscribe = AsyncMock(side_effect=mock_subscribe)
        client.close = AsyncMock()
        
        return client
    
    def get_semaphore(self, name: str, value: int = 10) -> asyncio.Semaphore:
        """Get or create a named semaphore for concurrency control."""
        if name not in self.semaphores:
            self.semaphores[name] = asyncio.Semaphore(value)
        return self.semaphores[name]
    
    async def run_concurrent_integration_tests(self, test_functions: List[Callable],
                                             max_concurrency: int = 5) -> List[Any]:
        """Run multiple integration tests concurrently."""
        semaphore = self.get_semaphore("integration_tests", max_concurrency)
        
        async def run_with_semaphore(test_func):
            async with semaphore:
                return await test_func()
        
        tasks = [asyncio.create_task(run_with_semaphore(test_func)) 
                for test_func in test_functions]
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results
        except Exception as e:
            logger.error(f"Concurrent integration tests failed: {e}")
            # Cancel remaining tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
            raise
    
    async def cleanup_async_resources(self):
        """Clean up all async resources."""
        # Close async clients
        for client in self.async_clients.values():
            try:
                if hasattr(client, 'aclose'):
                    await client.aclose()
                elif hasattr(client, 'close'):
                    await client.close()
            except Exception as e:
                logger.warning(f"Error closing async client: {e}")
        
        # Clean up async services
        for service in self.async_services.values():
            try:
                if hasattr(service, 'cleanup'):
                    await service.cleanup()
            except Exception as e:
                logger.warning(f"Error cleaning up async service: {e}")
        
        # Cancel cleanup tasks
        for task in self.cleanup_tasks:
            if not task.done():
                task.cancel()
        
        # Clear all resources
        self.async_clients.clear()
        self.async_services.clear()
        self.semaphores.clear()
        self.cleanup_tasks.clear()


# Global instances
integration_optimizer = IntegrationTestOptimizer()
async_integration_manager = AsyncIntegrationTestManager()


def get_integration_optimizer() -> IntegrationTestOptimizer:
    """Get the global integration test optimizer."""
    return integration_optimizer


def get_async_integration_manager() -> AsyncIntegrationTestManager:
    """Get the global async integration test manager."""
    return async_integration_manager


# Pytest fixtures for integration test optimization
@pytest.fixture(scope="session")
def integration_test_optimizer():
    """Provide integration test optimizer."""
    return integration_optimizer


@pytest.fixture(scope="function")
async def async_integration_manager():
    """Provide async integration test manager."""
    manager = AsyncIntegrationTestManager()
    try:
        yield manager
    finally:
        await manager.cleanup_async_resources()


@pytest.fixture(scope="function")
def optimized_integration_db():
    """Provide optimized database session for integration tests."""
    with integration_optimizer.optimized_integration_session() as session:
        integration_optimizer.optimize_database_operations(session)
        yield session


@pytest.fixture(scope="session")
def shared_integration_fixtures():
    """Provide shared fixtures for integration tests."""
    fixture_config = {
        "database_connections": 3,
        "mock_services": ["external_api", "llm_service", "notification_service"]
    }
    
    fixtures = integration_optimizer.create_shared_test_fixtures(fixture_config)
    yield fixtures


@pytest.fixture(scope="function")
def integration_test_data():
    """Provide test data for integration tests."""
    def create_test_data(session, config):
        return integration_optimizer.create_bulk_test_data_efficiently(session, config)
    
    return create_test_data


@pytest.fixture(scope="session", autouse=True)
def cleanup_integration_resources():
    """Clean up integration test resources after all tests."""
    yield
    integration_optimizer.cleanup_all()


# Context managers for integration test optimization
@contextmanager
def integration_test_environment(config: Dict[str, Any]):
    """Context manager for integration test environment setup."""
    integration_optimizer.setup_integration_test_environment(config)
    
    try:
        yield integration_optimizer
    finally:
        # Cleanup is handled by the autouse fixture
        pass


@asynccontextmanager
async def async_integration_test_context():
    """Async context manager for integration test setup."""
    manager = AsyncIntegrationTestManager()
    
    try:
        yield manager
    finally:
        await manager.cleanup_async_resources()


# Decorators for integration test optimization
def optimized_integration_test(config: Dict[str, Any] = None):
    """Decorator for optimized integration tests."""
    def decorator(test_func):
        @wraps(test_func)
        def wrapper(*args, **kwargs):
            test_config = config or {}
            
            with integration_test_environment(test_config):
                return test_func(*args, **kwargs)
        
        return wrapper
    return decorator


def async_optimized_integration_test(config: Dict[str, Any] = None):
    """Decorator for optimized async integration tests."""
    def decorator(test_func):
        @wraps(test_func)
        async def wrapper(*args, **kwargs):
            async with async_integration_test_context() as manager:
                return await test_func(*args, **kwargs)
        
        return wrapper
    return decorator


# Utility functions for integration test optimization
def create_integration_test_suite(test_functions: List[Callable], 
                                config: Dict[str, Any] = None) -> Callable:
    """Create an optimized integration test suite."""
    def run_test_suite():
        test_config = config or {}
        results = []
        
        with integration_test_environment(test_config):
            for test_func in test_functions:
                try:
                    result = test_func()
                    results.append(("PASS", test_func.__name__, result))
                except Exception as e:
                    results.append(("FAIL", test_func.__name__, str(e)))
        
        return results
    
    return run_test_suite


async def create_async_integration_test_suite(async_test_functions: List[Callable],
                                            max_concurrency: int = 5) -> List[Any]:
    """Create an optimized async integration test suite."""
    async with async_integration_test_context() as manager:
        return await manager.run_concurrent_integration_tests(
            async_test_functions, max_concurrency
        )


def benchmark_integration_test(test_func: Callable, iterations: int = 5) -> Dict[str, Any]:
    """Benchmark an integration test function."""
    times = []
    errors = []
    
    for i in range(iterations):
        start_time = time.perf_counter()
        try:
            test_func()
            duration = time.perf_counter() - start_time
            times.append(duration)
        except Exception as e:
            duration = time.perf_counter() - start_time
            errors.append((i, str(e), duration))
    
    if times:
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
    else:
        avg_time = min_time = max_time = 0
    
    return {
        "iterations": iterations,
        "successful_runs": len(times),
        "failed_runs": len(errors),
        "average_time": avg_time,
        "min_time": min_time,
        "max_time": max_time,
        "times": times,
        "errors": errors
    }
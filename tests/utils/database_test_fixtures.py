"""
Optimized database test fixtures and mocks for comprehensive testing.

This module provides efficient database mocking, transaction handling,
and test data management with proper isolation between tests.
"""

import asyncio
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Generator, Union
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import pytest
from sqlalchemy import create_engine, text, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from sqlalchemy.pool import StaticPool

from src.database.models import (
    Base, AuthorizationRequestDB, AuthorizationDecisionDB, 
    CoveragePolicyDB, AIConfigurationDB
)
from src.models.medical_codes import ICD10CodeDB, CPTCodeDB, HCPCSCodeDB


class OptimizedDatabaseTestManager:
    """Manages optimized database testing with proper isolation and cleanup."""
    
    def __init__(self):
        self._engines = {}
        self._session_factories = {}
        self._test_data_cache = {}
        self._active_sessions = []
    
    def create_test_engine(self, test_name: str = "default") -> Engine:
        """Create an optimized in-memory SQLite engine for testing."""
        if test_name in self._engines:
            return self._engines[test_name]
        
        # Use in-memory SQLite with performance optimizations
        engine = create_engine(
            "sqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={
                "check_same_thread": False,
                "timeout": 1.0  # Fast timeout
            },
            echo=False,  # Disable SQL logging for performance
            future=True,
            pool_pre_ping=False,  # Skip connection validation for speed
            pool_recycle=-1  # No connection recycling
        )
        
        # Configure SQLite for maximum performance in tests
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            # Performance optimizations for testing
            cursor.execute("PRAGMA synchronous=OFF")  # Disable fsync for speed
            cursor.execute("PRAGMA journal_mode=MEMORY")  # In-memory journal
            cursor.execute("PRAGMA cache_size=10000")  # Large cache
            cursor.execute("PRAGMA temp_store=MEMORY")  # Memory temp storage
            cursor.execute("PRAGMA mmap_size=268435456")  # 256MB mmap
            cursor.execute("PRAGMA page_size=4096")  # Optimal page size
            cursor.execute("PRAGMA foreign_keys=OFF")  # Disable FK checks for speed
            cursor.execute("PRAGMA locking_mode=EXCLUSIVE")  # Exclusive locking
            cursor.close()
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        
        self._engines[test_name] = engine
        return engine
    
    def get_test_session_factory(self, test_name: str = "default") -> sessionmaker:
        """Get or create an optimized session factory for testing."""
        if test_name not in self._session_factories:
            engine = self.create_test_engine(test_name)
            self._session_factories[test_name] = sessionmaker(
                bind=engine,
                autoflush=False,  # Manual flushing for control
                expire_on_commit=False,  # Keep objects after commit
                class_=Session  # Use standard Session class
            )
        return self._session_factories[test_name]
    
    @contextmanager
    def get_test_session(self, test_name: str = "default") -> Generator[Session, None, None]:
        """Get a test database session with automatic cleanup."""
        session_factory = self.get_test_session_factory(test_name)
        session = session_factory()
        self._active_sessions.append(session)
        
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            if session in self._active_sessions:
                self._active_sessions.remove(session)
    
    def create_mock_session(self, with_data: bool = True) -> Mock:
        """Create a comprehensive mock database session."""
        mock_session = Mock(spec=Session)
        
        # Configure basic session methods
        mock_session.add = Mock()
        mock_session.commit = Mock()
        mock_session.rollback = Mock()
        mock_session.close = Mock()
        mock_session.flush = Mock()
        mock_session.refresh = Mock()
        mock_session.merge = Mock()
        mock_session.delete = Mock()
        mock_session.expunge = Mock()
        mock_session.expunge_all = Mock()
        
        # Configure query methods
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
        mock_query.distinct = Mock(return_value=mock_query)
        
        # Configure result methods
        if with_data:
            mock_query.first = Mock(return_value=self._create_sample_record())
            mock_query.all = Mock(return_value=[self._create_sample_record()])
            mock_query.one = Mock(return_value=self._create_sample_record())
            mock_query.one_or_none = Mock(return_value=self._create_sample_record())
            mock_query.count = Mock(return_value=1)
            mock_query.exists = Mock(return_value=True)
        else:
            mock_query.first = Mock(return_value=None)
            mock_query.all = Mock(return_value=[])
            mock_query.one_or_none = Mock(return_value=None)
            mock_query.count = Mock(return_value=0)
            mock_query.exists = Mock(return_value=False)
        
        mock_session.query = Mock(return_value=mock_query)
        mock_session.execute = Mock(return_value=Mock(fetchall=Mock(return_value=[])))
        
        # Configure context manager behavior
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=None)
        
        return mock_session
    
    def _create_sample_record(self) -> Mock:
        """Create a sample database record for mocking."""
        record = Mock()
        record.id = 1
        record.created_at = datetime.now(timezone.utc)
        record.updated_at = datetime.now(timezone.utc)
        return record
    
    def populate_test_data(self, session: Session, data_type: str = "comprehensive") -> Dict[str, Any]:
        """Populate test database with sample data."""
        if data_type in self._test_data_cache:
            return self._test_data_cache[data_type]
        
        test_data = {}
        
        if data_type in ["comprehensive", "medical_codes"]:
            # Add ICD-10 codes
            icd10_codes = [
                ICD10CodeDB(
                    code="M25.511",
                    description="Pain in right shoulder",
                    category="Arthropathies",
                    is_billable=True,
                    effective_date=datetime(2024, 1, 1)
                ),
                ICD10CodeDB(
                    code="M54.5", 
                    description="Low back pain",
                    category="Dorsopathies",
                    is_billable=True,
                    effective_date=datetime(2024, 1, 1)
                ),
                ICD10CodeDB(
                    code="G93.1",
                    description="Anoxic brain damage, not elsewhere classified",
                    category="Nervous system diseases",
                    is_billable=True,
                    effective_date=datetime(2024, 1, 1)
                )
            ]
            
            for code in icd10_codes:
                session.add(code)
            
            test_data["icd10_codes"] = icd10_codes
            
            # Add CPT codes
            cpt_codes = [
                CPTCodeDB(
                    code="70551",
                    description="MRI brain without contrast",
                    category="Radiology",
                    rvu_work=2.89,
                    effective_date=datetime(2024, 1, 1)
                ),
                CPTCodeDB(
                    code="72148",
                    description="MRI lumbar spine without contrast", 
                    category="Radiology",
                    rvu_work=2.67,
                    effective_date=datetime(2024, 1, 1)
                ),
                CPTCodeDB(
                    code="73221",
                    description="MRI upper extremity without contrast",
                    category="Radiology", 
                    rvu_work=2.34,
                    effective_date=datetime(2024, 1, 1)
                )
            ]
            
            for code in cpt_codes:
                session.add(code)
            
            test_data["cpt_codes"] = cpt_codes
        
        if data_type in ["comprehensive", "patient_data"]:
            # Patient demographics are stored encrypted in authorization requests
            # So we'll create sample authorization requests with patient data
            pass
        
        if data_type in ["comprehensive", "authorization_data"]:
            # Add authorization requests with encrypted patient data
            auth_requests = []
            
            # Create first request
            request1 = AuthorizationRequestDB(
                request_id="req_test_001",
                provider_id="prov_test_001",
                diagnosis_codes=["G93.1"],
                procedure_codes=["70551"],
                procedure_type="MRI",
                urgency_level="ROUTINE",
                status="SUBMITTED",
                submitted_at=datetime.now(timezone.utc)
            )
            
            # Encrypt patient demographics
            patient_data1 = {
                "patient_id": "enc_pat_test_001",
                "age": 45,
                "gender": "MALE",
                "insurance_id": "enc_ins_test_001",
                "member_id": "enc_mem_test_001"
            }
            request1.encrypt_patient_demographics(patient_data1)
            request1.encrypt_clinical_notes("Patient with persistent headaches")
            
            auth_requests.append(request1)
            session.add(request1)
            
            # Create second request
            request2 = AuthorizationRequestDB(
                request_id="req_test_002", 
                provider_id="prov_test_002",
                diagnosis_codes=["M25.511"],
                procedure_codes=["73221"],
                procedure_type="MRI",
                urgency_level="URGENT",
                status="SUBMITTED",
                submitted_at=datetime.now(timezone.utc)
            )
            
            patient_data2 = {
                "patient_id": "enc_pat_test_002",
                "age": 32,
                "gender": "FEMALE",
                "insurance_id": "enc_ins_test_002",
                "member_id": "enc_mem_test_002"
            }
            request2.encrypt_patient_demographics(patient_data2)
            request2.encrypt_clinical_notes("Shoulder pain after injury")
            
            auth_requests.append(request2)
            session.add(request2)
            
            test_data["auth_requests"] = auth_requests
            
            # Add authorization decisions
            decision1 = AuthorizationDecisionDB(
                decision_id="dec_test_001",
                request_id="req_test_001",
                status="APPROVED",
                reasoning=["Medical necessity criteria met"],
                policy_references=["NCD_220.2"],
                confidence_score=0.95,
                authorization_number="auth_test_001",
                decided_at=datetime.now(timezone.utc)
            )
            
            session.add(decision1)
            test_data["auth_decisions"] = [decision1]
        
        session.commit()
        self._test_data_cache[data_type] = test_data
        return test_data
    
    def create_transaction_mock(self, should_fail: bool = False) -> Mock:
        """Create a mock database transaction."""
        mock_transaction = Mock()
        
        if should_fail:
            mock_transaction.commit.side_effect = Exception("Transaction failed")
            mock_transaction.rollback = Mock()
        else:
            mock_transaction.commit = Mock()
            mock_transaction.rollback = Mock()
        
        mock_transaction.__enter__ = Mock(return_value=mock_transaction)
        mock_transaction.__exit__ = Mock(return_value=None)
        
        return mock_transaction
    
    def create_connection_pool_mock(self, pool_size: int = 5, max_overflow: int = 10) -> Mock:
        """Create a mock connection pool."""
        mock_pool = Mock()
        mock_pool.size = Mock(return_value=pool_size)
        mock_pool.checked_in = Mock(return_value=pool_size - 2)
        mock_pool.checked_out = Mock(return_value=2)
        mock_pool.overflow = Mock(return_value=0)
        mock_pool.invalid = Mock(return_value=0)
        
        # Mock connection checkout/checkin
        mock_connection = Mock()
        mock_pool.connect = Mock(return_value=mock_connection)
        mock_pool.dispose = Mock()
        
        return mock_pool
    
    def cleanup_test_data(self, test_name: str = "default") -> None:
        """Clean up test data and connections."""
        # Close active sessions
        for session in self._active_sessions[:]:
            try:
                session.close()
            except Exception:
                pass
        self._active_sessions.clear()
        
        # Dispose of engines
        if test_name in self._engines:
            self._engines[test_name].dispose()
            del self._engines[test_name]
        
        if test_name in self._session_factories:
            del self._session_factories[test_name]
        
        # Clear test data cache
        if test_name in self._test_data_cache:
            del self._test_data_cache[test_name]
    
    def cleanup_all(self) -> None:
        """Clean up all test resources."""
        for test_name in list(self._engines.keys()):
            self.cleanup_test_data(test_name)
        
        self._test_data_cache.clear()


class DatabaseTestFixtures:
    """Pytest fixtures for database testing."""
    
    def __init__(self):
        self.test_manager = OptimizedDatabaseTestManager()
    
    @pytest.fixture(scope="function")
    def test_db_session(self):
        """Provide a real test database session."""
        with self.test_manager.get_test_session("test_session") as session:
            yield session
        self.test_manager.cleanup_test_data("test_session")
    
    @pytest.fixture(scope="function") 
    def mock_db_session(self):
        """Provide a mock database session."""
        return self.test_manager.create_mock_session()
    
    @pytest.fixture(scope="function")
    def empty_mock_db_session(self):
        """Provide a mock database session with no data."""
        return self.test_manager.create_mock_session(with_data=False)
    
    @pytest.fixture(scope="function")
    def populated_test_db(self):
        """Provide a test database populated with sample data."""
        with self.test_manager.get_test_session("populated_test") as session:
            test_data = self.test_manager.populate_test_data(session, "comprehensive")
            yield session, test_data
        self.test_manager.cleanup_test_data("populated_test")
    
    @pytest.fixture(scope="function")
    def medical_codes_test_db(self):
        """Provide a test database with medical codes data."""
        with self.test_manager.get_test_session("medical_codes_test") as session:
            test_data = self.test_manager.populate_test_data(session, "medical_codes")
            yield session, test_data
        self.test_manager.cleanup_test_data("medical_codes_test")
    
    @pytest.fixture(scope="function")
    def transaction_mock(self):
        """Provide a mock database transaction."""
        return self.test_manager.create_transaction_mock()
    
    @pytest.fixture(scope="function")
    def failing_transaction_mock(self):
        """Provide a mock database transaction that fails."""
        return self.test_manager.create_transaction_mock(should_fail=True)
    
    @pytest.fixture(scope="function")
    def connection_pool_mock(self):
        """Provide a mock connection pool."""
        return self.test_manager.create_connection_pool_mock()
    
    @pytest.fixture(scope="session", autouse=True)
    def cleanup_database_tests(self):
        """Clean up database test resources after all tests."""
        yield
        self.test_manager.cleanup_all()


# Global test manager instance
_test_manager = OptimizedDatabaseTestManager()


def get_test_database_manager() -> OptimizedDatabaseTestManager:
    """Get the global test database manager."""
    return _test_manager


@contextmanager
def isolated_test_database(test_name: str = None) -> Generator[Session, None, None]:
    """Context manager for isolated test database sessions."""
    test_name = test_name or f"isolated_{id(asyncio.current_task() if asyncio.current_task() else 'sync')}"
    
    with _test_manager.get_test_session(test_name) as session:
        try:
            yield session
        finally:
            _test_manager.cleanup_test_data(test_name)


def create_database_mock_patches() -> Dict[str, Any]:
    """Create comprehensive database mock patches."""
    patches = {
        'get_session': patch('src.database.connection.get_session'),
        'get_db_session': patch('src.database.connection.get_db_session'),
        'get_database_manager': patch('src.database.connection.get_database_manager'),
        'DatabaseManager': patch('src.database.connection.DatabaseManager')
    }
    
    # Configure the patches
    mock_session = _test_manager.create_mock_session()
    mock_manager = Mock()
    mock_manager.get_session.return_value.__enter__ = Mock(return_value=mock_session)
    mock_manager.get_session.return_value.__exit__ = Mock(return_value=None)
    mock_manager.health_check.return_value = True
    mock_manager.engine = Mock()
    
    started_patches = {}
    for name, patch_obj in patches.items():
        mock_obj = patch_obj.start()
        
        if name in ['get_session', 'get_db_session']:
            mock_obj.return_value.__enter__ = Mock(return_value=mock_session)
            mock_obj.return_value.__exit__ = Mock(return_value=None)
        elif name == 'get_database_manager':
            mock_obj.return_value = mock_manager
        elif name == 'DatabaseManager':
            mock_obj.return_value = mock_manager
        
        started_patches[name] = mock_obj
    
    return started_patches


def cleanup_database_mock_patches():
    """Clean up all database mock patches."""
    patch.stopall()


# Performance testing utilities
class DatabasePerformanceTestHelper:
    """Helper for database performance testing."""
    
    @staticmethod
    def create_bulk_test_data(session: Session, record_count: int = 1000) -> Dict[str, List[Any]]:
        """Create bulk test data for performance testing."""
        test_data = {"records_created": 0}
        
        # Create bulk ICD-10 codes
        icd10_codes = []
        for i in range(record_count // 3):
            code = ICD10CodeDB(
                code=f"M25.{i:03d}",
                description=f"Test condition {i}",
                category="Test Category",
                is_billable=True,
                effective_date=datetime(2024, 1, 1)
            )
            icd10_codes.append(code)
        
        session.bulk_save_objects(icd10_codes)
        test_data["icd10_codes"] = icd10_codes
        test_data["records_created"] += len(icd10_codes)
        
        # Create bulk CPT codes
        cpt_codes = []
        for i in range(record_count // 3):
            code = CPTCodeDB(
                code=f"7{i:04d}",
                description=f"Test procedure {i}",
                category="Test Category",
                rvu_work=1.0 + (i * 0.01),
                effective_date=datetime(2024, 1, 1)
            )
            cpt_codes.append(code)
        
        session.bulk_save_objects(cpt_codes)
        test_data["cpt_codes"] = cpt_codes
        test_data["records_created"] += len(cpt_codes)
        
        # Create bulk authorization requests
        auth_requests = []
        for i in range(record_count // 3):
            request = AuthorizationRequestDB(
                request_id=f"req_perf_test_{i:06d}",
                provider_id=f"prov_{i % 100}",
                diagnosis_codes=[f"M25.{i % 100:03d}"],
                procedure_codes=[f"7{i % 1000:04d}"],
                procedure_type="MRI",
                urgency_level="ROUTINE",
                status="SUBMITTED",
                submitted_at=datetime.now(timezone.utc)
            )
            
            # Add encrypted patient data
            patient_data = {
                "patient_id": f"enc_pat_{i % 500}",
                "age": 30 + (i % 50),
                "gender": "MALE" if i % 2 == 0 else "FEMALE",
                "insurance_id": f"enc_ins_{i % 200}",
                "member_id": f"enc_mem_{i % 300}"
            }
            request.encrypt_patient_demographics(patient_data)
            request.encrypt_clinical_notes(f"Performance test request {i}")
            
            auth_requests.append(request)
        
        session.bulk_save_objects(auth_requests)
        test_data["auth_requests"] = auth_requests
        test_data["records_created"] += len(auth_requests)
        
        session.commit()
        return test_data
    
    @staticmethod
    def measure_query_performance(session: Session, query_func, iterations: int = 100) -> Dict[str, float]:
        """Measure query performance over multiple iterations."""
        import time
        
        times = []
        for _ in range(iterations):
            start_time = time.perf_counter()
            result = query_func(session)
            end_time = time.perf_counter()
            times.append(end_time - start_time)
        
        return {
            "min_time": min(times),
            "max_time": max(times),
            "avg_time": sum(times) / len(times),
            "total_time": sum(times),
            "iterations": iterations
        }


# Export commonly used fixtures and utilities
database_fixtures = DatabaseTestFixtures()
test_db_session = database_fixtures.test_db_session
mock_db_session = database_fixtures.mock_db_session
empty_mock_db_session = database_fixtures.empty_mock_db_session
populated_test_db = database_fixtures.populated_test_db
medical_codes_test_db = database_fixtures.medical_codes_test_db
transaction_mock = database_fixtures.transaction_mock
failing_transaction_mock = database_fixtures.failing_transaction_mock
connection_pool_mock = database_fixtures.connection_pool_mock
cleanup_database_tests = database_fixtures.cleanup_database_tests
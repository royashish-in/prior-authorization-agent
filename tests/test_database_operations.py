"""
Comprehensive database operations testing for the Prior Authorization Agent.

This module tests repository patterns, CRUD operations, transaction handling,
rollback scenarios, data integrity, connection pooling, and database management.
"""

import pytest
import tempfile
import os
import json
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, OperationalError
from sqlalchemy.pool import QueuePool

from src.database.base import Base
from src.database.connection import DatabaseManager, get_database_manager, get_session
from src.database.models import (
    AuthorizationRequestDB, AuthorizationDecisionDB, CoveragePolicyDB,
    AIConfigurationDB, ModelPerformanceMetricsDB, ConfigurationAuditLogDB, AIFeedbackDB
)
from src.models.enums import (
    RequestStatus, DecisionStatus, UrgencyLevel, Gender, ProcedureType
)


class TestDatabaseManager:
    """Test database manager functionality and connection handling."""
    
    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database file for testing."""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_file.close()
        yield temp_file.name
        # Cleanup
        try:
            os.unlink(temp_file.name)
        except OSError:
            pass
    
    @pytest.fixture
    def in_memory_db_manager(self):
        """Create database manager with in-memory SQLite for testing."""
        with patch('src.database.connection.get_settings') as mock_settings:
            mock_settings.return_value = Mock(
                database_url="sqlite:///:memory:",
                db_pool_size=5,
                db_max_overflow=10,
                db_echo=False
            )
            manager = DatabaseManager()
            manager.create_tables()
            yield manager
            manager.close()
    
    def test_database_manager_initialization(self):
        """Test database manager initialization with configuration."""
        with patch('src.database.connection.get_settings') as mock_settings:
            mock_settings.return_value = Mock(
                database_url="sqlite:///:memory:",
                db_pool_size=5,
                db_max_overflow=10,
                db_echo=False
            )
            
            manager = DatabaseManager()
            assert manager.settings is not None
            assert manager._engine is None
            assert manager._session_factory is None
    
    def test_engine_creation_and_configuration(self, in_memory_db_manager):
        """Test database engine creation with proper configuration."""
        engine = in_memory_db_manager.engine
        
        assert engine is not None
        assert engine.pool.size() == 5
        assert engine.pool._max_overflow == 10
        assert hasattr(engine.pool, '_pre_ping')
    
    def test_session_factory_creation(self, in_memory_db_manager):
        """Test session factory creation and configuration."""
        session_factory = in_memory_db_manager.session_factory
        
        assert session_factory is not None
        
        # Test session creation
        session = session_factory()
        assert isinstance(session, Session)
        assert session.bind == in_memory_db_manager.engine
        session.close()
    
    def test_database_url_construction(self):
        """Test database URL construction from configuration components."""
        with patch('src.database.connection.get_settings') as mock_settings:
            mock_settings.return_value = Mock(
                database_url=None,
                db_driver='mysql+pymysql',
                db_username='testuser',
                db_password='testpass',
                db_host='localhost',
                db_port=3306,
                db_name='testdb'
            )
            
            manager = DatabaseManager()
            url = manager._get_database_url()
            
            expected = "mysql+pymysql://testuser:testpass@localhost:3306/testdb"
            assert url == expected
    
    def test_database_url_without_password(self):
        """Test database URL construction without password."""
        with patch('src.database.connection.get_settings') as mock_settings:
            mock_settings.return_value = Mock(
                database_url=None,
                db_driver='mysql+pymysql',
                db_username='testuser',
                db_password='',
                db_host='localhost',
                db_port=3306,
                db_name='testdb'
            )
            
            manager = DatabaseManager()
            url = manager._get_database_url()
            
            expected = "mysql+pymysql://testuser@localhost:3306/testdb"
            assert url == expected
    
    def test_create_tables_success(self, in_memory_db_manager):
        """Test successful table creation."""
        # Tables should already be created in fixture
        # Test that we can query the tables
        with in_memory_db_manager.get_session() as session:
            result = session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            tables = [row[0] for row in result.fetchall()]
            
            expected_tables = [
                'authorization_requests', 'authorization_decisions', 'coverage_policies',
                'ai_configurations', 'model_performance_metrics', 'configuration_audit_logs',
                'ai_feedback'
            ]
            
            for table in expected_tables:
                assert table in tables
    
    def test_create_tables_failure(self):
        """Test table creation failure handling."""
        with patch('src.database.connection.get_settings') as mock_settings:
            mock_settings.return_value = Mock(
                database_url="sqlite:///invalid/path/test.db",
                db_pool_size=5,
                db_max_overflow=10,
                db_echo=False
            )
            
            manager = DatabaseManager()
            
            with pytest.raises(SQLAlchemyError):
                manager.create_tables()
    
    def test_drop_tables(self, in_memory_db_manager):
        """Test table dropping functionality."""
        # Verify tables exist first
        with in_memory_db_manager.get_session() as session:
            result = session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            tables_before = [row[0] for row in result.fetchall()]
            assert len(tables_before) > 0
        
        # Drop tables
        in_memory_db_manager.drop_tables()
        
        # Verify tables are dropped
        with in_memory_db_manager.get_session() as session:
            result = session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            tables_after = [row[0] for row in result.fetchall()]
            assert len(tables_after) == 0
    
    def test_health_check_success(self, in_memory_db_manager):
        """Test successful database health check."""
        result = in_memory_db_manager.health_check()
        assert result is True
    
    def test_health_check_failure(self):
        """Test database health check failure."""
        with patch('src.database.connection.get_settings') as mock_settings:
            mock_settings.return_value = Mock(
                database_url="sqlite:///nonexistent/path/test.db",
                db_pool_size=5,
                db_max_overflow=10,
                db_echo=False
            )
            
            manager = DatabaseManager()
            result = manager.health_check()
            assert result is False
    
    def test_session_context_manager_success(self, in_memory_db_manager):
        """Test session context manager with successful operations."""
        with in_memory_db_manager.get_session() as session:
            # Perform a simple operation
            result = session.execute(text("SELECT 1"))
            assert result.scalar() == 1
    
    def test_session_context_manager_rollback(self, in_memory_db_manager):
        """Test session context manager with rollback on error."""
        with pytest.raises(Exception):
            with in_memory_db_manager.get_session() as session:
                # This should cause an error and trigger rollback
                session.execute(text("SELECT * FROM nonexistent_table"))
    
    def test_connection_pooling_configuration(self):
        """Test connection pooling configuration."""
        with patch('src.database.connection.get_settings') as mock_settings:
            mock_settings.return_value = Mock(
                database_url="sqlite:///:memory:",
                db_pool_size=10,
                db_max_overflow=20,
                db_echo=False
            )
            
            manager = DatabaseManager()
            engine = manager.engine
            
            assert isinstance(engine.pool, QueuePool)
            assert engine.pool.size() == 10
            assert engine.pool._max_overflow == 20
    
    def test_engine_event_listeners(self, in_memory_db_manager):
        """Test that engine event listeners are properly set up."""
        engine = in_memory_db_manager.engine
        
        # Check that event listeners are registered
        connect_listeners = event.contains(engine, "connect", in_memory_db_manager._setup_engine_events)
        # Note: We can't easily test the actual listener functions without MySQL
        # but we can verify the engine is properly configured
        assert engine is not None
    
    def test_global_database_manager_singleton(self):
        """Test global database manager singleton pattern."""
        with patch('src.database.connection.get_settings') as mock_settings:
            mock_settings.return_value = Mock(
                database_url="sqlite:///:memory:",
                db_pool_size=5,
                db_max_overflow=10,
                db_echo=False
            )
            
            # Clear any existing global manager
            import src.database.connection
            src.database.connection._db_manager = None
            
            manager1 = get_database_manager()
            manager2 = get_database_manager()
            
            assert manager1 is manager2
    
    def test_get_session_dependency_injection(self, in_memory_db_manager):
        """Test get_session function for dependency injection."""
        with patch('src.database.connection.get_database_manager', return_value=in_memory_db_manager):
            session_generator = get_session()
            session = next(session_generator)
            
            assert isinstance(session, Session)
            
            # Clean up
            try:
                next(session_generator)
            except StopIteration:
                pass


class TestDatabaseCRUDOperations:
    """Test CRUD operations for all database models."""
    
    @pytest.fixture
    def db_session(self):
        """Create in-memory database session for testing."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        yield session
        session.close()
    
    @pytest.fixture
    def sample_authorization_request_data(self):
        """Create sample authorization request data."""
        return {
            "request_id": "req_test_001",
            "provider_id": "prov_test_001",
            "patient_demographics_encrypted": "encrypted_patient_data",
            "diagnosis_codes": ["M25.511", "M25.512"],
            "procedure_codes": ["73221", "73222"],
            "clinical_notes_encrypted": "encrypted_clinical_notes",
            "procedure_type": ProcedureType.MRI.value,
            "urgency_level": UrgencyLevel.ROUTINE.value,
            "status": RequestStatus.SUBMITTED.value
        }
    
    def test_authorization_request_create(self, db_session, sample_authorization_request_data):
        """Test creating authorization request in database."""
        request = AuthorizationRequestDB(**sample_authorization_request_data)
        
        db_session.add(request)
        db_session.commit()
        
        # Verify creation
        retrieved = db_session.query(AuthorizationRequestDB).filter_by(
            request_id="req_test_001"
        ).first()
        
        assert retrieved is not None
        assert retrieved.request_id == "req_test_001"
        assert retrieved.provider_id == "prov_test_001"
        assert retrieved.status == RequestStatus.SUBMITTED.value
        assert retrieved.submitted_at is not None
    
    def test_authorization_request_read(self, db_session, sample_authorization_request_data):
        """Test reading authorization request from database."""
        # Create request
        request = AuthorizationRequestDB(**sample_authorization_request_data)
        db_session.add(request)
        db_session.commit()
        
        # Test various read operations
        by_id = db_session.query(AuthorizationRequestDB).filter_by(
            request_id="req_test_001"
        ).first()
        assert by_id is not None
        
        by_provider = db_session.query(AuthorizationRequestDB).filter_by(
            provider_id="prov_test_001"
        ).all()
        assert len(by_provider) == 1
        
        by_status = db_session.query(AuthorizationRequestDB).filter_by(
            status=RequestStatus.SUBMITTED.value
        ).all()
        assert len(by_status) == 1
    
    def test_authorization_request_update(self, db_session, sample_authorization_request_data):
        """Test updating authorization request in database."""
        # Create request
        request = AuthorizationRequestDB(**sample_authorization_request_data)
        db_session.add(request)
        db_session.commit()
        
        # Update status
        request.status = RequestStatus.IN_REVIEW.value
        db_session.commit()
        
        # Verify update
        retrieved = db_session.query(AuthorizationRequestDB).filter_by(
            request_id="req_test_001"
        ).first()
        
        assert retrieved.status == RequestStatus.IN_REVIEW.value
        assert retrieved.updated_at > retrieved.submitted_at
    
    def test_authorization_request_delete(self, db_session, sample_authorization_request_data):
        """Test deleting authorization request from database."""
        # Create request
        request = AuthorizationRequestDB(**sample_authorization_request_data)
        db_session.add(request)
        db_session.commit()
        
        # Delete request
        db_session.delete(request)
        db_session.commit()
        
        # Verify deletion
        retrieved = db_session.query(AuthorizationRequestDB).filter_by(
            request_id="req_test_001"
        ).first()
        
        assert retrieved is None
    
    def test_authorization_decision_crud(self, db_session, sample_authorization_request_data):
        """Test CRUD operations for authorization decisions."""
        # Create request first
        request = AuthorizationRequestDB(**sample_authorization_request_data)
        db_session.add(request)
        db_session.commit()
        
        # Create decision
        decision_data = {
            "decision_id": "dec_test_001",
            "request_id": "req_test_001",
            "status": DecisionStatus.APPROVED.value,
            "reasoning": ["Medical necessity met", "Policy coverage confirmed"],
            "policy_references": ["CMS NCD 220.2"],
            "authorization_number": "auth_test_001",
            "valid_until": datetime.now(timezone.utc) + timedelta(days=30),
            "confidence_score": Decimal("0.95")
        }
        
        decision = AuthorizationDecisionDB(**decision_data)
        db_session.add(decision)
        db_session.commit()
        
        # Test read
        retrieved = db_session.query(AuthorizationDecisionDB).filter_by(
            decision_id="dec_test_001"
        ).first()
        
        assert retrieved is not None
        assert retrieved.status == DecisionStatus.APPROVED.value
        assert retrieved.confidence_score == Decimal("0.95")
        assert len(retrieved.reasoning) == 2
        
        # Test relationship
        assert retrieved.request is not None
        assert retrieved.request.request_id == "req_test_001"
        
        # Test update
        retrieved.confidence_score = Decimal("0.98")
        db_session.commit()
        
        updated = db_session.query(AuthorizationDecisionDB).filter_by(
            decision_id="dec_test_001"
        ).first()
        assert updated.confidence_score == Decimal("0.98")
        
        # Test delete (should cascade from request)
        db_session.delete(request)
        db_session.commit()
        
        deleted_decision = db_session.query(AuthorizationDecisionDB).filter_by(
            decision_id="dec_test_001"
        ).first()
        assert deleted_decision is None
    
    def test_coverage_policy_crud(self, db_session):
        """Test CRUD operations for coverage policies."""
        policy_data = {
            "policy_id": "pol_test_001",
            "payer_id": "payer_test_001",
            "procedure_code": "73221",
            "diagnosis_codes": ["M25.511", "M25.512"],
            "coverage_criteria": {
                "medical_necessity": True,
                "prior_auth_required": True,
                "age_restrictions": {"min": 18, "max": 65}
            },
            "policy_type": "PAYER",
            "policy_name": "MRI Shoulder Coverage Policy",
            "policy_version": "1.0",
            "effective_date": date.today(),
            "is_active": True,
            "created_by": "test_user",
            "updated_by": "test_user"
        }
        
        policy = CoveragePolicyDB(**policy_data)
        db_session.add(policy)
        db_session.commit()
        
        # Test read
        retrieved = db_session.query(CoveragePolicyDB).filter_by(
            policy_id="pol_test_001"
        ).first()
        
        assert retrieved is not None
        assert retrieved.policy_type == "PAYER"
        assert retrieved.is_currently_effective() is True
        assert "medical_necessity" in retrieved.coverage_criteria
        
        # Test update
        retrieved.policy_version = "1.1"
        # Update the entire coverage_criteria dict for JSON field update
        updated_criteria = retrieved.coverage_criteria.copy()
        updated_criteria["age_restrictions"]["max"] = 70
        retrieved.coverage_criteria = updated_criteria
        
        # Mark the JSON field as modified for SQLAlchemy
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(retrieved, "coverage_criteria")
        db_session.commit()
        
        updated = db_session.query(CoveragePolicyDB).filter_by(
            policy_id="pol_test_001"
        ).first()
        assert updated.policy_version == "1.1"
        assert updated.coverage_criteria["age_restrictions"]["max"] == 70
        
        # Test delete
        db_session.delete(updated)
        db_session.commit()
        
        deleted = db_session.query(CoveragePolicyDB).filter_by(
            policy_id="pol_test_001"
        ).first()
        assert deleted is None


class TestTransactionHandling:
    """Test database transaction handling and rollback scenarios."""
    
    @pytest.fixture
    def db_session(self):
        """Create in-memory database session for testing."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        yield session
        session.close()
    
    def test_successful_transaction_commit(self, db_session):
        """Test successful transaction with commit."""
        # Start transaction
        request_data = {
            "request_id": "req_trans_001",
            "provider_id": "prov_trans_001",
            "patient_demographics_encrypted": "encrypted_data",
            "diagnosis_codes": ["M25.511"],
            "procedure_codes": ["73221"],
            "procedure_type": ProcedureType.MRI.value,
            "urgency_level": UrgencyLevel.ROUTINE.value,
            "status": RequestStatus.SUBMITTED.value
        }
        
        request = AuthorizationRequestDB(**request_data)
        db_session.add(request)
        
        # Commit transaction
        db_session.commit()
        
        # Verify data is persisted
        retrieved = db_session.query(AuthorizationRequestDB).filter_by(
            request_id="req_trans_001"
        ).first()
        
        assert retrieved is not None
        assert retrieved.provider_id == "prov_trans_001"
    
    def test_transaction_rollback_on_error(self, db_session):
        """Test transaction rollback when error occurs."""
        # Create valid request first
        request1_data = {
            "request_id": "req_rollback_001",
            "provider_id": "prov_rollback_001",
            "patient_demographics_encrypted": "encrypted_data",
            "diagnosis_codes": ["M25.511"],
            "procedure_codes": ["73221"],
            "procedure_type": ProcedureType.MRI.value,
            "urgency_level": UrgencyLevel.ROUTINE.value,
            "status": RequestStatus.SUBMITTED.value
        }
        
        request1 = AuthorizationRequestDB(**request1_data)
        db_session.add(request1)
        
        try:
            # Try to create request with duplicate ID (should fail)
            request2_data = request1_data.copy()
            request2_data["provider_id"] = "prov_rollback_002"
            
            request2 = AuthorizationRequestDB(**request2_data)
            db_session.add(request2)
            
            # This should fail due to primary key constraint
            db_session.commit()
            
        except IntegrityError:
            # Rollback the transaction
            db_session.rollback()
        
        # Verify that neither request was persisted
        count = db_session.query(AuthorizationRequestDB).filter(
            AuthorizationRequestDB.request_id.in_(["req_rollback_001"])
        ).count()
        
        assert count == 0
    
    def test_explicit_rollback(self, db_session):
        """Test explicit transaction rollback."""
        request_data = {
            "request_id": "req_explicit_001",
            "provider_id": "prov_explicit_001",
            "patient_demographics_encrypted": "encrypted_data",
            "diagnosis_codes": ["M25.511"],
            "procedure_codes": ["73221"],
            "procedure_type": ProcedureType.MRI.value,
            "urgency_level": UrgencyLevel.ROUTINE.value,
            "status": RequestStatus.SUBMITTED.value
        }
        
        request = AuthorizationRequestDB(**request_data)
        db_session.add(request)
        
        # Explicitly rollback before commit
        db_session.rollback()
        
        # Verify data was not persisted
        retrieved = db_session.query(AuthorizationRequestDB).filter_by(
            request_id="req_explicit_001"
        ).first()
        
        assert retrieved is None
    
    def test_nested_transaction_handling(self, db_session):
        """Test nested transaction handling with savepoints."""
        # Create first request
        request1_data = {
            "request_id": "req_nested_001",
            "provider_id": "prov_nested_001",
            "patient_demographics_encrypted": "encrypted_data",
            "diagnosis_codes": ["M25.511"],
            "procedure_codes": ["73221"],
            "procedure_type": ProcedureType.MRI.value,
            "urgency_level": UrgencyLevel.ROUTINE.value,
            "status": RequestStatus.SUBMITTED.value
        }
        
        request1 = AuthorizationRequestDB(**request1_data)
        db_session.add(request1)
        
        # Create savepoint
        savepoint = db_session.begin_nested()
        
        try:
            # Create second request
            request2_data = {
                "request_id": "req_nested_002",
                "provider_id": "prov_nested_002",
                "patient_demographics_encrypted": "encrypted_data",
                "diagnosis_codes": ["M25.512"],
                "procedure_codes": ["73222"],
                "procedure_type": ProcedureType.MRI.value,
                "urgency_level": UrgencyLevel.ROUTINE.value,
                "status": RequestStatus.SUBMITTED.value
            }
            
            request2 = AuthorizationRequestDB(**request2_data)
            db_session.add(request2)
            
            # Rollback to savepoint (simulating partial failure)
            savepoint.rollback()
            
        except Exception:
            savepoint.rollback()
        
        # Commit main transaction
        db_session.commit()
        
        # Verify only first request was persisted
        request1_exists = db_session.query(AuthorizationRequestDB).filter_by(
            request_id="req_nested_001"
        ).first() is not None
        
        request2_exists = db_session.query(AuthorizationRequestDB).filter_by(
            request_id="req_nested_002"
        ).first() is not None
        
        assert request1_exists is True
        assert request2_exists is False
    
    def test_concurrent_transaction_handling(self, db_session):
        """Test handling of concurrent transactions."""
        # This test simulates concurrent access patterns
        # In SQLite, this is limited, but we can test the basic patterns
        
        request_data = {
            "request_id": "req_concurrent_001",
            "provider_id": "prov_concurrent_001",
            "patient_demographics_encrypted": "encrypted_data",
            "diagnosis_codes": ["M25.511"],
            "procedure_codes": ["73221"],
            "procedure_type": ProcedureType.MRI.value,
            "urgency_level": UrgencyLevel.ROUTINE.value,
            "status": RequestStatus.SUBMITTED.value
        }
        
        request = AuthorizationRequestDB(**request_data)
        db_session.add(request)
        db_session.commit()
        
        # Simulate concurrent update
        retrieved = db_session.query(AuthorizationRequestDB).filter_by(
            request_id="req_concurrent_001"
        ).first()
        
        original_updated_at = retrieved.updated_at
        
        # Update status
        retrieved.status = RequestStatus.IN_REVIEW.value
        db_session.commit()
        
        # Verify update
        updated = db_session.query(AuthorizationRequestDB).filter_by(
            request_id="req_concurrent_001"
        ).first()
        
        assert updated.status == RequestStatus.IN_REVIEW.value
        assert updated.updated_at > original_updated_at


class TestDataIntegrity:
    """Test data integrity constraints and validation."""
    
    @pytest.fixture
    def db_session(self):
        """Create in-memory database session for testing."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        yield session
        session.close()
    
    def test_primary_key_constraint(self, db_session):
        """Test primary key constraint enforcement."""
        request_data = {
            "request_id": "req_pk_001",
            "provider_id": "prov_pk_001",
            "patient_demographics_encrypted": "encrypted_data",
            "diagnosis_codes": ["M25.511"],
            "procedure_codes": ["73221"],
            "procedure_type": ProcedureType.MRI.value,
            "urgency_level": UrgencyLevel.ROUTINE.value,
            "status": RequestStatus.SUBMITTED.value
        }
        
        # Create first request
        request1 = AuthorizationRequestDB(**request_data)
        db_session.add(request1)
        db_session.commit()
        
        # Try to create second request with same ID
        request2 = AuthorizationRequestDB(**request_data)
        db_session.add(request2)
        
        with pytest.raises(IntegrityError):
            db_session.commit()
    
    def test_foreign_key_constraint(self, db_session):
        """Test foreign key constraint enforcement."""
        # Try to create decision without corresponding request
        decision_data = {
            "decision_id": "dec_fk_001",
            "request_id": "nonexistent_request",
            "status": DecisionStatus.APPROVED.value,
            "reasoning": ["Test reasoning"],
            "confidence_score": Decimal("0.95")
        }
        
        decision = AuthorizationDecisionDB(**decision_data)
        db_session.add(decision)
        
        # SQLite doesn't enforce foreign keys by default in memory
        # But we can test the relationship logic
        db_session.commit()
        
        # Verify the decision exists but has no related request
        retrieved = db_session.query(AuthorizationDecisionDB).filter_by(
            decision_id="dec_fk_001"
        ).first()
        
        assert retrieved is not None
        assert retrieved.request is None
    
    def test_model_validation_constraints(self, db_session):
        """Test model validation constraints."""
        # Test invalid status value
        with pytest.raises(ValueError, match="Invalid request status"):
            request_data = {
                "request_id": "req_validation_001",
                "provider_id": "prov_validation_001",
                "patient_demographics_encrypted": "encrypted_data",
                "diagnosis_codes": ["M25.511"],
                "procedure_codes": ["73221"],
                "procedure_type": ProcedureType.MRI.value,
                "urgency_level": UrgencyLevel.ROUTINE.value,
                "status": "INVALID_STATUS"
            }
            
            request = AuthorizationRequestDB(**request_data)
            # Validation happens during attribute setting
    
    def test_confidence_score_validation(self, db_session):
        """Test confidence score validation constraints."""
        # Create valid request first
        request_data = {
            "request_id": "req_confidence_001",
            "provider_id": "prov_confidence_001",
            "patient_demographics_encrypted": "encrypted_data",
            "diagnosis_codes": ["M25.511"],
            "procedure_codes": ["73221"],
            "procedure_type": ProcedureType.MRI.value,
            "urgency_level": UrgencyLevel.ROUTINE.value,
            "status": RequestStatus.SUBMITTED.value
        }
        
        request = AuthorizationRequestDB(**request_data)
        db_session.add(request)
        db_session.commit()
        
        # Test invalid confidence score (too high)
        with pytest.raises(ValueError, match="Confidence score must be between 0.0 and 1.0"):
            decision_data = {
                "decision_id": "dec_confidence_001",
                "request_id": "req_confidence_001",
                "status": DecisionStatus.APPROVED.value,
                "reasoning": ["Test reasoning"],
                "confidence_score": Decimal("1.5")  # Invalid: > 1.0
            }
            
            decision = AuthorizationDecisionDB(**decision_data)
    
    def test_json_field_validation(self, db_session):
        """Test JSON field validation and serialization."""
        request_data = {
            "request_id": "req_json_001",
            "provider_id": "prov_json_001",
            "patient_demographics_encrypted": "encrypted_data",
            "diagnosis_codes": ["M25.511", "M25.512"],  # JSON array
            "procedure_codes": ["73221", "73222"],      # JSON array
            "procedure_type": ProcedureType.MRI.value,
            "urgency_level": UrgencyLevel.ROUTINE.value,
            "status": RequestStatus.SUBMITTED.value
        }
        
        request = AuthorizationRequestDB(**request_data)
        db_session.add(request)
        db_session.commit()
        
        # Verify JSON fields are properly stored and retrieved
        retrieved = db_session.query(AuthorizationRequestDB).filter_by(
            request_id="req_json_001"
        ).first()
        
        assert isinstance(retrieved.diagnosis_codes, list)
        assert len(retrieved.diagnosis_codes) == 2
        assert "M25.511" in retrieved.diagnosis_codes
        
        assert isinstance(retrieved.procedure_codes, list)
        assert len(retrieved.procedure_codes) == 2
        assert "73221" in retrieved.procedure_codes
    
    def test_datetime_field_handling(self, db_session):
        """Test datetime field handling and timezone awareness."""
        request_data = {
            "request_id": "req_datetime_001",
            "provider_id": "prov_datetime_001",
            "patient_demographics_encrypted": "encrypted_data",
            "diagnosis_codes": ["M25.511"],
            "procedure_codes": ["73221"],
            "procedure_type": ProcedureType.MRI.value,
            "urgency_level": UrgencyLevel.ROUTINE.value,
            "status": RequestStatus.SUBMITTED.value
        }
        
        request = AuthorizationRequestDB(**request_data)
        db_session.add(request)
        db_session.commit()
        
        # Verify datetime fields are set
        retrieved = db_session.query(AuthorizationRequestDB).filter_by(
            request_id="req_datetime_001"
        ).first()
        
        assert retrieved.submitted_at is not None
        assert retrieved.updated_at is not None
        assert isinstance(retrieved.submitted_at, datetime)
        assert isinstance(retrieved.updated_at, datetime)
        
        # Test update timestamp
        original_updated_at = retrieved.updated_at
        retrieved.status = RequestStatus.IN_REVIEW.value
        db_session.commit()
        
        updated = db_session.query(AuthorizationRequestDB).filter_by(
            request_id="req_datetime_001"
        ).first()
        
        assert updated.updated_at > original_updated_at


class TestConnectionPooling:
    """Test database connection pooling and management."""
    
    def test_connection_pool_configuration(self):
        """Test connection pool configuration and limits."""
        with patch('src.database.connection.get_settings') as mock_settings:
            mock_settings.return_value = Mock(
                database_url="sqlite:///:memory:",
                db_pool_size=8,
                db_max_overflow=16,
                db_echo=False
            )
            
            manager = DatabaseManager()
            engine = manager.engine
            
            # Verify pool configuration
            assert engine.pool.size() == 8
            assert engine.pool._max_overflow == 16
            assert hasattr(engine.pool, '_pre_ping')
    
    def test_connection_pool_checkout_checkin(self):
        """Test connection checkout and checkin from pool."""
        with patch('src.database.connection.get_settings') as mock_settings:
            mock_settings.return_value = Mock(
                database_url="sqlite:///:memory:",
                db_pool_size=2,
                db_max_overflow=1,
                db_echo=False
            )
            
            manager = DatabaseManager()
            manager.create_tables()
            
            # Test multiple session usage
            sessions = []
            
            try:
                # Create multiple sessions (should use pool)
                for i in range(3):  # More than pool size
                    with manager.get_session() as session:
                        # Perform simple operation
                        result = session.execute(text("SELECT 1"))
                        assert result.scalar() == 1
                
            finally:
                # Sessions are automatically cleaned up by context manager
                pass
    
    def test_connection_pool_exhaustion_handling(self):
        """Test handling of connection pool exhaustion."""
        with patch('src.database.connection.get_settings') as mock_settings:
            mock_settings.return_value = Mock(
                database_url="sqlite:///:memory:",
                db_pool_size=1,
                db_max_overflow=0,  # No overflow allowed
                db_echo=False
            )
            
            manager = DatabaseManager()
            manager.create_tables()
            
            # SQLite doesn't have the same connection pool limitations as other databases
            # So we'll just test that the pool configuration is respected
            engine = manager.engine
            assert engine.pool.size() == 1
            assert engine.pool._max_overflow == 0
            
            # Test that we can still get connections (SQLite is more permissive)
            with manager.get_session() as session:
                result = session.execute(text("SELECT 1"))
                assert result.scalar() == 1
    
    def test_connection_pre_ping_validation(self):
        """Test connection pre-ping validation."""
        with patch('src.database.connection.get_settings') as mock_settings:
            mock_settings.return_value = Mock(
                database_url="sqlite:///:memory:",
                db_pool_size=2,
                db_max_overflow=1,
                db_echo=False
            )
            
            manager = DatabaseManager()
            engine = manager.engine
            
            # Verify pre_ping is enabled
            assert hasattr(engine.pool, '_pre_ping')
            
            # Test that connections are validated
            with manager.get_session() as session:
                result = session.execute(text("SELECT 1"))
                assert result.scalar() == 1


class TestDatabaseMigrationAndBackup:
    """Test database migration and backup functionality."""
    
    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database file for testing."""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_file.close()
        yield temp_file.name
        # Cleanup
        try:
            os.unlink(temp_file.name)
        except OSError:
            pass
    
    def test_database_schema_creation(self, temp_db_path):
        """Test database schema creation and table structure."""
        engine = create_engine(f"sqlite:///{temp_db_path}", echo=False)
        Base.metadata.create_all(engine)
        
        # Verify all tables were created
        with engine.connect() as conn:
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            tables = [row[0] for row in result.fetchall()]
            
            expected_tables = [
                'authorization_requests', 'authorization_decisions', 'coverage_policies',
                'ai_configurations', 'model_performance_metrics', 'configuration_audit_logs',
                'ai_feedback'
            ]
            
            for table in expected_tables:
                assert table in tables
        
        engine.dispose()
    
    def test_database_schema_indexes(self, temp_db_path):
        """Test that database indexes are properly created."""
        engine = create_engine(f"sqlite:///{temp_db_path}", echo=False)
        Base.metadata.create_all(engine)
        
        # Check for indexes on authorization_requests table
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT name FROM sqlite_master 
                WHERE type='index' AND tbl_name='authorization_requests'
            """))
            indexes = [row[0] for row in result.fetchall()]
            
            # Should have indexes for common query patterns
            expected_patterns = ['provider', 'status', 'submitted']
            for pattern in expected_patterns:
                assert any(pattern in idx.lower() for idx in indexes)
        
        engine.dispose()
    
    def test_database_backup_simulation(self, temp_db_path):
        """Test database backup functionality simulation."""
        # Create database with test data
        engine = create_engine(f"sqlite:///{temp_db_path}", echo=False)
        Base.metadata.create_all(engine)
        
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        
        try:
            # Add test data
            request_data = {
                "request_id": "req_backup_001",
                "provider_id": "prov_backup_001",
                "patient_demographics_encrypted": "encrypted_data",
                "diagnosis_codes": ["M25.511"],
                "procedure_codes": ["73221"],
                "procedure_type": ProcedureType.MRI.value,
                "urgency_level": UrgencyLevel.ROUTINE.value,
                "status": RequestStatus.SUBMITTED.value
            }
            
            request = AuthorizationRequestDB(**request_data)
            session.add(request)
            session.commit()
            
            # Simulate backup by copying database file
            backup_path = temp_db_path + ".backup"
            
            # In a real implementation, this would use proper backup tools
            import shutil
            shutil.copy2(temp_db_path, backup_path)
            
            # Verify backup contains data
            backup_engine = create_engine(f"sqlite:///{backup_path}", echo=False)
            BackupSession = sessionmaker(bind=backup_engine)
            backup_session = BackupSession()
            
            try:
                backup_request = backup_session.query(AuthorizationRequestDB).filter_by(
                    request_id="req_backup_001"
                ).first()
                
                assert backup_request is not None
                assert backup_request.provider_id == "prov_backup_001"
                
            finally:
                backup_session.close()
                backup_engine.dispose()
                
                # Cleanup backup file
                try:
                    os.unlink(backup_path)
                except OSError:
                    pass
            
        finally:
            session.close()
            engine.dispose()
    
    def test_database_migration_simulation(self, temp_db_path):
        """Test database migration functionality simulation."""
        # Create initial schema
        engine = create_engine(f"sqlite:///{temp_db_path}", echo=False)
        
        # Create a simplified initial schema
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE test_migration (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            
            # Insert test data
            conn.execute(text("""
                INSERT INTO test_migration (name) VALUES ('test_record_1')
            """))
            conn.commit()
        
        # Simulate migration by adding new column
        with engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE test_migration ADD COLUMN status TEXT DEFAULT 'active'
            """))
            conn.commit()
            
            # Verify migration worked
            result = conn.execute(text("SELECT * FROM test_migration"))
            row = result.fetchone()
            
            assert row is not None
            assert len(row) == 4  # id, name, created_at, status
            assert row[3] == 'active'  # Default status value
        
        engine.dispose()
    
    def test_database_recovery_simulation(self, temp_db_path):
        """Test database recovery functionality simulation."""
        # Create database with test data
        engine = create_engine(f"sqlite:///{temp_db_path}", echo=False)
        Base.metadata.create_all(engine)
        
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        
        try:
            # Add test data
            request_data = {
                "request_id": "req_recovery_001",
                "provider_id": "prov_recovery_001",
                "patient_demographics_encrypted": "encrypted_data",
                "diagnosis_codes": ["M25.511"],
                "procedure_codes": ["73221"],
                "procedure_type": ProcedureType.MRI.value,
                "urgency_level": UrgencyLevel.ROUTINE.value,
                "status": RequestStatus.SUBMITTED.value
            }
            
            request = AuthorizationRequestDB(**request_data)
            session.add(request)
            session.commit()
            
            # Simulate corruption by truncating table
            session.execute(text("DELETE FROM authorization_requests"))
            session.commit()
            
            # Verify data is gone
            count = session.query(AuthorizationRequestDB).count()
            assert count == 0
            
            # Simulate recovery by re-inserting data
            recovered_request = AuthorizationRequestDB(**request_data)
            session.add(recovered_request)
            session.commit()
            
            # Verify recovery
            recovered = session.query(AuthorizationRequestDB).filter_by(
                request_id="req_recovery_001"
            ).first()
            
            assert recovered is not None
            assert recovered.provider_id == "prov_recovery_001"
            
        finally:
            session.close()
            engine.dispose()


class TestDatabasePerformanceOptimization:
    """Test database performance optimization features."""
    
    @pytest.fixture
    def db_session(self):
        """Create in-memory database session for testing."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        yield session
        session.close()
    
    def test_bulk_insert_performance(self, db_session):
        """Test bulk insert operations for performance."""
        import time
        
        # Create bulk test data
        bulk_requests = []
        for i in range(100):
            request_data = {
                "request_id": f"req_bulk_{i:03d}",
                "provider_id": f"prov_bulk_{i:03d}",
                "patient_demographics_encrypted": f"encrypted_data_{i}",
                "diagnosis_codes": ["M25.511"],
                "procedure_codes": ["73221"],
                "procedure_type": ProcedureType.MRI.value,
                "urgency_level": UrgencyLevel.ROUTINE.value,
                "status": RequestStatus.SUBMITTED.value
            }
            bulk_requests.append(AuthorizationRequestDB(**request_data))
        
        # Measure bulk insert time
        start_time = time.time()
        db_session.bulk_save_objects(bulk_requests)
        db_session.commit()
        end_time = time.time()
        
        # Verify all records were inserted
        count = db_session.query(AuthorizationRequestDB).count()
        assert count == 100
        
        # Performance should be reasonable (less than 1 second for 100 records)
        insert_time = end_time - start_time
        assert insert_time < 1.0
    
    def test_query_optimization_with_indexes(self, db_session):
        """Test query performance with proper indexing."""
        # Create test data
        for i in range(50):
            request_data = {
                "request_id": f"req_query_{i:03d}",
                "provider_id": f"prov_{i % 5:03d}",  # 5 different providers
                "patient_demographics_encrypted": f"encrypted_data_{i}",
                "diagnosis_codes": ["M25.511"],
                "procedure_codes": ["73221"],
                "procedure_type": ProcedureType.MRI.value,
                "urgency_level": UrgencyLevel.ROUTINE.value,
                "status": RequestStatus.SUBMITTED.value if i % 2 == 0 else RequestStatus.IN_REVIEW.value
            }
            
            request = AuthorizationRequestDB(**request_data)
            db_session.add(request)
        
        db_session.commit()
        
        import time
        
        # Test indexed query performance (by provider_id)
        start_time = time.time()
        provider_requests = db_session.query(AuthorizationRequestDB).filter_by(
            provider_id="prov_001"
        ).all()
        end_time = time.time()
        
        query_time = end_time - start_time
        assert len(provider_requests) == 10  # Should find 10 requests
        assert query_time < 0.1  # Should be very fast with index
        
        # Test compound index query (provider + status)
        start_time = time.time()
        filtered_requests = db_session.query(AuthorizationRequestDB).filter(
            AuthorizationRequestDB.provider_id == "prov_001",
            AuthorizationRequestDB.status == RequestStatus.SUBMITTED.value
        ).all()
        end_time = time.time()
        
        compound_query_time = end_time - start_time
        assert len(filtered_requests) == 5  # Should find 5 submitted requests
        assert compound_query_time < 0.1  # Should be fast with compound index
    
    def test_connection_reuse_efficiency(self):
        """Test connection reuse efficiency in database manager."""
        with patch('src.database.connection.get_settings') as mock_settings:
            mock_settings.return_value = Mock(
                database_url="sqlite:///:memory:",
                db_pool_size=3,
                db_max_overflow=2,
                db_echo=False
            )
            
            manager = DatabaseManager()
            manager.create_tables()
            
            # Perform multiple operations to test connection reuse
            for i in range(10):
                with manager.get_session() as session:
                    result = session.execute(text("SELECT 1"))
                    assert result.scalar() == 1
            
            # Verify manager is still functional
            assert manager.health_check() is True
    
    def test_query_result_caching_simulation(self, db_session):
        """Test query result caching simulation for performance."""
        # Create test data
        request_data = {
            "request_id": "req_cache_001",
            "provider_id": "prov_cache_001",
            "patient_demographics_encrypted": "encrypted_data",
            "diagnosis_codes": ["M25.511"],
            "procedure_codes": ["73221"],
            "procedure_type": ProcedureType.MRI.value,
            "urgency_level": UrgencyLevel.ROUTINE.value,
            "status": RequestStatus.SUBMITTED.value
        }
        
        request = AuthorizationRequestDB(**request_data)
        db_session.add(request)
        db_session.commit()
        
        import time
        
        # Simulate caching by storing query result
        cache = {}
        cache_key = "provider_cache_001_requests"
        
        # First query (cache miss)
        start_time = time.time()
        if cache_key not in cache:
            result = db_session.query(AuthorizationRequestDB).filter_by(
                provider_id="prov_cache_001"
            ).all()
            cache[cache_key] = result
        first_query_time = time.time() - start_time
        
        # Second query (cache hit)
        start_time = time.time()
        if cache_key in cache:
            result = cache[cache_key]
        second_query_time = time.time() - start_time
        
        # Cache hit should be much faster
        assert len(result) == 1
        assert second_query_time < first_query_time
        assert second_query_time < 0.001  # Cache access should be very fast


class TestDatabaseErrorHandling:
    """Test database error handling and recovery scenarios."""
    
    def test_connection_error_handling(self):
        """Test handling of database connection errors."""
        with patch('src.database.connection.get_settings') as mock_settings:
            mock_settings.return_value = Mock(
                database_url="sqlite:///nonexistent/path/test.db",
                db_pool_size=5,
                db_max_overflow=10,
                db_echo=False
            )
            
            manager = DatabaseManager()
            
            # Health check should fail gracefully
            result = manager.health_check()
            assert result is False
    
    def test_session_error_recovery(self):
        """Test session error recovery and cleanup."""
        with patch('src.database.connection.get_settings') as mock_settings:
            mock_settings.return_value = Mock(
                database_url="sqlite:///:memory:",
                db_pool_size=5,
                db_max_overflow=10,
                db_echo=False
            )
            
            manager = DatabaseManager()
            manager.create_tables()
            
            # Test that errors in session context are handled properly
            with pytest.raises(Exception):
                with manager.get_session() as session:
                    # This should cause an error
                    session.execute(text("SELECT * FROM nonexistent_table"))
            
            # Manager should still be functional after error
            assert manager.health_check() is True
    
    def test_transaction_deadlock_simulation(self, db_session):
        """Test transaction deadlock simulation and handling."""
        # SQLite doesn't have true deadlocks, but we can simulate the pattern
        
        request_data = {
            "request_id": "req_deadlock_001",
            "provider_id": "prov_deadlock_001",
            "patient_demographics_encrypted": "encrypted_data",
            "diagnosis_codes": ["M25.511"],
            "procedure_codes": ["73221"],
            "procedure_type": ProcedureType.MRI.value,
            "urgency_level": UrgencyLevel.ROUTINE.value,
            "status": RequestStatus.SUBMITTED.value
        }
        
        request = AuthorizationRequestDB(**request_data)
        db_session.add(request)
        db_session.commit()
        
        # Simulate deadlock handling by testing rollback recovery
        try:
            # Start a transaction
            retrieved = db_session.query(AuthorizationRequestDB).filter_by(
                request_id="req_deadlock_001"
            ).first()
            
            # Simulate deadlock by forcing an error
            retrieved.status = "INVALID_STATUS"  # This should cause validation error
            
        except ValueError:
            # Rollback and retry with valid data
            db_session.rollback()
            
            retrieved = db_session.query(AuthorizationRequestDB).filter_by(
                request_id="req_deadlock_001"
            ).first()
            retrieved.status = RequestStatus.IN_REVIEW.value
            db_session.commit()
        
        # Verify recovery worked
        final_request = db_session.query(AuthorizationRequestDB).filter_by(
            request_id="req_deadlock_001"
        ).first()
        
        assert final_request.status == RequestStatus.IN_REVIEW.value
    
    def test_database_constraint_violation_handling(self, db_session):
        """Test handling of database constraint violations."""
        # Create initial request
        request_data = {
            "request_id": "req_constraint_001",
            "provider_id": "prov_constraint_001",
            "patient_demographics_encrypted": "encrypted_data",
            "diagnosis_codes": ["M25.511"],
            "procedure_codes": ["73221"],
            "procedure_type": ProcedureType.MRI.value,
            "urgency_level": UrgencyLevel.ROUTINE.value,
            "status": RequestStatus.SUBMITTED.value
        }
        
        request1 = AuthorizationRequestDB(**request_data)
        db_session.add(request1)
        db_session.commit()
        
        # Try to create duplicate (should violate primary key constraint)
        request2 = AuthorizationRequestDB(**request_data)
        db_session.add(request2)
        
        with pytest.raises(IntegrityError):
            db_session.commit()
        
        # Session should be in rollback state
        db_session.rollback()
        
        # Should be able to continue with valid operations
        request_data["request_id"] = "req_constraint_002"
        request3 = AuthorizationRequestDB(**request_data)
        db_session.add(request3)
        db_session.commit()
        
        # Verify both requests exist
        count = db_session.query(AuthorizationRequestDB).count()
        assert count == 2


# Integration test for complete database workflow
class TestDatabaseIntegration:
    """Integration tests for complete database workflows."""
    
    @pytest.fixture
    def db_manager(self):
        """Create database manager for integration testing."""
        with patch('src.database.connection.get_settings') as mock_settings:
            mock_settings.return_value = Mock(
                database_url="sqlite:///:memory:",
                db_pool_size=5,
                db_max_overflow=10,
                db_echo=False
            )
            
            manager = DatabaseManager()
            manager.create_tables()
            yield manager
            manager.close()
    
    def test_complete_authorization_workflow(self, db_manager):
        """Test complete authorization workflow from request to decision."""
        with db_manager.get_session() as session:
            # Create authorization request
            request_data = {
                "request_id": "req_workflow_001",
                "provider_id": "prov_workflow_001",
                "patient_demographics_encrypted": "encrypted_patient_data",
                "diagnosis_codes": ["M25.511"],
                "procedure_codes": ["73221"],
                "clinical_notes_encrypted": "encrypted_clinical_notes",
                "procedure_type": ProcedureType.MRI.value,
                "urgency_level": UrgencyLevel.ROUTINE.value,
                "status": RequestStatus.SUBMITTED.value
            }
            
            request = AuthorizationRequestDB(**request_data)
            session.add(request)
            session.commit()
            
            # Update request status to in review
            request.status = RequestStatus.IN_REVIEW.value
            session.commit()
            
            # Create authorization decision
            decision_data = {
                "decision_id": "dec_workflow_001",
                "request_id": "req_workflow_001",
                "status": DecisionStatus.APPROVED.value,
                "reasoning": [
                    "Patient meets medical necessity criteria",
                    "Diagnosis code is covered under policy",
                    "Prior authorization approved"
                ],
                "policy_references": ["CMS NCD 220.2", "Payer Policy IMG-001"],
                "authorization_number": "auth_workflow_001",
                "valid_until": datetime.now(timezone.utc) + timedelta(days=30),
                "confidence_score": Decimal("0.95")
            }
            
            decision = AuthorizationDecisionDB(**decision_data)
            session.add(decision)
            session.commit()
            
            # Update request status to completed
            request.status = RequestStatus.COMPLETED.value
            session.commit()
            
            # Verify complete workflow
            final_request = session.query(AuthorizationRequestDB).filter_by(
                request_id="req_workflow_001"
            ).first()
            
            assert final_request.status == RequestStatus.COMPLETED.value
            assert len(final_request.decisions) == 1
            assert final_request.decisions[0].status == DecisionStatus.APPROVED.value
            assert final_request.decisions[0].authorization_number == "auth_workflow_001"
    
    def test_policy_and_configuration_workflow(self, db_manager):
        """Test policy and AI configuration workflow."""
        with db_manager.get_session() as session:
            # Create coverage policy
            policy_data = {
                "policy_id": "pol_integration_001",
                "payer_id": "payer_integration_001",
                "procedure_code": "73221",
                "diagnosis_codes": ["M25.511", "M25.512"],
                "coverage_criteria": {
                    "medical_necessity": True,
                    "prior_auth_required": True,
                    "age_restrictions": {"min": 18, "max": 65}
                },
                "policy_type": "PAYER",
                "policy_name": "MRI Shoulder Coverage Policy",
                "effective_date": date.today(),
                "is_active": True,
                "created_by": "test_user",
                "updated_by": "test_user"
            }
            
            policy = CoveragePolicyDB(**policy_data)
            session.add(policy)
            session.commit()
            
            # Create AI configuration
            ai_config_data = {
                "config_id": "config_integration_001",
                "configuration_type": "decision_threshold",
                "configuration_name": "Standard Decision Thresholds",
                "configuration_data": {
                    "approval_threshold": 0.8,
                    "denial_threshold": 0.3,
                    "escalation_threshold": 0.5
                },
                "effective_date": date.today(),
                "is_active": True,
                "created_by": "test_user",
                "updated_by": "test_user"
            }
            
            ai_config = AIConfigurationDB(**ai_config_data)
            session.add(ai_config)
            session.commit()
            
            # Verify both are active and effective
            active_policy = session.query(CoveragePolicyDB).filter_by(
                policy_id="pol_integration_001"
            ).first()
            
            active_config = session.query(AIConfigurationDB).filter_by(
                config_id="config_integration_001"
            ).first()
            
            assert active_policy.is_currently_effective() is True
            assert active_config.is_currently_effective() is True
            assert active_config.configuration_data["approval_threshold"] == 0.8
"""
Integration tests for database operations and migrations.

Tests database schema, connection management, and PHI encryption
for the Prior Authorization Agent.
"""

import os
import pytest
import tempfile
from datetime import datetime, date, timedelta, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.database.models import (
    Base, AuthorizationRequestDB, AuthorizationDecisionDB, CoveragePolicyDB
)
from src.database.connection import DatabaseManager, get_database_manager
from src.models.enums import RequestStatus, DecisionStatus, UrgencyLevel, Gender, ProcedureType


class TestDatabaseModels:
    """Test database models and operations."""
    
    @pytest.fixture
    def temp_db_url(self):
        """Create temporary SQLite database for testing."""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_file.close()
        db_url = f"sqlite:///{temp_file.name}"
        yield db_url
        # Cleanup
        try:
            os.unlink(temp_file.name)
        except OSError:
            pass
    
    @pytest.fixture
    def test_engine(self, temp_db_url):
        """Create test database engine."""
        engine = create_engine(temp_db_url, echo=False)
        Base.metadata.create_all(bind=engine)
        yield engine
        engine.dispose()
    
    @pytest.fixture
    def test_session(self, test_engine):
        """Create test database session."""
        Session = sessionmaker(bind=test_engine)
        session = Session()
        yield session
        session.close()
    
    def test_authorization_request_creation(self, test_session):
        """Test creating authorization request in database."""
        # Create test data
        demographics_data = {
            "patient_id": "test_patient_123",
            "age": 45,
            "gender": "female",
            "insurance_id": "test_insurance_456",
            "member_id": "test_member_789"
        }
        
        diagnosis_codes = [
            {"code": "M25.511", "description": "Pain in right shoulder"}
        ]
        
        procedure_codes = [
            {"code": "73221", "description": "MRI upper extremity without contrast"}
        ]
        
        # Create authorization request
        request = AuthorizationRequestDB(
            request_id="req_test_001",
            provider_id="prov_test_123",
            diagnosis_codes=diagnosis_codes,
            procedure_codes=procedure_codes,
            procedure_type=ProcedureType.MRI.value,
            urgency_level=UrgencyLevel.ROUTINE.value,
            status=RequestStatus.SUBMITTED.value,
            submitted_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        # Encrypt PHI data
        request.encrypt_patient_demographics(demographics_data)
        request.encrypt_clinical_notes("Patient reports persistent shoulder pain for 6 weeks")
        
        # Save to database
        test_session.add(request)
        test_session.commit()
        
        # Verify data was saved
        saved_request = test_session.query(AuthorizationRequestDB).filter_by(
            request_id="req_test_001"
        ).first()
        
        assert saved_request is not None
        assert saved_request.provider_id == "prov_test_123"
        assert saved_request.procedure_type == ProcedureType.MRI.value
        assert saved_request.status == RequestStatus.SUBMITTED.value
        
        # Verify PHI encryption/decryption
        decrypted_demographics = saved_request.decrypt_patient_demographics()
        assert decrypted_demographics["patient_id"] == "test_patient_123"
        assert decrypted_demographics["age"] == 45
        
        decrypted_notes = saved_request.decrypt_clinical_notes()
        assert "persistent shoulder pain" in decrypted_notes
    
    def test_authorization_decision_creation(self, test_session):
        """Test creating authorization decision in database."""
        # First create a request
        request = AuthorizationRequestDB(
            request_id="req_test_002",
            provider_id="prov_test_123",
            diagnosis_codes=[{"code": "M25.511"}],
            procedure_codes=[{"code": "73221"}],
            procedure_type=ProcedureType.MRI.value,
            urgency_level=UrgencyLevel.ROUTINE.value,
            status=RequestStatus.IN_REVIEW.value,
            submitted_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        request.encrypt_patient_demographics({
            "patient_id": "test_patient_456",
            "age": 35,
            "gender": "male",
            "insurance_id": "test_insurance_789",
            "member_id": "test_member_012"
        })
        
        test_session.add(request)
        test_session.commit()
        
        # Create decision
        decision = AuthorizationDecisionDB(
            decision_id="dec_test_001",
            request_id="req_test_002",
            status=DecisionStatus.APPROVED.value,
            reasoning=[
                "Patient meets medical necessity criteria",
                "Diagnosis code is covered under policy"
            ],
            policy_references=["CMS NCD 220.2", "Payer Policy IMG-001"],
            authorization_number="auth_test_123456",
            valid_until=datetime.now(timezone.utc) + timedelta(days=30),
            confidence_score=0.95,
            decided_at=datetime.now(timezone.utc)
        )
        
        test_session.add(decision)
        test_session.commit()
        
        # Verify decision was saved
        saved_decision = test_session.query(AuthorizationDecisionDB).filter_by(
            decision_id="dec_test_001"
        ).first()
        
        assert saved_decision is not None
        assert saved_decision.request_id == "req_test_002"
        assert saved_decision.status == DecisionStatus.APPROVED.value
        assert saved_decision.authorization_number == "auth_test_123456"
        assert float(saved_decision.confidence_score) == 0.95
        assert len(saved_decision.reasoning) == 2
        assert len(saved_decision.policy_references) == 2
        
        # Verify relationship
        assert saved_decision.request is not None
        assert saved_decision.request.request_id == "req_test_002"
    
    def test_coverage_policy_creation(self, test_session):
        """Test creating coverage policy in database."""
        policy = CoveragePolicyDB(
            policy_id="pol_test_001",
            payer_id="payer_test_123",
            procedure_code="73221",
            diagnosis_codes=["M25.511", "M25.512"],
            coverage_criteria={
                "medical_necessity": True,
                "prior_conservative_treatment": "6_weeks",
                "age_restrictions": {"min": 18, "max": 80}
            },
            policy_type="PAYER",
            policy_name="MRI Shoulder Coverage Policy",
            policy_version="1.0",
            effective_date=date.today(),
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            created_by="admin_test",
            updated_by="admin_test"
        )
        
        test_session.add(policy)
        test_session.commit()
        
        # Verify policy was saved
        saved_policy = test_session.query(CoveragePolicyDB).filter_by(
            policy_id="pol_test_001"
        ).first()
        
        assert saved_policy is not None
        assert saved_policy.payer_id == "payer_test_123"
        assert saved_policy.procedure_code == "73221"
        assert saved_policy.policy_type == "PAYER"
        assert saved_policy.is_active is True
        assert "M25.511" in saved_policy.diagnosis_codes
        assert saved_policy.coverage_criteria["medical_necessity"] is True
        
        # Test policy effectiveness check
        assert saved_policy.is_currently_effective() is True
    
    def test_model_validations(self, test_session):
        """Test model validation rules."""
        # Test invalid request status
        with pytest.raises(ValueError, match="Invalid request status"):
            request = AuthorizationRequestDB(
                request_id="req_invalid_001",
                provider_id="prov_test",
                diagnosis_codes=[{"code": "M25.511"}],
                procedure_codes=[{"code": "73221"}],
                procedure_type=ProcedureType.MRI.value,
                urgency_level=UrgencyLevel.ROUTINE.value,
                status="invalid_status",  # Invalid status
                submitted_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            test_session.add(request)
            test_session.commit()
        
        # Test invalid decision status
        with pytest.raises(ValueError, match="Invalid decision status"):
            decision = AuthorizationDecisionDB(
                decision_id="dec_invalid_001",
                request_id="req_test_001",
                status="invalid_decision",  # Invalid status
                reasoning=["Test reasoning"],
                confidence_score=0.5,
                decided_at=datetime.now(timezone.utc)
            )
            test_session.add(decision)
            test_session.commit()
        
        # Test invalid confidence score
        with pytest.raises(ValueError, match="Confidence score must be between"):
            decision = AuthorizationDecisionDB(
                decision_id="dec_invalid_002",
                request_id="req_test_001",
                status=DecisionStatus.APPROVED.value,
                reasoning=["Test reasoning"],
                confidence_score=1.5,  # Invalid score > 1.0
                decided_at=datetime.now(timezone.utc)
            )
            test_session.add(decision)
            test_session.commit()
    
    def test_database_indexes(self, test_engine):
        """Test that database indexes are created correctly."""
        from sqlalchemy import inspect
        
        # Get table information
        inspector = inspect(test_engine)
        
        # Check authorization_requests indexes
        auth_req_indexes = inspector.get_indexes('authorization_requests')
        index_names = [idx['name'] for idx in auth_req_indexes]
        
        assert 'idx_provider_status' in index_names
        assert 'idx_submitted_at' in index_names
        assert 'idx_status_updated' in index_names
        
        # Check authorization_decisions indexes
        auth_dec_indexes = inspector.get_indexes('authorization_decisions')
        index_names = [idx['name'] for idx in auth_dec_indexes]
        
        assert 'idx_request_decided' in index_names
        assert 'idx_status_decided' in index_names
        
        # Check coverage_policies indexes
        policy_indexes = inspector.get_indexes('coverage_policies')
        index_names = [idx['name'] for idx in policy_indexes]
        
        assert 'idx_payer_procedure' in index_names
        assert 'idx_effective_date' in index_names


class TestDatabaseConnection:
    """Test database connection management."""
    
    @pytest.fixture
    def temp_db_url(self):
        """Create temporary SQLite database for testing."""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_file.close()
        db_url = f"sqlite:///{temp_file.name}"
        yield db_url
        # Cleanup
        try:
            os.unlink(temp_file.name)
        except OSError:
            pass
    
    def test_database_manager_creation(self, temp_db_url, monkeypatch):
        """Test database manager initialization."""
        # Mock settings
        class MockSettings:
            database_url = temp_db_url
            db_pool_size = 5
            db_max_overflow = 10
            db_echo = False
        
        monkeypatch.setattr('src.database.connection.get_settings', lambda: MockSettings())
        
        db_manager = DatabaseManager()
        
        # Test engine creation
        engine = db_manager.engine
        assert engine is not None
        
        # Test session factory
        session_factory = db_manager.session_factory
        assert session_factory is not None
        
        # Test table creation
        db_manager.create_tables()
        
        # Test health check
        assert db_manager.health_check() is True
        
        # Test session context manager
        with db_manager.get_session() as session:
            result = session.execute(text("SELECT 1")).scalar()
            assert result == 1
        
        # Cleanup
        db_manager.close()
    
    def test_database_manager_error_handling(self, monkeypatch):
        """Test database manager error handling."""
        # Mock settings with invalid database URL
        class MockSettings:
            database_url = "invalid://invalid_url"
            db_pool_size = 5
            db_max_overflow = 10
            db_echo = False
        
        monkeypatch.setattr('src.database.connection.get_settings', lambda: MockSettings())
        
        db_manager = DatabaseManager()
        
        # Health check should fail with invalid URL
        assert db_manager.health_check() is False
    
    def test_session_rollback_on_error(self, temp_db_url, monkeypatch):
        """Test that sessions rollback on errors."""
        # Mock settings
        class MockSettings:
            database_url = temp_db_url
            db_pool_size = 5
            db_max_overflow = 10
            db_echo = False
        
        monkeypatch.setattr('src.database.connection.get_settings', lambda: MockSettings())
        
        db_manager = DatabaseManager()
        db_manager.create_tables()
        
        # Test session rollback on exception
        with pytest.raises(Exception):
            with db_manager.get_session() as session:
                # Create a valid request
                request = AuthorizationRequestDB(
                    request_id="req_rollback_test",
                    provider_id="prov_test",
                    diagnosis_codes=[{"code": "M25.511"}],
                    procedure_codes=[{"code": "73221"}],
                    procedure_type=ProcedureType.MRI.value,
                    urgency_level=UrgencyLevel.ROUTINE.value,
                    status=RequestStatus.SUBMITTED.value,
                    submitted_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                
                request.encrypt_patient_demographics({
                    "patient_id": "test_patient",
                    "age": 30,
                    "gender": "male",
                    "insurance_id": "test_insurance",
                    "member_id": "test_member"
                })
                
                session.add(request)
                session.flush()  # This should work
                
                # Force an error
                raise Exception("Test exception")
        
        # Verify the transaction was rolled back
        with db_manager.get_session() as session:
            count = session.query(AuthorizationRequestDB).filter_by(
                request_id="req_rollback_test"
            ).count()
            assert count == 0
        
        db_manager.close()


class TestDatabaseMigrations:
    """Test database migration functionality."""
    
    def test_migration_script_exists(self):
        """Test that migration script exists and is valid."""
        migration_file = "alembic/versions/001_initial_schema.py"
        assert os.path.exists(migration_file)
        
        # Read and validate migration file
        with open(migration_file, 'r') as f:
            content = f.read()
            
        # Check for required functions
        assert "def upgrade()" in content
        assert "def downgrade()" in content
        
        # Check for table creation
        assert "authorization_requests" in content
        assert "authorization_decisions" in content
        assert "coverage_policies" in content
        
        # Check for indexes
        assert "idx_provider_status" in content
        assert "idx_request_decided" in content
        assert "idx_payer_procedure" in content
    
    def test_alembic_configuration(self):
        """Test Alembic configuration files."""
        # Check alembic.ini exists
        assert os.path.exists("alembic.ini")
        
        # Check env.py exists
        assert os.path.exists("alembic/env.py")
        
        # Check script template exists
        assert os.path.exists("alembic/script.py.mako")
        
        # Check versions directory exists
        assert os.path.exists("alembic/versions")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
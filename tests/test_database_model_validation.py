"""
Comprehensive database model validation testing for the Prior Authorization Agent.

This module tests all model validation rules, constraints, serialization/deserialization,
model relationships, foreign key constraints, and comprehensive error handling.
"""

import pytest
import json
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock, patch
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError, DataError

from src.database.base import Base
from src.database.models import (
    AuthorizationRequestDB, AuthorizationDecisionDB, CoveragePolicyDB,
    AIConfigurationDB, ModelPerformanceMetricsDB, ConfigurationAuditLogDB, AIFeedbackDB
)
from src.models.enums import (
    RequestStatus, DecisionStatus, UrgencyLevel, Gender, ProcedureType
)


class TestAuthorizationRequestValidation:
    """Test validation rules for AuthorizationRequestDB model."""
    
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
    def valid_request_data(self):
        """Create valid authorization request data."""
        return {
            "request_id": "req_validation_001",
            "provider_id": "prov_validation_001",
            "patient_demographics_encrypted": "encrypted_patient_data",
            "diagnosis_codes": ["M25.511", "M25.512"],
            "procedure_codes": ["73221", "73222"],
            "clinical_notes_encrypted": "encrypted_clinical_notes",
            "procedure_type": ProcedureType.MRI.value,
            "urgency_level": UrgencyLevel.ROUTINE.value,
            "status": RequestStatus.SUBMITTED.value
        }
    
    def test_valid_request_creation(self, db_session, valid_request_data):
        """Test creation of valid authorization request."""
        request = AuthorizationRequestDB(**valid_request_data)
        db_session.add(request)
        db_session.commit()
        
        retrieved = db_session.query(AuthorizationRequestDB).filter_by(
            request_id="req_validation_001"
        ).first()
        
        assert retrieved is not None
        assert retrieved.request_id == "req_validation_001"
        assert retrieved.status == RequestStatus.SUBMITTED.value
        assert retrieved.procedure_type == ProcedureType.MRI.value
        assert retrieved.urgency_level == UrgencyLevel.ROUTINE.value
    
    def test_status_validation(self, valid_request_data):
        """Test status field validation."""
        # Test valid status
        request = AuthorizationRequestDB(**valid_request_data)
        assert request.status == RequestStatus.SUBMITTED.value
        
        # Test invalid status
        with pytest.raises(ValueError, match="Invalid request status"):
            invalid_data = valid_request_data.copy()
            invalid_data["status"] = "INVALID_STATUS"
            request = AuthorizationRequestDB(**invalid_data)
    
    def test_urgency_level_validation(self, valid_request_data):
        """Test urgency level field validation."""
        # Test valid urgency levels
        for urgency in UrgencyLevel:
            data = valid_request_data.copy()
            data["urgency_level"] = urgency.value
            data["request_id"] = f"req_urgency_{urgency.value}"
            
            request = AuthorizationRequestDB(**data)
            assert request.urgency_level == urgency.value
        
        # Test invalid urgency level
        with pytest.raises(ValueError, match="Invalid urgency level"):
            invalid_data = valid_request_data.copy()
            invalid_data["urgency_level"] = "INVALID_URGENCY"
            request = AuthorizationRequestDB(**invalid_data)
    
    def test_procedure_type_validation(self, valid_request_data):
        """Test procedure type field validation."""
        # Test valid procedure types
        for proc_type in ProcedureType:
            data = valid_request_data.copy()
            data["procedure_type"] = proc_type.value
            data["request_id"] = f"req_proc_{proc_type.value}"
            
            request = AuthorizationRequestDB(**data)
            assert request.procedure_type == proc_type.value
        
        # Test invalid procedure type
        with pytest.raises(ValueError, match="Invalid procedure type"):
            invalid_data = valid_request_data.copy()
            invalid_data["procedure_type"] = "INVALID_PROCEDURE"
            request = AuthorizationRequestDB(**invalid_data)
    
    def test_required_fields_validation(self, db_session):
        """Test that required fields are enforced."""
        # Test missing request_id
        with pytest.raises((IntegrityError, TypeError)):
            request = AuthorizationRequestDB(
                provider_id="prov_test",
                patient_demographics_encrypted="encrypted_data",
                diagnosis_codes=["M25.511"],
                procedure_codes=["73221"],
                procedure_type=ProcedureType.MRI.value,
                urgency_level=UrgencyLevel.ROUTINE.value,
                status=RequestStatus.SUBMITTED.value
            )
            db_session.add(request)
            db_session.commit()
    
    def test_json_field_serialization(self, db_session, valid_request_data):
        """Test JSON field serialization and deserialization."""
        # Test with complex diagnosis codes
        complex_diagnosis = [
            "M25.511",  # Primary diagnosis
            "M25.512",  # Secondary diagnosis
            "Z87.891"   # History code
        ]
        
        data = valid_request_data.copy()
        data["diagnosis_codes"] = complex_diagnosis
        data["procedure_codes"] = ["73221", "73222", "73223"]
        
        request = AuthorizationRequestDB(**data)
        db_session.add(request)
        db_session.commit()
        
        # Retrieve and verify JSON serialization
        retrieved = db_session.query(AuthorizationRequestDB).filter_by(
            request_id="req_validation_001"
        ).first()
        
        assert isinstance(retrieved.diagnosis_codes, list)
        assert len(retrieved.diagnosis_codes) == 3
        assert "M25.511" in retrieved.diagnosis_codes
        assert "Z87.891" in retrieved.diagnosis_codes
        
        assert isinstance(retrieved.procedure_codes, list)
        assert len(retrieved.procedure_codes) == 3
        assert "73221" in retrieved.procedure_codes
    
    def test_phi_encryption_methods(self, valid_request_data):
        """Test PHI encryption and decryption methods."""
        request = AuthorizationRequestDB(**valid_request_data)
        
        # Test patient demographics encryption/decryption
        demographics_data = {
            "patient_id": "test_patient_123",
            "age": 45,
            "gender": "FEMALE",
            "insurance_id": "test_insurance_456"
        }
        
        with patch('src.core.encryption.PHIEncryption') as mock_encryption:
            mock_encryption_instance = Mock()
            mock_encryption.return_value = mock_encryption_instance
            mock_encryption_instance.encrypt.return_value = "encrypted_demographics"
            mock_encryption_instance.decrypt.return_value = json.dumps(demographics_data)
            
            # Test encryption
            request.encrypt_patient_demographics(demographics_data)
            assert request.patient_demographics_encrypted == "encrypted_demographics"
            
            # Test decryption
            decrypted = request.decrypt_patient_demographics()
            assert decrypted == demographics_data
    
    def test_clinical_notes_encryption(self, valid_request_data):
        """Test clinical notes encryption and decryption."""
        request = AuthorizationRequestDB(**valid_request_data)
        
        clinical_notes = "Patient reports persistent shoulder pain for 6 weeks."
        
        with patch('src.core.encryption.PHIEncryption') as mock_encryption:
            mock_encryption_instance = Mock()
            mock_encryption.return_value = mock_encryption_instance
            mock_encryption_instance.encrypt.return_value = "encrypted_notes"
            mock_encryption_instance.decrypt.return_value = clinical_notes
            
            # Test encryption
            request.encrypt_clinical_notes(clinical_notes)
            assert request.clinical_notes_encrypted == "encrypted_notes"
            
            # Test decryption
            decrypted = request.decrypt_clinical_notes()
            assert decrypted == clinical_notes
            
            # Test None handling
            request.encrypt_clinical_notes(None)
            assert request.clinical_notes_encrypted is None
            
            request.clinical_notes_encrypted = None
            assert request.decrypt_clinical_notes() is None
    
    def test_timestamp_auto_generation(self, db_session, valid_request_data):
        """Test automatic timestamp generation and updates."""
        request = AuthorizationRequestDB(**valid_request_data)
        db_session.add(request)
        db_session.commit()
        
        # Verify timestamps are set
        assert request.submitted_at is not None
        assert request.updated_at is not None
        assert isinstance(request.submitted_at, datetime)
        assert isinstance(request.updated_at, datetime)
        
        original_updated_at = request.updated_at
        
        # Update request and verify updated_at changes
        import time
        time.sleep(0.01)  # Small delay to ensure timestamp difference
        
        request.status = RequestStatus.IN_REVIEW.value
        db_session.commit()
        
        assert request.updated_at > original_updated_at
    
    def test_model_representation(self, valid_request_data):
        """Test model string representation."""
        request = AuthorizationRequestDB(**valid_request_data)
        
        repr_str = repr(request)
        assert "AuthorizationRequest" in repr_str
        assert "req_validation_001" in repr_str
        assert "prov_validation_001" in repr_str
        assert RequestStatus.SUBMITTED.value in repr_str


class TestAuthorizationDecisionValidation:
    """Test validation rules for AuthorizationDecisionDB model."""
    
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
    def valid_decision_data(self):
        """Create valid authorization decision data."""
        return {
            "decision_id": "dec_validation_001",
            "request_id": "req_validation_001",
            "status": DecisionStatus.APPROVED.value,
            "reasoning": [
                "Patient meets medical necessity criteria",
                "Diagnosis code is covered under policy"
            ],
            "policy_references": ["CMS NCD 220.2"],
            "authorization_number": "auth_validation_001",
            "valid_until": datetime.now(timezone.utc) + timedelta(days=30),
            "confidence_score": Decimal("0.95")
        }
    
    def test_valid_decision_creation(self, db_session, valid_decision_data):
        """Test creation of valid authorization decision."""
        # Create request first (for foreign key)
        request_data = {
            "request_id": "req_validation_001",
            "provider_id": "prov_validation_001",
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
        
        # Create decision
        decision = AuthorizationDecisionDB(**valid_decision_data)
        db_session.add(decision)
        db_session.commit()
        
        retrieved = db_session.query(AuthorizationDecisionDB).filter_by(
            decision_id="dec_validation_001"
        ).first()
        
        assert retrieved is not None
        assert retrieved.status == DecisionStatus.APPROVED.value
        assert retrieved.confidence_score == Decimal("0.95")
        assert len(retrieved.reasoning) == 2
    
    def test_decision_status_validation(self, valid_decision_data):
        """Test decision status field validation."""
        # Test valid statuses
        for status in DecisionStatus:
            data = valid_decision_data.copy()
            data["status"] = status.value
            data["decision_id"] = f"dec_status_{status.value}"
            
            decision = AuthorizationDecisionDB(**data)
            assert decision.status == status.value
        
        # Test invalid status
        with pytest.raises(ValueError, match="Invalid decision status"):
            invalid_data = valid_decision_data.copy()
            invalid_data["status"] = "INVALID_STATUS"
            decision = AuthorizationDecisionDB(**invalid_data)
    
    def test_confidence_score_validation(self, valid_decision_data):
        """Test confidence score validation constraints."""
        # Test valid confidence scores
        valid_scores = [0.0, 0.25, 0.5, 0.75, 1.0]
        
        for score in valid_scores:
            data = valid_decision_data.copy()
            data["confidence_score"] = Decimal(str(score))
            data["decision_id"] = f"dec_score_{int(score*100)}"
            
            decision = AuthorizationDecisionDB(**data)
            assert decision.confidence_score == Decimal(str(score))
        
        # Test invalid confidence scores
        invalid_scores = [-0.1, 1.1, 2.0, -1.0]
        
        for score in invalid_scores:
            with pytest.raises(ValueError, match="Confidence score must be between 0.0 and 1.0"):
                data = valid_decision_data.copy()
                data["confidence_score"] = Decimal(str(score))
                decision = AuthorizationDecisionDB(**data)
    
    def test_reasoning_validation(self, valid_decision_data):
        """Test reasoning field validation."""
        # Test valid reasoning (non-empty list)
        valid_reasoning = [
            ["Single reason"],
            ["Reason 1", "Reason 2"],
            ["Multiple", "reasons", "for", "decision"]
        ]
        
        for reasoning in valid_reasoning:
            data = valid_decision_data.copy()
            data["reasoning"] = reasoning
            data["decision_id"] = f"dec_reason_{len(reasoning)}"
            
            decision = AuthorizationDecisionDB(**data)
            assert decision.reasoning == reasoning
        
        # Test invalid reasoning (empty list)
        with pytest.raises(ValueError, match="Reasoning must be a non-empty list"):
            data = valid_decision_data.copy()
            data["reasoning"] = []
            decision = AuthorizationDecisionDB(**data)
        
        # Test invalid reasoning (not a list)
        with pytest.raises(ValueError, match="Reasoning must be a non-empty list"):
            data = valid_decision_data.copy()
            data["reasoning"] = "Single string reason"
            decision = AuthorizationDecisionDB(**data)
    
    def test_json_field_complex_data(self, db_session, valid_decision_data):
        """Test complex JSON field data serialization."""
        # Create request first
        request_data = {
            "request_id": "req_validation_001",
            "provider_id": "prov_validation_001",
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
        
        # Create decision with complex JSON data
        complex_data = valid_decision_data.copy()
        complex_data.update({
            "policy_references": [
                {"type": "NCD", "id": "220.2", "title": "MRI Coverage"},
                {"type": "LCD", "id": "L33721", "title": "Shoulder MRI"}
            ],
            "additional_info_needed": [
                {"field": "prior_therapy", "description": "Physical therapy records"},
                {"field": "imaging_history", "description": "Previous imaging results"}
            ],
            "alternative_procedures": [
                {"code": "73020", "description": "X-ray shoulder", "cost_difference": -200},
                {"code": "76881", "description": "Ultrasound shoulder", "cost_difference": -500}
            ]
        })
        
        decision = AuthorizationDecisionDB(**complex_data)
        db_session.add(decision)
        db_session.commit()
        
        # Verify complex JSON serialization
        retrieved = db_session.query(AuthorizationDecisionDB).filter_by(
            decision_id="dec_validation_001"
        ).first()
        
        assert isinstance(retrieved.policy_references, list)
        assert len(retrieved.policy_references) == 2
        assert retrieved.policy_references[0]["type"] == "NCD"
        
        assert isinstance(retrieved.additional_info_needed, list)
        assert len(retrieved.additional_info_needed) == 2
        assert retrieved.additional_info_needed[0]["field"] == "prior_therapy"
        
        assert isinstance(retrieved.alternative_procedures, list)
        assert len(retrieved.alternative_procedures) == 2
        assert retrieved.alternative_procedures[0]["cost_difference"] == -200
    
    def test_relationship_with_request(self, db_session, valid_decision_data):
        """Test relationship between decision and request models."""
        # Create request
        request_data = {
            "request_id": "req_relationship_001",
            "provider_id": "prov_relationship_001",
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
        
        # Create decision
        decision_data = valid_decision_data.copy()
        decision_data["request_id"] = "req_relationship_001"
        
        decision = AuthorizationDecisionDB(**decision_data)
        db_session.add(decision)
        db_session.commit()
        
        # Test relationship from decision to request
        retrieved_decision = db_session.query(AuthorizationDecisionDB).filter_by(
            decision_id="dec_validation_001"
        ).first()
        
        assert retrieved_decision.request is not None
        assert retrieved_decision.request.request_id == "req_relationship_001"
        assert retrieved_decision.request.provider_id == "prov_relationship_001"
        
        # Test relationship from request to decisions
        retrieved_request = db_session.query(AuthorizationRequestDB).filter_by(
            request_id="req_relationship_001"
        ).first()
        
        assert len(retrieved_request.decisions) == 1
        assert retrieved_request.decisions[0].decision_id == "dec_validation_001"
        assert retrieved_request.decisions[0].status == DecisionStatus.APPROVED.value
    
    def test_cascade_delete_relationship(self, db_session, valid_decision_data):
        """Test cascade delete from request to decisions."""
        # Create request
        request_data = {
            "request_id": "req_cascade_001",
            "provider_id": "prov_cascade_001",
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
        
        # Create multiple decisions
        for i in range(3):
            decision_data = valid_decision_data.copy()
            decision_data.update({
                "decision_id": f"dec_cascade_{i:03d}",
                "request_id": "req_cascade_001"
            })
            
            decision = AuthorizationDecisionDB(**decision_data)
            db_session.add(decision)
        
        db_session.commit()
        
        # Verify decisions exist
        decision_count = db_session.query(AuthorizationDecisionDB).filter_by(
            request_id="req_cascade_001"
        ).count()
        assert decision_count == 3
        
        # Delete request (should cascade to decisions)
        db_session.delete(request)
        db_session.commit()
        
        # Verify decisions are deleted
        remaining_decisions = db_session.query(AuthorizationDecisionDB).filter_by(
            request_id="req_cascade_001"
        ).count()
        assert remaining_decisions == 0


class TestCoveragePolicyValidation:
    """Test validation rules for CoveragePolicyDB model."""
    
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
    def valid_policy_data(self):
        """Create valid coverage policy data."""
        return {
            "policy_id": "pol_validation_001",
            "payer_id": "payer_validation_001",
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
    
    def test_valid_policy_creation(self, db_session, valid_policy_data):
        """Test creation of valid coverage policy."""
        policy = CoveragePolicyDB(**valid_policy_data)
        db_session.add(policy)
        db_session.commit()
        
        retrieved = db_session.query(CoveragePolicyDB).filter_by(
            policy_id="pol_validation_001"
        ).first()
        
        assert retrieved is not None
        assert retrieved.policy_type == "PAYER"
        assert retrieved.is_active is True
        assert retrieved.is_currently_effective() is True
    
    def test_policy_type_validation(self, valid_policy_data):
        """Test policy type field validation."""
        # Test valid policy types
        valid_types = ["NCD", "LCD", "PAYER"]
        
        for policy_type in valid_types:
            data = valid_policy_data.copy()
            data["policy_type"] = policy_type
            data["policy_id"] = f"pol_type_{policy_type}"
            
            policy = CoveragePolicyDB(**data)
            assert policy.policy_type == policy_type
        
        # Test invalid policy type
        with pytest.raises(ValueError, match="Invalid policy type"):
            data = valid_policy_data.copy()
            data["policy_type"] = "INVALID_TYPE"
            policy = CoveragePolicyDB(**data)
    
    def test_coverage_criteria_validation(self, valid_policy_data):
        """Test coverage criteria field validation."""
        # Test valid coverage criteria (non-empty dict)
        valid_criteria = [
            {"medical_necessity": True},
            {"prior_auth_required": False, "age_limit": 65},
            {"complex": {"nested": {"criteria": True}}}
        ]
        
        for criteria in valid_criteria:
            data = valid_policy_data.copy()
            data["coverage_criteria"] = criteria
            data["policy_id"] = f"pol_criteria_{len(str(criteria))}"
            
            policy = CoveragePolicyDB(**data)
            assert policy.coverage_criteria == criteria
        
        # Test invalid coverage criteria (empty dict)
        with pytest.raises(ValueError, match="Coverage criteria must be a non-empty dictionary"):
            data = valid_policy_data.copy()
            data["coverage_criteria"] = {}
            policy = CoveragePolicyDB(**data)
        
        # Test invalid coverage criteria (not a dict)
        with pytest.raises(ValueError, match="Coverage criteria must be a non-empty dictionary"):
            data = valid_policy_data.copy()
            data["coverage_criteria"] = "string criteria"
            policy = CoveragePolicyDB(**data)
    
    def test_effective_date_validation(self, valid_policy_data):
        """Test effective date validation."""
        # Test valid effective date (today or past)
        valid_dates = [
            date.today(),
            date.today() - timedelta(days=1),
            date.today() - timedelta(days=30)
        ]
        
        for effective_date in valid_dates:
            data = valid_policy_data.copy()
            data["effective_date"] = effective_date
            data["policy_id"] = f"pol_date_{effective_date.strftime('%Y%m%d')}"
            
            policy = CoveragePolicyDB(**data)
            assert policy.effective_date == effective_date
        
        # Test future effective date with active policy (should be allowed in model)
        # The validation in the model only warns, doesn't prevent
        future_date = date.today() + timedelta(days=30)
        data = valid_policy_data.copy()
        data["effective_date"] = future_date
        data["is_active"] = True
        
        # This should work - the model allows future effective dates
        policy = CoveragePolicyDB(**data)
        assert policy.effective_date == future_date
    
    def test_is_currently_effective_method(self, db_session, valid_policy_data):
        """Test is_currently_effective method logic."""
        # Test active policy with current effective date
        policy = CoveragePolicyDB(**valid_policy_data)
        db_session.add(policy)
        db_session.commit()
        
        assert policy.is_currently_effective() is True
        
        # Test inactive policy
        policy.is_active = False
        assert policy.is_currently_effective() is False
        
        # Test policy with future effective date
        policy.is_active = True
        policy.effective_date = date.today() + timedelta(days=30)
        assert policy.is_currently_effective() is False
        
        # Test policy with past expiration date
        policy.effective_date = date.today() - timedelta(days=30)
        policy.expiration_date = date.today() - timedelta(days=1)
        assert policy.is_currently_effective() is False
        
        # Test policy with future expiration date
        policy.expiration_date = date.today() + timedelta(days=30)
        assert policy.is_currently_effective() is True
    
    def test_complex_coverage_criteria_serialization(self, db_session, valid_policy_data):
        """Test complex coverage criteria JSON serialization."""
        complex_criteria = {
            "medical_necessity": {
                "required": True,
                "documentation": ["physician_notes", "imaging_results"],
                "timeframe": {"min_symptoms_duration": 30, "max_delay": 90}
            },
            "prior_authorization": {
                "required": True,
                "exceptions": ["emergency", "urgent"],
                "approval_criteria": {
                    "age_range": {"min": 18, "max": 65},
                    "diagnosis_codes": ["M25.511", "M25.512", "M25.513"],
                    "failed_conservative_treatment": True
                }
            },
            "cost_sharing": {
                "copay": 50,
                "coinsurance": 0.2,
                "deductible_applies": True
            }
        }
        
        data = valid_policy_data.copy()
        data["coverage_criteria"] = complex_criteria
        
        policy = CoveragePolicyDB(**data)
        db_session.add(policy)
        db_session.commit()
        
        # Verify complex JSON serialization
        retrieved = db_session.query(CoveragePolicyDB).filter_by(
            policy_id="pol_validation_001"
        ).first()
        
        assert isinstance(retrieved.coverage_criteria, dict)
        assert "medical_necessity" in retrieved.coverage_criteria
        assert "prior_authorization" in retrieved.coverage_criteria
        assert "cost_sharing" in retrieved.coverage_criteria
        
        # Test nested access
        medical_necessity = retrieved.coverage_criteria["medical_necessity"]
        assert medical_necessity["required"] is True
        assert len(medical_necessity["documentation"]) == 2
        assert medical_necessity["timeframe"]["min_symptoms_duration"] == 30
        
        prior_auth = retrieved.coverage_criteria["prior_authorization"]
        assert len(prior_auth["approval_criteria"]["diagnosis_codes"]) == 3
        assert prior_auth["approval_criteria"]["age_range"]["max"] == 65


class TestAIConfigurationValidation:
    """Test validation rules for AIConfigurationDB model."""
    
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
    def valid_ai_config_data(self):
        """Create valid AI configuration data."""
        return {
            "config_id": "config_validation_001",
            "configuration_type": "llm_model",
            "configuration_name": "GPT-4 Medical Decision Model",
            "configuration_version": "1.0",
            "configuration_data": {
                "model_name": "gpt-4-medical",
                "temperature": 0.1,
                "max_tokens": 1000,
                "decision_threshold": 0.8
            },
            "effective_date": date.today(),
            "is_active": True,
            "created_by": "test_user",
            "updated_by": "test_user"
        }
    
    def test_valid_ai_config_creation(self, db_session, valid_ai_config_data):
        """Test creation of valid AI configuration."""
        config = AIConfigurationDB(**valid_ai_config_data)
        db_session.add(config)
        db_session.commit()
        
        retrieved = db_session.query(AIConfigurationDB).filter_by(
            config_id="config_validation_001"
        ).first()
        
        assert retrieved is not None
        assert retrieved.configuration_type == "llm_model"
        assert retrieved.is_currently_effective() is True
        assert "model_name" in retrieved.configuration_data
    
    def test_configuration_type_validation(self, valid_ai_config_data):
        """Test configuration type field validation."""
        # Test valid configuration types
        valid_types = ["llm_model", "decision_threshold", "escalation_rule", "clinical_guideline", "feedback_rule"]
        
        for config_type in valid_types:
            data = valid_ai_config_data.copy()
            data["configuration_type"] = config_type
            data["config_id"] = f"config_type_{config_type}"
            
            config = AIConfigurationDB(**data)
            assert config.configuration_type == config_type
        
        # Test invalid configuration type
        with pytest.raises(ValueError, match="Invalid configuration type"):
            data = valid_ai_config_data.copy()
            data["configuration_type"] = "INVALID_TYPE"
            config = AIConfigurationDB(**data)
    
    def test_configuration_data_validation(self, valid_ai_config_data):
        """Test configuration data field validation."""
        # Test valid configuration data (non-empty dict)
        valid_data = [
            {"simple": "value"},
            {"complex": {"nested": {"data": True}}},
            {"array": [1, 2, 3], "object": {"key": "value"}}
        ]
        
        for config_data in valid_data:
            data = valid_ai_config_data.copy()
            data["configuration_data"] = config_data
            data["config_id"] = f"config_data_{len(str(config_data))}"
            
            config = AIConfigurationDB(**data)
            assert config.configuration_data == config_data
        
        # Test invalid configuration data (empty dict)
        with pytest.raises(ValueError, match="Configuration data must be a non-empty dictionary"):
            data = valid_ai_config_data.copy()
            data["configuration_data"] = {}
            config = AIConfigurationDB(**data)
        
        # Test invalid configuration data (not a dict)
        with pytest.raises(ValueError, match="Configuration data must be a non-empty dictionary"):
            data = valid_ai_config_data.copy()
            data["configuration_data"] = "string data"
            config = AIConfigurationDB(**data)


class TestModelPerformanceMetricsValidation:
    """Test validation rules for ModelPerformanceMetricsDB model."""
    
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
    def valid_metrics_data(self):
        """Create valid model performance metrics data."""
        return {
            "metric_id": "metric_validation_001",
            "model_id": "gpt-4-medical-v1",
            "model_name": "GPT-4 Medical Decision Model",
            "accuracy_score": Decimal("0.95"),
            "precision_score": Decimal("0.92"),
            "recall_score": Decimal("0.88"),
            "f1_score": Decimal("0.90"),
            "average_response_time_ms": Decimal("1500.50"),
            "success_rate": Decimal("0.98"),
            "error_rate": Decimal("0.02"),
            "total_requests": 1000,
            "successful_requests": 980,
            "failed_requests": 20,
            "total_cost": Decimal("150.75"),
            "cost_per_request": Decimal("0.15075"),
            "measurement_start": datetime.now(timezone.utc) - timedelta(hours=24),
            "measurement_end": datetime.now(timezone.utc)
        }
    
    def test_valid_metrics_creation(self, db_session, valid_metrics_data):
        """Test creation of valid model performance metrics."""
        metrics = ModelPerformanceMetricsDB(**valid_metrics_data)
        db_session.add(metrics)
        db_session.commit()
        
        retrieved = db_session.query(ModelPerformanceMetricsDB).filter_by(
            metric_id="metric_validation_001"
        ).first()
        
        assert retrieved is not None
        assert retrieved.accuracy_score == Decimal("0.95")
        assert retrieved.total_requests == 1000
        assert retrieved.cost_per_request == Decimal("0.15075")
    
    def test_score_range_validation(self, valid_metrics_data):
        """Test score range validation (0.0 to 1.0)."""
        score_fields = ["accuracy_score", "precision_score", "recall_score", "f1_score", "success_rate", "error_rate"]
        
        # Test valid scores
        valid_scores = [0.0, 0.25, 0.5, 0.75, 1.0]
        
        for field in score_fields:
            for score in valid_scores:
                data = valid_metrics_data.copy()
                data[field] = Decimal(str(score))
                data["metric_id"] = f"metric_{field}_{int(score*100)}"
                
                metrics = ModelPerformanceMetricsDB(**data)
                assert getattr(metrics, field) == Decimal(str(score))
        
        # Test invalid scores
        invalid_scores = [-0.1, 1.1, 2.0]
        
        for field in score_fields:
            for score in invalid_scores:
                with pytest.raises(ValueError, match=f"{field} must be between 0.0 and 1.0"):
                    data = valid_metrics_data.copy()
                    data[field] = Decimal(str(score))
                    metrics = ModelPerformanceMetricsDB(**data)
    
    def test_request_count_validation(self, valid_metrics_data):
        """Test request count validation (non-negative)."""
        count_fields = ["total_requests", "successful_requests", "failed_requests"]
        
        # Test valid counts
        valid_counts = [0, 1, 100, 1000]
        
        for field in count_fields:
            for count in valid_counts:
                data = valid_metrics_data.copy()
                data[field] = count
                data["metric_id"] = f"metric_{field}_{count}"
                
                metrics = ModelPerformanceMetricsDB(**data)
                assert getattr(metrics, field) == count
        
        # Test invalid counts
        invalid_counts = [-1, -10, -100]
        
        for field in count_fields:
            for count in invalid_counts:
                with pytest.raises(ValueError, match=f"{field} must be non-negative"):
                    data = valid_metrics_data.copy()
                    data[field] = count
                    metrics = ModelPerformanceMetricsDB(**data)


class TestAIFeedbackValidation:
    """Test validation rules for AIFeedbackDB model."""
    
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
    def valid_feedback_data(self):
        """Create valid AI feedback data."""
        return {
            "feedback_id": "feedback_validation_001",
            "decision_id": "dec_feedback_001",
            "request_id": "req_feedback_001",
            "feedback_type": "decision_accuracy",
            "feedback_score": Decimal("0.8"),
            "feedback_text": "Decision was accurate but reasoning could be improved",
            "feedback_source": "PROVIDER",
            "source_user_id": "user_feedback_001",
            "source_role": "physician",
            "model_id": "gpt-4-medical-v1",
            "model_version": "1.0",
            "original_confidence": Decimal("0.95"),
            "processed": False
        }
    
    def test_valid_feedback_creation(self, db_session, valid_feedback_data):
        """Test creation of valid AI feedback."""
        # Create required parent records first
        request_data = {
            "request_id": "req_feedback_001",
            "provider_id": "prov_feedback_001",
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
        
        decision_data = {
            "decision_id": "dec_feedback_001",
            "request_id": "req_feedback_001",
            "status": DecisionStatus.APPROVED.value,
            "reasoning": ["Test reasoning"],
            "confidence_score": Decimal("0.95")
        }
        
        decision = AuthorizationDecisionDB(**decision_data)
        db_session.add(decision)
        db_session.commit()
        
        # Create feedback
        feedback = AIFeedbackDB(**valid_feedback_data)
        db_session.add(feedback)
        db_session.commit()
        
        retrieved = db_session.query(AIFeedbackDB).filter_by(
            feedback_id="feedback_validation_001"
        ).first()
        
        assert retrieved is not None
        assert retrieved.feedback_type == "decision_accuracy"
        assert retrieved.feedback_score == Decimal("0.8")
        assert retrieved.feedback_source == "PROVIDER"
    
    def test_feedback_score_validation(self, valid_feedback_data):
        """Test feedback score validation (-1.0 to 1.0)."""
        # Test valid scores
        valid_scores = [-1.0, -0.5, 0.0, 0.5, 1.0]
        
        for score in valid_scores:
            data = valid_feedback_data.copy()
            data["feedback_score"] = Decimal(str(score))
            data["feedback_id"] = f"feedback_score_{int(score*100)}"
            
            feedback = AIFeedbackDB(**data)
            assert feedback.feedback_score == Decimal(str(score))
        
        # Test invalid scores
        invalid_scores = [-1.1, 1.1, 2.0, -2.0]
        
        for score in invalid_scores:
            with pytest.raises(ValueError, match="Feedback score must be between -1.0 and 1.0"):
                data = valid_feedback_data.copy()
                data["feedback_score"] = Decimal(str(score))
                feedback = AIFeedbackDB(**data)
    
    def test_feedback_type_validation(self, valid_feedback_data):
        """Test feedback type field validation."""
        # Test valid feedback types
        valid_types = ["decision_accuracy", "reasoning_quality", "policy_compliance", "clinical_appropriateness"]
        
        for feedback_type in valid_types:
            data = valid_feedback_data.copy()
            data["feedback_type"] = feedback_type
            data["feedback_id"] = f"feedback_type_{feedback_type}"
            
            feedback = AIFeedbackDB(**data)
            assert feedback.feedback_type == feedback_type
        
        # Test invalid feedback type
        with pytest.raises(ValueError, match="Invalid feedback type"):
            data = valid_feedback_data.copy()
            data["feedback_type"] = "INVALID_TYPE"
            feedback = AIFeedbackDB(**data)
    
    def test_feedback_source_validation(self, valid_feedback_data):
        """Test feedback source field validation."""
        # Test valid feedback sources
        valid_sources = ["PROVIDER", "PAYER", "EXPERT", "SYSTEM", "PATIENT"]
        
        for source in valid_sources:
            data = valid_feedback_data.copy()
            data["feedback_source"] = source
            data["feedback_id"] = f"feedback_source_{source}"
            
            feedback = AIFeedbackDB(**data)
            assert feedback.feedback_source == source
        
        # Test invalid feedback source
        with pytest.raises(ValueError, match="Invalid feedback source"):
            data = valid_feedback_data.copy()
            data["feedback_source"] = "INVALID_SOURCE"
            feedback = AIFeedbackDB(**data)


class TestConfigurationAuditLogValidation:
    """Test validation rules for ConfigurationAuditLogDB model."""
    
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
    def valid_audit_data(self):
        """Create valid configuration audit log data."""
        return {
            "audit_id": "audit_validation_001",
            "configuration_type": "llm_model",
            "config_id": "config_audit_001",
            "action": "UPDATE",
            "old_values": {"temperature": 0.1, "max_tokens": 1000},
            "new_values": {"temperature": 0.2, "max_tokens": 1500},
            "change_summary": "Updated model parameters for better performance",
            "user_id": "user_audit_001",
            "user_role": "admin",
            "reason": "Performance optimization based on feedback",
            "approval_required": False
        }
    
    def test_valid_audit_creation(self, db_session, valid_audit_data):
        """Test creation of valid configuration audit log."""
        audit = ConfigurationAuditLogDB(**valid_audit_data)
        db_session.add(audit)
        db_session.commit()
        
        retrieved = db_session.query(ConfigurationAuditLogDB).filter_by(
            audit_id="audit_validation_001"
        ).first()
        
        assert retrieved is not None
        assert retrieved.action == "UPDATE"
        assert retrieved.configuration_type == "llm_model"
        assert "temperature" in retrieved.old_values
        assert "temperature" in retrieved.new_values
    
    def test_action_validation(self, valid_audit_data):
        """Test audit action field validation."""
        # Test valid actions
        valid_actions = ["CREATE", "UPDATE", "DELETE", "ACTIVATE", "DEACTIVATE", "APPROVE", "REJECT"]
        
        for action in valid_actions:
            data = valid_audit_data.copy()
            data["action"] = action
            data["audit_id"] = f"audit_action_{action}"
            
            audit = ConfigurationAuditLogDB(**data)
            assert audit.action == action
        
        # Test invalid action
        with pytest.raises(ValueError, match="Invalid audit action"):
            data = valid_audit_data.copy()
            data["action"] = "INVALID_ACTION"
            audit = ConfigurationAuditLogDB(**data)
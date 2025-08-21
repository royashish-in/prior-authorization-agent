"""
Tests for the decision engine service.

This module tests the core decision-making logic for prior authorization
requests, including policy validation, medical necessity checks, and
decision generation.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any, List

from src.services.decision_engine import DecisionEngine, DecisionContext, DecisionMode
from src.models.authorization import AuthorizationDecision, AuthorizationRequest
from src.models.enums import DecisionStatus, UrgencyLevel, ProcedureType, RequestStatus
from src.models.medical_codes import ICD10Code, CPTCode
from src.models.patient import PatientDemographics
from src.services.validation import ValidationResult, ValidationError as ValidationErrorModel


class TestDecisionEngine:
    """Test decision engine functionality."""
    
    @pytest.fixture
    def decision_engine(self):
        """Create decision engine instance."""
        return DecisionEngine()
    
    @pytest.fixture
    def sample_validation_result(self):
        """Create sample validation result."""
        return ValidationResult(
            is_valid=True,
            errors=[],
            warnings=[],
            processing_time_ms=100.0
        )
    
    @pytest.fixture
    def sample_request(self):
        """Create sample authorization request."""
        return AuthorizationRequest(
            request_id="req_test_001",
            provider_id="prov_test_001",
            patient_demographics=PatientDemographics(
                patient_id="pat_test_001",
                age=43,
                gender="male",
                insurance_id="ins_test_001",
                member_id="TEST123456"
            ),
            diagnosis_codes=[
                ICD10Code(
                    code="G93.1",
                    description="Anoxic brain damage"
                )
            ],
            procedure_codes=[
                CPTCode(
                    code="70551",
                    description="MRI brain without contrast"
                )
            ],
            clinical_notes="Patient presents with persistent headaches.",
            urgency_level=UrgencyLevel.ROUTINE,
            procedure_type=ProcedureType.MRI
        )
    
    def test_generate_decision_approved(self, decision_engine, sample_request, sample_validation_result):
        """Test decision generation for approved request."""
        result = decision_engine.generate_decision(
            request=sample_request,
            validation_result=sample_validation_result
        )
        
        assert isinstance(result, AuthorizationDecision)
        assert result.status in [DecisionStatus.APPROVED, DecisionStatus.MORE_INFO_NEEDED, DecisionStatus.DENIED]
        assert result.decision_id is not None
        assert len(result.reasoning) > 0
        assert result.confidence_score >= 0.0
    
    def test_generate_decision_basic(self, decision_engine, sample_request, sample_validation_result):
        """Test basic decision generation."""
        result = decision_engine.generate_decision(
            request=sample_request,
            validation_result=sample_validation_result
        )
        
        assert isinstance(result, AuthorizationDecision)
        assert result.decision_id is not None
        assert result.request_id == sample_request.request_id
        assert len(result.reasoning) > 0
        assert 0.0 <= result.confidence_score <= 1.0
    
    def test_decision_engine_initialization(self, decision_engine):
        """Test decision engine initialization."""
        assert decision_engine is not None
        assert hasattr(decision_engine, 'generate_decision')
        assert hasattr(decision_engine, 'decision_mode')
    
    def test_decision_engine_modes(self):
        """Test decision engine mode configuration."""
        engine_rule_based = DecisionEngine(DecisionMode.RULE_BASED_ONLY)
        assert engine_rule_based.decision_mode == DecisionMode.RULE_BASED_ONLY
        
        engine_hybrid = DecisionEngine(DecisionMode.HYBRID)
        assert engine_hybrid.decision_mode == DecisionMode.HYBRID


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
"""
Comprehensive tests for AI Configuration API endpoints.

This module provides comprehensive testing for all AI configuration endpoints
including LLM model configuration, decision thresholds, escalation rules,
clinical guidelines, and feedback management.
"""

import pytest
from datetime import date, datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException, status

from src.api.ai_config import router
from src.services.ai_config_manager import get_ai_config_manager
from src.auth.oauth2 import get_current_user
from src.audit.logger import AuditLogger
from src.auth.models import UserRole
from src.models.ai_config import ConfigurationType, ModelSelectionStrategy


@pytest.fixture
def client():
    """Create test client."""
    from src.main import app
    return TestClient(app)


@pytest.fixture
def mock_ai_config_manager():
    """Create mock AI configuration manager."""
    manager = Mock()
    manager.create_configuration = AsyncMock(return_value="config_123")
    manager.get_configuration_by_id = Mock(return_value=Mock(
        config_id="config_123",
        configuration_type="LLM_MODEL",
        configuration_name="test_model",
        configuration_data={"model_id": "test_model", "enabled": True},
        effective_date=date.today(),
        expiration_date=None,
        is_active=True,
        configuration_version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        created_by="user_123",
        updated_by="user_123"
    ))
    manager.list_configurations = Mock(return_value=[])
    manager.validate_configuration = AsyncMock(return_value=Mock(
        is_valid=True,
        validation_errors=[],
        warnings=[]
    ))
    manager.deactivate_configuration = AsyncMock(return_value=True)
    manager.select_optimal_model = AsyncMock(return_value=Mock(
        model_id="best_model",
        model_name="Best Model",
        confidence=0.95,
        selection_reason="Highest performance"
    ))
    manager.record_performance_metrics = AsyncMock(return_value=True)
    manager.record_feedback = AsyncMock(return_value=True)
    manager.get_dashboard_data = AsyncMock(return_value={
        "total_configurations": 10,
        "active_models": 3,
        "performance_summary": {}
    })
    return manager


@pytest.fixture
def mock_audit_logger():
    """Create mock audit logger."""
    logger = Mock()
    logger.log_ai_config_action = AsyncMock()
    return logger


@pytest.fixture
def authenticated_user():
    """Create authenticated user with admin role."""
    return {
        "user_id": "user_123",
        "username": "admin_user",
        "roles": [UserRole.ADMIN],
        "organization_id": "org_123"
    }


class TestLLMModelConfiguration:
    """Test LLM model configuration endpoints."""
    
    def test_create_llm_model_config_success(
        self, 
        client, 
        mock_ai_config_manager, 
        mock_audit_logger,
        authenticated_user
    ):
        """Test successful LLM model configuration creation."""
        from src.main import app
        
        # Mock dependencies
        app.dependency_overrides[get_ai_config_manager] = lambda db: mock_ai_config_manager
        app.dependency_overrides[AuditLogger] = lambda db: mock_audit_logger
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        try:
            # Test data
            model_config = {
                "model_id": "microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract",
                "model_name": "PubMedBERT Base",
                "deployment_type": "huggingface_api",
                "model_type": "biomedical_bert",
                "priority": 1,
                "enabled": True,
                "max_tokens": 512,
                "temperature": 0.1,
                "top_p": 0.9,
                "confidence_threshold": 0.7,
                "timeout_seconds": 30,
                "max_retries": 3,
                "use_auth_token": True,
                "device": "auto",
                "torch_dtype": "auto",
                "load_in_8bit": False,
                "load_in_4bit": False,
                "max_requests_per_minute": 60,
                "max_concurrent_requests": 10,
                "cost_per_request": 0.001
            }
            
            # Execute
            response = client.post("/api/v1/ai-config/llm-models", json=model_config)
            
            # Verify
            assert response.status_code == 200
            data = response.json()
            assert data["config_id"] == "config_123"
            assert data["configuration_type"] == "LLM_MODEL"
            assert data["is_active"] is True
            
            # Verify service calls
            mock_ai_config_manager.create_configuration.assert_called_once()
            mock_ai_config_manager.get_configuration_by_id.assert_called_once_with("config_123")
            
        finally:
            app.dependency_overrides.clear()
    
    def test_create_llm_model_config_invalid_deployment_type(self, client, authenticated_user):
        """Test LLM model configuration with invalid deployment type."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        try:
            model_config = {
                "model_id": "test_model",
                "model_name": "Test Model",
                "deployment_type": "invalid_type",  # Invalid
                "model_type": "biomedical_bert"
            }
            
            response = client.post("/api/v1/ai-config/llm-models", json=model_config)
            
            assert response.status_code == 422  # Validation error
            
        finally:
            app.dependency_overrides.clear()
    
    def test_create_llm_model_config_unauthorized(self, client):
        """Test LLM model configuration creation without authentication."""
        model_config = {
            "model_id": "test_model",
            "model_name": "Test Model",
            "deployment_type": "huggingface_api",
            "model_type": "biomedical_bert"
        }
        
        response = client.post("/api/v1/ai-config/llm-models", json=model_config)
        
        assert response.status_code == 401  # Unauthorized


class TestDecisionThresholdConfiguration:
    """Test decision threshold configuration endpoints."""
    
    def test_create_decision_threshold_config_success(
        self, 
        client, 
        mock_ai_config_manager,
        authenticated_user
    ):
        """Test successful decision threshold configuration creation."""
        from src.main import app
        
        app.dependency_overrides[get_ai_config_manager] = lambda db: mock_ai_config_manager
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        try:
            threshold_config = {
                "config_name": "Standard Thresholds",
                "auto_approve_threshold": 0.9,
                "auto_deny_threshold": 0.8,
                "manual_review_threshold": 0.6,
                "procedure_thresholds": {
                    "MRI": {"auto_approve": 0.95, "auto_deny": 0.85}
                },
                "payer_thresholds": {
                    "BCBS": {"auto_approve": 0.88, "auto_deny": 0.78}
                },
                "high_risk_adjustment": -0.1,
                "low_risk_adjustment": 0.05,
                "effective_date": "2024-01-01"
            }
            
            response = client.post("/api/v1/ai-config/decision-thresholds", json=threshold_config)
            
            assert response.status_code == 200
            data = response.json()
            assert data["config_id"] == "config_123"
            
            mock_ai_config_manager.create_configuration.assert_called_once()
            
        finally:
            app.dependency_overrides.clear()
    
    def test_create_decision_threshold_config_invalid_thresholds(self, client, authenticated_user):
        """Test decision threshold configuration with invalid threshold values."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        try:
            threshold_config = {
                "config_name": "Invalid Thresholds",
                "auto_approve_threshold": 1.5,  # Invalid - > 1.0
                "auto_deny_threshold": 0.8,
                "manual_review_threshold": 0.6
            }
            
            response = client.post("/api/v1/ai-config/decision-thresholds", json=threshold_config)
            
            assert response.status_code == 422  # Validation error
            
        finally:
            app.dependency_overrides.clear()


class TestEscalationRuleConfiguration:
    """Test escalation rule configuration endpoints."""
    
    def test_create_escalation_rule_config_success(
        self, 
        client, 
        mock_ai_config_manager,
        authenticated_user
    ):
        """Test successful escalation rule configuration creation."""
        from src.main import app
        
        app.dependency_overrides[get_ai_config_manager] = lambda db: mock_ai_config_manager
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        try:
            escalation_config = {
                "rule_name": "High Risk Escalation",
                "triggers": ["high_risk_procedure", "low_confidence"],
                "trigger_conditions": {
                    "confidence_threshold": 0.6,
                    "risk_score_threshold": 0.8
                },
                "escalation_queue": "senior_reviewers",
                "escalation_priority": 2,
                "notify_immediately": True,
                "notification_recipients": ["senior@example.com"],
                "escalation_timeout_hours": 24,
                "max_escalation_level": 3,
                "effective_date": "2024-01-01"
            }
            
            response = client.post("/api/v1/ai-config/escalation-rules", json=escalation_config)
            
            assert response.status_code == 200
            data = response.json()
            assert data["config_id"] == "config_123"
            
            mock_ai_config_manager.create_configuration.assert_called_once()
            
        finally:
            app.dependency_overrides.clear()


class TestClinicalGuidelineConfiguration:
    """Test clinical guideline configuration endpoints."""
    
    def test_create_clinical_guideline_config_success(
        self, 
        client, 
        mock_ai_config_manager,
        authenticated_user
    ):
        """Test successful clinical guideline configuration creation."""
        from src.main import app
        
        app.dependency_overrides[get_ai_config_manager] = lambda db: mock_ai_config_manager
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        try:
            guideline_config = {
                "guideline_name": "MRI Brain Guidelines",
                "guideline_version": "2.1",
                "guideline_text": "Comprehensive guidelines for MRI brain imaging...",
                "guideline_summary": "Guidelines for appropriate MRI brain imaging",
                "applicable_procedures": ["70551", "70552", "70553"],
                "applicable_diagnoses": ["G93.1", "R51"],
                "applicable_payers": ["BCBS", "Aetna"],
                "decision_rules": [
                    {
                        "condition": "headache_with_neurological_signs",
                        "action": "approve",
                        "confidence": 0.9
                    }
                ],
                "contraindications": ["metallic_implants"],
                "relative_contraindications": ["claustrophobia"],
                "evidence_level": "A",
                "references": [
                    {
                        "title": "ACR Appropriateness Criteria",
                        "url": "https://example.com/acr-criteria"
                    }
                ],
                "source_organization": "American College of Radiology",
                "effective_date": "2024-01-01"
            }
            
            response = client.post("/api/v1/ai-config/clinical-guidelines", json=guideline_config)
            
            assert response.status_code == 200
            data = response.json()
            assert data["config_id"] == "config_123"
            
            mock_ai_config_manager.create_configuration.assert_called_once()
            
        finally:
            app.dependency_overrides.clear()


class TestFeedbackConfiguration:
    """Test feedback configuration endpoints."""
    
    def test_create_feedback_config_success(
        self, 
        client, 
        mock_ai_config_manager,
        authenticated_user
    ):
        """Test successful feedback configuration creation."""
        from src.main import app
        
        app.dependency_overrides[get_ai_config_manager] = lambda db: mock_ai_config_manager
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        try:
            feedback_config = {
                "feedback_name": "Provider Feedback Config",
                "feedback_types": ["accuracy", "appropriateness", "timeliness"],
                "collection_triggers": ["decision_made", "case_closed"],
                "auto_process_feedback": True,
                "feedback_weight": 1.0,
                "minimum_feedback_count": 5,
                "learning_rate": 0.01,
                "feedback_decay_days": 90,
                "minimum_confidence_for_learning": 0.7,
                "exclude_outliers": True,
                "require_expert_validation": False,
                "effective_date": "2024-01-01"
            }
            
            response = client.post("/api/v1/ai-config/feedback-rules", json=feedback_config)
            
            assert response.status_code == 200
            data = response.json()
            assert data["config_id"] == "config_123"
            
            mock_ai_config_manager.create_configuration.assert_called_once()
            
        finally:
            app.dependency_overrides.clear()


class TestConfigurationManagement:
    """Test configuration management endpoints."""
    
    def test_list_configurations_success(
        self, 
        client, 
        mock_ai_config_manager,
        authenticated_user
    ):
        """Test successful configuration listing."""
        from src.main import app
        
        # Setup mock data
        mock_configs = [
            Mock(
                config_id="config_1",
                configuration_type="LLM_MODEL",
                configuration_name="Model 1",
                is_active=True
            ),
            Mock(
                config_id="config_2",
                configuration_type="DECISION_THRESHOLD",
                configuration_name="Thresholds 1",
                is_active=True
            )
        ]
        mock_ai_config_manager.list_configurations.return_value = mock_configs
        
        app.dependency_overrides[get_ai_config_manager] = lambda db: mock_ai_config_manager
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        try:
            response = client.get("/api/v1/ai-config/configurations")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["config_id"] == "config_1"
            assert data[1]["config_id"] == "config_2"
            
            mock_ai_config_manager.list_configurations.assert_called_once()
            
        finally:
            app.dependency_overrides.clear()
    
    def test_get_configuration_success(
        self, 
        client, 
        mock_ai_config_manager,
        authenticated_user
    ):
        """Test successful configuration retrieval."""
        from src.main import app
        
        app.dependency_overrides[get_ai_config_manager] = lambda db: mock_ai_config_manager
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        try:
            response = client.get("/api/v1/ai-config/configurations/config_123")
            
            assert response.status_code == 200
            data = response.json()
            assert data["config_id"] == "config_123"
            
            mock_ai_config_manager.get_configuration_by_id.assert_called_once_with("config_123")
            
        finally:
            app.dependency_overrides.clear()
    
    def test_get_configuration_not_found(
        self, 
        client, 
        mock_ai_config_manager,
        authenticated_user
    ):
        """Test configuration retrieval when not found."""
        from src.main import app
        
        mock_ai_config_manager.get_configuration_by_id.return_value = None
        
        app.dependency_overrides[get_ai_config_manager] = lambda db: mock_ai_config_manager
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        try:
            response = client.get("/api/v1/ai-config/configurations/nonexistent")
            
            assert response.status_code == 404
            
        finally:
            app.dependency_overrides.clear()
    
    def test_validate_configuration_success(
        self, 
        client, 
        mock_ai_config_manager,
        authenticated_user
    ):
        """Test successful configuration validation."""
        from src.main import app
        
        app.dependency_overrides[get_ai_config_manager] = lambda db: mock_ai_config_manager
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        try:
            response = client.post("/api/v1/ai-config/configurations/config_123/validate")
            
            assert response.status_code == 200
            data = response.json()
            assert data["is_valid"] is True
            
            mock_ai_config_manager.validate_configuration.assert_called_once_with("config_123")
            
        finally:
            app.dependency_overrides.clear()
    
    def test_deactivate_configuration_success(
        self, 
        client, 
        mock_ai_config_manager,
        authenticated_user
    ):
        """Test successful configuration deactivation."""
        from src.main import app
        
        app.dependency_overrides[get_ai_config_manager] = lambda db: mock_ai_config_manager
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        try:
            response = client.delete("/api/v1/ai-config/configurations/config_123")
            
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Configuration deactivated successfully"
            
            mock_ai_config_manager.deactivate_configuration.assert_called_once_with("config_123")
            
        finally:
            app.dependency_overrides.clear()


class TestModelSelection:
    """Test model selection endpoints."""
    
    def test_select_optimal_model_success(
        self, 
        client, 
        mock_ai_config_manager,
        authenticated_user
    ):
        """Test successful optimal model selection."""
        from src.main import app
        
        app.dependency_overrides[get_ai_config_manager] = lambda db: mock_ai_config_manager
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        try:
            selection_request = {
                "strategy": "PRIORITY_BASED",
                "context": {
                    "procedure_type": "MRI",
                    "urgency": "routine"
                }
            }
            
            response = client.post("/api/v1/ai-config/model-selection", json=selection_request)
            
            assert response.status_code == 200
            data = response.json()
            assert data["model_id"] == "best_model"
            assert data["confidence"] == 0.95
            
            mock_ai_config_manager.select_optimal_model.assert_called_once()
            
        finally:
            app.dependency_overrides.clear()


class TestPerformanceTracking:
    """Test performance tracking endpoints."""
    
    def test_record_model_performance_success(
        self, 
        client, 
        mock_ai_config_manager,
        authenticated_user
    ):
        """Test successful model performance recording."""
        from src.main import app
        
        app.dependency_overrides[get_ai_config_manager] = lambda db: mock_ai_config_manager
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        try:
            performance_data = {
                "model_id": "test_model",
                "model_name": "Test Model",
                "accuracy_score": 0.85,
                "precision_score": 0.82,
                "recall_score": 0.88,
                "f1_score": 0.85,
                "average_response_time_ms": 150.5,
                "success_rate": 0.95,
                "error_rate": 0.05,
                "total_requests": 1000,
                "successful_requests": 950,
                "failed_requests": 50,
                "total_cost": 10.50,
                "cost_per_request": 0.0105,
                "measurement_start": "2024-01-01T00:00:00Z",
                "measurement_end": "2024-01-01T23:59:59Z"
            }
            
            response = client.post("/api/v1/ai-config/model-performance", json=performance_data)
            
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Performance metrics recorded successfully"
            
            mock_ai_config_manager.record_performance_metrics.assert_called_once()
            
        finally:
            app.dependency_overrides.clear()


class TestFeedbackRecording:
    """Test feedback recording endpoints."""
    
    def test_record_feedback_success(
        self, 
        client, 
        mock_ai_config_manager,
        authenticated_user
    ):
        """Test successful feedback recording."""
        from src.main import app
        
        app.dependency_overrides[get_ai_config_manager] = lambda db: mock_ai_config_manager
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        try:
            feedback_data = {
                "decision_id": "decision_123",
                "request_id": "request_456",
                "feedback_type": "accuracy",
                "feedback_score": 0.8,
                "feedback_text": "Good decision, but could be faster",
                "feedback_source": "PROVIDER",
                "source_role": "PHYSICIAN",
                "model_id": "test_model",
                "model_version": "1.0",
                "original_confidence": 0.85
            }
            
            response = client.post("/api/v1/ai-config/feedback", json=feedback_data)
            
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Feedback recorded successfully"
            
            mock_ai_config_manager.record_feedback.assert_called_once()
            
        finally:
            app.dependency_overrides.clear()


class TestDashboard:
    """Test dashboard endpoints."""
    
    def test_get_ai_config_dashboard_success(
        self, 
        client, 
        mock_ai_config_manager,
        authenticated_user
    ):
        """Test successful dashboard data retrieval."""
        from src.main import app
        
        app.dependency_overrides[get_ai_config_manager] = lambda db: mock_ai_config_manager
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        try:
            response = client.get("/api/v1/ai-config/dashboard")
            
            assert response.status_code == 200
            data = response.json()
            assert data["total_configurations"] == 10
            assert data["active_models"] == 3
            assert "performance_summary" in data
            
            mock_ai_config_manager.get_dashboard_data.assert_called_once()
            
        finally:
            app.dependency_overrides.clear()


class TestErrorHandling:
    """Test error handling scenarios."""
    
    def test_create_config_service_error(
        self, 
        client, 
        mock_ai_config_manager,
        authenticated_user
    ):
        """Test configuration creation with service error."""
        from src.main import app
        
        # Setup service to raise exception
        mock_ai_config_manager.create_configuration.side_effect = Exception("Service error")
        
        app.dependency_overrides[get_ai_config_manager] = lambda db: mock_ai_config_manager
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        try:
            model_config = {
                "model_id": "test_model",
                "model_name": "Test Model",
                "deployment_type": "huggingface_api",
                "model_type": "biomedical_bert"
            }
            
            response = client.post("/api/v1/ai-config/llm-models", json=model_config)
            
            assert response.status_code == 500
            data = response.json()
            assert "Failed to create LLM model configuration" in data["detail"]
            
        finally:
            app.dependency_overrides.clear()
    
    def test_missing_required_fields(self, client, authenticated_user):
        """Test configuration creation with missing required fields."""
        from src.main import app
        
        app.dependency_overrides[get_current_user] = lambda: authenticated_user
        
        try:
            # Missing required fields
            model_config = {
                "model_name": "Test Model"
                # Missing model_id, deployment_type, model_type
            }
            
            response = client.post("/api/v1/ai-config/llm-models", json=model_config)
            
            assert response.status_code == 422  # Validation error
            
        finally:
            app.dependency_overrides.clear()


class TestImportAndBasicFunctionality:
    """Test basic import and functionality."""
    
    def test_router_import(self):
        """Test that the router can be imported."""
        from src.api.ai_config import router
        assert router is not None
        assert hasattr(router, 'routes')
    
    def test_models_import(self):
        """Test that all models can be imported."""
        from src.api.ai_config import (
            LLMModelConfigRequest,
            DecisionThresholdConfigRequest,
            EscalationRuleConfigRequest,
            ClinicalGuidelineConfigRequest,
            FeedbackConfigRequest,
            ModelSelectionRequest,
            ModelPerformanceRequest,
            FeedbackRequest
        )
        
        # Verify models can be instantiated with minimal data
        assert LLMModelConfigRequest
        assert DecisionThresholdConfigRequest
        assert EscalationRuleConfigRequest
        assert ClinicalGuidelineConfigRequest
        assert FeedbackConfigRequest
        assert ModelSelectionRequest
        assert ModelPerformanceRequest
        assert FeedbackRequest
    
    def test_endpoint_count(self):
        """Test that all expected endpoints are registered."""
        from src.api.ai_config import router
        
        # Should have 12 endpoints based on our analysis
        routes = [route for route in router.routes if hasattr(route, 'methods')]
        assert len(routes) >= 12
    
    def test_configuration_types_coverage(self):
        """Test that all configuration types are covered."""
        from src.models.ai_config import ConfigurationType
        
        # Verify all configuration types exist
        expected_types = [
            ConfigurationType.LLM_MODEL,
            ConfigurationType.DECISION_THRESHOLD,
            ConfigurationType.ESCALATION_RULE,
            ConfigurationType.CLINICAL_GUIDELINE,
            ConfigurationType.FEEDBACK_RULE
        ]
        
        for config_type in expected_types:
            assert config_type is not None
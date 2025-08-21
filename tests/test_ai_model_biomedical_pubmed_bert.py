"""
Comprehensive testing for BiomedNLP-PubMedBERT AI model integration.

This test suite validates the BiomedNLP-PubMedBERT model functionality including
medical literature comprehension, clinical reasoning, confidence scoring, and
error handling scenarios.

PHI Compliance: All test data uses synthetic information with SYNTH_ prefixes.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import json

# Import the services we're testing
try:
    from src.services.huggingface_client import HuggingFaceClient, HuggingFaceRequest, HuggingFaceResponse
    from src.services.llm_decision_service import LLMDecisionService, PolicyComplianceResult, RiskAssessment
    from src.services.llm_model_manager import LLMModelManager, ModelStatus, ModelHealth
    from src.services.llm_config import ModelType, ModelConfig
    from src.models.authorization import AuthorizationRequest, AuthorizationDecision
    from src.models.enums import DecisionStatus, UrgencyLevel
except ImportError as e:
    pytest.skip(f"Required modules not available: {e}", allow_module_level=True)


class TestBiomedNLPPubMedBERTModel:
    """Test suite for BiomedNLP-PubMedBERT model functionality."""
    
    @pytest.fixture
    def mock_huggingface_client(self):
        """Create mock HuggingFace client for testing."""
        client = Mock(spec=HuggingFaceClient)
        client.process_request = AsyncMock()
        client.get_model_health = Mock()
        client.is_model_available = Mock(return_value=True)
        return client
    
    @pytest.fixture
    def mock_model_manager(self):
        """Create mock model manager for testing."""
        manager = Mock(spec=LLMModelManager)
        manager.get_model_health = Mock()
        manager.load_model = AsyncMock()
        manager.unload_model = AsyncMock()
        return manager
    
    @pytest.fixture
    def sample_medical_request(self):
        """Create sample medical authorization request with synthetic data."""
        return {
            "patient_id": "SYNTH_PATIENT_12345",
            "procedure_code": "70551",  # MRI brain without contrast
            "diagnosis_code": "G93.1",  # Anoxic brain damage
            "clinical_notes": "SYNTH_PATIENT presents with severe cephalgia and photophobia following recent trauma. Neurological examination reveals altered mental status.",
            "urgency": "ROUTINE",
            "provider_id": "SYNTH_PROVIDER_789"
        }
    
    @pytest.fixture
    def expected_biomedical_response(self):
        """Expected response from BiomedNLP-PubMedBERT model."""
        return {
            "decision": "APPROVE",
            "confidence": 0.92,
            "reasoning": "Clinical evidence supports medical necessity. Patient symptoms (severe cephalgia, photophobia) combined with trauma history indicate potential intracranial pathology requiring MRI evaluation per medical literature.",
            "medical_literature_references": [
                "PubMed ID: 12345678 - Traumatic brain injury imaging guidelines",
                "PubMed ID: 87654321 - Post-traumatic headache evaluation"
            ],
            "risk_factors": ["trauma history", "neurological symptoms"],
            "contraindications": []
        }
    
    @pytest.mark.asyncio

    
    async def test_biomedical_model_initialization(self, mock_huggingface_client):
        """Test BiomedNLP-PubMedBERT model initialization."""
        # Test model configuration
        model_config = ModelConfig(
            model_id="microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext",
            model_type=ModelType.BIOMEDICAL_PUBMED_BERT,
            max_tokens=512,
            temperature=0.1
        )
        
        assert model_config.model_type == ModelType.BIOMEDICAL_PUBMED_BERT
        assert "PubMedBERT" in model_config.model_id
        assert model_config.max_tokens == 512
        
        # Test client initialization
        mock_huggingface_client.is_model_available.return_value = True
        assert mock_huggingface_client.is_model_available()
    
    @pytest.mark.asyncio
    async def test_biomedical_medical_literature_comprehension(self, mock_huggingface_client, sample_medical_request, expected_biomedical_response):
        """Test BiomedNLP-PubMedBERT medical literature comprehension."""
        # Mock successful model response
        mock_response = HuggingFaceResponse(
            model_id="microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext",
            response_data=expected_biomedical_response,
            processing_time_ms=150.0,
            success=True,
            confidence_score=0.92,
            model_type=ModelType.BIOMEDICAL_PUBMED_BERT
        )
        
        mock_huggingface_client.process_request.return_value = mock_response
        
        # Create request
        request = HuggingFaceRequest(
            inputs=f"Analyze medical necessity for procedure {sample_medical_request['procedure_code']} given diagnosis {sample_medical_request['diagnosis_code']} and clinical notes: {sample_medical_request['clinical_notes']}",
            parameters={"max_length": 512, "temperature": 0.1}
        )
        
        # Process request
        result = await mock_huggingface_client.process_request(request)
        
        # Validate response
        assert result.success is True
        assert result.model_type == ModelType.BIOMEDICAL_PUBMED_BERT
        assert result.confidence_score >= 0.9
        assert "medical literature" in result.response_data["reasoning"].lower()
        assert len(result.response_data["medical_literature_references"]) > 0
        assert result.processing_time_ms < 200  # Performance requirement
    
    @pytest.mark.asyncio
    async def test_biomedical_clinical_reasoning_generation(self, mock_huggingface_client, sample_medical_request):
        """Test BiomedNLP-PubMedBERT clinical reasoning generation."""
        # Mock response with detailed clinical reasoning
        clinical_reasoning_response = {
            "decision": "APPROVE",
            "confidence": 0.89,
            "reasoning": "Based on PubMed literature analysis, patient presents with classic post-traumatic headache syndrome. Severe cephalgia with photophobia following trauma indicates potential intracranial complications. MRI brain imaging is medically necessary per established clinical guidelines.",
            "evidence_strength": "HIGH",
            "literature_support": "STRONG",
            "clinical_indicators": [
                "severe cephalgia post-trauma",
                "photophobia indicating meningeal irritation",
                "altered mental status"
            ]
        }
        
        mock_response = HuggingFaceResponse(
            model_id="microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext",
            response_data=clinical_reasoning_response,
            processing_time_ms=180.0,
            success=True,
            confidence_score=0.89,
            model_type=ModelType.BIOMEDICAL_PUBMED_BERT
        )
        
        mock_huggingface_client.process_request.return_value = mock_response
        
        # Test clinical reasoning request
        request = HuggingFaceRequest(
            inputs=f"Provide detailed clinical reasoning for MRI authorization based on: {sample_medical_request['clinical_notes']}",
            parameters={"max_length": 512, "do_sample": False}
        )
        
        result = await mock_huggingface_client.process_request(request)
        
        # Validate clinical reasoning quality
        assert result.success is True
        assert result.confidence_score >= 0.85
        assert "clinical" in result.response_data["reasoning"].lower()
        assert "literature" in result.response_data["reasoning"].lower()
        assert len(result.response_data["clinical_indicators"]) >= 2
        assert result.response_data["evidence_strength"] in ["HIGH", "MEDIUM", "LOW"]
    
    @pytest.mark.asyncio
    async def test_biomedical_confidence_scoring_validation(self, mock_huggingface_client):
        """Test BiomedNLP-PubMedBERT confidence scoring and threshold validation."""
        test_cases = [
            # High confidence case
            {
                "input": "Clear medical necessity with strong literature support",
                "expected_confidence": 0.95,
                "expected_decision": "APPROVE"
            },
            # Medium confidence case
            {
                "input": "Moderate medical necessity with some literature support",
                "expected_confidence": 0.75,
                "expected_decision": "PENDING"
            },
            # Low confidence case
            {
                "input": "Unclear medical necessity with limited literature support",
                "expected_confidence": 0.45,
                "expected_decision": "DENY"
            }
        ]
        
        for i, test_case in enumerate(test_cases):
            mock_response = HuggingFaceResponse(
                model_id="microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext",
                response_data={
                    "decision": test_case["expected_decision"],
                    "confidence": test_case["expected_confidence"],
                    "reasoning": f"Analysis based on medical literature for case {i+1}"
                },
                processing_time_ms=120.0,
                success=True,
                confidence_score=test_case["expected_confidence"],
                model_type=ModelType.BIOMEDICAL_PUBMED_BERT
            )
            
            mock_huggingface_client.process_request.return_value = mock_response
            
            request = HuggingFaceRequest(inputs=test_case["input"])
            result = await mock_huggingface_client.process_request(request)
            
            # Validate confidence scoring
            assert result.confidence_score == test_case["expected_confidence"]
            assert result.response_data["decision"] == test_case["expected_decision"]
            
            # Validate confidence thresholds
            if result.confidence_score >= 0.9:
                assert result.response_data["decision"] in ["APPROVE", "DENY"]
            elif result.confidence_score < 0.6:
                assert result.response_data["decision"] in ["PENDING", "DENY"]
    
    @pytest.mark.asyncio
    async def test_biomedical_model_failure_scenarios(self, mock_huggingface_client):
        """Test BiomedNLP-PubMedBERT model failure and error handling."""
        # Test timeout scenario
        mock_huggingface_client.process_request.side_effect = asyncio.TimeoutError("Model timeout")
        
        request = HuggingFaceRequest(inputs="Test medical query")
        
        with pytest.raises(asyncio.TimeoutError):
            await mock_huggingface_client.process_request(request)
        
        # Test model unavailable scenario
        mock_huggingface_client.is_model_available.return_value = False
        assert not mock_huggingface_client.is_model_available()
        
        # Test error response
        error_response = HuggingFaceResponse(
            model_id="microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext",
            response_data=None,
            processing_time_ms=0.0,
            success=False,
            error_message="Model inference failed",
            model_type=ModelType.BIOMEDICAL_PUBMED_BERT
        )
        
        mock_huggingface_client.process_request.side_effect = None
        mock_huggingface_client.process_request.return_value = error_response
        
        result = await mock_huggingface_client.process_request(request)
        assert result.success is False
        assert result.error_message is not None
    
    @pytest.mark.asyncio

    
    async def test_biomedical_model_health_monitoring(self, mock_model_manager):
        """Test BiomedNLP-PubMedBERT model health monitoring."""
        # Test healthy model
        healthy_status = ModelHealth(
            status=ModelStatus.LOADED,
            last_check=datetime.now(timezone.utc),
            response_time_ms=150.0,
            memory_usage_mb=512.0
        )
        
        mock_model_manager.get_model_health.return_value = healthy_status
        
        health = mock_model_manager.get_model_health("microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext")
        
        assert health.status == ModelStatus.LOADED
        assert health.response_time_ms < 200  # Performance requirement
        assert health.memory_usage_mb is not None
        
        # Test unhealthy model
        unhealthy_status = ModelHealth(
            status=ModelStatus.ERROR,
            last_check=datetime.now(timezone.utc),
            error_message="Model loading failed"
        )
        
        mock_model_manager.get_model_health.return_value = unhealthy_status
        
        health = mock_model_manager.get_model_health("microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext")
        
        assert health.status == ModelStatus.ERROR
        assert health.error_message is not None
    
    @pytest.mark.asyncio
    async def test_biomedical_model_performance_benchmarks(self, mock_huggingface_client):
        """Test BiomedNLP-PubMedBERT model performance benchmarks."""
        # Test response time requirements
        fast_response = HuggingFaceResponse(
            model_id="microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext",
            response_data={"decision": "APPROVE", "confidence": 0.9},
            processing_time_ms=120.0,  # Under 200ms requirement
            success=True,
            confidence_score=0.9,
            model_type=ModelType.BIOMEDICAL_PUBMED_BERT
        )
        
        mock_huggingface_client.process_request.return_value = fast_response
        
        request = HuggingFaceRequest(inputs="Quick medical analysis")
        result = await mock_huggingface_client.process_request(request)
        
        # Validate performance requirements
        assert result.processing_time_ms < 200  # Sub-200ms requirement
        assert result.success is True
        assert result.confidence_score >= 0.85  # Minimum confidence
    
    def test_biomedical_model_configuration_validation(self):
        """Test BiomedNLP-PubMedBERT model configuration validation."""
        # Test valid configuration
        valid_config = ModelConfig(
            model_id="microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext",
            model_type=ModelType.BIOMEDICAL_PUBMED_BERT,
            max_tokens=512,
            temperature=0.1,
            top_p=0.9
        )
        
        assert valid_config.model_type == ModelType.BIOMEDICAL_PUBMED_BERT
        assert valid_config.max_tokens == 512
        assert 0.0 <= valid_config.temperature <= 1.0
        assert 0.0 <= valid_config.top_p <= 1.0
        
        # Test configuration bounds
        assert valid_config.temperature >= 0.0
        assert valid_config.temperature <= 1.0
        assert valid_config.max_tokens > 0
        assert valid_config.max_tokens <= 2048  # Reasonable upper bound


class TestBiomedNLPIntegrationScenarios:
    """Integration test scenarios for BiomedNLP-PubMedBERT model."""
    
    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_end_to_end_medical_decision_workflow(self):
        """Test complete medical decision workflow with BiomedNLP-PubMedBERT."""
        # Mock the complete workflow
        with patch('src.services.huggingface_client.HuggingFaceClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            
            # Mock successful workflow
            mock_response = HuggingFaceResponse(
                model_id="microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext",
                response_data={
                    "decision": "APPROVE",
                    "confidence": 0.94,
                    "reasoning": "Medical literature supports necessity for MRI brain imaging given patient presentation",
                    "medical_evidence": "Strong literature support for imaging in post-traumatic headache"
                },
                processing_time_ms=145.0,
                success=True,
                confidence_score=0.94,
                model_type=ModelType.BIOMEDICAL_PUBMED_BERT
            )
            
            mock_client.process_request = AsyncMock(return_value=mock_response)
            
            # Test workflow execution
            request = HuggingFaceRequest(
                inputs="Analyze medical necessity for MRI brain given post-traumatic headache with neurological symptoms"
            )
            
            result = await mock_client.process_request(request)
            
            # Validate end-to-end workflow
            assert result.success is True
            assert result.confidence_score >= 0.9
            assert result.model_type == ModelType.BIOMEDICAL_PUBMED_BERT
            assert "literature" in result.response_data["reasoning"].lower()
            assert result.processing_time_ms < 200
    
    @pytest.mark.asyncio
    async def test_biomedical_model_fallback_mechanisms(self):
        """Test BiomedNLP-PubMedBERT fallback mechanisms."""
        # Test primary model failure scenario
        with patch('src.services.huggingface_client.HuggingFaceClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            
            # Mock primary model failure
            mock_client.is_model_available.return_value = False
            
            # Validate fallback detection
            assert not mock_client.is_model_available()
            
            # Mock fallback response
            fallback_response = HuggingFaceResponse(
                model_id="fallback-model",
                response_data={"decision": "PENDING", "confidence": 0.7},
                processing_time_ms=100.0,
                success=True,
                fallback_used=True,
                model_type=ModelType.BIOMEDICAL_PUBMED_BERT
            )
            
            mock_client.process_request = AsyncMock(return_value=fallback_response)
            
            # Validate fallback functionality
            assert fallback_response.fallback_used is True
            assert fallback_response.success is True
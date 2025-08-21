#!/usr/bin/env python3
"""
Test script for AI Configuration Management implementation.

This script tests the AI configuration management system without requiring
database migrations, using in-memory SQLite for testing.
"""

import asyncio
import sys
import os
from datetime import date, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.database.base import Base
from src.services.ai_config_manager import AIConfigurationManager
from src.models.ai_config import (
    ConfigurationType, AIConfigurationRequest, 
    ModelSelectionStrategy, DecisionThresholdConfig
)


def create_test_database():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    
    # Create all tables
    Base.metadata.create_all(engine)
    
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


@pytest.mark.asyncio
async def test_llm_model_configuration():
    """Test LLM model configuration creation and management."""
    print("Testing LLM Model Configuration...")
    
    db_session = create_test_database()
    config_manager = AIConfigurationManager(db_session)
    
    # Test creating LLM model configuration
    llm_config_data = {
        "model_id": "microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext",
        "model_name": "Microsoft BiomedNLP-PubMedBERT",
        "deployment_type": "huggingface_api",
        "model_type": "pubmed_bert",
        "priority": 1,
        "enabled": True,
        "max_tokens": 512,
        "temperature": 0.1,
        "confidence_threshold": 0.8,
        "timeout_seconds": 30,
        "max_retries": 3,
        "use_auth_token": True,
        "max_requests_per_minute": 60,
        "max_concurrent_requests": 10,
        "cost_per_request": 0.001
    }
    
    config_request = AIConfigurationRequest(
        configuration_type=ConfigurationType.LLM_MODEL,
        configuration_data=llm_config_data,
        is_active=True
    )
    
    try:
        config_id = await config_manager.create_configuration(
            config_request=config_request,
            created_by="test_user"
        )
        print(f"✓ Created LLM model configuration: {config_id}")
        
        # Test retrieving configuration
        config = config_manager.get_configuration_by_id(config_id)
        assert config is not None
        assert config.configuration_type == ConfigurationType.LLM_MODEL.value
        print(f"✓ Retrieved configuration: {config.configuration_name}")
        
        # Test listing configurations
        configs = config_manager.list_configurations(
            configuration_type=ConfigurationType.LLM_MODEL
        )
        assert len(configs) == 1
        print(f"✓ Listed {len(configs)} LLM model configurations")
        
        # Test validation
        validation_result = await config_manager.validate_configuration(config_id)
        assert validation_result.is_valid
        print(f"✓ Configuration validation passed")
        
    except Exception as e:
        print(f"✗ LLM model configuration test failed: {str(e)}")
        return False
    
    return True


async def test_decision_threshold_configuration():
    """Test decision threshold configuration."""
    print("\nTesting Decision Threshold Configuration...")
    
    db_session = create_test_database()
    config_manager = AIConfigurationManager(db_session)
    
    threshold_config_data = {
        "config_name": "Default Thresholds",
        "auto_approve_threshold": 0.9,
        "auto_deny_threshold": 0.8,
        "manual_review_threshold": 0.6,
        "high_risk_adjustment": -0.1,
        "low_risk_adjustment": 0.05,
        "procedure_thresholds": {
            "70551": {"auto_approve_threshold": 0.95}  # MRI Brain
        },
        "payer_thresholds": {
            "BCBS": {"auto_approve_threshold": 0.85}
        }
    }
    
    config_request = AIConfigurationRequest(
        configuration_type=ConfigurationType.DECISION_THRESHOLD,
        configuration_data=threshold_config_data,
        effective_date=date.today(),
        is_active=True
    )
    
    try:
        config_id = await config_manager.create_configuration(
            config_request=config_request,
            created_by="test_user"
        )
        print(f"✓ Created decision threshold configuration: {config_id}")
        
        # Test validation
        validation_result = await config_manager.validate_configuration(config_id)
        assert validation_result.is_valid
        print(f"✓ Decision threshold validation passed")
        
        # Test getting effective configuration
        effective_config = await config_manager.get_effective_configuration(
            ConfigurationType.DECISION_THRESHOLD
        )
        assert effective_config is not None
        print(f"✓ Retrieved effective configuration: {effective_config.configuration_name}")
        
    except Exception as e:
        print(f"✗ Decision threshold configuration test failed: {str(e)}")
        return False
    
    return True


async def test_model_selection():
    """Test model selection functionality."""
    print("\nTesting Model Selection...")
    
    db_session = create_test_database()
    config_manager = AIConfigurationManager(db_session)
    
    # Create multiple model configurations
    models = [
        {
            "model_id": "microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext",
            "model_name": "Microsoft BiomedNLP-PubMedBERT",
            "deployment_type": "huggingface_api",
            "model_type": "pubmed_bert",
            "priority": 1,
            "enabled": True
        },
        {
            "model_id": "emilyalsentzer/Bio_ClinicalBERT",
            "model_name": "Clinical BERT",
            "deployment_type": "huggingface_api",
            "model_type": "clinical_bert",
            "priority": 2,
            "enabled": True
        },
        {
            "model_id": "distilbert-base-uncased",
            "model_name": "Fallback Model",
            "deployment_type": "huggingface_api",
            "model_type": "fallback",
            "priority": 10,
            "enabled": True
        }
    ]
    
    try:
        # Create model configurations
        for model_data in models:
            config_request = AIConfigurationRequest(
                configuration_type=ConfigurationType.LLM_MODEL,
                configuration_data=model_data,
                is_active=True
            )
            
            await config_manager.create_configuration(
                config_request=config_request,
                created_by="test_user"
            )
        
        print(f"✓ Created {len(models)} model configurations")
        
        # Test priority-based selection
        selected_model = await config_manager.select_optimal_model(
            strategy=ModelSelectionStrategy.PRIORITY_BASED
        )
        assert selected_model == "microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext"
        print(f"✓ Priority-based selection: {selected_model}")
        
        # Test complexity-based selection with context
        context = {
            "diagnosis_codes": ["G93.1", "R51"],
            "clinical_notes": "Patient presents with severe headaches and neurological symptoms."
        }
        
        selected_model = await config_manager.select_optimal_model(
            strategy=ModelSelectionStrategy.COMPLEXITY_BASED,
            context=context
        )
        print(f"✓ Complexity-based selection: {selected_model}")
        
    except Exception as e:
        print(f"✗ Model selection test failed: {str(e)}")
        return False
    
    return True


async def test_performance_metrics():
    """Test performance metrics recording."""
    print("\nTesting Performance Metrics...")
    
    db_session = create_test_database()
    config_manager = AIConfigurationManager(db_session)
    
    performance_data = {
        "model_name": "Microsoft BiomedNLP-PubMedBERT",
        "accuracy_score": 0.92,
        "precision_score": 0.89,
        "recall_score": 0.94,
        "f1_score": 0.91,
        "average_response_time_ms": 1250.5,
        "success_rate": 0.98,
        "error_rate": 0.02,
        "total_requests": 1000,
        "successful_requests": 980,
        "failed_requests": 20,
        "total_cost": 1.50,
        "cost_per_request": 0.0015,
        "measurement_start": datetime.now(),
        "measurement_end": datetime.now()
    }
    
    try:
        metric_id = await config_manager.record_model_performance(
            model_id="microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext",
            performance_data=performance_data
        )
        print(f"✓ Recorded performance metrics: {metric_id}")
        
    except Exception as e:
        print(f"✗ Performance metrics test failed: {str(e)}")
        return False
    
    return True


async def test_feedback_system():
    """Test feedback recording system."""
    print("\nTesting Feedback System...")
    
    db_session = create_test_database()
    config_manager = AIConfigurationManager(db_session)
    
    feedback_data = {
        "feedback_type": "decision_accuracy",
        "feedback_score": 0.85,
        "feedback_text": "Decision was accurate but reasoning could be clearer",
        "feedback_source": "PROVIDER",
        "source_role": "physician",
        "model_id": "microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext",
        "model_version": "1.0",
        "original_confidence": 0.82
    }
    
    try:
        feedback_id = await config_manager.record_feedback(
            decision_id="test_decision_123",
            request_id="test_request_123",
            feedback_data=feedback_data,
            source_user_id="test_provider"
        )
        print(f"✓ Recorded feedback: {feedback_id}")
        
    except Exception as e:
        print(f"✗ Feedback system test failed: {str(e)}")
        return False
    
    return True


async def main():
    """Run all tests."""
    print("AI Configuration Management System Test")
    print("=" * 50)
    
    tests = [
        test_llm_model_configuration,
        test_decision_threshold_configuration,
        test_model_selection,
        test_performance_metrics,
        test_feedback_system
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if await test():
                passed += 1
        except Exception as e:
            print(f"✗ Test failed with exception: {str(e)}")
    
    print("\n" + "=" * 50)
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! AI Configuration Management system is working correctly.")
        return True
    else:
        print("❌ Some tests failed. Please check the implementation.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
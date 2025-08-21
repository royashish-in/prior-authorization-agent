"""
LLM Configuration Management

This module handles configuration for different LLM models and endpoints,
supporting both Hugging Face API and local model deployments.
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings
import os


class ModelType(str, Enum):
    """Supported LLM model types for medical decision making."""
    BIOMEDICAL_BERT = "biomedical_bert"
    CLINICAL_BERT = "clinical_bert"
    PUBMED_BERT = "pubmed_bert"
    GENERAL_MEDICAL = "general_medical"
    FALLBACK = "fallback"


class DeploymentType(str, Enum):
    """Model deployment options."""
    HUGGINGFACE_API = "huggingface_api"
    LOCAL_MODEL = "local_model"
    INFERENCE_ENDPOINT = "inference_endpoint"


class ModelConfig(BaseModel):
    """Configuration for a specific LLM model."""
    name: str = Field(..., description="Human-readable model name")
    model_id: str = Field(..., description="Hugging Face model identifier or local path")
    deployment_type: DeploymentType
    model_type: ModelType
    max_tokens: int = Field(default=512, ge=1, le=4096)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    max_retries: int = Field(default=3, ge=0, le=10)
    enabled: bool = Field(default=True)
    priority: int = Field(default=1, ge=1, le=10, description="Lower number = higher priority")
    
    # Model-specific parameters
    use_auth_token: bool = Field(default=True)
    device: Optional[str] = Field(default=None, description="cuda, cpu, or auto")
    torch_dtype: Optional[str] = Field(default="auto")
    load_in_8bit: bool = Field(default=False)
    load_in_4bit: bool = Field(default=False)
    
    @field_validator('model_id')
    @classmethod
    def validate_model_id(cls, v):
        if not v or not v.strip():
            raise ValueError("model_id cannot be empty")
        return v.strip()
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Microsoft BiomedNLP-PubMedBERT",
                "model_id": "microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext",
                "deployment_type": "huggingface_api",
                "model_type": "pubmed_bert",
                "max_tokens": 512,
                "temperature": 0.1,
                "top_p": 0.9,
                "confidence_threshold": 0.8,
                "timeout_seconds": 45,
                "max_retries": 3,
                "enabled": True,
                "priority": 1,
                "use_auth_token": True,
                "device": "auto",
                "torch_dtype": "auto",
                "load_in_8bit": False,
                "load_in_4bit": False
            }
        }
    )


class LLMSettings(BaseSettings):
    """LLM integration settings loaded from environment variables."""
    
    # Hugging Face API Configuration
    huggingface_api_token: Optional[str] = Field(
        default=None,
        env="HUGGINGFACE_API_TOKEN",
        description="Hugging Face API token for model access"
    )
    huggingface_api_url: str = Field(
        default="https://api-inference.huggingface.co/models",
        env="HUGGINGFACE_API_URL"
    )
    
    # Local Model Configuration
    local_models_path: str = Field(
        default="./models",
        env="LOCAL_MODELS_PATH",
        description="Path to store local models"
    )
    
    # Performance Settings
    max_concurrent_requests: int = Field(
        default=10,
        env="LLM_MAX_CONCURRENT_REQUESTS",
        ge=1,
        le=100
    )
    default_timeout: int = Field(
        default=30,
        env="LLM_DEFAULT_TIMEOUT",
        ge=1,
        le=300
    )
    
    # Caching Settings
    enable_response_cache: bool = Field(
        default=True,
        env="LLM_ENABLE_CACHE"
    )
    cache_ttl_seconds: int = Field(
        default=3600,
        env="LLM_CACHE_TTL",
        ge=60,
        le=86400
    )
    
    # Health Check Settings
    health_check_interval: int = Field(
        default=300,
        env="LLM_HEALTH_CHECK_INTERVAL",
        ge=60,
        le=3600
    )
    
    # Fallback Settings
    enable_fallback: bool = Field(
        default=True,
        env="LLM_ENABLE_FALLBACK"
    )
    fallback_to_rules: bool = Field(
        default=True,
        env="LLM_FALLBACK_TO_RULES",
        description="Fall back to rule-based engine if all LLMs fail"
    )
    
    model_config = ConfigDict(
        env_file=".env",
        env_prefix="LLM_",
        extra="ignore"  # Ignore extra environment variables
    )


class LLMConfigManager:
    """Manages LLM model configurations and provides model selection logic."""
    
    def __init__(self):
        self.settings = LLMSettings()
        self._models: Dict[str, ModelConfig] = {}
        self._load_default_models()
    
    def _load_default_models(self):
        """Load default model configurations."""
        default_models = [
            ModelConfig(
                name="Flan-T5 Small",
                model_id="google/flan-t5-small",
                deployment_type=DeploymentType.HUGGINGFACE_API,
                model_type=ModelType.GENERAL_MEDICAL,
                priority=1,
                confidence_threshold=0.7,
                max_tokens=512,
                max_retries=3,
                timeout_seconds=30
            ),
            ModelConfig(
                name="Clinical BERT",
                model_id="emilyalsentzer/Bio_ClinicalBERT",
                deployment_type=DeploymentType.HUGGINGFACE_API,
                model_type=ModelType.CLINICAL_BERT,
                priority=2,
                confidence_threshold=0.75,
                max_tokens=512,
                max_retries=3,
                timeout_seconds=40
            ),
            ModelConfig(
                name="BioBERT",
                model_id="dmis-lab/biobert-base-cased-v1.2",
                deployment_type=DeploymentType.HUGGINGFACE_API,
                model_type=ModelType.BIOMEDICAL_BERT,
                priority=3,
                confidence_threshold=0.7,
                max_tokens=512,
                max_retries=2,
                timeout_seconds=35
            ),
            ModelConfig(
                name="Clinical BERT Alternative",
                model_id="medicalai/ClinicalBERT",
                deployment_type=DeploymentType.HUGGINGFACE_API,
                model_type=ModelType.CLINICAL_BERT,
                priority=4,
                confidence_threshold=0.7,
                max_tokens=512,
                max_retries=2,
                timeout_seconds=30
            ),
            ModelConfig(
                name="Fallback Model",
                model_id="distilbert-base-uncased",
                deployment_type=DeploymentType.HUGGINGFACE_API,
                model_type=ModelType.FALLBACK,
                priority=10,
                confidence_threshold=0.6,
                max_tokens=256,
                max_retries=1,
                timeout_seconds=20,
                enabled=self.settings.enable_fallback
            )
        ]
        
        for model in default_models:
            self._models[model.model_id] = model
    
    def get_model_config(self, model_id: str) -> Optional[ModelConfig]:
        """Get configuration for a specific model."""
        return self._models.get(model_id)
    
    def get_models_by_type(self, model_type: ModelType) -> List[ModelConfig]:
        """Get all models of a specific type, sorted by priority."""
        models = [
            model for model in self._models.values()
            if model.model_type == model_type and model.enabled
        ]
        return sorted(models, key=lambda x: x.priority)
    
    def get_primary_model(self) -> Optional[ModelConfig]:
        """Get the primary (highest priority) enabled model."""
        enabled_models = [m for m in self._models.values() if m.enabled]
        if not enabled_models:
            return None
        return min(enabled_models, key=lambda x: x.priority)
    
    def get_fallback_models(self) -> List[ModelConfig]:
        """Get fallback models in priority order."""
        return self.get_models_by_type(ModelType.FALLBACK)
    
    def add_model(self, model_config: ModelConfig) -> None:
        """Add or update a model configuration."""
        self._models[model_config.model_id] = model_config
    
    def remove_model(self, model_id: str) -> bool:
        """Remove a model configuration."""
        if model_id in self._models:
            del self._models[model_id]
            return True
        return False
    
    def list_models(self) -> List[ModelConfig]:
        """List all configured models."""
        return list(self._models.values())
    
    def get_enabled_models(self) -> List[ModelConfig]:
        """Get all enabled models sorted by priority."""
        enabled = [m for m in self._models.values() if m.enabled]
        return sorted(enabled, key=lambda x: x.priority)
    
    def validate_configuration(self) -> List[str]:
        """Validate the current configuration and return any issues."""
        issues = []
        
        if not self._models:
            issues.append("No models configured")
            return issues
        
        enabled_models = self.get_enabled_models()
        if not enabled_models:
            issues.append("No enabled models found")
        
        # Check for Hugging Face API token if needed
        api_models = [
            m for m in enabled_models
            if m.deployment_type == DeploymentType.HUGGINGFACE_API
        ]
        if api_models and not self.settings.huggingface_api_token:
            issues.append("Hugging Face API token required but not configured")
        
        # Check for duplicate priorities
        priorities = [m.priority for m in enabled_models]
        if len(priorities) != len(set(priorities)):
            issues.append("Duplicate model priorities detected")
        
        return issues
    
    def add_model(self, model_config: ModelConfig) -> None:
        """Add or update a model configuration."""
        self._models[model_config.model_id] = model_config
    
    def remove_model(self, model_id: str) -> bool:
        """Remove a model configuration."""
        if model_id in self._models:
            del self._models[model_id]
            return True
        return False
    
    def get_model_config(self, model_id: str) -> Optional[ModelConfig]:
        """Get configuration for a specific model."""
        return self._models.get(model_id)
    
    def get_all_models(self) -> List[ModelConfig]:
        """Get all model configurations."""
        return list(self._models.values())
    
    def get_enabled_models(self) -> List[ModelConfig]:
        """Get all enabled model configurations sorted by priority."""
        enabled = [model for model in self._models.values() if model.enabled]
        return sorted(enabled, key=lambda x: x.priority)
    
    def get_models_by_type(self, model_type: ModelType) -> List[ModelConfig]:
        """Get models of a specific type."""
        return [
            model for model in self._models.values()
            if model.model_type == model_type and model.enabled
        ]
    
    def get_primary_model(self) -> Optional[ModelConfig]:
        """Get the primary (highest priority) enabled model."""
        enabled_models = self.get_enabled_models()
        return enabled_models[0] if enabled_models else None
    
    def get_fallback_models(self, exclude_model_id: Optional[str] = None) -> List[ModelConfig]:
        """Get fallback models excluding the specified model."""
        enabled_models = self.get_enabled_models()
        
        if exclude_model_id:
            enabled_models = [
                model for model in enabled_models
                if model.model_id != exclude_model_id
            ]
        
        # Return models sorted by priority (excluding the primary)
        return enabled_models[1:] if len(enabled_models) > 1 else []
    
    def get_model_for_task(self, task_type: str, complexity: str = "medium") -> Optional[ModelConfig]:
        """Get the best model for a specific task type and complexity."""
        enabled_models = self.get_enabled_models()
        
        if not enabled_models:
            return None
        
        # Task-specific model selection logic
        if task_type == "medical_reasoning":
            # Prefer medical-specific models
            medical_models = [
                model for model in enabled_models
                if model.model_type in [ModelType.PUBMED_BERT, ModelType.CLINICAL_BERT, ModelType.BIOMEDICAL_BERT]
            ]
            if medical_models:
                return medical_models[0]
        
        elif task_type == "policy_compliance":
            # Prefer models with higher confidence thresholds
            policy_models = sorted(
                enabled_models,
                key=lambda x: x.confidence_threshold,
                reverse=True
            )
            return policy_models[0]
        
        elif task_type == "quick_decision":
            # Prefer faster models with lower timeouts
            quick_models = sorted(
                enabled_models,
                key=lambda x: (x.timeout_seconds, x.max_tokens)
            )
            return quick_models[0]
        
        # Default to primary model
        return enabled_models[0]
    
    def update_model_config(self, model_id: str, updates: Dict[str, Any]) -> bool:
        """Update specific fields of a model configuration."""
        if model_id not in self._models:
            return False
        
        model = self._models[model_id]
        
        # Update allowed fields
        allowed_fields = {
            'enabled', 'priority', 'confidence_threshold', 'max_tokens',
            'temperature', 'top_p', 'timeout_seconds', 'max_retries'
        }
        
        for field, value in updates.items():
            if field in allowed_fields and hasattr(model, field):
                setattr(model, field, value)
        
        return True
    
    def validate_configuration(self) -> Dict[str, List[str]]:
        """Validate the current configuration and return any issues."""
        issues = {
            'errors': [],
            'warnings': []
        }
        
        enabled_models = self.get_enabled_models()
        
        if not enabled_models:
            issues['errors'].append("No enabled models configured")
            return issues
        
        # Check for API token if using Hugging Face API
        api_models = [
            model for model in enabled_models
            if model.deployment_type == DeploymentType.HUGGINGFACE_API
        ]
        
        if api_models and not self.settings.huggingface_api_token:
            issues['warnings'].append(
                "Hugging Face API models configured but no API token provided"
            )
        
        # Check for duplicate priorities
        priorities = [model.priority for model in enabled_models]
        if len(priorities) != len(set(priorities)):
            issues['warnings'].append("Duplicate model priorities detected")
        
        # Check for reasonable timeout values
        for model in enabled_models:
            if model.timeout_seconds > 60:
                issues['warnings'].append(
                    f"Model {model.model_id} has high timeout ({model.timeout_seconds}s)"
                )
        
        return issues
    
    def get_configuration_summary(self) -> Dict[str, Any]:
        """Get a summary of the current configuration."""
        enabled_models = self.get_enabled_models()
        
        return {
            'total_models': len(self._models),
            'enabled_models': len(enabled_models),
            'primary_model': enabled_models[0].model_id if enabled_models else None,
            'model_types': {
                model_type.value: len(self.get_models_by_type(model_type))
                for model_type in ModelType
            },
            'deployment_types': {
                deployment_type.value: len([
                    model for model in enabled_models
                    if model.deployment_type == deployment_type
                ])
                for deployment_type in DeploymentType
            },
            'settings': {
                'max_concurrent_requests': self.settings.max_concurrent_requests,
                'default_timeout': self.settings.default_timeout,
                'enable_response_cache': self.settings.enable_response_cache,
                'enable_fallback': self.settings.enable_fallback
            }
        }
    
    def export_configuration(self) -> Dict[str, Any]:
        """Export the current configuration to a dictionary."""
        return {
            'models': {
                model_id: {
                    'name': model.name,
                    'model_id': model.model_id,
                    'deployment_type': model.deployment_type.value,
                    'model_type': model.model_type.value,
                    'enabled': model.enabled,
                    'priority': model.priority,
                    'confidence_threshold': model.confidence_threshold,
                    'max_tokens': model.max_tokens,
                    'temperature': model.temperature,
                    'top_p': model.top_p,
                    'timeout_seconds': model.timeout_seconds,
                    'max_retries': model.max_retries
                }
                for model_id, model in self._models.items()
            },
            'settings': {
                'max_concurrent_requests': self.settings.max_concurrent_requests,
                'default_timeout': self.settings.default_timeout,
                'enable_response_cache': self.settings.enable_response_cache,
                'cache_ttl_seconds': self.settings.cache_ttl_seconds,
                'health_check_interval': self.settings.health_check_interval,
                'enable_fallback': self.settings.enable_fallback,
                'fallback_to_rules': self.settings.fallback_to_rules
            }
        }
    
    def import_configuration(self, config_data: Dict[str, Any]) -> bool:
        """Import configuration from a dictionary."""
        try:
            # Clear existing models
            self._models.clear()
            
            # Import models
            if 'models' in config_data:
                for model_id, model_data in config_data['models'].items():
                    model_config = ModelConfig(
                        name=model_data['name'],
                        model_id=model_data['model_id'],
                        deployment_type=DeploymentType(model_data['deployment_type']),
                        model_type=ModelType(model_data['model_type']),
                        enabled=model_data.get('enabled', True),
                        priority=model_data.get('priority', 1),
                        confidence_threshold=model_data.get('confidence_threshold', 0.7),
                        max_tokens=model_data.get('max_tokens', 512),
                        temperature=model_data.get('temperature', 0.1),
                        top_p=model_data.get('top_p', 0.9),
                        timeout_seconds=model_data.get('timeout_seconds', 30),
                        max_retries=model_data.get('max_retries', 3)
                    )
                    self._models[model_id] = model_config
            
            # Import settings (settings are read-only from environment)
            # We don't update settings here as they come from environment variables
            
            return True
            
        except Exception as e:
            # Reload default models on error
            self._load_default_models()
            raise ValueError(f"Failed to import configuration: {str(e)}")


# Global LLM configuration manager
llm_config = LLMConfigManager()
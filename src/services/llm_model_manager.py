"""
LLM Model Manager

Manages loading, unloading, and health monitoring of local LLM models.
Provides model lifecycle management and resource optimization.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum
import os


class ModelStatus(Enum):
    """Model status enumeration."""
    NOT_LOADED = "not_loaded"
    LOADING = "loading"
    LOADED = "loaded"
    ERROR = "error"
    UNLOADING = "unloading"


@dataclass
class ModelHealth:
    """Model health information."""
    status: ModelStatus
    last_check: datetime
    response_time_ms: Optional[float] = None
    error_message: Optional[str] = None
    memory_usage_mb: Optional[float] = None


@dataclass
class LoadedModel:
    """Represents a loaded model."""
    model_id: str
    model_path: str
    pipeline: Optional[Any] = None
    tokenizer: Optional[Any] = None
    model: Optional[Any] = None
    load_time: Optional[datetime] = None
    last_used: Optional[datetime] = None


class LLMModelManager:
    """Manages local LLM models."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.loaded_models: Dict[str, LoadedModel] = {}
        self.model_health: Dict[str, ModelHealth] = {}
        self._loading_locks: Dict[str, asyncio.Lock] = {}
    
    async def load_model(self, model_id: str, model_path: Optional[str] = None) -> bool:
        """Load a model into memory."""
        # Get or create loading lock for this model
        if model_id not in self._loading_locks:
            self._loading_locks[model_id] = asyncio.Lock()
        
        async with self._loading_locks[model_id]:
            # Check if already loaded
            if model_id in self.loaded_models:
                loaded_model = self.loaded_models[model_id]
                if loaded_model.pipeline is not None:
                    self.logger.info(f"Model {model_id} already loaded")
                    return True
            
            try:
                self.logger.info(f"Loading model: {model_id}")
                
                # Update status to loading
                self.model_health[model_id] = ModelHealth(
                    status=ModelStatus.LOADING,
                    last_check=datetime.utcnow()
                )
                
                # For now, create a mock loaded model since we don't have actual model loading
                # In a real implementation, this would load the actual model using transformers
                loaded_model = LoadedModel(
                    model_id=model_id,
                    model_path=model_path or f"./models/{model_id}",
                    pipeline=self._create_mock_pipeline(model_id),
                    load_time=datetime.utcnow()
                )
                
                self.loaded_models[model_id] = loaded_model
                
                # Update health status
                self.model_health[model_id] = ModelHealth(
                    status=ModelStatus.LOADED,
                    last_check=datetime.utcnow(),
                    response_time_ms=100.0  # Mock response time
                )
                
                self.logger.info(f"Successfully loaded model: {model_id}")
                return True
                
            except Exception as e:
                self.logger.error(f"Failed to load model {model_id}: {str(e)}")
                
                # Update health status to error
                self.model_health[model_id] = ModelHealth(
                    status=ModelStatus.ERROR,
                    last_check=datetime.utcnow(),
                    error_message=str(e)
                )
                
                return False
    
    def _create_mock_pipeline(self, model_id: str) -> Any:
        """Create a mock pipeline for testing purposes."""
        class MockPipeline:
            def __init__(self, model_id: str):
                self.model_id = model_id
            
            def __call__(self, inputs: str, **kwargs) -> list:
                # Mock response that looks like a real model output
                return [{
                    "generated_text": f"Mock response from {self.model_id} for input: {inputs[:50]}..."
                }]
        
        return MockPipeline(model_id)
    
    async def unload_model(self, model_id: str) -> bool:
        """Unload a model from memory."""
        if model_id not in self.loaded_models:
            self.logger.warning(f"Model {model_id} not loaded")
            return True
        
        try:
            self.logger.info(f"Unloading model: {model_id}")
            
            # Update status
            self.model_health[model_id] = ModelHealth(
                status=ModelStatus.UNLOADING,
                last_check=datetime.utcnow()
            )
            
            # Remove from loaded models
            del self.loaded_models[model_id]
            
            # Update health status
            self.model_health[model_id] = ModelHealth(
                status=ModelStatus.NOT_LOADED,
                last_check=datetime.utcnow()
            )
            
            self.logger.info(f"Successfully unloaded model: {model_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to unload model {model_id}: {str(e)}")
            
            # Update health status to error
            self.model_health[model_id] = ModelHealth(
                status=ModelStatus.ERROR,
                last_check=datetime.utcnow(),
                error_message=str(e)
            )
            
            return False
    
    def get_loaded_model(self, model_id: str) -> Optional[LoadedModel]:
        """Get a loaded model."""
        return self.loaded_models.get(model_id)
    
    def get_model_health(self, model_id: str) -> Optional[ModelHealth]:
        """Get model health information."""
        return self.model_health.get(model_id)
    
    def list_loaded_models(self) -> Dict[str, LoadedModel]:
        """List all loaded models."""
        return self.loaded_models.copy()
    
    def get_memory_usage(self) -> Dict[str, float]:
        """Get memory usage for all loaded models."""
        # Mock implementation - in real scenario would calculate actual memory usage
        return {
            model_id: 1024.0  # Mock 1GB per model
            for model_id in self.loaded_models.keys()
        }
    
    async def health_check(self, model_id: str) -> bool:
        """Perform health check on a model."""
        if model_id not in self.loaded_models:
            return False
        
        try:
            loaded_model = self.loaded_models[model_id]
            if loaded_model.pipeline is None:
                return False
            
            # Test the model with a simple input
            start_time = datetime.utcnow()
            result = loaded_model.pipeline("Health check test")
            end_time = datetime.utcnow()
            
            response_time = (end_time - start_time).total_seconds() * 1000
            
            # Update health status
            self.model_health[model_id] = ModelHealth(
                status=ModelStatus.LOADED,
                last_check=datetime.utcnow(),
                response_time_ms=response_time
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Health check failed for model {model_id}: {str(e)}")
            
            # Update health status to error
            self.model_health[model_id] = ModelHealth(
                status=ModelStatus.ERROR,
                last_check=datetime.utcnow(),
                error_message=str(e)
            )
            
            return False
    
    async def cleanup_unused_models(self, max_idle_minutes: int = 30):
        """Cleanup models that haven't been used recently."""
        current_time = datetime.utcnow()
        models_to_unload = []
        
        for model_id, loaded_model in self.loaded_models.items():
            if loaded_model.last_used:
                idle_time = current_time - loaded_model.last_used
                if idle_time.total_seconds() > (max_idle_minutes * 60):
                    models_to_unload.append(model_id)
        
        for model_id in models_to_unload:
            await self.unload_model(model_id)
            self.logger.info(f"Unloaded idle model: {model_id}")


# Global model manager instance
model_manager = LLMModelManager()
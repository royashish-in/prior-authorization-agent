"""
Hugging Face Client

Handles communication with Hugging Face models via API and local inference.
Provides enhanced medical decision-making capabilities with automatic failover.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from datetime import datetime
import httpx
import json
import time
import random
from contextlib import asynccontextmanager

from .llm_config import ModelConfig, DeploymentType, ModelType, llm_config
from .llm_model_manager import model_manager, LoadedModel, ModelStatus
from .circuit_breaker import circuit_breaker_manager, CircuitBreakerConfig, CircuitBreakerOpenError
from ..core.secrets import llm_secrets_manager


@dataclass
class HuggingFaceRequest:
    """Request to Hugging Face model."""
    inputs: str
    parameters: Optional[Dict[str, Any]] = None
    options: Optional[Dict[str, Any]] = None


@dataclass
class HuggingFaceResponse:
    """Response from Hugging Face model."""
    model_id: str
    response_data: Any
    processing_time_ms: float
    success: bool
    error_message: Optional[str] = None
    confidence_score: Optional[float] = None
    fallback_used: bool = False
    retry_count: int = 0
    model_type: Optional[ModelType] = None


class HuggingFaceClient:
    """Client for interacting with Hugging Face models with circuit breaker and retry logic."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._http_client: Optional[httpx.AsyncClient] = None
        self._api_token: Optional[str] = None
        self._circuit_breakers: Dict[str, Any] = {}
        
    async def initialize(self):
        """Initialize the Hugging Face client."""
        self.logger.info("Initializing Hugging Face client")
        
        # Get API token
        self._api_token = llm_secrets_manager.get_huggingface_token()
        
        # Initialize HTTP client
        timeout = httpx.Timeout(llm_config.settings.default_timeout)
        limits = httpx.Limits(
            max_connections=llm_config.settings.max_concurrent_requests,
            max_keepalive_connections=10
        )
        
        self._http_client = httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            headers=self._get_default_headers()
        )
        
        # Initialize circuit breakers for each model
        self._initialize_circuit_breakers()
        
        self.logger.info("Hugging Face client initialized")
    
    async def shutdown(self):
        """Shutdown the client and cleanup resources."""
        if self._http_client:
            await self._http_client.aclose()
        self.logger.info("Hugging Face client shutdown")
    
    def _get_default_headers(self) -> Dict[str, str]:
        """Get default headers for API requests."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "PriorAuthAgent/1.0"
        }
        
        if self._api_token:
            headers["Authorization"] = f"Bearer {self._api_token}"
        
        return headers
    
    def _initialize_circuit_breakers(self):
        """Initialize circuit breakers for all configured models."""
        for model_config in llm_config.get_enabled_models():
            circuit_config = CircuitBreakerConfig(
                failure_threshold=5,
                recovery_timeout=60,
                success_threshold=3,
                timeout_seconds=model_config.timeout_seconds
            )
            
            circuit_breaker = circuit_breaker_manager.get_circuit_breaker(
                f"hf_model_{model_config.model_id}",
                circuit_config
            )
            self._circuit_breakers[model_config.model_id] = circuit_breaker
    
    def _get_circuit_breaker(self, model_id: str):
        """Get or create circuit breaker for a model."""
        if model_id not in self._circuit_breakers:
            config = llm_config.get_model_config(model_id)
            if config:
                circuit_config = CircuitBreakerConfig(
                    failure_threshold=5,
                    recovery_timeout=60,
                    success_threshold=3,
                    timeout_seconds=config.timeout_seconds
                )
                
                circuit_breaker = circuit_breaker_manager.get_circuit_breaker(
                    f"hf_model_{model_id}",
                    circuit_config
                )
                self._circuit_breakers[model_id] = circuit_breaker
        
        return self._circuit_breakers.get(model_id)
    
    async def query_model(
        self,
        model_id: str,
        request: HuggingFaceRequest,
        timeout: Optional[int] = None
    ) -> HuggingFaceResponse:
        """Query a Hugging Face model with circuit breaker and retry logic."""
        config = llm_config.get_model_config(model_id)
        if not config:
            return HuggingFaceResponse(
                model_id=model_id,
                response_data=None,
                processing_time_ms=0,
                success=False,
                error_message="Model configuration not found"
            )
        
        circuit_breaker = self._get_circuit_breaker(model_id)
        start_time = datetime.now()
        
        # Try with circuit breaker and retry logic
        for attempt in range(config.max_retries + 1):
            try:
                if circuit_breaker:
                    # Use circuit breaker for the call
                    async def make_call():
                        if config.deployment_type == DeploymentType.LOCAL_MODEL:
                            return await self._query_local_model(config, request)
                        else:
                            return await self._query_api_model(config, request, timeout)
                    
                    response = await circuit_breaker.call(make_call)
                else:
                    # Fallback without circuit breaker
                    if config.deployment_type == DeploymentType.LOCAL_MODEL:
                        response = await self._query_local_model(config, request)
                    else:
                        response = await self._query_api_model(config, request, timeout)
                
                processing_time = (datetime.now() - start_time).total_seconds() * 1000
                response.processing_time_ms = processing_time
                response.retry_count = attempt
                
                return response
                
            except CircuitBreakerOpenError as e:
                # Circuit breaker is open, try failover
                self.logger.warning(f"Circuit breaker open for {model_id}: {str(e)}")
                return await self._try_failover_models(model_id, request, timeout, start_time, attempt)
                
            except Exception as e:
                self.logger.warning(f"Attempt {attempt + 1} failed for model {model_id}: {str(e)}")
                
                # If this is the last attempt, return error
                if attempt == config.max_retries:
                    processing_time = (datetime.now() - start_time).total_seconds() * 1000
                    
                    # Try failover models before giving up
                    failover_response = await self._try_failover_models(
                        model_id, request, timeout, start_time, attempt
                    )
                    if failover_response.success:
                        return failover_response
                    
                    return HuggingFaceResponse(
                        model_id=model_id,
                        response_data=None,
                        processing_time_ms=processing_time,
                        success=False,
                        error_message=str(e),
                        retry_count=attempt
                    )
                
                # Exponential backoff with jitter
                delay = min(2 ** attempt + random.uniform(0, 1), 30)
                await asyncio.sleep(delay)
        
        # This should never be reached, but just in case
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        return HuggingFaceResponse(
            model_id=model_id,
            response_data=None,
            processing_time_ms=processing_time,
            success=False,
            error_message="Max retries exceeded",
            retry_count=config.max_retries
        )
    
    async def _query_api_model(
        self,
        config: ModelConfig,
        request: HuggingFaceRequest,
        timeout: Optional[int] = None
    ) -> HuggingFaceResponse:
        """Query a model via Hugging Face API."""
        if not self._http_client:
            raise RuntimeError("HTTP client not initialized")
        
        url = f"{llm_config.settings.huggingface_api_url}/{config.model_id}"
        
        # Prepare request payload
        payload = {
            "inputs": request.inputs
        }
        
        if request.parameters:
            payload["parameters"] = request.parameters
        
        if request.options:
            payload["options"] = request.options
        else:
            # Default options
            payload["options"] = {
                "wait_for_model": True,
                "use_cache": llm_config.settings.enable_response_cache
            }
        
        # Use model-specific timeout or default
        request_timeout = timeout or config.timeout_seconds
        
        try:
            response = await self._http_client.post(
                url,
                json=payload,
                timeout=request_timeout
            )
            
            if response.status_code == 200:
                response_data = response.json()
                return HuggingFaceResponse(
                    model_id=config.model_id,
                    response_data=response_data,
                    processing_time_ms=0,  # Will be set by caller
                    success=True
                )
            elif response.status_code == 503:
                return HuggingFaceResponse(
                    model_id=config.model_id,
                    response_data=None,
                    processing_time_ms=0,
                    success=False,
                    error_message="Model is currently loading, please retry"
                )
            else:
                error_text = response.text
                return HuggingFaceResponse(
                    model_id=config.model_id,
                    response_data=None,
                    processing_time_ms=0,
                    success=False,
                    error_message=f"API error {response.status_code}: {error_text}"
                )
                
        except httpx.TimeoutException:
            return HuggingFaceResponse(
                model_id=config.model_id,
                response_data=None,
                processing_time_ms=0,
                success=False,
                error_message=f"Request timeout after {request_timeout}s"
            )
    
    async def _query_local_model(
        self,
        config: ModelConfig,
        request: HuggingFaceRequest
    ) -> HuggingFaceResponse:
        """Query a locally loaded model."""
        # Ensure model is loaded
        if not await model_manager.load_model(config.model_id):
            return HuggingFaceResponse(
                model_id=config.model_id,
                response_data=None,
                processing_time_ms=0,
                success=False,
                error_message="Failed to load local model"
            )
        
        loaded_model = model_manager.get_loaded_model(config.model_id)
        if not loaded_model or not loaded_model.pipeline:
            return HuggingFaceResponse(
                model_id=config.model_id,
                response_data=None,
                processing_time_ms=0,
                success=False,
                error_message="Local model not available"
            )
        
        try:
            # Run inference using the pipeline
            result = loaded_model.pipeline(
                request.inputs,
                max_length=config.max_tokens,
                temperature=config.temperature,
                top_p=config.top_p,
                do_sample=True if config.temperature > 0 else False
            )
            
            return HuggingFaceResponse(
                model_id=config.model_id,
                response_data=result,
                processing_time_ms=0,  # Will be set by caller
                success=True
            )
            
        except Exception as e:
            return HuggingFaceResponse(
                model_id=config.model_id,
                response_data=None,
                processing_time_ms=0,
                success=False,
                error_message=f"Local inference error: {str(e)}"
            )
    
    async def test_model_connection(self, model_id: str) -> bool:
        """Test connection to a specific model."""
        test_request = HuggingFaceRequest(
            inputs="This is a test input to verify model connectivity.",
            options={"wait_for_model": False}
        )
        
        response = await self.query_model(model_id, test_request, timeout=10)
        return response.success
    
    async def get_model_info(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a model from Hugging Face Hub."""
        if not self._http_client:
            return None
        
        try:
            url = f"https://huggingface.co/api/models/{model_id}"
            response = await self._http_client.get(url, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                self.logger.warning(f"Failed to get model info for {model_id}: {response.status_code}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting model info for {model_id}: {str(e)}")
            return None
    
    async def batch_query(
        self,
        model_id: str,
        requests: List[HuggingFaceRequest],
        max_concurrent: int = 5
    ) -> List[HuggingFaceResponse]:
        """Query a model with multiple requests concurrently."""
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def query_with_semaphore(request: HuggingFaceRequest) -> HuggingFaceResponse:
            async with semaphore:
                return await self.query_model(model_id, request)
        
        tasks = [query_with_semaphore(request) for request in requests]
        return await asyncio.gather(*tasks)
    
    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get status of all circuit breakers."""
        status = {}
        for model_id, circuit_breaker in self._circuit_breakers.items():
            stats = circuit_breaker.get_stats()
            status[model_id] = {
                "state": stats.state.value,
                "failure_count": stats.failure_count,
                "success_count": stats.success_count,
                "total_calls": stats.total_calls,
                "total_failures": stats.total_failures,
                "total_successes": stats.total_successes,
                "last_failure_time": stats.last_failure_time.isoformat() if stats.last_failure_time else None,
                "last_success_time": stats.last_success_time.isoformat() if stats.last_success_time else None,
                "is_available": circuit_breaker.is_available()
            }
        return status
    
    async def get_comprehensive_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status including circuit breakers and model health."""
        health_status = {
            "models": {},
            "circuit_breakers": self.get_circuit_breaker_status(),
            "overall_health": "healthy"
        }
        
        unhealthy_count = 0
        total_models = 0
        
        for model_config in llm_config.get_enabled_models():
            model_id = model_config.model_id
            total_models += 1
            
            # Get model health from model manager
            model_health = model_manager.get_model_health(model_id)
            
            # Get circuit breaker status
            circuit_breaker = self._get_circuit_breaker(model_id)
            circuit_available = circuit_breaker.is_available() if circuit_breaker else True
            
            model_status = {
                "model_type": model_config.model_type.value,
                "deployment_type": model_config.deployment_type.value,
                "priority": model_config.priority,
                "enabled": model_config.enabled,
                "circuit_breaker_available": circuit_available,
                "health_status": model_health.status.value if model_health else "unknown",
                "last_health_check": model_health.last_check.isoformat() if model_health else None,
                "response_time_ms": model_health.response_time_ms if model_health else None,
                "error_message": model_health.error_message if model_health else None
            }
            
            if not circuit_available or (model_health and model_health.status.value != "healthy"):
                unhealthy_count += 1
                model_status["overall_status"] = "unhealthy"
            else:
                model_status["overall_status"] = "healthy"
            
            health_status["models"][model_id] = model_status
        
        # Determine overall health
        if unhealthy_count == 0:
            health_status["overall_health"] = "healthy"
        elif unhealthy_count < total_models:
            health_status["overall_health"] = "degraded"
        else:
            health_status["overall_health"] = "unhealthy"
        
        health_status["summary"] = {
            "total_models": total_models,
            "healthy_models": total_models - unhealthy_count,
            "unhealthy_models": unhealthy_count
        }
        
        return health_status
    
    async def _try_failover_models(
        self,
        original_model_id: str,
        request: HuggingFaceRequest,
        timeout: Optional[int],
        start_time: datetime,
        retry_count: int
    ) -> HuggingFaceResponse:
        """Try failover models when primary model fails."""
        original_config = llm_config.get_model_config(original_model_id)
        if not original_config:
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            return HuggingFaceResponse(
                model_id=original_model_id,
                response_data=None,
                processing_time_ms=processing_time,
                success=False,
                error_message="No failover available - original model config not found",
                retry_count=retry_count
            )
        
        # Get models of the same type with higher priority numbers (lower priority)
        same_type_models = llm_config.get_models_by_type(original_config.model_type)
        failover_models = [
            model for model in same_type_models
            if model.model_id != original_model_id and model.priority > original_config.priority
        ]
        
        # Also try fallback models
        fallback_models = llm_config.get_fallback_models()
        all_failover_models = failover_models + fallback_models
        
        self.logger.info(f"Trying {len(all_failover_models)} failover models for {original_model_id}")
        
        for failover_model in all_failover_models:
            try:
                self.logger.info(f"Attempting failover to {failover_model.model_id}")
                
                # Try the failover model (without retries to avoid infinite loops)
                if failover_model.deployment_type == DeploymentType.LOCAL_MODEL:
                    response = await self._query_local_model(failover_model, request)
                else:
                    response = await self._query_api_model(failover_model, request, timeout)
                
                if response.success:
                    processing_time = (datetime.now() - start_time).total_seconds() * 1000
                    response.processing_time_ms = processing_time
                    response.fallback_used = True
                    response.retry_count = retry_count
                    response.model_id = failover_model.model_id  # Update to show which model was used
                    
                    self.logger.info(f"Successful failover from {original_model_id} to {failover_model.model_id}")
                    return response
                    
            except Exception as e:
                self.logger.warning(f"Failover model {failover_model.model_id} also failed: {str(e)}")
                continue
        
        # All failover attempts failed
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        return HuggingFaceResponse(
            model_id=original_model_id,
            response_data=None,
            processing_time_ms=processing_time,
            success=False,
            error_message="All failover models failed",
            retry_count=retry_count,
            fallback_used=True
        )



    
    async def _query_api_model(
        self,
        config: ModelConfig,
        request: HuggingFaceRequest,
        timeout: Optional[int] = None
    ) -> HuggingFaceResponse:
        """Query model via Hugging Face API."""
        if not self._http_client:
            raise RuntimeError("HTTP client not initialized")
        
        api_url = f"https://api-inference.huggingface.co/models/{config.model_id}"
        
        # Prepare request payload
        payload = {
            "inputs": request.inputs,
            "parameters": request.parameters or {},
            "options": request.options or {}
        }
        
        # Set timeout
        request_timeout = timeout or config.timeout_seconds
        
        try:
            response = await self._http_client.post(
                api_url,
                json=payload,
                timeout=request_timeout
            )
            
            if response.status_code == 200:
                response_data = response.json()
                
                return HuggingFaceResponse(
                    model_id=config.model_id,
                    response_data=response_data,
                    processing_time_ms=0,  # Will be set by caller
                    success=True,
                    model_type=config.model_type
                )
            else:
                error_message = f"API request failed with status {response.status_code}: {response.text}"
                return HuggingFaceResponse(
                    model_id=config.model_id,
                    response_data=None,
                    processing_time_ms=0,
                    success=False,
                    error_message=error_message
                )
                
        except httpx.TimeoutException:
            return HuggingFaceResponse(
                model_id=config.model_id,
                response_data=None,
                processing_time_ms=0,
                success=False,
                error_message=f"Request timeout after {request_timeout} seconds"
            )
        except Exception as e:
            return HuggingFaceResponse(
                model_id=config.model_id,
                response_data=None,
                processing_time_ms=0,
                success=False,
                error_message=f"API request failed: {str(e)}"
            )
    
    async def _query_local_model(
        self,
        config: ModelConfig,
        request: HuggingFaceRequest
    ) -> HuggingFaceResponse:
        """Query local model via model manager."""
        try:
            # Load model if not already loaded
            if not await model_manager.load_model(config.model_id, config.model_id):
                return HuggingFaceResponse(
                    model_id=config.model_id,
                    response_data=None,
                    processing_time_ms=0,
                    success=False,
                    error_message="Failed to load local model"
                )
            
            # Get loaded model
            loaded_model = model_manager.get_loaded_model(config.model_id)
            if not loaded_model or not loaded_model.pipeline:
                return HuggingFaceResponse(
                    model_id=config.model_id,
                    response_data=None,
                    processing_time_ms=0,
                    success=False,
                    error_message="Local model not available"
                )
            
            # Query the model
            start_time = datetime.now()
            
            # Prepare parameters
            generation_params = {
                "max_new_tokens": request.parameters.get("max_new_tokens", config.max_tokens),
                "temperature": request.parameters.get("temperature", config.temperature),
                "top_p": request.parameters.get("top_p", config.top_p),
                "do_sample": True if config.temperature > 0 else False
            }
            
            # Generate response
            response_data = loaded_model.pipeline(request.inputs, **generation_params)
            
            # Update last used time
            loaded_model.last_used = datetime.utcnow()
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return HuggingFaceResponse(
                model_id=config.model_id,
                response_data=response_data,
                processing_time_ms=processing_time,
                success=True,
                model_type=config.model_type
            )
            
        except Exception as e:
            return HuggingFaceResponse(
                model_id=config.model_id,
                response_data=None,
                processing_time_ms=0,
                success=False,
                error_message=f"Local model query failed: {str(e)}"
            )
    
    async def _try_failover_models(
        self,
        original_model_id: str,
        request: HuggingFaceRequest,
        timeout: Optional[int],
        start_time: datetime,
        attempt_count: int
    ) -> HuggingFaceResponse:
        """Try failover models when primary model fails."""
        failover_models = llm_config.get_failover_models(original_model_id)
        
        for failover_model in failover_models:
            try:
                self.logger.info(f"Trying failover model {failover_model.model_id} for {original_model_id}")
                
                if failover_model.deployment_type == DeploymentType.LOCAL_MODEL:
                    response = await self._query_local_model(failover_model, request)
                else:
                    response = await self._query_api_model(failover_model, request, timeout)
                
                if response.success:
                    processing_time = (datetime.now() - start_time).total_seconds() * 1000
                    response.processing_time_ms = processing_time
                    response.retry_count = attempt_count
                    response.fallback_used = True
                    
                    self.logger.info(f"Failover successful with model {failover_model.model_id}")
                    return response
                    
            except Exception as e:
                self.logger.warning(f"Failover model {failover_model.model_id} also failed: {str(e)}")
                continue
        
        # All failover models failed
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        return HuggingFaceResponse(
            model_id=original_model_id,
            response_data=None,
            processing_time_ms=processing_time,
            success=False,
            error_message="All models including failovers failed",
            retry_count=attempt_count,
            fallback_used=True
        )
    
    async def query_multiple_models(
        self,
        model_ids: List[str],
        request: HuggingFaceRequest,
        timeout: Optional[int] = None
    ) -> List[HuggingFaceResponse]:
        """Query multiple models in parallel."""
        tasks = [
            self.query_model(model_id, request, timeout)
            for model_id in model_ids
        ]
        
        return await asyncio.gather(*tasks)
    
    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get status of all circuit breakers."""
        status = {}
        for model_id, circuit_breaker in self._circuit_breakers.items():
            stats = circuit_breaker.get_stats()
            status[model_id] = {
                "state": stats.state.value,
                "failure_count": stats.failure_count,
                "success_count": stats.success_count,
                "total_calls": stats.total_calls,
                "total_failures": stats.total_failures,
                "total_successes": stats.total_successes,
                "last_failure_time": stats.last_failure_time.isoformat() if stats.last_failure_time else None,
                "last_success_time": stats.last_success_time.isoformat() if stats.last_success_time else None,
                "is_available": circuit_breaker.is_available()
            }
        return status
    
    async def get_comprehensive_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status of all models."""
        health_status = {
            "models": {},
            "circuit_breakers": self.get_circuit_breaker_status(),
            "overall_health": "healthy"
        }
        
        enabled_models = llm_config.get_enabled_models()
        unhealthy_models = 0
        
        for model_config in enabled_models:
            model_id = model_config.model_id
            
            # Get model health from model manager
            model_health = model_manager.get_model_health(model_id)
            
            # Get circuit breaker status
            circuit_breaker = self._get_circuit_breaker(model_id)
            circuit_available = circuit_breaker.is_available() if circuit_breaker else True
            
            model_status = {
                "model_id": model_id,
                "deployment_type": model_config.deployment_type.value,
                "priority": model_config.priority,
                "enabled": model_config.enabled,
                "circuit_breaker_available": circuit_available,
                "model_loaded": model_health is not None,
                "health_status": model_health.status.value if model_health else "unknown",
                "last_health_check": model_health.last_check.isoformat() if model_health else None,
                "response_time_ms": model_health.response_time_ms if model_health else None,
                "error_message": model_health.error_message if model_health else None
            }
            
            # Determine if model is healthy
            is_healthy = (
                model_config.enabled and
                circuit_available and
                (not model_health or model_health.status in [ModelStatus.LOADED, ModelStatus.NOT_LOADED])
            )
            
            if not is_healthy:
                unhealthy_models += 1
            
            model_status["is_healthy"] = is_healthy
            health_status["models"][model_id] = model_status
        
        # Determine overall health
        if unhealthy_models == 0:
            health_status["overall_health"] = "healthy"
        elif unhealthy_models < len(enabled_models) / 2:
            health_status["overall_health"] = "degraded"
        else:
            health_status["overall_health"] = "unhealthy"
        
        health_status["total_models"] = len(enabled_models)
        health_status["healthy_models"] = len(enabled_models) - unhealthy_models
        health_status["unhealthy_models"] = unhealthy_models
        
        return health_status
    
    async def health_check(self, model_id: Optional[str] = None) -> bool:
        """Perform health check on specific model or all models."""
        if model_id:
            # Check specific model
            config = llm_config.get_model_config(model_id)
            if not config:
                return False
            
            try:
                test_request = HuggingFaceRequest(
                    inputs="Health check test",
                    parameters={"max_new_tokens": 10}
                )
                
                response = await self.query_model(model_id, test_request, timeout=10)
                return response.success
                
            except Exception:
                return False
        else:
            # Check all models
            health_status = await self.get_comprehensive_health_status()
            return health_status["overall_health"] in ["healthy", "degraded"]


# Global Hugging Face client instance
huggingface_client = HuggingFaceClient()
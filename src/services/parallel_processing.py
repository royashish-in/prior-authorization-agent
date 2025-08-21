"""
Parallel Processing Service for Authorization Requests

This service provides parallel processing capabilities for multiple authorization
requests to improve throughput and reduce overall processing time.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import uuid
from concurrent.futures import ThreadPoolExecutor
import time

from ..models.authorization import AuthorizationRequest, AuthorizationDecision
from ..models.enums import DecisionStatus, UrgencyLevel
from .llm_decision_service import llm_decision_service, LLMDecisionResponse
from .decision_cache import decision_cache_service
from .semantic_similarity import semantic_similarity_service, SimilarityMatch

logger = logging.getLogger(__name__)


class ProcessingPriority(str, Enum):
    """Processing priority levels."""
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class ProcessingStatus(str, Enum):
    """Processing status for batch requests."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ProcessingRequest:
    """Container for a processing request."""
    request_id: str
    authorization_request: AuthorizationRequest
    priority: ProcessingPriority
    submitted_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: ProcessingStatus = ProcessingStatus.QUEUED
    result: Optional[Any] = None
    error: Optional[str] = None
    processing_time_ms: float = 0.0
    cache_hit: bool = False
    similarity_used: bool = False


@dataclass
class BatchProcessingResult:
    """Result of batch processing operation."""
    batch_id: str
    total_requests: int
    completed_requests: int
    failed_requests: int
    processing_time_ms: float
    results: List[ProcessingRequest] = field(default_factory=list)
    cache_hits: int = 0
    similarity_hits: int = 0


@dataclass
class ProcessingStats:
    """Processing statistics."""
    total_processed: int = 0
    successful_processed: int = 0
    failed_processed: int = 0
    cache_hit_rate: float = 0.0
    similarity_hit_rate: float = 0.0
    average_processing_time_ms: float = 0.0
    concurrent_requests_peak: int = 0
    queue_size_peak: int = 0


class ParallelProcessingService:
    """
    Service for parallel processing of authorization requests.
    
    Provides batch processing, priority queuing, and intelligent caching
    to optimize throughput and response times.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Processing configuration
        self.max_concurrent_requests = 10
        self.max_queue_size = 1000
        self.batch_timeout_seconds = 30
        self.similarity_threshold = 0.85
        
        # Processing queues by priority
        self._queues: Dict[ProcessingPriority, asyncio.Queue] = {
            ProcessingPriority.URGENT: asyncio.Queue(maxsize=100),
            ProcessingPriority.HIGH: asyncio.Queue(maxsize=200),
            ProcessingPriority.NORMAL: asyncio.Queue(maxsize=500),
            ProcessingPriority.LOW: asyncio.Queue(maxsize=200)
        }
        
        # Active processing tracking
        self._active_requests: Dict[str, ProcessingRequest] = {}
        self._processing_semaphore = asyncio.Semaphore(self.max_concurrent_requests)
        self._worker_tasks: List[asyncio.Task] = []
        self._shutdown_event = asyncio.Event()
        
        # Statistics tracking
        self._stats = ProcessingStats()
        self._batch_results: Dict[str, BatchProcessingResult] = {}
        
        # Thread pool for CPU-intensive operations
        self._thread_pool = ThreadPoolExecutor(max_workers=4)
        
    async def initialize(self):
        """Initialize the parallel processing service."""
        self.logger.info("Initializing Parallel Processing Service")
        
        # Start worker tasks for each priority level
        for priority in ProcessingPriority:
            worker_task = asyncio.create_task(
                self._priority_worker(priority),
                name=f"worker_{priority.value}"
            )
            self._worker_tasks.append(worker_task)
        
        # Start statistics update task
        stats_task = asyncio.create_task(
            self._update_stats_loop(),
            name="stats_updater"
        )
        self._worker_tasks.append(stats_task)
        
        self.logger.info("Parallel Processing Service initialized")
    
    async def shutdown(self):
        """Shutdown the parallel processing service."""
        self.logger.info("Shutting down Parallel Processing Service")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Cancel all worker tasks
        for task in self._worker_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        
        # Shutdown thread pool
        self._thread_pool.shutdown(wait=True)
        
        self.logger.info("Parallel Processing Service shutdown complete")
    
    async def process_single_request(
        self,
        request: AuthorizationRequest,
        priority: ProcessingPriority = ProcessingPriority.NORMAL,
        use_cache: bool = True,
        use_similarity: bool = True
    ) -> ProcessingRequest:
        """
        Process a single authorization request with caching and similarity matching.
        
        Args:
            request: Authorization request to process
            priority: Processing priority
            use_cache: Whether to use cached results
            use_similarity: Whether to use similarity matching
            
        Returns:
            Processing request with result
        """
        request_id = str(uuid.uuid4())
        processing_request = ProcessingRequest(
            request_id=request_id,
            authorization_request=request,
            priority=priority,
            submitted_at=datetime.now(timezone.utc)
        )
        
        try:
            # Check cache first if enabled
            if use_cache:
                cached_result = await self._check_cache(request)
                if cached_result:
                    processing_request.result = cached_result
                    processing_request.status = ProcessingStatus.COMPLETED
                    processing_request.cache_hit = True
                    processing_request.completed_at = datetime.now(timezone.utc)
                    processing_request.processing_time_ms = 0.0
                    return processing_request
            
            # Check similarity matching if enabled
            if use_similarity:
                similar_result = await self._check_similarity(request)
                if similar_result:
                    processing_request.result = similar_result
                    processing_request.status = ProcessingStatus.COMPLETED
                    processing_request.similarity_used = True
                    processing_request.completed_at = datetime.now(timezone.utc)
                    processing_request.processing_time_ms = 5.0  # Minimal processing time
                    return processing_request
            
            # Process with LLM
            start_time = datetime.now(timezone.utc)
            processing_request.started_at = start_time
            processing_request.status = ProcessingStatus.PROCESSING
            
            # Add to active requests tracking
            self._active_requests[request_id] = processing_request
            
            try:
                # Use semaphore to limit concurrent processing
                async with self._processing_semaphore:
                    # Process the request
                    result = await self._process_with_llm(request)
                    
                    processing_request.result = result
                    processing_request.status = ProcessingStatus.COMPLETED
                    processing_request.completed_at = datetime.now(timezone.utc)
                    processing_request.processing_time_ms = (
                        processing_request.completed_at - start_time
                    ).total_seconds() * 1000
                    
                    # Cache the result for future use
                    if use_cache and result:
                        await self._cache_result(request, result)
                    
                    # Cache similarity vector
                    if use_similarity and result:
                        await semantic_similarity_service.cache_request_vector(request, result)
                    
            finally:
                # Remove from active requests
                self._active_requests.pop(request_id, None)
            
            return processing_request
            
        except Exception as e:
            self.logger.error(f"Error processing request {request_id}: {str(e)}")
            processing_request.status = ProcessingStatus.FAILED
            processing_request.error = str(e)
            processing_request.completed_at = datetime.now(timezone.utc)
            return processing_request
    
    async def process_batch_requests(
        self,
        requests: List[Tuple[AuthorizationRequest, ProcessingPriority]],
        batch_id: Optional[str] = None,
        max_concurrent: Optional[int] = None
    ) -> BatchProcessingResult:
        """
        Process multiple authorization requests in parallel.
        
        Args:
            requests: List of (request, priority) tuples
            batch_id: Optional batch identifier
            max_concurrent: Maximum concurrent requests (overrides default)
            
        Returns:
            Batch processing result
        """
        if not batch_id:
            batch_id = str(uuid.uuid4())
        
        if max_concurrent:
            # Create temporary semaphore for this batch
            batch_semaphore = asyncio.Semaphore(max_concurrent)
        else:
            batch_semaphore = self._processing_semaphore
        
        start_time = datetime.now(timezone.utc)
        
        self.logger.info(f"Starting batch processing: {batch_id} ({len(requests)} requests)")
        
        # Create processing tasks
        tasks = []
        for auth_request, priority in requests:
            task = asyncio.create_task(
                self._process_batch_item(auth_request, priority, batch_semaphore),
                name=f"batch_{batch_id}_{len(tasks)}"
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        completed_requests = []
        failed_requests = []
        cache_hits = 0
        similarity_hits = 0
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Create failed processing request
                failed_request = ProcessingRequest(
                    request_id=f"batch_{batch_id}_{i}",
                    authorization_request=requests[i][0],
                    priority=requests[i][1],
                    submitted_at=start_time,
                    status=ProcessingStatus.FAILED,
                    error=str(result),
                    completed_at=datetime.now(timezone.utc)
                )
                failed_requests.append(failed_request)
            else:
                completed_requests.append(result)
                if result.cache_hit:
                    cache_hits += 1
                if result.similarity_used:
                    similarity_hits += 1
        
        end_time = datetime.now(timezone.utc)
        processing_time = (end_time - start_time).total_seconds() * 1000
        
        batch_result = BatchProcessingResult(
            batch_id=batch_id,
            total_requests=len(requests),
            completed_requests=len(completed_requests),
            failed_requests=len(failed_requests),
            processing_time_ms=processing_time,
            results=completed_requests + failed_requests,
            cache_hits=cache_hits,
            similarity_hits=similarity_hits
        )
        
        # Store batch result
        self._batch_results[batch_id] = batch_result
        
        self.logger.info(
            f"Batch processing completed: {batch_id} "
            f"({batch_result.completed_requests}/{batch_result.total_requests} successful, "
            f"{processing_time:.2f}ms total)"
        )
        
        return batch_result
    
    async def queue_request(
        self,
        request: AuthorizationRequest,
        priority: ProcessingPriority = ProcessingPriority.NORMAL
    ) -> str:
        """
        Queue a request for asynchronous processing.
        
        Args:
            request: Authorization request to queue
            priority: Processing priority
            
        Returns:
            Request ID for tracking
        """
        request_id = str(uuid.uuid4())
        processing_request = ProcessingRequest(
            request_id=request_id,
            authorization_request=request,
            priority=priority,
            submitted_at=datetime.now(timezone.utc)
        )
        
        try:
            # Add to appropriate priority queue
            await self._queues[priority].put(processing_request)
            self.logger.debug(f"Request queued: {request_id} (priority: {priority.value})")
            return request_id
            
        except asyncio.QueueFull:
            self.logger.error(f"Queue full for priority {priority.value}")
            raise Exception(f"Processing queue full for priority {priority.value}")
    
    async def get_request_status(self, request_id: str) -> Optional[ProcessingRequest]:
        """Get the status of a queued or processing request."""
        # Check active requests first
        if request_id in self._active_requests:
            return self._active_requests[request_id]
        
        # Check completed batch results
        for batch_result in self._batch_results.values():
            for result in batch_result.results:
                if result.request_id == request_id:
                    return result
        
        return None
    
    async def get_processing_stats(self) -> ProcessingStats:
        """Get current processing statistics."""
        # Update current queue sizes
        current_queue_size = sum(queue.qsize() for queue in self._queues.values())
        if current_queue_size > self._stats.queue_size_peak:
            self._stats.queue_size_peak = current_queue_size
        
        # Update concurrent requests peak
        current_concurrent = len(self._active_requests)
        if current_concurrent > self._stats.concurrent_requests_peak:
            self._stats.concurrent_requests_peak = current_concurrent
        
        return self._stats
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status."""
        return {
            'queue_sizes': {
                priority.value: queue.qsize() 
                for priority, queue in self._queues.items()
            },
            'active_requests': len(self._active_requests),
            'max_concurrent': self.max_concurrent_requests,
            'available_slots': self._processing_semaphore._value
        }
    
    async def _priority_worker(self, priority: ProcessingPriority):
        """Worker task for processing requests from a priority queue."""
        queue = self._queues[priority]
        
        while not self._shutdown_event.is_set():
            try:
                # Wait for request with timeout
                processing_request = await asyncio.wait_for(
                    queue.get(), timeout=1.0
                )
                
                # Process the request
                await self._process_queued_request(processing_request)
                
            except asyncio.TimeoutError:
                # No requests in queue, continue
                continue
            except Exception as e:
                self.logger.error(f"Error in {priority.value} worker: {str(e)}")
    
    async def _process_queued_request(self, processing_request: ProcessingRequest):
        """Process a queued request."""
        try:
            # Update status
            processing_request.started_at = datetime.now(timezone.utc)
            processing_request.status = ProcessingStatus.PROCESSING
            
            # Add to active requests
            self._active_requests[processing_request.request_id] = processing_request
            
            # Use semaphore to limit concurrent processing
            async with self._processing_semaphore:
                # Check cache first
                cached_result = await self._check_cache(processing_request.authorization_request)
                if cached_result:
                    processing_request.result = cached_result
                    processing_request.cache_hit = True
                    processing_request.processing_time_ms = 1.0
                else:
                    # Check similarity
                    similar_result = await self._check_similarity(processing_request.authorization_request)
                    if similar_result:
                        processing_request.result = similar_result
                        processing_request.similarity_used = True
                        processing_request.processing_time_ms = 5.0
                    else:
                        # Process with LLM
                        start_time = datetime.now(timezone.utc)
                        result = await self._process_with_llm(processing_request.authorization_request)
                        processing_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                        
                        processing_request.result = result
                        processing_request.processing_time_ms = processing_time
                        
                        # Cache results
                        if result:
                            await self._cache_result(processing_request.authorization_request, result)
                            await semantic_similarity_service.cache_request_vector(
                                processing_request.authorization_request, result
                            )
                
                processing_request.status = ProcessingStatus.COMPLETED
                processing_request.completed_at = datetime.now(timezone.utc)
                
        except Exception as e:
            self.logger.error(f"Error processing queued request {processing_request.request_id}: {str(e)}")
            processing_request.status = ProcessingStatus.FAILED
            processing_request.error = str(e)
            processing_request.completed_at = datetime.now(timezone.utc)
        
        finally:
            # Remove from active requests
            self._active_requests.pop(processing_request.request_id, None)
    
    async def _process_batch_item(
        self,
        request: AuthorizationRequest,
        priority: ProcessingPriority,
        semaphore: asyncio.Semaphore
    ) -> ProcessingRequest:
        """Process a single item in a batch."""
        async with semaphore:
            return await self.process_single_request(request, priority)
    
    async def _check_cache(self, request: AuthorizationRequest) -> Optional[Dict[str, Any]]:
        """Check if request result is cached."""
        try:
            # Create a simple hash of the request for cache lookup
            request_data = {
                'diagnosis_codes': [str(code) for code in getattr(request, 'diagnosis_codes', [])],
                'procedure_codes': [str(code) for code in getattr(request, 'procedure_codes', [])],
                'payer_id': getattr(request, 'payer_id', ''),
                'urgency_level': str(getattr(request, 'urgency_level', ''))
            }
            
            cached_result = await decision_cache_service.get_validation_result(
                decision_cache_service._hash_request_data(request_data)
            )
            
            return cached_result
            
        except Exception as e:
            self.logger.debug(f"Cache check failed: {str(e)}")
            return None
    
    async def _check_similarity(self, request: AuthorizationRequest) -> Optional[Dict[str, Any]]:
        """Check for similar requests using semantic similarity."""
        try:
            similar_matches = await semantic_similarity_service.find_similar_requests(
                request, min_similarity=self.similarity_threshold
            )
            
            if similar_matches:
                # Use the most similar match
                best_match = similar_matches[0]
                if best_match.cached_decision:
                    self.logger.debug(f"Using similar request result (similarity: {best_match.similarity_score:.3f})")
                    return best_match.cached_decision
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Similarity check failed: {str(e)}")
            return None
    
    async def _process_with_llm(self, request: AuthorizationRequest) -> Dict[str, Any]:
        """Process request using LLM decision service."""
        # This would integrate with the actual LLM decision service
        # For now, return a mock result structure
        return {
            'decision': 'APPROVE',
            'confidence_score': 0.85,
            'medical_reasoning': 'Mock LLM processing result',
            'processing_method': 'llm'
        }
    
    async def _cache_result(self, request: AuthorizationRequest, result: Dict[str, Any]):
        """Cache the processing result."""
        try:
            request_data = {
                'diagnosis_codes': [str(code) for code in getattr(request, 'diagnosis_codes', [])],
                'procedure_codes': [str(code) for code in getattr(request, 'procedure_codes', [])],
                'payer_id': getattr(request, 'payer_id', ''),
                'urgency_level': str(getattr(request, 'urgency_level', ''))
            }
            
            await decision_cache_service.cache_validation_result(result, request_data)
            
        except Exception as e:
            self.logger.debug(f"Result caching failed: {str(e)}")
    
    async def _update_stats_loop(self):
        """Background task to update processing statistics."""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(60)  # Update every minute
                
                # Calculate statistics from batch results
                total_processed = 0
                successful_processed = 0
                failed_processed = 0
                cache_hits = 0
                similarity_hits = 0
                total_processing_time = 0.0
                
                for batch_result in self._batch_results.values():
                    total_processed += batch_result.total_requests
                    successful_processed += batch_result.completed_requests
                    failed_processed += batch_result.failed_requests
                    cache_hits += batch_result.cache_hits
                    similarity_hits += batch_result.similarity_hits
                    
                    for result in batch_result.results:
                        if result.status == ProcessingStatus.COMPLETED:
                            total_processing_time += result.processing_time_ms
                
                # Update stats
                self._stats.total_processed = total_processed
                self._stats.successful_processed = successful_processed
                self._stats.failed_processed = failed_processed
                
                if total_processed > 0:
                    self._stats.cache_hit_rate = cache_hits / total_processed
                    self._stats.similarity_hit_rate = similarity_hits / total_processed
                
                if successful_processed > 0:
                    self._stats.average_processing_time_ms = total_processing_time / successful_processed
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error updating stats: {str(e)}")


# Global parallel processing service instance
parallel_processing_service = ParallelProcessingService()
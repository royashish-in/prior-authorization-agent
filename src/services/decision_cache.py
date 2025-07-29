"""
Decision caching service for the Prior Authorization Agent.

This module provides specialized caching for authorization decisions,
validation results, and decision reasoning with appropriate TTL management.
"""

import logging
import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import hashlib

from src.services.cache import cache_manager, CacheKey, CacheTTL

logger = logging.getLogger(__name__)


class DecisionStatus:
    """Decision status constants."""
    APPROVED = "approved"
    DENIED = "denied"
    PENDING = "pending"
    MORE_INFO_NEEDED = "more_info_needed"


class DecisionCacheService:
    """
    Specialized caching service for authorization decisions.
    
    Provides caching for decisions, validation results, and reasoning
    with status-appropriate TTL management.
    """
    
    def __init__(self):
        self.cache = cache_manager
    
    async def get_decision_by_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        """
        Get cached decision by request ID.
        
        Args:
            request_id: Authorization request identifier
            
        Returns:
            Decision data or None if not cached
        """
        key = CacheKey.generate_key(CacheKey.DECISION_BY_REQUEST, request_id=request_id)
        return await self.cache.get(key)
    
    async def get_decision_by_id(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """
        Get cached decision by decision ID.
        
        Args:
            decision_id: Decision identifier
            
        Returns:
            Decision data or None if not cached
        """
        key = CacheKey.generate_key(CacheKey.DECISION_BY_ID, decision_id=decision_id)
        return await self.cache.get(key)
    
    async def cache_decision(
        self,
        decision: Dict[str, Any],
        request_id: str,
        decision_id: str,
        status: str
    ) -> bool:
        """
        Cache authorization decision with status-appropriate TTL.
        
        Args:
            decision: Decision data to cache
            request_id: Authorization request identifier
            decision_id: Decision identifier
            status: Decision status (approved, denied, pending, etc.)
            
        Returns:
            True if cached successfully, False otherwise
        """
        # Determine TTL based on decision status
        ttl = self._get_decision_ttl(status)
        
        # Add metadata to decision
        enhanced_decision = {
            **decision,
            'request_id': request_id,
            'decision_id': decision_id,
            'status': status,
            'cached_at': datetime.now(timezone.utc).isoformat(),
            'ttl': ttl
        }
        
        # Cache by request ID
        request_key = CacheKey.generate_key(
            CacheKey.DECISION_BY_REQUEST, 
            request_id=request_id
        )
        request_cached = await self.cache.set(request_key, enhanced_decision, ttl=ttl)
        
        # Cache by decision ID
        decision_key = CacheKey.generate_key(
            CacheKey.DECISION_BY_ID, 
            decision_id=decision_id
        )
        decision_cached = await self.cache.set(decision_key, enhanced_decision, ttl=ttl)
        
        success = request_cached and decision_cached
        
        if success:
            logger.debug(f"Decision {decision_id} cached successfully (status: {status})")
        else:
            logger.warning(f"Failed to cache decision {decision_id}")
        
        return success
    
    async def get_validation_result(self, request_hash: str) -> Optional[Dict[str, Any]]:
        """
        Get cached validation result for a request.
        
        Args:
            request_hash: Hash of the request data
            
        Returns:
            Validation result or None if not cached
        """
        key = CacheKey.generate_key(CacheKey.VALIDATION_RESULT, request_hash=request_hash)
        return await self.cache.get(key)
    
    async def cache_validation_result(
        self,
        validation_result: Dict[str, Any],
        request_data: Dict[str, Any]
    ) -> bool:
        """
        Cache validation result for similar future requests.
        
        Args:
            validation_result: Validation result data
            request_data: Original request data for hashing
            
        Returns:
            True if cached successfully, False otherwise
        """
        # Create hash of request data for cache key
        request_hash = self._hash_request_data(request_data)
        
        key = CacheKey.generate_key(CacheKey.VALIDATION_RESULT, request_hash=request_hash)
        
        # Add metadata to validation result
        enhanced_result = {
            **validation_result,
            'request_hash': request_hash,
            'cached_at': datetime.now(timezone.utc).isoformat(),
            'ttl': CacheTTL.VALIDATION_RESULT
        }
        
        success = await self.cache.set(
            key, 
            enhanced_result, 
            ttl=CacheTTL.VALIDATION_RESULT
        )
        
        if success:
            logger.debug(f"Validation result cached for request hash {request_hash}")
        else:
            logger.warning(f"Failed to cache validation result for request hash {request_hash}")
        
        return success
    
    async def invalidate_decision(self, decision_id: str, request_id: str) -> bool:
        """
        Invalidate cached decision by both decision ID and request ID.
        
        Args:
            decision_id: Decision identifier
            request_id: Request identifier
            
        Returns:
            True if invalidation was successful
        """
        keys_to_delete = [
            CacheKey.generate_key(CacheKey.DECISION_BY_ID, decision_id=decision_id),
            CacheKey.generate_key(CacheKey.DECISION_BY_REQUEST, request_id=request_id)
        ]
        
        success = True
        for key in keys_to_delete:
            if not await self.cache.delete(key):
                success = False
        
        if success:
            logger.info(f"Decision {decision_id} invalidated from cache")
        else:
            logger.warning(f"Failed to fully invalidate decision {decision_id}")
        
        return success
    
    async def update_decision_status(
        self,
        decision_id: str,
        request_id: str,
        new_status: str,
        updated_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update cached decision status and optionally update data.
        
        Args:
            decision_id: Decision identifier
            request_id: Request identifier
            new_status: New decision status
            updated_data: Optional updated decision data
            
        Returns:
            True if update was successful
        """
        # Get current cached decision
        current_decision = await self.get_decision_by_id(decision_id)
        
        if not current_decision:
            logger.warning(f"Cannot update non-cached decision {decision_id}")
            return False
        
        # Update status and data
        updated_decision = {
            **current_decision,
            'status': new_status,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        
        if updated_data:
            updated_decision.update(updated_data)
        
        # Re-cache with new TTL based on status
        return await self.cache_decision(
            updated_decision,
            request_id,
            decision_id,
            new_status
        )
    
    async def get_decisions_by_status(self, status: str) -> List[Dict[str, Any]]:
        """
        Get all cached decisions with a specific status.
        
        Args:
            status: Decision status to filter by
            
        Returns:
            List of decisions with the specified status
        """
        decisions = []
        
        try:
            async with self.cache.get_client() as client:
                # Get all decision keys
                decision_keys = await asyncio.get_event_loop().run_in_executor(
                    None, client.keys, f"{CacheKey.DECISION_PREFIX}:*"
                )
                
                # Check each decision for matching status
                for key in decision_keys:
                    decision = await self.cache.get(key)
                    if decision and decision.get('status') == status:
                        decisions.append(decision)
        
        except Exception as e:
            logger.error(f"Failed to get decisions by status {status}: {e}")
        
        return decisions
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get decision cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        stats = {
            'total_decisions': 0,
            'approved_decisions': 0,
            'denied_decisions': 0,
            'pending_decisions': 0,
            'validation_results': 0,
            'expired_decisions': 0
        }
        
        try:
            async with self.cache.get_client() as client:
                # Get all decision-related keys
                decision_keys = await asyncio.get_event_loop().run_in_executor(
                    None, client.keys, f"{CacheKey.DECISION_PREFIX}:*"
                )
                
                validation_keys = await asyncio.get_event_loop().run_in_executor(
                    None, client.keys, f"{CacheKey.VALIDATION_PREFIX}:*"
                )
                
                stats['validation_results'] = len(validation_keys)
                
                for key in decision_keys:
                    decision = await self.cache.get(key)
                    if decision:
                        stats['total_decisions'] += 1
                        status = decision.get('status', '').lower()
                        
                        if status == DecisionStatus.APPROVED:
                            stats['approved_decisions'] += 1
                        elif status == DecisionStatus.DENIED:
                            stats['denied_decisions'] += 1
                        elif status in [DecisionStatus.PENDING, DecisionStatus.MORE_INFO_NEEDED]:
                            stats['pending_decisions'] += 1
                    else:
                        stats['expired_decisions'] += 1
        
        except Exception as e:
            logger.error(f"Failed to get decision cache stats: {e}")
        
        return stats
    
    def _get_decision_ttl(self, status: str) -> int:
        """
        Get appropriate TTL based on decision status.
        
        Args:
            status: Decision status
            
        Returns:
            TTL in seconds
        """
        status_lower = status.lower()
        
        if status_lower == DecisionStatus.APPROVED:
            return CacheTTL.DECISION_APPROVED
        elif status_lower == DecisionStatus.DENIED:
            return CacheTTL.DECISION_DENIED
        elif status_lower in [DecisionStatus.PENDING, DecisionStatus.MORE_INFO_NEEDED]:
            return CacheTTL.DECISION_PENDING
        else:
            return CacheTTL.DECISION_PENDING  # Default to pending TTL
    
    def _hash_request_data(self, request_data: Dict[str, Any]) -> str:
        """
        Create hash of request data for validation caching.
        
        Args:
            request_data: Request data to hash
            
        Returns:
            SHA-256 hash of the request data
        """
        # Extract relevant fields for hashing (exclude timestamps, IDs, etc.)
        hashable_fields = {
            'diagnosis_codes': request_data.get('diagnosis_codes', []),
            'procedure_codes': request_data.get('procedure_codes', []),
            'payer_id': request_data.get('payer_id', ''),
            'urgency_level': request_data.get('urgency_level', ''),
            # Note: We don't include PHI like patient demographics
        }
        
        # Sort to ensure consistent hashing
        sorted_data = json.dumps(hashable_fields, sort_keys=True)
        return hashlib.sha256(sorted_data.encode()).hexdigest()


# Global decision cache service instance
decision_cache_service = DecisionCacheService()
"""
Policy-specific caching service for the Prior Authorization Agent.

This module provides specialized caching operations for coverage policies,
including cache warming, invalidation strategies, and policy-specific TTL management.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import hashlib

from src.services.cache import cache_manager, CacheKey, CacheTTL

logger = logging.getLogger(__name__)


class PolicyCacheService:
    """
    Specialized caching service for coverage policies.
    
    Provides policy-specific caching operations with intelligent TTL management
    based on policy status and frequency of access.
    """
    
    def __init__(self):
        self.cache = cache_manager
    
    async def get_policy_by_id(self, policy_id: str) -> Optional[Dict[str, Any]]:
        """
        Get policy by ID from cache.
        
        Args:
            policy_id: Policy identifier
            
        Returns:
            Policy data or None if not cached
        """
        key = CacheKey.generate_key(CacheKey.POLICY_BY_ID, policy_id=policy_id)
        return await self.cache.get(key)
    
    async def cache_policy(
        self, 
        policy: Dict[str, Any], 
        policy_id: str,
        is_active: bool = True
    ) -> bool:
        """
        Cache policy with appropriate TTL based on status.
        
        Args:
            policy: Policy data to cache
            policy_id: Policy identifier
            is_active: Whether policy is currently active
            
        Returns:
            True if cached successfully, False otherwise
        """
        # Determine TTL based on policy status
        ttl = CacheTTL.POLICY_ACTIVE if is_active else CacheTTL.POLICY_EXPIRED
        
        # Cache by policy ID
        id_key = CacheKey.generate_key(CacheKey.POLICY_BY_ID, policy_id=policy_id)
        id_cached = await self.cache.set(id_key, policy, ttl=ttl)
        
        # Cache by payer if payer_id is available
        payer_cached = True
        if 'payer_id' in policy:
            payer_key = CacheKey.generate_key(
                CacheKey.POLICY_BY_PAYER, 
                payer_id=policy['payer_id']
            )
            payer_cached = await self.cache.set(payer_key, policy, ttl=ttl)
        
        # Cache by procedure code if available
        procedure_cached = True
        if 'procedure_code' in policy:
            procedure_key = CacheKey.generate_key(
                CacheKey.POLICY_BY_PROCEDURE, 
                procedure_code=policy['procedure_code']
            )
            procedure_cached = await self.cache.set(procedure_key, policy, ttl=ttl)
        
        success = id_cached and payer_cached and procedure_cached
        
        if success:
            logger.debug(f"Policy {policy_id} cached successfully (active: {is_active})")
        else:
            logger.warning(f"Failed to cache policy {policy_id}")
        
        return success
    
    async def get_policies_by_payer(self, payer_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get all policies for a payer from cache.
        
        Args:
            payer_id: Payer identifier
            
        Returns:
            List of policies or None if not cached
        """
        key = CacheKey.generate_key(CacheKey.POLICY_BY_PAYER, payer_id=payer_id)
        return await self.cache.get(key)
    
    async def get_policies_by_procedure(
        self, 
        procedure_code: str
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get all policies for a procedure code from cache.
        
        Args:
            procedure_code: CPT/HCPCS procedure code
            
        Returns:
            List of policies or None if not cached
        """
        key = CacheKey.generate_key(
            CacheKey.POLICY_BY_PROCEDURE, 
            procedure_code=procedure_code
        )
        return await self.cache.get(key)
    
    async def invalidate_policy(self, policy_id: str) -> bool:
        """
        Invalidate all cache entries for a specific policy.
        
        Args:
            policy_id: Policy identifier
            
        Returns:
            True if invalidation was successful
        """
        # Get policy data to determine other cache keys to invalidate
        policy = await self.get_policy_by_id(policy_id)
        
        keys_to_delete = [
            CacheKey.generate_key(CacheKey.POLICY_BY_ID, policy_id=policy_id)
        ]
        
        if policy:
            if 'payer_id' in policy:
                keys_to_delete.append(
                    CacheKey.generate_key(
                        CacheKey.POLICY_BY_PAYER, 
                        payer_id=policy['payer_id']
                    )
                )
            
            if 'procedure_code' in policy:
                keys_to_delete.append(
                    CacheKey.generate_key(
                        CacheKey.POLICY_BY_PROCEDURE, 
                        procedure_code=policy['procedure_code']
                    )
                )
        
        # Delete all related cache entries
        success = True
        for key in keys_to_delete:
            if not await self.cache.delete(key):
                success = False
        
        if success:
            logger.info(f"Policy {policy_id} invalidated from cache")
        else:
            logger.warning(f"Failed to fully invalidate policy {policy_id}")
        
        return success
    
    async def invalidate_payer_policies(self, payer_id: str) -> int:
        """
        Invalidate all cached policies for a payer.
        
        Args:
            payer_id: Payer identifier
            
        Returns:
            Number of cache entries invalidated
        """
        pattern = f"{CacheKey.POLICY_PREFIX}:*{payer_id}*"
        deleted_count = await self.cache.delete_pattern(pattern)
        
        logger.info(f"Invalidated {deleted_count} policy cache entries for payer {payer_id}")
        return deleted_count
    
    async def warm_frequently_accessed_policies(
        self, 
        policy_ids: List[str]
    ) -> Dict[str, bool]:
        """
        Warm cache with frequently accessed policies.
        
        Args:
            policy_ids: List of policy IDs to warm
            
        Returns:
            Dictionary mapping policy_id to success status
        """
        # This would typically fetch from database and cache
        # For now, we'll create a placeholder implementation
        results = {}
        
        for policy_id in policy_ids:
            # In a real implementation, this would fetch from database
            # and then cache the policy
            key = CacheKey.generate_key(CacheKey.POLICY_BY_ID, policy_id=policy_id)
            
            # Check if already cached
            if await self.cache.exists(key):
                # Extend TTL for frequently accessed policies
                extended = await self.cache.extend_ttl(key, CacheTTL.POLICY_ACTIVE)
                results[policy_id] = extended
            else:
                # Would fetch from database and cache here
                results[policy_id] = False
        
        warmed_count = sum(1 for success in results.values() if success)
        logger.info(f"Warmed {warmed_count}/{len(policy_ids)} frequently accessed policies")
        
        return results
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get policy cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        stats = {
            'total_policy_keys': 0,
            'active_policies': 0,
            'expired_policies': 0,
            'payer_indexes': 0,
            'procedure_indexes': 0
        }
        
        try:
            # Count different types of policy cache keys
            async with self.cache.get_client() as client:
                # This is a simplified implementation
                # In production, you might want to use Redis SCAN for large datasets
                all_keys = await asyncio.get_event_loop().run_in_executor(
                    None, client.keys, f"{CacheKey.POLICY_PREFIX}:*"
                )
                
                stats['total_policy_keys'] = len(all_keys)
                
                for key in all_keys:
                    if ':id:' in key:
                        ttl = await self.cache.get_ttl(key)
                        if ttl and ttl > CacheTTL.POLICY_EXPIRED:
                            stats['active_policies'] += 1
                        else:
                            stats['expired_policies'] += 1
                    elif ':payer:' in key:
                        stats['payer_indexes'] += 1
                    elif ':procedure:' in key:
                        stats['procedure_indexes'] += 1
        
        except Exception as e:
            logger.error(f"Failed to get policy cache stats: {e}")
        
        return stats


# Global policy cache service instance
policy_cache_service = PolicyCacheService()
"""
Multi-level caching system for the Prior Authorization Agent.

This module provides Redis-based caching for policies, decisions, and medical codes
with support for cache invalidation, TTL management, and cache warming.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union
from enum import Enum
import redis
from redis.exceptions import RedisError, ConnectionError
import asyncio
from contextlib import asynccontextmanager

from src.core.config import get_settings

logger = logging.getLogger(__name__)


class CacheLevel(Enum):
    """Cache levels for different types of data."""
    L1_MEMORY = "l1_memory"  # In-memory cache (future enhancement)
    L2_REDIS = "l2_redis"    # Redis cache
    L3_DATABASE = "l3_database"  # Database cache


class CacheKey:
    """Cache key constants and generators."""
    
    # Policy cache keys
    POLICY_PREFIX = "policy"
    POLICY_BY_PAYER = "policy:payer:{payer_id}"
    POLICY_BY_PROCEDURE = "policy:procedure:{procedure_code}"
    POLICY_BY_ID = "policy:id:{policy_id}"
    
    # Decision cache keys
    DECISION_PREFIX = "decision"
    DECISION_BY_REQUEST = "decision:request:{request_id}"
    DECISION_BY_ID = "decision:id:{decision_id}"
    
    # Medical code cache keys
    MEDICAL_CODE_PREFIX = "medical_code"
    ICD10_CODE = "medical_code:icd10:{code}"
    CPT_CODE = "medical_code:cpt:{code}"
    HCPCS_CODE = "medical_code:hcpcs:{code}"
    
    # Validation cache keys
    VALIDATION_PREFIX = "validation"
    VALIDATION_RESULT = "validation:result:{request_hash}"
    
    # Frequently accessed data
    FREQUENT_PREFIX = "frequent"
    FREQUENT_POLICIES = "frequent:policies"
    FREQUENT_CODES = "frequent:codes"
    
    @staticmethod
    def generate_key(template: str, **kwargs) -> str:
        """Generate cache key from template and parameters."""
        return template.format(**kwargs)


class CacheTTL:
    """TTL constants for different cache types."""
    
    # Policy TTLs (policies change infrequently)
    POLICY_DEFAULT = 3600 * 24  # 24 hours
    POLICY_ACTIVE = 3600 * 12   # 12 hours for active policies
    POLICY_EXPIRED = 3600       # 1 hour for expired policies
    
    # Decision TTLs (decisions are immutable once made)
    DECISION_APPROVED = 3600 * 24 * 30  # 30 days
    DECISION_DENIED = 3600 * 24 * 7     # 7 days
    DECISION_PENDING = 3600             # 1 hour
    
    # Medical code TTLs (codes change rarely)
    MEDICAL_CODE_VALID = 3600 * 24 * 7    # 7 days
    MEDICAL_CODE_INVALID = 3600 * 2       # 2 hours
    
    # Validation TTLs (validation results can be cached briefly)
    VALIDATION_RESULT = 3600 * 2  # 2 hours
    
    # Frequently accessed data (shorter TTL for freshness)
    FREQUENT_DATA = 3600 * 6  # 6 hours


class CacheManager:
    """
    Multi-level cache manager with Redis backend.
    
    Provides caching for policies, decisions, medical codes, and validation results
    with automatic TTL management and cache invalidation strategies.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._redis_client: Optional[redis.Redis] = None
        self._connection_pool: Optional[redis.ConnectionPool] = None
        self._is_connected = False
        
    async def initialize(self):
        """Initialize Redis connection and connection pool."""
        try:
            # Create connection pool for better performance
            self._connection_pool = redis.ConnectionPool(
                host=self.settings.redis_host,
                port=self.settings.redis_port,
                db=self.settings.redis_db,
                password=self.settings.redis_password,
                decode_responses=True,
                max_connections=20,
                retry_on_timeout=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            
            self._redis_client = redis.Redis(
                connection_pool=self._connection_pool,
                decode_responses=True
            )
            
            # Test connection
            await asyncio.get_event_loop().run_in_executor(
                None, self._redis_client.ping
            )
            
            self._is_connected = True
            logger.info("Redis cache initialized successfully")
            
        except (RedisError, ConnectionError) as e:
            logger.error(f"Failed to initialize Redis cache: {e}")
            self._is_connected = False
            raise
    
    async def close(self):
        """Close Redis connection and cleanup resources."""
        if self._connection_pool:
            self._connection_pool.disconnect()
        self._is_connected = False
        logger.info("Redis cache connection closed")
    
    @asynccontextmanager
    async def get_client(self):
        """Get Redis client with connection management."""
        if not self._is_connected or not self._redis_client:
            await self.initialize()
        
        try:
            yield self._redis_client
        except (RedisError, ConnectionError) as e:
            logger.error(f"Redis operation failed: {e}")
            self._is_connected = False
            raise
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        try:
            async with self.get_client() as client:
                value = await asyncio.get_event_loop().run_in_executor(
                    None, client.get, key
                )
                
                if value is not None:
                    logger.debug(f"Cache hit for key: {key}")
                    return json.loads(value)
                else:
                    logger.debug(f"Cache miss for key: {key}")
                    return None
                    
        except (RedisError, json.JSONDecodeError) as e:
            logger.error(f"Failed to get cache value for key {key}: {e}")
            return None
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None,
        nx: bool = False
    ) -> bool:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
            nx: Only set if key doesn't exist
            
        Returns:
            True if value was set, False otherwise
        """
        try:
            async with self.get_client() as client:
                serialized_value = json.dumps(value, default=str)
                
                result = await asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: client.set(key, serialized_value, ex=ttl, nx=nx)
                )
                
                if result:
                    logger.debug(f"Cache set for key: {key} (TTL: {ttl})")
                return bool(result)
                
        except (RedisError, json.JSONEncodeError) as e:
            logger.error(f"Failed to set cache value for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """
        Delete value from cache.
        
        Args:
            key: Cache key to delete
            
        Returns:
            True if key was deleted, False otherwise
        """
        try:
            async with self.get_client() as client:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, client.delete, key
                )
                
                if result:
                    logger.debug(f"Cache deleted for key: {key}")
                return bool(result)
                
        except RedisError as e:
            logger.error(f"Failed to delete cache key {key}: {e}")
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern.
        
        Args:
            pattern: Pattern to match (e.g., "policy:*")
            
        Returns:
            Number of keys deleted
        """
        try:
            async with self.get_client() as client:
                keys = await asyncio.get_event_loop().run_in_executor(
                    None, client.keys, pattern
                )
                
                if keys:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None, client.delete, *keys
                    )
                    logger.info(f"Deleted {result} cache keys matching pattern: {pattern}")
                    return result
                
                return 0
                
        except RedisError as e:
            logger.error(f"Failed to delete cache pattern {pattern}: {e}")
            return 0
    
    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.
        
        Args:
            key: Cache key to check
            
        Returns:
            True if key exists, False otherwise
        """
        try:
            async with self.get_client() as client:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, client.exists, key
                )
                return bool(result)
                
        except RedisError as e:
            logger.error(f"Failed to check cache key existence {key}: {e}")
            return False
    
    async def get_ttl(self, key: str) -> Optional[int]:
        """
        Get TTL for cache key.
        
        Args:
            key: Cache key
            
        Returns:
            TTL in seconds or None if key doesn't exist
        """
        try:
            async with self.get_client() as client:
                ttl = await asyncio.get_event_loop().run_in_executor(
                    None, client.ttl, key
                )
                
                if ttl == -2:  # Key doesn't exist
                    return None
                elif ttl == -1:  # Key exists but no TTL
                    return -1
                else:
                    return ttl
                    
        except RedisError as e:
            logger.error(f"Failed to get TTL for key {key}: {e}")
            return None
    
    async def extend_ttl(self, key: str, additional_seconds: int) -> bool:
        """
        Extend TTL for existing cache key.
        
        Args:
            key: Cache key
            additional_seconds: Additional seconds to add to TTL
            
        Returns:
            True if TTL was extended, False otherwise
        """
        try:
            current_ttl = await self.get_ttl(key)
            if current_ttl is None:
                return False
            
            new_ttl = max(0, current_ttl + additional_seconds)
            
            async with self.get_client() as client:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, client.expire, key, new_ttl
                )
                
                if result:
                    logger.debug(f"Extended TTL for key {key} by {additional_seconds}s")
                return bool(result)
                
        except RedisError as e:
            logger.error(f"Failed to extend TTL for key {key}: {e}")
            return False


# Global cache manager instance
cache_manager = CacheManager()
"""
Database optimization service for the Prior Authorization Agent.

This module provides query optimization, connection pooling management,
and database performance monitoring with caching integration.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple, Union
from contextlib import contextmanager
from dataclasses import dataclass
from collections import defaultdict
import asyncio

from sqlalchemy import text, func, and_, or_, select, update, delete
from sqlalchemy.orm import Session, Query, joinedload, selectinload
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import ClauseElement

from src.database.connection import get_database_manager, get_session
from src.database.models import (
    AuthorizationRequestDB, 
    AuthorizationDecisionDB, 
    CoveragePolicyDB
)
from src.services.cache import cache_manager
from src.models.enums import RequestStatus, DecisionStatus

logger = logging.getLogger(__name__)


@dataclass
class QueryPerformanceMetrics:
    """Performance metrics for database queries."""
    query_type: str
    execution_time: float
    rows_affected: int
    cache_hit: bool
    timestamp: datetime
    query_hash: str


@dataclass
class ConnectionPoolMetrics:
    """Connection pool performance metrics."""
    pool_size: int
    checked_out: int
    overflow: int
    invalid: int
    timestamp: datetime


class DatabaseOptimizationService:
    """
    Service for database query optimization and performance monitoring.
    
    Provides optimized queries, connection pool management, and performance
    monitoring with integrated caching for frequently accessed data.
    """
    
    def __init__(self):
        self.db_manager = get_database_manager()
        self.cache = cache_manager
        self.query_metrics: List[QueryPerformanceMetrics] = []
        self.connection_metrics: List[ConnectionPoolMetrics] = []
        self._query_cache: Dict[str, Any] = {}
    
    # Optimized Authorization Request Queries
    
    async def get_requests_by_provider_optimized(
        self,
        provider_id: str,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        use_cache: bool = True
    ) -> Tuple[List[AuthorizationRequestDB], int]:
        """
        Get authorization requests by provider with optimized query and caching.
        
        Args:
            provider_id: Provider identifier
            status: Optional status filter
            limit: Maximum number of results
            offset: Offset for pagination
            use_cache: Whether to use caching
            
        Returns:
            Tuple of (requests list, total count)
        """
        cache_key = f"requests:provider:{provider_id}:status:{status}:limit:{limit}:offset:{offset}"
        
        # Try cache first if enabled
        if use_cache:
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                logger.debug(f"Cache hit for provider requests: {provider_id}")
                return (
                    [self._deserialize_request(req) for req in cached_result['requests']],
                    cached_result['total_count']
                )
        
        start_time = time.time()
        
        with get_session() as session:
            # Build optimized query with proper indexing
            query = session.query(AuthorizationRequestDB).filter(
                AuthorizationRequestDB.provider_id == provider_id
            )
            
            if status:
                query = query.filter(AuthorizationRequestDB.status == status)
            
            # Use index hint for MySQL (if applicable)
            if self.db_manager.engine.dialect.name == "mysql":
                query = query.with_hint(
                    AuthorizationRequestDB, 
                    "USE INDEX (idx_provider_status)"
                )
            
            # Get total count efficiently
            total_count = query.count()
            
            # Get paginated results with eager loading
            requests = query.options(
                selectinload(AuthorizationRequestDB.decisions)
            ).order_by(
                AuthorizationRequestDB.submitted_at.desc()
            ).limit(limit).offset(offset).all()
        
        execution_time = time.time() - start_time
        
        # Record performance metrics
        self._record_query_metrics(
            "get_requests_by_provider",
            execution_time,
            len(requests),
            False,
            self._generate_query_hash(cache_key)
        )
        
        # Cache results if enabled
        if use_cache and requests:
            cache_data = {
                'requests': [self._serialize_request(req) for req in requests],
                'total_count': total_count
            }
            await self.cache.set(cache_key, cache_data, ttl=300)  # 5 minutes
        
        logger.debug(f"Retrieved {len(requests)} requests for provider {provider_id} in {execution_time:.3f}s")
        return requests, total_count
    
    async def get_pending_requests_optimized(
        self,
        urgency_filter: Optional[str] = None,
        age_hours: Optional[int] = None,
        use_cache: bool = True
    ) -> List[AuthorizationRequestDB]:
        """
        Get pending requests with optimized query for dashboard display.
        
        Args:
            urgency_filter: Optional urgency level filter
            age_hours: Optional filter for requests older than X hours
            use_cache: Whether to use caching
            
        Returns:
            List of pending authorization requests
        """
        cache_key = f"pending_requests:urgency:{urgency_filter}:age:{age_hours}"
        
        if use_cache:
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                logger.debug("Cache hit for pending requests")
                return [self._deserialize_request(req) for req in cached_result]
        
        start_time = time.time()
        
        with get_session() as session:
            # Optimized query using compound index
            query = session.query(AuthorizationRequestDB).filter(
                AuthorizationRequestDB.status.in_([
                    RequestStatus.SUBMITTED.value,
                    RequestStatus.IN_REVIEW.value,
                    RequestStatus.MORE_INFO_NEEDED.value
                ])
            )
            
            if urgency_filter:
                query = query.filter(AuthorizationRequestDB.urgency_level == urgency_filter)
            
            if age_hours:
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=age_hours)
                query = query.filter(AuthorizationRequestDB.submitted_at <= cutoff_time)
            
            # Use index hint and optimize ordering
            if self.db_manager.engine.dialect.name == "mysql":
                query = query.with_hint(
                    AuthorizationRequestDB,
                    "USE INDEX (idx_status_updated)"
                )
            
            requests = query.order_by(
                AuthorizationRequestDB.urgency_level.desc(),
                AuthorizationRequestDB.submitted_at.asc()
            ).limit(500).all()  # Reasonable limit for dashboard
        
        execution_time = time.time() - start_time
        
        self._record_query_metrics(
            "get_pending_requests",
            execution_time,
            len(requests),
            False,
            self._generate_query_hash(cache_key)
        )
        
        # Cache results
        if use_cache and requests:
            cache_data = [self._serialize_request(req) for req in requests]
            await self.cache.set(cache_key, cache_data, ttl=180)  # 3 minutes
        
        logger.debug(f"Retrieved {len(requests)} pending requests in {execution_time:.3f}s")
        return requests
    
    # Optimized Policy Queries
    
    async def get_active_policies_by_procedure_optimized(
        self,
        procedure_code: str,
        payer_id: Optional[str] = None,
        use_cache: bool = True
    ) -> List[CoveragePolicyDB]:
        """
        Get active policies for a procedure with optimized query and caching.
        
        Args:
            procedure_code: CPT/HCPCS procedure code
            payer_id: Optional payer filter
            use_cache: Whether to use caching
            
        Returns:
            List of active coverage policies
        """
        cache_key = f"policies:procedure:{procedure_code}:payer:{payer_id}"
        
        if use_cache:
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                logger.debug(f"Cache hit for policies: {procedure_code}")
                return [self._deserialize_policy(pol) for pol in cached_result]
        
        start_time = time.time()
        
        with get_session() as session:
            # Optimized query using compound indexes
            query = session.query(CoveragePolicyDB).filter(
                and_(
                    CoveragePolicyDB.procedure_code == procedure_code,
                    CoveragePolicyDB.is_active == True,
                    CoveragePolicyDB.effective_date <= datetime.now(timezone.utc).date(),
                    or_(
                        CoveragePolicyDB.expiration_date.is_(None),
                        CoveragePolicyDB.expiration_date > datetime.now(timezone.utc).date()
                    )
                )
            )
            
            if payer_id:
                query = query.filter(CoveragePolicyDB.payer_id == payer_id)
            
            # Use index hint for optimal performance
            if self.db_manager.engine.dialect.name == "mysql":
                query = query.with_hint(
                    CoveragePolicyDB,
                    "USE INDEX (idx_payer_procedure, idx_active_policies)"
                )
            
            policies = query.order_by(
                CoveragePolicyDB.policy_type.desc(),  # NCD > LCD > PAYER
                CoveragePolicyDB.effective_date.desc()
            ).all()
        
        execution_time = time.time() - start_time
        
        self._record_query_metrics(
            "get_active_policies_by_procedure",
            execution_time,
            len(policies),
            False,
            self._generate_query_hash(cache_key)
        )
        
        # Cache results with longer TTL for policies
        if use_cache and policies:
            cache_data = [self._serialize_policy(pol) for pol in policies]
            await self.cache.set(cache_key, cache_data, ttl=3600)  # 1 hour
        
        logger.debug(f"Retrieved {len(policies)} policies for {procedure_code} in {execution_time:.3f}s")
        return policies
    
    # Optimized Decision Queries
    
    async def get_recent_decisions_optimized(
        self,
        days: int = 7,
        status: Optional[str] = None,
        limit: int = 100,
        use_cache: bool = True
    ) -> List[AuthorizationDecisionDB]:
        """
        Get recent decisions with optimized query and caching.
        
        Args:
            days: Number of days to look back
            status: Optional status filter
            limit: Maximum number of results
            use_cache: Whether to use caching
            
        Returns:
            List of recent authorization decisions
        """
        cache_key = f"recent_decisions:days:{days}:status:{status}:limit:{limit}"
        
        if use_cache:
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                logger.debug("Cache hit for recent decisions")
                return [self._deserialize_decision(dec) for dec in cached_result]
        
        start_time = time.time()
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        with get_session() as session:
            query = session.query(AuthorizationDecisionDB).filter(
                AuthorizationDecisionDB.decided_at >= cutoff_date
            )
            
            if status:
                query = query.filter(AuthorizationDecisionDB.status == status)
            
            # Use index for optimal performance
            if self.db_manager.engine.dialect.name == "mysql":
                query = query.with_hint(
                    AuthorizationDecisionDB,
                    "USE INDEX (idx_status_decided)"
                )
            
            # Eager load related request data
            decisions = query.options(
                joinedload(AuthorizationDecisionDB.request)
            ).order_by(
                AuthorizationDecisionDB.decided_at.desc()
            ).limit(limit).all()
        
        execution_time = time.time() - start_time
        
        self._record_query_metrics(
            "get_recent_decisions",
            execution_time,
            len(decisions),
            False,
            self._generate_query_hash(cache_key)
        )
        
        # Cache results
        if use_cache and decisions:
            cache_data = [self._serialize_decision(dec) for dec in decisions]
            await self.cache.set(cache_key, cache_data, ttl=600)  # 10 minutes
        
        logger.debug(f"Retrieved {len(decisions)} recent decisions in {execution_time:.3f}s")
        return decisions
    
    # Batch Operations for Performance
    
    async def batch_update_request_status(
        self,
        request_ids: List[str],
        new_status: str
    ) -> int:
        """
        Batch update request status for better performance.
        
        Args:
            request_ids: List of request IDs to update
            new_status: New status value
            
        Returns:
            Number of rows updated
        """
        if not request_ids:
            return 0
        
        start_time = time.time()
        
        with get_session() as session:
            # Use bulk update for better performance
            result = session.execute(
                update(AuthorizationRequestDB)
                .where(AuthorizationRequestDB.request_id.in_(request_ids))
                .values(
                    status=new_status,
                    updated_at=datetime.now(timezone.utc)
                )
            )
            
            rows_updated = result.rowcount
            session.commit()
        
        execution_time = time.time() - start_time
        
        self._record_query_metrics(
            "batch_update_request_status",
            execution_time,
            rows_updated,
            False,
            self._generate_query_hash(f"batch_update:{len(request_ids)}")
        )
        
        # Invalidate related cache entries
        await self._invalidate_request_caches(request_ids)
        
        logger.info(f"Batch updated {rows_updated} request statuses in {execution_time:.3f}s")
        return rows_updated
    
    # Connection Pool Management
    
    def get_connection_pool_status(self) -> ConnectionPoolMetrics:
        """
        Get current connection pool status and metrics.
        
        Returns:
            Connection pool metrics
        """
        engine = self.db_manager.engine
        pool = engine.pool
        
        metrics = ConnectionPoolMetrics(
            pool_size=pool.size(),
            checked_out=pool.checkedout(),
            overflow=pool.overflow(),
            invalid=pool.invalid(),
            timestamp=datetime.now(timezone.utc)
        )
        
        self.connection_metrics.append(metrics)
        
        # Keep only recent metrics (last 24 hours)
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
        self.connection_metrics = [
            m for m in self.connection_metrics 
            if m.timestamp > cutoff_time
        ]
        
        return metrics
    
    def optimize_connection_pool(self) -> Dict[str, Any]:
        """
        Analyze connection pool usage and provide optimization recommendations.
        
        Returns:
            Dictionary with optimization recommendations
        """
        recent_metrics = [
            m for m in self.connection_metrics 
            if m.timestamp > datetime.now(timezone.utc) - timedelta(hours=1)
        ]
        
        if not recent_metrics:
            return {"status": "insufficient_data"}
        
        avg_checked_out = sum(m.checked_out for m in recent_metrics) / len(recent_metrics)
        max_checked_out = max(m.checked_out for m in recent_metrics)
        avg_overflow = sum(m.overflow for m in recent_metrics) / len(recent_metrics)
        
        recommendations = {
            "current_pool_size": self.db_manager.settings.db_pool_size,
            "avg_checked_out": avg_checked_out,
            "max_checked_out": max_checked_out,
            "avg_overflow": avg_overflow,
            "recommendations": []
        }
        
        # Generate recommendations
        if avg_checked_out > self.db_manager.settings.db_pool_size * 0.8:
            recommendations["recommendations"].append(
                "Consider increasing pool_size - high utilization detected"
            )
        
        if avg_overflow > 0:
            recommendations["recommendations"].append(
                "Connection overflow detected - consider increasing pool_size or max_overflow"
            )
        
        if max_checked_out < self.db_manager.settings.db_pool_size * 0.5:
            recommendations["recommendations"].append(
                "Pool may be oversized - consider reducing pool_size"
            )
        
        return recommendations
    
    # Performance Monitoring
    
    def get_query_performance_stats(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get query performance statistics for the specified time period.
        
        Args:
            hours: Number of hours to analyze
            
        Returns:
            Dictionary with performance statistics
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent_metrics = [
            m for m in self.query_metrics 
            if m.timestamp > cutoff_time
        ]
        
        if not recent_metrics:
            return {"status": "no_data"}
        
        # Group metrics by query type
        by_type = defaultdict(list)
        for metric in recent_metrics:
            by_type[metric.query_type].append(metric)
        
        stats = {
            "total_queries": len(recent_metrics),
            "time_period_hours": hours,
            "by_query_type": {}
        }
        
        for query_type, metrics in by_type.items():
            execution_times = [m.execution_time for m in metrics]
            cache_hits = sum(1 for m in metrics if m.cache_hit)
            
            stats["by_query_type"][query_type] = {
                "count": len(metrics),
                "avg_execution_time": sum(execution_times) / len(execution_times),
                "max_execution_time": max(execution_times),
                "min_execution_time": min(execution_times),
                "cache_hit_rate": cache_hits / len(metrics),
                "total_rows": sum(m.rows_affected for m in metrics)
            }
        
        return stats
    
    def get_slow_queries(self, threshold_seconds: float = 1.0) -> List[QueryPerformanceMetrics]:
        """
        Get queries that exceeded the performance threshold.
        
        Args:
            threshold_seconds: Execution time threshold
            
        Returns:
            List of slow query metrics
        """
        return [
            metric for metric in self.query_metrics
            if metric.execution_time > threshold_seconds
        ]
    
    # Helper Methods
    
    def _record_query_metrics(
        self,
        query_type: str,
        execution_time: float,
        rows_affected: int,
        cache_hit: bool,
        query_hash: str
    ) -> None:
        """Record query performance metrics."""
        metric = QueryPerformanceMetrics(
            query_type=query_type,
            execution_time=execution_time,
            rows_affected=rows_affected,
            cache_hit=cache_hit,
            timestamp=datetime.now(timezone.utc),
            query_hash=query_hash
        )
        
        self.query_metrics.append(metric)
        
        # Keep only recent metrics (last 24 hours)
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
        self.query_metrics = [
            m for m in self.query_metrics 
            if m.timestamp > cutoff_time
        ]
        
        # Log slow queries
        if execution_time > 2.0:
            logger.warning(f"Slow query detected: {query_type} took {execution_time:.3f}s")
    
    def _generate_query_hash(self, query_key: str) -> str:
        """Generate hash for query identification."""
        import hashlib
        return hashlib.md5(query_key.encode()).hexdigest()[:8]
    
    async def _invalidate_request_caches(self, request_ids: List[str]) -> None:
        """Invalidate cache entries related to requests."""
        # This would invalidate various cache patterns
        patterns = [
            "requests:provider:*",
            "pending_requests:*",
            "recent_decisions:*"
        ]
        
        for pattern in patterns:
            await self.cache.delete_pattern(pattern)
    
    def _serialize_request(self, request: AuthorizationRequestDB) -> Dict[str, Any]:
        """Serialize request for caching."""
        return {
            'request_id': request.request_id,
            'provider_id': request.provider_id,
            'status': request.status,
            'urgency_level': request.urgency_level,
            'submitted_at': request.submitted_at.isoformat(),
            'updated_at': request.updated_at.isoformat()
        }
    
    def _deserialize_request(self, data: Dict[str, Any]) -> AuthorizationRequestDB:
        """Deserialize request from cache (simplified)."""
        # In a real implementation, this would fully reconstruct the object
        request = AuthorizationRequestDB()
        request.request_id = data['request_id']
        request.provider_id = data['provider_id']
        request.status = data['status']
        request.urgency_level = data['urgency_level']
        return request
    
    def _serialize_policy(self, policy: CoveragePolicyDB) -> Dict[str, Any]:
        """Serialize policy for caching."""
        return {
            'policy_id': policy.policy_id,
            'payer_id': policy.payer_id,
            'procedure_code': policy.procedure_code,
            'policy_type': policy.policy_type,
            'is_active': policy.is_active
        }
    
    def _deserialize_policy(self, data: Dict[str, Any]) -> CoveragePolicyDB:
        """Deserialize policy from cache (simplified)."""
        policy = CoveragePolicyDB()
        policy.policy_id = data['policy_id']
        policy.payer_id = data['payer_id']
        policy.procedure_code = data['procedure_code']
        policy.policy_type = data['policy_type']
        policy.is_active = data['is_active']
        return policy
    
    def _serialize_decision(self, decision: AuthorizationDecisionDB) -> Dict[str, Any]:
        """Serialize decision for caching."""
        return {
            'decision_id': decision.decision_id,
            'request_id': decision.request_id,
            'status': decision.status,
            'decided_at': decision.decided_at.isoformat()
        }
    
    def _deserialize_decision(self, data: Dict[str, Any]) -> AuthorizationDecisionDB:
        """Deserialize decision from cache (simplified)."""
        decision = AuthorizationDecisionDB()
        decision.decision_id = data['decision_id']
        decision.request_id = data['request_id']
        decision.status = data['status']
        return decision


# Global database optimization service instance
db_optimization_service = DatabaseOptimizationService()
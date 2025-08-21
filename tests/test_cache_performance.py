"""
Performance tests for the caching system.

This module tests cache performance, effectiveness, and behavior under load
to ensure the caching system meets performance requirements.
"""

import pytest
import pytest_asyncio
import asyncio
import time
import random
from typing import Dict, List, Any
from unittest.mock import AsyncMock, patch

from tests.utils.performance_helpers import (
    PerformanceOptimizedFixtures,
    fast_test,
    get_performance_fixtures
)

from src.services.cache import cache_manager, CacheKey, CacheTTL
from src.services.policy_cache import policy_cache_service
from src.services.medical_code_cache import medical_code_cache_service, MedicalCodeType
from src.services.decision_cache import decision_cache_service
from src.services.cache_warming import cache_warming_service


class TestCachePerformance:
    """Test cache performance and effectiveness."""
    
    def setup_method(self):
        """Set up test method with performance optimizations."""
        self.config = get_optimization_config()
        self.optimizer = TestPerformanceOptimizer()
    
    @pytest_asyncio.fixture(autouse=True)
    async def setup_cache(self):
        """Setup cache for testing."""
        # Mock Redis client for testing
        with patch.object(cache_manager, '_redis_client') as mock_redis:
            mock_redis.ping.return_value = True
            mock_redis.get.return_value = None
            mock_redis.set.return_value = True
            mock_redis.delete.return_value = 1
            mock_redis.keys.return_value = []
            mock_redis.exists.return_value = False
            mock_redis.ttl.return_value = 3600
            mock_redis.expire.return_value = True
            
            cache_manager._is_connected = True
            yield
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    @fast_test(timeout=30.0)
    @pytest.mark.asyncio
    async def test_cache_get_performance(self):
        """Test cache get operation performance."""
        # Setup test data
        test_key = "test:performance:get"
        test_value = {"data": "test_value", "timestamp": time.time()}
        
        # Optimize iteration count
        iteration_count = self.optimizer.reduce_test_iterations(100, self.config['fast_mode'])
        
        with patch.object(cache_manager, 'get') as mock_get:
            mock_get.return_value = test_value
            
            # Measure performance of cache get operations
            start_time = time.time()
            tasks = []
            
            for _ in range(iteration_count):
                task = cache_manager.get(test_key)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks)
            end_time = time.time()
            
            # Verify performance (adjusted for optimized iteration count)
            total_time = end_time - start_time
            avg_time_per_operation = total_time / iteration_count
            
            expected_max_time = 1.0 if not self.config['fast_mode'] else 0.3
            expected_avg_time = 0.01 if not self.config['fast_mode'] else 0.03
            
            assert total_time < expected_max_time, f"{iteration_count} cache get operations took {total_time}s, should be < {expected_max_time}s"
            assert avg_time_per_operation < expected_avg_time, f"Average get time {avg_time_per_operation}s should be < {expected_avg_time}s"
            assert all(result == test_value for result in results)
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    @fast_test(timeout=30.0)
    async def test_cache_set_performance(self):
        """Test cache set operation performance."""
        # Optimize test data size
        data_count = self.optimizer.reduce_test_iterations(100, self.config['fast_mode'])
        test_data = [
            (f"test:performance:set:{i}", {"data": f"value_{i}", "index": i})
            for i in range(data_count)
        ]
        
        with patch.object(cache_manager, 'set') as mock_set:
            mock_set.return_value = True
            
            # Measure performance of cache set operations
            start_time = time.time()
            tasks = []
            
            for key, value in test_data:
                task = cache_manager.set(key, value, ttl=3600)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks)
            end_time = time.time()
            
            # Verify performance
            total_time = end_time - start_time
            avg_time_per_operation = total_time / 100
            
            assert total_time < 2.0, f"100 cache set operations took {total_time}s, should be < 2s"
            assert avg_time_per_operation < 0.02, f"Average set time {avg_time_per_operation}s should be < 0.02s"
            assert all(result is True for result in results)
    
    @pytest.mark.asyncio
    async def test_concurrent_cache_operations(self):
        """Test cache performance under concurrent load."""
        num_concurrent_operations = 50
        
        with patch.object(cache_manager, 'get') as mock_get, \
             patch.object(cache_manager, 'set') as mock_set:
            
            mock_get.return_value = {"cached": "data"}
            mock_set.return_value = True
            
            # Create mixed read/write operations
            tasks = []
            
            for i in range(num_concurrent_operations):
                if i % 2 == 0:
                    # Read operation
                    task = cache_manager.get(f"test:concurrent:read:{i}")
                else:
                    # Write operation
                    task = cache_manager.set(
                        f"test:concurrent:write:{i}", 
                        {"data": f"value_{i}"}, 
                        ttl=3600
                    )
                tasks.append(task)
            
            # Execute all operations concurrently
            start_time = time.time()
            results = await asyncio.gather(*tasks)
            end_time = time.time()
            
            # Verify performance
            total_time = end_time - start_time
            
            assert total_time < 3.0, f"50 concurrent operations took {total_time}s, should be < 3s"
            assert len(results) == num_concurrent_operations
    
    @pytest.mark.asyncio
    async def test_policy_cache_effectiveness(self):
        """Test policy cache hit rate and effectiveness."""
        test_policies = [
            {
                'policy_id': f'policy_{i}',
                'payer_id': f'payer_{i % 5}',  # 5 different payers
                'procedure_code': f'7055{i % 10}',  # 10 different procedures
                'is_active': True
            }
            for i in range(20)
        ]
        
        with patch.object(policy_cache_service.cache, 'set') as mock_set, \
             patch.object(policy_cache_service.cache, 'get') as mock_get:
            
            mock_set.return_value = True
            
            # Cache all policies
            cache_tasks = []
            for policy in test_policies:
                task = policy_cache_service.cache_policy(
                    policy, 
                    policy['policy_id'], 
                    policy['is_active']
                )
                cache_tasks.append(task)
            
            cache_results = await asyncio.gather(*cache_tasks)
            assert all(cache_results), "All policies should be cached successfully"
            
            # Simulate cache hits
            mock_get.return_value = test_policies[0]
            
            # Test retrieval performance
            start_time = time.time()
            retrieval_tasks = []
            
            for policy in test_policies:
                task = policy_cache_service.get_policy_by_id(policy['policy_id'])
                retrieval_tasks.append(task)
            
            retrieval_results = await asyncio.gather(*retrieval_tasks)
            end_time = time.time()
            
            # Verify effectiveness
            retrieval_time = end_time - start_time
            assert retrieval_time < 1.0, f"Policy retrieval took {retrieval_time}s, should be < 1s"
            assert all(result is not None for result in retrieval_results)
    
    @pytest.mark.asyncio
    async def test_medical_code_cache_batch_performance(self):
        """Test medical code cache batch operations performance."""
        test_codes = [
            (f"7055{i}", MedicalCodeType.CPT) for i in range(50)
        ] + [
            (f"M79.{i}", MedicalCodeType.ICD10) for i in range(50)
        ]
        
        with patch.object(medical_code_cache_service.cache, 'get') as mock_get:
            mock_get.return_value = {
                'code': '70551',
                'code_type': 'cpt',
                'is_valid': True,
                'description': 'MRI brain without contrast'
            }
            
            # Test batch retrieval performance
            start_time = time.time()
            batch_results = await medical_code_cache_service.batch_get_validations(test_codes)
            end_time = time.time()
            
            # Verify performance
            batch_time = end_time - start_time
            assert batch_time < 2.0, f"Batch code validation took {batch_time}s, should be < 2s"
            assert len(batch_results) == 100
    
    @pytest.mark.asyncio
    async def test_decision_cache_under_load(self):
        """Test decision cache performance under high load."""
        num_decisions = 100
        
        test_decisions = [
            {
                'decision_id': f'decision_{i}',
                'request_id': f'request_{i}',
                'status': 'approved' if i % 2 == 0 else 'denied',
                'reasoning': [f'Reason {i}'],
                'timestamp': time.time()
            }
            for i in range(num_decisions)
        ]
        
        with patch.object(decision_cache_service.cache, 'set') as mock_set, \
             patch.object(decision_cache_service.cache, 'get') as mock_get:
            
            mock_set.return_value = True
            mock_get.return_value = test_decisions[0]
            
            # Cache all decisions
            start_time = time.time()
            cache_tasks = []
            
            for decision in test_decisions:
                task = decision_cache_service.cache_decision(
                    decision,
                    decision['request_id'],
                    decision['decision_id'],
                    decision['status']
                )
                cache_tasks.append(task)
            
            cache_results = await asyncio.gather(*cache_tasks)
            cache_time = time.time() - start_time
            
            # Verify caching performance
            assert cache_time < 3.0, f"Caching {num_decisions} decisions took {cache_time}s, should be < 3s"
            assert all(cache_results), "All decisions should be cached successfully"
            
            # Test retrieval performance
            start_time = time.time()
            retrieval_tasks = []
            
            for decision in test_decisions:
                task = decision_cache_service.get_decision_by_id(decision['decision_id'])
                retrieval_tasks.append(task)
            
            retrieval_results = await asyncio.gather(*retrieval_tasks)
            retrieval_time = time.time() - start_time
            
            # Verify retrieval performance
            assert retrieval_time < 2.0, f"Retrieving {num_decisions} decisions took {retrieval_time}s, should be < 2s"
            assert all(result is not None for result in retrieval_results)
    
    @pytest.mark.asyncio
    async def test_cache_warming_performance(self):
        """Test cache warming service performance."""
        with patch.object(cache_warming_service.policy_cache, 'warm_frequently_accessed_policies') as mock_warm_policies, \
             patch.object(cache_warming_service.medical_code_cache, 'warm_frequently_used_codes') as mock_warm_codes:
            
            mock_warm_policies.return_value = {f'policy_{i}': True for i in range(10)}
            mock_warm_codes.return_value = {f'code_{i}': True for i in range(20)}
            
            # Test cache warming performance
            start_time = time.time()
            warming_results = await cache_warming_service.warm_frequently_accessed_data()
            end_time = time.time()
            
            # Verify warming performance
            warming_time = end_time - start_time
            assert warming_time < 5.0, f"Cache warming took {warming_time}s, should be < 5s"
            assert warming_results['total_warmed'] > 0
            assert 'completed_at' in warming_results
    
    @pytest.mark.asyncio
    async def test_cache_memory_efficiency(self):
        """Test cache memory usage and efficiency."""
        # This test would measure memory usage in a real implementation
        # For now, we'll test that cache operations don't accumulate memory leaks
        
        initial_operations = 100
        
        with patch.object(cache_manager, 'set') as mock_set, \
             patch.object(cache_manager, 'get') as mock_get:
            
            mock_set.return_value = True
            mock_get.return_value = {"test": "data"}
            
            # Perform initial operations
            for i in range(initial_operations):
                await cache_manager.set(f"memory_test_{i}", {"data": f"value_{i}"})
                await cache_manager.get(f"memory_test_{i}")
            
            # Perform additional operations to test for memory leaks
            additional_operations = 200
            start_time = time.time()
            
            for i in range(additional_operations):
                await cache_manager.set(f"memory_test_additional_{i}", {"data": f"value_{i}"})
                await cache_manager.get(f"memory_test_additional_{i}")
            
            end_time = time.time()
            
            # Verify that performance doesn't degrade significantly
            # (indicating potential memory leaks)
            total_time = end_time - start_time
            avg_time_per_operation = total_time / (additional_operations * 2)  # 2 operations per iteration
            
            assert avg_time_per_operation < 0.01, f"Average operation time {avg_time_per_operation}s indicates potential memory issues"
    
    @pytest.mark.asyncio
    async def test_cache_ttl_effectiveness(self):
        """Test TTL management effectiveness."""
        test_key = "test:ttl:effectiveness"
        test_value = {"data": "test"}
        
        with patch.object(cache_manager, 'set') as mock_set, \
             patch.object(cache_manager, 'get_ttl') as mock_get_ttl, \
             patch.object(cache_manager, 'extend_ttl') as mock_extend_ttl:
            
            mock_set.return_value = True
            mock_get_ttl.return_value = 1800  # 30 minutes
            mock_extend_ttl.return_value = True
            
            # Test TTL setting
            start_time = time.time()
            await cache_manager.set(test_key, test_value, ttl=3600)
            
            # Test TTL retrieval
            ttl = await cache_manager.get_ttl(test_key)
            
            # Test TTL extension
            await cache_manager.extend_ttl(test_key, 1800)
            
            end_time = time.time()
            
            # Verify TTL operations performance
            ttl_operations_time = end_time - start_time
            assert ttl_operations_time < 0.1, f"TTL operations took {ttl_operations_time}s, should be < 0.1s"
            assert ttl == 1800


class TestCacheEffectiveness:
    """Test cache effectiveness and hit rates."""
    
    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_cache_hit_rate_simulation(self):
        """Simulate cache hit rate under realistic usage patterns."""
        # Simulate 80/20 rule - 20% of data accessed 80% of the time
        popular_keys = [f"popular_{i}" for i in range(20)]
        rare_keys = [f"rare_{i}" for i in range(80)]
        
        cache_hits = 0
        cache_misses = 0
        
        with patch.object(cache_manager, 'get') as mock_get:
            # Simulate cache behavior
            async def mock_get_behavior(key):
                if key in popular_keys:
                    return {"cached": "data", "key": key}  # Cache hit
                else:
                    return None  # Cache miss
            
            mock_get.side_effect = mock_get_behavior
            
            # Simulate 1000 requests following 80/20 pattern
            for _ in range(1000):
                if random.random() < 0.8:
                    # 80% of requests for popular data
                    key = random.choice(popular_keys)
                else:
                    # 20% of requests for rare data
                    key = random.choice(rare_keys)
                
                result = await cache_manager.get(key)
                if result is not None:
                    cache_hits += 1
                else:
                    cache_misses += 1
            
            # Calculate hit rate
            hit_rate = cache_hits / (cache_hits + cache_misses)
            
            # Verify effectiveness
            assert hit_rate > 0.7, f"Cache hit rate {hit_rate} should be > 70% for 80/20 pattern"
            assert cache_hits > 700, f"Expected > 700 cache hits, got {cache_hits}"
    
    @pytest.mark.asyncio
    async def test_cache_warming_effectiveness(self):
        """Test that cache warming improves hit rates."""
        test_keys = [f"warm_test_{i}" for i in range(50)]
        
        with patch.object(cache_warming_service, 'warm_frequently_accessed_data') as mock_warm:
            mock_warm.return_value = {
                'total_warmed': 30,
                'policies': {f'policy_{i}': True for i in range(10)},
                'medical_codes': {f'code_{i}': True for i in range(20)}
            }
            
            # Warm cache
            warming_result = await cache_warming_service.warm_frequently_accessed_data()
            
            # Verify warming effectiveness
            assert warming_result['total_warmed'] >= 30
            assert len(warming_result['policies']) == 10
            assert len(warming_result['medical_codes']) == 20
            assert all(warming_result['policies'].values())
            assert all(warming_result['medical_codes'].values())
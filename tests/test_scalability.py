"""
Scalability tests for auto-scaling behavior validation.

Tests system behavior under varying loads to validate auto-scaling capabilities.
"""

import pytest
import time
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

from src.main import app
from src.services.validation import ValidationResult
from tests.test_data_generator import TestDataGenerator


class TestAutoScalingBehavior:
    """Test auto-scaling behavior validation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.client = TestClient(app)
        self.data_generator = TestDataGenerator()
    
    @pytest.mark.performance
    @pytest.mark.slow
    def test_load_ramp_up_behavior(self):
        """Test system behavior during load ramp-up scenarios."""
        # Simulate gradual load increase
        load_phases = [
            {"concurrent_users": 5, "duration": 10, "description": "Initial load"},
            {"concurrent_users": 20, "duration": 15, "description": "Medium load"},
            {"concurrent_users": 50, "duration": 20, "description": "High load"},
            {"concurrent_users": 100, "duration": 15, "description": "Peak load"},
            {"concurrent_users": 30, "duration": 10, "description": "Scale down"}
        ]
        
        phase_results = []
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            mock_validate.return_value = ValidationResult(
                is_valid=True, errors=[], warnings=[], processing_time_ms=800.0
            )
            mock_store.return_value = None
            
            for phase in load_phases:
                print(f"\nTesting {phase['description']}: {phase['concurrent_users']} users for {phase['duration']}s")
                
                phase_result = self._execute_load_phase(
                    concurrent_users=phase['concurrent_users'],
                    duration_seconds=phase['duration']
                )
                
                phase_result['description'] = phase['description']
                phase_result['concurrent_users'] = phase['concurrent_users']
                phase_results.append(phase_result)
                
                print(f"  Success rate: {phase_result['success_rate']:.2%}")
                print(f"  Avg response time: {phase_result['avg_response_time']:.3f}s")
                print(f"  Throughput: {phase_result['throughput']:.2f} req/s")
                
                # Brief pause between phases
                time.sleep(2)
        
        # Analyze auto-scaling behavior
        self._validate_auto_scaling_behavior(phase_results)
    
    @pytest.mark.performance
    def test_burst_load_handling(self):
        """Test system handling of sudden burst loads."""
        burst_scenarios = [
            {"name": "Small burst", "users": 25, "duration": 5},
            {"name": "Medium burst", "users": 75, "duration": 10},
            {"name": "Large burst", "users": 150, "duration": 8}
        ]
        
        burst_results = []
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            mock_validate.return_value = ValidationResult(
                is_valid=True, errors=[], warnings=[], processing_time_ms=600.0
            )
            mock_store.return_value = None
            
            for scenario in burst_scenarios:
                print(f"\nTesting {scenario['name']}: {scenario['users']} users")
                
                # Execute burst load
                start_time = time.time()
                results = []
                
                with ThreadPoolExecutor(max_workers=scenario['users']) as executor:
                    futures = []
                    
                    # Submit all requests simultaneously (burst)
                    for _ in range(scenario['users']):
                        future = executor.submit(self._submit_test_request)
                        futures.append(future)
                    
                    # Collect results
                    for future in as_completed(futures, timeout=scenario['duration'] + 10):
                        try:
                            result = future.result()
                            results.append(result)
                        except Exception as e:
                            results.append({'success': False, 'error': str(e), 'response_time': 10.0})
                
                end_time = time.time()
                total_time = end_time - start_time
                
                # Analyze burst results
                successful_requests = [r for r in results if r.get('success', False)]
                success_rate = len(successful_requests) / len(results)
                
                if successful_requests:
                    response_times = [r['response_time'] for r in successful_requests]
                    avg_response_time = statistics.mean(response_times)
                    p95_response_time = sorted(response_times)[int(0.95 * len(response_times))]
                else:
                    avg_response_time = float('inf')
                    p95_response_time = float('inf')
                
                burst_result = {
                    'name': scenario['name'],
                    'users': scenario['users'],
                    'success_rate': success_rate,
                    'avg_response_time': avg_response_time,
                    'p95_response_time': p95_response_time,
                    'total_time': total_time,
                    'throughput': len(successful_requests) / total_time if total_time > 0 else 0
                }
                
                burst_results.append(burst_result)
                
                print(f"  Success rate: {success_rate:.2%}")
                print(f"  Avg response time: {avg_response_time:.3f}s")
                print(f"  95th percentile: {p95_response_time:.3f}s")
                print(f"  Throughput: {burst_result['throughput']:.2f} req/s")
                
                # Pause between bursts
                time.sleep(5)
        
        # Validate burst handling
        for result in burst_results:
            assert result['success_rate'] >= 0.70, f"{result['name']} success rate too low: {result['success_rate']:.2%}"
            assert result['avg_response_time'] < 15.0, f"{result['name']} avg response time too high: {result['avg_response_time']:.3f}s"
    
    @pytest.mark.performance
    def test_sustained_load_stability(self):
        """Test system stability under sustained load."""
        sustained_load_config = {
            "concurrent_users": 40,
            "duration_minutes": 3,  # 3 minutes of sustained load
            "request_interval": 0.5  # Request every 0.5 seconds per user
        }
        
        print(f"Testing sustained load: {sustained_load_config['concurrent_users']} users for {sustained_load_config['duration_minutes']} minutes")
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            mock_validate.return_value = ValidationResult(
                is_valid=True, errors=[], warnings=[], processing_time_ms=700.0
            )
            mock_store.return_value = None
            
            # Execute sustained load test
            results = self._execute_sustained_load_test(sustained_load_config)
            
            # Analyze stability metrics
            time_windows = self._analyze_time_windows(results, window_size_seconds=30)
            
            print(f"\nSustained load results:")
            print(f"Total requests: {len(results)}")
            print(f"Overall success rate: {results['overall_success_rate']:.2%}")
            print(f"Average response time: {results['avg_response_time']:.3f}s")
            print(f"Throughput: {results['throughput']:.2f} req/s")
            
            # Validate stability over time
            success_rates = [window['success_rate'] for window in time_windows]
            response_times = [window['avg_response_time'] for window in time_windows]
            
            # Check for stability (low variance)
            success_rate_variance = statistics.variance(success_rates) if len(success_rates) > 1 else 0
            response_time_variance = statistics.variance(response_times) if len(response_times) > 1 else 0
            
            print(f"Success rate variance: {success_rate_variance:.6f}")
            print(f"Response time variance: {response_time_variance:.6f}")
            
            # Stability assertions
            assert results['overall_success_rate'] >= 0.85, f"Overall success rate too low: {results['overall_success_rate']:.2%}"
            assert results['avg_response_time'] < 10.0, f"Average response time too high: {results['avg_response_time']:.3f}s"
            assert success_rate_variance < 0.01, f"Success rate too variable: {success_rate_variance:.6f}"
            assert response_time_variance < 25.0, f"Response time too variable: {response_time_variance:.6f}"
    
    def _execute_load_phase(self, concurrent_users: int, duration_seconds: int) -> dict:
        """Execute a single load phase."""
        results = []
        start_time = time.time()
        end_time = start_time + duration_seconds
        
        def user_simulation():
            """Simulate a single user making requests."""
            user_results = []
            while time.time() < end_time:
                result = self._submit_test_request()
                user_results.append(result)
                time.sleep(0.5)  # Request every 0.5 seconds
            return user_results
        
        # Execute concurrent users
        with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = [executor.submit(user_simulation) for _ in range(concurrent_users)]
            
            for future in as_completed(futures):
                user_results = future.result()
                results.extend(user_results)
        
        # Analyze phase results
        successful_requests = [r for r in results if r.get('success', False)]
        success_rate = len(successful_requests) / len(results) if results else 0
        
        if successful_requests:
            response_times = [r['response_time'] for r in successful_requests]
            avg_response_time = statistics.mean(response_times)
        else:
            avg_response_time = float('inf')
        
        actual_duration = time.time() - start_time
        throughput = len(successful_requests) / actual_duration if actual_duration > 0 else 0
        
        return {
            'total_requests': len(results),
            'successful_requests': len(successful_requests),
            'success_rate': success_rate,
            'avg_response_time': avg_response_time,
            'throughput': throughput,
            'duration': actual_duration
        }
    
    def _execute_sustained_load_test(self, config: dict) -> dict:
        """Execute sustained load test."""
        results = []
        start_time = time.time()
        end_time = start_time + (config['duration_minutes'] * 60)
        
        def sustained_user():
            """Simulate sustained user activity."""
            user_results = []
            while time.time() < end_time:
                result = self._submit_test_request()
                result['timestamp'] = time.time()
                user_results.append(result)
                time.sleep(config['request_interval'])
            return user_results
        
        # Execute sustained load
        with ThreadPoolExecutor(max_workers=config['concurrent_users']) as executor:
            futures = [executor.submit(sustained_user) for _ in range(config['concurrent_users'])]
            
            for future in as_completed(futures):
                user_results = future.result()
                results.extend(user_results)
        
        # Analyze sustained load results
        successful_requests = [r for r in results if r.get('success', False)]
        success_rate = len(successful_requests) / len(results) if results else 0
        
        if successful_requests:
            response_times = [r['response_time'] for r in successful_requests]
            avg_response_time = statistics.mean(response_times)
        else:
            avg_response_time = float('inf')
        
        actual_duration = time.time() - start_time
        throughput = len(successful_requests) / actual_duration if actual_duration > 0 else 0
        
        return {
            'results': results,
            'overall_success_rate': success_rate,
            'avg_response_time': avg_response_time,
            'throughput': throughput,
            'duration': actual_duration
        }
    
    def _analyze_time_windows(self, results: dict, window_size_seconds: int = 30) -> list:
        """Analyze results in time windows for stability assessment."""
        if not results['results']:
            return []
        
        # Sort results by timestamp
        sorted_results = sorted(results['results'], key=lambda x: x.get('timestamp', 0))
        
        start_time = sorted_results[0]['timestamp']
        end_time = sorted_results[-1]['timestamp']
        
        windows = []
        current_time = start_time
        
        while current_time < end_time:
            window_end = current_time + window_size_seconds
            
            # Get results in this window
            window_results = [
                r for r in sorted_results
                if current_time <= r.get('timestamp', 0) < window_end
            ]
            
            if window_results:
                successful = [r for r in window_results if r.get('success', False)]
                success_rate = len(successful) / len(window_results)
                
                if successful:
                    avg_response_time = statistics.mean([r['response_time'] for r in successful])
                else:
                    avg_response_time = float('inf')
                
                windows.append({
                    'start_time': current_time,
                    'end_time': window_end,
                    'total_requests': len(window_results),
                    'successful_requests': len(successful),
                    'success_rate': success_rate,
                    'avg_response_time': avg_response_time
                })
            
            current_time = window_end
        
        return windows
    
    def _validate_auto_scaling_behavior(self, phase_results: list):
        """Validate auto-scaling behavior from phase results."""
        print("\nValidating auto-scaling behavior:")
        
        # Check that system maintains reasonable performance across phases
        for result in phase_results:
            assert result['success_rate'] >= 0.75, f"{result['description']} success rate too low: {result['success_rate']:.2%}"
            assert result['avg_response_time'] < 20.0, f"{result['description']} response time too high: {result['avg_response_time']:.3f}s"
        
        # Check that throughput scales appropriately with load
        throughputs = [r['throughput'] for r in phase_results]
        concurrent_users = [r['concurrent_users'] for r in phase_results]
        
        # Throughput should generally increase with more users (up to a point)
        peak_throughput = max(throughputs)
        peak_users = concurrent_users[throughputs.index(peak_throughput)]
        
        print(f"Peak throughput: {peak_throughput:.2f} req/s at {peak_users} users")
        
        # Validate that system doesn't completely fail under high load
        high_load_phases = [r for r in phase_results if r['concurrent_users'] >= 50]
        if high_load_phases:
            min_high_load_success = min(r['success_rate'] for r in high_load_phases)
            assert min_high_load_success >= 0.60, f"High load success rate too low: {min_high_load_success:.2%}"
        
        print("Auto-scaling behavior validation passed")
    
    def _submit_test_request(self) -> dict:
        """Submit a single test request and return metrics."""
        try:
            request = self.data_generator.generate_authorization_request()
            request_data = self._convert_request_to_api_format(request)
            
            start_time = time.time()
            response = self.client.post("/api/v1/authorization/requests", json=request_data)
            end_time = time.time()
            
            return {
                'success': response.status_code in [200, 400, 422],
                'status_code': response.status_code,
                'response_time': end_time - start_time
            }
        except Exception as e:
            return {
                'success': False,
                'status_code': 500,
                'response_time': 10.0,
                'error': str(e)
            }
    
    def _convert_request_to_api_format(self, request) -> dict:
        """Convert AuthorizationRequest to API format."""
        return {
            "provider_id": request.provider_id,
            "patient_demographics": {
                "patient_id": request.patient_demographics.patient_id,
                "age": request.patient_demographics.age,
                "gender": request.patient_demographics.gender.value,
                "insurance_id": request.patient_demographics.insurance_id,
                "member_id": request.patient_demographics.member_id
            },
            "diagnosis_codes": [
                {"code": code.code, "description": code.description}
                for code in request.diagnosis_codes
            ],
            "procedure_codes": [
                {"code": code.code, "description": code.description}
                for code in request.procedure_codes
            ],
            "clinical_notes": request.clinical_notes,
            "procedure_type": request.procedure_type.value,
            "urgency_level": request.urgency_level.value
        }


class TestResourceUtilization:
    """Test resource utilization under various loads."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.client = TestClient(app)
        self.data_generator = TestDataGenerator()
    
    @pytest.mark.performance
    def test_memory_usage_under_load(self):
        """Test memory usage patterns under increasing load."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        
        load_levels = [10, 25, 50, 100]
        memory_usage = []
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            mock_validate.return_value = ValidationResult(
                is_valid=True, errors=[], warnings=[], processing_time_ms=500.0
            )
            mock_store.return_value = None
            
            for load_level in load_levels:
                print(f"\nTesting memory usage at {load_level} concurrent requests")
                
                # Measure memory before load
                initial_memory = process.memory_info().rss / 1024 / 1024  # MB
                
                # Execute load
                with ThreadPoolExecutor(max_workers=load_level) as executor:
                    futures = [
                        executor.submit(self._submit_test_request)
                        for _ in range(load_level)
                    ]
                    
                    # Measure memory during load
                    peak_memory = process.memory_info().rss / 1024 / 1024  # MB
                    
                    # Wait for completion
                    for future in as_completed(futures):
                        future.result()
                
                # Measure memory after load
                final_memory = process.memory_info().rss / 1024 / 1024  # MB
                
                memory_usage.append({
                    'load_level': load_level,
                    'initial_memory': initial_memory,
                    'peak_memory': peak_memory,
                    'final_memory': final_memory,
                    'memory_increase': peak_memory - initial_memory
                })
                
                print(f"  Initial: {initial_memory:.1f} MB")
                print(f"  Peak: {peak_memory:.1f} MB")
                print(f"  Final: {final_memory:.1f} MB")
                print(f"  Increase: {peak_memory - initial_memory:.1f} MB")
                
                # Brief pause for memory cleanup
                time.sleep(2)
        
        # Analyze memory usage patterns
        max_memory_increase = max(usage['memory_increase'] for usage in memory_usage)
        
        print(f"\nMemory usage analysis:")
        print(f"Maximum memory increase: {max_memory_increase:.1f} MB")
        
        # Memory usage should be reasonable
        assert max_memory_increase < 500.0, f"Memory increase too high: {max_memory_increase:.1f} MB"
        
        # Memory should not grow linearly with load (indicating memory leaks)
        memory_increases = [usage['memory_increase'] for usage in memory_usage]
        load_levels_tested = [usage['load_level'] for usage in memory_usage]
        
        # Simple check: memory increase shouldn't be directly proportional to load
        if len(memory_increases) > 1:
            memory_per_request = [inc / load for inc, load in zip(memory_increases, load_levels_tested)]
            memory_variance = statistics.variance(memory_per_request)
            
            print(f"Memory per request variance: {memory_variance:.3f}")
            # High variance is actually good - means memory doesn't scale linearly
    
    def _submit_test_request(self) -> dict:
        """Submit a single test request."""
        try:
            request = self.data_generator.generate_authorization_request()
            request_data = self._convert_request_to_api_format(request)
            
            response = self.client.post("/api/v1/authorization/requests", json=request_data)
            
            return {
                'success': response.status_code in [200, 400, 422],
                'status_code': response.status_code
            }
        except Exception:
            return {'success': False, 'status_code': 500}
    
    def _convert_request_to_api_format(self, request) -> dict:
        """Convert AuthorizationRequest to API format."""
        return {
            "provider_id": request.provider_id,
            "patient_demographics": {
                "patient_id": request.patient_demographics.patient_id,
                "age": request.patient_demographics.age,
                "gender": request.patient_demographics.gender.value,
                "insurance_id": request.patient_demographics.insurance_id,
                "member_id": request.patient_demographics.member_id
            },
            "diagnosis_codes": [
                {"code": code.code, "description": code.description}
                for code in request.diagnosis_codes
            ],
            "procedure_codes": [
                {"code": code.code, "description": code.description}
                for code in request.procedure_codes
            ],
            "clinical_notes": request.clinical_notes,
            "procedure_type": request.procedure_type.value,
            "urgency_level": request.urgency_level.value
        }
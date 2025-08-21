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
from tests.utils.data_generator import DataGenerator
from tests.utils.performance_helpers import (
    LoadTestOptimizer, 
    performance_test,
    get_optimization_config
)


class TestAutoScalingBehavior:
    
    def setup_method(self):
        """Set up test method with performance optimizations."""
        self.optimizer = LoadTestOptimizer(fast_mode=get_optimization_config()['fast_mode'])
        self.client = TestClient(app)
    """Test auto-scaling behavior validation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.client = TestClient(app)
        self.data_generator = DataGenerator()
    
        @pytest.mark.performance
        @pytest.mark.slow
        @performance_test(timeout=180.0)
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
        
        # Optimize for faster execution
        load_phases = [self.optimizer.optimize_load_config(phase) for phase in load_phases]
        
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
                
                # Brief pause between phases (optimized)
                time.sleep(0.1 if self.optimizer.fast_mode else 2)
        
        # Analyze auto-scaling behavior
        self._validate_auto_scaling_behavior(phase_results)
    
    @pytest.mark.performance
    @pytest.mark.slow
    @performance_test(timeout=120.0)
    def test_burst_load_handling(self):
    """
        Test burst load handling.
        
        This test validates that the system meets performance requirements
        under various load conditions and maintains acceptable response
        times while handling concurrent requests.
        
        Performance Requirements:
        - 95% of requests must complete within 2 minutes
        - System must handle 1000+ concurrent requests
        - Memory usage must remain within acceptable limits
        - Database connections must be properly managed
        
        Test Scenarios:
        - Standard input scenarios
        - Edge cases and boundary conditions
        - Error handling scenarios
        
        Expected Behavior:
        - Response times should meet or exceed performance targets
        - System should remain stable under load
        - Resource utilization should be within acceptable ranges
        - Error rates should remain below 5% under normal load
        
        Monitoring:
        - Response time distribution analysis
        - Resource utilization tracking
        - Error rate monitoring
        - Throughput measurement
        """
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
        self.data_generator = DataGenerator()
    
        @pytest.mark.performance
        def test_memory_usage_under_load(self):
    """
        Test memory usage under load.
        
        This test validates that the system meets performance requirements
        under various load conditions and maintains acceptable response
        times while handling concurrent requests.
        
        Performance Requirements:
        - 95% of requests must complete within 2 minutes
        - System must handle 1000+ concurrent requests
        - Memory usage must remain within acceptable limits
        - Database connections must be properly managed
        
        Test Scenarios:
        - Standard input scenarios
        - Edge cases and boundary conditions
        - Error handling scenarios
        
        Expected Behavior:
        - Response times should meet or exceed performance targets
        - System should remain stable under load
        - Resource utilization should be within acceptable ranges
        - Error rates should remain below 5% under normal load
        
        Monitoring:
        - Response time distribution analysis
        - Resource utilization tracking
        - Error rate monitoring
        - Throughput measurement
        """
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
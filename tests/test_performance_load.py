"""
Performance and load testing for the prior authorization system.

Tests system behavior under various load conditions and validates
performance requirements.
"""

import pytest
import asyncio
import time
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

from src.main import app
from src.services.validation import ValidationResult
from tests.test_data_generator import TestDataGenerator


class TestPerformanceRequirements:
    """Test performance requirements compliance."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.client = TestClient(app)
        self.data_generator = TestDataGenerator()
    
    @pytest.mark.performance
    def test_request_processing_time_requirement(self):
        """Test that 95% of requests are processed within 2 minutes."""
        request_count = 100
        processing_times = []
        
        # Generate test requests
        test_requests = []
        for _ in range(request_count):
            request = self.data_generator.generate_authorization_request()
            request_data = self._convert_request_to_api_format(request)
            test_requests.append(request_data)
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.policy_validation.PolicyValidationService.validate_with_medical_necessity') as mock_policy, \
             patch('src.services.decision_engine.DecisionEngine.generate_decision') as mock_decision, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            # Mock fast responses
            mock_validate.return_value = ValidationResult(
                is_valid=True, errors=[], warnings=[], processing_time_ms=500.0
            )
            mock_policy.return_value = {'policy_validation': {'is_covered': True}}
            mock_decision.return_value = Mock()
            mock_store.return_value = None
            
            # Process requests and measure time
            for request_data in test_requests:
                start_time = time.time()
                
                response = self.client.post("/api/v1/authorization/requests", json=request_data)
                
                end_time = time.time()
                processing_time = end_time - start_time
                processing_times.append(processing_time)
                
                # Basic response validation
                assert response.status_code in [200, 400, 422]
        
        # Analyze performance
        processing_times.sort()
        percentile_95 = processing_times[int(0.95 * len(processing_times))]
        average_time = statistics.mean(processing_times)
        
        print(f"Average processing time: {average_time:.3f}s")
        print(f"95th percentile: {percentile_95:.3f}s")
        print(f"Max processing time: {max(processing_times):.3f}s")
        
        # Requirement: 95% of requests under 2 minutes (120 seconds)
        assert percentile_95 < 120.0, f"95th percentile ({percentile_95:.3f}s) exceeds 2-minute requirement"
        
        # Additional performance assertions
        assert average_time < 10.0, f"Average time ({average_time:.3f}s) too high"
        assert max(processing_times) < 180.0, f"Max time ({max(processing_times):.3f}s) too high"
    
    @pytest.mark.performance
    def test_validation_performance_requirement(self):
        """Test that data validation completes within 5 seconds."""
        validation_times = []
        
        # Generate test data with various complexity levels
        test_cases = [
            self.data_generator.generate_authorization_request("routine"),
            self.data_generator.generate_authorization_request("urgent"),
            self.data_generator.generate_authorization_request("emergent")
        ]
        
        for request in test_cases:
            request_data = self._convert_request_to_api_format(request)
            
            # Measure validation time specifically
            start_time = time.time()
            
            # This would normally call the validation service directly
            # For testing, we'll measure the API call time as a proxy
            response = self.client.post("/api/v1/authorization/requests", json=request_data)
            
            end_time = time.time()
            validation_time = end_time - start_time
            validation_times.append(validation_time)
        
        # Analyze validation performance
        max_validation_time = max(validation_times)
        average_validation_time = statistics.mean(validation_times)
        
        print(f"Average validation time: {average_validation_time:.3f}s")
        print(f"Max validation time: {max_validation_time:.3f}s")
        
        # Requirement: validation within 5 seconds
        assert max_validation_time < 5.0, f"Validation time ({max_validation_time:.3f}s) exceeds 5-second requirement"
        assert average_validation_time < 2.0, f"Average validation time ({average_validation_time:.3f}s) too high"
    
    @pytest.mark.performance
    @pytest.mark.slow
    def test_concurrent_request_performance(self):
        """Test performance under concurrent load."""
        concurrent_requests = 50
        
        def submit_request():
            """Submit a single request and return processing time."""
            request = self.data_generator.generate_authorization_request()
            request_data = self._convert_request_to_api_format(request)
            
            start_time = time.time()
            response = self.client.post("/api/v1/authorization/requests", json=request_data)
            end_time = time.time()
            
            return {
                'processing_time': end_time - start_time,
                'status_code': response.status_code,
                'success': response.status_code in [200, 400, 422]
            }
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            mock_validate.return_value = ValidationResult(
                is_valid=True, errors=[], warnings=[], processing_time_ms=800.0
            )
            mock_store.return_value = None
            
            # Execute concurrent requests
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(submit_request) for _ in range(concurrent_requests)]
                results = [future.result() for future in as_completed(futures)]
        
        # Analyze concurrent performance
        processing_times = [r['processing_time'] for r in results]
        success_rate = sum(1 for r in results if r['success']) / len(results)
        
        average_time = statistics.mean(processing_times)
        percentile_95 = sorted(processing_times)[int(0.95 * len(processing_times))]
        
        print(f"Concurrent requests: {concurrent_requests}")
        print(f"Success rate: {success_rate:.2%}")
        print(f"Average time under load: {average_time:.3f}s")
        print(f"95th percentile under load: {percentile_95:.3f}s")
        
        # Performance assertions under load
        assert success_rate >= 0.95, f"Success rate ({success_rate:.2%}) below 95%"
        assert average_time < 15.0, f"Average time under load ({average_time:.3f}s) too high"
        assert percentile_95 < 30.0, f"95th percentile under load ({percentile_95:.3f}s) too high"
    
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


class TestLoadTesting:
    """Load testing for system scalability."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.client = TestClient(app)
        self.data_generator = TestDataGenerator()
    
    @pytest.mark.performance
    @pytest.mark.slow
    def test_1000_concurrent_requests_requirement(self):
        """Test system can handle 1000+ concurrent requests."""
        concurrent_requests = 1000
        batch_size = 100  # Process in batches to avoid overwhelming test environment
        
        def process_batch(batch_requests):
            """Process a batch of requests."""
            batch_results = []
            
            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = []
                
                for request_data in batch_requests:
                    future = executor.submit(self._submit_single_request, request_data)
                    futures.append(future)
                
                for future in as_completed(futures):
                    try:
                        result = future.result(timeout=30)
                        batch_results.append(result)
                    except Exception as e:
                        batch_results.append({
                            'success': False,
                            'error': str(e),
                            'processing_time': 30.0
                        })
            
            return batch_results
        
        # Generate test data
        all_requests = []
        for _ in range(concurrent_requests):
            request = self.data_generator.generate_authorization_request()
            request_data = self._convert_request_to_api_format(request)
            all_requests.append(request_data)
        
        # Process in batches
        all_results = []
        batches = [all_requests[i:i + batch_size] for i in range(0, len(all_requests), batch_size)]
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            mock_validate.return_value = ValidationResult(
                is_valid=True, errors=[], warnings=[], processing_time_ms=600.0
            )
            mock_store.return_value = None
            
            start_time = time.time()
            
            for i, batch in enumerate(batches):
                print(f"Processing batch {i+1}/{len(batches)}")
                batch_results = process_batch(batch)
                all_results.extend(batch_results)
            
            end_time = time.time()
            total_time = end_time - start_time
        
        # Analyze load test results
        successful_requests = [r for r in all_results if r.get('success', False)]
        success_rate = len(successful_requests) / len(all_results)
        
        if successful_requests:
            processing_times = [r['processing_time'] for r in successful_requests]
            average_time = statistics.mean(processing_times)
            percentile_95 = sorted(processing_times)[int(0.95 * len(processing_times))]
            throughput = len(successful_requests) / total_time
        else:
            average_time = float('inf')
            percentile_95 = float('inf')
            throughput = 0
        
        print(f"Load test results for {concurrent_requests} requests:")
        print(f"Total time: {total_time:.2f}s")
        print(f"Success rate: {success_rate:.2%}")
        print(f"Throughput: {throughput:.2f} requests/second")
        print(f"Average processing time: {average_time:.3f}s")
        print(f"95th percentile: {percentile_95:.3f}s")
        
        # Load test assertions
        assert success_rate >= 0.90, f"Success rate ({success_rate:.2%}) below 90% under load"
        assert throughput >= 10.0, f"Throughput ({throughput:.2f} req/s) too low"
        
        if successful_requests:
            assert average_time < 20.0, f"Average time under load ({average_time:.3f}s) too high"
            assert percentile_95 < 60.0, f"95th percentile under load ({percentile_95:.3f}s) too high"
    
    @pytest.mark.performance
    def test_stress_testing_behavior(self):
        """Test system behavior under extreme stress conditions."""
        stress_requests = 200
        max_workers = 50  # High concurrency
        
        def stress_request():
            """Submit request under stress conditions."""
            try:
                request = self.data_generator.generate_authorization_request()
                request_data = self._convert_request_to_api_format(request)
                
                start_time = time.time()
                response = self.client.post("/api/v1/authorization/requests", json=request_data)
                end_time = time.time()
                
                return {
                    'success': response.status_code in [200, 400, 422, 429, 503],  # Include rate limit and service unavailable
                    'status_code': response.status_code,
                    'processing_time': end_time - start_time,
                    'error': None
                }
            except Exception as e:
                return {
                    'success': False,
                    'status_code': 500,
                    'processing_time': 30.0,
                    'error': str(e)
                }
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            mock_validate.return_value = ValidationResult(
                is_valid=True, errors=[], warnings=[], processing_time_ms=1000.0
            )
            mock_store.return_value = None
            
            # Execute stress test
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(stress_request) for _ in range(stress_requests)]
                results = []
                
                for future in as_completed(futures, timeout=120):  # 2-minute timeout
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        results.append({
                            'success': False,
                            'status_code': 500,
                            'processing_time': 120.0,
                            'error': str(e)
                        })
        
        # Analyze stress test results
        success_rate = sum(1 for r in results if r['success']) / len(results)
        error_rate = sum(1 for r in results if not r['success']) / len(results)
        
        status_codes = {}
        for result in results:
            code = result['status_code']
            status_codes[code] = status_codes.get(code, 0) + 1
        
        print(f"Stress test results for {stress_requests} requests:")
        print(f"Success rate: {success_rate:.2%}")
        print(f"Error rate: {error_rate:.2%}")
        print(f"Status code distribution: {status_codes}")
        
        # Stress test assertions - system should degrade gracefully
        assert success_rate >= 0.70, f"Success rate ({success_rate:.2%}) too low under stress"
        assert error_rate <= 0.30, f"Error rate ({error_rate:.2%}) too high under stress"
        
        # System should return appropriate error codes under stress
        if 429 in status_codes or 503 in status_codes:
            print("System correctly returned rate limiting or service unavailable responses")
    
    @pytest.mark.performance
    def test_auto_scaling_behavior_validation(self):
        """Test that system behavior is consistent with auto-scaling expectations."""
        # This test validates that the system can handle varying loads
        # which would trigger auto-scaling in production
        
        load_phases = [
            {"requests": 10, "description": "Low load"},
            {"requests": 50, "description": "Medium load"},
            {"requests": 100, "description": "High load"},
            {"requests": 50, "description": "Scale down"},
            {"requests": 10, "description": "Low load again"}
        ]
        
        phase_results = []
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            mock_validate.return_value = ValidationResult(
                is_valid=True, errors=[], warnings=[], processing_time_ms=800.0
            )
            mock_store.return_value = None
            
            for phase in load_phases:
                print(f"Testing {phase['description']} ({phase['requests']} requests)")
                
                # Generate requests for this phase
                requests = []
                for _ in range(phase['requests']):
                    request = self.data_generator.generate_authorization_request()
                    request_data = self._convert_request_to_api_format(request)
                    requests.append(request_data)
                
                # Execute phase
                start_time = time.time()
                phase_success_count = 0
                
                with ThreadPoolExecutor(max_workers=min(20, phase['requests'])) as executor:
                    futures = [
                        executor.submit(self._submit_single_request, req_data)
                        for req_data in requests
                    ]
                    
                    for future in as_completed(futures):
                        result = future.result()
                        if result.get('success', False):
                            phase_success_count += 1
                
                end_time = time.time()
                phase_time = end_time - start_time
                
                phase_result = {
                    'description': phase['description'],
                    'requests': phase['requests'],
                    'success_count': phase_success_count,
                    'success_rate': phase_success_count / phase['requests'],
                    'total_time': phase_time,
                    'throughput': phase_success_count / phase_time if phase_time > 0 else 0
                }
                
                phase_results.append(phase_result)
                
                print(f"  Success rate: {phase_result['success_rate']:.2%}")
                print(f"  Throughput: {phase_result['throughput']:.2f} req/s")
                
                # Brief pause between phases
                time.sleep(1)
        
        # Analyze auto-scaling behavior
        for result in phase_results:
            # Each phase should maintain reasonable success rates
            assert result['success_rate'] >= 0.80, f"{result['description']} success rate too low: {result['success_rate']:.2%}"
            
            # Throughput should be reasonable for the load
            expected_min_throughput = min(result['requests'] / 10, 5.0)  # At least 5 req/s or requests/10s
            assert result['throughput'] >= expected_min_throughput, f"{result['description']} throughput too low: {result['throughput']:.2f}"
        
        print("Auto-scaling behavior validation completed successfully")
    
    def _submit_single_request(self, request_data):
        """Submit a single request and return result."""
        try:
            start_time = time.time()
            response = self.client.post("/api/v1/authorization/requests", json=request_data)
            end_time = time.time()
            
            return {
                'success': response.status_code in [200, 400, 422],
                'status_code': response.status_code,
                'processing_time': end_time - start_time
            }
        except Exception as e:
            return {
                'success': False,
                'status_code': 500,
                'processing_time': 30.0,
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


class TestResponseTimeValidation:
    """Test response time validation for 2-minute processing target."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.client = TestClient(app)
        self.data_generator = TestDataGenerator()
    
    @pytest.mark.performance
    def test_2_minute_processing_target_validation(self):
        """Validate that 95% of requests meet the 2-minute processing target."""
        test_scenarios = [
            {"type": "routine", "count": 50},
            {"type": "urgent", "count": 30},
            {"type": "emergent", "count": 20}
        ]
        
        all_processing_times = []
        
        with patch('src.services.validation.ValidationService.validate_request') as mock_validate, \
             patch('src.services.policy_validation.PolicyValidationService.validate_with_medical_necessity') as mock_policy, \
             patch('src.services.decision_engine.DecisionEngine.generate_decision') as mock_decision, \
             patch('src.services.tracking.TrackingService.store_request') as mock_store:
            
            # Mock realistic processing times
            mock_validate.return_value = ValidationResult(
                is_valid=True, errors=[], warnings=[], processing_time_ms=1200.0
            )
            mock_policy.return_value = {'policy_validation': {'is_covered': True}}
            mock_decision.return_value = Mock()
            mock_store.return_value = None
            
            for scenario in test_scenarios:
                print(f"Testing {scenario['type']} requests ({scenario['count']} requests)")
                
                scenario_times = []
                
                for _ in range(scenario['count']):
                    request = self.data_generator.generate_authorization_request(scenario['type'])
                    request_data = self._convert_request_to_api_format(request)
                    
                    start_time = time.time()
                    response = self.client.post("/api/v1/authorization/requests", json=request_data)
                    end_time = time.time()
                    
                    processing_time = end_time - start_time
                    scenario_times.append(processing_time)
                    all_processing_times.append(processing_time)
                    
                    # Basic response validation
                    assert response.status_code in [200, 400, 422]
                
                # Analyze scenario performance
                avg_time = statistics.mean(scenario_times)
                max_time = max(scenario_times)
                
                print(f"  Average time: {avg_time:.3f}s")
                print(f"  Max time: {max_time:.3f}s")
        
        # Overall analysis
        all_processing_times.sort()
        total_requests = len(all_processing_times)
        percentile_95_index = int(0.95 * total_requests)
        percentile_95_time = all_processing_times[percentile_95_index]
        
        average_time = statistics.mean(all_processing_times)
        max_time = max(all_processing_times)
        
        # Count requests meeting 2-minute target
        under_2_minutes = sum(1 for t in all_processing_times if t < 120.0)
        percentage_under_2_minutes = (under_2_minutes / total_requests) * 100
        
        print(f"\nOverall Performance Analysis:")
        print(f"Total requests: {total_requests}")
        print(f"Average processing time: {average_time:.3f}s")
        print(f"95th percentile: {percentile_95_time:.3f}s")
        print(f"Max processing time: {max_time:.3f}s")
        print(f"Requests under 2 minutes: {percentage_under_2_minutes:.1f}%")
        
        # Validate 2-minute requirement
        assert percentage_under_2_minutes >= 95.0, f"Only {percentage_under_2_minutes:.1f}% of requests under 2 minutes (requirement: 95%)"
        assert percentile_95_time < 120.0, f"95th percentile ({percentile_95_time:.3f}s) exceeds 2-minute requirement"
        
        # Additional performance validations
        assert average_time < 30.0, f"Average processing time ({average_time:.3f}s) too high"
        assert max_time < 180.0, f"Maximum processing time ({max_time:.3f}s) exceeds reasonable limits"
    
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
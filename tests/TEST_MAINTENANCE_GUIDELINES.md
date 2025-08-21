# Test Maintenance Guidelines

This document provides comprehensive guidelines for maintaining and extending the Prior Authorization System test suite. Follow these procedures to ensure consistent test quality, organization, and compliance.

## Adding New Tests

### 1. Test File Organization

#### Naming Conventions
- **Test files**: Use `test_[functionality].py` format (e.g., `test_medical_codes.py`)
- **Test classes**: Use `Test[Component]` format (e.g., `TestMedicalCodeValidator`)
- **Test methods**: Use `test_[specific_behavior]` format (e.g., `test_validates_icd10_codes`)
- **Utility classes**: Avoid `Test*` prefix to prevent pytest collection (use `DataGenerator`, not `TestDataGenerator`)

#### Coverage-Focused Test Files
- **Extended tests**: Use `test_[module]_extended.py` for comprehensive coverage
- **Comprehensive tests**: Use `test_[module]_comprehensive.py` for API endpoint coverage
- **Enhanced tests**: Use `test_[module]_enhanced.py` for service layer coverage
- **Simple tests**: Use `test_[module]_simple.py` for basic functionality coverage

#### File Placement
```
tests/
├── test_[core_functionality].py     # Core system functionality
├── test_[api_component].py          # API-specific tests
├── test_[service_name].py           # Service-specific tests
├── utils/                           # Shared utilities only
│   ├── [utility_name].py           # No test_ prefix for utilities
└── integration_scripts/             # End-to-end integration tests
    └── test_[workflow_name].py      # Complete workflow tests
```

### 2. Test Structure Template

Use this template for new test files:

```python
"""
Test module for [Component/Functionality Name].

This module contains tests for [brief description of what is being tested].
Tests are organized by functionality and include unit, integration, and edge case scenarios.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from tests.utils.data_generator import DataGenerator
from tests.utils.mock_helpers import create_mock_response
from tests.utils.fixtures import db_session, auth_token

# Import the component being tested
from src.services.example_service import ExampleService


class TestExampleService:
    """Test suite for ExampleService functionality."""
    
    @pytest.fixture
    def service(self, db_session):
        """Create ExampleService instance for testing."""
        return ExampleService(db_session)
    
    @pytest.fixture
    def sample_data(self):
        """Generate sample test data."""
        generator = DataGenerator()
        return generator.generate_example_data()
    
    @pytest.mark.unit
    def test_basic_functionality(self, service, sample_data):
        """
        Test basic service functionality with valid input.
        
        Verifies that the service correctly processes valid input data
        and returns expected results.
        """
        # Arrange
        expected_result = "expected_value"
        
        # Act
        result = service.process_data(sample_data)
        
        # Assert
        assert result == expected_result
        assert service.is_valid_state()
    
    @pytest.mark.unit
    def test_error_handling(self, service):
        """
        Test service error handling with invalid input.
        
        Verifies that the service properly handles and reports errors
        for invalid input data.
        """
        # Arrange
        invalid_data = None
        
        # Act & Assert
        with pytest.raises(ValueError, match="Invalid input data"):
            service.process_data(invalid_data)
    
    @pytest.mark.integration
    @patch('src.services.example_service.external_api_call')
    def test_external_service_integration(self, mock_api, service, sample_data):
        """
        Test integration with external services.
        
        Verifies that the service correctly interacts with external APIs
        and handles responses appropriately.
        """
        # Arrange
        mock_api.return_value = create_mock_response({"status": "success"})
        
        # Act
        result = service.process_with_external_service(sample_data)
        
        # Assert
        assert result.status == "success"
        mock_api.assert_called_once_with(sample_data)
    
    @pytest.mark.security
    def test_phi_protection(self, service):
        """
        Test PHI protection and data sanitization.
        
        Verifies that the service properly protects PHI data and
        does not expose sensitive information.
        """
        # Arrange
        generator = DataGenerator()
        phi_data = generator.generate_patient_demographics()
        
        # Act
        result = service.sanitize_output(phi_data)
        
        # Assert
        assert "SYNTH_" in result.patient_id  # Ensure synthetic data
        assert result.ssn is None  # Ensure PHI is removed
        assert result.phone_number is None
```

### 3. Required Test Markers

Apply appropriate markers to all tests:

```python
@pytest.mark.unit          # Isolated unit tests
@pytest.mark.integration   # Multi-component integration tests
@pytest.mark.performance   # Performance and load tests
@pytest.mark.security      # Security and compliance tests
@pytest.mark.slow          # Tests taking > 30 seconds
@pytest.mark.coverage      # Tests specifically for coverage improvement
@pytest.mark.extended      # Extended test suites for comprehensive coverage
@pytest.mark.simple        # Simple tests for basic functionality coverage
```

### Coverage-Focused Test Categories

For the 30% coverage target achievement, use these specialized markers:

```python
@pytest.mark.coverage
@pytest.mark.simple
def test_basic_module_import():
    """Simple test to ensure module can be imported and basic functionality works."""
    pass

@pytest.mark.coverage
@pytest.mark.extended
def test_comprehensive_functionality():
    """Extended test covering multiple code paths and scenarios."""
    pass
```

### 4. Documentation Requirements

Every test must include:
- **Module docstring**: Explains what the module tests
- **Class docstring**: Describes the test suite purpose
- **Method docstrings**: Explains what each test validates
- **Inline comments**: Clarify complex test logic

## Test Data Management

### 1. Using DataGenerator

Always use the DataGenerator for creating test data:

```python
from tests.utils.data_generator import DataGenerator

def test_with_synthetic_data():
    """Test using properly generated synthetic data."""
    generator = DataGenerator()
    
    # Generate different types of test data
    patient = generator.generate_patient_demographics()
    medical_codes = generator.generate_medical_codes("imaging")
    clinical_notes = generator.generate_clinical_notes("back_pain")
    
    # All generated data includes synthetic markers
    assert patient.patient_id.startswith("SYNTH_PAT_")
    assert all(code.code_type in ["ICD10", "CPT"] for code in medical_codes)
```

### 2. PHI Compliance Validation

Before adding any test data, validate PHI compliance:

```python
from tests.utils.phi_compliance import check_string_for_phi, validate_test_data

def test_new_functionality():
    """Test with PHI-compliant data."""
    test_data = {
        "patient_name": "SYNTH_John_Doe_TEST",
        "patient_id": "SYNTH_PAT_1234567_TEST",
        "diagnosis": "M54.5"  # ICD-10 code for low back pain
    }
    
    # Validate PHI compliance
    violations = validate_test_data(test_data)
    assert len(violations) == 0, f"PHI violations found: {violations}"
    
    # Proceed with test logic
    result = process_patient_data(test_data)
    assert result.is_valid()
```

### 3. Test Data Categories

Organize test data by scenario type:

```python
class TestDataScenarios:
    """Standard test data scenarios for consistent testing."""
    
    @staticmethod
    def routine_imaging_request():
        """Standard imaging request with no complications."""
        return {
            "procedure_code": "72148",  # MRI lumbar spine
            "diagnosis_code": "M54.5",  # Low back pain
            "urgency": "routine",
            "prior_auth_required": True
        }
    
    @staticmethod
    def emergency_procedure():
        """Emergency procedure requiring immediate approval."""
        return {
            "procedure_code": "70450",  # CT head without contrast
            "diagnosis_code": "G93.1",  # Anoxic brain damage
            "urgency": "emergency",
            "prior_auth_required": False
        }
    
    @staticmethod
    def invalid_codes():
        """Invalid medical codes for error testing."""
        return {
            "procedure_code": "99999",  # Invalid CPT code
            "diagnosis_code": "Z99.99", # Invalid ICD-10 code
            "urgency": "invalid_urgency"
        }
```

## Mock Management

### 1. Using Mock Helpers

Leverage shared mock utilities for consistency:

```python
from tests.utils.mock_helpers import (
    create_mock_database_response,
    create_mock_api_response,
    create_mock_llm_response,
    simulate_service_failure
)

@patch('src.services.external_service.api_call')
def test_external_service_integration(mock_api):
    """Test external service integration with proper mocking."""
    # Use helper to create realistic mock response
    mock_api.return_value = create_mock_api_response(
        status_code=200,
        data={"authorization": "approved", "reason": "meets_criteria"}
    )
    
    result = service.check_authorization(request_data)
    assert result.status == "approved"
```

### 2. Mock Configuration Patterns

Follow these patterns for different mock types:

```python
# Database mocks
@patch('src.database.connection.get_session')
def test_database_operation(mock_session):
    mock_session.return_value = create_mock_database_response(
        query_result=[{"id": 1, "status": "active"}]
    )

# External API mocks
@patch('requests.post')
def test_api_call(mock_post):
    mock_post.return_value = create_mock_api_response(
        status_code=200,
        json_data={"result": "success"}
    )

# Async service mocks
@patch('src.services.async_service.process_async')
async def test_async_operation(mock_async):
    mock_async.return_value = AsyncMock(return_value="completed")
```

### 3. Error Simulation

Test error conditions with realistic failure scenarios:

```python
def test_service_failure_handling():
    """Test handling of external service failures."""
    with patch('src.services.external_service.api_call') as mock_api:
        # Simulate different failure types
        mock_api.side_effect = simulate_service_failure(
            failure_type="timeout",
            retry_count=3
        )
        
        with pytest.raises(ServiceTimeoutError):
            service.process_request(test_data)
```

## Performance Test Guidelines

### 1. Performance Test Structure

```python
@pytest.mark.performance
@pytest.mark.slow
def test_concurrent_request_handling():
    """
    Test system performance under concurrent load.
    
    Validates that the system can handle 1000+ concurrent requests
    with 95% completing within 2 minutes.
    """
    import asyncio
    import time
    from tests.utils.performance_helpers import measure_response_times
    
    async def simulate_request():
        start_time = time.time()
        result = await service.process_request_async(test_data)
        end_time = time.time()
        return end_time - start_time, result.status
    
    # Run concurrent requests
    tasks = [simulate_request() for _ in range(1000)]
    results = await asyncio.gather(*tasks)
    
    # Analyze performance
    response_times = [r[0] for r in results]
    success_count = sum(1 for r in results if r[1] == "success")
    
    # Validate performance requirements
    assert success_count >= 950  # 95% success rate
    assert sum(1 for t in response_times if t <= 120) >= 950  # 95% under 2 minutes
```

### 2. Performance Monitoring

```python
from tests.utils.performance_helpers import PerformanceMonitor

@pytest.mark.performance
def test_memory_usage():
    """Test memory usage under load."""
    monitor = PerformanceMonitor()
    
    with monitor.track_memory():
        # Perform memory-intensive operations
        for i in range(1000):
            result = service.process_large_dataset(test_data)
    
    # Validate memory usage
    assert monitor.peak_memory_mb < 500  # Under 500MB peak
    assert monitor.memory_leak_detected == False
```

## Updating Existing Tests

### 1. Modernization Checklist

When updating existing tests, ensure:

- [ ] **Pydantic V2 patterns**: Use `@field_validator` instead of `@validator`
- [ ] **ConfigDict usage**: Replace class-based config with `model_config = ConfigDict()`
- [ ] **Import paths**: Update imports for moved utilities
- [ ] **Marker application**: Add appropriate pytest markers
- [ ] **Documentation**: Add/update docstrings
- [ ] **PHI compliance**: Validate all test data is synthetic

### 2. Migration Template

```python
# OLD PATTERN (Pydantic V1)
from pydantic import BaseModel, validator

class OldModel(BaseModel):
    value: str
    
    @validator('value')
    def validate_value(cls, v):
        return v.upper()
    
    class Config:
        extra = "forbid"

# NEW PATTERN (Pydantic V2)
from pydantic import BaseModel, field_validator, ConfigDict

class NewModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    value: str
    
    @field_validator('value')
    @classmethod
    def validate_value(cls, v: str) -> str:
        return v.upper()
```

### 3. Test Refactoring Guidelines

When refactoring tests:

1. **Preserve test intent**: Keep the same test coverage and validation logic
2. **Update patterns**: Modernize deprecated patterns and imports
3. **Improve documentation**: Add clear docstrings and comments
4. **Enhance assertions**: Use more specific assertion messages
5. **Add markers**: Apply appropriate pytest markers

## Continuous Integration Integration

### 1. CI Test Categories

Organize tests for different CI stages:

```bash
# Quick validation (< 5 minutes)
python -m pytest tests/ -m "unit and not slow" --maxfail=5

# Integration testing (< 15 minutes)  
python -m pytest tests/ -m "integration and not slow" --maxfail=3

# Full test suite (< 30 minutes)
python -m pytest tests/ --cov=src --cov-fail-under=90

# Performance validation (nightly)
python -m pytest tests/ -m performance --timeout=3600
```

### 2. Test Reporting

Configure test reporting for CI:

```bash
# Generate JUnit XML for CI reporting
python -m pytest tests/ --junitxml=test-results.xml

# Generate coverage reports
python -m pytest tests/ --cov=src --cov-report=xml --cov-report=html

# Generate performance reports
python -m pytest tests/ -m performance --benchmark-json=performance-results.json
```

## Quality Assurance

### 1. Pre-commit Checklist

Before committing test changes:

- [ ] All tests pass locally
- [ ] Coverage meets 90% threshold
- [ ] PHI compliance validation passes
- [ ] Test documentation is complete
- [ ] Appropriate markers are applied
- [ ] Mock configurations are realistic

### 2. Code Review Guidelines

When reviewing test code:

- **Test coverage**: Verify new functionality has appropriate test coverage
- **PHI compliance**: Ensure all test data is synthetic and properly marked
- **Mock realism**: Check that mocks accurately represent real service behavior
- **Performance impact**: Assess if new tests significantly impact execution time
- **Documentation quality**: Verify tests are well-documented and understandable

### 3. Maintenance Schedule

Regular maintenance tasks:

- **Weekly**: Review test execution times and optimize slow tests
- **Monthly**: Update test data scenarios and medical codes
- **Quarterly**: Review and update mock configurations
- **Annually**: Comprehensive PHI compliance audit and test suite review

## Common Patterns and Examples

### 1. Database Testing Pattern

```python
@pytest.mark.integration
def test_database_transaction(db_session):
    """Test database operations with proper transaction handling."""
    # Arrange
    test_data = DataGenerator().generate_patient_data()
    
    # Act
    with db_session.begin():
        result = service.save_patient(test_data)
        db_session.flush()  # Ensure data is written
        
        # Verify within transaction
        saved_patient = service.get_patient(result.id)
        assert saved_patient.patient_id == test_data.patient_id
    
    # Verify after transaction commit
    final_patient = service.get_patient(result.id)
    assert final_patient is not None
```

### 2. Async Testing Pattern

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_async_workflow():
    """Test asynchronous workflow processing."""
    # Arrange
    request_data = DataGenerator().generate_auth_request()
    
    # Act
    async with service.create_session() as session:
        result = await service.process_async(request_data, session)
        await session.commit()
    
    # Assert
    assert result.status == "completed"
    assert result.processing_time < 120  # Under 2 minutes
```

### 3. Security Testing Pattern

```python
@pytest.mark.security
def test_access_control(auth_token):
    """Test role-based access control enforcement."""
    # Test with different user roles
    test_cases = [
        ("admin", True),
        ("provider", True),
        ("patient", False),
        ("anonymous", False)
    ]
    
    for role, should_succeed in test_cases:
        token = create_auth_token(role=role)
        
        if should_succeed:
            result = service.access_protected_resource(token)
            assert result.status == "success"
        else:
            with pytest.raises(UnauthorizedError):
                service.access_protected_resource(token)
```

This comprehensive guide ensures consistent, high-quality test maintenance and development practices across the Prior Authorization System test suite.
# Test Coverage 30% Target - Design Document

## Overview

This design outlines a strategic approach to increase test coverage from 24% to 30% by targeting high-impact modules and implementing focused test coverage. The approach prioritizes modules with large codebases and low coverage to maximize the coverage gain with minimal effort.

## Architecture

### Coverage Analysis Strategy

The design follows a data-driven approach based on the existing coverage report:

1. **Current State**: 24.27% coverage (3,811 statements covered out of 15,704 total)
2. **Target State**: 30% coverage (4,711 statements covered)
3. **Gap**: 900 additional statements need to be covered

### Module Prioritization Matrix

Based on the coverage report analysis, modules are prioritized using this formula:
```
Priority Score = (Statement Count × (100 - Current Coverage %)) / 100
```

High-priority targets identified:
- `src/services/decision_engine.py`: ~793 statements at 14% coverage (Priority: 682)
- `src/api/llm_decisions.py`: ~501 statements at 28% coverage (Priority: 361)
- `src/api/intake.py`: ~384 statements at 21% coverage (Priority: 303)
- `src/services/validation.py`: ~190 statements at 20% coverage (Priority: 152)
- `src/services/tracking.py`: ~267 statements at 19% coverage (Priority: 216)

## Components and Interfaces

### Test File Organization

```
tests/
├── test_coverage_30_percent/
│   ├── test_decision_engine_extended.py    # Target: +150 statements
│   ├── test_llm_decisions_api.py          # Target: +120 statements
│   ├── test_intake_api_extended.py        # Target: +100 statements
│   ├── test_validation_service_extended.py # Target: +80 statements
│   ├── test_tracking_service_extended.py   # Target: +90 statements
│   ├── test_medical_codes_extended.py      # Target: +100 statements
│   ├── test_external_services_extended.py  # Target: +80 statements
│   ├── test_database_operations.py         # Target: +70 statements
│   ├── test_authentication_flows.py        # Target: +60 statements
│   └── test_configuration_management.py    # Target: +40 statements
└── coverage_reports/
    ├── baseline_24_percent.json
    ├── incremental_progress.json
    └── final_30_percent.json
```

### Testing Strategy by Module Type

#### 1. Decision Engine Testing
- **Focus**: Authorization decision logic, policy validation, medical necessity evaluation
- **Approach**: Mock external dependencies, test decision paths, validate reasoning generation
- **Coverage Target**: Increase from 14% to 35% (+150 statements)

#### 2. API Endpoint Testing
- **Focus**: Request processing, validation, response generation, error handling
- **Approach**: Use FastAPI test client, mock service dependencies, test all HTTP methods
- **Coverage Target**: Increase LLM Decisions API from 28% to 52% (+120 statements)

#### 3. Service Layer Testing
- **Focus**: Business logic, data processing, external service integration
- **Approach**: Mock databases and external APIs, test service methods, validate error handling
- **Coverage Target**: Increase Validation Service from 20% to 62% (+80 statements)

#### 4. Database Operations Testing
- **Focus**: CRUD operations, transaction handling, connection management
- **Approach**: Use in-memory SQLite for tests, test repository patterns, validate data integrity
- **Coverage Target**: Add 70 new statements across database modules

## Data Models

### Test Data Structures

```python
# Test fixtures for consistent data across tests
@pytest.fixture
def sample_authorization_request():
    return {
        "patient_id": "test-patient-123",
        "procedure_code": "70553",
        "diagnosis_code": "M25.511",
        "provider_id": "test-provider-456"
    }

@pytest.fixture
def mock_policy_config():
    return {
        "policy_id": "test-policy-001",
        "coverage_rules": [...],
        "medical_necessity_criteria": [...]
    }
```

### Coverage Tracking Models

```python
class CoverageProgress:
    module_name: str
    baseline_coverage: float
    current_coverage: float
    statements_added: int
    target_coverage: float
    
class CoverageReport:
    total_coverage: float
    modules: List[CoverageProgress]
    timestamp: datetime
    test_files_added: List[str]
```

## Error Handling

### Test Failure Management
1. **Import Errors**: Graceful handling of missing dependencies with skip decorators
2. **Mock Failures**: Fallback mock configurations for complex dependencies
3. **Async Test Issues**: Proper event loop management and cleanup
4. **Database Test Errors**: Automatic rollback and cleanup mechanisms

### Coverage Measurement Errors
1. **Missing Modules**: Skip coverage for modules that can't be imported
2. **Calculation Errors**: Validate coverage percentages and provide warnings
3. **Report Generation**: Fallback to basic coverage metrics if detailed reports fail

## Testing Strategy

### Phase 1: High-Impact Module Testing (Target: +400 statements)
1. **Decision Engine Extended Testing**
   - Test all decision paths (approve/deny/more-info)
   - Add policy validation scenarios
   - Test medical necessity evaluation logic
   - Mock LLM integration and test fallback logic

2. **API Endpoint Comprehensive Testing**
   - Test LLM Decisions API with various request types
   - Add Intake API validation and processing tests
   - Test Medical Codes API search and validation functionality
   - Add comprehensive error handling tests

### Phase 2: Service Layer Deep Testing (Target: +300 statements)
1. **Validation Service Extended Testing**
   - Test all medical code validation scenarios
   - Add business rule validation tests
   - Test field relationship validation
   - Add comprehensive error and warning scenarios

2. **Tracking Service Extended Testing**
   - Test request tracking and status updates
   - Add audit trail generation tests
   - Test notification trigger logic
   - Add database operation tests

### Phase 3: Integration and Support Testing (Target: +200 statements)
1. **External Services Integration**
   - Mock CMS API integration tests
   - Test medical code lookup services
   - Add authentication flow tests
   - Test configuration management

2. **Database Operations**
   - Test repository patterns and CRUD operations
   - Add transaction handling tests
   - Test connection pooling and management
   - Add data migration and backup tests

### Implementation Approach

#### Test Development Pattern
```python
class TestModuleExtended:
    """Extended test coverage for [Module Name]"""
    
    def setup_method(self):
        """Setup mocks and test data"""
        pass
    
    def test_core_functionality(self):
        """Test main business logic paths"""
        pass
    
    def test_error_scenarios(self):
        """Test error handling and edge cases"""
        pass
    
    def test_integration_points(self):
        """Test interactions with other modules"""
        pass
```

#### Coverage Measurement Workflow
1. Run baseline coverage measurement
2. Implement test file for target module
3. Measure incremental coverage improvement
4. Validate coverage gain meets target
5. Move to next priority module
6. Generate final coverage report

### Quality Assurance

#### Test Quality Metrics
- All new tests must pass consistently (100% pass rate)
- Test execution time must remain under 60 seconds total
- Each test file must contribute at least 40 statements of coverage
- Mock usage must be consistent and maintainable

#### Coverage Validation
- Module-level coverage improvements must be measurable
- Overall coverage must reach exactly 30% or higher
- No regression in existing test functionality
- Coverage reports must be generated automatically

## Performance Considerations

### Test Execution Optimization
- Use pytest-xdist for parallel test execution where possible
- Implement efficient fixture setup and teardown
- Use in-memory databases for database tests
- Mock external services to avoid network delays

### Memory Management
- Clean up test data after each test method
- Use context managers for resource management
- Implement proper async resource cleanup
- Monitor memory usage during test execution

## Security Considerations

### Test Data Security
- Use synthetic test data only (no real PHI)
- Implement proper test data cleanup
- Secure test database connections
- Validate that test mocks don't expose sensitive data

### Authentication Testing
- Test OAuth2 flows with mock tokens
- Validate role-based access controls
- Test security monitoring integration
- Ensure test authentication doesn't use production credentials
# Test Execution and Maintenance Guide

## Overview

This guide provides comprehensive instructions for executing tests, maintaining test quality, and troubleshooting common issues in the Prior Authorization System test suite.

## Test Execution Commands

### Basic Test Execution

```bash
# Run all tests
python -m pytest

# Run tests with coverage
python -m pytest --cov=src --cov-report=html

# Run specific test categories
python -m pytest -m unit          # Unit tests only
python -m pytest -m integration   # Integration tests only
python -m pytest -m fast          # Fast tests only
python -m pytest -m slow          # Slow tests only

# Run coverage-focused tests (30% target achievement)
python -m pytest tests/test_zero_coverage_modules.py
python -m pytest tests/test_api_coverage_simple.py
python -m pytest tests/test_services_simple.py

# Run extended test suites
python -m pytest tests/test_*_extended.py
python -m pytest tests/test_*_comprehensive.py
python -m pytest tests/test_*_enhanced.py
```

### Integration Tests

```bash
# Run all integration tests
python -m pytest tests/integration_scripts/

# Run specific integration test
python -m pytest tests/integration_scripts/test_automatic_decision.py

# Run integration tests with verbose output
python -m pytest tests/integration_scripts/ -v
```

### Performance Testing

```bash
# Run performance tests
python -m pytest -m performance

# Run with timing information
python -m pytest --durations=10

# Run fast tests only (under 5 seconds)
python -m pytest -m fast --timeout=5
```

### Coverage Analysis

```bash
# Generate HTML coverage report
python -m pytest --cov=src --cov-report=html:htmlcov

# Generate terminal coverage report
python -m pytest --cov=src --cov-report=term-missing

# Set coverage failure threshold (current target: 30%)
python -m pytest --cov=src --cov-fail-under=24

# Run coverage validation for 30% target
python scripts/validate_final_coverage.py

# Generate coverage improvement report
python scripts/generate_final_coverage_report.py

# Track coverage progress
python tests/coverage_tracking/coverage_cli.py --report
```

## Test Organization

### Test Directory Structure

```
tests/
├── integration_scripts/     # End-to-end integration tests
├── utils/                   # Test utilities and helpers
├── quality_assurance/       # Test quality monitoring
├── test_*.py               # Unit test files
├── conftest.py             # Pytest configuration and fixtures
└── pytest.ini             # Pytest settings
```

### Test Categories and Markers

- **unit**: Isolated unit tests for individual functions
- **integration**: Tests verifying component interactions
- **performance**: Performance and load testing
- **security**: Security and compliance testing
- **slow**: Tests taking longer than 30 seconds
- **fast**: Tests completing within 5 seconds

## Test Maintenance Procedures

### Adding New Tests

1. **Create test file** following naming convention `test_<module_name>.py`
2. **Use appropriate markers** to categorize tests
3. **Follow test naming convention** `test_<functionality>_<scenario>`
4. **Add docstrings** explaining test purpose and scenarios
5. **Update coverage targets** if adding new modules

Example test structure:
```python
import pytest
from unittest.mock import Mock, patch

class TestNewFeature:
    """Test suite for new feature functionality."""
    
    @pytest.mark.unit
    def test_feature_success_scenario(self):
        """Test successful execution of feature."""
        # Test implementation
        pass
    
    @pytest.mark.integration
    async def test_feature_integration(self):
        """Test feature integration with other components."""
        # Test implementation
        pass
```

### Updating Existing Tests

1. **Check test relevance** - ensure tests still validate current functionality
2. **Update mock configurations** to match current system behavior
3. **Verify test assertions** align with expected outcomes
4. **Update test documentation** to reflect changes
5. **Run full test suite** to ensure no regressions

### Test Quality Monitoring

```bash
# Run test quality checks
python -m pytest tests/quality_assurance/test_quality_metrics.py

# Monitor test performance
python tests/quality_assurance/coverage_monitor.py

# Run automated maintenance
python tests/quality_assurance/automated_maintenance.py
```

## Troubleshooting Common Issues

### Test Collection Issues

**Problem**: Tests not being collected
```bash
# Check test discovery
python -m pytest --collect-only

# Verify file naming
ls tests/test_*.py

# Check import errors
python -m pytest --tb=short
```

**Solution**: Ensure test files follow naming convention and have no syntax errors.

### Import Errors

**Problem**: Module import failures
```bash
# Check Python path
python -c "import sys; print(sys.path)"

# Verify module structure
python -c "from src.module import function"
```

**Solution**: Update imports to match current module structure.

### Database Test Issues

**Problem**: SQLite threading errors
```bash
# Use in-memory database for tests
pytest -s tests/test_database.py
```

**Solution**: Configure test database with proper threading settings:
```python
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False}
)
```

### Async Test Problems

**Problem**: Async tests hanging or failing
```bash
# Run with asyncio debug mode
pytest --asyncio-mode=auto -s
```

**Solution**: Ensure proper async/await patterns and cleanup:
```python
@pytest.mark.asyncio
async def test_async_function():
    async with AsyncClient() as client:
        response = await client.get("/endpoint")
        assert response.status_code == 200
```

### Coverage Issues

**Problem**: Low coverage or missing files
```bash
# Check coverage configuration
cat pytest.ini | grep cov

# Verify source paths
python -m pytest --cov=src --cov-report=term
```

**Solution**: Update coverage configuration and add missing tests.

## Performance Optimization

### Fast Test Execution

1. **Use in-memory databases** for unit tests
2. **Optimize fixture setup/teardown**
3. **Implement efficient mocks**
4. **Run tests in parallel** where safe
5. **Use test markers** for selective execution

### Memory Management

```python
# Efficient test data generation
@pytest.fixture
def bulk_test_data():
    """Generate test data efficiently."""
    return [create_test_record(i) for i in range(100)]

# Proper cleanup
@pytest.fixture
def database_session():
    session = create_session()
    yield session
    session.close()
```

## Continuous Integration

### Pre-commit Hooks

```bash
# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Run hooks manually
pre-commit run --all-files
```

### CI Pipeline Configuration

```yaml
# Example GitHub Actions workflow
name: Test Suite
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.11
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        run: pytest --cov=src --cov-fail-under=90
```

## Quality Metrics

### Coverage Targets

- **Overall**: 90% minimum
- **Critical Components**: 95% minimum
- **API Endpoints**: 90% minimum
- **Business Logic**: 95% minimum

### Performance Targets

- **Unit Tests**: < 30 seconds total
- **Integration Tests**: < 5 minutes total
- **Full Suite**: < 10 minutes total
- **Individual Tests**: < 5 seconds each

### Reliability Targets

- **Pass Rate**: 100% for stable tests
- **Flaky Test Rate**: < 1%
- **Test Maintenance**: Monthly review cycle

## Documentation Standards

### Test Documentation Requirements

1. **Test file docstrings** explaining module purpose
2. **Test class docstrings** describing test suite scope
3. **Test method docstrings** explaining specific scenarios
4. **Inline comments** for complex test logic
5. **README updates** for new test categories

### Example Documentation

```python
"""
Tests for authorization decision engine.

This module tests the core decision-making logic for prior authorization
requests, including policy validation, medical necessity checks, and
decision generation.
"""

class TestDecisionEngine:
    """Test suite for authorization decision engine."""
    
    def test_approve_valid_request(self):
        """
        Test approval of valid authorization request.
        
        Scenario: Request meets all policy requirements and medical necessity
        Expected: Decision status is 'approved' with authorization number
        """
        # Test implementation
```

## Support and Resources

### Getting Help

- **Test Issues**: Check troubleshooting section above
- **Coverage Questions**: Review coverage analysis tools
- **Performance Problems**: Use performance profiling tools
- **Documentation**: Refer to test-specific README files

### Useful Commands Reference

```bash
# Quick test validation
pytest --collect-only -q

# Coverage summary
pytest --cov=src --cov-report=term-missing

# Performance analysis
pytest --durations=0

# Parallel execution
pytest -n auto

# Debug mode
pytest -s --pdb

# Specific test pattern
pytest -k "test_decision"
```

---

This guide should be updated regularly as the test suite evolves and new patterns emerge.
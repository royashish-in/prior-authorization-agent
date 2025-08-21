# Coverage Tracking Infrastructure

This directory contains the coverage tracking infrastructure for the 30% coverage target project. The goal is to systematically increase test coverage from the current baseline to 30% through targeted testing of high-impact modules.

## Overview

The coverage tracking system provides:

- **Baseline Tracking**: Establish and maintain coverage baselines
- **Incremental Progress**: Measure coverage improvements after adding tests
- **Automated Reporting**: Generate comprehensive coverage reports
- **Target Validation**: Verify when the 30% target is reached
- **Test Fixtures**: Standardized test data and mocks for consistent testing

## Quick Start

### 1. Establish Baseline (Already Done)

```bash
python tests/coverage_tracking/coverage_cli.py baseline
```

This creates a baseline snapshot at `tests/coverage_reports/baseline_24_percent.json`.

### 2. Check Current Status

```bash
python tests/coverage_tracking/coverage_cli.py status
```

### 3. Measure Progress After Adding Tests

```bash
python tests/coverage_tracking/coverage_cli.py progress --test-file "test_decision_engine_extended.py"
```

### 4. Generate Comprehensive Report

```bash
python tests/coverage_tracking/coverage_cli.py report
```

### 5. Validate Target Achievement

```bash
python tests/coverage_tracking/coverage_cli.py validate
```

## Components

### 1. Baseline Tracker (`baseline_tracker.py`)

Core functionality for measuring and tracking coverage:

- `CoverageTracker`: Main tracking utility
- `CoverageSnapshot`: Point-in-time coverage data
- `ModuleCoverage`: Per-module coverage information

**Key Methods:**
- `establish_baseline()`: Create initial coverage baseline
- `measure_incremental_progress()`: Track progress after test additions
- `validate_target_reached()`: Check if 30% target is met

### 2. Test Fixtures (`test_fixtures.py`)

Standardized test data and mocks for consistent coverage testing:

- `CoverageTestFixtures`: Centralized fixture provider
- `CoverageTestScenario`: Structured test scenarios
- Comprehensive medical codes, patient demographics, and mock configurations

**Key Features:**
- Decision engine test scenarios (5 scenarios covering different paths)
- API endpoint test scenarios (3 scenarios for different endpoints)
- Service layer test scenarios (2 scenarios for validation and tracking)
- Standardized mock configurations for all services

### 3. Reporting (`reporting.py`)

Advanced reporting and progress tracking:

- `CoverageReporter`: Generate detailed reports
- `CoverageImprovementReport`: Comprehensive improvement analysis
- `ModuleTargetProgress`: Per-module progress tracking

**Key Features:**
- Module-specific progress tracking with targets
- Recommendations based on current progress
- Next target identification
- Markdown and JSON report generation

### 4. CLI Interface (`coverage_cli.py`)

Command-line interface for easy access to all functionality:

```bash
# Available commands
python tests/coverage_tracking/coverage_cli.py baseline   # Establish baseline
python tests/coverage_tracking/coverage_cli.py progress   # Measure progress
python tests/coverage_tracking/coverage_cli.py report     # Generate report
python tests/coverage_tracking/coverage_cli.py status     # Quick status
python tests/coverage_tracking/coverage_cli.py validate   # Check target
```

## Module Targets

Based on the design document, the following modules are prioritized for coverage improvement:

| Priority | Module | Target Increase | Current Coverage |
|----------|--------|----------------|------------------|
| 1 | `src.services.decision_engine` | +150 statements | 14% |
| 2 | `src.api.llm_decisions` | +120 statements | 28% |
| 3 | `src.api.intake` | +100 statements | 21% |
| 4 | `src.services.validation` | +80 statements | 20% |
| 5 | `src.services.tracking` | +90 statements | 19% |
| 6 | `src.api.medical_codes` | +100 statements | 27% |
| 7 | `src.services.external_services` | +80 statements | 35% |
| 8 | `src.database.models` | +70 statements | 65% |
| 9 | `src.auth.oauth2` | +60 statements | 19% |
| 10 | `src.core.config` | +40 statements | 100% |

## Usage Patterns

### For Test Development

1. **Before adding tests**: Check current status
   ```bash
   python tests/coverage_tracking/coverage_cli.py status
   ```

2. **After adding a test file**: Measure progress
   ```bash
   python tests/coverage_tracking/coverage_cli.py progress --test-file "test_new_coverage.py"
   ```

3. **Use standardized fixtures**: Import from `test_fixtures.py`
   ```python
   from tests.coverage_tracking.test_fixtures import CoverageTestFixtures
   
   def test_with_coverage_fixtures(coverage_test_fixtures):
       scenarios = coverage_test_fixtures.get_decision_engine_test_scenarios()
       # Use scenarios for comprehensive testing
   ```

### For Progress Tracking

1. **Generate weekly reports**:
   ```bash
   python tests/coverage_tracking/coverage_cli.py report
   ```

2. **Monitor specific modules**:
   Check the generated reports for module-specific progress.

3. **Validate milestones**:
   ```bash
   python tests/coverage_tracking/coverage_cli.py validate
   ```

## File Structure

```
tests/coverage_tracking/
├── __init__.py                 # Package initialization
├── README.md                   # This documentation
├── baseline_tracker.py         # Core tracking functionality
├── test_fixtures.py            # Standardized test fixtures
├── reporting.py                # Advanced reporting
└── coverage_cli.py             # Command-line interface

tests/coverage_reports/         # Generated reports
├── baseline_24_percent.json    # Initial baseline
├── incremental_*.json          # Progress snapshots
└── coverage_report_*.json      # Comprehensive reports
```

## Integration with Existing Tests

The coverage tracking infrastructure integrates seamlessly with the existing test suite:

1. **Pytest Integration**: Uses standard pytest and coverage.py
2. **Existing Fixtures**: Extends existing `conftest.py` fixtures
3. **Mock Compatibility**: Works with existing mock patterns
4. **Performance Optimized**: Designed for fast execution

## Best Practices

### When Adding Coverage Tests

1. **Use standardized fixtures** from `test_fixtures.py`
2. **Target specific modules** based on priority list
3. **Measure progress** after each test file addition
4. **Aim for meaningful coverage** - test actual business logic paths
5. **Keep tests fast** - use mocks for external dependencies

### When Measuring Progress

1. **Run measurements regularly** to track incremental progress
2. **Document test files added** using the `--test-file` parameter
3. **Generate reports weekly** to track overall progress
4. **Focus on high-impact modules** first

### Performance Considerations

- Tests should complete within 60 seconds total
- Use in-memory databases for database tests
- Mock external services to avoid network delays
- Optimize fixture setup and teardown

## Troubleshooting

### Common Issues

1. **Coverage measurement fails**:
   - Ensure all dependencies are installed
   - Check that `coverage.json` is generated
   - Verify pytest configuration

2. **Baseline not found**:
   - Run `baseline` command first
   - Check `tests/coverage_reports/` directory exists

3. **Tests timeout**:
   - Optimize test fixtures
   - Use mocks for slow operations
   - Consider parallel test execution

### Getting Help

1. Check the test infrastructure tests: `tests/test_coverage_infrastructure.py`
2. Review existing test patterns in `tests/conftest.py`
3. Examine the CLI help: `python tests/coverage_tracking/coverage_cli.py --help`

## Current Status

- **Baseline Established**: ✅ 16.09% coverage (2,527/15,704 statements)
- **Target**: 30% coverage (~4,711 statements)
- **Remaining**: ~2,184 additional statements needed
- **Infrastructure**: ✅ Complete and tested
- **Ready for**: Test development and coverage improvement

## Next Steps

1. Begin implementing high-priority test files:
   - `tests/test_decision_engine_extended.py` (Priority 1)
   - `tests/test_llm_decisions_api.py` (Priority 2)
   - `tests/test_intake_api_extended.py` (Priority 3)

2. Use the CLI to track progress after each test file

3. Generate reports regularly to monitor progress toward 30% target
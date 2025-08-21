"""
Test data generator utilities - DEPRECATED

This module has been moved to tests/utils/data_generator.py
Import from the new location instead:

    from tests.utils.data_generator import DataGenerator, MedicalScenario
    from tests.utils.data_generator import (
        create_test_request_batch,
        create_validation_test_cases,
        create_policy_test_scenarios
    )
"""

# Import from new location for backward compatibility
from tests.utils.data_generator import (
    DataGenerator,
    MedicalScenario,
    create_test_request_batch,
    create_validation_test_cases,
    create_policy_test_scenarios
)

# Deprecated - use imports from tests.utils.data_generator instead
__all__ = [
    'DataGenerator',
    'MedicalScenario',
    'create_test_request_batch',
    'create_validation_test_cases',
    'create_policy_test_scenarios'
]
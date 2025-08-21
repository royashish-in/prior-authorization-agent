# PHI Compliance Guidelines for Test Data

## Overview

This document provides guidelines for maintaining HIPAA compliance in test data for the Prior Authorization System. All test data must be synthetic and clearly marked to prevent any real Protected Health Information (PHI) from entering our test suite.

## ⚠️ CRITICAL REQUIREMENTS

### 1. NO REAL PHI EVER
- **NEVER** use real patient names, SSNs, phone numbers, addresses, or any other real PHI
- **NEVER** copy data from real medical records or systems
- **NEVER** use real medical record numbers (MRNs) or patient identifiers

### 2. ALL TEST DATA MUST BE SYNTHETIC
- Use clearly synthetic identifiers with markers like `SYNTH_`, `TEST_`, `MOCK_`
- Include explicit synthetic markers in clinical notes: `[SYNTHETIC TEST DATA]`
- Use obviously fake domains for email addresses: `@synthetic-test.test`

### 3. VALIDATION IS MANDATORY
- All new test data must pass PHI compliance validation
- Use the provided PHI compliance tools before adding new test data
- Run `python validate_phi_compliance.py` to check compliance

## Tools and Utilities

### DataGenerator Class
Located in `tests/utils/data_generator.py`

```python
from tests.utils.data_generator import DataGenerator

# Generate synthetic patient data
generator = DataGenerator()
patient = generator.generate_patient_demographics()
# Results in: SYNTH_PAT_1234567_TEST

# Generate synthetic authorization request
request = generator.generate_authorization_request()
# Includes synthetic markers throughout
```

### PHI Compliance Checker
Located in `tests/utils/phi_compliance.py`

```python
from tests.utils.phi_compliance import PHIComplianceChecker, check_string_for_phi

# Check a string for PHI violations
violations = check_string_for_phi("Patient John Smith", "clinical_notes")

# Check an object for PHI violations
checker = PHIComplianceChecker()
violations = checker.check_object(patient_data, "patient")

# Generate compliance report
report = checker.generate_compliance_report([data1, data2, data3])
```

## Synthetic Data Patterns

### Patient Identifiers
```python
# ✅ CORRECT - Clearly synthetic
patient_id = "SYNTH_PAT_1234567_TEST"
insurance_id = "SYNTH_INS_7654321_TEST"
member_id = "SYNTH_MEM_9876543_TEST"

# ❌ WRONG - Could be real
patient_id = "12345"
insurance_id = "ABC123456"
member_id = "MEM789"
```

### Clinical Notes
```python
# ✅ CORRECT - Marked as synthetic
clinical_notes = """
[SYNTHETIC TEST DATA] Patient reports persistent shoulder pain for 6 weeks 
following sports injury. Conservative treatment with physical therapy has 
provided limited relief. [This is synthetic test data for system testing only]
"""

# ❌ WRONG - No synthetic markers
clinical_notes = "Patient John Smith has shoulder pain after car accident"
```

### Email Addresses
```python
# ✅ CORRECT - Obviously synthetic
email = "SYNTH_PROVIDER_TEST@synthetic-hospital.test"
email = "test-user-123@fake-domain.test"

# ❌ WRONG - Could be real
email = "doctor@hospital.com"
email = "john.smith@clinic.org"
```

### Phone Numbers
```python
# ✅ CORRECT - Use test ranges or synthetic markers
phone = "SYNTH-TEST-PHONE-555-0123"
phone = "555-TEST-123"  # 555 is reserved for testing

# ❌ WRONG - Real phone number format
phone = "617-555-1234"  # Could be real
phone = "(555) 123-4567"  # Ambiguous
```

## Validation Checklist

Before adding new test data, ensure:

- [ ] All patient identifiers include `SYNTH_` and `_TEST` markers
- [ ] Clinical notes include `[SYNTHETIC TEST DATA]` markers
- [ ] No real names, addresses, phone numbers, or SSNs
- [ ] Email addresses use synthetic domains (`.test`, `.synthetic`)
- [ ] Medical codes are legitimate but not linked to real cases
- [ ] Run PHI compliance validation and fix any violations

## Common Violations and Fixes

### Real Names
```python
# ❌ VIOLATION
patient_name = "John Smith"

# ✅ FIX
# Don't use patient names in test data at all, or use:
patient_name = "SYNTH_PATIENT_TEST_001"
```

### Real-Looking Addresses
```python
# ❌ VIOLATION
address = "123 Main Street, Boston, MA 02101"

# ✅ FIX
address = "SYNTH_ADDRESS_123_TEST_STREET, SYNTHETIC_CITY, ST 00000"
```

### Ambiguous Identifiers
```python
# ❌ VIOLATION
patient_id = "12345"
mrn = "MRN123456"

# ✅ FIX
patient_id = "SYNTH_PAT_12345_TEST"
mrn = "SYNTH_MRN_123456_TEST"
```

## Testing Your Compliance

### Quick Validation
```bash
# Run the PHI compliance validator
python validate_phi_compliance.py
```

### Detailed Testing
```python
# Test specific data
from tests.utils.phi_compliance import validate_test_data_phi_compliance

test_data = [your_test_data_here]
report = validate_test_data_phi_compliance(test_data)
print(f"Compliance Status: {report['overall_compliance_status']}")
```

### Pytest Integration
```python
def test_my_data_is_phi_compliant():
    """Test that my test data is PHI compliant."""
    from tests.utils.phi_compliance import PHIComplianceChecker
    
    checker = PHIComplianceChecker()
    violations = checker.check_object(my_test_data, "my_test_data")
    
    # Should have no high-severity violations
    high_violations = [v for v in violations if v.severity == 'high']
    assert len(high_violations) == 0, f"PHI violations found: {high_violations}"
```

## Environment Setup

Ensure your test environment is properly configured:

```bash
# Set environment to testing
export PA_ENVIRONMENT=testing

# This enables additional PHI validation warnings
```

## Reporting Issues

If you discover potential PHI in test data:

1. **Immediately** stop using the data
2. Replace with synthetic alternatives
3. Run validation to confirm fix
4. Update this documentation if needed

## Resources

- [HIPAA Privacy Rule](https://www.hhs.gov/hipaa/for-professionals/privacy/index.html)
- [PHI Definition](https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/identifying-protected-health-information/index.html)
- [Synthetic Data Best Practices](https://www.nist.gov/privacy-framework/synthetic-data)

## Questions?

If you have questions about PHI compliance in testing:

1. Review this document
2. Run the compliance validation tools
3. Consult with the compliance team
4. When in doubt, make it more obviously synthetic

Remember: **It's better to be overly cautious with PHI compliance than to risk a violation.**
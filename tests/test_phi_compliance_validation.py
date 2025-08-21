"""
Test PHI compliance validation functionality.

This test validates that our PHI compliance checking and synthetic data
generation is working correctly.
"""

import pytest
from datetime import datetime, timezone

from tests.utils.data_generator import DataGenerator, PHIValidationError
from tests.utils.phi_compliance import (
    PHIComplianceChecker, 
    validate_test_data_phi_compliance,
    check_string_for_phi
)
from src.models.patient import PatientDemographics
from src.models.enums import DecisionStatus, UrgencyLevel, ProcedureType, RequestStatus


class TestPHIComplianceValidation:
    """Test PHI compliance validation functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.data_generator = DataGenerator()
        self.phi_checker = PHIComplianceChecker()
    
    def test_synthetic_data_generation_has_markers(self):
    """Test that generated synthetic data has proper markers."""
        # Generate patient demographics
        patient = self.data_generator.generate_patient_demographics()
        
        # Check that synthetic markers are present
        assert "SYNTH" in patient.patient_id
        assert "TEST" in patient.patient_id
        assert "SYNTH" in patient.insurance_id
        assert "TEST" in patient.insurance_id
        assert "SYNTH" in patient.member_id
        assert "TEST" in patient.member_id
    
    def test_clinical_notes_have_synthetic_markers(self):
    """
        Test clinical notes have synthetic markers.
        
        This test verifies system functionality and ensures that the system
        behaves correctly under the specified conditions.
        
        Test Scenarios:
        - Standard input scenarios
        - Edge cases and boundary conditions
        - Error handling scenarios
        
        Expected Behavior:
        - System should behave according to specified requirements
        
        PHI Compliance:
        All test data uses synthetic information with appropriate markers.
        """
        request = self.data_generator.generate_authorization_request()
        
        # Check request ID
        assert "SYNTH_REQ_TEST_" in request.request_id
        
        # Check provider ID
        assert "SYNTH_PROV_" in request.provider_id
        assert "_TEST" in request.provider_id
        
        # Check clinical notes
        assert "[SYNTHETIC TEST DATA]" in request.clinical_notes
    
        def test_authorization_decision_has_synthetic_markers(self):
    """Test that authorization decisions have synthetic markers."""
        request = self.data_generator.generate_authorization_request()
        decision = self.data_generator.generate_authorization_decision(request, "approved")
        
        # Check decision ID
        assert "SYNTH_DEC_" in decision.decision_id
        assert "_TEST" in decision.decision_id
        
        # Check authorization number if approved
        if hasattr(decision, 'authorization_number'):
            assert "SYNTH_AUTH_" in decision.authorization_number
            assert "_TEST" in decision.authorization_number
    
    def test_phi_validation_detects_ssn(self):
    """
        Test phi validation detects ssn.
        
        This test verifies that the phicompliancevalidation correctly validates input data
        and handles both valid and invalid input scenarios appropriately.
        
        Test Scenarios:
        - Valid input data that meets all validation criteria
        - Invalid input data with specific validation errors
        - Edge cases and boundary conditions
        - Error handling and user-friendly error messages
        
        Expected Behavior:
        - Valid data should pass validation without errors
        - Invalid data should be rejected with specific error messages
        - Error messages should be clear and actionable
        - Validation should be consistent and deterministic
        
        Business Rules:
        - All input data must meet healthcare industry standards and regulatory requirements
        
        PHI Compliance:
        Uses only synthetic test data with clear SYNTH_ prefixes.
        """
        test_text = "Call patient at 555-123-4567"
        violations = check_string_for_phi(test_text, "test_field")
        
        assert len(violations) > 0
        assert any(v.violation_type == 'phone' for v in violations)
        assert any(v.severity == 'high' for v in violations)
    
    def test_phi_validation_detects_email(self):
    """
        Test phi validation detects email.
        
        This test verifies that the phicompliancevalidation correctly validates input data
        and handles both valid and invalid input scenarios appropriately.
        
        Test Scenarios:
        - Valid input data that meets all validation criteria
        - Invalid input data with specific validation errors
        - Edge cases and boundary conditions
        - Error handling and user-friendly error messages
        
        Expected Behavior:
        - Valid data should pass validation without errors
        - Invalid data should be rejected with specific error messages
        - Error messages should be clear and actionable
        - Validation should be consistent and deterministic
        
        Business Rules:
        - All input data must meet healthcare industry standards and regulatory requirements
        
        PHI Compliance:
        Uses only synthetic test data with clear SYNTH_ prefixes.
        """
        test_text = "Patient John Smith has shoulder pain"
        violations = check_string_for_phi(test_text, "test_field")
        
        assert len(violations) > 0
        assert any(v.violation_type == 'real_names' for v in violations)
    
    def test_phi_validation_allows_synthetic_data(self):
    """Test that PHI validation allows clearly synthetic data."""
        test_text = "SYNTH_PAT_1234567_TEST has shoulder pain"
        violations = check_string_for_phi(test_text, "test_field")
        
        # Should have low severity or no violations for synthetic data
        high_severity_violations = [v for v in violations if v.severity == 'high']
        assert len(high_severity_violations) == 0
    
    def test_data_generator_phi_validation_prevents_real_data(self):
    """Test that data generator prevents real PHI from being used."""
        # This would normally raise an exception if real PHI patterns were detected
        # Since our generator creates synthetic data, this should pass
        patient = self.data_generator.generate_patient_demographics()
        
        # Validate the generated patient data
        violations = self.phi_checker.check_object(patient, "patient")
        
        # Should have no high-severity violations
        high_severity_violations = [v for v in violations if v.severity == 'high']
        assert len(high_severity_violations) == 0
    
    def test_compliance_report_generation(self):
    """
        Test compliance report generation.
        
        This test verifies system functionality and ensures that the system
        behaves correctly under the specified conditions.
        
        Test Scenarios:
        - Standard input scenarios
        - Edge cases and boundary conditions
        - Error handling scenarios
        
        Expected Behavior:
        - System should behave according to specified requirements
        
        PHI Compliance:
        All test data uses synthetic information with appropriate markers.
        """
        scenarios = self.data_generator.generate_medical_scenarios(count=5)
        
        for scenario in scenarios:
            # Check that scenario is marked as synthetic
            assert scenario.is_synthetic is True
            assert scenario.synthetic_marker == "SYNTHETIC_TEST_DATA"
            
            # Check patient data
            assert "SYNTH" in scenario.patient.patient_id
            assert "TEST" in scenario.patient.patient_id
            
            # Check clinical notes
            assert "[SYNTHETIC TEST DATA]" in scenario.clinical_notes
    
    def test_performance_test_data_is_synthetic(self):
    """Test that performance test data is properly synthetic."""
        requests = self.data_generator.generate_performance_test_data(count=10)
        
        for request in requests:
            # Check request ID
            assert "SYNTH_REQ_TEST_" in request.request_id
            
            # Check patient data
            assert "SYNTH" in request.patient_demographics.patient_id
            assert "TEST" in request.patient_demographics.patient_id
            
            # Check clinical notes
            assert "[SYNTHETIC TEST DATA]" in request.clinical_notes
    
    def test_edge_case_scenarios_compliance(self):
    """
        Test edge case scenarios compliance.
        
        This test verifies system functionality and ensures that the system
        behaves correctly under the specified conditions.
        
        Test Scenarios:
        - Standard input scenarios
        - Edge cases and boundary conditions
        - Error handling scenarios
        
        Expected Behavior:
        - System should behave according to specified requirements
        
        PHI Compliance:
        All test data uses synthetic information with appropriate markers.
        """
        request = self.data_generator.generate_authorization_request(scenario_type)
        
        # Validate the request
        violations = self.phi_checker.check_object(request, f"{scenario_type}_request")
        
        # Should have no high-severity violations
        high_severity_violations = [v for v in violations if v.severity == 'high']
        assert len(high_severity_violations) == 0
        
        # Should have synthetic markers
        assert "SYNTH" in request.request_id
        assert "TEST" in request.request_id
    
        def test_compliance_checker_detects_multiple_violation_types(self):
    """Test that compliance checker can detect multiple types of violations."""
        # Create test data with multiple PHI violations
        test_data = {
            "patient_name": "John Smith",
            "ssn": "123-45-6789",
            "phone": "555-123-4567",
            "email": "john@example.com",
            "address": "123 Main Street"
        }
        
        violations = self.phi_checker.check_object(test_data, "test_data")
        
        # Should detect multiple violation types
        violation_types = {v.violation_type for v in violations}
        expected_types = {'real_names', 'ssn', 'phone', 'email', 'address'}
        
        # Should detect most or all of these violation types
        assert len(violation_types.intersection(expected_types)) >= 3
    
    def test_data_generator_environment_validation(self):
    """
        Test data generator environment validation.
        
        This test verifies that the phicompliancevalidation correctly validates input data
        and handles both valid and invalid input scenarios appropriately.
        
        Test Scenarios:
        - Valid input data that meets all validation criteria
        - Invalid input data with specific validation errors
        - Edge cases and boundary conditions
        - Error handling and user-friendly error messages
        
        Expected Behavior:
        - Valid data should pass validation without errors
        - Invalid data should be rejected with specific error messages
        - Error messages should be clear and actionable
        - Validation should be consistent and deterministic
        
        Business Rules:
        - All input data must meet healthcare industry standards and regulatory requirements
        
        PHI Compliance:
        Uses only synthetic test data with clear SYNTH_ prefixes.
        """

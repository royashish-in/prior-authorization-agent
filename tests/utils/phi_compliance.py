"""
PHI Compliance utilities for test data validation.

This module provides utilities to ensure all test data is HIPAA-compliant
and contains no real Protected Health Information (PHI).

⚠️  IMPORTANT: This module helps prevent real PHI from entering test data
⚠️  All test data must be synthetic and clearly marked as such
⚠️  Use these utilities to validate compliance before adding new test data
"""

import re
import warnings
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timezone
from dataclasses import dataclass


@dataclass
class PHIViolation:
    """Represents a potential PHI violation in test data."""
    violation_type: str
    field_name: str
    violation_text: str
    severity: str  # 'high', 'medium', 'low'
    recommendation: str


class PHIComplianceChecker:
    """Utility class for checking PHI compliance in test data."""
    
    # Patterns that indicate potential real PHI
    PHI_PATTERNS = {
        'ssn': {
            'pattern': re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
            'severity': 'high',
            'description': 'Social Security Number format detected'
        },
        'phone': {
            'pattern': re.compile(r'\b\d{3}-\d{3}-\d{4}\b|\b\(\d{3}\)\s*\d{3}-\d{4}\b'),
            'severity': 'high',
            'description': 'Phone number format detected'
        },
        'email': {
            'pattern': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
            'severity': 'medium',
            'description': 'Email address format detected'
        },
        'real_names': {
            'pattern': re.compile(
                r'\b(John|Jane|Smith|Johnson|Williams|Brown|Davis|Miller|Wilson|Moore|'
                r'Taylor|Anderson|Thomas|Jackson|White|Harris|Martin|Thompson|Garcia|'
                r'Martinez|Robinson|Clark|Rodriguez|Lewis|Lee|Walker|Hall|Allen|Young|'
                r'Hernandez|King|Wright|Lopez|Hill|Scott|Green|Adams|Baker|Gonzalez|'
                r'Nelson|Carter|Mitchell|Perez|Roberts|Turner|Phillips|Campbell|Parker|'
                r'Evans|Edwards|Collins|Stewart|Sanchez|Morris|Rogers|Reed|Cook|Morgan|'
                r'Bell|Murphy|Bailey|Rivera|Cooper|Richardson|Cox|Howard|Ward|Torres|'
                r'Peterson|Gray|Ramirez|James|Watson|Brooks|Kelly|Sanders|Price|Bennett|'
                r'Wood|Barnes|Ross|Henderson|Coleman|Jenkins|Perry|Powell|Long|Patterson|'
                r'Hughes|Flores|Washington|Butler|Simmons|Foster|Gonzales|Bryant|Alexander|'
                r'Russell|Griffin|Diaz|Hayes)\b', 
                re.IGNORECASE
            ),
            'severity': 'medium',
            'description': 'Common real name detected'
        },
        'address': {
            'pattern': re.compile(
                r'\b\d{1,5}\s+(Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|'
                r'Drive|Dr|Court|Ct|Place|Pl)\b', 
                re.IGNORECASE
            ),
            'severity': 'high',
            'description': 'Street address format detected'
        },
        'zip_code': {
            'pattern': re.compile(r'\b\d{5}(-\d{4})?\b'),
            'severity': 'medium',
            'description': 'ZIP code format detected'
        },
        'date_of_birth': {
            'pattern': re.compile(r'\b(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])/\d{4}\b'),
            'severity': 'high',
            'description': 'Date of birth format detected'
        },
        'mrn': {
            'pattern': re.compile(r'\bMRN\s*:?\s*\d{6,}\b', re.IGNORECASE),
            'severity': 'high',
            'description': 'Medical Record Number format detected'
        }
    }
    
    # Approved synthetic patterns that are safe to use
    SYNTHETIC_PATTERNS = [
        r'SYNTH_',
        r'TEST_',
        r'SYNTHETIC',
        r'enc_pat_',
        r'enc_ins_',
        r'enc_mem_',
        r'_TEST',
        r'MOCK_',
        r'FAKE_'
    ]
    
    def __init__(self):
        """Initialize the PHI compliance checker."""
        self.synthetic_pattern = re.compile('|'.join(self.SYNTHETIC_PATTERNS), re.IGNORECASE)
    
    def check_text(self, text: str, field_name: str = "unknown") -> List[PHIViolation]:
        """Check text for potential PHI violations.
        
        Args:
            text: Text to check for PHI
            field_name: Name of the field being checked
            
        Returns:
            List of PHI violations found
        """
        violations = []
        
        if not text:
            return violations
        
        # Check for PHI patterns
        for pattern_name, pattern_info in self.PHI_PATTERNS.items():
            matches = pattern_info['pattern'].findall(text)
            if matches:
                # Check if this might be synthetic data
                if self.synthetic_pattern.search(text):
                    # Likely synthetic, but warn anyway
                    severity = 'low'
                    recommendation = f"Verify that {pattern_name} in {field_name} is synthetic"
                else:
                    severity = pattern_info['severity']
                    recommendation = f"Replace {pattern_name} in {field_name} with synthetic alternative"
                
                violation = PHIViolation(
                    violation_type=pattern_name,
                    field_name=field_name,
                    violation_text=matches[0] if matches else "",
                    severity=severity,
                    recommendation=recommendation
                )
                violations.append(violation)
        
        return violations
    
    def check_object(self, obj: Any, obj_name: str = "object") -> List[PHIViolation]:
        """Check an object for potential PHI violations.
        
        Args:
            obj: Object to check (dict, dataclass, Pydantic model, etc.)
            obj_name: Name of the object being checked
            
        Returns:
            List of PHI violations found
        """
        violations = []
        
        # Convert object to dict for inspection
        if hasattr(obj, '__dict__'):
            obj_dict = obj.__dict__
        elif hasattr(obj, 'dict') and callable(obj.dict):
            # Pydantic model
            obj_dict = obj.dict()
        elif isinstance(obj, dict):
            obj_dict = obj
        else:
            # Convert to string and check
            return self.check_text(str(obj), obj_name)
        
        # Check each field
        for field_name, field_value in obj_dict.items():
            if isinstance(field_value, str):
                field_violations = self.check_text(field_value, f"{obj_name}.{field_name}")
                violations.extend(field_violations)
            elif isinstance(field_value, (list, tuple)):
                for i, item in enumerate(field_value):
                    if isinstance(item, str):
                        item_violations = self.check_text(item, f"{obj_name}.{field_name}[{i}]")
                        violations.extend(item_violations)
                    else:
                        item_violations = self.check_object(item, f"{obj_name}.{field_name}[{i}]")
                        violations.extend(item_violations)
            elif hasattr(field_value, '__dict__') or isinstance(field_value, dict):
                nested_violations = self.check_object(field_value, f"{obj_name}.{field_name}")
                violations.extend(nested_violations)
        
        return violations
    
    def is_synthetic_data(self, text: str) -> bool:
        """Check if text appears to be synthetic test data.
        
        Args:
            text: Text to check
            
        Returns:
            True if text appears to be synthetic
        """
        if not text:
            return False
        
        return bool(self.synthetic_pattern.search(text))
    
    def generate_compliance_report(self, test_data: List[Any], 
                                 data_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """Generate a comprehensive PHI compliance report.
        
        Args:
            test_data: List of test data objects to check
            data_names: Optional list of names for the test data objects
            
        Returns:
            Comprehensive compliance report
        """
        if data_names is None:
            data_names = [f"test_data_{i}" for i in range(len(test_data))]
        
        report = {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'total_objects_checked': len(test_data),
            'compliant_objects': 0,
            'objects_with_violations': 0,
            'total_violations': 0,
            'violations_by_severity': {'high': 0, 'medium': 0, 'low': 0},
            'violations_by_type': {},
            'detailed_violations': [],
            'recommendations': [],
            'overall_compliance_status': 'COMPLIANT'
        }
        
        all_violations = []
        
        # Check each test data object
        for i, (data, name) in enumerate(zip(test_data, data_names)):
            violations = self.check_object(data, name)
            
            if violations:
                report['objects_with_violations'] += 1
                all_violations.extend(violations)
                
                # Add to detailed violations
                report['detailed_violations'].append({
                    'object_name': name,
                    'violations': [
                        {
                            'type': v.violation_type,
                            'field': v.field_name,
                            'text': v.violation_text,
                            'severity': v.severity,
                            'recommendation': v.recommendation
                        }
                        for v in violations
                    ]
                })
            else:
                report['compliant_objects'] += 1
        
        # Aggregate violation statistics
        report['total_violations'] = len(all_violations)
        
        for violation in all_violations:
            # Count by severity
            report['violations_by_severity'][violation.severity] += 1
            
            # Count by type
            if violation.violation_type not in report['violations_by_type']:
                report['violations_by_type'][violation.violation_type] = 0
            report['violations_by_type'][violation.violation_type] += 1
        
        # Determine overall compliance status
        high_severity_violations = report['violations_by_severity']['high']
        if high_severity_violations > 0:
            report['overall_compliance_status'] = 'NON_COMPLIANT'
        elif report['violations_by_severity']['medium'] > 0:
            report['overall_compliance_status'] = 'NEEDS_REVIEW'
        
        # Generate recommendations
        if high_severity_violations > 0:
            report['recommendations'].append(
                "CRITICAL: High-severity PHI violations detected. "
                "Remove all real PHI immediately and replace with synthetic data."
            )
        
        if report['violations_by_severity']['medium'] > 0:
            report['recommendations'].append(
                "Medium-severity violations detected. "
                "Review flagged data and ensure it is clearly synthetic."
            )
        
        if report['violations_by_severity']['low'] > 0:
            report['recommendations'].append(
                "Low-severity warnings detected. "
                "Verify that flagged data is properly marked as synthetic."
            )
        
        if report['total_violations'] == 0:
            report['recommendations'].append(
                "All test data appears PHI-compliant. "
                "Continue monitoring for compliance in future test data."
            )
        
        return report
    
    def validate_synthetic_markers(self, data: Any) -> Dict[str, Any]:
        """Validate that data has appropriate synthetic markers.
        
        Args:
            data: Data to validate for synthetic markers
            
        Returns:
            Validation results
        """
        result = {
            'has_synthetic_markers': False,
            'marker_types_found': [],
            'recommendations': []
        }
        
        # Convert to string for pattern matching
        data_str = str(data)
        
        # Check for synthetic patterns
        for pattern in self.SYNTHETIC_PATTERNS:
            if re.search(pattern, data_str, re.IGNORECASE):
                result['has_synthetic_markers'] = True
                result['marker_types_found'].append(pattern)
        
        if not result['has_synthetic_markers']:
            result['recommendations'].append(
                "Add clear synthetic markers (e.g., SYNTH_, TEST_, SYNTHETIC) to test data"
            )
        
        return result


def validate_test_data_phi_compliance(test_data: List[Any], 
                                    data_names: Optional[List[str]] = None) -> Dict[str, Any]:
    """Convenience function to validate PHI compliance of test data.
    
    Args:
        test_data: List of test data objects to validate
        data_names: Optional names for the test data objects
        
    Returns:
        Compliance validation report
    """
    checker = PHIComplianceChecker()
    return checker.generate_compliance_report(test_data, data_names)


def check_string_for_phi(text: str, field_name: str = "text") -> List[PHIViolation]:
    """Convenience function to check a string for PHI violations.
    
    Args:
        text: Text to check
        field_name: Name of the field being checked
        
    Returns:
        List of PHI violations found
    """
    checker = PHIComplianceChecker()
    return checker.check_text(text, field_name)


# Warning for developers
def _issue_phi_warning():
    """Issue a warning about PHI compliance."""
    warnings.warn(
        "PHI Compliance Check: Ensure all test data is synthetic and HIPAA-compliant. "
        "Never use real patient information in tests.",
        UserWarning,
        stacklevel=3
    )


# Automatically issue warning when module is imported
_issue_phi_warning()
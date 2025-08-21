"""
PHI De-identification Service for HIPAA-Compliant LLM Processing

This service provides comprehensive PHI de-identification capabilities to ensure
that patient health information is properly sanitized before being sent to
external LLM services, maintaining HIPAA compliance.
"""

import re
import logging
import hashlib
import uuid
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
import json

from ..models.authorization import AuthorizationRequest
from ..models.patient import PatientInfo
from ..core.encryption import get_phi_encryption
from ..audit.logger import get_audit_logger
from ..audit.models import AuditEventType, SecurityLevel


class PHIType(str, Enum):
    """Types of PHI that need de-identification."""
    NAME = "name"
    DATE = "date"
    PHONE = "phone"
    EMAIL = "email"
    SSN = "ssn"
    MRN = "mrn"
    ACCOUNT_NUMBER = "account_number"
    CERTIFICATE_NUMBER = "certificate_number"
    VEHICLE_IDENTIFIER = "vehicle_identifier"
    DEVICE_IDENTIFIER = "device_identifier"
    WEB_URL = "web_url"
    IP_ADDRESS = "ip_address"
    BIOMETRIC_IDENTIFIER = "biometric_identifier"
    PHOTO = "photo"
    GEOGRAPHIC_SUBDIVISION = "geographic_subdivision"
    ADDRESS = "address"
    ZIP_CODE = "zip_code"
    AGE_OVER_89 = "age_over_89"


@dataclass
class PHIMatch:
    """Represents a detected PHI element."""
    phi_type: PHIType
    original_value: str
    start_position: int
    end_position: int
    confidence: float
    replacement_token: str
    context: Optional[str] = None


@dataclass
class DeidentificationResult:
    """Result of PHI de-identification process."""
    original_text: str
    deidentified_text: str
    phi_matches: List[PHIMatch] = field(default_factory=list)
    replacement_map: Dict[str, str] = field(default_factory=dict)
    risk_level: str = "low"
    processing_time_ms: float = 0.0
    method_used: str = "safe_harbor"
    validation_errors: List[str] = field(default_factory=list)


@dataclass
class ReidentificationMap:
    """Secure mapping for re-identification if needed."""
    request_id: str
    encrypted_mappings: str
    creation_time: datetime
    expiry_time: datetime
    phi_types_found: List[PHIType] = field(default_factory=list)


class PHIDetector:
    """Detects various types of PHI in text using pattern matching and rules."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.PHIDetector")
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for PHI detection."""
        self.patterns = {
            PHIType.SSN: [
                re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
                re.compile(r'\b\d{3}\s\d{2}\s\d{4}\b'),
                re.compile(r'\b\d{9}\b')
            ],
            PHIType.PHONE: [
                re.compile(r'\b\d{3}-\d{3}-\d{4}\b'),
                re.compile(r'\(\d{3}\)\s?\d{3}-\d{4}'),
                re.compile(r'\b\d{3}\.\d{3}\.\d{4}\b'),
                re.compile(r'\b\d{10}\b')
            ],
            PHIType.EMAIL: [
                re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
            ],
            PHIType.DATE: [
                re.compile(r'\b\d{1,2}/\d{1,2}/\d{4}\b'),
                re.compile(r'\b\d{1,2}-\d{1,2}-\d{4}\b'),
                re.compile(r'\b\d{4}-\d{1,2}-\d{1,2}\b'),
                re.compile(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b', re.IGNORECASE),
                re.compile(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b', re.IGNORECASE)
            ],
            PHIType.ZIP_CODE: [
                re.compile(r'\b\d{5}(-\d{4})?\b')
            ],
            PHIType.MRN: [
                re.compile(r'\bMRN:?\s*([A-Z0-9]{6,12})\b', re.IGNORECASE),
                re.compile(r'\bMedical\s+Record\s+Number:?\s*([A-Z0-9]{6,12})\b', re.IGNORECASE),
                re.compile(r'\bPatient\s+ID:?\s*([A-Z0-9]{6,12})\b', re.IGNORECASE)
            ],
            PHIType.ACCOUNT_NUMBER: [
                re.compile(r'\bAccount\s+Number:?\s*([A-Z0-9]{8,16})\b', re.IGNORECASE),
                re.compile(r'\bAcct:?\s*([A-Z0-9]{8,16})\b', re.IGNORECASE)
            ],
            PHIType.IP_ADDRESS: [
                re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
            ],
            PHIType.WEB_URL: [
                re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')
            ]
        }
        
        # Common name patterns (basic detection)
        self.name_patterns = [
            re.compile(r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b'),  # First Last
            re.compile(r'\b[A-Z][a-z]+,\s+[A-Z][a-z]+\b'),  # Last, First
            re.compile(r'\bDr\.\s+[A-Z][a-z]+\s+[A-Z][a-z]+\b'),  # Dr. First Last
            re.compile(r'\b[A-Z][a-z]+\s+[A-Z]\.\s+[A-Z][a-z]+\b')  # First M. Last
        ]
        
        # Geographic subdivisions (states, cities)
        self.geographic_patterns = [
            re.compile(r'\b(Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming)\b', re.IGNORECASE),
            re.compile(r'\b(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)\b')
        ]
    
    def detect_phi(self, text: str) -> List[PHIMatch]:
        """Detect PHI elements in text."""
        matches = []
        
        # Detect using compiled patterns
        for phi_type, patterns in self.patterns.items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    phi_match = PHIMatch(
                        phi_type=phi_type,
                        original_value=match.group(),
                        start_position=match.start(),
                        end_position=match.end(),
                        confidence=0.9,  # High confidence for regex matches
                        replacement_token=self._generate_replacement_token(phi_type, match.group())
                    )
                    matches.append(phi_match)
        
        # Detect names (lower confidence)
        for pattern in self.name_patterns:
            for match in pattern.finditer(text):
                # Skip if it's a medical term or common word
                if not self._is_likely_name(match.group()):
                    continue
                
                phi_match = PHIMatch(
                    phi_type=PHIType.NAME,
                    original_value=match.group(),
                    start_position=match.start(),
                    end_position=match.end(),
                    confidence=0.7,  # Lower confidence for name detection
                    replacement_token=self._generate_replacement_token(PHIType.NAME, match.group())
                )
                matches.append(phi_match)
        
        # Detect geographic subdivisions
        for pattern in self.geographic_patterns:
            for match in pattern.finditer(text):
                phi_match = PHIMatch(
                    phi_type=PHIType.GEOGRAPHIC_SUBDIVISION,
                    original_value=match.group(),
                    start_position=match.start(),
                    end_position=match.end(),
                    confidence=0.8,
                    replacement_token=self._generate_replacement_token(PHIType.GEOGRAPHIC_SUBDIVISION, match.group())
                )
                matches.append(phi_match)
        
        # Sort matches by position for proper replacement
        matches.sort(key=lambda x: x.start_position)
        
        # Remove overlapping matches (keep highest confidence)
        filtered_matches = self._remove_overlapping_matches(matches)
        
        return filtered_matches
    
    def _is_likely_name(self, text: str) -> bool:
        """Check if text is likely a person's name."""
        # Skip common medical terms
        medical_terms = {
            'patient', 'doctor', 'nurse', 'medical', 'clinical', 'diagnosis',
            'treatment', 'procedure', 'medication', 'therapy', 'surgery',
            'hospital', 'clinic', 'health', 'care', 'service', 'department'
        }
        
        words = text.lower().split()
        for word in words:
            if word in medical_terms:
                return False
        
        # Must be proper case
        if not all(word[0].isupper() and word[1:].islower() for word in words if word):
            return False
        
        return True
    
    def _remove_overlapping_matches(self, matches: List[PHIMatch]) -> List[PHIMatch]:
        """Remove overlapping matches, keeping the one with highest confidence."""
        if not matches:
            return matches
        
        filtered = []
        current_match = matches[0]
        
        for next_match in matches[1:]:
            # Check for overlap
            if next_match.start_position < current_match.end_position:
                # Keep the match with higher confidence
                if next_match.confidence > current_match.confidence:
                    current_match = next_match
            else:
                filtered.append(current_match)
                current_match = next_match
        
        filtered.append(current_match)
        return filtered
    
    def _generate_replacement_token(self, phi_type: PHIType, original_value: str) -> str:
        """Generate a replacement token for PHI."""
        # Create a consistent hash-based token
        hash_input = f"{phi_type.value}:{original_value}"
        hash_value = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        
        token_map = {
            PHIType.NAME: f"[NAME_{hash_value}]",
            PHIType.DATE: f"[DATE_{hash_value}]",
            PHIType.PHONE: f"[PHONE_{hash_value}]",
            PHIType.EMAIL: f"[EMAIL_{hash_value}]",
            PHIType.SSN: f"[SSN_{hash_value}]",
            PHIType.MRN: f"[MRN_{hash_value}]",
            PHIType.ACCOUNT_NUMBER: f"[ACCOUNT_{hash_value}]",
            PHIType.ZIP_CODE: f"[ZIP_{hash_value}]",
            PHIType.IP_ADDRESS: f"[IP_{hash_value}]",
            PHIType.WEB_URL: f"[URL_{hash_value}]",
            PHIType.GEOGRAPHIC_SUBDIVISION: f"[LOCATION_{hash_value}]"
        }
        
        return token_map.get(phi_type, f"[{phi_type.value.upper()}_{hash_value}]")


class SafeHarborDeidentifier:
    """Implements HIPAA Safe Harbor de-identification method."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.SafeHarborDeidentifier")
        self.phi_detector = PHIDetector()
        self.encryption = get_phi_encryption()
        self.audit_logger = get_audit_logger()
    
    def deidentify_text(
        self,
        text: str,
        request_id: Optional[str] = None,
        preserve_structure: bool = True
    ) -> DeidentificationResult:
        """De-identify text using Safe Harbor method."""
        start_time = datetime.now()
        
        if not text or not text.strip():
            return DeidentificationResult(
                original_text=text,
                deidentified_text=text,
                processing_time_ms=0.0
            )
        
        try:
            # Detect PHI elements
            phi_matches = self.phi_detector.detect_phi(text)
            
            # Create replacement map
            replacement_map = {}
            deidentified_text = text
            
            # Replace PHI elements (in reverse order to maintain positions)
            for match in reversed(phi_matches):
                replacement_map[match.original_value] = match.replacement_token
                deidentified_text = (
                    deidentified_text[:match.start_position] +
                    match.replacement_token +
                    deidentified_text[match.end_position:]
                )
            
            # Calculate risk level
            risk_level = self._calculate_risk_level(phi_matches)
            
            # Validate de-identification
            validation_errors = self._validate_deidentification(deidentified_text)
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            result = DeidentificationResult(
                original_text=text,
                deidentified_text=deidentified_text,
                phi_matches=phi_matches,
                replacement_map=replacement_map,
                risk_level=risk_level,
                processing_time_ms=processing_time,
                method_used="safe_harbor",
                validation_errors=validation_errors
            )
            
            # Log de-identification event
            self._log_deidentification_event(result, request_id)
            
            return result
            
        except Exception as e:
            self.logger.error(f"De-identification failed: {str(e)}")
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return DeidentificationResult(
                original_text=text,
                deidentified_text=text,  # Return original on failure
                processing_time_ms=processing_time,
                validation_errors=[f"De-identification failed: {str(e)}"]
            )
    
    def deidentify_authorization_request(
        self,
        request: AuthorizationRequest
    ) -> Tuple[AuthorizationRequest, ReidentificationMap]:
        """De-identify an entire authorization request."""
        request_id = request.request_id or str(uuid.uuid4())
        
        # Create a copy of the request for modification
        deidentified_request = AuthorizationRequest(
            request_id=request_id,
            patient_id=request.patient_id,  # Keep encrypted patient ID
            provider_id=request.provider_id,
            payer_id=request.payer_id,
            procedure_code=request.procedure_code,
            diagnosis_codes=request.diagnosis_codes,
            urgency_level=request.urgency_level,
            requested_date=request.requested_date,
            clinical_notes=request.clinical_notes,
            supporting_documentation=request.supporting_documentation,
            created_at=request.created_at
        )
        
        # Collect all mappings for re-identification
        all_mappings = {}
        phi_types_found = set()
        
        # De-identify clinical notes
        if request.clinical_notes:
            notes_result = self.deidentify_text(request.clinical_notes, request_id)
            deidentified_request.clinical_notes = notes_result.deidentified_text
            all_mappings.update(notes_result.replacement_map)
            phi_types_found.update([match.phi_type for match in notes_result.phi_matches])
        
        # De-identify supporting documentation
        if request.supporting_documentation:
            for i, doc in enumerate(request.supporting_documentation):
                if isinstance(doc, str):
                    doc_result = self.deidentify_text(doc, request_id)
                    deidentified_request.supporting_documentation[i] = doc_result.deidentified_text
                    all_mappings.update(doc_result.replacement_map)
                    phi_types_found.update([match.phi_type for match in doc_result.phi_matches])
        
        # Create secure re-identification map
        reidentification_map = self._create_reidentification_map(
            request_id, all_mappings, list(phi_types_found)
        )
        
        return deidentified_request, reidentification_map
    
    def _calculate_risk_level(self, phi_matches: List[PHIMatch]) -> str:
        """Calculate risk level based on PHI found."""
        if not phi_matches:
            return "low"
        
        high_risk_types = {PHIType.SSN, PHIType.MRN, PHIType.ACCOUNT_NUMBER}
        medium_risk_types = {PHIType.NAME, PHIType.PHONE, PHIType.EMAIL, PHIType.DATE}
        
        found_types = {match.phi_type for match in phi_matches}
        
        if found_types.intersection(high_risk_types):
            return "high"
        elif found_types.intersection(medium_risk_types):
            return "medium"
        else:
            return "low"
    
    def _validate_deidentification(self, deidentified_text: str) -> List[str]:
        """Validate that de-identification was successful."""
        errors = []
        
        # Check for remaining PHI patterns
        remaining_phi = self.phi_detector.detect_phi(deidentified_text)
        
        for match in remaining_phi:
            # Only flag if it's not a replacement token
            if not match.original_value.startswith('[') or not match.original_value.endswith(']'):
                errors.append(f"Potential remaining PHI: {match.phi_type.value} - {match.original_value}")
        
        return errors
    
    def _create_reidentification_map(
        self,
        request_id: str,
        mappings: Dict[str, str],
        phi_types_found: List[PHIType]
    ) -> ReidentificationMap:
        """Create encrypted re-identification map."""
        # Encrypt the mappings
        mappings_json = json.dumps(mappings)
        encrypted_mappings = self.encryption.encrypt(mappings_json)
        
        return ReidentificationMap(
            request_id=request_id,
            encrypted_mappings=encrypted_mappings,
            creation_time=datetime.now(),
            expiry_time=datetime.now().replace(hour=23, minute=59, second=59),  # Expire at end of day
            phi_types_found=phi_types_found
        )
    
    def _log_deidentification_event(
        self,
        result: DeidentificationResult,
        request_id: Optional[str]
    ):
        """Log de-identification event for audit purposes."""
        phi_types_found = [match.phi_type.value for match in result.phi_matches]
        
        self.audit_logger.log_event(
            event_type=AuditEventType.PHI_DEIDENTIFICATION,
            action="deidentify_text",
            outcome="success" if not result.validation_errors else "warning",
            request_id=request_id,
            security_level=SecurityLevel.HIGH,
            phi_involved=True,
            compliance_flags=["HIPAA", "Safe_Harbor"],
            details={
                "phi_types_found": phi_types_found,
                "phi_count": len(result.phi_matches),
                "risk_level": result.risk_level,
                "processing_time_ms": result.processing_time_ms,
                "validation_errors": result.validation_errors
            }
        )


class PHIDeidentificationService:
    """Main service for PHI de-identification with multiple methods."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.safe_harbor_deidentifier = SafeHarborDeidentifier()
        self.audit_logger = get_audit_logger()
    
    def prepare_for_llm(
        self,
        request: AuthorizationRequest,
        method: str = "safe_harbor"
    ) -> Tuple[AuthorizationRequest, ReidentificationMap]:
        """Prepare authorization request for LLM processing by de-identifying PHI."""
        start_time = datetime.now()
        
        try:
            if method == "safe_harbor":
                deidentified_request, reidentification_map = (
                    self.safe_harbor_deidentifier.deidentify_authorization_request(request)
                )
            else:
                raise ValueError(f"Unsupported de-identification method: {method}")
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # Log the preparation event
            self.audit_logger.log_event(
                event_type=AuditEventType.LLM_DATA_PREPARATION,
                action="prepare_for_llm",
                outcome="success",
                request_id=request.request_id,
                security_level=SecurityLevel.HIGH,
                phi_involved=True,
                compliance_flags=["HIPAA", "LLM_Processing"],
                details={
                    "method": method,
                    "phi_types_found": [phi_type.value for phi_type in reidentification_map.phi_types_found],
                    "processing_time_ms": processing_time
                }
            )
            
            return deidentified_request, reidentification_map
            
        except Exception as e:
            self.logger.error(f"Failed to prepare request for LLM: {str(e)}")
            
            # Log the failure
            self.audit_logger.log_event(
                event_type=AuditEventType.LLM_DATA_PREPARATION,
                action="prepare_for_llm",
                outcome="failure",
                request_id=request.request_id,
                security_level=SecurityLevel.HIGH,
                phi_involved=True,
                error_message=str(e)
            )
            
            raise
    
    def validate_deidentification(
        self,
        original_text: str,
        deidentified_text: str
    ) -> Dict[str, Any]:
        """Validate that de-identification was successful."""
        # Re-run detection on deidentified text
        detector = PHIDetector()
        remaining_phi = detector.detect_phi(deidentified_text)
        
        # Filter out replacement tokens
        actual_remaining_phi = [
            match for match in remaining_phi
            if not (match.original_value.startswith('[') and match.original_value.endswith(']'))
        ]
        
        return {
            "is_valid": len(actual_remaining_phi) == 0,
            "remaining_phi_count": len(actual_remaining_phi),
            "remaining_phi_types": [match.phi_type.value for match in actual_remaining_phi],
            "risk_assessment": "high" if actual_remaining_phi else "low"
        }
    
    def get_supported_methods(self) -> List[str]:
        """Get list of supported de-identification methods."""
        return ["safe_harbor"]
    
    def get_phi_statistics(self, text: str) -> Dict[str, Any]:
        """Get statistics about PHI in text without de-identifying."""
        detector = PHIDetector()
        phi_matches = detector.detect_phi(text)
        
        phi_type_counts = {}
        for match in phi_matches:
            phi_type_counts[match.phi_type.value] = phi_type_counts.get(match.phi_type.value, 0) + 1
        
        return {
            "total_phi_elements": len(phi_matches),
            "phi_type_counts": phi_type_counts,
            "risk_level": self.safe_harbor_deidentifier._calculate_risk_level(phi_matches),
            "requires_deidentification": len(phi_matches) > 0
        }


# Global service instance
phi_deidentification_service = PHIDeidentificationService()
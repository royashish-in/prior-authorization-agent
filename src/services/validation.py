"""
Validation service for authorization requests.

This module provides comprehensive validation of authorization requests
including data format validation, medical code validation, and business rules.
"""

import re
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from src.models.authorization import AuthorizationRequest
from src.models.medical_codes import ICD10Code, CPTCode, HCPCSCode
from src.services.medical_code_validator import (
    MedicalCodeValidator,
    CodeValidationResult,
)
from src.services.external_services import ExternalServiceIntegrator
from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationError:
    """Represents a validation error with details."""

    field: str
    message: str
    value: Any
    suggestion: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of validation process."""

    is_valid: bool
    errors: List[ValidationError]
    warnings: List[str]
    processing_time_ms: float


class ValidationService:
    """
    Service for validating authorization requests.

    Provides comprehensive validation including:
    - Data format validation
    - Medical code validation
    - Business rule validation
    - Cross-field validation
    """

    def __init__(self):
        """Initialize validation service."""
        self.logger = get_logger(self.__class__.__name__)

        # Initialize medical code validator with caching and external database integration
        self._medical_code_validator = MedicalCodeValidator()

        # Initialize external service integrator
        self._external_services = ExternalServiceIntegrator()

    async def validate_request(self, request: AuthorizationRequest) -> ValidationResult:
        """
        Perform comprehensive validation of an authorization request.

        Args:
            request: Authorization request to validate

        Returns:
            Validation result with errors and warnings
        """
        start_time = datetime.now(timezone.utc)
        errors = []
        warnings = []

        try:
            # Validate medical codes
            code_errors, code_warnings = await self._validate_medical_codes(request)
            errors.extend(code_errors)
            warnings.extend(code_warnings)

            # Validate business rules
            business_errors, business_warnings = await self._validate_business_rules(
                request
            )
            errors.extend(business_errors)
            warnings.extend(business_warnings)

            # Validate cross-field relationships
            relationship_errors = await self._validate_field_relationships(request)
            errors.extend(relationship_errors)

            # Calculate processing time
            processing_time = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds() * 1000

            is_valid = len(errors) == 0

            self.logger.info(
                "Request validation completed",
                request_id=request.request_id,
                is_valid=is_valid,
                error_count=len(errors),
                warning_count=len(warnings),
                processing_time_ms=processing_time,
            )

            return ValidationResult(
                is_valid=is_valid,
                errors=errors,
                warnings=warnings,
                processing_time_ms=processing_time,
            )

        except Exception as e:
            self.logger.error(
                "Validation service error",
                request_id=request.request_id,
                error=str(e),
                exc_info=True,
            )

            # Return validation failure for unexpected errors
            processing_time = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds() * 1000
            return ValidationResult(
                is_valid=False,
                errors=[
                    ValidationError(
                        field="system",
                        message="Validation service encountered an unexpected error",
                        value=str(e),
                    )
                ],
                warnings=[],
                processing_time_ms=processing_time,
            )

    async def _validate_medical_codes(
        self, request: AuthorizationRequest
    ) -> tuple[List[ValidationError], List[str]]:
        """
        Validate medical codes (ICD-10, CPT, HCPCS) using external services.

        Args:
            request: Authorization request

        Returns:
            Tuple of (errors, warnings)
        """
        errors = []
        warnings = []

        try:
            # Prepare codes for external validation
            codes_to_validate = []

            # Add diagnosis codes
            for diagnosis_code in request.diagnosis_codes:
                codes_to_validate.append(
                    {
                        "code": diagnosis_code.code,
                        "code_type": "icd10",
                        "description": diagnosis_code.description,
                    }
                )

            # Add procedure codes
            for procedure_code in request.procedure_codes:
                code_type = "cpt" if isinstance(procedure_code, CPTCode) else "hcpcs"
                codes_to_validate.append(
                    {
                        "code": procedure_code.code,
                        "code_type": code_type,
                        "description": procedure_code.description,
                    }
                )

            # Validate codes using external service
            validation_responses = await self._external_services.validate_medical_codes(
                codes=codes_to_validate, use_cache=True, fallback_on_error=True
            )

            # Process validation results
            diagnosis_index = 0
            procedure_index = 0

            for i, response in enumerate(validation_responses):
                if response.code_type == "icd10":
                    field_path = f"diagnosis_codes[{diagnosis_index}]"
                    diagnosis_index += 1
                else:
                    field_path = f"procedure_codes[{procedure_index}]"
                    procedure_index += 1

                if not response.is_valid:
                    suggestion = None
                    if response.suggestions:
                        suggestion = "; ".join(response.suggestions[:3])

                    errors.append(
                        ValidationError(
                            field=f"{field_path}.code",
                            message=f"Medical code '{response.code}' is not valid",
                            value=response.code,
                            suggestion=suggestion,
                        )
                    )

                # Check for expiration warnings
                if (
                    response.expiration_date
                    and response.expiration_date < datetime.now(timezone.utc)
                ):
                    warnings.append(
                        f"Code {response.code} has expired on {response.expiration_date.date()}"
                    )

            # Fallback to local validation if external service fails
        except Exception as e:
            self.logger.warning(
                f"External code validation failed, using local validation: {str(e)}"
            )

            # Validate ICD-10 diagnosis codes locally
            for i, diagnosis_code in enumerate(request.diagnosis_codes):
                code_errors = await self._validate_icd10_code(
                    diagnosis_code, f"diagnosis_codes[{i}]"
                )
                errors.extend(code_errors)

            # Validate procedure codes (CPT/HCPCS) locally
            for i, procedure_code in enumerate(request.procedure_codes):
                if isinstance(procedure_code, CPTCode):
                    code_errors = await self._validate_cpt_code(
                        procedure_code, f"procedure_codes[{i}]"
                    )
                else:  # HCPCSCode
                    code_errors = await self._validate_hcpcs_code(
                        procedure_code, f"procedure_codes[{i}]"
                    )
                errors.extend(code_errors)

        # Check for code compatibility
        compatibility_warnings = await self._check_code_compatibility(request)
        warnings.extend(compatibility_warnings)

        return errors, warnings

    async def _validate_icd10_code(
        self, code: ICD10Code, field_path: str
    ) -> List[ValidationError]:
        """
        Validate a single ICD-10 code using the medical code validator.

        Args:
            code: ICD-10 code to validate
            field_path: Field path for error reporting

        Returns:
            List of validation errors
        """
        errors = []

        # Use the medical code validator for comprehensive validation
        validation_result = await self._medical_code_validator.validate_icd10_code(code)

        if validation_result.result != CodeValidationResult.VALID:
            # Format suggestions from the validator
            suggestion = None
            if validation_result.suggestions:
                suggestion = "; ".join(
                    validation_result.suggestions[:3]
                )  # Limit to 3 suggestions

            errors.append(
                ValidationError(
                    field=f"{field_path}.code",
                    message=f"ICD-10 code '{code.code}' is not recognized or may be invalid",
                    value=code.code,
                    suggestion=suggestion,
                )
            )

        # Validate description matches if provided and code is valid
        elif code.description and validation_result.description:
            if code.description.lower() != validation_result.description.lower():
                errors.append(
                    ValidationError(
                        field=f"{field_path}.description",
                        message=f"Description does not match expected description for code {code.code}",
                        value=code.description,
                        suggestion=f"Expected: {validation_result.description}",
                    )
                )

        return errors

    async def _validate_cpt_code(
        self, code: CPTCode, field_path: str
    ) -> List[ValidationError]:
        """
        Validate a single CPT code using the medical code validator.

        Args:
            code: CPT code to validate
            field_path: Field path for error reporting

        Returns:
            List of validation errors
        """
        errors = []

        # Use the medical code validator for comprehensive validation
        validation_result = await self._medical_code_validator.validate_cpt_code(code)

        if validation_result.result != CodeValidationResult.VALID:
            # Format suggestions from the validator
            suggestion = None
            if validation_result.suggestions:
                suggestion = "; ".join(
                    validation_result.suggestions[:3]
                )  # Limit to 3 suggestions

            errors.append(
                ValidationError(
                    field=f"{field_path}.code",
                    message=f"CPT code '{code.code}' is not recognized for imaging services",
                    value=code.code,
                    suggestion=suggestion,
                )
            )

        # Validate description matches if provided and code is valid
        elif code.description and validation_result.description:
            if code.description.lower() != validation_result.description.lower():
                errors.append(
                    ValidationError(
                        field=f"{field_path}.description",
                        message=f"Description does not match expected description for code {code.code}",
                        value=code.description,
                        suggestion=f"Expected: {validation_result.description}",
                    )
                )

        return errors

    async def _validate_hcpcs_code(
        self, code: HCPCSCode, field_path: str
    ) -> List[ValidationError]:
        """
        Validate a single HCPCS code using the medical code validator.

        Args:
            code: HCPCS code to validate
            field_path: Field path for error reporting

        Returns:
            List of validation errors
        """
        errors = []

        # Use the medical code validator for comprehensive validation
        validation_result = await self._medical_code_validator.validate_hcpcs_code(code)

        if validation_result.result != CodeValidationResult.VALID:
            # Format suggestions from the validator
            suggestion = None
            if validation_result.suggestions:
                suggestion = "; ".join(
                    validation_result.suggestions[:3]
                )  # Limit to 3 suggestions

            errors.append(
                ValidationError(
                    field=f"{field_path}.code",
                    message=f"HCPCS code '{code.code}' is not recognized or may be invalid",
                    value=code.code,
                    suggestion=suggestion,
                )
            )

        # Validate description matches if provided and code is valid
        elif code.description and validation_result.description:
            if code.description.lower() != validation_result.description.lower():
                errors.append(
                    ValidationError(
                        field=f"{field_path}.description",
                        message=f"Description does not match expected description for code {code.code}",
                        value=code.description,
                        suggestion=f"Expected: {validation_result.description}",
                    )
                )

        return errors

    async def _validate_business_rules(
        self, request: AuthorizationRequest
    ) -> tuple[List[ValidationError], List[str]]:
        """
        Validate business rules for authorization requests.

        Args:
            request: Authorization request

        Returns:
            Tuple of (errors, warnings)
        """
        errors = []
        warnings = []

        # Rule: Patient age must be appropriate for procedure
        age_errors, age_warnings = await self._validate_age_appropriateness(request)
        errors.extend(age_errors)
        warnings.extend(age_warnings)

        # Rule: Clinical notes required for certain procedures
        notes_errors = await self._validate_clinical_notes_requirement(request)
        errors.extend(notes_errors)

        # Rule: Urgency level validation
        urgency_warnings = await self._validate_urgency_level(request)
        warnings.extend(urgency_warnings)

        return errors, warnings

    async def _validate_age_appropriateness(
        self, request: AuthorizationRequest
    ) -> tuple[List[ValidationError], List[str]]:
        """
        Validate age appropriateness for requested procedures.

        Args:
            request: Authorization request

        Returns:
            Tuple of (errors, warnings)
        """
        errors = []
        warnings = []

        patient_age = request.patient_demographics.age

        # Age validation rules for different procedures
        for procedure_code in request.procedure_codes:
            if isinstance(procedure_code, CPTCode):
                # Brain MRI age considerations
                if procedure_code.code.startswith("705") and patient_age < 5:
                    warnings.append(
                        f"Brain MRI (CPT {procedure_code.code}) in patients under 5 years "
                        "may require special pediatric protocols"
                    )

                # Spine MRI considerations
                elif procedure_code.code.startswith("721") and patient_age > 80:
                    warnings.append(
                        f"Spine MRI (CPT {procedure_code.code}) in patients over 80 years "
                        "should consider contraindications and medical necessity"
                    )

        return errors, warnings

    async def _validate_clinical_notes_requirement(
        self, request: AuthorizationRequest
    ) -> List[ValidationError]:
        """
        Validate clinical notes requirements based on procedure type.

        Args:
            request: Authorization request

        Returns:
            List of validation errors
        """
        errors = []

        # Procedures that require clinical notes
        requires_notes = False

        for procedure_code in request.procedure_codes:
            if isinstance(procedure_code, CPTCode):
                # MRI procedures typically require clinical justification
                if procedure_code.code.startswith(("705", "721", "732")):
                    requires_notes = True
                    break

        if requires_notes and not request.clinical_notes:
            errors.append(
                ValidationError(
                    field="clinical_notes",
                    message="Clinical notes are required for MRI procedures to establish medical necessity",
                    value=request.clinical_notes,
                    suggestion="Provide clinical notes describing symptoms, duration, and medical necessity",
                )
            )
        elif (
            requires_notes
            and request.clinical_notes
            and len(request.clinical_notes.strip()) < 50
        ):
            errors.append(
                ValidationError(
                    field="clinical_notes",
                    message="Clinical notes are too brief for adequate medical necessity review",
                    value=request.clinical_notes,
                    suggestion="Provide more detailed clinical notes (minimum 50 characters)",
                )
            )

        return errors

    async def _validate_urgency_level(self, request: AuthorizationRequest) -> List[str]:
        """
        Validate urgency level appropriateness.

        Args:
            request: Authorization request

        Returns:
            List of warnings
        """
        warnings = []

        # Check if urgency level matches procedure type
        if request.urgency_level.value == "emergent":
            # Most imaging procedures are not truly emergent
            warnings.append(
                "Emergent urgency level should be reserved for life-threatening conditions. "
                "Consider 'urgent' for most imaging needs."
            )

        return warnings

    async def _validate_field_relationships(
        self, request: AuthorizationRequest
    ) -> List[ValidationError]:
        """
        Validate relationships between different fields.

        Args:
            request: Authorization request

        Returns:
            List of validation errors
        """
        errors = []

        # Validate diagnosis and procedure code relationships
        relationship_errors = await self._validate_diagnosis_procedure_relationship(
            request
        )
        errors.extend(relationship_errors)

        return errors

    async def _validate_diagnosis_procedure_relationship(
        self, request: AuthorizationRequest
    ) -> List[ValidationError]:
        """
        Validate that diagnosis codes support the requested procedures.

        Args:
            request: Authorization request

        Returns:
            List of validation errors
        """
        errors = []

        # Simple relationship validation (in production, this would be more comprehensive)
        diagnosis_codes = [code.code for code in request.diagnosis_codes]

        for procedure_code in request.procedure_codes:
            if isinstance(procedure_code, CPTCode):
                # Shoulder MRI should have shoulder-related diagnosis
                if procedure_code.code in ["73221", "73222", "73223"]:
                    has_shoulder_diagnosis = any(
                        code.startswith("M25.51") for code in diagnosis_codes
                    )
                    if not has_shoulder_diagnosis:
                        errors.append(
                            ValidationError(
                                field="diagnosis_codes",
                                message=f"Shoulder MRI (CPT {procedure_code.code}) requires shoulder-related diagnosis",
                                value=diagnosis_codes,
                                suggestion="Include shoulder pain diagnosis (e.g., M25.511, M25.512, M25.519)",
                            )
                        )

        return errors

    async def _check_code_compatibility(
        self, request: AuthorizationRequest
    ) -> List[str]:
        """
        Check compatibility between diagnosis and procedure codes.

        Args:
            request: Authorization request

        Returns:
            List of warnings
        """
        warnings = []

        # Check for common compatibility issues
        diagnosis_codes = [code.code for code in request.diagnosis_codes]

        # Example: Multiple MRI procedures might indicate over-utilization
        mri_procedures = [
            code
            for code in request.procedure_codes
            if isinstance(code, CPTCode) and code.code.startswith(("705", "721", "732"))
        ]

        if len(mri_procedures) > 2:
            warnings.append(
                "Multiple MRI procedures requested. Ensure all procedures are medically necessary "
                "and cannot be combined into a single study."
            )

        return warnings

    def get_validation_stats(self) -> Dict[str, Any]:
        """
        Get validation statistics including medical code validator stats.

        Returns:
            Dictionary with validation statistics
        """
        return self._medical_code_validator.get_cache_stats()

    def clear_validation_cache(self):
        """Clear medical code validation cache."""
        self._medical_code_validator.clear_cache()
        self.logger.info("Validation cache cleared")

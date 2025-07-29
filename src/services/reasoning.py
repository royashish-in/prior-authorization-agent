"""
Decision reasoning and documentation service.

This module provides detailed reasoning generation, structured decision documentation,
and alternative procedure suggestions for authorization decisions.
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from src.models.authorization import AuthorizationRequest, AuthorizationDecision
from src.models.enums import DecisionStatus, ProcedureType
from src.services.validation import ValidationResult
from src.services.policy_validation import PolicyValidationResult
from src.core.logging import get_logger


class ReasoningCategory(Enum):
    """Categories for decision reasoning."""

    MEDICAL_NECESSITY = "medical_necessity"
    POLICY_COMPLIANCE = "policy_compliance"
    CMS_GUIDELINES = "cms_guidelines"
    CLINICAL_CRITERIA = "clinical_criteria"
    DOCUMENTATION = "documentation"
    ALTERNATIVE_OPTIONS = "alternative_options"


@dataclass
class ReasoningElement:
    """Individual reasoning element with category and details."""

    category: ReasoningCategory
    statement: str
    policy_reference: Optional[str] = None
    confidence_level: Optional[str] = None  # "high", "moderate", "low"
    supporting_evidence: Optional[List[str]] = None


@dataclass
class DecisionDocumentation:
    """Structured decision documentation for audit trail."""

    decision_id: str
    request_id: str
    decision_timestamp: datetime
    decision_status: DecisionStatus
    reasoning_elements: List[ReasoningElement]
    policy_references: List[str]
    clinical_factors: Dict[str, Any]
    risk_assessment: Dict[str, Any]
    alternative_procedures: List[Dict[str, str]]
    reviewer_notes: Optional[str] = None
    audit_trail: List[Dict[str, Any]] = None


class ReasoningEngine:
    """
    Advanced reasoning engine for generating detailed decision explanations.

    Provides comprehensive reasoning generation, structured documentation,
    and alternative procedure suggestions for authorization decisions.
    """

    def __init__(self):
        """Initialize the reasoning engine."""
        self.logger = get_logger(self.__class__.__name__)

        # Procedure code mappings for alternatives
        self.procedure_alternatives = {
            # MRI alternatives
            "73221": [
                "73200",
                "73218",
                "76881",
            ],  # MRI upper extremity -> X-ray, CT, US
            "73720": [
                "73610",
                "73700",
                "76882",
            ],  # MRI lower extremity -> X-ray, CT, US
            "70551": [
                "70450",
                "70460",
                "76506",
            ],  # Brain MRI -> CT head, CT with contrast, US
            "72148": ["72100", "72125", "76775"],  # Lumbar MRI -> X-ray, CT, US
            # CT alternatives
            "70450": ["70030", "76506"],  # CT head -> X-ray skull, US
            "74150": ["74000", "76700"],  # CT abdomen -> X-ray, US abdomen
            "71250": ["71020", "76604"],  # CT chest -> X-ray chest, US chest
            # X-ray alternatives (limited alternatives, mostly clinical)
            "73030": ["clinical_evaluation"],  # Shoulder X-ray -> clinical eval
            "73610": ["clinical_evaluation"],  # Knee X-ray -> clinical eval
        }

        # Medical necessity criteria by procedure type
        self.necessity_criteria = {
            ProcedureType.MRI: {
                "required_duration": 6,  # weeks of conservative treatment
                "required_symptoms": [
                    "pain",
                    "limited_mobility",
                    "neurological_symptoms",
                ],
                "contraindications": [
                    "claustrophobia",
                    "metallic_implants",
                    "pacemaker",
                ],
            },
            ProcedureType.CT_SCAN: {
                "required_duration": 4,  # weeks of conservative treatment
                "required_symptoms": ["acute_pain", "trauma", "suspected_fracture"],
                "contraindications": ["pregnancy", "contrast_allergy"],
            },
            ProcedureType.X_RAY: {
                "required_duration": 2,  # weeks of symptoms
                "required_symptoms": ["pain", "trauma", "deformity"],
                "contraindications": ["pregnancy"],
            },
        }

    def generate_detailed_reasoning(
        self,
        request: AuthorizationRequest,
        validation_result: ValidationResult,
        policy_result: Optional[PolicyValidationResult] = None,
        comprehensive_validation: Optional[Dict[str, Any]] = None,
    ) -> List[ReasoningElement]:
        """
        Generate detailed reasoning elements for a decision.

        Args:
            request: Authorization request
            validation_result: Basic validation result
            policy_result: Policy validation result
            comprehensive_validation: Comprehensive validation results

        Returns:
            List of structured reasoning elements
        """
        try:
            reasoning_elements = []

            # Generate medical necessity reasoning
            medical_reasoning = self._generate_medical_necessity_reasoning(
                request, comprehensive_validation
            )
            reasoning_elements.extend(medical_reasoning)

            # Generate policy compliance reasoning
            policy_reasoning = self._generate_policy_compliance_reasoning(
                request, policy_result, comprehensive_validation
            )
            reasoning_elements.extend(policy_reasoning)

            # Generate CMS guidelines reasoning
            cms_reasoning = self._generate_cms_guidelines_reasoning(
                request, comprehensive_validation
            )
            reasoning_elements.extend(cms_reasoning)

            # Generate clinical criteria reasoning
            clinical_reasoning = self._generate_clinical_criteria_reasoning(
                request, validation_result
            )
            reasoning_elements.extend(clinical_reasoning)

            # Generate documentation reasoning
            documentation_reasoning = self._generate_documentation_reasoning(
                request, validation_result
            )
            reasoning_elements.extend(documentation_reasoning)

            self.logger.info(
                "Generated detailed reasoning",
                request_id=request.request_id,
                reasoning_count=len(reasoning_elements),
            )

            return reasoning_elements

        except Exception as e:
            request_id = request.request_id if request else "unknown"
            self.logger.error(
                "Failed to generate detailed reasoning",
                request_id=request_id,
                error=str(e),
                exc_info=True,
            )

            # Return basic reasoning on error
            return [
                ReasoningElement(
                    category=ReasoningCategory.DOCUMENTATION,
                    statement="Unable to generate detailed reasoning due to system error",
                    confidence_level="low",
                )
            ]

    def create_decision_documentation(
        self,
        decision: AuthorizationDecision,
        request: AuthorizationRequest,
        reasoning_elements: List[ReasoningElement],
        validation_context: Optional[Dict[str, Any]] = None,
    ) -> DecisionDocumentation:
        """
        Create structured decision documentation for audit trail.

        Args:
            decision: Authorization decision
            request: Original authorization request
            reasoning_elements: Detailed reasoning elements
            validation_context: Additional validation context

        Returns:
            Structured decision documentation
        """
        try:
            # Extract clinical factors
            clinical_factors = self._extract_clinical_factors(
                request, validation_context
            )

            # Perform risk assessment
            risk_assessment = self._perform_risk_assessment(
                request, decision, reasoning_elements
            )

            # Generate alternative procedures if denied
            alternative_procedures = []
            if decision.status == DecisionStatus.DENIED:
                alternative_procedures = self._generate_detailed_alternatives(request)

            # Create audit trail
            audit_trail = self._create_audit_trail(
                request, decision, reasoning_elements
            )

            documentation = DecisionDocumentation(
                decision_id=decision.decision_id,
                request_id=decision.request_id,
                decision_timestamp=decision.decided_at,
                decision_status=decision.status,
                reasoning_elements=reasoning_elements,
                policy_references=decision.policy_references,
                clinical_factors=clinical_factors,
                risk_assessment=risk_assessment,
                alternative_procedures=alternative_procedures,
                audit_trail=audit_trail,
            )

            self.logger.info(
                "Created decision documentation",
                decision_id=decision.decision_id,
                request_id=decision.request_id,
                reasoning_count=len(reasoning_elements),
                alternatives_count=len(alternative_procedures),
            )

            return documentation

        except Exception as e:
            self.logger.error(
                "Failed to create decision documentation",
                decision_id=decision.decision_id,
                error=str(e),
                exc_info=True,
            )
            raise

    def generate_alternative_procedures(
        self, request: AuthorizationRequest, denial_reasons: List[str]
    ) -> List[Dict[str, str]]:
        """
        Generate alternative procedure suggestions for denied requests.

        Args:
            request: Authorization request
            denial_reasons: Reasons for denial

        Returns:
            List of alternative procedures with details
        """
        try:
            alternatives = []

            # Get primary procedure codes
            procedure_codes = [code.code for code in request.procedure_codes]

            for code in procedure_codes:
                # Get code-specific alternatives
                code_alternatives = self._get_procedure_alternatives(
                    code, request.procedure_type
                )
                alternatives.extend(code_alternatives)

                # Get diagnosis-specific alternatives
                diagnosis_alternatives = self._get_diagnosis_specific_alternatives(
                    code, request.diagnosis_codes, denial_reasons
                )
                alternatives.extend(diagnosis_alternatives)

            # Add general alternatives based on denial reasons
            general_alternatives = self._get_general_alternatives(
                denial_reasons, request
            )
            alternatives.extend(general_alternatives)

            # Remove duplicates and sort by preference
            unique_alternatives = self._deduplicate_and_rank_alternatives(alternatives)

            self.logger.info(
                "Generated alternative procedures",
                request_id=request.request_id,
                alternatives_count=len(unique_alternatives),
            )

            return unique_alternatives

        except Exception as e:
            self.logger.error(
                "Failed to generate alternative procedures",
                request_id=request.request_id,
                error=str(e),
                exc_info=True,
            )

            # Return basic alternatives on error
            return [
                {
                    "procedure_code": "clinical_evaluation",
                    "description": "Clinical evaluation and conservative treatment",
                    "rationale": "Consider non-imaging approaches for initial assessment",
                    "cost_impact": "Lower cost alternative",
                    "clinical_appropriateness": "Appropriate for initial evaluation",
                }
            ]

    def _generate_medical_necessity_reasoning(
        self,
        request: AuthorizationRequest,
        comprehensive_validation: Optional[Dict[str, Any]],
    ) -> List[ReasoningElement]:
        """Generate medical necessity reasoning elements."""
        elements = []

        if (
            not comprehensive_validation
            or "medical_necessity" not in comprehensive_validation
        ):
            return elements

        medical_necessity = comprehensive_validation["medical_necessity"]
        necessity_level = medical_necessity.get("necessity_level", "unknown")
        confidence_score = medical_necessity.get("confidence_score", 0.5)

        # Main necessity assessment
        if necessity_level == "high":
            elements.append(
                ReasoningElement(
                    category=ReasoningCategory.MEDICAL_NECESSITY,
                    statement=f"High medical necessity established (confidence: {confidence_score:.2f})",
                    confidence_level="high",
                    supporting_evidence=medical_necessity.get("supporting_factors", []),
                )
            )
        elif necessity_level == "moderate":
            elements.append(
                ReasoningElement(
                    category=ReasoningCategory.MEDICAL_NECESSITY,
                    statement=f"Moderate medical necessity demonstrated (confidence: {confidence_score:.2f})",
                    confidence_level="moderate",
                    supporting_evidence=medical_necessity.get("supporting_factors", []),
                )
            )
        else:
            elements.append(
                ReasoningElement(
                    category=ReasoningCategory.MEDICAL_NECESSITY,
                    statement=f"Insufficient medical necessity demonstrated (confidence: {confidence_score:.2f})",
                    confidence_level="low",
                    supporting_evidence=medical_necessity.get("missing_factors", []),
                )
            )

        # Add specific necessity factors
        necessity_factors = medical_necessity.get("evaluation_factors", {})

        # Conservative treatment duration
        treatment_duration = necessity_factors.get("conservative_treatment_duration", 0)
        required_duration = self.necessity_criteria.get(request.procedure_type, {}).get(
            "required_duration", 4
        )

        if treatment_duration >= required_duration:
            elements.append(
                ReasoningElement(
                    category=ReasoningCategory.MEDICAL_NECESSITY,
                    statement=f"Adequate conservative treatment duration documented ({treatment_duration} weeks)",
                    confidence_level="high",
                )
            )
        else:
            elements.append(
                ReasoningElement(
                    category=ReasoningCategory.MEDICAL_NECESSITY,
                    statement=f"Insufficient conservative treatment duration ({treatment_duration} weeks, {required_duration} required)",
                    confidence_level="high",
                )
            )

        # Symptom severity
        symptom_severity = necessity_factors.get("symptom_severity", "unknown")
        if symptom_severity in ["severe", "moderate"]:
            elements.append(
                ReasoningElement(
                    category=ReasoningCategory.MEDICAL_NECESSITY,
                    statement=f"Documented {symptom_severity} symptom severity supports imaging need",
                    confidence_level="moderate",
                )
            )

        return elements

    def _generate_policy_compliance_reasoning(
        self,
        request: AuthorizationRequest,
        policy_result: Optional[PolicyValidationResult],
        comprehensive_validation: Optional[Dict[str, Any]],
    ) -> List[ReasoningElement]:
        """Generate policy compliance reasoning elements."""
        elements = []

        # Use policy_result if available, otherwise extract from comprehensive validation
        if policy_result:
            if policy_result.is_covered:
                elements.append(
                    ReasoningElement(
                        category=ReasoningCategory.POLICY_COMPLIANCE,
                        statement="Request meets payer coverage policy requirements",
                        policy_reference=policy_result.policy_id,
                        confidence_level="high",
                        supporting_evidence=policy_result.reasoning,
                    )
                )
            else:
                elements.append(
                    ReasoningElement(
                        category=ReasoningCategory.POLICY_COMPLIANCE,
                        statement="Request does not meet payer coverage policy requirements",
                        policy_reference=policy_result.policy_id,
                        confidence_level="high",
                        supporting_evidence=policy_result.reasoning,
                    )
                )

        elif (
            comprehensive_validation and "policy_validation" in comprehensive_validation
        ):
            policy_validation = comprehensive_validation["policy_validation"]
            is_covered = policy_validation.get("is_covered", False)

            if is_covered:
                elements.append(
                    ReasoningElement(
                        category=ReasoningCategory.POLICY_COMPLIANCE,
                        statement="Request complies with applicable coverage policies",
                        confidence_level="moderate",
                    )
                )
            else:
                elements.append(
                    ReasoningElement(
                        category=ReasoningCategory.POLICY_COMPLIANCE,
                        statement="Request does not comply with coverage policy requirements",
                        confidence_level="moderate",
                    )
                )

        return elements

    def _generate_cms_guidelines_reasoning(
        self,
        request: AuthorizationRequest,
        comprehensive_validation: Optional[Dict[str, Any]],
    ) -> List[ReasoningElement]:
        """Generate CMS guidelines reasoning elements."""
        elements = []

        if (
            not comprehensive_validation
            or "cms_compliance" not in comprehensive_validation
        ):
            return elements

        cms_compliance = comprehensive_validation["cms_compliance"]
        is_compliant = cms_compliance.get("is_compliant", True)

        if is_compliant:
            elements.append(
                ReasoningElement(
                    category=ReasoningCategory.CMS_GUIDELINES,
                    statement="Request complies with CMS National and Local Coverage Determinations",
                    confidence_level="high",
                )
            )
        else:
            compliance_issues = cms_compliance.get("compliance_issues", [])
            elements.append(
                ReasoningElement(
                    category=ReasoningCategory.CMS_GUIDELINES,
                    statement="Request does not comply with CMS guidelines",
                    confidence_level="high",
                    supporting_evidence=compliance_issues,
                )
            )

        # Add specific NCD/LCD references
        ncd_policies = cms_compliance.get("ncd_policies", [])
        for policy in ncd_policies:
            policy_name = policy.get("policy_name", "Unknown NCD")
            is_compliant_policy = policy.get("is_compliant", False)

            elements.append(
                ReasoningElement(
                    category=ReasoningCategory.CMS_GUIDELINES,
                    statement=f"{'Complies with' if is_compliant_policy else 'Does not comply with'} {policy_name}",
                    policy_reference=f"CMS NCD: {policy_name}",
                    confidence_level="high",
                )
            )

        lcd_policies = cms_compliance.get("lcd_policies", [])
        for policy in lcd_policies:
            policy_name = policy.get("policy_name", "Unknown LCD")
            is_compliant_policy = policy.get("is_compliant", False)

            elements.append(
                ReasoningElement(
                    category=ReasoningCategory.CMS_GUIDELINES,
                    statement=f"{'Complies with' if is_compliant_policy else 'Does not comply with'} {policy_name}",
                    policy_reference=f"CMS LCD: {policy_name}",
                    confidence_level="high",
                )
            )

        return elements

    def _generate_clinical_criteria_reasoning(
        self, request: AuthorizationRequest, validation_result: ValidationResult
    ) -> List[ReasoningElement]:
        """Generate clinical criteria reasoning elements."""
        elements = []

        # Validate diagnosis and procedure code alignment
        diagnosis_codes = [code.code for code in request.diagnosis_codes]
        procedure_codes = [code.code for code in request.procedure_codes]

        # Check for appropriate diagnosis-procedure alignment
        alignment_assessment = self._assess_diagnosis_procedure_alignment(
            diagnosis_codes, procedure_codes, request.procedure_type
        )

        elements.append(
            ReasoningElement(
                category=ReasoningCategory.CLINICAL_CRITERIA,
                statement=alignment_assessment["statement"],
                confidence_level=alignment_assessment["confidence"],
                supporting_evidence=alignment_assessment.get("evidence", []),
            )
        )

        # Assess urgency appropriateness
        urgency_assessment = self._assess_urgency_appropriateness(request)
        if urgency_assessment:
            elements.append(urgency_assessment)

        # Check for contraindications
        contraindication_assessment = self._assess_contraindications(request)
        if contraindication_assessment:
            elements.extend(contraindication_assessment)

        return elements

    def _generate_documentation_reasoning(
        self, request: AuthorizationRequest, validation_result: ValidationResult
    ) -> List[ReasoningElement]:
        """Generate documentation quality reasoning elements."""
        elements = []

        # Assess clinical notes quality
        if request.clinical_notes:
            notes_assessment = self._assess_clinical_notes_quality(
                request.clinical_notes
            )
            elements.append(
                ReasoningElement(
                    category=ReasoningCategory.DOCUMENTATION,
                    statement=notes_assessment["statement"],
                    confidence_level=notes_assessment["confidence"],
                    supporting_evidence=notes_assessment.get("evidence", []),
                )
            )
        else:
            elements.append(
                ReasoningElement(
                    category=ReasoningCategory.DOCUMENTATION,
                    statement="No clinical notes provided to support medical necessity",
                    confidence_level="high",
                )
            )

        # Assess code validity and completeness
        if validation_result.is_valid:
            elements.append(
                ReasoningElement(
                    category=ReasoningCategory.DOCUMENTATION,
                    statement="All medical codes are valid and properly formatted",
                    confidence_level="high",
                )
            )
        else:
            error_messages = [error.message for error in validation_result.errors]
            elements.append(
                ReasoningElement(
                    category=ReasoningCategory.DOCUMENTATION,
                    statement="Medical code validation issues identified",
                    confidence_level="high",
                    supporting_evidence=error_messages,
                )
            )

        return elements

    def _extract_clinical_factors(
        self,
        request: AuthorizationRequest,
        validation_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Extract clinical factors for documentation."""
        factors = {
            "patient_age": request.patient_demographics.age,
            "patient_gender": request.patient_demographics.gender.value,
            "procedure_type": request.procedure_type.value,
            "urgency_level": request.urgency_level.value,
            "diagnosis_count": len(request.diagnosis_codes),
            "procedure_count": len(request.procedure_codes),
            "clinical_notes_provided": bool(request.clinical_notes),
            "primary_diagnosis": (
                request.diagnosis_codes[0].code if request.diagnosis_codes else None
            ),
            "primary_procedure": (
                request.procedure_codes[0].code if request.procedure_codes else None
            ),
        }

        # Add validation context factors
        if validation_context:
            medical_necessity = validation_context.get("medical_necessity", {})
            factors.update(
                {
                    "medical_necessity_level": medical_necessity.get("necessity_level"),
                    "medical_necessity_confidence": medical_necessity.get(
                        "confidence_score"
                    ),
                    "conservative_treatment_duration": medical_necessity.get(
                        "evaluation_factors", {}
                    ).get("conservative_treatment_duration"),
                    "symptom_severity": medical_necessity.get(
                        "evaluation_factors", {}
                    ).get("symptom_severity"),
                }
            )

        return factors

    def _perform_risk_assessment(
        self,
        request: AuthorizationRequest,
        decision: AuthorizationDecision,
        reasoning_elements: List[ReasoningElement],
    ) -> Dict[str, Any]:
        """Perform risk assessment for the decision."""
        risk_factors = []
        risk_level = "low"

        # Assess clinical risk factors
        if request.urgency_level.value == "urgent":
            risk_factors.append(
                "Urgent clinical situation may require expedited imaging"
            )
            risk_level = "moderate"

        # Assess age-related risks
        if request.patient_demographics.age >= 65:
            risk_factors.append("Advanced age may increase clinical complexity")
            if risk_level == "low":
                risk_level = "moderate"
        elif request.patient_demographics.age <= 18:
            risk_factors.append("Pediatric patient requires special consideration")
            if risk_level == "low":
                risk_level = "moderate"

        # Assess decision confidence risk
        if decision.confidence_score < 0.7:
            risk_factors.append(
                "Lower decision confidence may require additional review"
            )
            risk_level = "moderate"

        # Assess denial risks
        if decision.status == DecisionStatus.DENIED:
            # Check for high medical necessity with denial
            medical_necessity_elements = [
                elem
                for elem in reasoning_elements
                if elem.category == ReasoningCategory.MEDICAL_NECESSITY
                and elem.confidence_level == "high"
            ]
            if medical_necessity_elements:
                risk_factors.append(
                    "High medical necessity with denial may require peer review"
                )
                risk_level = "high"

        return {
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "requires_peer_review": risk_level == "high",
            "requires_expedited_processing": request.urgency_level.value == "urgent",
            "assessment_timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _generate_detailed_alternatives(
        self, request: AuthorizationRequest
    ) -> List[Dict[str, str]]:
        """Generate detailed alternative procedures for denied requests."""
        alternatives = []

        # Get procedure-specific alternatives
        for procedure_code in request.procedure_codes:
            code_alternatives = self._get_procedure_alternatives(
                procedure_code.code, request.procedure_type
            )
            alternatives.extend(code_alternatives)

        # Add conservative treatment alternatives
        conservative_alternatives = self._get_conservative_alternatives(request)
        alternatives.extend(conservative_alternatives)

        return alternatives

    def _create_audit_trail(
        self,
        request: AuthorizationRequest,
        decision: AuthorizationDecision,
        reasoning_elements: List[ReasoningElement],
    ) -> List[Dict[str, Any]]:
        """Create audit trail for decision documentation."""
        audit_events = []

        # Request submission event
        audit_events.append(
            {
                "event_type": "request_submitted",
                "timestamp": request.submitted_at.isoformat(),
                "details": {
                    "provider_id": request.provider_id,
                    "procedure_type": request.procedure_type.value,
                    "urgency_level": request.urgency_level.value,
                },
            }
        )

        # Decision generation event
        audit_events.append(
            {
                "event_type": "decision_generated",
                "timestamp": decision.decided_at.isoformat(),
                "details": {
                    "decision_status": decision.status.value,
                    "confidence_score": decision.confidence_score,
                    "reasoning_categories": list(
                        set([elem.category.value for elem in reasoning_elements])
                    ),
                    "policy_references_count": len(decision.policy_references),
                },
            }
        )

        # Authorization number generation (if applicable)
        if decision.authorization_number:
            audit_events.append(
                {
                    "event_type": "authorization_generated",
                    "timestamp": decision.decided_at.isoformat(),
                    "details": {
                        "authorization_number": decision.authorization_number,
                        "valid_until": (
                            decision.valid_until.isoformat()
                            if decision.valid_until
                            else None
                        ),
                    },
                }
            )

        return audit_events

    def _get_procedure_alternatives(
        self, procedure_code: str, procedure_type: ProcedureType
    ) -> List[Dict[str, str]]:
        """Get alternative procedures for a specific code."""
        alternatives = []

        # Get mapped alternatives
        alternative_codes = self.procedure_alternatives.get(procedure_code, [])

        for alt_code in alternative_codes:
            if alt_code == "clinical_evaluation":
                alternatives.append(
                    {
                        "procedure_code": "clinical_evaluation",
                        "description": "Clinical evaluation and physical examination",
                        "rationale": "Non-imaging assessment may provide sufficient diagnostic information",
                        "cost_impact": "Significantly lower cost",
                        "clinical_appropriateness": "Appropriate for initial evaluation of symptoms",
                    }
                )
            else:
                # Map procedure codes to descriptions
                alt_description = self._get_procedure_description(alt_code)
                alternatives.append(
                    {
                        "procedure_code": alt_code,
                        "description": alt_description,
                        "rationale": f"Less expensive alternative to {procedure_code}",
                        "cost_impact": "Lower cost alternative",
                        "clinical_appropriateness": "May provide adequate diagnostic information",
                    }
                )

        return alternatives

    def _get_diagnosis_specific_alternatives(
        self, procedure_code: str, diagnosis_codes: List, denial_reasons: List[str]
    ) -> List[Dict[str, str]]:
        """Get alternatives based on specific diagnosis codes."""
        alternatives = []

        # Extract primary diagnosis
        if not diagnosis_codes:
            return alternatives

        primary_diagnosis = diagnosis_codes[0].code

        # Musculoskeletal conditions
        if primary_diagnosis.startswith("M"):
            alternatives.append(
                {
                    "procedure_code": "physical_therapy",
                    "description": "Physical therapy evaluation and treatment",
                    "rationale": "Conservative treatment appropriate for musculoskeletal conditions",
                    "cost_impact": "Lower cost than imaging",
                    "clinical_appropriateness": "First-line treatment for many musculoskeletal conditions",
                }
            )

        # Pain-related diagnoses
        if "pain" in denial_reasons or any(
            "pain" in reason.lower() for reason in denial_reasons
        ):
            alternatives.append(
                {
                    "procedure_code": "pain_management",
                    "description": "Pain management consultation",
                    "rationale": "Specialized pain evaluation may guide treatment without imaging",
                    "cost_impact": "Moderate cost",
                    "clinical_appropriateness": "Appropriate for chronic pain conditions",
                }
            )

        return alternatives

    def _get_general_alternatives(
        self, denial_reasons: List[str], request: AuthorizationRequest
    ) -> List[Dict[str, str]]:
        """Get general alternatives based on denial reasons."""
        alternatives = []

        # Conservative treatment
        alternatives.append(
            {
                "procedure_code": "conservative_treatment",
                "description": "Conservative treatment with follow-up evaluation",
                "rationale": "Trial of conservative treatment before advanced imaging",
                "cost_impact": "Significantly lower cost",
                "clinical_appropriateness": "Appropriate first-line approach for many conditions",
            }
        )

        # Specialist consultation
        alternatives.append(
            {
                "procedure_code": "specialist_consultation",
                "description": "Specialist consultation for clinical evaluation",
                "rationale": "Specialist evaluation may clarify need for imaging",
                "cost_impact": "Moderate cost",
                "clinical_appropriateness": "Provides expert clinical assessment",
            }
        )

        return alternatives

    def _get_conservative_alternatives(
        self, request: AuthorizationRequest
    ) -> List[Dict[str, str]]:
        """Get conservative treatment alternatives."""
        alternatives = []

        # Based on procedure type
        if request.procedure_type in [ProcedureType.MRI, ProcedureType.CT_SCAN]:
            alternatives.extend(
                [
                    {
                        "procedure_code": "rest_and_activity_modification",
                        "description": "Rest and activity modification",
                        "rationale": "Conservative approach may resolve symptoms without imaging",
                        "cost_impact": "No additional cost",
                        "clinical_appropriateness": "Appropriate initial management for many conditions",
                    },
                    {
                        "procedure_code": "anti_inflammatory_treatment",
                        "description": "Anti-inflammatory medication trial",
                        "rationale": "Medical management may address underlying inflammation",
                        "cost_impact": "Low cost",
                        "clinical_appropriateness": "Standard treatment for inflammatory conditions",
                    },
                ]
            )

        return alternatives

    def _deduplicate_and_rank_alternatives(
        self, alternatives: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """Remove duplicates and rank alternatives by clinical appropriateness."""
        # Remove duplicates based on procedure code
        seen_codes = set()
        unique_alternatives = []

        for alt in alternatives:
            code = alt["procedure_code"]
            if code not in seen_codes:
                seen_codes.add(code)
                unique_alternatives.append(alt)

        # Rank by clinical appropriateness and cost
        ranking_order = [
            "clinical_evaluation",
            "conservative_treatment",
            "physical_therapy",
            "rest_and_activity_modification",
            "anti_inflammatory_treatment",
            "specialist_consultation",
            "pain_management",
        ]

        def get_rank(alt):
            code = alt["procedure_code"]
            try:
                return ranking_order.index(code)
            except ValueError:
                return len(ranking_order)  # Put unknown codes at the end

        unique_alternatives.sort(key=get_rank)

        return unique_alternatives[:5]  # Limit to top 5 alternatives

    def _assess_diagnosis_procedure_alignment(
        self,
        diagnosis_codes: List[str],
        procedure_codes: List[str],
        procedure_type: ProcedureType,
    ) -> Dict[str, Any]:
        """Assess alignment between diagnosis and procedure codes."""
        # Simplified alignment assessment
        primary_diagnosis = diagnosis_codes[0] if diagnosis_codes else None
        primary_procedure = procedure_codes[0] if procedure_codes else None

        if not primary_diagnosis or not primary_procedure:
            return {
                "statement": "Incomplete diagnosis or procedure code information",
                "confidence": "low",
                "evidence": ["Missing primary diagnosis or procedure code"],
            }

        # Basic alignment rules
        alignment_score = 0.5  # Default moderate alignment
        evidence = []

        # Musculoskeletal diagnoses with imaging
        if primary_diagnosis.startswith("M") and procedure_type in [
            ProcedureType.MRI,
            ProcedureType.X_RAY,
        ]:
            alignment_score = 0.8
            evidence.append(
                "Musculoskeletal diagnosis appropriate for imaging evaluation"
            )

        # Neurological diagnoses with brain/spine imaging
        if primary_diagnosis.startswith("G") and primary_procedure.startswith(
            "70"
        ):  # Head imaging
            alignment_score = 0.9
            evidence.append("Neurological diagnosis appropriate for head imaging")

        if alignment_score >= 0.8:
            statement = (
                "Strong clinical alignment between diagnosis and requested procedure"
            )
            confidence = "high"
        elif alignment_score >= 0.6:
            statement = (
                "Moderate clinical alignment between diagnosis and requested procedure"
            )
            confidence = "moderate"
        else:
            statement = "Questionable clinical alignment between diagnosis and requested procedure"
            confidence = "low"

        return {"statement": statement, "confidence": confidence, "evidence": evidence}

    def _assess_urgency_appropriateness(
        self, request: AuthorizationRequest
    ) -> Optional[ReasoningElement]:
        """Assess appropriateness of urgency level."""
        if request.urgency_level.value == "urgent":
            return ReasoningElement(
                category=ReasoningCategory.CLINICAL_CRITERIA,
                statement="Urgent priority level requires clinical justification",
                confidence_level="moderate",
            )
        return None

    def _assess_contraindications(
        self, request: AuthorizationRequest
    ) -> List[ReasoningElement]:
        """Assess potential contraindications for the procedure."""
        elements = []

        # Get contraindications for procedure type
        contraindications = self.necessity_criteria.get(request.procedure_type, {}).get(
            "contraindications", []
        )

        if contraindications:
            elements.append(
                ReasoningElement(
                    category=ReasoningCategory.CLINICAL_CRITERIA,
                    statement=f"Consider contraindications for {request.procedure_type.value}: {', '.join(contraindications)}",
                    confidence_level="moderate",
                )
            )

        return elements

    def _assess_clinical_notes_quality(self, clinical_notes: str) -> Dict[str, Any]:
        """Assess quality and completeness of clinical notes."""
        notes_lower = clinical_notes.lower()

        # Check for key elements
        has_symptoms = any(
            symptom in notes_lower
            for symptom in ["pain", "swelling", "weakness", "numbness"]
        )
        has_duration = any(
            duration in notes_lower
            for duration in ["weeks", "months", "days", "chronic"]
        )
        has_treatment = any(
            treatment in notes_lower
            for treatment in ["therapy", "medication", "treatment", "conservative"]
        )

        quality_score = sum([has_symptoms, has_duration, has_treatment]) / 3

        evidence = []
        if has_symptoms:
            evidence.append("Symptoms documented")
        if has_duration:
            evidence.append("Duration of symptoms noted")
        if has_treatment:
            evidence.append("Previous treatment documented")

        if quality_score >= 0.8:
            statement = "Comprehensive clinical notes support medical necessity"
            confidence = "high"
        elif quality_score >= 0.5:
            statement = "Adequate clinical documentation provided"
            confidence = "moderate"
        else:
            statement = (
                "Limited clinical documentation may not fully support medical necessity"
            )
            confidence = "moderate"

        return {"statement": statement, "confidence": confidence, "evidence": evidence}

    def _get_procedure_description(self, procedure_code: str) -> str:
        """Get description for procedure code."""
        # Simplified procedure code descriptions
        descriptions = {
            "73200": "X-ray upper extremity",
            "73218": "CT upper extremity",
            "76881": "Ultrasound upper extremity",
            "73610": "X-ray knee",
            "73700": "CT lower extremity",
            "76882": "Ultrasound lower extremity",
            "70450": "CT head without contrast",
            "70460": "CT head with contrast",
            "76506": "Ultrasound head/neck",
            "72100": "X-ray spine",
            "72125": "CT spine",
            "76775": "Ultrasound spine",
            "70030": "X-ray skull",
            "74000": "X-ray abdomen",
            "76700": "Ultrasound abdomen",
            "71020": "X-ray chest",
            "76604": "Ultrasound chest",
        }

        return descriptions.get(procedure_code, f"Procedure code {procedure_code}")

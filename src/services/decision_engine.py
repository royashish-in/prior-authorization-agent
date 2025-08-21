"""
Decision engine service for generating authorization decisions.

This module implements the core decision logic that processes validation results
and generates authorization decisions with reasoning, confidence scoring,
and authorization number generation. Enhanced with LLM integration for
AI-powered medical reasoning while maintaining backward compatibility.
"""

import uuid
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum

from src.models.authorization import AuthorizationRequest, AuthorizationDecision
from src.models.enums import DecisionStatus, UrgencyLevel
from src.services.validation import ValidationResult
from src.services.policy_validation import PolicyValidationResult
from src.services.reasoning import ReasoningEngine, DecisionDocumentation
from src.services.llm_decision_service import (
    llm_decision_service,
    LLMDecisionResponse,
    LLMDecisionStatus,
    PolicyComplianceResult as LLMPolicyComplianceResult,
)
from src.services.prompt_engineering import PolicyContext
from src.core.logging import get_logger
from src.core.exceptions import ValidationException


class DecisionMode(Enum):
    """Decision-making mode enumeration."""

    RULE_BASED_ONLY = "rule_based_only"
    LLM_ONLY = "llm_only"
    HYBRID = "hybrid"
    AUTO_SELECT = "auto_select"


@dataclass
class DecisionContext:
    """Context information for decision generation."""

    request: AuthorizationRequest
    validation_result: ValidationResult
    policy_result: Optional[PolicyValidationResult] = None
    cms_compliance: Optional[Dict[str, Any]] = None
    medical_necessity: Optional[Dict[str, Any]] = None


@dataclass
class HybridDecisionResult:
    """Result of hybrid decision-making process."""

    final_decision: AuthorizationDecision
    llm_decision: Optional[LLMDecisionResponse] = None
    rule_based_decision: Optional[AuthorizationDecision] = None
    decision_method: str = "unknown"
    confidence_comparison: Optional[Dict[str, float]] = None
    reasoning_sources: List[str] = None


class DecisionEngine:
    """
    Enhanced decision engine for authorization requests with LLM integration.

    Generates authorization decisions using hybrid approach that combines
    LLM-powered medical reasoning with rule-based validation while maintaining
    backward compatibility with existing rule-based decisions.
    """

    def __init__(self, decision_mode: DecisionMode = DecisionMode.AUTO_SELECT):
        """Initialize the enhanced decision engine."""
        self.logger = get_logger(self.__class__.__name__)

        # Initialize reasoning engine
        self.reasoning_engine = ReasoningEngine()

        # Decision mode configuration
        self.decision_mode = decision_mode
        self.llm_enabled = decision_mode in [
            DecisionMode.LLM_ONLY,
            DecisionMode.HYBRID,
            DecisionMode.AUTO_SELECT,
        ]

        # Decision thresholds
        self.approval_confidence_threshold = 0.8
        self.denial_confidence_threshold = 0.6
        self.llm_confidence_threshold = 0.7  # Minimum confidence for LLM decisions

        # Authorization validity period (30 days)
        self.authorization_validity_days = 30

        # Hybrid decision weights (configurable for different payers/scenarios)
        self.llm_weight = 0.7  # Weight for LLM decisions in hybrid mode
        self.rule_weight = 0.3  # Weight for rule-based decisions in hybrid mode

        # Performance tracking
        self._decision_metrics = {
            "total_decisions": 0,
            "llm_decisions": 0,
            "rule_based_decisions": 0,
            "hybrid_decisions": 0,
            "fallback_decisions": 0,
        }

        # Initialize LLM service if enabled
        self._llm_initialized = False

    def generate_decision(
        self,
        request: AuthorizationRequest,
        validation_result: ValidationResult,
        policy_result: Optional[PolicyValidationResult] = None,
        comprehensive_validation: Optional[Dict[str, Any]] = None,
        enhanced_context: Optional[Dict[str, Any]] = None,
    ) -> AuthorizationDecision:
        """
        Generate an authorization decision based on validation results.

        This method maintains backward compatibility with existing rule-based decisions
        while supporting enhanced LLM integration when available.

        Args:
            request: Authorization request
            validation_result: Basic validation result
            policy_result: Policy validation result (optional)
            comprehensive_validation: Comprehensive validation including medical necessity
            enhanced_context: Enhanced medical context for improved decision-making

        Returns:
            AuthorizationDecision with complete decision information
        """
        try:
            # Validate input parameters
            if request is None:
                self.logger.error("Decision generation failed: request cannot be None")
                return self._generate_error_decision(
                    None, "Invalid request: request cannot be None"
                )

            # For backward compatibility, if LLM is disabled, use pure rule-based approach
            if (
                not self.llm_enabled
                or self.decision_mode == DecisionMode.RULE_BASED_ONLY
            ):
                return self._generate_rule_based_decision_sync(
                    request,
                    validation_result,
                    policy_result,
                    comprehensive_validation,
                    enhanced_context,
                )

            # For LLM-enabled modes, we need to use async processing
            # This sync method will be deprecated in favor of generate_enhanced_decision
            self.logger.warning(
                "Using synchronous decision generation with LLM enabled. "
                "Consider using generate_enhanced_decision for full LLM capabilities."
            )

            return self._generate_rule_based_decision_sync(
                request,
                validation_result,
                policy_result,
                comprehensive_validation,
                enhanced_context,
            )

        except Exception as e:
            self.logger.error(
                "Decision generation failed",
                request_id=request.request_id,
                error=str(e),
                exc_info=True,
            )

            # Return denial decision for system errors
            return self._generate_error_decision(request, str(e))

    def _generate_rule_based_decision_sync(
        self,
        request: AuthorizationRequest,
        validation_result: ValidationResult,
        policy_result: Optional[PolicyValidationResult] = None,
        comprehensive_validation: Optional[Dict[str, Any]] = None,
        enhanced_context: Optional[Dict[str, Any]] = None,
    ) -> AuthorizationDecision:
        """
        Generate a rule-based decision synchronously for backward compatibility.

        Args:
            request: Authorization request
            validation_result: Basic validation result
            policy_result: Policy validation result (optional)
            comprehensive_validation: Comprehensive validation including medical necessity
            enhanced_context: Enhanced medical context for improved decision-making

        Returns:
            AuthorizationDecision with complete decision information
        """
        # Create decision context
        context = DecisionContext(
            request=request,
            validation_result=validation_result,
            policy_result=policy_result,
        )

        # Extract additional context from comprehensive validation
        if comprehensive_validation and isinstance(comprehensive_validation, dict):
            context.cms_compliance = comprehensive_validation.get("cms_compliance")
            context.medical_necessity = comprehensive_validation.get(
                "medical_necessity"
            )
            context.policy_result = self._extract_policy_result_from_comprehensive(
                comprehensive_validation.get("policy_validation", {})
            )

        # Incorporate enhanced medical context if provided
        if enhanced_context:
            # Enhanced context can improve confidence scores and reasoning
            self.logger.info(
                "Using enhanced medical context for decision generation",
                request_id=request.request_id,
                context_fields=list(enhanced_context.keys()),
            )

        # Generate decision based on context
        decision_status, reasoning, confidence_score = self._evaluate_decision(context)

        # Generate decision ID
        decision_id = self._generate_decision_id()

        # Generate authorization number if approved
        authorization_number = None
        valid_until = None
        if decision_status == DecisionStatus.APPROVED:
            authorization_number = self._generate_authorization_number()
            valid_until = datetime.now(timezone.utc) + timedelta(
                days=self.authorization_validity_days
            )

        # Collect policy references
        policy_references = self._collect_policy_references(context)

        # Generate additional information needed if applicable
        additional_info_needed = None
        if decision_status == DecisionStatus.MORE_INFO_NEEDED:
            additional_info_needed = self._generate_additional_info_requirements(
                context
            )

        # Generate alternative procedures if denied
        alternative_procedures = None
        if decision_status == DecisionStatus.DENIED:
            detailed_alternatives = (
                self.reasoning_engine.generate_alternative_procedures(
                    request, reasoning
                )
            )
            # Convert to simple string list for compatibility
            alternative_procedures = [
                alt["description"] for alt in detailed_alternatives
            ]

        # Create decision
        decision = AuthorizationDecision(
            decision_id=decision_id,
            request_id=request.request_id,
            status=decision_status,
            reasoning=reasoning,
            policy_references=policy_references,
            authorization_number=authorization_number,
            valid_until=valid_until,
            confidence_score=confidence_score,
            decided_at=datetime.now(timezone.utc),
            additional_info_needed=additional_info_needed,
            alternative_procedures=alternative_procedures,
        )

        self.logger.info(
            "Rule-based decision generated successfully",
            request_id=request.request_id,
            decision_id=decision_id,
            status=decision_status.value,
            confidence_score=confidence_score,
            authorization_number=authorization_number,
        )

        return decision

    async def route_request_to_llm(
        self,
        request: AuthorizationRequest,
        validation_result: ValidationResult,
        policy_result: Optional[PolicyValidationResult] = None,
        comprehensive_validation: Optional[Dict[str, Any]] = None,
        payer_id: str = "default_payer",
    ) -> AuthorizationDecision:
        """
        Route authorization request to LLM for medical reasoning and decision-making.

        This method implements requirement 1.1: "WHEN the system receives a prior
        authorization request THEN it SHALL route the request to a Hugging Face LLM
        for medical reasoning and decision-making"

        Args:
            request: Authorization request
            validation_result: Basic validation result
            policy_result: Policy validation result (optional)
            comprehensive_validation: Comprehensive validation including medical necessity
            payer_id: Payer identifier for policy context

        Returns:
            AuthorizationDecision from LLM processing with fallback support
        """
        try:
            self.logger.info(
                f"Routing request {request.request_id} to LLM for decision-making"
            )

            # Generate enhanced decision using hybrid approach
            hybrid_result = await self.generate_enhanced_decision(
                request,
                validation_result,
                policy_result,
                comprehensive_validation,
                payer_id,
            )

            # Log the decision method used
            self.logger.info(
                f"Request {request.request_id} processed using {hybrid_result.decision_method} method"
            )

            return hybrid_result.final_decision

        except Exception as e:
            self.logger.error(
                f"LLM routing failed for request {request.request_id}: {str(e)}",
                exc_info=True,
            )

            # Fallback to rule-based decision as per requirement 1.5
            self.logger.info(
                f"Falling back to rule-based decision for request {request.request_id}"
            )
            return self.generate_decision(
                request, validation_result, policy_result, comprehensive_validation
            )

    async def generate_enhanced_decision(
        self,
        request: AuthorizationRequest,
        validation_result: ValidationResult,
        policy_result: Optional[PolicyValidationResult] = None,
        comprehensive_validation: Optional[Dict[str, Any]] = None,
        payer_id: str = "default_payer",
    ) -> HybridDecisionResult:
        """
        Generate enhanced authorization decision using hybrid LLM and rule-based approach.

        Args:
            request: Authorization request
            validation_result: Basic validation result
            policy_result: Policy validation result (optional)
            comprehensive_validation: Comprehensive validation including medical necessity
            payer_id: Payer identifier for policy context

        Returns:
            HybridDecisionResult with enhanced decision information
        """
        try:
            # Initialize LLM service if needed
            if self.llm_enabled and not self._llm_initialized:
                await self._initialize_llm_service()

            # Determine decision method based on mode and request characteristics
            decision_method = self._select_decision_method(request, validation_result)

            if decision_method == "llm_only":
                result = await self._generate_llm_only_decision(
                    request,
                    validation_result,
                    policy_result,
                    comprehensive_validation,
                    payer_id,
                )
            elif decision_method == "rule_based_only":
                result = await self._generate_rule_based_only_decision(
                    request, validation_result, policy_result, comprehensive_validation
                )
            else:  # hybrid
                result = await self._generate_hybrid_decision(
                    request,
                    validation_result,
                    policy_result,
                    comprehensive_validation,
                    payer_id,
                )

            # Track the decision method used
            self._track_decision_method(result.decision_method)
            return result

        except Exception as e:
            self.logger.error(
                "Enhanced decision generation failed",
                request_id=request.request_id,
                error=str(e),
                exc_info=True,
            )

            # Fallback to rule-based decision
            rule_based_decision = self.generate_decision(
                request, validation_result, policy_result, comprehensive_validation
            )

            return HybridDecisionResult(
                final_decision=rule_based_decision,
                decision_method="fallback_rule_based",
                reasoning_sources=["rule_based_fallback"],
            )

    async def _initialize_llm_service(self):
        """Initialize the LLM decision service."""
        try:
            await llm_decision_service.initialize()
            self._llm_initialized = True
            self.logger.info("LLM service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize LLM service: {str(e)}")
            self.llm_enabled = False

    def _select_decision_method(
        self, request: AuthorizationRequest, validation_result: ValidationResult
    ) -> str:
        """
        Select the optimal decision method based on request characteristics and configuration.

        Args:
            request: Authorization request
            validation_result: Validation result

        Returns:
            Decision method: "llm_only", "rule_based_only", or "hybrid"
        """
        # If LLM is disabled, use rule-based only
        if not self.llm_enabled:
            return "rule_based_only"

        # Explicit mode selection
        if self.decision_mode == DecisionMode.LLM_ONLY:
            return "llm_only"
        elif self.decision_mode == DecisionMode.RULE_BASED_ONLY:
            return "rule_based_only"
        elif self.decision_mode == DecisionMode.HYBRID:
            return "hybrid"

        # Auto-select based on request characteristics
        complexity_score = self._calculate_request_complexity(
            request, validation_result
        )

        if complexity_score >= 0.8:
            # High complexity - use hybrid approach
            return "hybrid"
        elif complexity_score >= 0.5:
            # Medium complexity - use LLM only
            return "llm_only"
        else:
            # Low complexity - use rule-based only
            return "rule_based_only"

    def _calculate_request_complexity(
        self, request: AuthorizationRequest, validation_result: ValidationResult
    ) -> float:
        """
        Calculate complexity score for request to determine optimal decision method.

        Args:
            request: Authorization request
            validation_result: Validation result

        Returns:
            Complexity score (0.0-1.0)
        """
        complexity_factors = []

        # Multiple diagnosis codes increase complexity
        if len(request.diagnosis_codes) > 1:
            complexity_factors.append(0.2)

        # Multiple procedure codes increase complexity
        if len(request.procedure_codes) > 1:
            complexity_factors.append(0.2)

        # Urgent requests may need more nuanced reasoning
        if request.urgency_level == UrgencyLevel.URGENT:
            complexity_factors.append(0.3)

        # Extensive clinical notes suggest complex case
        if request.clinical_notes and len(request.clinical_notes) > 500:
            complexity_factors.append(0.2)

        # Validation warnings suggest edge cases
        if validation_result.warnings and len(validation_result.warnings) > 2:
            complexity_factors.append(0.1)

        return min(1.0, sum(complexity_factors))

    async def _generate_llm_only_decision(
        self,
        request: AuthorizationRequest,
        validation_result: ValidationResult,
        policy_result: Optional[PolicyValidationResult],
        comprehensive_validation: Optional[Dict[str, Any]],
        payer_id: str,
    ) -> HybridDecisionResult:
        """Generate decision using LLM only."""
        try:
            # Build policy context
            policy_context = self._build_policy_context(
                policy_result, comprehensive_validation, payer_id
            )

            # Get LLM decision
            llm_decision = await llm_decision_service.make_decision(
                request, policy_context
            )

            # Convert LLM decision to AuthorizationDecision
            final_decision = self._convert_llm_to_authorization_decision(
                llm_decision, request
            )

            return HybridDecisionResult(
                final_decision=final_decision,
                llm_decision=llm_decision,
                decision_method="llm_only",
                reasoning_sources=["llm_medical_reasoning"],
            )

        except Exception as e:
            self.logger.error(f"LLM-only decision failed: {str(e)}")
            # Fallback to rule-based
            return await self._generate_rule_based_only_decision(
                request, validation_result, policy_result, comprehensive_validation
            )

    async def _generate_rule_based_only_decision(
        self,
        request: AuthorizationRequest,
        validation_result: ValidationResult,
        policy_result: Optional[PolicyValidationResult],
        comprehensive_validation: Optional[Dict[str, Any]],
    ) -> HybridDecisionResult:
        """Generate decision using rule-based approach only."""
        rule_based_decision = self.generate_decision(
            request, validation_result, policy_result, comprehensive_validation
        )

        return HybridDecisionResult(
            final_decision=rule_based_decision,
            rule_based_decision=rule_based_decision,
            decision_method="rule_based_only",
            reasoning_sources=["rule_based_validation", "policy_compliance"],
        )

    async def _generate_hybrid_decision(
        self,
        request: AuthorizationRequest,
        validation_result: ValidationResult,
        policy_result: Optional[PolicyValidationResult],
        comprehensive_validation: Optional[Dict[str, Any]],
        payer_id: str,
    ) -> HybridDecisionResult:
        """
        Generate decision using hybrid approach that combines LLM and rule-based methods.

        Args:
            request: Authorization request
            validation_result: Validation result
            policy_result: Policy validation result
            comprehensive_validation: Comprehensive validation data
            payer_id: Payer identifier

        Returns:
            HybridDecisionResult with aggregated decision
        """
        try:
            # Generate both LLM and rule-based decisions in parallel
            llm_task = self._get_llm_decision_safe(
                request, policy_result, comprehensive_validation, payer_id
            )
            rule_task = self._get_rule_based_decision_safe(
                request, validation_result, policy_result, comprehensive_validation
            )

            # Wait for both decisions
            llm_decision, rule_based_decision = await asyncio.gather(
                llm_task, rule_task, return_exceptions=True
            )

            # Handle exceptions
            if isinstance(llm_decision, Exception):
                self.logger.warning(
                    f"LLM decision failed in hybrid mode: {str(llm_decision)}"
                )
                llm_decision = None

            if isinstance(rule_based_decision, Exception):
                self.logger.warning(
                    f"Rule-based decision failed in hybrid mode: {str(rule_based_decision)}"
                )
                rule_based_decision = None

            # Aggregate decisions
            final_decision = self._aggregate_decisions(
                llm_decision, rule_based_decision, request
            )

            # Calculate confidence comparison
            confidence_comparison = self._calculate_confidence_comparison(
                llm_decision, rule_based_decision
            )

            return HybridDecisionResult(
                final_decision=final_decision,
                llm_decision=llm_decision,
                rule_based_decision=rule_based_decision,
                decision_method="hybrid",
                confidence_comparison=confidence_comparison,
                reasoning_sources=[
                    "llm_medical_reasoning",
                    "rule_based_validation",
                    "hybrid_aggregation",
                ],
            )

        except Exception as e:
            self.logger.error(f"Hybrid decision generation failed: {str(e)}")
            # Fallback to rule-based only
            return await self._generate_rule_based_only_decision(
                request, validation_result, policy_result, comprehensive_validation
            )

    async def _get_llm_decision_safe(
        self,
        request: AuthorizationRequest,
        policy_result: Optional[PolicyValidationResult],
        comprehensive_validation: Optional[Dict[str, Any]],
        payer_id: str,
    ) -> Optional[LLMDecisionResponse]:
        """Safely get LLM decision with error handling."""
        try:
            policy_context = self._build_policy_context(
                policy_result, comprehensive_validation, payer_id
            )
            return await llm_decision_service.make_decision(request, policy_context)
        except Exception as e:
            self.logger.error(f"LLM decision error: {str(e)}")
            return None

    async def _get_rule_based_decision_safe(
        self,
        request: AuthorizationRequest,
        validation_result: ValidationResult,
        policy_result: Optional[PolicyValidationResult],
        comprehensive_validation: Optional[Dict[str, Any]],
    ) -> Optional[AuthorizationDecision]:
        """Safely get rule-based decision with error handling."""
        try:
            return self.generate_decision(
                request, validation_result, policy_result, comprehensive_validation
            )
        except Exception as e:
            self.logger.error(f"Rule-based decision error: {str(e)}")
            return None

    def _build_policy_context(
        self,
        policy_result: Optional[PolicyValidationResult],
        comprehensive_validation: Optional[Dict[str, Any]],
        payer_id: str,
    ) -> PolicyContext:
        """Build policy context for LLM decision making."""
        coverage_policies = []
        medical_necessity_criteria = []

        if policy_result:
            coverage_policies.extend(policy_result.reasoning)
            if policy_result.additional_requirements:
                medical_necessity_criteria.extend(policy_result.additional_requirements)

        if comprehensive_validation:
            cms_compliance = comprehensive_validation.get("cms_compliance", {})
            if cms_compliance.get("recommendations"):
                coverage_policies.extend(cms_compliance["recommendations"])

            medical_necessity = comprehensive_validation.get("medical_necessity", {})
            if medical_necessity.get("reasoning"):
                medical_necessity_criteria.extend(medical_necessity["reasoning"])

        return PolicyContext(
            payer_id=payer_id,
            coverage_criteria=coverage_policies + medical_necessity_criteria,
            prior_auth_requirements=True,
            clinical_guidelines="standard"
        )

    def _convert_llm_to_authorization_decision(
        self, llm_decision: LLMDecisionResponse, request: Optional[AuthorizationRequest]
    ) -> AuthorizationDecision:
        """Convert LLM decision response to AuthorizationDecision format."""
        # Map LLM decision status to DecisionStatus
        status_mapping = {
            LLMDecisionStatus.APPROVE: DecisionStatus.APPROVED,
            LLMDecisionStatus.DENY: DecisionStatus.DENIED,
            LLMDecisionStatus.PENDING: DecisionStatus.MORE_INFO_NEEDED,
        }

        decision_status = status_mapping.get(
            llm_decision.decision, DecisionStatus.MORE_INFO_NEEDED
        )

        # Build reasoning from LLM response
        reasoning = [llm_decision.medical_reasoning]
        if llm_decision.policy_compliance.analysis:
            reasoning.append(
                f"Policy analysis: {llm_decision.policy_compliance.analysis}"
            )

        # Generate decision ID and authorization number
        decision_id = self._generate_decision_id()
        authorization_number = None
        valid_until = None

        if decision_status == DecisionStatus.APPROVED:
            authorization_number = self._generate_authorization_number()
            valid_until = datetime.now(timezone.utc) + timedelta(
                days=self.authorization_validity_days
            )

        # Collect policy references
        policy_references = llm_decision.policy_compliance.policy_references.copy()
        if llm_decision.evidence_base:
            policy_references.append(f"Evidence: {llm_decision.evidence_base}")

        # Handle additional info needed
        additional_info_needed = None
        if decision_status == DecisionStatus.MORE_INFO_NEEDED:
            additional_info_needed = llm_decision.required_documentation

        # Handle alternative procedures
        alternative_procedures = None
        if (
            decision_status == DecisionStatus.DENIED
            and llm_decision.alternative_procedures
        ):
            alternative_procedures = [
                alt.procedure for alt in llm_decision.alternative_procedures
            ]

        return AuthorizationDecision(
            decision_id=decision_id,
            request_id=request.request_id if request else "req_temp_request",
            status=decision_status,
            reasoning=reasoning,
            policy_references=policy_references,
            authorization_number=authorization_number,
            valid_until=valid_until,
            confidence_score=llm_decision.confidence_score,
            decided_at=datetime.now(timezone.utc),
            additional_info_needed=additional_info_needed,
            alternative_procedures=alternative_procedures,
        )

    def _aggregate_decisions(
        self,
        llm_decision: Optional[LLMDecisionResponse],
        rule_based_decision: Optional[AuthorizationDecision],
        request: AuthorizationRequest,
    ) -> AuthorizationDecision:
        """
        Aggregate LLM and rule-based decisions using sophisticated weighted approach.

        This method implements the core hybrid decision-making logic that combines
        LLM medical reasoning with rule-based policy validation to produce the
        most reliable authorization decision.

        Args:
            llm_decision: LLM decision response
            rule_based_decision: Rule-based authorization decision
            request: Original authorization request

        Returns:
            Final aggregated authorization decision
        """
        self.logger.debug(f"Aggregating decisions for request {request.request_id}")

        # Handle cases where only one decision is available
        if llm_decision and not rule_based_decision:
            self.logger.info(
                f"Using LLM-only decision for request {request.request_id}"
            )
            return self._convert_llm_to_authorization_decision(llm_decision, request)
        elif rule_based_decision and not llm_decision:
            self.logger.info(
                f"Using rule-based-only decision for request {request.request_id}"
            )
            return rule_based_decision
        elif not llm_decision and not rule_based_decision:
            self.logger.error(
                f"Both decision methods failed for request {request.request_id}"
            )
            return self._generate_error_decision(
                request, "Both decision methods failed"
            )

        # Both decisions available - perform sophisticated aggregation
        llm_auth_decision = self._convert_llm_to_authorization_decision(
            llm_decision, request
        )

        self.logger.info(
            f"Aggregating hybrid decision for request {request.request_id}: "
            f"LLM={llm_auth_decision.status.value}({llm_decision.confidence_score:.2f}), "
            f"Rule={rule_based_decision.status.value}({rule_based_decision.confidence_score:.2f})"
        )

        # Determine final status using enhanced aggregation logic
        final_status = self._aggregate_decision_status(
            llm_auth_decision.status,
            rule_based_decision.status,
            llm_decision.confidence_score,
            rule_based_decision.confidence_score,
        )

        # Build comprehensive reasoning that explains the hybrid approach
        combined_reasoning = self._build_hybrid_reasoning(
            llm_decision, rule_based_decision, final_status
        )

        # Calculate weighted confidence with quality adjustments
        weighted_confidence = self._calculate_hybrid_confidence(
            llm_decision, rule_based_decision, final_status
        )

        # Merge policy references with deduplication and prioritization
        combined_policy_refs = self._merge_policy_references(
            llm_auth_decision.policy_references, rule_based_decision.policy_references
        )

        # Handle authorization details
        authorization_number = None
        valid_until = None
        if final_status == DecisionStatus.APPROVED:
            authorization_number = self._generate_authorization_number()
            valid_until = datetime.now(timezone.utc) + timedelta(
                days=self.authorization_validity_days
            )

        # Intelligently merge additional information requirements
        additional_info_needed = None
        if final_status == DecisionStatus.MORE_INFO_NEEDED:
            additional_info_needed = self._merge_additional_info_requirements(
                llm_auth_decision.additional_info_needed,
                rule_based_decision.additional_info_needed,
            )

        # Combine alternative procedures with ranking
        alternative_procedures = None
        if final_status == DecisionStatus.DENIED:
            alternative_procedures = self._merge_alternative_procedures(
                llm_auth_decision.alternative_procedures,
                rule_based_decision.alternative_procedures,
            )

        final_decision = AuthorizationDecision(
            decision_id=self._generate_decision_id(),
            request_id=request.request_id,
            status=final_status,
            reasoning=combined_reasoning,
            policy_references=combined_policy_refs,
            authorization_number=authorization_number,
            valid_until=valid_until,
            confidence_score=weighted_confidence,
            decided_at=datetime.now(timezone.utc),
            additional_info_needed=additional_info_needed,
            alternative_procedures=alternative_procedures,
        )

        self.logger.info(
            f"Hybrid decision completed for request {request.request_id}: "
            f"status={final_status.value}, confidence={weighted_confidence:.2f}"
        )

        return final_decision

    def _build_hybrid_reasoning(
        self,
        llm_decision: LLMDecisionResponse,
        rule_based_decision: AuthorizationDecision,
        final_status: DecisionStatus,
    ) -> List[str]:
        """Build comprehensive reasoning that explains the hybrid decision process."""
        reasoning = []

        # Add hybrid decision explanation
        reasoning.append(
            f"Hybrid Decision Analysis (LLM weight: {self.llm_weight}, Rule weight: {self.rule_weight})"
        )

        # Add LLM medical reasoning
        reasoning.append(f"AI Medical Analysis: {llm_decision.medical_reasoning}")

        # Add rule-based reasoning
        for rule_reason in rule_based_decision.reasoning:
            reasoning.append(f"Policy Validation: {rule_reason}")

        # Add decision reconciliation explanation if decisions differed
        llm_auth_decision = self._convert_llm_to_authorization_decision(
            llm_decision, None
        )
        if llm_auth_decision.status != rule_based_decision.status:
            reasoning.append(
                f"Decision Reconciliation: LLM suggested {llm_auth_decision.status.value}, "
                f"rules suggested {rule_based_decision.status.value}, "
                f"final decision: {final_status.value}"
            )

        # Add confidence analysis
        reasoning.append(
            f"Confidence Analysis: LLM={llm_decision.confidence_score:.2f}, "
            f"Rule-based={rule_based_decision.confidence_score:.2f}"
        )

        return reasoning

    def _calculate_hybrid_confidence(
        self,
        llm_decision: LLMDecisionResponse,
        rule_based_decision: AuthorizationDecision,
        final_status: DecisionStatus,
    ) -> float:
        """Calculate weighted confidence with quality adjustments."""
        base_confidence = (
            llm_decision.confidence_score * self.llm_weight
            + rule_based_decision.confidence_score * self.rule_weight
        )

        # Agreement bonus
        llm_auth_decision = self._convert_llm_to_authorization_decision(
            llm_decision, None
        )
        if llm_auth_decision.status == rule_based_decision.status:
            base_confidence += 0.1  # Boost confidence when both methods agree

        # Quality adjustments
        if llm_decision.validation_errors:
            base_confidence -= len(llm_decision.validation_errors) * 0.05

        if llm_decision.fallback_used:
            base_confidence -= 0.1  # Reduce confidence if LLM fallback was used

        # Ensure confidence stays within valid range
        return max(0.0, min(1.0, base_confidence))

    def _merge_policy_references(
        self, llm_refs: List[str], rule_refs: List[str]
    ) -> List[str]:
        """Merge policy references with deduplication and prioritization."""
        # Combine and deduplicate
        all_refs = list(set(llm_refs + rule_refs))

        # Sort by priority (CMS first, then payer policies, then others)
        def ref_priority(ref: str) -> int:
            ref_lower = ref.lower()
            if "cms" in ref_lower or "ncd" in ref_lower:
                return 0  # Highest priority
            elif "payer" in ref_lower or "policy" in ref_lower:
                return 1  # Medium priority
            else:
                return 2  # Lower priority

        return sorted(all_refs, key=ref_priority)

    def _merge_additional_info_requirements(
        self,
        llm_requirements: Optional[List[str]],
        rule_requirements: Optional[List[str]],
    ) -> List[str]:
        """Merge additional information requirements intelligently."""
        all_requirements = []

        if llm_requirements:
            all_requirements.extend(llm_requirements)

        if rule_requirements:
            all_requirements.extend(rule_requirements)

        # Deduplicate while preserving order
        seen = set()
        unique_requirements = []
        for req in all_requirements:
            if req not in seen:
                seen.add(req)
                unique_requirements.append(req)

        return unique_requirements

    def _merge_alternative_procedures(
        self,
        llm_alternatives: Optional[List[str]],
        rule_alternatives: Optional[List[str]],
    ) -> List[str]:
        """Merge alternative procedures with ranking."""
        all_alternatives = []

        # LLM alternatives get priority as they're based on medical reasoning
        if llm_alternatives:
            all_alternatives.extend(llm_alternatives)

        if rule_alternatives:
            # Add rule-based alternatives that aren't already included
            for alt in rule_alternatives:
                if alt not in all_alternatives:
                    all_alternatives.append(alt)

        # Limit to top 5 alternatives to avoid overwhelming users
        return all_alternatives[:5]

    def _aggregate_decision_status(
        self,
        llm_status: DecisionStatus,
        rule_status: DecisionStatus,
        llm_confidence: float,
        rule_confidence: float,
    ) -> DecisionStatus:
        """
        Aggregate decision statuses from LLM and rule-based approaches using weighted logic.

        This method implements sophisticated decision aggregation that considers both
        the decision outcomes and confidence scores to produce the most reliable result.

        Args:
            llm_status: LLM decision status
            rule_status: Rule-based decision status
            llm_confidence: LLM confidence score
            rule_confidence: Rule-based confidence score

        Returns:
            Final aggregated decision status
        """
        self.logger.debug(
            f"Aggregating decisions: LLM={llm_status.value}({llm_confidence:.2f}), "
            f"Rule={rule_status.value}({rule_confidence:.2f})"
        )

        # If both agree, use the agreed status with confidence boost
        if llm_status == rule_status:
            self.logger.debug(f"Both methods agree on {llm_status.value}")
            return llm_status

        # Calculate weighted decision scores for each status
        decision_scores = self._calculate_weighted_decision_scores(
            llm_status, rule_status, llm_confidence, rule_confidence
        )

        # Find the status with highest weighted score
        best_status = max(decision_scores.items(), key=lambda x: x[1])[0]
        best_score = decision_scores[best_status]

        # Apply safety thresholds
        if best_status == DecisionStatus.APPROVED and best_score < 0.7:
            # Low confidence approval - request more info instead
            self.logger.info(
                f"Converting low-confidence approval (score={best_score:.2f}) to pending"
            )
            return DecisionStatus.MORE_INFO_NEEDED

        elif best_status == DecisionStatus.DENIED and best_score < 0.6:
            # Low confidence denial - request more info instead
            self.logger.info(
                f"Converting low-confidence denial (score={best_score:.2f}) to pending"
            )
            return DecisionStatus.MORE_INFO_NEEDED

        self.logger.debug(
            f"Final aggregated decision: {best_status.value} (score={best_score:.2f})"
        )
        return best_status

    def _calculate_weighted_decision_scores(
        self,
        llm_status: DecisionStatus,
        rule_status: DecisionStatus,
        llm_confidence: float,
        rule_confidence: float,
    ) -> Dict[DecisionStatus, float]:
        """
        Calculate weighted scores for each possible decision status.

        Args:
            llm_status: LLM decision status
            rule_status: Rule-based decision status
            llm_confidence: LLM confidence score
            rule_confidence: Rule-based confidence score

        Returns:
            Dictionary mapping decision statuses to weighted scores
        """
        scores = {
            DecisionStatus.APPROVED: 0.0,
            DecisionStatus.DENIED: 0.0,
            DecisionStatus.MORE_INFO_NEEDED: 0.0,
        }

        # Add weighted scores for LLM decision
        llm_weighted_confidence = llm_confidence * self.llm_weight
        scores[llm_status] += llm_weighted_confidence

        # Add weighted scores for rule-based decision
        rule_weighted_confidence = rule_confidence * self.rule_weight
        scores[rule_status] += rule_weighted_confidence

        # Apply decision-specific bonuses and penalties
        scores = self._apply_decision_modifiers(
            scores, llm_status, rule_status, llm_confidence, rule_confidence
        )

        return scores

    def _apply_decision_modifiers(
        self,
        scores: Dict[DecisionStatus, float],
        llm_status: DecisionStatus,
        rule_status: DecisionStatus,
        llm_confidence: float,
        rule_confidence: float,
    ) -> Dict[DecisionStatus, float]:
        """
        Apply decision-specific modifiers to weighted scores.

        Args:
            scores: Current decision scores
            llm_status: LLM decision status
            rule_status: Rule-based decision status
            llm_confidence: LLM confidence score
            rule_confidence: Rule-based confidence score

        Returns:
            Modified decision scores
        """
        modified_scores = scores.copy()

        # Conservative bias: slightly favor denial over approval when uncertain
        if llm_status != rule_status:
            if DecisionStatus.DENIED in [llm_status, rule_status]:
                modified_scores[DecisionStatus.DENIED] += 0.05

            # Favor pending when there's significant disagreement
            confidence_diff = abs(llm_confidence - rule_confidence)
            if confidence_diff > 0.3:
                modified_scores[DecisionStatus.MORE_INFO_NEEDED] += 0.1

        # High confidence bonus
        if llm_confidence > 0.9:
            modified_scores[llm_status] += 0.1
        if rule_confidence > 0.9:
            modified_scores[rule_status] += 0.1

        # Ensure scores don't exceed 1.0
        for status in modified_scores:
            modified_scores[status] = min(1.0, modified_scores[status])

        return modified_scores

    def _calculate_confidence_comparison(
        self,
        llm_decision: Optional[LLMDecisionResponse],
        rule_based_decision: Optional[AuthorizationDecision],
    ) -> Dict[str, float]:
        """Calculate confidence comparison between decision methods."""
        comparison = {}

        if llm_decision:
            comparison["llm_confidence"] = llm_decision.confidence_score

        if rule_based_decision:
            comparison["rule_based_confidence"] = rule_based_decision.confidence_score

        if llm_decision and rule_based_decision:
            comparison["confidence_difference"] = abs(
                llm_decision.confidence_score - rule_based_decision.confidence_score
            )
            comparison["agreement_score"] = 1.0 - comparison["confidence_difference"]

        return comparison

    def generate_decision_with_detailed_reasoning(
        self,
        request: AuthorizationRequest,
        validation_result: ValidationResult,
        policy_result: Optional[PolicyValidationResult] = None,
        comprehensive_validation: Optional[Dict[str, Any]] = None,
    ) -> Tuple[AuthorizationDecision, DecisionDocumentation]:
        """
        Generate authorization decision with detailed reasoning and documentation.

        Args:
            request: Authorization request
            validation_result: Basic validation result
            policy_result: Policy validation result (optional)
            comprehensive_validation: Comprehensive validation including medical necessity

        Returns:
            Tuple of (AuthorizationDecision, DecisionDocumentation)
        """
        try:
            # Generate the decision using existing logic
            decision = self.generate_decision(
                request, validation_result, policy_result, comprehensive_validation
            )

            # Generate detailed reasoning elements
            reasoning_elements = self.reasoning_engine.generate_detailed_reasoning(
                request, validation_result, policy_result, comprehensive_validation
            )

            # Create comprehensive decision documentation
            documentation = self.reasoning_engine.create_decision_documentation(
                decision, request, reasoning_elements, comprehensive_validation
            )

            self.logger.info(
                "Generated decision with detailed reasoning",
                request_id=request.request_id,
                decision_id=decision.decision_id,
                reasoning_elements_count=len(reasoning_elements),
            )

            return decision, documentation

        except Exception as e:
            self.logger.error(
                "Failed to generate decision with detailed reasoning",
                request_id=request.request_id,
                error=str(e),
                exc_info=True,
            )

            # Generate basic decision on error
            decision = self.generate_decision(
                request, validation_result, policy_result, comprehensive_validation
            )

            # Create minimal documentation
            documentation = DecisionDocumentation(
                decision_id=decision.decision_id,
                request_id=decision.request_id,
                decision_timestamp=decision.decided_at,
                decision_status=decision.status,
                reasoning_elements=[],
                policy_references=decision.policy_references,
                clinical_factors={},
                risk_assessment={"risk_level": "unknown", "risk_factors": []},
                alternative_procedures=[],
                audit_trail=[],
            )

            return decision, documentation

    def calculate_confidence_score(
        self,
        validation_results: List[ValidationResult],
        policy_results: List[PolicyValidationResult] = None,
        medical_necessity_score: float = None,
    ) -> float:
        """
        Calculate overall confidence score for a decision.

        Args:
            validation_results: List of validation results
            policy_results: List of policy validation results
            medical_necessity_score: Medical necessity confidence score

        Returns:
            Overall confidence score (0.0-1.0)
        """
        try:
            scores = []

            # Validation confidence (based on processing time and error count)
            for validation in validation_results:
                if validation.is_valid:
                    # High confidence for fast, error-free validation
                    validation_score = max(0.7, 1.0 - (len(validation.warnings) * 0.1))
                else:
                    # Low confidence for validation failures
                    validation_score = max(0.1, 0.5 - (len(validation.errors) * 0.1))
                scores.append(validation_score)

            # Policy confidence
            if policy_results:
                for policy in policy_results:
                    scores.append(policy.confidence_score)

            # Medical necessity confidence
            if medical_necessity_score is not None:
                scores.append(medical_necessity_score)

            # Calculate weighted average (equal weights for now)
            if scores:
                confidence = sum(scores) / len(scores)
            else:
                confidence = 0.5  # Default moderate confidence

            # Ensure confidence is within bounds
            return max(0.0, min(1.0, confidence))

        except Exception as e:
            self.logger.error(f"Confidence calculation error: {str(e)}")
            return 0.5  # Default moderate confidence on error

    def _evaluate_decision(
        self, context: DecisionContext
    ) -> Tuple[DecisionStatus, List[str], float]:
        """
        Evaluate decision based on context.

        Args:
            context: Decision context with all validation results

        Returns:
            Tuple of (decision_status, reasoning, confidence_score)
        """
        reasoning = []

        # Check basic validation first
        if not context.validation_result.is_valid:
            return (
                DecisionStatus.DENIED,
                [
                    f"Request validation failed: {'; '.join([e.message for e in context.validation_result.errors])}"
                ],
                0.9,  # High confidence in denial for validation failures
            )

        # Initialize decision factors
        approval_factors = []
        denial_factors = []
        info_needed_factors = []

        # Evaluate policy validation
        if context.policy_result:
            if context.policy_result.is_covered:
                approval_factors.append("Request meets coverage policy requirements")
                reasoning.extend(context.policy_result.reasoning)
            else:
                denial_factors.append(
                    "Request does not meet coverage policy requirements"
                )
                reasoning.extend(context.policy_result.reasoning)

            # Check for additional requirements
            if context.policy_result.additional_requirements:
                info_needed_factors.extend(
                    context.policy_result.additional_requirements
                )

        # Evaluate CMS compliance
        if context.cms_compliance:
            if context.cms_compliance.get("is_compliant", True):
                approval_factors.append("Request complies with CMS guidelines")
            else:
                denial_factors.append("Request does not comply with CMS guidelines")
                reasoning.extend(context.cms_compliance.get("compliance_issues", []))

            # Add CMS recommendations as info needed
            cms_recommendations = context.cms_compliance.get("recommendations", [])
            if cms_recommendations:
                info_needed_factors.extend(cms_recommendations)

        # Evaluate medical necessity
        if context.medical_necessity:
            necessity_level = context.medical_necessity.get(
                "necessity_level", "unknown"
            )
            necessity_confidence = context.medical_necessity.get(
                "confidence_score", 0.5
            )

            if necessity_level == "high" and necessity_confidence >= 0.8:
                approval_factors.append("High medical necessity established")
            elif necessity_level == "moderate" and necessity_confidence >= 0.6:
                approval_factors.append("Moderate medical necessity established")
            elif necessity_level == "low" or necessity_confidence < 0.5:
                denial_factors.append("Insufficient medical necessity demonstrated")

            # Add medical necessity reasoning
            necessity_reasoning = context.medical_necessity.get("reasoning", [])
            reasoning.extend(necessity_reasoning)

            # Check for additional documentation needed
            additional_docs = context.medical_necessity.get(
                "additional_documentation_needed", []
            )
            if additional_docs:
                info_needed_factors.extend(additional_docs)

        # Add validation warnings as reasoning
        if context.validation_result.warnings:
            reasoning.extend(
                [f"Note: {warning}" for warning in context.validation_result.warnings]
            )

        # Make decision based on factors
        decision_status, final_reasoning, confidence = self._resolve_decision_factors(
            approval_factors, denial_factors, info_needed_factors, reasoning
        )

        return decision_status, final_reasoning, confidence

    def _resolve_decision_factors(
        self,
        approval_factors: List[str],
        denial_factors: List[str],
        info_needed_factors: List[str],
        base_reasoning: List[str],
    ) -> Tuple[DecisionStatus, List[str], float]:
        """
        Resolve decision based on competing factors.

        Args:
            approval_factors: Factors supporting approval
            denial_factors: Factors supporting denial
            info_needed_factors: Factors requiring more information
            base_reasoning: Base reasoning statements

        Returns:
            Tuple of (decision_status, reasoning, confidence_score)
        """
        reasoning = base_reasoning.copy()

        # If there are denial factors, deny the request
        if denial_factors:
            reasoning.extend([f"Denial reason: {factor}" for factor in denial_factors])
            confidence = min(0.95, 0.7 + (len(denial_factors) * 0.1))
            return DecisionStatus.DENIED, reasoning, confidence

        # If there are significant info needed factors, request more info
        if len(info_needed_factors) >= 2:  # Threshold for requesting more info
            reasoning.append("Additional information required for complete evaluation")
            reasoning.extend([f"Required: {factor}" for factor in info_needed_factors])
            confidence = 0.8
            return DecisionStatus.MORE_INFO_NEEDED, reasoning, confidence

        # If there are approval factors and minimal info needed, approve
        if approval_factors and len(info_needed_factors) <= 1:
            reasoning.extend(
                [f"Approval basis: {factor}" for factor in approval_factors]
            )
            if info_needed_factors:
                reasoning.extend([f"Note: {factor}" for factor in info_needed_factors])
            confidence = min(0.95, 0.8 + (len(approval_factors) * 0.05))
            return DecisionStatus.APPROVED, reasoning, confidence

        # Default case - request more information if uncertain
        reasoning.append("Insufficient information for definitive decision")
        if info_needed_factors:
            reasoning.extend([f"Required: {factor}" for factor in info_needed_factors])
        else:
            reasoning.append("Additional clinical documentation may be required")

        return DecisionStatus.MORE_INFO_NEEDED, reasoning, 0.6

    def _generate_decision_id(self) -> str:
        """Generate a unique decision ID."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        return f"dec_{timestamp}_{unique_id}"

    def _generate_authorization_number(self) -> str:
        """Generate a unique authorization number for approved requests."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        unique_id = str(uuid.uuid4())[:12].upper()
        return f"auth_{timestamp}_{unique_id}"

    def _collect_policy_references(self, context: DecisionContext) -> List[str]:
        """Collect all policy references from the decision context."""
        references = []

        if context.policy_result and context.policy_result.policy_references:
            references.extend(context.policy_result.policy_references)

        if context.cms_compliance:
            # Add NCD references
            ncd_policies = context.cms_compliance.get("ncd_policies", [])
            for policy in ncd_policies:
                if policy.get("policy_name"):
                    references.append(f"CMS NCD: {policy['policy_name']}")

            # Add LCD references
            lcd_policies = context.cms_compliance.get("lcd_policies", [])
            for policy in lcd_policies:
                if policy.get("policy_name"):
                    references.append(f"CMS LCD: {policy['policy_name']}")

        return list(set(references))  # Remove duplicates

    def _generate_additional_info_requirements(
        self, context: DecisionContext
    ) -> List[str]:
        """Generate list of additional information needed."""
        requirements = []

        # From policy validation
        if context.policy_result and context.policy_result.additional_requirements:
            requirements.extend(context.policy_result.additional_requirements)

        # From CMS compliance
        if context.cms_compliance:
            cms_recommendations = context.cms_compliance.get("recommendations", [])
            requirements.extend(cms_recommendations)

        # From medical necessity
        if context.medical_necessity:
            additional_docs = context.medical_necessity.get(
                "additional_documentation_needed", []
            )
            requirements.extend(additional_docs)

        # Remove duplicates and return
        return list(set(requirements))

    def _extract_policy_result_from_comprehensive(
        self, policy_validation: Dict[str, Any]
    ) -> PolicyValidationResult:
        """Extract PolicyValidationResult from comprehensive validation dictionary."""
        from src.services.policy_validation import PolicyValidationResult, PolicyType

        if not policy_validation:
            return None

        try:
            return PolicyValidationResult(
                is_covered=policy_validation.get("is_covered", False),
                policy_id=policy_validation.get("policy_id", ""),
                policy_type=PolicyType(policy_validation.get("policy_type", "PAYER")),
                reasoning=policy_validation.get("reasoning", []),
                confidence_score=policy_validation.get("confidence_score", 0.5),
                policy_references=policy_validation.get("policy_references", []),
                additional_requirements=policy_validation.get(
                    "additional_requirements", []
                ),
            )
        except Exception as e:
            self.logger.error(f"Error extracting policy result: {str(e)}")
            return None

    def _generate_error_decision(
        self, request: Optional[AuthorizationRequest], error_message: str
    ) -> AuthorizationDecision:
        """Generate a denial decision for system errors with user-friendly messaging."""

        # Log the technical error for debugging but don't expose it to users
        self.logger.error(f"Technical error in decision generation: {error_message}")

        # Provide user-friendly reasoning based on common error patterns
        user_friendly_reasoning = [
            "Authorization request requires manual review",
            "Unable to automatically process this request due to incomplete policy information",
            "Please ensure all required medical codes and clinical documentation are provided",
            "Contact your payer representative for assistance if this issue persists",
        ]

        return AuthorizationDecision(
            decision_id=self._generate_decision_id(),
            request_id=request.request_id if request else "req_unknown",
            status=DecisionStatus.MORE_INFO_NEEDED,  # Changed from DENIED to MORE_INFO_NEEDED for better UX
            reasoning=user_friendly_reasoning,
            policy_references=[],
            authorization_number=None,
            valid_until=None,
            confidence_score=0.3,  # Lower confidence for system errors
            decided_at=datetime.now(timezone.utc),
            additional_info_needed=[
                "Verify all ICD-10 diagnosis codes are current and specific",
                "Ensure CPT/HCPCS procedure codes match the requested service",
                "Include detailed clinical notes supporting medical necessity",
                "Confirm patient demographics and insurance information",
            ],
            alternative_procedures=[
                "Submit request through manual review process",
                "Contact payer support for assistance",
            ],
        )

    async def get_decision(self, decision_id: str) -> Optional[AuthorizationDecision]:
        """
        Retrieve a specific authorization decision by ID.

        Args:
            decision_id: Unique decision identifier

        Returns:
            AuthorizationDecision if found, None otherwise
        """
        try:
            # In a real implementation, this would query the database
            # For now, return a mock decision for testing
            if decision_id.startswith("dec_"):
                return AuthorizationDecision(
                    decision_id=decision_id,
                    request_id=f"req_{decision_id[4:]}",  # Extract from decision ID
                    status=DecisionStatus.APPROVED,
                    reasoning=["Medical necessity criteria met per CMS NCD 220.2"],
                    policy_references=["CMS_NCD_220.2"],
                    authorization_number=f"AUTH{decision_id[4:]}",
                    valid_until=datetime.now(timezone.utc) + timedelta(days=30),
                    confidence_score=0.95,
                    decided_at=datetime.now(timezone.utc),
                    additional_info_needed=None,
                    alternative_procedures=None,
                )
            return None

        except Exception as e:
            self.logger.error(f"Error retrieving decision {decision_id}: {str(e)}")
            return None

    async def get_decision_by_request(
        self, request_id: str
    ) -> Optional[AuthorizationDecision]:
        """
        Retrieve authorization decision for a specific request.

        Args:
            request_id: Authorization request identifier

        Returns:
            AuthorizationDecision if found, None otherwise
        """
        try:
            # In a real implementation, this would query the database
            # For now, return a mock decision for testing
            if request_id.startswith("req_"):
                decision_id = f"dec_{request_id[4:]}"
                return await self.get_decision(decision_id)
            return None

        except Exception as e:
            self.logger.error(
                f"Error retrieving decision for request {request_id}: {str(e)}"
            )
            return None

    async def get_provider_decision_history(
        self,
        provider_id: str,
        status_filter: Optional[DecisionStatus] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> "DecisionHistoryResult":
        """
        Get decision history for a provider with filtering and pagination.

        Args:
            provider_id: Provider identifier
            status_filter: Optional status filter
            date_from: Optional start date filter
            date_to: Optional end date filter
            page: Page number
            page_size: Number of decisions per page

        Returns:
            DecisionHistoryResult with decisions and metadata
        """
        try:
            # In a real implementation, this would query the database
            # For now, return mock decisions for testing
            mock_decisions = []

            # Generate some mock decisions
            for i in range(min(page_size, 10)):  # Limit to 10 for demo
                decision_id = f"dec_2024_{i:06d}"
                request_id = f"req_2024_{i:06d}"

                decision = AuthorizationDecision(
                    decision_id=decision_id,
                    request_id=request_id,
                    status=(
                        DecisionStatus.APPROVED if i % 3 != 2 else DecisionStatus.DENIED
                    ),
                    reasoning=(
                        ["Medical necessity criteria met"]
                        if i % 3 != 2
                        else ["Insufficient medical necessity"]
                    ),
                    policy_references=["CMS_NCD_220.2"],
                    authorization_number=f"AUTH2024{i:06d}" if i % 3 != 2 else None,
                    valid_until=(
                        datetime.now(timezone.utc) + timedelta(days=30)
                        if i % 3 != 2
                        else None
                    ),
                    confidence_score=0.95,
                    decided_at=datetime.now(timezone.utc) - timedelta(days=i),
                    additional_info_needed=None,
                    alternative_procedures=None,
                )

                # Apply status filter
                if status_filter is None or decision.status == status_filter:
                    mock_decisions.append(decision)

            # Apply date filters
            if date_from:
                mock_decisions = [
                    d for d in mock_decisions if d.decided_at >= date_from
                ]
            if date_to:
                mock_decisions = [d for d in mock_decisions if d.decided_at <= date_to]

            return DecisionHistoryResult(
                decisions=mock_decisions,
                total_count=len(mock_decisions),
                page=page,
                page_size=page_size,
            )

        except Exception as e:
            self.logger.error(
                f"Error retrieving decision history for provider {provider_id}: {str(e)}"
            )
            return DecisionHistoryResult(
                decisions=[], total_count=0, page=page, page_size=page_size
            )

    async def get_provider_decision_summary(
        self, provider_id: str, days_back: int = 30
    ) -> "DecisionSummaryResult":
        """
        Get decision summary statistics for a provider.

        Args:
            provider_id: Provider identifier
            days_back: Number of days to include in summary

        Returns:
            DecisionSummaryResult with summary statistics
        """
        try:
            # In a real implementation, this would query the database
            # For now, return mock summary for testing
            total_decisions = 150
            approved_decisions = 120
            denied_decisions = 25
            info_needed_decisions = 5

            approval_rate = (
                (approved_decisions / total_decisions) * 100
                if total_decisions > 0
                else 0
            )

            return DecisionSummaryResult(
                total_decisions=total_decisions,
                approval_rate=approval_rate,
                average_processing_time_hours=1.5,
                decisions_by_status={
                    "approved": approved_decisions,
                    "denied": denied_decisions,
                    "more_info_needed": info_needed_decisions,
                },
                decisions_by_procedure={"mri": 85, "ct_scan": 45, "x_ray": 20},
            )

        except Exception as e:
            self.logger.error(
                f"Error generating decision summary for provider {provider_id}: {str(e)}"
            )
            return DecisionSummaryResult(
                total_decisions=0,
                approval_rate=0.0,
                average_processing_time_hours=0.0,
                decisions_by_status={},
                decisions_by_procedure={},
            )

    def configure_hybrid_weights(self, llm_weight: float, rule_weight: float):
        """
        Configure the weights for hybrid decision-making.

        Args:
            llm_weight: Weight for LLM decisions (0.0-1.0)
            rule_weight: Weight for rule-based decisions (0.0-1.0)
        """
        if not (0.0 <= llm_weight <= 1.0) or not (0.0 <= rule_weight <= 1.0):
            raise ValueError("Weights must be between 0.0 and 1.0")

        if abs((llm_weight + rule_weight) - 1.0) > 0.01:
            raise ValueError("Weights must sum to approximately 1.0")

        self.llm_weight = llm_weight
        self.rule_weight = rule_weight

        self.logger.info(
            f"Updated hybrid weights: LLM={llm_weight}, Rule={rule_weight}"
        )

    def set_decision_mode(self, mode: DecisionMode):
        """
        Set the decision-making mode.

        Args:
            mode: Decision mode to use
        """
        self.decision_mode = mode
        self.llm_enabled = mode in [
            DecisionMode.LLM_ONLY,
            DecisionMode.HYBRID,
            DecisionMode.AUTO_SELECT,
        ]

        self.logger.info(f"Decision mode set to: {mode.value}")

    def get_decision_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics for the decision engine.

        Returns:
            Dictionary containing decision metrics
        """
        return {
            **self._decision_metrics,
            "llm_enabled": self.llm_enabled,
            "decision_mode": self.decision_mode.value,
            "llm_weight": self.llm_weight,
            "rule_weight": self.rule_weight,
            "llm_initialized": self._llm_initialized,
        }

    def _track_decision_method(self, method: str):
        """Track which decision method was used."""
        self._decision_metrics["total_decisions"] += 1

        if method == "llm_only":
            self._decision_metrics["llm_decisions"] += 1
        elif method == "rule_based_only" or method == "fallback_rule_based":
            self._decision_metrics["rule_based_decisions"] += 1
        elif method == "hybrid":
            self._decision_metrics["hybrid_decisions"] += 1
        elif "fallback" in method:
            self._decision_metrics["fallback_decisions"] += 1

    async def process_authorization_with_enhanced_routing(
        self,
        request: AuthorizationRequest,
        validation_result: ValidationResult,
        policy_result: Optional[PolicyValidationResult] = None,
        comprehensive_validation: Optional[Dict[str, Any]] = None,
        payer_id: str = "default_payer",
    ) -> HybridDecisionResult:
        """
        Process authorization request with enhanced LLM routing and hybrid decision-making.

        This method implements the core task 7 requirements:
        - Routes requests to LLM service for medical reasoning
        - Combines LLM and rule-based approaches in hybrid mode
        - Aggregates decisions with weighted outputs
        - Maintains backward compatibility

        Args:
            request: Authorization request
            validation_result: Basic validation result
            policy_result: Policy validation result (optional)
            comprehensive_validation: Comprehensive validation including medical necessity
            payer_id: Payer identifier for policy context

        Returns:
            HybridDecisionResult with complete decision information
        """
        try:
            self.logger.info(
                f"Processing authorization request {request.request_id} with enhanced routing"
            )

            # Route to appropriate decision method based on configuration and request characteristics
            if self.decision_mode == DecisionMode.RULE_BASED_ONLY:
                # Pure rule-based for backward compatibility
                result = await self._generate_rule_based_only_decision(
                    request, validation_result, policy_result, comprehensive_validation
                )
                self.logger.info(
                    f"Request {request.request_id} processed with rule-based only"
                )

            elif self.decision_mode == DecisionMode.LLM_ONLY:
                # Pure LLM with fallback to rule-based
                result = await self._generate_llm_only_decision(
                    request,
                    validation_result,
                    policy_result,
                    comprehensive_validation,
                    payer_id,
                )
                self.logger.info(
                    f"Request {request.request_id} processed with LLM only"
                )

            else:
                # Hybrid or auto-select mode
                result = await self._generate_hybrid_decision(
                    request,
                    validation_result,
                    policy_result,
                    comprehensive_validation,
                    payer_id,
                )
                self.logger.info(
                    f"Request {request.request_id} processed with hybrid decision-making"
                )

            # Track decision method for metrics
            self._track_decision_method(result.decision_method)

            # Log final decision details
            self.logger.info(
                f"Enhanced routing completed for request {request.request_id}: "
                f"status={result.final_decision.status.value}, "
                f"confidence={result.final_decision.confidence_score:.2f}, "
                f"method={result.decision_method}"
            )

            return result

        except Exception as e:
            self.logger.error(
                f"Enhanced routing failed for request {request.request_id}: {str(e)}",
                exc_info=True,
            )

            # Fallback to basic rule-based decision
            fallback_decision = self.generate_decision(
                request, validation_result, policy_result, comprehensive_validation
            )

            return HybridDecisionResult(
                final_decision=fallback_decision,
                decision_method="fallback_rule_based",
                reasoning_sources=["rule_based_fallback"],
            )

    def supports_llm_integration(self) -> bool:
        """
        Check if LLM integration is supported and properly configured.

        Returns:
            True if LLM integration is available, False otherwise
        """
        return self.llm_enabled and self._llm_initialized

    def get_decision_routing_info(
        self, request: AuthorizationRequest
    ) -> Dict[str, Any]:
        """
        Get information about how a request would be routed for decision-making.

        Args:
            request: Authorization request to analyze

        Returns:
            Dictionary with routing information
        """
        # Create a minimal validation result for complexity calculation
        from src.services.validation import ValidationResult

        mock_validation = ValidationResult(
            is_valid=True, errors=[], warnings=[], processing_time_ms=0.0
        )

        complexity_score = self._calculate_request_complexity(request, mock_validation)
        selected_method = self._select_decision_method(request, mock_validation)

        return {
            "request_id": request.request_id,
            "complexity_score": complexity_score,
            "selected_method": selected_method,
            "decision_mode": self.decision_mode.value,
            "llm_enabled": self.llm_enabled,
            "llm_initialized": self._llm_initialized,
            "llm_weight": self.llm_weight,
            "rule_weight": self.rule_weight,
            "routing_factors": {
                "diagnosis_count": len(request.diagnosis_codes),
                "procedure_count": len(request.procedure_codes),
                "urgency_level": request.urgency_level.value,
                "has_clinical_notes": bool(request.clinical_notes),
                "clinical_notes_length": (
                    len(request.clinical_notes) if request.clinical_notes else 0
                ),
            },
        }


@dataclass
class DecisionHistoryResult:
    """Result container for decision history queries."""

    decisions: List[AuthorizationDecision]
    total_count: int
    page: int
    page_size: int


@dataclass
class DecisionSummaryResult:
    """Result container for decision summary statistics."""

    total_decisions: int
    approval_rate: float
    average_processing_time_hours: float
    decisions_by_status: Dict[str, int]
    decisions_by_procedure: Dict[str, int]

    def _aggregate_decision_status(
        self,
        llm_status: DecisionStatus,
        rule_status: DecisionStatus,
        llm_confidence: float,
        rule_confidence: float,
    ) -> DecisionStatus:
        """Aggregate decision statuses using confidence-weighted logic."""

        # If both agree, use the agreed status
        if llm_status == rule_status:
            return llm_status

        # Handle disagreements based on confidence and conservative approach
        if llm_status == DecisionStatus.DENIED or rule_status == DecisionStatus.DENIED:
            # Conservative approach: if either denies, lean toward denial
            if llm_status == DecisionStatus.DENIED and llm_confidence > 0.7:
                return DecisionStatus.DENIED
            elif rule_status == DecisionStatus.DENIED and rule_confidence > 0.7:
                return DecisionStatus.DENIED
            else:
                return DecisionStatus.MORE_INFO_NEEDED

        # If one approves and other needs more info, use higher confidence
        if (
            llm_status == DecisionStatus.APPROVED
            and rule_status == DecisionStatus.MORE_INFO_NEEDED
        ) or (
            rule_status == DecisionStatus.APPROVED
            and llm_status == DecisionStatus.MORE_INFO_NEEDED
        ):
            if llm_confidence > rule_confidence and llm_confidence > 0.8:
                return llm_status
            elif rule_confidence > llm_confidence and rule_confidence > 0.8:
                return rule_status
            else:
                return DecisionStatus.MORE_INFO_NEEDED

        # Default to more info needed for unclear cases
        return DecisionStatus.MORE_INFO_NEEDED

    def _build_hybrid_reasoning(
        self,
        llm_decision: LLMDecisionResponse,
        rule_based_decision: AuthorizationDecision,
        final_status: DecisionStatus,
    ) -> List[str]:
        """Build comprehensive reasoning that explains the hybrid decision."""

        reasoning = [
            "HYBRID DECISION ANALYSIS:",
            f"Final Decision: {final_status.value.upper()}",
        ]

        # Add LLM reasoning
        reasoning.append("LLM Medical Analysis:")
        reasoning.append(f"- {llm_decision.medical_reasoning}")
        reasoning.append(f"- LLM Confidence: {llm_decision.confidence_score:.2f}")

        # Add rule-based reasoning
        reasoning.append("Rule-Based Policy Analysis:")
        for rule_reason in rule_based_decision.reasoning:
            reasoning.append(f"- {rule_reason}")
        reasoning.append(
            f"- Rule-Based Confidence: {rule_based_decision.confidence_score:.2f}"
        )

        # Add aggregation explanation
        reasoning.append("Decision Aggregation:")
        reasoning.append(f"- Combined both AI medical reasoning and policy validation")
        reasoning.append(f"- Applied conservative approach for patient safety")

        return reasoning

    def _calculate_hybrid_confidence(
        self,
        llm_decision: LLMDecisionResponse,
        rule_based_decision: AuthorizationDecision,
        final_status: DecisionStatus,
    ) -> float:
        """Calculate weighted confidence score for hybrid decision."""

        # Base weighted average
        weighted_confidence = (
            llm_decision.confidence_score * self.llm_weight
            + rule_based_decision.confidence_score * self.rule_weight
        )

        # Adjust based on agreement
        llm_auth_decision = self._convert_llm_to_authorization_decision(
            llm_decision, None
        )
        if llm_auth_decision.status == rule_based_decision.status:
            # Boost confidence when both methods agree
            weighted_confidence = min(1.0, weighted_confidence * 1.1)
        else:
            # Reduce confidence when methods disagree
            weighted_confidence = weighted_confidence * 0.8

        # Ensure confidence is within valid range
        return max(0.0, min(1.0, weighted_confidence))

    def _merge_policy_references(
        self, llm_refs: List[str], rule_refs: List[str]
    ) -> List[str]:
        """Merge policy references with deduplication."""

        combined_refs = []
        seen_refs = set()

        # Add rule-based references first (higher priority)
        for ref in rule_refs:
            if ref not in seen_refs:
                combined_refs.append(ref)
                seen_refs.add(ref)

        # Add LLM references
        for ref in llm_refs:
            if ref not in seen_refs:
                combined_refs.append(ref)
                seen_refs.add(ref)

        return combined_refs

    def _merge_additional_info_requirements(
        self, llm_info: Optional[List[str]], rule_info: Optional[List[str]]
    ) -> List[str]:
        """Merge additional information requirements."""

        combined_info = []
        seen_info = set()

        # Add rule-based requirements
        if rule_info:
            for info in rule_info:
                if info not in seen_info:
                    combined_info.append(info)
                    seen_info.add(info)

        # Add LLM requirements
        if llm_info:
            for info in llm_info:
                if info not in seen_info:
                    combined_info.append(info)
                    seen_info.add(info)

        return combined_info if combined_info else None

    def _merge_alternative_procedures(
        self,
        llm_alternatives: Optional[List[str]],
        rule_alternatives: Optional[List[str]],
    ) -> List[str]:
        """Merge alternative procedures with ranking."""

        combined_alternatives = []
        seen_alternatives = set()

        # Add rule-based alternatives first
        if rule_alternatives:
            for alt in rule_alternatives:
                if alt not in seen_alternatives:
                    combined_alternatives.append(alt)
                    seen_alternatives.add(alt)

        # Add LLM alternatives
        if llm_alternatives:
            for alt in llm_alternatives:
                if alt not in seen_alternatives:
                    combined_alternatives.append(alt)
                    seen_alternatives.add(alt)

        return combined_alternatives if combined_alternatives else None

    def _calculate_confidence_comparison(
        self,
        llm_decision: Optional[LLMDecisionResponse],
        rule_based_decision: Optional[AuthorizationDecision],
    ) -> Dict[str, float]:
        """Calculate confidence comparison metrics."""

        comparison = {}

        if llm_decision:
            comparison["llm_confidence"] = llm_decision.confidence_score

        if rule_based_decision:
            comparison["rule_based_confidence"] = rule_based_decision.confidence_score

        if llm_decision and rule_based_decision:
            comparison["confidence_difference"] = abs(
                llm_decision.confidence_score - rule_based_decision.confidence_score
            )
            comparison["average_confidence"] = (
                llm_decision.confidence_score + rule_based_decision.confidence_score
            ) / 2

        return comparison

    def _track_decision_method(self, method: str):
        """Track which decision method was used for metrics."""
        self._decision_metrics["total_decisions"] += 1

        if method == "llm_only":
            self._decision_metrics["llm_decisions"] += 1
        elif method == "rule_based_only":
            self._decision_metrics["rule_based_decisions"] += 1
        elif method == "hybrid":
            self._decision_metrics["hybrid_decisions"] += 1
        elif method.startswith("fallback"):
            self._decision_metrics["fallback_decisions"] += 1

    def get_decision_metrics(self) -> Dict[str, Any]:
        """Get decision-making metrics."""
        total = self._decision_metrics["total_decisions"]
        if total == 0:
            return self._decision_metrics

        return {
            **self._decision_metrics,
            "llm_percentage": (self._decision_metrics["llm_decisions"] / total) * 100,
            "rule_based_percentage": (
                self._decision_metrics["rule_based_decisions"] / total
            )
            * 100,
            "hybrid_percentage": (self._decision_metrics["hybrid_decisions"] / total)
            * 100,
            "fallback_percentage": (
                self._decision_metrics["fallback_decisions"] / total
            )
            * 100,
        }

    def _convert_llm_to_authorization_decision(
        self, llm_decision: LLMDecisionResponse, request: Optional[AuthorizationRequest]
    ) -> AuthorizationDecision:
        """Convert LLM decision response to AuthorizationDecision format."""
        # Map LLM decision status to DecisionStatus
        status_mapping = {
            LLMDecisionStatus.APPROVE: DecisionStatus.APPROVED,
            LLMDecisionStatus.DENY: DecisionStatus.DENIED,
            LLMDecisionStatus.PENDING: DecisionStatus.MORE_INFO_NEEDED,
        }

        decision_status = status_mapping.get(
            llm_decision.decision, DecisionStatus.MORE_INFO_NEEDED
        )

        # Build reasoning from LLM response
        reasoning = [llm_decision.medical_reasoning]
        if llm_decision.policy_compliance.analysis:
            reasoning.append(
                f"Policy analysis: {llm_decision.policy_compliance.analysis}"
            )

        # Generate decision ID and authorization number
        decision_id = self._generate_decision_id()
        authorization_number = None
        valid_until = None

        if decision_status == DecisionStatus.APPROVED:
            authorization_number = self._generate_authorization_number()
            valid_until = datetime.now(timezone.utc) + timedelta(
                days=self.authorization_validity_days
            )

        # Collect policy references
        policy_references = llm_decision.policy_compliance.policy_references.copy()
        if llm_decision.evidence_base:
            policy_references.append(f"Evidence: {llm_decision.evidence_base}")

        # Handle additional info needed
        additional_info_needed = None
        if decision_status == DecisionStatus.MORE_INFO_NEEDED:
            additional_info_needed = llm_decision.required_documentation

        # Handle alternative procedures
        alternative_procedures = None
        if (
            decision_status == DecisionStatus.DENIED
            and llm_decision.alternative_procedures
        ):
            alternative_procedures = [
                alt.procedure for alt in llm_decision.alternative_procedures
            ]

        return AuthorizationDecision(
            decision_id=decision_id,
            request_id=request.request_id if request else "req_temp_request",
            status=decision_status,
            reasoning=reasoning,
            policy_references=policy_references,
            authorization_number=authorization_number,
            valid_until=valid_until,
            confidence_score=llm_decision.confidence_score,
            decided_at=datetime.now(timezone.utc),
            additional_info_needed=additional_info_needed,
            alternative_procedures=alternative_procedures,
        )

    def _aggregate_decisions(
        self,
        llm_decision: Optional[LLMDecisionResponse],
        rule_based_decision: Optional[AuthorizationDecision],
        request: AuthorizationRequest,
    ) -> AuthorizationDecision:
        """Aggregate LLM and rule-based decisions into final decision."""
        # If only one decision is available, use it
        if llm_decision and not rule_based_decision:
            return self._convert_llm_to_authorization_decision(llm_decision, request)
        elif rule_based_decision and not llm_decision:
            return rule_based_decision
        elif not llm_decision and not rule_based_decision:
            # Both failed, return error decision
            return self._generate_error_decision(
                request, "Both LLM and rule-based decisions failed"
            )

        # Both decisions available - aggregate them
        llm_auth_decision = self._convert_llm_to_authorization_decision(
            llm_decision, request
        )

        # Weighted decision aggregation
        llm_confidence = llm_decision.confidence_score * self.llm_weight
        rule_confidence = rule_based_decision.confidence_score * self.rule_weight

        # Choose decision with higher weighted confidence
        if llm_confidence >= rule_confidence:
            final_decision = llm_auth_decision
            # Enhance with rule-based insights
            if rule_based_decision.reasoning:
                final_decision.reasoning.extend(
                    [f"Rule-based: {r}" for r in rule_based_decision.reasoning]
                )
        else:
            final_decision = rule_based_decision
            # Enhance with LLM insights
            if llm_decision.medical_reasoning:
                final_decision.reasoning.append(
                    f"LLM analysis: {llm_decision.medical_reasoning}"
                )

        # Combine confidence scores
        final_decision.confidence_score = max(llm_confidence, rule_confidence)

        # Merge policy references
        if llm_decision.policy_compliance.policy_references:
            final_decision.policy_references.extend(
                llm_decision.policy_compliance.policy_references
            )

        return final_decision

    def _calculate_confidence_comparison(
        self,
        llm_decision: Optional[LLMDecisionResponse],
        rule_based_decision: Optional[AuthorizationDecision],
    ) -> Optional[Dict[str, float]]:
        """Calculate confidence comparison between decisions."""
        if not llm_decision or not rule_based_decision:
            return None

        return {
            "llm_confidence": llm_decision.confidence_score,
            "rule_based_confidence": rule_based_decision.confidence_score,
            "weighted_llm": llm_decision.confidence_score * self.llm_weight,
            "weighted_rule": rule_based_decision.confidence_score * self.rule_weight,
            "agreement_score": self._calculate_agreement_score(
                llm_decision, rule_based_decision
            ),
        }

    def _calculate_agreement_score(
        self,
        llm_decision: LLMDecisionResponse,
        rule_based_decision: AuthorizationDecision,
    ) -> float:
        """Calculate agreement score between LLM and rule-based decisions."""
        # Map LLM decision to DecisionStatus
        llm_status_mapping = {
            LLMDecisionStatus.APPROVE: DecisionStatus.APPROVED,
            LLMDecisionStatus.DENY: DecisionStatus.DENIED,
            LLMDecisionStatus.PENDING: DecisionStatus.MORE_INFO_NEEDED,
        }

        llm_status = llm_status_mapping.get(
            llm_decision.decision, DecisionStatus.MORE_INFO_NEEDED
        )

        # Perfect agreement
        if llm_status == rule_based_decision.status:
            return 1.0

        # Partial agreement (both non-approval)
        if (
            llm_status != DecisionStatus.APPROVED
            and rule_based_decision.status != DecisionStatus.APPROVED
        ):
            return 0.5

        # Complete disagreement
        return 0.0

    def _track_decision_method(self, method: str):
        """Track which decision method was used."""
        self._decision_metrics["total_decisions"] += 1

        if method == "llm_only":
            self._decision_metrics["llm_decisions"] += 1
        elif method == "rule_based_only":
            self._decision_metrics["rule_based_decisions"] += 1
        elif method == "hybrid":
            self._decision_metrics["hybrid_decisions"] += 1
        elif method.startswith("fallback"):
            self._decision_metrics["fallback_decisions"] += 1

    def get_decision_metrics(self) -> Dict[str, Any]:
        """Get decision-making metrics."""
        total = self._decision_metrics["total_decisions"]
        if total == 0:
            return self._decision_metrics

        return {
            **self._decision_metrics,
            "llm_percentage": (self._decision_metrics["llm_decisions"] / total) * 100,
            "rule_based_percentage": (
                self._decision_metrics["rule_based_decisions"] / total
            )
            * 100,
            "hybrid_percentage": (self._decision_metrics["hybrid_decisions"] / total)
            * 100,
            "fallback_percentage": (
                self._decision_metrics["fallback_decisions"] / total
            )
            * 100,
        }

    async def get_provider_decision_history(
        self,
        provider_id: str,
        status_filter: Optional[DecisionStatus] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Any:
        """Get decision history for a provider (placeholder implementation)."""
        # This would typically query the database for historical decisions
        # For now, return a mock response structure
        return type(
            "HistoryResult",
            (),
            {
                "decisions": [],
                "total_count": 0,
                "page": page,
                "page_size": page_size,
            },
        )()

    async def get_provider_decision_summary(
        self, provider_id: str, days_back: int = 30
    ) -> Any:
        """Get decision summary for a provider (placeholder implementation)."""
        # This would typically aggregate decision statistics from the database
        # For now, return a mock response structure
        return type(
            "SummaryResult",
            (),
            {
                "total_decisions": 0,
                "approval_rate": 0.0,
                "average_processing_time_hours": 0.0,
                "decisions_by_status": {},
                "decisions_by_procedure": {},
            },
        )()

    def _extract_policy_result_from_comprehensive(
        self, policy_validation_data: Dict[str, Any]
    ) -> Optional[PolicyValidationResult]:
        """Extract PolicyValidationResult from comprehensive validation data."""
        if not policy_validation_data:
            return None

        try:
            return PolicyValidationResult(
                is_covered=policy_validation_data.get("is_covered", False),
                policy_type=policy_validation_data.get("policy_type", "unknown"),
                reasoning=policy_validation_data.get("reasoning", []),
                confidence_score=policy_validation_data.get("confidence_score", 0.5),
                additional_requirements=policy_validation_data.get(
                    "additional_requirements", []
                ),
                policy_references=policy_validation_data.get("policy_references", []),
            )
        except Exception as e:
            self.logger.warning(
                f"Failed to extract policy result from comprehensive validation: {str(e)}"
            )
            return None
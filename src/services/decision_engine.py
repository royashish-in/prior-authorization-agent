"""
Decision engine service for generating authorization decisions.

This module implements the core decision logic that processes validation results
and generates authorization decisions with reasoning, confidence scoring,
and authorization number generation.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from src.models.authorization import AuthorizationRequest, AuthorizationDecision
from src.models.enums import DecisionStatus
from src.services.validation import ValidationResult
from src.services.policy_validation import PolicyValidationResult
from src.services.reasoning import ReasoningEngine, DecisionDocumentation
from src.core.logging import get_logger


@dataclass
class DecisionContext:
    """Context information for decision generation."""
    request: AuthorizationRequest
    validation_result: ValidationResult
    policy_result: Optional[PolicyValidationResult] = None
    cms_compliance: Optional[Dict[str, Any]] = None
    medical_necessity: Optional[Dict[str, Any]] = None


class DecisionEngine:
    """
    Core decision engine for authorization requests.
    
    Generates authorization decisions based on validation results,
    policy compliance, and medical necessity evaluation.
    """
    
    def __init__(self):
        """Initialize the decision engine."""
        self.logger = get_logger(self.__class__.__name__)
        
        # Initialize reasoning engine
        self.reasoning_engine = ReasoningEngine()
        
        # Decision thresholds
        self.approval_confidence_threshold = 0.8
        self.denial_confidence_threshold = 0.6
        
        # Authorization validity period (30 days)
        self.authorization_validity_days = 30
    
    def generate_decision(
        self,
        request: AuthorizationRequest,
        validation_result: ValidationResult,
        policy_result: Optional[PolicyValidationResult] = None,
        comprehensive_validation: Optional[Dict[str, Any]] = None
    ) -> AuthorizationDecision:
        """
        Generate an authorization decision based on validation results.
        
        Args:
            request: Authorization request
            validation_result: Basic validation result
            policy_result: Policy validation result (optional)
            comprehensive_validation: Comprehensive validation including medical necessity
            
        Returns:
            AuthorizationDecision with complete decision information
        """
        try:
            # Validate input parameters
            if request is None:
                self.logger.error("Decision generation failed: request cannot be None")
                return self._generate_error_decision(None, "Invalid request: request cannot be None")
            
            # Create decision context
            context = DecisionContext(
                request=request,
                validation_result=validation_result,
                policy_result=policy_result
            )
            
            # Extract additional context from comprehensive validation
            if comprehensive_validation and isinstance(comprehensive_validation, dict):
                context.cms_compliance = comprehensive_validation.get('cms_compliance')
                context.medical_necessity = comprehensive_validation.get('medical_necessity')
                context.policy_result = self._extract_policy_result_from_comprehensive(
                    comprehensive_validation.get('policy_validation', {})
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
                valid_until = datetime.now(timezone.utc) + timedelta(days=self.authorization_validity_days)
            
            # Collect policy references
            policy_references = self._collect_policy_references(context)
            
            # Generate additional information needed if applicable
            additional_info_needed = None
            if decision_status == DecisionStatus.MORE_INFO_NEEDED:
                additional_info_needed = self._generate_additional_info_requirements(context)
            
            # Generate alternative procedures if denied
            # Generate alternative procedures if denied
            alternative_procedures = None
            if decision_status == DecisionStatus.DENIED:
                detailed_alternatives = self.reasoning_engine.generate_alternative_procedures(
                    request, reasoning
                )
                # Convert to simple string list for compatibility
                alternative_procedures = [alt['description'] for alt in detailed_alternatives]
            
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
                alternative_procedures=alternative_procedures
            )
            
            self.logger.info(
                "Decision generated successfully",
                request_id=request.request_id,
                decision_id=decision_id,
                status=decision_status.value,
                confidence_score=confidence_score,
                authorization_number=authorization_number
            )
            
            return decision
            
        except Exception as e:
            self.logger.error(
                "Decision generation failed",
                request_id=request.request_id,
                error=str(e),
                exc_info=True
            )
            
            # Return denial decision for system errors
            return self._generate_error_decision(request, str(e))
    
    def generate_decision_with_detailed_reasoning(
        self,
        request: AuthorizationRequest,
        validation_result: ValidationResult,
        policy_result: Optional[PolicyValidationResult] = None,
        comprehensive_validation: Optional[Dict[str, Any]] = None
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
                reasoning_elements_count=len(reasoning_elements)
            )
            
            return decision, documentation
            
        except Exception as e:
            self.logger.error(
                "Failed to generate decision with detailed reasoning",
                request_id=request.request_id,
                error=str(e),
                exc_info=True
            )
            
            # Generate basic decision on error
            decision = self.generate_decision(request, validation_result, policy_result, comprehensive_validation)
            
            # Create minimal documentation
            documentation = DecisionDocumentation(
                decision_id=decision.decision_id,
                request_id=decision.request_id,
                decision_timestamp=decision.decided_at,
                decision_status=decision.status,
                reasoning_elements=[],
                policy_references=decision.policy_references,
                clinical_factors={},
                risk_assessment={'risk_level': 'unknown', 'risk_factors': []},
                alternative_procedures=[],
                audit_trail=[]
            )
            
            return decision, documentation
    
    def calculate_confidence_score(
        self,
        validation_results: List[ValidationResult],
        policy_results: List[PolicyValidationResult] = None,
        medical_necessity_score: float = None
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
    
    def _evaluate_decision(self, context: DecisionContext) -> Tuple[DecisionStatus, List[str], float]:
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
                [f"Request validation failed: {'; '.join([e.message for e in context.validation_result.errors])}"],
                0.9  # High confidence in denial for validation failures
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
                denial_factors.append("Request does not meet coverage policy requirements")
                reasoning.extend(context.policy_result.reasoning)
            
            # Check for additional requirements
            if context.policy_result.additional_requirements:
                info_needed_factors.extend(context.policy_result.additional_requirements)
        
        # Evaluate CMS compliance
        if context.cms_compliance:
            if context.cms_compliance.get('is_compliant', True):
                approval_factors.append("Request complies with CMS guidelines")
            else:
                denial_factors.append("Request does not comply with CMS guidelines")
                reasoning.extend(context.cms_compliance.get('compliance_issues', []))
            
            # Add CMS recommendations as info needed
            cms_recommendations = context.cms_compliance.get('recommendations', [])
            if cms_recommendations:
                info_needed_factors.extend(cms_recommendations)
        
        # Evaluate medical necessity
        if context.medical_necessity:
            necessity_level = context.medical_necessity.get('necessity_level', 'unknown')
            necessity_confidence = context.medical_necessity.get('confidence_score', 0.5)
            
            if necessity_level == 'high' and necessity_confidence >= 0.8:
                approval_factors.append("High medical necessity established")
            elif necessity_level == 'moderate' and necessity_confidence >= 0.6:
                approval_factors.append("Moderate medical necessity established")
            elif necessity_level == 'low' or necessity_confidence < 0.5:
                denial_factors.append("Insufficient medical necessity demonstrated")
            
            # Add medical necessity reasoning
            necessity_reasoning = context.medical_necessity.get('reasoning', [])
            reasoning.extend(necessity_reasoning)
            
            # Check for additional documentation needed
            additional_docs = context.medical_necessity.get('additional_documentation_needed', [])
            if additional_docs:
                info_needed_factors.extend(additional_docs)
        
        # Add validation warnings as reasoning
        if context.validation_result.warnings:
            reasoning.extend([f"Note: {warning}" for warning in context.validation_result.warnings])
        
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
        base_reasoning: List[str]
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
            reasoning.extend([f"Approval basis: {factor}" for factor in approval_factors])
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
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        return f"dec_{timestamp}_{unique_id}"
    
    def _generate_authorization_number(self) -> str:
        """Generate a unique authorization number for approved requests."""
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d')
        unique_id = str(uuid.uuid4())[:12].upper()
        return f"auth_{timestamp}_{unique_id}"
    
    def _collect_policy_references(self, context: DecisionContext) -> List[str]:
        """Collect all policy references from the decision context."""
        references = []
        
        if context.policy_result and context.policy_result.policy_references:
            references.extend(context.policy_result.policy_references)
        
        if context.cms_compliance:
            # Add NCD references
            ncd_policies = context.cms_compliance.get('ncd_policies', [])
            for policy in ncd_policies:
                if policy.get('policy_name'):
                    references.append(f"CMS NCD: {policy['policy_name']}")
            
            # Add LCD references
            lcd_policies = context.cms_compliance.get('lcd_policies', [])
            for policy in lcd_policies:
                if policy.get('policy_name'):
                    references.append(f"CMS LCD: {policy['policy_name']}")
        
        return list(set(references))  # Remove duplicates
    
    def _generate_additional_info_requirements(self, context: DecisionContext) -> List[str]:
        """Generate list of additional information needed."""
        requirements = []
        
        # From policy validation
        if context.policy_result and context.policy_result.additional_requirements:
            requirements.extend(context.policy_result.additional_requirements)
        
        # From CMS compliance
        if context.cms_compliance:
            cms_recommendations = context.cms_compliance.get('recommendations', [])
            requirements.extend(cms_recommendations)
        
        # From medical necessity
        if context.medical_necessity:
            additional_docs = context.medical_necessity.get('additional_documentation_needed', [])
            requirements.extend(additional_docs)
        
        # Remove duplicates and return
        return list(set(requirements))
    

    
    def _extract_policy_result_from_comprehensive(self, policy_validation: Dict[str, Any]) -> PolicyValidationResult:
        """Extract PolicyValidationResult from comprehensive validation dictionary."""
        from src.services.policy_validation import PolicyValidationResult, PolicyType
        
        if not policy_validation:
            return None
        
        try:
            return PolicyValidationResult(
                is_covered=policy_validation.get('is_covered', False),
                policy_id=policy_validation.get('policy_id', ''),
                policy_type=PolicyType(policy_validation.get('policy_type', 'PAYER')),
                reasoning=policy_validation.get('reasoning', []),
                confidence_score=policy_validation.get('confidence_score', 0.5),
                policy_references=policy_validation.get('policy_references', []),
                additional_requirements=policy_validation.get('additional_requirements', [])
            )
        except Exception as e:
            self.logger.error(f"Error extracting policy result: {str(e)}")
            return None
    
    def _generate_error_decision(self, request: Optional[AuthorizationRequest], error_message: str) -> AuthorizationDecision:
        """Generate a denial decision for system errors with user-friendly messaging."""
        
        # Log the technical error for debugging but don't expose it to users
        self.logger.error(f"Technical error in decision generation: {error_message}")
        
        # Provide user-friendly reasoning based on common error patterns
        user_friendly_reasoning = [
            "Authorization request requires manual review",
            "Unable to automatically process this request due to incomplete policy information",
            "Please ensure all required medical codes and clinical documentation are provided",
            "Contact your payer representative for assistance if this issue persists"
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
                "Confirm patient demographics and insurance information"
            ],
            alternative_procedures=["Submit request through manual review process", "Contact payer support for assistance"]
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
                    alternative_procedures=None
                )
            return None
            
        except Exception as e:
            self.logger.error(f"Error retrieving decision {decision_id}: {str(e)}")
            return None
    
    async def get_decision_by_request(self, request_id: str) -> Optional[AuthorizationDecision]:
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
            self.logger.error(f"Error retrieving decision for request {request_id}: {str(e)}")
            return None
    
    async def get_provider_decision_history(
        self,
        provider_id: str,
        status_filter: Optional[DecisionStatus] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20
    ) -> 'DecisionHistoryResult':
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
                    status=DecisionStatus.APPROVED if i % 3 != 2 else DecisionStatus.DENIED,
                    reasoning=["Medical necessity criteria met"] if i % 3 != 2 else ["Insufficient medical necessity"],
                    policy_references=["CMS_NCD_220.2"],
                    authorization_number=f"AUTH2024{i:06d}" if i % 3 != 2 else None,
                    valid_until=datetime.now(timezone.utc) + timedelta(days=30) if i % 3 != 2 else None,
                    confidence_score=0.95,
                    decided_at=datetime.now(timezone.utc) - timedelta(days=i),
                    additional_info_needed=None,
                    alternative_procedures=None
                )
                
                # Apply status filter
                if status_filter is None or decision.status == status_filter:
                    mock_decisions.append(decision)
            
            # Apply date filters
            if date_from:
                mock_decisions = [d for d in mock_decisions if d.decided_at >= date_from]
            if date_to:
                mock_decisions = [d for d in mock_decisions if d.decided_at <= date_to]
            
            return DecisionHistoryResult(
                decisions=mock_decisions,
                total_count=len(mock_decisions),
                page=page,
                page_size=page_size
            )
            
        except Exception as e:
            self.logger.error(f"Error retrieving decision history for provider {provider_id}: {str(e)}")
            return DecisionHistoryResult(decisions=[], total_count=0, page=page, page_size=page_size)
    
    async def get_provider_decision_summary(
        self,
        provider_id: str,
        days_back: int = 30
    ) -> 'DecisionSummaryResult':
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
            
            approval_rate = (approved_decisions / total_decisions) * 100 if total_decisions > 0 else 0
            
            return DecisionSummaryResult(
                total_decisions=total_decisions,
                approval_rate=approval_rate,
                average_processing_time_hours=1.5,
                decisions_by_status={
                    "approved": approved_decisions,
                    "denied": denied_decisions,
                    "more_info_needed": info_needed_decisions
                },
                decisions_by_procedure={
                    "mri": 85,
                    "ct_scan": 45,
                    "x_ray": 20
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error generating decision summary for provider {provider_id}: {str(e)}")
            return DecisionSummaryResult(
                total_decisions=0,
                approval_rate=0.0,
                average_processing_time_hours=0.0,
                decisions_by_status={},
                decisions_by_procedure={}
            )


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
"""
LLM Decision Service with Structured Response Parsing

This service provides the core LLM-based decision-making functionality for medical
authorization requests, including structured response parsing, confidence scoring,
and fallback mechanisms.
"""

import asyncio
import json
import logging
import html
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum
import re

from ..models.authorization import AuthorizationRequest, AuthorizationDecision
from ..models.enums import DecisionStatus, UrgencyLevel
from .huggingface_client import huggingface_client, HuggingFaceRequest, HuggingFaceResponse
from .prompt_engineering import (
    prompt_builder, prompt_template_manager, MedicalContext, PolicyContext,
    PromptType, PromptVersion
)
from .llm_config import llm_config, ModelType
from ..core.exceptions import ValidationException

logger = logging.getLogger(__name__)


class LLMDecisionStatus(str, Enum):
    """LLM decision status values."""
    APPROVE = "APPROVE"
    DENY = "DENY"
    PENDING = "PENDING"


@dataclass
class PolicyComplianceResult:
    """Policy compliance analysis result."""
    compliant: bool
    analysis: str
    violated_criteria: List[str] = field(default_factory=list)
    compliance_score: float = 0.0
    policy_references: List[str] = field(default_factory=list)


@dataclass
class RiskAssessment:
    """Risk assessment result."""
    risk_factors: List[str] = field(default_factory=list)
    contraindications: List[str] = field(default_factory=list)
    safety_considerations: str = ""
    risk_score: float = 0.0


@dataclass
class AlternativeProcedure:
    """Alternative procedure recommendation."""
    procedure: str
    rationale: str
    cost_effectiveness: Optional[str] = None
    clinical_appropriateness: float = 0.0


@dataclass
class LLMDecisionResponse:
    """Structured LLM decision response."""
    decision: LLMDecisionStatus
    confidence_score: float
    medical_reasoning: str
    policy_compliance: PolicyComplianceResult
    required_documentation: List[str] = field(default_factory=list)
    alternative_procedures: List[AlternativeProcedure] = field(default_factory=list)
    risk_assessment: RiskAssessment = field(default_factory=RiskAssessment)
    evidence_base: Optional[str] = None
    recommendations: Optional[str] = None
    model_used: str = ""
    processing_time_ms: float = 0.0
    template_used: str = ""
    raw_response: Optional[str] = None
    validation_errors: List[str] = field(default_factory=list)
    fallback_used: bool = False


@dataclass
class ValidationResult:
    """Response validation result."""
    is_valid: bool
    confidence_score: float
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    corrected_response: Optional[Dict[str, Any]] = None


class ResponseParser:
    """Parses and validates LLM responses into structured format."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.ResponseParser")
    
    def parse_response(self, raw_response: str, model_id: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
        """Parse raw LLM response into structured format."""
        errors = []
        
        try:
            # Try to extract JSON from response
            json_data = self._extract_json(raw_response)
            if not json_data:
                errors.append("No valid JSON found in response")
                return None, errors
            
            # Validate required fields
            validation_errors = self._validate_json_structure(json_data)
            if validation_errors:
                errors.extend(validation_errors)
                # Try to fix common issues
                json_data = self._attempt_json_correction(json_data)
            
            return json_data, errors
            
        except Exception as e:
            self.logger.error(f"Error parsing response from {model_id}: {str(e)}")
            errors.append(f"Parsing error: {str(e)}")
            return None, errors
    
    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from text response."""
        # Try to find JSON block
        json_patterns = [
            r'```json\s*(\{.*?\})\s*```',  # JSON code block
            r'```\s*(\{.*?\})\s*```',      # Generic code block
            r'(\{.*\})',                   # Any JSON-like structure
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue
        
        # Try parsing the entire text as JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        return None
    
    def _validate_json_structure(self, data: Dict[str, Any]) -> List[str]:
        """Validate JSON structure against expected schema."""
        errors = []
        
        # Required fields
        required_fields = ['decision', 'confidence_score', 'medical_reasoning']
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        
        # Validate decision value
        if 'decision' in data:
            valid_decisions = ['APPROVE', 'DENY', 'PENDING']
            if data['decision'] not in valid_decisions:
                errors.append(f"Invalid decision value: {data['decision']}. Must be one of {valid_decisions}")
        
        # Validate confidence score
        if 'confidence_score' in data:
            try:
                score = float(data['confidence_score'])
                if not 0.0 <= score <= 1.0:
                    errors.append("Confidence score must be between 0.0 and 1.0")
            except (ValueError, TypeError):
                errors.append("Confidence score must be a number")
        
        # Validate medical reasoning
        if 'medical_reasoning' in data:
            if not isinstance(data['medical_reasoning'], str) or not data['medical_reasoning'].strip():
                errors.append("Medical reasoning must be a non-empty string")
        
        return errors
    
    def _attempt_json_correction(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Attempt to correct common JSON structure issues."""
        corrected = data.copy()
        
        # Fix decision values
        if 'decision' in corrected:
            decision = str(corrected['decision']).upper()
            if decision in ['APPROVED', 'APPROVE']:
                corrected['decision'] = 'APPROVE'
            elif decision in ['DENIED', 'DENY']:
                corrected['decision'] = 'DENY'
            elif decision in ['PENDING', 'DEFER', 'DEFER_FOR_ADDITIONAL_INFO']:
                corrected['decision'] = 'PENDING'
        
        # Ensure confidence score is float
        if 'confidence_score' in corrected:
            try:
                corrected['confidence_score'] = float(corrected['confidence_score'])
                # Clamp to valid range
                corrected['confidence_score'] = max(0.0, min(1.0, corrected['confidence_score']))
            except (ValueError, TypeError):
                corrected['confidence_score'] = 0.5  # Default fallback
        
        # Ensure lists are properly formatted
        list_fields = ['required_documentation', 'alternative_procedures', 'risk_factors', 'contraindications']
        for field in list_fields:
            if field in corrected and not isinstance(corrected[field], list):
                if isinstance(corrected[field], str):
                    corrected[field] = [corrected[field]]
                else:
                    corrected[field] = []
        
        return corrected


class ConfidenceScorer:
    """Calculates confidence scores for LLM decisions."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.ConfidenceScorer")
    
    def calculate_confidence(
        self,
        parsed_response: Dict[str, Any],
        model_confidence: float,
        validation_errors: List[str]
    ) -> float:
        """Calculate overall confidence score."""
        
        # Start with model's confidence
        base_confidence = parsed_response.get('confidence_score', model_confidence)
        
        # Adjust for validation errors
        error_penalty = len(validation_errors) * 0.1
        adjusted_confidence = max(0.0, base_confidence - error_penalty)
        
        # Adjust for response completeness
        completeness_bonus = self._calculate_completeness_bonus(parsed_response)
        final_confidence = min(1.0, adjusted_confidence + completeness_bonus)
        
        self.logger.debug(f"Confidence calculation: base={base_confidence}, "
                         f"errors_penalty={error_penalty}, completeness_bonus={completeness_bonus}, "
                         f"final={final_confidence}")
        
        return final_confidence
    
    def _calculate_completeness_bonus(self, response: Dict[str, Any]) -> float:
        """Calculate bonus for response completeness."""
        bonus = 0.0
        
        # Bonus for detailed medical reasoning
        if response.get('medical_reasoning') and len(response['medical_reasoning']) > 100:
            bonus += 0.05
        
        # Bonus for policy compliance analysis
        if response.get('policy_compliance'):
            bonus += 0.05
        
        # Bonus for alternative procedures
        if response.get('alternative_procedures') and len(response['alternative_procedures']) > 0:
            bonus += 0.03
        
        # Bonus for risk assessment
        if response.get('risk_factors') or response.get('contraindications'):
            bonus += 0.03
        
        return min(0.15, bonus)  # Cap bonus at 0.15


class DecisionValidator:
    """Validates LLM decisions against business rules."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.DecisionValidator")
    
    def validate_decision(
        self,
        decision_response: LLMDecisionResponse,
        original_request: AuthorizationRequest
    ) -> ValidationResult:
        """Validate decision against business rules."""
        
        errors = []
        warnings = []
        
        # Validate confidence threshold
        min_confidence = 0.6  # Configurable threshold
        if decision_response.confidence_score < min_confidence:
            warnings.append(f"Low confidence score: {decision_response.confidence_score}")
        
        # Validate decision consistency
        if decision_response.decision == LLMDecisionStatus.APPROVE:
            if not decision_response.medical_reasoning:
                errors.append("Approved decisions must include medical reasoning")
        
        elif decision_response.decision == LLMDecisionStatus.DENY:
            if not decision_response.alternative_procedures:
                warnings.append("Denied decisions should include alternative procedures")
        
        elif decision_response.decision == LLMDecisionStatus.PENDING:
            if not decision_response.required_documentation:
                errors.append("Pending decisions must specify required documentation")
        
        # Validate urgency handling
        if original_request.urgency_level == UrgencyLevel.URGENT:
            if decision_response.decision == LLMDecisionStatus.PENDING:
                warnings.append("Urgent requests should avoid pending status when possible")
        
        is_valid = len(errors) == 0
        confidence_adjustment = max(0.0, decision_response.confidence_score - (len(errors) * 0.2))
        
        return ValidationResult(
            is_valid=is_valid,
            confidence_score=confidence_adjustment,
            errors=errors,
            warnings=warnings
        )


class LLMDecisionService:
    """Main LLM decision service with async processing capabilities."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.response_parser = ResponseParser()
        self.confidence_scorer = ConfidenceScorer()
        self.decision_validator = DecisionValidator()
        self._initialized = False
    
    def _sanitize_input(self, text: str) -> str:
        """Sanitize input to prevent injection attacks."""
        if not isinstance(text, str):
            return str(text)
        # Remove dangerous characters and HTML escape
        sanitized = re.sub(r'[<>"\';\\]', '', text)
        return html.escape(sanitized)[:1000]
    
    async def initialize(self):
        """Initialize the LLM decision service."""
        if self._initialized:
            return
        
        self.logger.info("Initializing LLM Decision Service")
        
        # Initialize Hugging Face client
        await huggingface_client.initialize()
        
        self._initialized = True
        self.logger.info("LLM Decision Service initialized")
    
    async def make_decision(
        self,
        request: AuthorizationRequest,
        policy_context: PolicyContext,
        template_id: Optional[str] = None
    ) -> LLMDecisionResponse:
        """Make an authorization decision using LLM."""
        
        if not self._initialized:
            await self.initialize()
        
        start_time = datetime.now()
        
        # Select template
        if not template_id:
            template_id = self._select_optimal_template(request)
        
        # Build prompt
        prompt = prompt_builder.build_from_authorization_request(
            template_id, request, policy_context
        )
        
        if not prompt:
            raise Exception(f"Failed to build prompt with template {template_id}")
        
        # Select model
        model_config = self._select_optimal_model(request)
        if not model_config:
            raise Exception("No suitable LLM model available")
        
        # Make LLM request
        llm_request = HuggingFaceRequest(
            inputs=prompt,
            parameters={
                "max_new_tokens": model_config.max_tokens,
                "temperature": model_config.temperature,
                "top_p": model_config.top_p,
                "do_sample": True if model_config.temperature > 0 else False
            }
        )
        
        try:
            # Query LLM
            llm_response = await huggingface_client.query_model(
                model_config.model_id, llm_request
            )
            
            if not llm_response.success:
                # Try fallback
                return await self._handle_llm_failure(
                    request, policy_context, template_id, llm_response.error_message
                )
            
            # Parse response
            decision_response = await self._parse_llm_response(
                llm_response, model_config.model_id, template_id, start_time
            )
            
            # Validate decision
            validation_result = self.decision_validator.validate_decision(
                decision_response, request
            )
            
            # Update confidence based on validation
            if validation_result.errors:
                decision_response.validation_errors = validation_result.errors
                decision_response.confidence_score = validation_result.confidence_score
            
            # Check if confidence is too low for final decision
            if decision_response.confidence_score < model_config.confidence_threshold:
                self.logger.warning(f"Low confidence decision: {decision_response.confidence_score}")
                # Could trigger human review or fallback here
            
            # Update template metrics
            prompt_template_manager.update_template_metrics(
                template_id, 
                validation_result.is_valid,
                decision_response.confidence_score
            )
            
            return decision_response
            
        except Exception as e:
            self.logger.error(f"Error in LLM decision making: {str(e)}")
            return await self._handle_llm_failure(
                request, policy_context, template_id, str(e)
            )
    
    async def _parse_llm_response(
        self,
        llm_response: HuggingFaceResponse,
        model_id: str,
        template_id: str,
        start_time: datetime
    ) -> LLMDecisionResponse:
        """Parse LLM response into structured format."""
        
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        # Extract text from response
        raw_text = self._extract_response_text(llm_response.response_data)
        
        # Parse JSON structure
        parsed_data, parsing_errors = self.response_parser.parse_response(raw_text, model_id)
        
        if not parsed_data:
            raise Exception(f"Failed to parse LLM response: {parsing_errors}")
        
        # Calculate confidence
        model_confidence = llm_response.confidence_score or 0.8
        final_confidence = self.confidence_scorer.calculate_confidence(
            parsed_data, model_confidence, parsing_errors
        )
        
        # Build structured response
        return self._build_decision_response(
            parsed_data, model_id, template_id, processing_time,
            raw_text, parsing_errors, llm_response.fallback_used, final_confidence
        )
    
    def _extract_response_text(self, response_data: Any) -> str:
        """Extract text from various response formats."""
        if isinstance(response_data, str):
            return response_data
        elif isinstance(response_data, list) and len(response_data) > 0:
            if isinstance(response_data[0], dict):
                return response_data[0].get('generated_text', str(response_data[0]))
            else:
                return str(response_data[0])
        elif isinstance(response_data, dict):
            return response_data.get('generated_text', str(response_data))
        else:
            return str(response_data)
    
    def _build_decision_response(
        self,
        parsed_data: Dict[str, Any],
        model_id: str,
        template_id: str,
        processing_time: float,
        raw_text: str,
        parsing_errors: List[str],
        fallback_used: bool,
        confidence_score: float
    ) -> LLMDecisionResponse:
        """Build structured decision response."""
        
        # Parse policy compliance
        policy_compliance_data = parsed_data.get('policy_compliance', {})
        if isinstance(policy_compliance_data, str):
            policy_compliance = PolicyComplianceResult(
                compliant=True,  # Default assumption
                analysis=policy_compliance_data
            )
        else:
            policy_compliance = PolicyComplianceResult(
                compliant=policy_compliance_data.get('compliant', True),
                analysis=policy_compliance_data.get('analysis', ''),
                violated_criteria=policy_compliance_data.get('violated_criteria', []),
                compliance_score=policy_compliance_data.get('compliance_score', 1.0)
            )
        
        # Parse risk assessment
        risk_data = parsed_data.get('risk_assessment', {})
        if not isinstance(risk_data, dict):
            risk_data = {}
        
        risk_assessment = RiskAssessment(
            risk_factors=parsed_data.get('risk_factors', risk_data.get('risk_factors', [])),
            contraindications=parsed_data.get('contraindications', risk_data.get('contraindications', [])),
            safety_considerations=risk_data.get('safety_considerations', ''),
            risk_score=risk_data.get('risk_score', 0.0)
        )
        
        # Parse alternative procedures
        alternatives_data = parsed_data.get('alternative_procedures', [])
        alternative_procedures = []
        
        for alt in alternatives_data:
            if isinstance(alt, str):
                alternative_procedures.append(AlternativeProcedure(
                    procedure=alt,
                    rationale="Alternative procedure suggested"
                ))
            elif isinstance(alt, dict):
                alternative_procedures.append(AlternativeProcedure(
                    procedure=alt.get('procedure', alt.get('alternative', '')),
                    rationale=alt.get('rationale', alt.get('clinical_rationale', '')),
                    cost_effectiveness=alt.get('cost_effectiveness'),
                    clinical_appropriateness=alt.get('clinical_appropriateness', 0.0)
                ))
        
        return LLMDecisionResponse(
            decision=LLMDecisionStatus(parsed_data['decision']),
            confidence_score=confidence_score,
            medical_reasoning=parsed_data['medical_reasoning'],
            policy_compliance=policy_compliance,
            required_documentation=parsed_data.get('required_documentation', []),
            alternative_procedures=alternative_procedures,
            risk_assessment=risk_assessment,
            evidence_base=parsed_data.get('evidence_base', parsed_data.get('evidence_support')),
            recommendations=parsed_data.get('recommendations', parsed_data.get('clinical_recommendations')),
            model_used=model_id,
            processing_time_ms=processing_time,
            template_used=template_id,
            raw_response=raw_text,
            validation_errors=parsing_errors,
            fallback_used=fallback_used
        )
    
    def _select_optimal_template(self, request: AuthorizationRequest) -> str:
        """Select the optimal prompt template for the request."""
        
        # For now, use enhanced template for complex cases, basic for simple ones
        if (len(request.diagnosis_codes) > 1 or 
            request.urgency_level == UrgencyLevel.URGENT or
            (request.clinical_notes and len(request.clinical_notes) > 500)):
            return "auth_decision_v2_enhanced"
        else:
            return "auth_decision_v1_basic"
    
    def _select_optimal_model(self, request: AuthorizationRequest):
        """Select the optimal model for the request."""
        
        # Get primary model (highest priority enabled model)
        primary_model = llm_config.get_primary_model()
        if primary_model:
            return primary_model
        
        # Fallback to any enabled model
        enabled_models = llm_config.get_enabled_models()
        if enabled_models:
            return enabled_models[0]
        
        return None
    
    async def _handle_llm_failure(
        self,
        request: AuthorizationRequest,
        policy_context: PolicyContext,
        template_id: str,
        error_message: str
    ) -> LLMDecisionResponse:
        """Handle LLM failure with fallback mechanisms."""
        
        self.logger.warning(f"LLM failure, attempting fallback: {error_message}")
        
        # Try fallback models
        fallback_models = llm_config.get_fallback_models()
        for model in fallback_models:
            try:
                prompt = prompt_builder.build_from_authorization_request(
                    template_id, request, policy_context
                )
                
                llm_request = HuggingFaceRequest(
                    inputs=prompt,
                    parameters={
                        "max_new_tokens": model.max_tokens,
                        "temperature": model.temperature,
                        "top_p": model.top_p
                    }
                )
                
                llm_response = await huggingface_client.query_model(
                    model.model_id, llm_request
                )
                
                if llm_response.success:
                    decision_response = await self._parse_llm_response(
                        llm_response, model.model_id, template_id, datetime.now()
                    )
                    decision_response.fallback_used = True
                    return decision_response
                    
            except Exception as e:
                self.logger.warning(f"Fallback model {model.model_id} also failed: {str(e)}")
                continue
        
        # If all LLMs fail, return a low-confidence pending decision
        return LLMDecisionResponse(
            decision=LLMDecisionStatus.PENDING,
            confidence_score=0.1,
            medical_reasoning="Unable to process request due to LLM service unavailability. Manual review required.",
            policy_compliance=PolicyComplianceResult(
                compliant=False,
                analysis="Could not perform policy compliance analysis due to service failure"
            ),
            required_documentation=["Manual clinical review required due to system unavailability"],
            model_used="fallback_error",
            processing_time_ms=0.0,
            template_used=template_id,
            validation_errors=[f"LLM service failure: {error_message}"],
            fallback_used=True
        )
    
    async def validate_medical_reasoning(
        self,
        decision: LLMDecisionResponse
    ) -> ValidationResult:
        """Validate the medical reasoning in a decision."""
        
        errors = []
        warnings = []
        
        # Check reasoning completeness
        if not decision.medical_reasoning or len(decision.medical_reasoning.strip()) < 50:
            errors.append("Medical reasoning is too brief or missing")
        
        # Check for medical terminology
        medical_terms = ['diagnosis', 'treatment', 'procedure', 'medical', 'clinical', 'patient']
        reasoning_lower = decision.medical_reasoning.lower()
        if not any(term in reasoning_lower for term in medical_terms):
            warnings.append("Medical reasoning lacks medical terminology")
        
        # Check policy references
        if decision.policy_compliance.compliant and not decision.policy_compliance.analysis:
            warnings.append("Policy compliance marked as compliant but lacks analysis")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            confidence_score=decision.confidence_score,
            errors=errors,
            warnings=warnings
        )
    
    async def get_model_health(self) -> Dict[str, Any]:
        """Get health status of LLM models."""
        return await huggingface_client.get_comprehensive_health_status()
    
    async def shutdown(self):
        """Shutdown the service and cleanup resources."""
        await huggingface_client.shutdown()
        self.logger.info("LLM Decision Service shutdown")


# Global service instance
llm_decision_service = LLMDecisionService()
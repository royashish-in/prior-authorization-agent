"""
Prompt Engineering System for Medical Decision-Making

This module provides medical context-aware prompt templates and builders
for LLM-based authorization decisions with A/B testing and versioning capabilities.
"""

import json
import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, field
from pydantic import BaseModel, Field, validator
import logging

from ..models.authorization import AuthorizationRequest, AuthorizationDecision
from ..models.patient import PatientDemographics
from ..models.medical_codes import ICD10Code, CPTCode, HCPCSCode
from ..models.enums import UrgencyLevel, ProcedureType, DecisionStatus

logger = logging.getLogger(__name__)


class PromptType(str, Enum):
    """Types of medical decision prompts."""
    AUTHORIZATION_DECISION = "authorization_decision"
    MEDICAL_NECESSITY = "medical_necessity"
    POLICY_COMPLIANCE = "policy_compliance"
    ALTERNATIVE_PROCEDURES = "alternative_procedures"
    RISK_ASSESSMENT = "risk_assessment"


class PromptVersion(str, Enum):
    """Prompt template versions for A/B testing."""
    V1_BASIC = "v1_basic"
    V2_ENHANCED = "v2_enhanced"
    V3_CLINICAL_FOCUSED = "v3_clinical_focused"
    V4_POLICY_FOCUSED = "v4_policy_focused"


@dataclass
class PromptTemplate:
    """Medical decision prompt template."""
    template_id: str
    name: str
    version: PromptVersion
    prompt_type: PromptType
    template: str
    description: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True
    performance_metrics: Dict[str, float] = field(default_factory=dict)
    usage_count: int = 0
    success_rate: float = 0.0
    avg_confidence: float = 0.0
    
    def get_template_hash(self) -> str:
        """Generate hash for template content."""
        return hashlib.md5(self.template.encode()).hexdigest()


@dataclass
class MedicalContext:
    """Medical context for prompt building."""
    patient_age: int
    patient_gender: str
    diagnosis_codes: List[Dict[str, Any]] = field(default_factory=list)
    procedure_codes: List[Dict[str, Any]] = field(default_factory=list)
    clinical_notes: Optional[str] = None
    urgency_level: str = "routine"
    medical_history: List[str] = field(default_factory=list)
    comorbidities: List[str] = field(default_factory=list)
    current_medications: List[str] = field(default_factory=list)
    allergies: List[str] = field(default_factory=list)
    lab_results: Dict[str, Any] = field(default_factory=dict)
    imaging_history: List[str] = field(default_factory=list)
    provider_notes: str = ""
    consultation_notes: str = ""
    
    # Legacy properties for backward compatibility
    @property
    def primary_diagnosis(self) -> str:
        return self.diagnosis_codes[0]["description"] if self.diagnosis_codes else ""
    
    @property
    def primary_icd10(self) -> str:
        return self.diagnosis_codes[0]["code"] if self.diagnosis_codes else ""
    
    @property
    def secondary_diagnoses(self) -> List[str]:
        return [d["description"] for d in self.diagnosis_codes[1:]] if len(self.diagnosis_codes) > 1 else []
    
    @property
    def secondary_icd10s(self) -> List[str]:
        return [d["code"] for d in self.diagnosis_codes[1:]] if len(self.diagnosis_codes) > 1 else []
    
    @property
    def procedure_name(self) -> str:
        return self.procedure_codes[0]["description"] if self.procedure_codes else ""
    
    @property
    def treatment_history(self) -> List[str]:
        return self.medical_history
    
    @property
    def contraindications(self) -> List[str]:
        return []  # Could be derived from allergies or other data


@dataclass
class PolicyContext:
    """Policy context for prompt building."""
    payer_id: str = "default_payer"
    policy_version: str = "2024.1"
    coverage_criteria: List[str] = field(default_factory=list)
    exclusions: List[str] = field(default_factory=list)
    prior_auth_requirements: bool = True
    clinical_guidelines: str = "standard"
    
    # Legacy properties for backward compatibility
    @property
    def payer_name(self) -> str:
        return f"Payer {self.payer_id}"
    
    @property
    def coverage_policies(self) -> List[str]:
        return self.coverage_criteria
    
    @property
    def medical_necessity_criteria(self) -> List[str]:
        return self.coverage_criteria


class PromptTemplateManager:
    """Manages medical decision prompt templates."""
    
    def __init__(self):
        self._templates: Dict[str, PromptTemplate] = {}
        self._load_default_templates()
    
    def _load_default_templates(self):
        """Load default prompt templates."""
        
        # V1 Basic Authorization Decision Template
        basic_auth_template = PromptTemplate(
            template_id="auth_decision_v1_basic",
            name="Basic Authorization Decision",
            version=PromptVersion.V1_BASIC,
            prompt_type=PromptType.AUTHORIZATION_DECISION,
            description="Basic template for authorization decisions",
            template="""You are a medical AI assistant specializing in prior authorization decisions for healthcare procedures.

PATIENT INFORMATION:
- Age: {patient_age}
- Gender: {patient_gender}
- Primary Diagnosis: {primary_diagnosis} (ICD-10: {primary_icd10})
{secondary_diagnoses_section}

REQUESTED PROCEDURE:
- Procedure: {procedure_name}
- Codes: {procedure_codes}
- Urgency: {urgency_level}
{clinical_notes_section}

POLICY CONTEXT:
- Payer: {payer_name}
{coverage_policies_section}
{medical_necessity_section}

Please analyze this prior authorization request and provide your decision in the following JSON format:
{{
    "decision": "APPROVE|DENY|PENDING",
    "confidence_score": 0.0-1.0,
    "medical_reasoning": "Detailed clinical justification",
    "policy_compliance": "Policy compliance analysis",
    "required_documentation": ["List of additional documentation needed"],
    "alternative_procedures": ["Suggested alternatives if denied"],
    "risk_factors": ["Identified risk factors"],
    "contraindications": ["Any contraindications found"]
}}"""
        )
        
        # V2 Enhanced Authorization Decision Template
        enhanced_auth_template = PromptTemplate(
            template_id="auth_decision_v2_enhanced",
            name="Enhanced Authorization Decision",
            version=PromptVersion.V2_ENHANCED,
            prompt_type=PromptType.AUTHORIZATION_DECISION,
            description="Enhanced template with detailed medical context",
            template="""You are an expert medical AI assistant with specialized knowledge in prior authorization for imaging and diagnostic procedures. Your role is to make evidence-based decisions that balance medical necessity with appropriate resource utilization.

CLINICAL PRESENTATION:
Patient Demographics:
- Age: {patient_age} years
- Gender: {patient_gender}

Primary Clinical Concern:
- Diagnosis: {primary_diagnosis}
- ICD-10 Code: {primary_icd10}

{secondary_diagnoses_section}
{comorbidities_section}
{treatment_history_section}

REQUESTED INTERVENTION:
- Procedure: {procedure_name}
- CPT/HCPCS Codes: {procedure_codes}
- Clinical Urgency: {urgency_level}

{clinical_notes_section}

AUTHORIZATION FRAMEWORK:
Payer: {payer_name}

Coverage Criteria:
{coverage_policies_section}

Medical Necessity Standards:
{medical_necessity_section}

Clinical Guidelines:
{clinical_guidelines_section}

DECISION ANALYSIS:
Please conduct a comprehensive evaluation considering:
1. Medical necessity based on clinical presentation
2. Appropriateness of requested procedure
3. Policy compliance and coverage criteria
4. Evidence-based medicine guidelines
5. Risk-benefit analysis
6. Alternative diagnostic approaches

Provide your analysis in this structured JSON format:
{{
    "decision": "APPROVE|DENY|PENDING",
    "confidence_score": 0.0-1.0,
    "medical_reasoning": "Comprehensive clinical justification with specific medical rationale",
    "policy_compliance": {{
        "compliant": true/false,
        "analysis": "Detailed policy compliance assessment",
        "violated_criteria": ["List any violated criteria"]
    }},
    "evidence_base": "References to clinical guidelines or literature",
    "required_documentation": ["Specific additional documentation needed"],
    "alternative_procedures": [
        {{
            "procedure": "Alternative procedure name",
            "rationale": "Why this alternative is appropriate",
            "cost_effectiveness": "Cost comparison if relevant"
        }}
    ],
    "risk_assessment": {{
        "risk_factors": ["Identified clinical risk factors"],
        "contraindications": ["Absolute or relative contraindications"],
        "safety_considerations": "Safety analysis"
    }},
    "recommendations": "Additional clinical recommendations"
}}"""
        )
        
        # V3 Clinical-Focused Template
        clinical_focused_template = PromptTemplate(
            template_id="auth_decision_v3_clinical",
            name="Clinical-Focused Authorization",
            version=PromptVersion.V3_CLINICAL_FOCUSED,
            prompt_type=PromptType.AUTHORIZATION_DECISION,
            description="Template emphasizing clinical decision-making",
            template="""As a board-certified physician with expertise in medical imaging and diagnostic procedures, evaluate this prior authorization request using clinical best practices and evidence-based medicine.

CLINICAL CASE SUMMARY:
Patient: {patient_age}-year-old {patient_gender}

Chief Clinical Concern:
• Primary Diagnosis: {primary_diagnosis} (ICD-10: {primary_icd10})
{secondary_diagnoses_section}

Clinical Context:
{comorbidities_section}
{treatment_history_section}

Requested Diagnostic Intervention:
• Procedure: {procedure_name}
• Medical Codes: {procedure_codes}
• Clinical Priority: {urgency_level}

Supporting Clinical Information:
{clinical_notes_section}

CLINICAL DECISION FRAMEWORK:

Medical Necessity Assessment:
{medical_necessity_section}

Evidence-Based Guidelines:
{clinical_guidelines_section}

Coverage Parameters:
{coverage_policies_section}

CLINICAL EVALUATION:
Apply your medical expertise to assess:

1. DIAGNOSTIC NECESSITY: Is this procedure medically necessary for diagnosis or treatment planning?
2. CLINICAL APPROPRIATENESS: Is this the most appropriate diagnostic approach?
3. TIMING CONSIDERATIONS: Is the timing of this procedure clinically justified?
4. ALTERNATIVE APPROACHES: Are there equally effective, less invasive alternatives?
5. RISK-BENEFIT RATIO: Do the potential benefits outweigh the risks?

Provide your clinical decision in this format:
{{
    "clinical_decision": "APPROVE|DENY|DEFER_FOR_ADDITIONAL_INFO",
    "medical_confidence": 0.0-1.0,
    "clinical_rationale": "Primary medical reasoning based on clinical presentation",
    "diagnostic_necessity": {{
        "necessary": true/false,
        "justification": "Clinical justification for diagnostic necessity"
    }},
    "clinical_appropriateness": {{
        "appropriate": true/false,
        "reasoning": "Assessment of procedural appropriateness"
    }},
    "evidence_support": "Relevant clinical guidelines or literature support",
    "additional_clinical_info_needed": ["Specific clinical information required"],
    "recommended_alternatives": [
        {{
            "alternative": "Alternative diagnostic approach",
            "clinical_rationale": "Medical reasoning for alternative",
            "when_appropriate": "Clinical scenarios where alternative is preferred"
        }}
    ],
    "clinical_recommendations": "Additional clinical guidance for optimal patient care"
}}"""
        )
        
        # Medical Necessity Specific Template
        medical_necessity_template = PromptTemplate(
            template_id="medical_necessity_v1",
            name="Medical Necessity Assessment",
            version=PromptVersion.V1_BASIC,
            prompt_type=PromptType.MEDICAL_NECESSITY,
            description="Focused template for medical necessity evaluation",
            template="""Evaluate the medical necessity of the requested procedure based on clinical presentation and established medical criteria.

CLINICAL INFORMATION:
Patient: {patient_age}-year-old {patient_gender}
Primary Diagnosis: {primary_diagnosis} (ICD-10: {primary_icd10})
{secondary_diagnoses_section}
Requested Procedure: {procedure_name} ({procedure_codes})
{clinical_notes_section}

MEDICAL NECESSITY CRITERIA:
{medical_necessity_section}

ASSESSMENT FOCUS:
Determine if the requested procedure meets medical necessity standards by evaluating:
1. Clinical indication strength
2. Symptom severity and duration
3. Failed conservative treatments (if applicable)
4. Diagnostic value for treatment planning
5. Impact on patient outcomes

Provide assessment in JSON format:
{{
    "medical_necessity": "MEETS|DOES_NOT_MEET|INSUFFICIENT_INFO",
    "necessity_score": 0.0-1.0,
    "clinical_indicators": ["Strong clinical indicators present"],
    "necessity_rationale": "Detailed medical necessity justification",
    "missing_criteria": ["Criteria not met or insufficient information"],
    "additional_requirements": ["What additional information would establish necessity"]
}}"""
        )
        
        # Store templates
        templates = [
            basic_auth_template,
            enhanced_auth_template,
            clinical_focused_template,
            medical_necessity_template
        ]
        
        for template in templates:
            self._templates[template.template_id] = template
    
    def get_template(self, template_id: str) -> Optional[PromptTemplate]:
        """Get a specific template by ID."""
        return self._templates.get(template_id)
    
    def get_templates_by_type(self, prompt_type: PromptType) -> List[PromptTemplate]:
        """Get all templates of a specific type."""
        return [t for t in self._templates.values() if t.prompt_type == prompt_type]
    
    def get_active_templates(self) -> List[PromptTemplate]:
        """Get all active templates."""
        return [t for t in self._templates.values() if t.is_active]
    
    def add_template(self, template: PromptTemplate) -> None:
        """Add a new template."""
        self._templates[template.template_id] = template
    
    def update_template_metrics(self, template_id: str, success: bool, confidence: float) -> None:
        """Update template performance metrics."""
        if template_id in self._templates:
            template = self._templates[template_id]
            template.usage_count += 1
            
            # Update success rate
            if template.usage_count == 1:
                template.success_rate = 1.0 if success else 0.0
            else:
                current_successes = template.success_rate * (template.usage_count - 1)
                new_successes = current_successes + (1 if success else 0)
                template.success_rate = new_successes / template.usage_count
            
            # Update average confidence
            if template.usage_count == 1:
                template.avg_confidence = confidence
            else:
                total_confidence = template.avg_confidence * (template.usage_count - 1)
                template.avg_confidence = (total_confidence + confidence) / template.usage_count


class PromptBuilder:
    """Builds medical decision prompts from templates and context."""
    
    def __init__(self, template_manager: PromptTemplateManager):
        self.template_manager = template_manager
    
    def build_prompt(
        self,
        template_id: str,
        medical_context: MedicalContext,
        policy_context: PolicyContext
    ) -> Optional[str]:
        """Build a prompt from template and context."""
        template = self.template_manager.get_template(template_id)
        if not template:
            logger.error(f"Template not found: {template_id}")
            return None
        
        try:
            # Prepare context variables
            context_vars = self._prepare_context_variables(medical_context, policy_context)
            
            # Format template
            formatted_prompt = template.template.format(**context_vars)
            
            logger.info(f"Built prompt using template {template_id}")
            return formatted_prompt
            
        except Exception as e:
            logger.error(f"Error building prompt with template {template_id}: {str(e)}")
            return None
    
    def _prepare_context_variables(
        self,
        medical_context: MedicalContext,
        policy_context: PolicyContext
    ) -> Dict[str, str]:
        """Prepare context variables for template formatting."""
        
        # Secondary diagnoses section
        secondary_diagnoses_section = ""
        if medical_context.secondary_diagnoses:
            diagnoses_list = []
            for i, (diag, code) in enumerate(zip(
                medical_context.secondary_diagnoses,
                medical_context.secondary_icd10s or []
            )):
                if code:
                    diagnoses_list.append(f"  • {diag} (ICD-10: {code})")
                else:
                    diagnoses_list.append(f"  • {diag}")
            
            secondary_diagnoses_section = "Secondary Diagnoses:\n" + "\n".join(diagnoses_list)
        
        # Clinical notes section
        clinical_notes_section = ""
        if medical_context.clinical_notes:
            clinical_notes_section = f"Clinical Notes:\n{medical_context.clinical_notes}"
        
        # Comorbidities section
        comorbidities_section = ""
        if medical_context.comorbidities:
            comorbidities_section = "Comorbidities:\n" + "\n".join([f"  • {c}" for c in medical_context.comorbidities])
        
        # Treatment history section
        treatment_history_section = ""
        if medical_context.treatment_history:
            treatment_history_section = "Previous Treatments:\n" + "\n".join([f"  • {t}" for t in medical_context.treatment_history])
        
        # Coverage policies section
        coverage_policies_section = ""
        if policy_context.coverage_policies:
            coverage_policies_section = "\n".join([f"  • {p}" for p in policy_context.coverage_policies])
        
        # Medical necessity section
        medical_necessity_section = ""
        if policy_context.medical_necessity_criteria:
            medical_necessity_section = "\n".join([f"  • {c}" for c in policy_context.medical_necessity_criteria])
        
        # Clinical guidelines section
        clinical_guidelines_section = ""
        if policy_context.clinical_guidelines:
            clinical_guidelines_section = "\n".join([f"  • {g}" for g in policy_context.clinical_guidelines])
        
        return {
            "patient_age": str(medical_context.patient_age),
            "patient_gender": medical_context.patient_gender,
            "primary_diagnosis": medical_context.primary_diagnosis,
            "primary_icd10": medical_context.primary_icd10,
            "secondary_diagnoses_section": secondary_diagnoses_section,
            "procedure_name": medical_context.procedure_name,
            "procedure_codes": ", ".join(medical_context.procedure_codes),
            "urgency_level": medical_context.urgency_level,
            "clinical_notes_section": clinical_notes_section,
            "comorbidities_section": comorbidities_section,
            "treatment_history_section": treatment_history_section,
            "payer_name": policy_context.payer_name,
            "coverage_policies_section": coverage_policies_section,
            "medical_necessity_section": medical_necessity_section,
            "clinical_guidelines_section": clinical_guidelines_section
        }
    
    def build_from_authorization_request(
        self,
        template_id: str,
        request: AuthorizationRequest,
        policy_context: PolicyContext
    ) -> Optional[str]:
        """Build prompt directly from authorization request."""
        
        # Extract medical context from request
        medical_context = self._extract_medical_context(request)
        
        return self.build_prompt(template_id, medical_context, policy_context)
    
    def _extract_medical_context(self, request: AuthorizationRequest) -> MedicalContext:
        """Extract medical context from authorization request."""
        
        # Get primary diagnosis
        primary_diagnosis = ""
        primary_icd10 = ""
        if request.diagnosis_codes:
            primary_diag = request.diagnosis_codes[0]
            primary_diagnosis = primary_diag.description
            primary_icd10 = primary_diag.code
        
        # Get secondary diagnoses
        secondary_diagnoses = []
        secondary_icd10s = []
        if len(request.diagnosis_codes) > 1:
            for diag in request.diagnosis_codes[1:]:
                secondary_diagnoses.append(diag.description)
                secondary_icd10s.append(diag.code)
        
        # Get procedure information
        procedure_name = ""
        procedure_codes = []
        if request.procedure_codes:
            procedure_name = request.procedure_codes[0].description
            procedure_codes = [code.code for code in request.procedure_codes]
        
        return MedicalContext(
            patient_age=request.patient_demographics.age,
            patient_gender=request.patient_demographics.gender,
            primary_diagnosis=primary_diagnosis,
            primary_icd10=primary_icd10,
            secondary_diagnoses=secondary_diagnoses,
            secondary_icd10s=secondary_icd10s,
            procedure_name=procedure_name,
            procedure_codes=procedure_codes,
            clinical_notes=request.clinical_notes,
            urgency_level=request.urgency_level.value
        )


# Global instances
prompt_template_manager = PromptTemplateManager()
prompt_builder = PromptBuilder(prompt_template_manager)
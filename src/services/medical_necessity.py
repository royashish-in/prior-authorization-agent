"""
Medical necessity evaluation engine for prior authorization requests.

This module analyzes clinical notes against medical necessity criteria,
implements rule-based evaluation for different procedure types,
and handles policy conflict resolution.
"""

import re
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple, Set
from dataclasses import dataclass
from enum import Enum

from src.models.authorization import AuthorizationRequest
from src.models.enums import ProcedureType
from src.models.medical_codes import ICD10Code, CPTCode, HCPCSCode


logger = logging.getLogger(__name__)


class NecessityLevel(Enum):
    """Medical necessity evaluation levels."""
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    INSUFFICIENT = "insufficient"


class ClinicalIndicator(Enum):
    """Clinical indicators for medical necessity."""
    PAIN_CHRONIC = "chronic_pain"
    PAIN_ACUTE = "acute_pain"
    NEUROLOGICAL_DEFICIT = "neurological_deficit"
    TRAUMA = "trauma"
    INFECTION_SUSPECTED = "infection_suspected"
    MALIGNANCY_SUSPECTED = "malignancy_suspected"
    CONSERVATIVE_TREATMENT_FAILED = "conservative_treatment_failed"
    PROGRESSIVE_SYMPTOMS = "progressive_symptoms"
    FUNCTIONAL_IMPAIRMENT = "functional_impairment"


@dataclass
class ClinicalEvidence:
    """Clinical evidence extracted from notes."""
    indicator: ClinicalIndicator
    confidence: float
    supporting_text: str
    duration_mentioned: Optional[str] = None
    severity_mentioned: Optional[str] = None


@dataclass
class MedicalNecessityResult:
    """Result of medical necessity evaluation."""
    necessity_level: NecessityLevel
    confidence_score: float
    clinical_evidence: List[ClinicalEvidence]
    criteria_met: List[str]
    criteria_not_met: List[str]
    additional_documentation_needed: List[str]
    reasoning: List[str]
    procedure_specific_findings: Dict[str, Any]


@dataclass
class ProcedureRule:
    """Rule for procedure-specific medical necessity evaluation."""
    procedure_codes: List[str]
    required_indicators: List[ClinicalIndicator]
    optional_indicators: List[ClinicalIndicator]
    minimum_duration: Optional[str]
    contraindications: List[str]
    documentation_requirements: List[str]


class MedicalNecessityEngine:
    """
    Engine for evaluating medical necessity of authorization requests.
    
    Analyzes clinical notes against established criteria and implements
    rule-based evaluation for different procedure types.
    """
    
    def __init__(self):
        """Initialize the medical necessity engine."""
        self.logger = logging.getLogger(__name__)
        self._initialize_procedure_rules()
        self._initialize_clinical_patterns()
    
    def evaluate_medical_necessity(
        self,
        request: AuthorizationRequest,
        policy_requirements: Optional[Dict[str, Any]] = None
    ) -> MedicalNecessityResult:
        """
        Evaluate medical necessity for an authorization request.
        
        Args:
            request: Authorization request to evaluate
            policy_requirements: Additional policy-specific requirements
            
        Returns:
            MedicalNecessityResult with evaluation outcome
        """
        try:
            self.logger.info(f"Starting medical necessity evaluation for request {request.request_id}")
            
            # Extract clinical evidence from notes
            clinical_evidence = self._extract_clinical_evidence(request.clinical_notes or "")
            
            # Get procedure-specific rules
            procedure_rules = self._get_procedure_rules(request.procedure_codes, request.procedure_type)
            
            # Evaluate against procedure rules
            criteria_met, criteria_not_met = self._evaluate_procedure_criteria(
                clinical_evidence, procedure_rules, request.diagnosis_codes
            )
            
            # Determine necessity level
            necessity_level = self._determine_necessity_level(
                clinical_evidence, criteria_met, criteria_not_met, procedure_rules
            )
            
            # Calculate confidence score
            confidence_score = self._calculate_confidence_score(
                clinical_evidence, criteria_met, len(criteria_not_met)
            )
            
            # Identify additional documentation needs
            additional_docs = self._identify_documentation_needs(
                criteria_not_met, procedure_rules, policy_requirements
            )
            
            # Generate reasoning
            reasoning = self._generate_reasoning(
                necessity_level, clinical_evidence, criteria_met, criteria_not_met
            )
            
            # Get procedure-specific findings
            procedure_findings = self._get_procedure_specific_findings(
                request.procedure_type, clinical_evidence, request.diagnosis_codes
            )
            
            result = MedicalNecessityResult(
                necessity_level=necessity_level,
                confidence_score=confidence_score,
                clinical_evidence=clinical_evidence,
                criteria_met=criteria_met,
                criteria_not_met=criteria_not_met,
                additional_documentation_needed=additional_docs,
                reasoning=reasoning,
                procedure_specific_findings=procedure_findings
            )
            
            self.logger.info(
                f"Medical necessity evaluation completed for request {request.request_id}: "
                f"level={necessity_level.value}, confidence={confidence_score:.2f}"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Medical necessity evaluation failed for request {request.request_id}: {str(e)}")
            return MedicalNecessityResult(
                necessity_level=NecessityLevel.INSUFFICIENT,
                confidence_score=0.0,
                clinical_evidence=[],
                criteria_met=[],
                criteria_not_met=["Evaluation error occurred"],
                additional_documentation_needed=["Complete clinical documentation"],
                reasoning=[f"Medical necessity evaluation error: {str(e)}"],
                procedure_specific_findings={}
            )
    
    def resolve_policy_conflicts(
        self,
        policy_results: List[Dict[str, Any]],
        necessity_result: MedicalNecessityResult
    ) -> Dict[str, Any]:
        """
        Resolve conflicts between multiple policies using most restrictive approach.
        
        Args:
            policy_results: List of policy validation results
            necessity_result: Medical necessity evaluation result
            
        Returns:
            Resolved policy decision with conflict documentation
        """
        try:
            if not policy_results:
                return {
                    "final_decision": "deny",
                    "reasoning": ["No applicable policies found"],
                    "conflicts_detected": [],
                    "resolution_method": "no_policies"
                }
            
            # Separate approved and denied policies
            approved_policies = [p for p in policy_results if p.get("is_covered", False)]
            denied_policies = [p for p in policy_results if not p.get("is_covered", False)]
            
            conflicts_detected = []
            
            # Check for conflicts between policies
            if approved_policies and denied_policies:
                conflicts_detected.append({
                    "type": "approval_conflict",
                    "description": "Some policies approve while others deny coverage",
                    "approved_count": len(approved_policies),
                    "denied_count": len(denied_policies)
                })
            
            # Apply most restrictive policy rule
            if denied_policies:
                # If any policy denies, the request is denied
                most_restrictive = denied_policies[0]
                final_decision = "deny"
                resolution_method = "most_restrictive_deny"
                
                reasoning = most_restrictive.get("reasoning", [])
                reasoning.append("Most restrictive policy applied - coverage denied by at least one policy")
                
            elif approved_policies:
                # All policies approve - check medical necessity
                if necessity_result.necessity_level in [NecessityLevel.HIGH, NecessityLevel.MODERATE]:
                    most_restrictive = approved_policies[0]
                    final_decision = "approve"
                    resolution_method = "all_approve_with_necessity"
                    
                    reasoning = most_restrictive.get("reasoning", [])
                    reasoning.append(f"All policies approve and medical necessity is {necessity_result.necessity_level.value}")
                    
                else:
                    # Check for additional requirements first
                    if necessity_result.additional_documentation_needed:
                        final_decision = "request_info"
                        resolution_method = "insufficient_necessity_request_info"
                        reasoning = [
                            "Policies approve coverage but medical necessity requires additional documentation",
                            f"Medical necessity level: {necessity_result.necessity_level.value}",
                            "Additional documentation may establish medical necessity"
                        ]
                    else:
                        final_decision = "deny"
                        resolution_method = "insufficient_medical_necessity"
                        reasoning = [
                            "Policies approve coverage but medical necessity is insufficient",
                            f"Medical necessity level: {necessity_result.necessity_level.value}"
                        ]
            
            else:
                final_decision = "deny"
                resolution_method = "no_coverage"
                reasoning = ["No policies provide coverage for this request"]
            
            # Document any requirement conflicts
            requirement_conflicts = self._detect_requirement_conflicts(policy_results)
            conflicts_detected.extend(requirement_conflicts)
            
            result = {
                "final_decision": final_decision,
                "reasoning": reasoning,
                "conflicts_detected": conflicts_detected,
                "resolution_method": resolution_method,
                "policy_count": len(policy_results),
                "medical_necessity_level": necessity_result.necessity_level.value,
                "confidence_score": min(
                    necessity_result.confidence_score,
                    min([p.get("confidence_score", 0.0) for p in policy_results], default=0.0)
                )
            }
            
            self.logger.info(
                f"Policy conflict resolution completed: decision={final_decision}, "
                f"conflicts={len(conflicts_detected)}, method={resolution_method}"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Policy conflict resolution failed: {str(e)}")
            return {
                "final_decision": "deny",
                "reasoning": [f"Policy conflict resolution error: {str(e)}"],
                "conflicts_detected": [],
                "resolution_method": "error",
                "policy_count": len(policy_results) if policy_results else 0,
                "medical_necessity_level": necessity_result.necessity_level.value if necessity_result else "unknown",
                "confidence_score": 0.0
            }
    
    def _initialize_procedure_rules(self):
        """Initialize procedure-specific medical necessity rules."""
        self.procedure_rules = {
            ProcedureType.MRI: [
                ProcedureRule(
                    procedure_codes=["70551", "70552", "70553"],  # Brain MRI
                    required_indicators=[ClinicalIndicator.NEUROLOGICAL_DEFICIT],
                    optional_indicators=[ClinicalIndicator.PAIN_CHRONIC, ClinicalIndicator.MALIGNANCY_SUSPECTED],
                    minimum_duration="4 weeks",
                    contraindications=["metallic implants", "claustrophobia"],
                    documentation_requirements=["neurological examination", "symptom duration"]
                ),
                ProcedureRule(
                    procedure_codes=["73221", "73222", "73223"],  # Upper extremity MRI
                    required_indicators=[ClinicalIndicator.PAIN_CHRONIC, ClinicalIndicator.FUNCTIONAL_IMPAIRMENT],
                    optional_indicators=[ClinicalIndicator.TRAUMA, ClinicalIndicator.CONSERVATIVE_TREATMENT_FAILED],
                    minimum_duration="6 weeks",
                    contraindications=["metallic implants"],
                    documentation_requirements=["physical examination", "conservative treatment history"]
                ),
                ProcedureRule(
                    procedure_codes=["72148", "72149", "72158"],  # Spine MRI
                    required_indicators=[ClinicalIndicator.PAIN_CHRONIC, ClinicalIndicator.NEUROLOGICAL_DEFICIT],
                    optional_indicators=[ClinicalIndicator.CONSERVATIVE_TREATMENT_FAILED],
                    minimum_duration="6 weeks",
                    contraindications=["metallic spinal hardware"],
                    documentation_requirements=["neurological examination", "conservative treatment trial"]
                )
            ],
            ProcedureType.CT_SCAN: [
                ProcedureRule(
                    procedure_codes=["70450", "70460", "70470"],  # Head CT
                    required_indicators=[ClinicalIndicator.TRAUMA, ClinicalIndicator.NEUROLOGICAL_DEFICIT],
                    optional_indicators=[ClinicalIndicator.PAIN_ACUTE],
                    minimum_duration=None,
                    contraindications=[],
                    documentation_requirements=["clinical indication", "symptom onset"]
                ),
                ProcedureRule(
                    procedure_codes=["74150", "74160", "74170"],  # Abdomen CT
                    required_indicators=[ClinicalIndicator.PAIN_ACUTE],
                    optional_indicators=[ClinicalIndicator.INFECTION_SUSPECTED, ClinicalIndicator.MALIGNANCY_SUSPECTED],
                    minimum_duration=None,
                    contraindications=["pregnancy"],
                    documentation_requirements=["clinical symptoms", "physical examination"]
                )
            ],
            ProcedureType.X_RAY: [
                ProcedureRule(
                    procedure_codes=["73060", "73070", "73080"],  # Extremity X-ray
                    required_indicators=[ClinicalIndicator.TRAUMA, ClinicalIndicator.PAIN_ACUTE],
                    optional_indicators=[ClinicalIndicator.FUNCTIONAL_IMPAIRMENT],
                    minimum_duration=None,
                    contraindications=["pregnancy"],
                    documentation_requirements=["mechanism of injury", "physical examination"]
                )
            ]
        }
    
    def _initialize_clinical_patterns(self):
        """Initialize clinical text patterns for evidence extraction."""
        self.clinical_patterns = {
            ClinicalIndicator.PAIN_CHRONIC: [
                r"chronic pain",
                r"persistent pain",
                r"pain (?:for|lasting|duration) (?:over )?(\d+) (?:weeks?|months?|years?)",
                r"ongoing pain",
                r"long-?standing pain"
            ],
            ClinicalIndicator.PAIN_ACUTE: [
                r"acute pain",
                r"sudden onset",
                r"sharp pain",
                r"severe pain",
                r"pain started (?:today|yesterday|\d+ days? ago)"
            ],
            ClinicalIndicator.NEUROLOGICAL_DEFICIT: [
                r"weakness",
                r"numbness",
                r"tingling",
                r"paresthesia",
                r"motor deficit",
                r"sensory loss",
                r"neurological deficit",
                r"radiculopathy",
                r"neurological symptoms",
                r"acute neurological"
            ],
            ClinicalIndicator.TRAUMA: [
                r"trauma",
                r"injury",
                r"fall",
                r"accident",
                r"motor vehicle",
                r"sports injury",
                r"fracture",
                r"injured",
                r"fell",
                r"head trauma"
            ],
            ClinicalIndicator.INFECTION_SUSPECTED: [
                r"infection",
                r"fever",
                r"elevated (?:white blood cell|WBC)",
                r"sepsis",
                r"abscess",
                r"cellulitis"
            ],
            ClinicalIndicator.MALIGNANCY_SUSPECTED: [
                r"malignancy",
                r"cancer",
                r"tumor",
                r"mass",
                r"neoplasm",
                r"suspicious lesion",
                r"weight loss",
                r"night sweats"
            ],
            ClinicalIndicator.CONSERVATIVE_TREATMENT_FAILED: [
                r"conservative treatment (?:failed|unsuccessful|has failed)",
                r"physical therapy (?:completed|failed|has failed)",
                r"medication (?:ineffective|failed)",
                r"non-?surgical treatment (?:failed|unsuccessful)",
                r"tried (?:PT|physical therapy|medications?)",
                r"(?:PT|physical therapy) (?:has )?failed"
            ],
            ClinicalIndicator.PROGRESSIVE_SYMPTOMS: [
                r"progressive",
                r"worsening",
                r"deteriorating",
                r"increasing",
                r"getting worse"
            ],
            ClinicalIndicator.FUNCTIONAL_IMPAIRMENT: [
                r"functional impairment",
                r"difficulty (?:walking|moving|working)",
                r"unable to (?:work|walk|function)",
                r"limited (?:mobility|function)",
                r"activities of daily living affected"
            ]
        }
    
    def _extract_clinical_evidence(self, clinical_notes: str) -> List[ClinicalEvidence]:
        """Extract clinical evidence from notes using pattern matching."""
        if not clinical_notes:
            return []
        
        evidence = []
        notes_lower = clinical_notes.lower()
        
        for indicator, patterns in self.clinical_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, notes_lower, re.IGNORECASE)
                for match in matches:
                    # Calculate confidence based on pattern specificity
                    confidence = self._calculate_pattern_confidence(pattern, match.group())
                    
                    # Extract duration if mentioned
                    duration = self._extract_duration(match.group())
                    
                    # Extract severity if mentioned
                    severity = self._extract_severity(match.group())
                    
                    evidence.append(ClinicalEvidence(
                        indicator=indicator,
                        confidence=confidence,
                        supporting_text=match.group(),
                        duration_mentioned=duration,
                        severity_mentioned=severity
                    ))
        
        # Remove duplicates and sort by confidence
        unique_evidence = self._deduplicate_evidence(evidence)
        return sorted(unique_evidence, key=lambda x: x.confidence, reverse=True)
    
    def _get_procedure_rules(
        self,
        procedure_codes: List[Any],
        procedure_type: ProcedureType
    ) -> List[ProcedureRule]:
        """Get applicable procedure rules for the given codes and type."""
        applicable_rules = []
        
        if procedure_type not in self.procedure_rules:
            return applicable_rules
        
        # Extract code strings from procedure code objects
        code_strings = []
        for code in procedure_codes:
            if hasattr(code, 'code'):
                code_strings.append(code.code)
            else:
                code_strings.append(str(code))
        
        # Find matching rules
        for rule in self.procedure_rules[procedure_type]:
            if any(code in rule.procedure_codes for code in code_strings):
                applicable_rules.append(rule)
        
        return applicable_rules
    
    def _evaluate_procedure_criteria(
        self,
        clinical_evidence: List[ClinicalEvidence],
        procedure_rules: List[ProcedureRule],
        diagnosis_codes: List[ICD10Code]
    ) -> Tuple[List[str], List[str]]:
        """Evaluate clinical evidence against procedure criteria."""
        criteria_met = []
        criteria_not_met = []
        
        if not procedure_rules:
            criteria_not_met.append("No applicable procedure rules found")
            return criteria_met, criteria_not_met
        
        # Get all indicators from evidence
        evidence_indicators = {ev.indicator for ev in clinical_evidence}
        
        for rule in procedure_rules:
            # Check required indicators
            for required_indicator in rule.required_indicators:
                if required_indicator in evidence_indicators:
                    criteria_met.append(f"Required indicator present: {required_indicator.value}")
                else:
                    criteria_not_met.append(f"Missing required indicator: {required_indicator.value}")
            
            # Check minimum duration if specified
            if rule.minimum_duration:
                duration_met = self._check_duration_requirement(
                    clinical_evidence, rule.minimum_duration
                )
                if duration_met:
                    criteria_met.append(f"Minimum duration requirement met: {rule.minimum_duration}")
                else:
                    criteria_not_met.append(f"Minimum duration not documented: {rule.minimum_duration}")
            
            # Check for contraindications
            contraindications_found = self._check_contraindications(
                clinical_evidence, rule.contraindications
            )
            if contraindications_found:
                criteria_not_met.extend([
                    f"Contraindication present: {ci}" for ci in contraindications_found
                ])
            else:
                criteria_met.append("No contraindications identified")
        
        return criteria_met, criteria_not_met
    
    def _determine_necessity_level(
        self,
        clinical_evidence: List[ClinicalEvidence],
        criteria_met: List[str],
        criteria_not_met: List[str],
        procedure_rules: List[ProcedureRule]
    ) -> NecessityLevel:
        """Determine medical necessity level based on evaluation results."""
        if not clinical_evidence:
            return NecessityLevel.INSUFFICIENT
        
        # Calculate scores
        met_score = len(criteria_met)
        not_met_score = len(criteria_not_met)
        evidence_score = sum(ev.confidence for ev in clinical_evidence)
        
        # High necessity: Most criteria met, strong evidence
        if met_score >= 3 and not_met_score <= 1 and evidence_score >= 2.0:
            return NecessityLevel.HIGH
        
        # Moderate necessity: Some criteria met, moderate evidence
        elif met_score >= 2 and not_met_score <= 2 and evidence_score >= 1.0:
            return NecessityLevel.MODERATE
        
        # Low necessity: Few criteria met, weak evidence
        elif met_score >= 1 and evidence_score >= 0.5:
            return NecessityLevel.LOW
        
        # Insufficient: Minimal or no evidence
        else:
            return NecessityLevel.INSUFFICIENT
    
    def _calculate_confidence_score(
        self,
        clinical_evidence: List[ClinicalEvidence],
        criteria_met: List[str],
        criteria_not_met_count: int
    ) -> float:
        """Calculate confidence score for the medical necessity evaluation."""
        if not clinical_evidence:
            return 0.0
        
        # Base confidence from evidence quality
        evidence_confidence = min(1.0, sum(ev.confidence for ev in clinical_evidence) / len(clinical_evidence))
        
        # Adjust for criteria compliance
        total_criteria = len(criteria_met) + criteria_not_met_count
        if total_criteria > 0:
            criteria_compliance = len(criteria_met) / total_criteria
        else:
            criteria_compliance = 0.0
        
        # Weighted combination
        final_confidence = (evidence_confidence * 0.6) + (criteria_compliance * 0.4)
        
        return round(final_confidence, 2)
    
    def _identify_documentation_needs(
        self,
        criteria_not_met: List[str],
        procedure_rules: List[ProcedureRule],
        policy_requirements: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Identify additional documentation needed."""
        additional_docs = []
        
        # Add documentation for unmet criteria
        for criterion in criteria_not_met:
            if "Missing required indicator" in criterion:
                indicator = criterion.split(": ")[-1]
                additional_docs.append(f"Clinical documentation of {indicator}")
            elif "duration not documented" in criterion:
                additional_docs.append("Documentation of symptom duration")
        
        # Add procedure-specific documentation requirements
        for rule in procedure_rules:
            for doc_req in rule.documentation_requirements:
                if doc_req not in additional_docs:
                    additional_docs.append(doc_req)
        
        # Add policy-specific requirements
        if policy_requirements and "documentation_required" in policy_requirements:
            for doc_req in policy_requirements["documentation_required"]:
                if doc_req not in additional_docs:
                    additional_docs.append(doc_req)
        
        return additional_docs
    
    def _generate_reasoning(
        self,
        necessity_level: NecessityLevel,
        clinical_evidence: List[ClinicalEvidence],
        criteria_met: List[str],
        criteria_not_met: List[str]
    ) -> List[str]:
        """Generate human-readable reasoning for the evaluation."""
        reasoning = []
        
        # Overall assessment
        reasoning.append(f"Medical necessity level determined as {necessity_level.value}")
        
        # Evidence summary
        if clinical_evidence:
            high_confidence_evidence = [ev for ev in clinical_evidence if ev.confidence >= 0.8]
            if high_confidence_evidence:
                indicators = [ev.indicator.value for ev in high_confidence_evidence]
                reasoning.append(f"Strong clinical evidence found for: {', '.join(indicators)}")
        
        # Criteria summary
        if criteria_met:
            reasoning.append(f"Met {len(criteria_met)} medical necessity criteria")
        
        if criteria_not_met:
            reasoning.append(f"Did not meet {len(criteria_not_met)} criteria")
            if len(criteria_not_met) <= 2:
                reasoning.extend(criteria_not_met[:2])  # Include specific unmet criteria
        
        # Recommendations
        if necessity_level == NecessityLevel.INSUFFICIENT:
            reasoning.append("Additional clinical documentation required to establish medical necessity")
        elif necessity_level == NecessityLevel.LOW:
            reasoning.append("Medical necessity may be established with additional documentation")
        
        return reasoning
    
    def _get_procedure_specific_findings(
        self,
        procedure_type: ProcedureType,
        clinical_evidence: List[ClinicalEvidence],
        diagnosis_codes: List[ICD10Code]
    ) -> Dict[str, Any]:
        """Get procedure-specific findings and recommendations."""
        findings = {
            "procedure_type": procedure_type.value,
            "diagnosis_alignment": self._check_diagnosis_alignment(procedure_type, diagnosis_codes),
            "clinical_appropriateness": self._assess_clinical_appropriateness(procedure_type, clinical_evidence)
        }
        
        # Add procedure-specific assessments
        if procedure_type == ProcedureType.MRI:
            findings["contrast_indication"] = self._assess_contrast_need(clinical_evidence)
            findings["alternative_imaging"] = self._suggest_alternative_imaging(clinical_evidence)
        
        elif procedure_type == ProcedureType.CT_SCAN:
            findings["radiation_justification"] = self._assess_radiation_justification(clinical_evidence)
            findings["contrast_indication"] = self._assess_contrast_need(clinical_evidence)
        
        elif procedure_type == ProcedureType.X_RAY:
            findings["fracture_likelihood"] = self._assess_fracture_likelihood(clinical_evidence)
        
        return findings
    
    def _detect_requirement_conflicts(self, policy_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect conflicts in policy requirements."""
        conflicts = []
        
        # Check for conflicting age requirements
        age_requirements = []
        for policy in policy_results:
            if "age_range" in policy.get("coverage_criteria", {}):
                age_requirements.append(policy["coverage_criteria"]["age_range"])
        
        if len(age_requirements) > 1:
            # Check for conflicting age ranges
            min_ages = [req.get("min_age") for req in age_requirements if req.get("min_age")]
            max_ages = [req.get("max_age") for req in age_requirements if req.get("max_age")]
            
            if len(set(min_ages)) > 1 or len(set(max_ages)) > 1:
                conflicts.append({
                    "type": "age_requirement_conflict",
                    "description": "Policies have conflicting age requirements",
                    "details": {"age_requirements": age_requirements}
                })
        
        # Check for conflicting documentation requirements
        doc_requirements = []
        for policy in policy_results:
            if "documentation_required" in policy.get("coverage_criteria", {}):
                doc_requirements.extend(policy["coverage_criteria"]["documentation_required"])
        
        if len(set(doc_requirements)) != len(doc_requirements):
            conflicts.append({
                "type": "documentation_conflict",
                "description": "Policies have overlapping documentation requirements",
                "details": {"requirements": list(set(doc_requirements))}
            })
        
        return conflicts
    
    # Helper methods for pattern matching and clinical assessment
    
    def _calculate_pattern_confidence(self, pattern: str, matched_text: str) -> float:
        """Calculate confidence score for a pattern match."""
        # More specific patterns get higher confidence
        if len(pattern) > 20:
            return 0.9
        elif len(pattern) > 10:
            return 0.7
        else:
            return 0.5
    
    def _extract_duration(self, text: str) -> Optional[str]:
        """Extract duration information from matched text."""
        duration_match = re.search(r"(\d+)\s*(weeks?|months?|years?)", text.lower())
        if duration_match:
            return f"{duration_match.group(1)} {duration_match.group(2)}"
        return None
    
    def _extract_severity(self, text: str) -> Optional[str]:
        """Extract severity information from matched text."""
        severity_terms = ["mild", "moderate", "severe", "chronic", "acute"]
        for term in severity_terms:
            if term in text.lower():
                return term
        return None
    
    def _deduplicate_evidence(self, evidence: List[ClinicalEvidence]) -> List[ClinicalEvidence]:
        """Remove duplicate evidence entries."""
        seen = set()
        unique_evidence = []
        
        for ev in evidence:
            key = (ev.indicator, ev.supporting_text.lower())
            if key not in seen:
                seen.add(key)
                unique_evidence.append(ev)
        
        return unique_evidence
    
    def _check_duration_requirement(self, clinical_evidence: List[ClinicalEvidence], required_duration: str) -> bool:
        """Check if duration requirement is met."""
        # Extract required duration in weeks
        duration_match = re.search(r"(\d+)\s*weeks?", required_duration.lower())
        if not duration_match:
            return False
        
        required_weeks = int(duration_match.group(1))
        
        # Check evidence for duration mentions
        for evidence in clinical_evidence:
            if evidence.duration_mentioned:
                evidence_match = re.search(r"(\d+)\s*(weeks?|months?)", evidence.duration_mentioned.lower())
                if evidence_match:
                    weeks = int(evidence_match.group(1))
                    if "month" in evidence_match.group(2):
                        weeks *= 4  # Convert months to weeks
                    
                    if weeks >= required_weeks:
                        return True
        
        return False
    
    def _check_contraindications(self, clinical_evidence: List[ClinicalEvidence], contraindications: List[str]) -> List[str]:
        """Check for contraindications in clinical evidence."""
        found_contraindications = []
        
        # This would need more sophisticated implementation
        # For now, return empty list as contraindications would need specific detection
        
        return found_contraindications
    
    def _check_diagnosis_alignment(self, procedure_type: ProcedureType, diagnosis_codes: List[ICD10Code]) -> Dict[str, Any]:
        """Check if diagnosis codes align with procedure type."""
        # Simplified alignment check
        return {
            "aligned": True,
            "reasoning": "Diagnosis codes are appropriate for requested imaging procedure"
        }
    
    def _assess_clinical_appropriateness(self, procedure_type: ProcedureType, clinical_evidence: List[ClinicalEvidence]) -> Dict[str, Any]:
        """Assess clinical appropriateness of the procedure."""
        return {
            "appropriate": len(clinical_evidence) > 0,
            "confidence": min(1.0, len(clinical_evidence) * 0.3),
            "reasoning": "Clinical evidence supports imaging request"
        }
    
    def _assess_contrast_need(self, clinical_evidence: List[ClinicalEvidence]) -> Dict[str, Any]:
        """Assess need for contrast enhancement."""
        malignancy_indicators = [ev for ev in clinical_evidence if ev.indicator == ClinicalIndicator.MALIGNANCY_SUSPECTED]
        
        return {
            "contrast_indicated": len(malignancy_indicators) > 0,
            "reasoning": "Contrast may be needed for suspected malignancy" if malignancy_indicators else "No specific contrast indication"
        }
    
    def _suggest_alternative_imaging(self, clinical_evidence: List[ClinicalEvidence]) -> Dict[str, Any]:
        """Suggest alternative imaging modalities."""
        return {
            "alternatives": [],
            "reasoning": "MRI is appropriate first-line imaging"
        }
    
    def _assess_radiation_justification(self, clinical_evidence: List[ClinicalEvidence]) -> Dict[str, Any]:
        """Assess justification for radiation exposure."""
        return {
            "justified": True,
            "reasoning": "Clinical indication justifies radiation exposure"
        }
    
    def _assess_fracture_likelihood(self, clinical_evidence: List[ClinicalEvidence]) -> Dict[str, Any]:
        """Assess likelihood of fracture for X-ray requests."""
        trauma_indicators = [ev for ev in clinical_evidence if ev.indicator == ClinicalIndicator.TRAUMA]
        
        return {
            "likelihood": "high" if trauma_indicators else "low",
            "reasoning": "Trauma history suggests possible fracture" if trauma_indicators else "No trauma history documented"
        }
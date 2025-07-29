"""
Policy validation service for coverage policies and CMS guidelines.

This module handles policy storage, retrieval, validation logic,
and CMS NCD/LCD compliance checking.
"""

import json
import logging
from datetime import date, datetime
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from src.core.datetime_utils import utcnow, utcnow_iso

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from src.database.models import CoveragePolicyDB
from src.models.authorization import AuthorizationRequest
from src.models.enums import DecisionStatus
from src.services.medical_necessity import MedicalNecessityEngine
from src.services.external_services import ExternalServiceIntegrator


logger = logging.getLogger(__name__)


class PolicyType(Enum):
    """Policy type enumeration."""
    NCD = "NCD"  # CMS National Coverage Determination
    LCD = "LCD"  # CMS Local Coverage Determination
    PAYER = "PAYER"  # Payer-specific policy


@dataclass
class PolicyValidationResult:
    """Result of policy validation."""
    is_covered: bool
    policy_id: str
    policy_type: PolicyType
    reasoning: List[str]
    confidence_score: float
    policy_references: List[str]
    additional_requirements: List[str] = None
    
    def __post_init__(self):
        if self.additional_requirements is None:
            self.additional_requirements = []


@dataclass
class CMSComplianceResult:
    """Result of CMS compliance checking."""
    is_compliant: bool
    ncd_policies: List[Dict[str, Any]]
    lcd_policies: List[Dict[str, Any]]
    compliance_issues: List[str]
    recommendations: List[str]


class PolicyValidationService:
    """
    Service for validating authorization requests against coverage policies.
    
    Handles policy storage, retrieval, and validation logic including
    CMS NCD/LCD compliance checking.
    """
    
    def __init__(self, db_session: Session):
        """Initialize the policy validation service."""
        self.db_session = db_session
        self.logger = logging.getLogger(__name__)
        self.medical_necessity_engine = MedicalNecessityEngine()
        self.external_services = ExternalServiceIntegrator()
    
    def validate_coverage_policy(
        self, 
        request: AuthorizationRequest,
        payer_id: str
    ) -> PolicyValidationResult:
        """
        Validate authorization request against coverage policies.
        
        Args:
            request: Authorization request to validate
            payer_id: Payer identifier for policy lookup
            
        Returns:
            PolicyValidationResult with validation outcome
        """
        try:
            # Get applicable policies for the request
            policies = self._get_applicable_policies(
                payer_id=payer_id,
                procedure_codes=[code.code for code in request.procedure_codes],
                diagnosis_codes=[code.code for code in request.diagnosis_codes]
            )
            
            if not policies:
                return PolicyValidationResult(
                    is_covered=False,
                    policy_id="",
                    policy_type=PolicyType.PAYER,
                    reasoning=["No applicable coverage policies found"],
                    confidence_score=1.0,
                    policy_references=[]
                )
            
            # Validate against each applicable policy
            validation_results = []
            for policy in policies:
                result = self._validate_against_policy(request, policy)
                validation_results.append(result)
            
            # Apply most restrictive policy rule
            final_result = self._apply_most_restrictive_policy(validation_results)
            
            self.logger.info(
                f"Policy validation completed for request {request.request_id}: "
                f"covered={final_result.is_covered}, confidence={final_result.confidence_score}"
            )
            
            return final_result
            
        except Exception as e:
            # Log technical error for debugging but provide user-friendly response
            self.logger.error(f"Policy validation technical error for request {request.request_id}: {str(e)}")
            
            # Return a user-friendly policy validation result
            return PolicyValidationResult(
                is_covered=False,
                policy_id="POLICY_MANUAL_REVIEW",
                policy_type=PolicyType.PAYER,
                reasoning=[
                    "Request requires manual policy review",
                    "Unable to automatically verify coverage criteria",
                    "Please ensure all required documentation is complete"
                ],
                confidence_score=0.3,
                policy_references=["MANUAL_REVIEW_REQUIRED"],
                additional_requirements=[
                    "Verify all medical codes are current and accurate",
                    "Include complete clinical documentation",
                    "Ensure prior authorization requirements are met"
                ]
            )
    
    async def check_cms_compliance(
        self,
        request: AuthorizationRequest
    ) -> CMSComplianceResult:
        """
        Check CMS NCD/LCD compliance using external CMS guidelines API.
        
        Args:
            request: Authorization request to check
            
        Returns:
            CMSComplianceResult with compliance status
        """
        try:
            procedure_codes = [code.code for code in request.procedure_codes]
            diagnosis_codes = [code.code for code in request.diagnosis_codes]
            
            # Use external CMS guidelines service
            try:
                cms_response = await self.external_services.get_cms_guidelines(
                    procedure_codes=procedure_codes,
                    diagnosis_codes=diagnosis_codes,
                    use_cache=True,
                    fallback_on_error=True
                )
                
                self.logger.info(
                    f"CMS compliance check completed via external service for request {request.request_id}: "
                    f"compliant={cms_response.is_compliant}"
                )
                
                return CMSComplianceResult(
                    is_compliant=cms_response.is_compliant,
                    ncd_policies=cms_response.ncd_policies,
                    lcd_policies=cms_response.lcd_policies,
                    compliance_issues=cms_response.compliance_issues,
                    recommendations=cms_response.recommendations
                )
                
            except Exception as external_error:
                self.logger.warning(
                    f"External CMS service failed, falling back to local policies: {str(external_error)}"
                )
                
                # Fallback to local CMS policy checking
                return await self._check_cms_compliance_local(request)
            
        except Exception as e:
            self.logger.error(f"CMS compliance check failed for request {request.request_id}: {str(e)}")
            return CMSComplianceResult(
                is_compliant=False,
                ncd_policies=[],
                lcd_policies=[],
                compliance_issues=[f"CMS compliance check error: {str(e)}"],
                recommendations=[]
            )
    
    async def _check_cms_compliance_local(self, request: AuthorizationRequest) -> CMSComplianceResult:
        """
        Fallback method for local CMS compliance checking.
        
        Args:
            request: Authorization request to check
            
        Returns:
            CMSComplianceResult with compliance status
        """
        procedure_codes = [code.code for code in request.procedure_codes]
        diagnosis_codes = [code.code for code in request.diagnosis_codes]
        
        # Get CMS NCD policies from local database
        ncd_policies = self._get_cms_policies(
            policy_type=PolicyType.NCD,
            procedure_codes=procedure_codes,
            diagnosis_codes=diagnosis_codes
        )
        
        # Get CMS LCD policies from local database
        lcd_policies = self._get_cms_policies(
            policy_type=PolicyType.LCD,
            procedure_codes=procedure_codes,
            diagnosis_codes=diagnosis_codes
        )
        
        # Check compliance
        compliance_issues = []
        recommendations = []
        
        # Validate against NCD policies
        for policy in ncd_policies:
            issues, recs = self._check_policy_compliance(request, policy)
            compliance_issues.extend(issues)
            recommendations.extend(recs)
        
        # Validate against LCD policies
        for policy in lcd_policies:
            issues, recs = self._check_policy_compliance(request, policy)
            compliance_issues.extend(issues)
            recommendations.extend(recs)
        
        is_compliant = len(compliance_issues) == 0
        
        return CMSComplianceResult(
            is_compliant=is_compliant,
            ncd_policies=[self._policy_to_dict(p) for p in ncd_policies],
            lcd_policies=[self._policy_to_dict(p) for p in lcd_policies],
            compliance_issues=compliance_issues,
            recommendations=recommendations
        )
    
    def store_policy(
        self,
        payer_id: str,
        procedure_code: str,
        policy_data: Dict[str, Any],
        policy_type: PolicyType = PolicyType.PAYER,
        created_by: str = "system"
    ) -> str:
        """
        Store a new coverage policy.
        
        Args:
            payer_id: Payer identifier
            procedure_code: Procedure code this policy covers
            policy_data: Policy configuration data
            policy_type: Type of policy (NCD, LCD, PAYER)
            created_by: User who created the policy
            
        Returns:
            Policy ID of the stored policy
        """
        try:
            # Generate policy ID
            policy_id = f"pol_{utcnow().strftime('%Y%m%d_%H%M%S')}_{payer_id}_{procedure_code}"
            
            # Create policy record
            policy = CoveragePolicyDB(
                policy_id=policy_id,
                payer_id=payer_id,
                procedure_code=procedure_code,
                diagnosis_codes=policy_data.get('diagnosis_codes', []),
                coverage_criteria=policy_data.get('coverage_criteria', {}),
                policy_type=policy_type.value,
                policy_name=policy_data.get('policy_name', f"Policy for {procedure_code}"),
                policy_version=policy_data.get('policy_version', "1.0"),
                effective_date=policy_data.get('effective_date', date.today()),
                expiration_date=policy_data.get('expiration_date'),
                is_active=policy_data.get('is_active', True),
                created_by=created_by,
                updated_by=created_by
            )
            
            self.db_session.add(policy)
            self.db_session.commit()
            
            self.logger.info(f"Policy stored successfully: {policy_id}")
            return policy_id
            
        except Exception as e:
            self.db_session.rollback()
            self.logger.error(f"Failed to store policy: {str(e)}")
            raise
    
    def get_policy_by_id(self, policy_id: str) -> Optional[CoveragePolicyDB]:
        """
        Retrieve a policy by its ID.
        
        Args:
            policy_id: Policy identifier
            
        Returns:
            Policy record or None if not found
        """
        return self.db_session.query(CoveragePolicyDB).filter(
            CoveragePolicyDB.policy_id == policy_id
        ).first()
    
    def get_policies_for_payer(
        self,
        payer_id: str,
        active_only: bool = True
    ) -> List[CoveragePolicyDB]:
        """
        Get all policies for a specific payer.
        
        Args:
            payer_id: Payer identifier
            active_only: Whether to return only active policies
            
        Returns:
            List of policy records
        """
        query = self.db_session.query(CoveragePolicyDB).filter(
            CoveragePolicyDB.payer_id == payer_id
        )
        
        if active_only:
            query = query.filter(
                and_(
                    CoveragePolicyDB.is_active == True,
                    CoveragePolicyDB.effective_date <= date.today(),
                    or_(
                        CoveragePolicyDB.expiration_date.is_(None),
                        CoveragePolicyDB.expiration_date >= date.today()
                    )
                )
            )
        
        return query.all()
    
    async def validate_with_medical_necessity(
        self,
        request: AuthorizationRequest,
        payer_id: str
    ) -> Dict[str, Any]:
        """
        Comprehensive validation including policy validation and medical necessity evaluation.
        
        Args:
            request: Authorization request to validate
            payer_id: Payer identifier for policy lookup
            
        Returns:
            Combined validation result with policy and medical necessity evaluation
        """
        try:
            # Perform policy validation
            policy_result = self.validate_coverage_policy(request, payer_id)
            
            # Perform CMS compliance check
            cms_result = await self.check_cms_compliance(request)
            
            # Perform medical necessity evaluation
            necessity_result = self.medical_necessity_engine.evaluate_medical_necessity(
                request, 
                policy_requirements=policy_result.additional_requirements
            )
            
            # Combine policy results for conflict resolution
            policy_results = [
                {
                    "is_covered": policy_result.is_covered,
                    "reasoning": policy_result.reasoning,
                    "confidence_score": policy_result.confidence_score,
                    "policy_id": policy_result.policy_id,
                    "policy_type": policy_result.policy_type.value,
                    "coverage_criteria": {},  # Would be populated from actual policy
                    "additional_requirements": policy_result.additional_requirements
                }
            ]
            
            # Add CMS compliance as additional policy results if applicable
            if not cms_result.is_compliant:
                policy_results.append({
                    "is_covered": False,
                    "reasoning": cms_result.compliance_issues,
                    "confidence_score": 0.8,
                    "policy_id": "cms_compliance",
                    "policy_type": "CMS",
                    "coverage_criteria": {},
                    "additional_requirements": cms_result.recommendations
                })
            
            # Resolve policy conflicts with medical necessity
            final_decision = self.medical_necessity_engine.resolve_policy_conflicts(
                policy_results, necessity_result
            )
            
            # Compile comprehensive result
            comprehensive_result = {
                "request_id": request.request_id,
                "policy_validation": {
                    "is_covered": policy_result.is_covered,
                    "policy_id": policy_result.policy_id,
                    "policy_type": policy_result.policy_type.value,
                    "reasoning": policy_result.reasoning,
                    "confidence_score": policy_result.confidence_score,
                    "policy_references": policy_result.policy_references,
                    "additional_requirements": policy_result.additional_requirements
                },
                "cms_compliance": {
                    "is_compliant": cms_result.is_compliant,
                    "ncd_policies": cms_result.ncd_policies,
                    "lcd_policies": cms_result.lcd_policies,
                    "compliance_issues": cms_result.compliance_issues,
                    "recommendations": cms_result.recommendations
                },
                "medical_necessity": {
                    "necessity_level": necessity_result.necessity_level.value,
                    "confidence_score": necessity_result.confidence_score,
                    "criteria_met": necessity_result.criteria_met,
                    "criteria_not_met": necessity_result.criteria_not_met,
                    "clinical_evidence_count": len(necessity_result.clinical_evidence),
                    "additional_documentation_needed": necessity_result.additional_documentation_needed,
                    "reasoning": necessity_result.reasoning,
                    "procedure_specific_findings": necessity_result.procedure_specific_findings
                },
                "final_decision": final_decision,
                "validation_timestamp": utcnow_iso()
            }
            
            self.logger.info(
                f"Comprehensive validation completed for request {request.request_id}: "
                f"final_decision={final_decision['final_decision']}, "
                f"necessity_level={necessity_result.necessity_level.value}, "
                f"policy_covered={policy_result.is_covered}"
            )
            
            return comprehensive_result
            
        except Exception as e:
            self.logger.error(f"Comprehensive validation failed for request {request.request_id}: {str(e)}")
            return {
                "request_id": request.request_id,
                "error": f"Validation error: {str(e)}",
                "final_decision": {
                    "final_decision": "deny",
                    "reasoning": [f"Validation system error: {str(e)}"],
                    "resolution_method": "system_error",
                    "confidence_score": 0.0
                },
                "validation_timestamp": utcnow_iso()
            }
    
    def _get_applicable_policies(
        self,
        payer_id: str,
        procedure_codes: List[str],
        diagnosis_codes: List[str]
    ) -> List[CoveragePolicyDB]:
        """Get policies applicable to the given codes."""
        # Query for policies matching procedure codes
        query = self.db_session.query(CoveragePolicyDB).filter(
            and_(
                CoveragePolicyDB.payer_id == payer_id,
                CoveragePolicyDB.procedure_code.in_(procedure_codes),
                CoveragePolicyDB.is_active == True,
                CoveragePolicyDB.effective_date <= date.today(),
                or_(
                    CoveragePolicyDB.expiration_date.is_(None),
                    CoveragePolicyDB.expiration_date >= date.today()
                )
            )
        )
        
        policies = query.all()
        
        # Filter by diagnosis codes if specified in policy
        applicable_policies = []
        for policy in policies:
            if not policy.diagnosis_codes:
                # Policy applies to all diagnosis codes
                applicable_policies.append(policy)
            else:
                # Check if any diagnosis code matches
                if any(dx_code in policy.diagnosis_codes for dx_code in diagnosis_codes):
                    applicable_policies.append(policy)
        
        return applicable_policies
    
    def _get_cms_policies(
        self,
        policy_type: PolicyType,
        procedure_codes: List[str],
        diagnosis_codes: List[str]
    ) -> List[CoveragePolicyDB]:
        """Get CMS policies (NCD/LCD) for the given codes."""
        query = self.db_session.query(CoveragePolicyDB).filter(
            and_(
                CoveragePolicyDB.policy_type == policy_type.value,
                CoveragePolicyDB.procedure_code.in_(procedure_codes),
                CoveragePolicyDB.is_active == True,
                CoveragePolicyDB.effective_date <= date.today(),
                or_(
                    CoveragePolicyDB.expiration_date.is_(None),
                    CoveragePolicyDB.expiration_date >= date.today()
                )
            )
        )
        
        return query.all()
    
    def _validate_against_policy(
        self,
        request: AuthorizationRequest,
        policy: CoveragePolicyDB
    ) -> PolicyValidationResult:
        """Validate request against a specific policy."""
        try:
            coverage_criteria = policy.coverage_criteria
            reasoning = []
            additional_requirements = []
            confidence_score = 1.0
            
            # Check basic coverage
            is_covered = True
            
            # Check age requirements
            if 'age_range' in coverage_criteria:
                age_range = coverage_criteria['age_range']
                patient_age = request.patient_demographics.age
                
                if 'min_age' in age_range and patient_age < age_range['min_age']:
                    is_covered = False
                    reasoning.append(f"Patient age {patient_age} below minimum required age {age_range['min_age']}")
                
                if 'max_age' in age_range and patient_age > age_range['max_age']:
                    is_covered = False
                    reasoning.append(f"Patient age {patient_age} above maximum allowed age {age_range['max_age']}")
            
            # Check medical necessity requirements
            if 'medical_necessity' in coverage_criteria:
                necessity_criteria = coverage_criteria['medical_necessity']
                
                if 'required_symptoms' in necessity_criteria:
                    # This would require clinical notes analysis
                    additional_requirements.append("Clinical documentation of required symptoms")
                
                if 'prior_treatment' in necessity_criteria:
                    additional_requirements.append("Documentation of prior conservative treatment")
                
                if 'duration_requirements' in necessity_criteria:
                    additional_requirements.append("Documentation of symptom duration")
            
            # Check procedure-specific requirements
            if 'procedure_requirements' in coverage_criteria:
                proc_requirements = coverage_criteria['procedure_requirements']
                
                if 'contrast_requirements' in proc_requirements:
                    additional_requirements.append("Contrast usage documentation")
                
                if 'anatomical_requirements' in proc_requirements:
                    additional_requirements.append("Anatomical region specification")
            
            # Adjust confidence based on completeness
            if additional_requirements:
                confidence_score = 0.8  # Lower confidence when additional info needed
            
            if is_covered and not reasoning:
                reasoning.append(f"Request meets coverage criteria per policy {policy.policy_name}")
            
            return PolicyValidationResult(
                is_covered=is_covered,
                policy_id=policy.policy_id,
                policy_type=PolicyType(policy.policy_type),
                reasoning=reasoning,
                confidence_score=confidence_score,
                policy_references=[f"{policy.policy_type}: {policy.policy_name}"],
                additional_requirements=additional_requirements
            )
            
        except Exception as e:
            self.logger.error(f"Policy validation error for policy {policy.policy_id}: {str(e)}")
            return PolicyValidationResult(
                is_covered=False,
                policy_id=policy.policy_id,
                policy_type=PolicyType(policy.policy_type),
                reasoning=[f"Policy validation error: {str(e)}"],
                confidence_score=0.0,
                policy_references=[]
            )
    
    def _apply_most_restrictive_policy(
        self,
        validation_results: List[PolicyValidationResult]
    ) -> PolicyValidationResult:
        """Apply most restrictive policy rule when multiple policies exist."""
        if not validation_results:
            return PolicyValidationResult(
                is_covered=False,
                policy_id="",
                policy_type=PolicyType.PAYER,
                reasoning=["No policies to evaluate"],
                confidence_score=0.0,
                policy_references=[]
            )
        
        # If any policy denies coverage, the request is denied
        denied_results = [r for r in validation_results if not r.is_covered]
        if denied_results:
            # Use the first denial result
            result = denied_results[0]
            result.reasoning.append("Most restrictive policy applied - coverage denied")
            return result
        
        # All policies approve - combine results
        approved_results = validation_results
        combined_reasoning = []
        combined_references = []
        combined_requirements = []
        
        for result in approved_results:
            combined_reasoning.extend(result.reasoning)
            combined_references.extend(result.policy_references)
            combined_requirements.extend(result.additional_requirements)
        
        # Use minimum confidence score
        min_confidence = min(r.confidence_score for r in approved_results)
        
        return PolicyValidationResult(
            is_covered=True,
            policy_id=approved_results[0].policy_id,  # Use first policy ID
            policy_type=approved_results[0].policy_type,
            reasoning=list(set(combined_reasoning)),  # Remove duplicates
            confidence_score=min_confidence,
            policy_references=list(set(combined_references)),
            additional_requirements=list(set(combined_requirements))
        )
    
    def _check_policy_compliance(
        self,
        request: AuthorizationRequest,
        policy: CoveragePolicyDB
    ) -> Tuple[List[str], List[str]]:
        """Check compliance against a specific CMS policy."""
        issues = []
        recommendations = []
        
        try:
            coverage_criteria = policy.coverage_criteria
            
            # Check mandatory CMS requirements
            if 'cms_requirements' in coverage_criteria:
                cms_reqs = coverage_criteria['cms_requirements']
                
                if 'documentation_required' in cms_reqs:
                    for doc_req in cms_reqs['documentation_required']:
                        if not request.clinical_notes or doc_req.lower() not in request.clinical_notes.lower():
                            issues.append(f"Missing required documentation: {doc_req}")
                            recommendations.append(f"Include documentation of {doc_req}")
                
                if 'contraindications' in cms_reqs:
                    # This would require more sophisticated clinical analysis
                    recommendations.append("Verify no contraindications exist per CMS guidelines")
            
            # Check frequency limitations
            if 'frequency_limits' in coverage_criteria:
                recommendations.append("Verify frequency limits per CMS guidelines")
            
        except Exception as e:
            issues.append(f"CMS compliance check error: {str(e)}")
        
        return issues, recommendations
    
    def _policy_to_dict(self, policy: CoveragePolicyDB) -> Dict[str, Any]:
        """Convert policy database model to dictionary."""
        return {
            'policy_id': policy.policy_id,
            'payer_id': policy.payer_id,
            'procedure_code': policy.procedure_code,
            'policy_type': policy.policy_type,
            'policy_name': policy.policy_name,
            'effective_date': policy.effective_date.isoformat() if policy.effective_date else None,
            'expiration_date': policy.expiration_date.isoformat() if policy.expiration_date else None,
            'is_active': policy.is_active
        }
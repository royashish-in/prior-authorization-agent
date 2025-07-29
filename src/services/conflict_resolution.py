"""
Policy conflict detection and resolution service.

This module handles automated detection of policy conflicts,
resolution workflows with approval processes, and policy
deployment validation with rollback capabilities.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

from src.database.models import CoveragePolicyDB
from src.services.policy_validation import PolicyValidationService
from src.audit.logger import AuditLogger


logger = logging.getLogger(__name__)


class ConflictType(Enum):
    """Types of policy conflicts."""
    OVERLAPPING_COVERAGE = "overlapping_coverage"
    CONTRADICTORY_CRITERIA = "contradictory_criteria"
    DUPLICATE_POLICY = "duplicate_policy"
    EFFECTIVE_DATE_CONFLICT = "effective_date_conflict"
    HIERARCHY_VIOLATION = "hierarchy_violation"


class ConflictSeverity(Enum):
    """Severity levels for policy conflicts."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ResolutionStatus(Enum):
    """Status of conflict resolution."""
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    RESOLVED = "resolved"


class DeploymentStatus(Enum):
    """Status of policy deployment."""
    PENDING = "pending"
    VALIDATING = "validating"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class PolicyConflict:
    """Represents a policy conflict."""
    conflict_id: str
    conflict_type: ConflictType
    severity: ConflictSeverity
    primary_policy_id: str
    conflicting_policy_id: str
    description: str
    details: Dict[str, Any]
    detected_at: datetime
    resolution_status: ResolutionStatus = ResolutionStatus.PENDING
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None


@dataclass
class ConflictResolution:
    """Represents a conflict resolution proposal."""
    resolution_id: str
    conflict_id: str
    resolution_type: str  # merge, override, deactivate, modify
    proposed_changes: Dict[str, Any]
    justification: str
    proposed_by: str
    proposed_at: datetime
    approval_status: str = "pending"
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


@dataclass
class DeploymentPlan:
    """Represents a policy deployment plan."""
    deployment_id: str
    policies: List[str]  # Policy IDs to deploy
    deployment_type: str  # new, update, rollback
    validation_results: Dict[str, Any]
    deployment_status: DeploymentStatus
    scheduled_at: datetime
    deployed_at: Optional[datetime] = None
    rollback_plan: Optional[Dict[str, Any]] = None


class PolicyConflictDetector:
    """
    Service for detecting policy conflicts automatically.
    
    Analyzes policies for overlapping coverage, contradictory criteria,
    and other types of conflicts that could affect authorization decisions.
    """
    
    def __init__(self, db_session: Session):
        """Initialize the conflict detector."""
        self.db_session = db_session
        self.logger = logging.getLogger(__name__)
        self.policy_validation_service = PolicyValidationService(db_session)
    
    def detect_all_conflicts(self) -> List[PolicyConflict]:
        """
        Detect all policy conflicts in the system.
        
        Returns:
            List of detected conflicts
        """
        try:
            conflicts = []
            
            # Get all active policies
            active_policies = self.db_session.query(CoveragePolicyDB).filter(
                and_(
                    CoveragePolicyDB.is_active == True,
                    CoveragePolicyDB.effective_date <= date.today(),
                    or_(
                        CoveragePolicyDB.expiration_date.is_(None),
                        CoveragePolicyDB.expiration_date >= date.today()
                    )
                )
            ).all()
            
            # Check for conflicts between all policy pairs
            for i, policy1 in enumerate(active_policies):
                for policy2 in active_policies[i+1:]:
                    policy_conflicts = self._detect_conflicts_between_policies(policy1, policy2)
                    conflicts.extend(policy_conflicts)
            
            self.logger.info(f"Detected {len(conflicts)} policy conflicts")
            return conflicts
            
        except Exception as e:
            self.logger.error(f"Failed to detect conflicts: {str(e)}")
            raise
    
    def detect_conflicts_for_policy(self, policy_id: str) -> List[PolicyConflict]:
        """
        Detect conflicts for a specific policy.
        
        Args:
            policy_id: Policy to check for conflicts
            
        Returns:
            List of conflicts involving the specified policy
        """
        try:
            policy = self.db_session.query(CoveragePolicyDB).filter(
                CoveragePolicyDB.policy_id == policy_id
            ).first()
            
            if not policy:
                return []
            
            conflicts = []
            
            # Get other active policies that could conflict
            other_policies = self.db_session.query(CoveragePolicyDB).filter(
                and_(
                    CoveragePolicyDB.policy_id != policy_id,
                    CoveragePolicyDB.is_active == True,
                    CoveragePolicyDB.effective_date <= date.today(),
                    or_(
                        CoveragePolicyDB.expiration_date.is_(None),
                        CoveragePolicyDB.expiration_date >= date.today()
                    )
                )
            ).all()
            
            # Check for conflicts with each other policy
            for other_policy in other_policies:
                policy_conflicts = self._detect_conflicts_between_policies(policy, other_policy)
                conflicts.extend(policy_conflicts)
            
            self.logger.info(f"Detected {len(conflicts)} conflicts for policy {policy_id}")
            return conflicts
            
        except Exception as e:
            self.logger.error(f"Failed to detect conflicts for policy {policy_id}: {str(e)}")
            raise
    
    def _detect_conflicts_between_policies(
        self,
        policy1: CoveragePolicyDB,
        policy2: CoveragePolicyDB
    ) -> List[PolicyConflict]:
        """Detect conflicts between two specific policies."""
        conflicts = []
        
        try:
            # Check for duplicate policies
            duplicate_conflict = self._check_duplicate_policy(policy1, policy2)
            if duplicate_conflict:
                conflicts.append(duplicate_conflict)
            
            # Check for overlapping coverage
            overlap_conflict = self._check_overlapping_coverage(policy1, policy2)
            if overlap_conflict:
                conflicts.append(overlap_conflict)
            
            # Check for contradictory criteria
            criteria_conflict = self._check_contradictory_criteria(policy1, policy2)
            if criteria_conflict:
                conflicts.append(criteria_conflict)
            
            # Check for effective date conflicts
            date_conflict = self._check_effective_date_conflict(policy1, policy2)
            if date_conflict:
                conflicts.append(date_conflict)
            
            # Check for policy hierarchy violations
            hierarchy_conflict = self._check_hierarchy_violation(policy1, policy2)
            if hierarchy_conflict:
                conflicts.append(hierarchy_conflict)
            
        except Exception as e:
            self.logger.error(
                f"Error detecting conflicts between {policy1.policy_id} and {policy2.policy_id}: {str(e)}"
            )
        
        return conflicts
    
    def _check_duplicate_policy(
        self,
        policy1: CoveragePolicyDB,
        policy2: CoveragePolicyDB
    ) -> Optional[PolicyConflict]:
        """Check for duplicate policies."""
        # Policies are duplicates if they have same payer, procedure, and type
        if (policy1.payer_id == policy2.payer_id and
            policy1.procedure_code == policy2.procedure_code and
            policy1.policy_type == policy2.policy_type):
            
            return PolicyConflict(
                conflict_id=f"dup_{uuid4().hex[:8]}",
                conflict_type=ConflictType.DUPLICATE_POLICY,
                severity=ConflictSeverity.HIGH,
                primary_policy_id=policy1.policy_id,
                conflicting_policy_id=policy2.policy_id,
                description=f"Duplicate policy detected for {policy1.payer_id} {policy1.procedure_code}",
                details={
                    "payer_id": policy1.payer_id,
                    "procedure_code": policy1.procedure_code,
                    "policy_type": policy1.policy_type,
                    "policy1_effective": policy1.effective_date.isoformat(),
                    "policy2_effective": policy2.effective_date.isoformat()
                },
                detected_at=datetime.now(timezone.utc)
            )
        
        return None
    
    def _check_overlapping_coverage(
        self,
        policy1: CoveragePolicyDB,
        policy2: CoveragePolicyDB
    ) -> Optional[PolicyConflict]:
        """Check for overlapping coverage between policies."""
        # Check if policies cover same procedure for same payer
        if (policy1.payer_id == policy2.payer_id and
            policy1.procedure_code == policy2.procedure_code):
            
            # Check for overlapping diagnosis codes
            dx_codes1 = set(policy1.diagnosis_codes or [])
            dx_codes2 = set(policy2.diagnosis_codes or [])
            
            # If either policy has no diagnosis codes, it covers all diagnoses
            if not dx_codes1 or not dx_codes2 or dx_codes1.intersection(dx_codes2):
                # Check for overlapping effective dates
                if self._dates_overlap(
                    policy1.effective_date, policy1.expiration_date,
                    policy2.effective_date, policy2.expiration_date
                ):
                    return PolicyConflict(
                        conflict_id=f"overlap_{uuid4().hex[:8]}",
                        conflict_type=ConflictType.OVERLAPPING_COVERAGE,
                        severity=ConflictSeverity.MEDIUM,
                        primary_policy_id=policy1.policy_id,
                        conflicting_policy_id=policy2.policy_id,
                        description=f"Overlapping coverage for {policy1.procedure_code}",
                        details={
                            "payer_id": policy1.payer_id,
                            "procedure_code": policy1.procedure_code,
                            "overlapping_diagnoses": list(dx_codes1.intersection(dx_codes2)) if dx_codes1 and dx_codes2 else "all",
                            "date_overlap": True
                        },
                        detected_at=datetime.now(timezone.utc)
                    )
        
        return None
    
    def _check_contradictory_criteria(
        self,
        policy1: CoveragePolicyDB,
        policy2: CoveragePolicyDB
    ) -> Optional[PolicyConflict]:
        """Check for contradictory coverage criteria."""
        # Only check policies for same payer and procedure
        if (policy1.payer_id != policy2.payer_id or
            policy1.procedure_code != policy2.procedure_code):
            return None
        
        criteria1 = policy1.coverage_criteria
        criteria2 = policy2.coverage_criteria
        
        contradictions = []
        
        # Check age range contradictions
        if 'age_range' in criteria1 and 'age_range' in criteria2:
            age1 = criteria1['age_range']
            age2 = criteria2['age_range']
            
            # Check for non-overlapping age ranges
            if ('min_age' in age1 and 'max_age' in age2 and
                age1['min_age'] > age2['max_age']):
                contradictions.append("Non-overlapping age ranges")
            elif ('max_age' in age1 and 'min_age' in age2 and
                  age1['max_age'] < age2['min_age']):
                contradictions.append("Non-overlapping age ranges")
        
        # Check medical necessity contradictions
        if 'medical_necessity' in criteria1 and 'medical_necessity' in criteria2:
            necessity1 = criteria1['medical_necessity']
            necessity2 = criteria2['medical_necessity']
            
            # Check for contradictory requirements
            if ('required_symptoms' in necessity1 and 'required_symptoms' in necessity2):
                symptoms1 = set(necessity1['required_symptoms'])
                symptoms2 = set(necessity2['required_symptoms'])
                if symptoms1.isdisjoint(symptoms2):
                    contradictions.append("Contradictory symptom requirements")
        
        if contradictions:
            return PolicyConflict(
                conflict_id=f"contra_{uuid4().hex[:8]}",
                conflict_type=ConflictType.CONTRADICTORY_CRITERIA,
                severity=ConflictSeverity.HIGH,
                primary_policy_id=policy1.policy_id,
                conflicting_policy_id=policy2.policy_id,
                description=f"Contradictory criteria: {', '.join(contradictions)}",
                details={
                    "payer_id": policy1.payer_id,
                    "procedure_code": policy1.procedure_code,
                    "contradictions": contradictions,
                    "criteria1": criteria1,
                    "criteria2": criteria2
                },
                detected_at=datetime.now(timezone.utc)
            )
        
        return None
    
    def _check_effective_date_conflict(
        self,
        policy1: CoveragePolicyDB,
        policy2: CoveragePolicyDB
    ) -> Optional[PolicyConflict]:
        """Check for effective date conflicts."""
        # Check if policies are for same payer/procedure with problematic dates
        if (policy1.payer_id == policy2.payer_id and
            policy1.procedure_code == policy2.procedure_code):
            
            # Check if one policy becomes effective before another expires
            if (policy1.effective_date < policy2.effective_date and
                policy1.expiration_date and
                policy1.expiration_date > policy2.effective_date):
                
                return PolicyConflict(
                    conflict_id=f"date_{uuid4().hex[:8]}",
                    conflict_type=ConflictType.EFFECTIVE_DATE_CONFLICT,
                    severity=ConflictSeverity.MEDIUM,
                    primary_policy_id=policy1.policy_id,
                    conflicting_policy_id=policy2.policy_id,
                    description="Effective date conflict - overlapping validity periods",
                    details={
                        "payer_id": policy1.payer_id,
                        "procedure_code": policy1.procedure_code,
                        "policy1_dates": {
                            "effective": policy1.effective_date.isoformat(),
                            "expiration": policy1.expiration_date.isoformat() if policy1.expiration_date else None
                        },
                        "policy2_dates": {
                            "effective": policy2.effective_date.isoformat(),
                            "expiration": policy2.expiration_date.isoformat() if policy2.expiration_date else None
                        }
                    },
                    detected_at=datetime.now(timezone.utc)
                )
        
        return None
    
    def _check_hierarchy_violation(
        self,
        policy1: CoveragePolicyDB,
        policy2: CoveragePolicyDB
    ) -> Optional[PolicyConflict]:
        """Check for policy hierarchy violations."""
        # CMS policies (NCD/LCD) should take precedence over payer policies
        hierarchy_order = {'NCD': 1, 'LCD': 2, 'PAYER': 3}
        
        if (policy1.payer_id == policy2.payer_id and
            policy1.procedure_code == policy2.procedure_code):
            
            priority1 = hierarchy_order.get(policy1.policy_type, 999)
            priority2 = hierarchy_order.get(policy2.policy_type, 999)
            
            # Check if lower priority policy contradicts higher priority
            if priority1 < priority2:
                # policy1 has higher priority, check if policy2 contradicts it
                if self._policies_contradict(policy1, policy2):
                    return PolicyConflict(
                        conflict_id=f"hier_{uuid4().hex[:8]}",
                        conflict_type=ConflictType.HIERARCHY_VIOLATION,
                        severity=ConflictSeverity.CRITICAL,
                        primary_policy_id=policy1.policy_id,
                        conflicting_policy_id=policy2.policy_id,
                        description=f"Hierarchy violation: {policy2.policy_type} policy contradicts {policy1.policy_type} policy",
                        details={
                            "higher_priority_policy": policy1.policy_id,
                            "higher_priority_type": policy1.policy_type,
                            "lower_priority_policy": policy2.policy_id,
                            "lower_priority_type": policy2.policy_type,
                            "procedure_code": policy1.procedure_code
                        },
                        detected_at=datetime.now(timezone.utc)
                    )
        
        return None
    
    def _dates_overlap(
        self,
        start1: date, end1: Optional[date],
        start2: date, end2: Optional[date]
    ) -> bool:
        """Check if two date ranges overlap."""
        # If either range has no end date, treat as ongoing
        if end1 is None:
            end1 = date.max
        if end2 is None:
            end2 = date.max
        
        # Check for overlap
        return start1 <= end2 and start2 <= end1
    
    def _policies_contradict(self, policy1: CoveragePolicyDB, policy2: CoveragePolicyDB) -> bool:
        """Check if two policies contradict each other."""
        # Simple contradiction check - different coverage decisions for same criteria
        # This would need more sophisticated logic in production
        criteria1 = policy1.coverage_criteria
        criteria2 = policy2.coverage_criteria
        
        # For now, assume contradiction if criteria are significantly different
        return criteria1 != criteria2


class ConflictResolutionService:
    """
    Service for managing conflict resolution workflows.
    
    Handles conflict resolution proposals, approval processes,
    and automated resolution strategies.
    """
    
    def __init__(self, db_session: Session):
        """Initialize the conflict resolution service."""
        self.db_session = db_session
        self.logger = logging.getLogger(__name__)
        self.conflict_detector = PolicyConflictDetector(db_session)
        self.audit_logger = AuditLogger(db_session)
    
    async def propose_resolution(
        self,
        conflict: PolicyConflict,
        resolution_type: str,
        proposed_changes: Dict[str, Any],
        justification: str,
        proposed_by: str
    ) -> ConflictResolution:
        """
        Propose a resolution for a policy conflict.
        
        Args:
            conflict: The conflict to resolve
            resolution_type: Type of resolution (merge, override, deactivate, modify)
            proposed_changes: Proposed changes to resolve conflict
            justification: Justification for the resolution
            proposed_by: User proposing the resolution
            
        Returns:
            ConflictResolution object
        """
        try:
            resolution = ConflictResolution(
                resolution_id=f"res_{uuid4().hex[:8]}",
                conflict_id=conflict.conflict_id,
                resolution_type=resolution_type,
                proposed_changes=proposed_changes,
                justification=justification,
                proposed_by=proposed_by,
                proposed_at=datetime.now(timezone.utc)
            )
            
            # Log the resolution proposal
            await self.audit_logger.log_policy_action(
                action="PROPOSE_CONFLICT_RESOLUTION",
                policy_id=conflict.primary_policy_id,
                user_id=proposed_by,
                details={
                    "conflict_id": conflict.conflict_id,
                    "resolution_id": resolution.resolution_id,
                    "resolution_type": resolution_type,
                    "justification": justification
                }
            )
            
            self.logger.info(f"Resolution proposed for conflict {conflict.conflict_id}: {resolution.resolution_id}")
            return resolution
            
        except Exception as e:
            self.logger.error(f"Failed to propose resolution for conflict {conflict.conflict_id}: {str(e)}")
            raise
    
    async def approve_resolution(
        self,
        resolution: ConflictResolution,
        approved_by: str,
        approval_notes: Optional[str] = None
    ) -> bool:
        """
        Approve a conflict resolution.
        
        Args:
            resolution: Resolution to approve
            approved_by: User approving the resolution
            approval_notes: Optional approval notes
            
        Returns:
            True if approved successfully
        """
        try:
            resolution.approval_status = "approved"
            resolution.approved_by = approved_by
            resolution.approved_at = datetime.now(timezone.utc)
            
            # Apply the resolution
            success = await self._apply_resolution(resolution)
            
            if success:
                # Log the approval
                await self.audit_logger.log_policy_action(
                    action="APPROVE_CONFLICT_RESOLUTION",
                    policy_id=resolution.conflict_id,
                    user_id=approved_by,
                    details={
                        "resolution_id": resolution.resolution_id,
                        "approval_notes": approval_notes,
                        "applied_successfully": success
                    }
                )
                
                self.logger.info(f"Resolution approved and applied: {resolution.resolution_id}")
                return True
            else:
                self.logger.error(f"Failed to apply approved resolution: {resolution.resolution_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to approve resolution {resolution.resolution_id}: {str(e)}")
            raise
    
    async def reject_resolution(
        self,
        resolution: ConflictResolution,
        rejected_by: str,
        rejection_reason: str
    ) -> bool:
        """
        Reject a conflict resolution.
        
        Args:
            resolution: Resolution to reject
            rejected_by: User rejecting the resolution
            rejection_reason: Reason for rejection
            
        Returns:
            True if rejected successfully
        """
        try:
            resolution.approval_status = "rejected"
            resolution.approved_by = rejected_by
            resolution.approved_at = datetime.now(timezone.utc)
            
            # Log the rejection
            await self.audit_logger.log_policy_action(
                action="REJECT_CONFLICT_RESOLUTION",
                policy_id=resolution.conflict_id,
                user_id=rejected_by,
                details={
                    "resolution_id": resolution.resolution_id,
                    "rejection_reason": rejection_reason
                }
            )
            
            self.logger.info(f"Resolution rejected: {resolution.resolution_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to reject resolution {resolution.resolution_id}: {str(e)}")
            raise
    
    async def auto_resolve_conflicts(self, conflicts: List[PolicyConflict]) -> List[ConflictResolution]:
        """
        Automatically resolve conflicts using predefined strategies.
        
        Args:
            conflicts: List of conflicts to resolve
            
        Returns:
            List of automatic resolutions
        """
        resolutions = []
        
        for conflict in conflicts:
            try:
                resolution = await self._get_auto_resolution_strategy(conflict)
                if resolution:
                    # Apply automatic resolution
                    success = await self._apply_resolution(resolution)
                    if success:
                        resolutions.append(resolution)
                        
                        # Log automatic resolution
                        await self.audit_logger.log_policy_action(
                            action="AUTO_RESOLVE_CONFLICT",
                            policy_id=conflict.primary_policy_id,
                            user_id="system",
                            details={
                                "conflict_id": conflict.conflict_id,
                                "resolution_id": resolution.resolution_id,
                                "resolution_type": resolution.resolution_type
                            }
                        )
                
            except Exception as e:
                self.logger.error(f"Failed to auto-resolve conflict {conflict.conflict_id}: {str(e)}")
        
        self.logger.info(f"Auto-resolved {len(resolutions)} conflicts")
        return resolutions
    
    async def _apply_resolution(self, resolution: ConflictResolution) -> bool:
        """Apply a conflict resolution."""
        try:
            if resolution.resolution_type == "deactivate":
                # Deactivate the conflicting policy
                policy = self.db_session.query(CoveragePolicyDB).filter(
                    CoveragePolicyDB.policy_id == resolution.proposed_changes.get('policy_to_deactivate')
                ).first()
                
                if policy:
                    policy.is_active = False
                    policy.updated_by = resolution.approved_by or "system"
                    policy.updated_at = datetime.now(timezone.utc)
                    self.db_session.commit()
                    return True
            
            elif resolution.resolution_type == "modify":
                # Modify policy criteria
                policy_id = resolution.proposed_changes.get('policy_to_modify')
                new_criteria = resolution.proposed_changes.get('new_criteria')
                
                policy = self.db_session.query(CoveragePolicyDB).filter(
                    CoveragePolicyDB.policy_id == policy_id
                ).first()
                
                if policy and new_criteria:
                    policy.coverage_criteria = new_criteria
                    policy.updated_by = resolution.approved_by or "system"
                    policy.updated_at = datetime.now(timezone.utc)
                    self.db_session.commit()
                    return True
            
            elif resolution.resolution_type == "merge":
                # Merge policies (complex operation)
                return await self._merge_policies(resolution)
            
            elif resolution.resolution_type == "override":
                # Set policy precedence
                return await self._set_policy_precedence(resolution)
            
            return False
            
        except Exception as e:
            self.db_session.rollback()
            self.logger.error(f"Failed to apply resolution {resolution.resolution_id}: {str(e)}")
            return False
    
    async def _get_auto_resolution_strategy(self, conflict: PolicyConflict) -> Optional[ConflictResolution]:
        """Get automatic resolution strategy for a conflict."""
        if conflict.conflict_type == ConflictType.DUPLICATE_POLICY:
            # For duplicates, deactivate the newer policy
            return ConflictResolution(
                resolution_id=f"auto_{uuid4().hex[:8]}",
                conflict_id=conflict.conflict_id,
                resolution_type="deactivate",
                proposed_changes={
                    "policy_to_deactivate": conflict.conflicting_policy_id
                },
                justification="Automatic resolution: deactivate duplicate policy",
                proposed_by="system",
                proposed_at=datetime.now(timezone.utc),
                approval_status="approved",
                approved_by="system",
                approved_at=datetime.now(timezone.utc)
            )
        
        elif conflict.conflict_type == ConflictType.HIERARCHY_VIOLATION:
            # For hierarchy violations, deactivate lower priority policy
            return ConflictResolution(
                resolution_id=f"auto_{uuid4().hex[:8]}",
                conflict_id=conflict.conflict_id,
                resolution_type="deactivate",
                proposed_changes={
                    "policy_to_deactivate": conflict.conflicting_policy_id
                },
                justification="Automatic resolution: enforce policy hierarchy",
                proposed_by="system",
                proposed_at=datetime.now(timezone.utc),
                approval_status="approved",
                approved_by="system",
                approved_at=datetime.now(timezone.utc)
            )
        
        # Other conflict types require manual resolution
        return None
    
    async def _merge_policies(self, resolution: ConflictResolution) -> bool:
        """Merge two conflicting policies."""
        # This would implement complex policy merging logic
        # For now, return False to indicate manual resolution needed
        self.logger.warning(f"Policy merge not implemented for resolution {resolution.resolution_id}")
        return False
    
    async def _set_policy_precedence(self, resolution: ConflictResolution) -> bool:
        """Set precedence between conflicting policies."""
        # This would implement policy precedence logic
        # For now, return False to indicate manual resolution needed
        self.logger.warning(f"Policy precedence not implemented for resolution {resolution.resolution_id}")
        return False


class PolicyDeploymentService:
    """
    Service for policy deployment validation and rollback.
    
    Handles deployment planning, validation, and rollback capabilities
    for policy changes.
    """
    
    def __init__(self, db_session: Session):
        """Initialize the deployment service."""
        self.db_session = db_session
        self.logger = logging.getLogger(__name__)
        self.conflict_detector = PolicyConflictDetector(db_session)
        self.audit_logger = AuditLogger(db_session)
    
    async def create_deployment_plan(
        self,
        policy_ids: List[str],
        deployment_type: str,
        scheduled_at: Optional[datetime] = None
    ) -> DeploymentPlan:
        """
        Create a deployment plan for policies.
        
        Args:
            policy_ids: List of policy IDs to deploy
            deployment_type: Type of deployment (new, update, rollback)
            scheduled_at: When to deploy (default: now)
            
        Returns:
            DeploymentPlan object
        """
        try:
            deployment_id = f"deploy_{uuid4().hex[:8]}"
            
            # Validate policies before deployment
            validation_results = await self._validate_deployment(policy_ids)
            
            # Create rollback plan
            rollback_plan = await self._create_rollback_plan(policy_ids)
            
            deployment_plan = DeploymentPlan(
                deployment_id=deployment_id,
                policies=policy_ids,
                deployment_type=deployment_type,
                validation_results=validation_results,
                deployment_status=DeploymentStatus.PENDING,
                scheduled_at=scheduled_at or datetime.now(timezone.utc),
                rollback_plan=rollback_plan
            )
            
            self.logger.info(f"Deployment plan created: {deployment_id} for {len(policy_ids)} policies")
            return deployment_plan
            
        except Exception as e:
            self.logger.error(f"Failed to create deployment plan: {str(e)}")
            raise
    
    async def execute_deployment(self, deployment_plan: DeploymentPlan) -> bool:
        """
        Execute a deployment plan.
        
        Args:
            deployment_plan: Plan to execute
            
        Returns:
            True if deployment successful
        """
        try:
            deployment_plan.deployment_status = DeploymentStatus.VALIDATING
            
            # Final validation before deployment
            validation_results = await self._validate_deployment(deployment_plan.policies)
            
            if not validation_results['is_valid']:
                deployment_plan.deployment_status = DeploymentStatus.FAILED
                self.logger.error(f"Deployment validation failed: {validation_results['errors']}")
                return False
            
            deployment_plan.deployment_status = DeploymentStatus.DEPLOYING
            
            # Execute deployment
            success = await self._deploy_policies(deployment_plan.policies)
            
            if success:
                deployment_plan.deployment_status = DeploymentStatus.DEPLOYED
                deployment_plan.deployed_at = datetime.now(timezone.utc)
                
                # Log successful deployment
                await self.audit_logger.log_policy_action(
                    action="DEPLOY_POLICIES",
                    policy_id="deployment",
                    user_id="system",
                    details={
                        "deployment_id": deployment_plan.deployment_id,
                        "policies": deployment_plan.policies,
                        "deployment_type": deployment_plan.deployment_type
                    }
                )
                
                self.logger.info(f"Deployment successful: {deployment_plan.deployment_id}")
                return True
            else:
                deployment_plan.deployment_status = DeploymentStatus.FAILED
                self.logger.error(f"Deployment failed: {deployment_plan.deployment_id}")
                return False
                
        except Exception as e:
            deployment_plan.deployment_status = DeploymentStatus.FAILED
            self.logger.error(f"Deployment execution failed: {str(e)}")
            return False
    
    async def rollback_deployment(self, deployment_plan: DeploymentPlan) -> bool:
        """
        Rollback a deployment.
        
        Args:
            deployment_plan: Plan to rollback
            
        Returns:
            True if rollback successful
        """
        try:
            if not deployment_plan.rollback_plan:
                self.logger.error(f"No rollback plan available for deployment {deployment_plan.deployment_id}")
                return False
            
            # Execute rollback
            success = await self._execute_rollback(deployment_plan.rollback_plan)
            
            if success:
                deployment_plan.deployment_status = DeploymentStatus.ROLLED_BACK
                
                # Log rollback
                await self.audit_logger.log_policy_action(
                    action="ROLLBACK_DEPLOYMENT",
                    policy_id="rollback",
                    user_id="system",
                    details={
                        "deployment_id": deployment_plan.deployment_id,
                        "rollback_reason": "Manual rollback requested"
                    }
                )
                
                self.logger.info(f"Rollback successful: {deployment_plan.deployment_id}")
                return True
            else:
                self.logger.error(f"Rollback failed: {deployment_plan.deployment_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"Rollback execution failed: {str(e)}")
            return False
    
    async def _validate_deployment(self, policy_ids: List[str]) -> Dict[str, Any]:
        """Validate policies before deployment."""
        validation_errors = []
        warnings = []
        
        try:
            for policy_id in policy_ids:
                # Check if policy exists
                policy = self.db_session.query(CoveragePolicyDB).filter(
                    CoveragePolicyDB.policy_id == policy_id
                ).first()
                
                if not policy:
                    validation_errors.append(f"Policy not found: {policy_id}")
                    continue
                
                # Check for conflicts
                conflicts = self.conflict_detector.detect_conflicts_for_policy(policy_id)
                if conflicts:
                    high_severity_conflicts = [c for c in conflicts if c.severity in [ConflictSeverity.HIGH, ConflictSeverity.CRITICAL]]
                    if high_severity_conflicts:
                        validation_errors.append(f"High severity conflicts detected for policy {policy_id}")
                    else:
                        warnings.append(f"Low/medium severity conflicts detected for policy {policy_id}")
            
            return {
                'is_valid': len(validation_errors) == 0,
                'errors': validation_errors,
                'warnings': warnings
            }
            
        except Exception as e:
            return {
                'is_valid': False,
                'errors': [f"Validation error: {str(e)}"],
                'warnings': []
            }
    
    async def _create_rollback_plan(self, policy_ids: List[str]) -> Dict[str, Any]:
        """Create rollback plan for deployment."""
        rollback_plan = {
            'policies_to_restore': [],
            'policies_to_deactivate': policy_ids,
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        # For each policy being deployed, save current state for rollback
        for policy_id in policy_ids:
            policy = self.db_session.query(CoveragePolicyDB).filter(
                CoveragePolicyDB.policy_id == policy_id
            ).first()
            
            if policy:
                rollback_plan['policies_to_restore'].append({
                    'policy_id': policy.policy_id,
                    'previous_state': {
                        'is_active': policy.is_active,
                        'coverage_criteria': policy.coverage_criteria,
                        'effective_date': policy.effective_date.isoformat(),
                        'expiration_date': policy.expiration_date.isoformat() if policy.expiration_date else None
                    }
                })
        
        return rollback_plan
    
    async def _deploy_policies(self, policy_ids: List[str]) -> bool:
        """Deploy policies to production."""
        try:
            # In a real system, this would involve:
            # 1. Updating policy cache
            # 2. Notifying all service instances
            # 3. Updating configuration
            # 4. Running health checks
            
            # For now, just mark policies as deployed
            for policy_id in policy_ids:
                policy = self.db_session.query(CoveragePolicyDB).filter(
                    CoveragePolicyDB.policy_id == policy_id
                ).first()
                
                if policy:
                    policy.updated_at = datetime.now(timezone.utc)
            
            self.db_session.commit()
            return True
            
        except Exception as e:
            self.db_session.rollback()
            self.logger.error(f"Policy deployment failed: {str(e)}")
            return False
    
    async def _execute_rollback(self, rollback_plan: Dict[str, Any]) -> bool:
        """Execute rollback plan."""
        try:
            # Restore previous policy states
            for policy_restore in rollback_plan['policies_to_restore']:
                policy = self.db_session.query(CoveragePolicyDB).filter(
                    CoveragePolicyDB.policy_id == policy_restore['policy_id']
                ).first()
                
                if policy:
                    previous_state = policy_restore['previous_state']
                    policy.is_active = previous_state['is_active']
                    policy.coverage_criteria = previous_state['coverage_criteria']
                    policy.updated_at = datetime.now(timezone.utc)
            
            self.db_session.commit()
            return True
            
        except Exception as e:
            self.db_session.rollback()
            self.logger.error(f"Rollback execution failed: {str(e)}")
            return False
"""
Policy configuration API endpoints for managing coverage policies.

This module provides web-based policy configuration with version control,
bulk import/validation, and policy testing sandbox environment.
"""

import json
import logging
from datetime import date, datetime, timezone
from typing import List, Dict, Optional, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session

from src.database.connection import get_db_session
from src.auth.oauth2 import get_current_user, require_permissions
from src.services.policy_validation import PolicyValidationService, PolicyType
from src.services.policy_config import PolicyConfigurationService
from src.services.conflict_resolution import (
    PolicyConflictDetector, ConflictResolutionService, PolicyDeploymentService,
    PolicyConflict, ConflictResolution, DeploymentPlan
)
from src.audit.logger import AuditLogger
from src.auth.models import UserRole


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/policy-config", tags=["Policy Configuration"])


# Request/Response Models
class PolicyConfigRequest(BaseModel):
    """Request model for policy configuration."""
    payer_id: str = Field(..., description="Payer identifier")
    procedure_code: str = Field(..., description="CPT/HCPCS procedure code")
    policy_name: str = Field(..., description="Human-readable policy name")
    policy_type: str = Field(..., description="Policy type: NCD, LCD, or PAYER")
    diagnosis_codes: Optional[List[str]] = Field(default=[], description="Applicable ICD-10 diagnosis codes")
    coverage_criteria: Dict[str, Any] = Field(..., description="Coverage criteria configuration")
    effective_date: date = Field(default_factory=date.today, description="Policy effective date")
    expiration_date: Optional[date] = Field(None, description="Policy expiration date")
    is_active: bool = Field(default=True, description="Whether policy is active")
    
    @validator('policy_type')
    def validate_policy_type(cls, v):
        if v not in ['NCD', 'LCD', 'PAYER']:
            raise ValueError('Policy type must be NCD, LCD, or PAYER')
        return v
    
    @validator('procedure_code')
    def validate_procedure_code(cls, v):
        if not v or len(v) < 5:
            raise ValueError('Procedure code must be at least 5 characters')
        return v
    
    @validator('coverage_criteria')
    def validate_coverage_criteria(cls, v):
        if not v or not isinstance(v, dict):
            raise ValueError('Coverage criteria must be a non-empty dictionary')
        return v


class PolicyUpdateRequest(BaseModel):
    """Request model for policy updates."""
    policy_name: Optional[str] = None
    diagnosis_codes: Optional[List[str]] = None
    coverage_criteria: Optional[Dict[str, Any]] = None
    effective_date: Optional[date] = None
    expiration_date: Optional[date] = None
    is_active: Optional[bool] = None
    update_reason: str = Field(..., description="Reason for policy update")


class PolicyVersionResponse(BaseModel):
    """Response model for policy version information."""
    policy_id: str
    version: str
    created_at: datetime
    created_by: str
    update_reason: Optional[str]
    is_current: bool


class PolicyResponse(BaseModel):
    """Response model for policy information."""
    policy_id: str
    payer_id: str
    procedure_code: str
    policy_name: str
    policy_type: str
    policy_version: str
    diagnosis_codes: List[str]
    coverage_criteria: Dict[str, Any]
    effective_date: date
    expiration_date: Optional[date]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str


class BulkImportRequest(BaseModel):
    """Request model for bulk policy import."""
    policies: List[PolicyConfigRequest]
    import_mode: str = Field(default="validate", description="Import mode: validate, import, or replace")
    
    @validator('import_mode')
    def validate_import_mode(cls, v):
        if v not in ['validate', 'import', 'replace']:
            raise ValueError('Import mode must be validate, import, or replace')
        return v


class BulkImportResponse(BaseModel):
    """Response model for bulk import results."""
    total_policies: int
    successful_imports: int
    failed_imports: int
    validation_errors: List[Dict[str, Any]]
    import_summary: Dict[str, Any]


class PolicyTestRequest(BaseModel):
    """Request model for policy testing."""
    policy_config: PolicyConfigRequest
    test_scenarios: List[Dict[str, Any]]


class PolicyTestResponse(BaseModel):
    """Response model for policy test results."""
    policy_id: str
    test_results: List[Dict[str, Any]]
    overall_success: bool
    recommendations: List[str]


# API Endpoints
@router.post("/policies", response_model=PolicyResponse)
async def create_policy(
    policy_request: PolicyConfigRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new coverage policy with version control.
    
    Requires ADMIN or POLICY_MANAGER role.
    """
    # Check permissions
    require_permissions(current_user, [UserRole.ADMIN, UserRole.POLICY_MANAGER])
    
    try:
        # Initialize services
        policy_service = PolicyConfigurationService(db)
        audit_logger = AuditLogger(db)
        
        # Create policy
        policy_id = await policy_service.create_policy(
            policy_data=policy_request.dict(),
            created_by=current_user['user_id']
        )
        
        # Get created policy for response
        policy = policy_service.get_policy_by_id(policy_id)
        if not policy:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Policy created but could not be retrieved"
            )
        
        # Log audit event
        background_tasks.add_task(
            audit_logger.log_policy_action,
            action="CREATE_POLICY",
            policy_id=policy_id,
            user_id=current_user['user_id'],
            details={
                "payer_id": policy_request.payer_id,
                "procedure_code": policy_request.procedure_code,
                "policy_type": policy_request.policy_type
            }
        )
        
        # Convert to response model
        response = PolicyResponse(
            policy_id=policy.policy_id,
            payer_id=policy.payer_id,
            procedure_code=policy.procedure_code,
            policy_name=policy.policy_name,
            policy_type=policy.policy_type,
            policy_version=policy.policy_version,
            diagnosis_codes=policy.diagnosis_codes or [],
            coverage_criteria=policy.coverage_criteria,
            effective_date=policy.effective_date,
            expiration_date=policy.expiration_date,
            is_active=policy.is_active,
            created_at=policy.created_at,
            updated_at=policy.updated_at,
            created_by=policy.created_by,
            updated_by=policy.updated_by
        )
        
        logger.info(f"Policy created successfully: {policy_id} by user {current_user['user_id']}")
        return response
        
    except Exception as e:
        logger.error(f"Failed to create policy: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create policy: {str(e)}"
        )


@router.get("/policies/{policy_id}", response_model=PolicyResponse)
async def get_policy(
    policy_id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """Get policy by ID."""
    try:
        policy_service = PolicyConfigurationService(db)
        policy = policy_service.get_policy_by_id(policy_id)
        
        if not policy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Policy not found: {policy_id}"
            )
        
        return PolicyResponse(
            policy_id=policy.policy_id,
            payer_id=policy.payer_id,
            procedure_code=policy.procedure_code,
            policy_name=policy.policy_name,
            policy_type=policy.policy_type,
            policy_version=policy.policy_version,
            diagnosis_codes=policy.diagnosis_codes or [],
            coverage_criteria=policy.coverage_criteria,
            effective_date=policy.effective_date,
            expiration_date=policy.expiration_date,
            is_active=policy.is_active,
            created_at=policy.created_at,
            updated_at=policy.updated_at,
            created_by=policy.created_by,
            updated_by=policy.updated_by
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get policy {policy_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve policy: {str(e)}"
        )


@router.put("/policies/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: str,
    update_request: PolicyUpdateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Update an existing policy with version control.
    
    Requires ADMIN or POLICY_MANAGER role.
    """
    # Check permissions
    require_permissions(current_user, [UserRole.ADMIN, UserRole.POLICY_MANAGER])
    
    try:
        policy_service = PolicyConfigurationService(db)
        audit_logger = AuditLogger(db)
        
        # Update policy
        updated_policy = await policy_service.update_policy(
            policy_id=policy_id,
            update_data=update_request.dict(exclude_unset=True),
            updated_by=current_user['user_id'],
            update_reason=update_request.update_reason
        )
        
        if not updated_policy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Policy not found: {policy_id}"
            )
        
        # Log audit event
        background_tasks.add_task(
            audit_logger.log_policy_action,
            action="UPDATE_POLICY",
            policy_id=policy_id,
            user_id=current_user['user_id'],
            details={
                "update_reason": update_request.update_reason,
                "updated_fields": list(update_request.dict(exclude_unset=True).keys())
            }
        )
        
        return PolicyResponse(
            policy_id=updated_policy.policy_id,
            payer_id=updated_policy.payer_id,
            procedure_code=updated_policy.procedure_code,
            policy_name=updated_policy.policy_name,
            policy_type=updated_policy.policy_type,
            policy_version=updated_policy.policy_version,
            diagnosis_codes=updated_policy.diagnosis_codes or [],
            coverage_criteria=updated_policy.coverage_criteria,
            effective_date=updated_policy.effective_date,
            expiration_date=updated_policy.expiration_date,
            is_active=updated_policy.is_active,
            created_at=updated_policy.created_at,
            updated_at=updated_policy.updated_at,
            created_by=updated_policy.created_by,
            updated_by=updated_policy.updated_by
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update policy {policy_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update policy: {str(e)}"
        )


@router.delete("/policies/{policy_id}")
async def deactivate_policy(
    policy_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Deactivate a policy (soft delete with audit trail).
    
    Requires ADMIN role.
    """
    # Check permissions
    require_permissions(current_user, [UserRole.ADMIN])
    
    try:
        policy_service = PolicyConfigurationService(db)
        audit_logger = AuditLogger(db)
        
        # Deactivate policy
        success = await policy_service.deactivate_policy(
            policy_id=policy_id,
            deactivated_by=current_user['user_id']
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Policy not found: {policy_id}"
            )
        
        # Log audit event
        background_tasks.add_task(
            audit_logger.log_policy_action,
            action="DEACTIVATE_POLICY",
            policy_id=policy_id,
            user_id=current_user['user_id'],
            details={"reason": "Policy deactivated via API"}
        )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": f"Policy {policy_id} deactivated successfully"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deactivate policy {policy_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deactivate policy: {str(e)}"
        )


@router.get("/policies/{policy_id}/versions", response_model=List[PolicyVersionResponse])
async def get_policy_versions(
    policy_id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """Get version history for a policy."""
    try:
        policy_service = PolicyConfigurationService(db)
        versions = policy_service.get_policy_versions(policy_id)
        
        return [
            PolicyVersionResponse(
                policy_id=version.policy_id,
                version=version.version,
                created_at=version.created_at,
                created_by=version.created_by,
                update_reason=version.update_reason,
                is_current=version.is_current
            )
            for version in versions
        ]
        
    except Exception as e:
        logger.error(f"Failed to get policy versions for {policy_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve policy versions: {str(e)}"
        )


@router.get("/policies", response_model=List[PolicyResponse])
async def list_policies(
    payer_id: Optional[str] = None,
    policy_type: Optional[str] = None,
    active_only: bool = True,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """List policies with filtering options."""
    try:
        policy_service = PolicyConfigurationService(db)
        policies = policy_service.list_policies(
            payer_id=payer_id,
            policy_type=policy_type,
            active_only=active_only,
            limit=limit,
            offset=offset
        )
        
        return [
            PolicyResponse(
                policy_id=policy.policy_id,
                payer_id=policy.payer_id,
                procedure_code=policy.procedure_code,
                policy_name=policy.policy_name,
                policy_type=policy.policy_type,
                policy_version=policy.policy_version,
                diagnosis_codes=policy.diagnosis_codes or [],
                coverage_criteria=policy.coverage_criteria,
                effective_date=policy.effective_date,
                expiration_date=policy.expiration_date,
                is_active=policy.is_active,
                created_at=policy.created_at,
                updated_at=policy.updated_at,
                created_by=policy.created_by,
                updated_by=policy.updated_by
            )
            for policy in policies
        ]
        
    except Exception as e:
        logger.error(f"Failed to list policies: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list policies: {str(e)}"
        )


@router.post("/policies/bulk-import", response_model=BulkImportResponse)
async def bulk_import_policies(
    import_request: BulkImportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Bulk import policies with validation.
    
    Requires ADMIN or POLICY_MANAGER role.
    """
    # Check permissions
    require_permissions(current_user, [UserRole.ADMIN, UserRole.POLICY_MANAGER])
    
    try:
        policy_service = PolicyConfigurationService(db)
        audit_logger = AuditLogger(db)
        
        # Perform bulk import
        import_result = await policy_service.bulk_import_policies(
            policies_data=[policy.dict() for policy in import_request.policies],
            import_mode=import_request.import_mode,
            imported_by=current_user['user_id']
        )
        
        # Log audit event
        background_tasks.add_task(
            audit_logger.log_policy_action,
            action="BULK_IMPORT_POLICIES",
            policy_id="bulk_import",
            user_id=current_user['user_id'],
            details={
                "total_policies": import_result['total_policies'],
                "successful_imports": import_result['successful_imports'],
                "failed_imports": import_result['failed_imports'],
                "import_mode": import_request.import_mode
            }
        )
        
        return BulkImportResponse(
            total_policies=import_result['total_policies'],
            successful_imports=import_result['successful_imports'],
            failed_imports=import_result['failed_imports'],
            validation_errors=import_result['validation_errors'],
            import_summary=import_result['import_summary']
        )
        
    except Exception as e:
        logger.error(f"Bulk import failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk import failed: {str(e)}"
        )


@router.post("/policies/bulk-import/file")
async def bulk_import_from_file(
    file: UploadFile = File(...),
    import_mode: str = "validate",
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Bulk import policies from JSON file.
    
    Requires ADMIN or POLICY_MANAGER role.
    """
    # Check permissions
    require_permissions(current_user, [UserRole.ADMIN, UserRole.POLICY_MANAGER])
    
    try:
        # Validate file type
        if not file.filename.endswith('.json'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be a JSON file"
            )
        
        # Read and parse file
        content = await file.read()
        try:
            policies_data = json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSON format: {str(e)}"
            )
        
        # Validate structure
        if not isinstance(policies_data, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="JSON file must contain an array of policy objects"
            )
        
        # Convert to request models for validation
        try:
            policies = [PolicyConfigRequest(**policy_data) for policy_data in policies_data]
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid policy data structure: {str(e)}"
            )
        
        # Create bulk import request
        import_request = BulkImportRequest(
            policies=policies,
            import_mode=import_mode
        )
        
        # Use existing bulk import endpoint
        return await bulk_import_policies(
            import_request=import_request,
            background_tasks=background_tasks,
            db=db,
            current_user=current_user
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File import failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File import failed: {str(e)}"
        )


@router.post("/policies/test", response_model=PolicyTestResponse)
async def test_policy(
    test_request: PolicyTestRequest,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Test policy configuration in sandbox environment.
    
    Requires ADMIN or POLICY_MANAGER role.
    """
    # Check permissions
    require_permissions(current_user, [UserRole.ADMIN, UserRole.POLICY_MANAGER])
    
    try:
        policy_service = PolicyConfigurationService(db)
        
        # Test policy in sandbox
        test_result = await policy_service.test_policy_sandbox(
            policy_config=test_request.policy_config.dict(),
            test_scenarios=test_request.test_scenarios,
            tested_by=current_user['user_id']
        )
        
        return PolicyTestResponse(
            policy_id=test_result['policy_id'],
            test_results=test_result['test_results'],
            overall_success=test_result['overall_success'],
            recommendations=test_result['recommendations']
        )
        
    except Exception as e:
        logger.error(f"Policy testing failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Policy testing failed: {str(e)}"
        )


@router.post("/policies/{policy_id}/validate")
async def validate_policy(
    policy_id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """Validate policy configuration and check for conflicts."""
    try:
        policy_service = PolicyConfigurationService(db)
        
        # Validate policy
        validation_result = await policy_service.validate_policy_configuration(
            policy_id=policy_id
        )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "policy_id": policy_id,
                "is_valid": validation_result['is_valid'],
                "validation_errors": validation_result['validation_errors'],
                "warnings": validation_result['warnings'],
                "recommendations": validation_result['recommendations']
            }
        )
        
    except Exception as e:
        logger.error(f"Policy validation failed for {policy_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Policy validation failed: {str(e)}"
        )


# Additional Request/Response Models for Conflict Resolution
class ConflictResponse(BaseModel):
    """Response model for policy conflicts."""
    conflict_id: str
    conflict_type: str
    severity: str
    primary_policy_id: str
    conflicting_policy_id: str
    description: str
    details: Dict[str, Any]
    detected_at: datetime
    resolution_status: str
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None


class ResolutionRequest(BaseModel):
    """Request model for conflict resolution."""
    resolution_type: str = Field(..., description="Type of resolution: merge, override, deactivate, modify")
    proposed_changes: Dict[str, Any] = Field(..., description="Proposed changes to resolve conflict")
    justification: str = Field(..., description="Justification for the resolution")
    
    @validator('resolution_type')
    def validate_resolution_type(cls, v):
        if v not in ['merge', 'override', 'deactivate', 'modify']:
            raise ValueError('Resolution type must be merge, override, deactivate, or modify')
        return v


class ResolutionResponse(BaseModel):
    """Response model for conflict resolution."""
    resolution_id: str
    conflict_id: str
    resolution_type: str
    proposed_changes: Dict[str, Any]
    justification: str
    proposed_by: str
    proposed_at: datetime
    approval_status: str
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


class DeploymentPlanRequest(BaseModel):
    """Request model for deployment plan."""
    policy_ids: List[str] = Field(..., description="List of policy IDs to deploy")
    deployment_type: str = Field(..., description="Type of deployment: new, update, rollback")
    scheduled_at: Optional[datetime] = Field(None, description="When to deploy (default: now)")
    
    @validator('deployment_type')
    def validate_deployment_type(cls, v):
        if v not in ['new', 'update', 'rollback']:
            raise ValueError('Deployment type must be new, update, or rollback')
        return v


class DeploymentPlanResponse(BaseModel):
    """Response model for deployment plan."""
    deployment_id: str
    policies: List[str]
    deployment_type: str
    validation_results: Dict[str, Any]
    deployment_status: str
    scheduled_at: datetime
    deployed_at: Optional[datetime] = None
    rollback_available: bool


# Conflict Detection and Resolution Endpoints
@router.get("/conflicts", response_model=List[ConflictResponse])
async def detect_all_conflicts(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Detect all policy conflicts in the system.
    
    Requires ADMIN or POLICY_MANAGER role.
    """
    # Check permissions
    require_permissions(current_user, [UserRole.ADMIN, UserRole.POLICY_MANAGER])
    
    try:
        conflict_detector = PolicyConflictDetector(db)
        conflicts = conflict_detector.detect_all_conflicts()
        
        return [
            ConflictResponse(
                conflict_id=conflict.conflict_id,
                conflict_type=conflict.conflict_type.value,
                severity=conflict.severity.value,
                primary_policy_id=conflict.primary_policy_id,
                conflicting_policy_id=conflict.conflicting_policy_id,
                description=conflict.description,
                details=conflict.details,
                detected_at=conflict.detected_at,
                resolution_status=conflict.resolution_status.value,
                resolution_notes=conflict.resolution_notes,
                resolved_at=conflict.resolved_at,
                resolved_by=conflict.resolved_by
            )
            for conflict in conflicts
        ]
        
    except Exception as e:
        logger.error(f"Failed to detect conflicts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to detect conflicts: {str(e)}"
        )


@router.get("/policies/{policy_id}/conflicts", response_model=List[ConflictResponse])
async def detect_policy_conflicts(
    policy_id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Detect conflicts for a specific policy.
    
    Requires ADMIN or POLICY_MANAGER role.
    """
    # Check permissions
    require_permissions(current_user, [UserRole.ADMIN, UserRole.POLICY_MANAGER])
    
    try:
        conflict_detector = PolicyConflictDetector(db)
        conflicts = conflict_detector.detect_conflicts_for_policy(policy_id)
        
        return [
            ConflictResponse(
                conflict_id=conflict.conflict_id,
                conflict_type=conflict.conflict_type.value,
                severity=conflict.severity.value,
                primary_policy_id=conflict.primary_policy_id,
                conflicting_policy_id=conflict.conflicting_policy_id,
                description=conflict.description,
                details=conflict.details,
                detected_at=conflict.detected_at,
                resolution_status=conflict.resolution_status.value,
                resolution_notes=conflict.resolution_notes,
                resolved_at=conflict.resolved_at,
                resolved_by=conflict.resolved_by
            )
            for conflict in conflicts
        ]
        
    except Exception as e:
        logger.error(f"Failed to detect conflicts for policy {policy_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to detect conflicts: {str(e)}"
        )


@router.post("/conflicts/{conflict_id}/resolutions", response_model=ResolutionResponse)
async def propose_conflict_resolution(
    conflict_id: str,
    resolution_request: ResolutionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Propose a resolution for a policy conflict.
    
    Requires ADMIN or POLICY_MANAGER role.
    """
    # Check permissions
    require_permissions(current_user, [UserRole.ADMIN, UserRole.POLICY_MANAGER])
    
    try:
        resolution_service = ConflictResolutionService(db)
        
        # Create a mock conflict object (in production, this would be retrieved from database)
        conflict = PolicyConflict(
            conflict_id=conflict_id,
            conflict_type=None,  # Would be retrieved from database
            severity=None,
            primary_policy_id="",
            conflicting_policy_id="",
            description="",
            details={},
            detected_at=datetime.now(timezone.utc)
        )
        
        # Propose resolution
        resolution = await resolution_service.propose_resolution(
            conflict=conflict,
            resolution_type=resolution_request.resolution_type,
            proposed_changes=resolution_request.proposed_changes,
            justification=resolution_request.justification,
            proposed_by=current_user['user_id']
        )
        
        return ResolutionResponse(
            resolution_id=resolution.resolution_id,
            conflict_id=resolution.conflict_id,
            resolution_type=resolution.resolution_type,
            proposed_changes=resolution.proposed_changes,
            justification=resolution.justification,
            proposed_by=resolution.proposed_by,
            proposed_at=resolution.proposed_at,
            approval_status=resolution.approval_status,
            approved_by=resolution.approved_by,
            approved_at=resolution.approved_at
        )
        
    except Exception as e:
        logger.error(f"Failed to propose resolution for conflict {conflict_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to propose resolution: {str(e)}"
        )


@router.post("/resolutions/{resolution_id}/approve")
async def approve_resolution(
    resolution_id: str,
    approval_notes: Optional[str] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Approve a conflict resolution.
    
    Requires ADMIN role.
    """
    # Check permissions
    require_permissions(current_user, [UserRole.ADMIN])
    
    try:
        resolution_service = ConflictResolutionService(db)
        
        # Create a mock resolution object (in production, this would be retrieved from database)
        resolution = ConflictResolution(
            resolution_id=resolution_id,
            conflict_id="",
            resolution_type="",
            proposed_changes={},
            justification="",
            proposed_by="",
            proposed_at=datetime.now(timezone.utc)
        )
        
        # Approve resolution
        success = await resolution_service.approve_resolution(
            resolution=resolution,
            approved_by=current_user['user_id'],
            approval_notes=approval_notes
        )
        
        if success:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"message": f"Resolution {resolution_id} approved successfully"}
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to apply approved resolution"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to approve resolution {resolution_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to approve resolution: {str(e)}"
        )


@router.post("/resolutions/{resolution_id}/reject")
async def reject_resolution(
    resolution_id: str,
    rejection_reason: str,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Reject a conflict resolution.
    
    Requires ADMIN role.
    """
    # Check permissions
    require_permissions(current_user, [UserRole.ADMIN])
    
    try:
        resolution_service = ConflictResolutionService(db)
        
        # Create a mock resolution object (in production, this would be retrieved from database)
        resolution = ConflictResolution(
            resolution_id=resolution_id,
            conflict_id="",
            resolution_type="",
            proposed_changes={},
            justification="",
            proposed_by="",
            proposed_at=datetime.now(timezone.utc)
        )
        
        # Reject resolution
        success = await resolution_service.reject_resolution(
            resolution=resolution,
            rejected_by=current_user['user_id'],
            rejection_reason=rejection_reason
        )
        
        if success:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"message": f"Resolution {resolution_id} rejected successfully"}
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reject resolution"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reject resolution {resolution_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reject resolution: {str(e)}"
        )


@router.post("/conflicts/auto-resolve")
async def auto_resolve_conflicts(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Automatically resolve conflicts using predefined strategies.
    
    Requires ADMIN role.
    """
    # Check permissions
    require_permissions(current_user, [UserRole.ADMIN])
    
    try:
        conflict_detector = PolicyConflictDetector(db)
        resolution_service = ConflictResolutionService(db)
        
        # Detect all conflicts
        conflicts = conflict_detector.detect_all_conflicts()
        
        # Auto-resolve conflicts
        resolutions = await resolution_service.auto_resolve_conflicts(conflicts)
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": f"Auto-resolved {len(resolutions)} conflicts",
                "total_conflicts": len(conflicts),
                "resolved_conflicts": len(resolutions),
                "resolution_ids": [r.resolution_id for r in resolutions]
            }
        )
        
    except Exception as e:
        logger.error(f"Auto-resolve conflicts failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Auto-resolve failed: {str(e)}"
        )


# Policy Deployment Endpoints
@router.post("/deployments", response_model=DeploymentPlanResponse)
async def create_deployment_plan(
    deployment_request: DeploymentPlanRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a deployment plan for policies.
    
    Requires ADMIN role.
    """
    # Check permissions
    require_permissions(current_user, [UserRole.ADMIN])
    
    try:
        deployment_service = PolicyDeploymentService(db)
        
        # Create deployment plan
        deployment_plan = await deployment_service.create_deployment_plan(
            policy_ids=deployment_request.policy_ids,
            deployment_type=deployment_request.deployment_type,
            scheduled_at=deployment_request.scheduled_at
        )
        
        # Log deployment plan creation
        background_tasks.add_task(
            AuditLogger(db).log_policy_action,
            action="CREATE_DEPLOYMENT_PLAN",
            policy_id="deployment",
            user_id=current_user['user_id'],
            details={
                "deployment_id": deployment_plan.deployment_id,
                "policies": deployment_plan.policies,
                "deployment_type": deployment_plan.deployment_type
            }
        )
        
        return DeploymentPlanResponse(
            deployment_id=deployment_plan.deployment_id,
            policies=deployment_plan.policies,
            deployment_type=deployment_plan.deployment_type,
            validation_results=deployment_plan.validation_results,
            deployment_status=deployment_plan.deployment_status.value,
            scheduled_at=deployment_plan.scheduled_at,
            deployed_at=deployment_plan.deployed_at,
            rollback_available=deployment_plan.rollback_plan is not None
        )
        
    except Exception as e:
        logger.error(f"Failed to create deployment plan: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create deployment plan: {str(e)}"
        )


@router.post("/deployments/{deployment_id}/execute")
async def execute_deployment(
    deployment_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Execute a deployment plan.
    
    Requires ADMIN role.
    """
    # Check permissions
    require_permissions(current_user, [UserRole.ADMIN])
    
    try:
        deployment_service = PolicyDeploymentService(db)
        
        # Create a mock deployment plan (in production, this would be retrieved from database)
        deployment_plan = DeploymentPlan(
            deployment_id=deployment_id,
            policies=[],
            deployment_type="update",
            validation_results={},
            deployment_status=None,
            scheduled_at=datetime.now(timezone.utc)
        )
        
        # Execute deployment
        success = await deployment_service.execute_deployment(deployment_plan)
        
        if success:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"message": f"Deployment {deployment_id} executed successfully"}
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Deployment execution failed"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to execute deployment {deployment_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute deployment: {str(e)}"
        )


@router.post("/deployments/{deployment_id}/rollback")
async def rollback_deployment(
    deployment_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Rollback a deployment.
    
    Requires ADMIN role.
    """
    # Check permissions
    require_permissions(current_user, [UserRole.ADMIN])
    
    try:
        deployment_service = PolicyDeploymentService(db)
        
        # Create a mock deployment plan (in production, this would be retrieved from database)
        deployment_plan = DeploymentPlan(
            deployment_id=deployment_id,
            policies=[],
            deployment_type="update",
            validation_results={},
            deployment_status=None,
            scheduled_at=datetime.now(timezone.utc),
            rollback_plan={"policies_to_restore": [], "policies_to_deactivate": []}
        )
        
        # Execute rollback
        success = await deployment_service.rollback_deployment(deployment_plan)
        
        if success:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"message": f"Deployment {deployment_id} rolled back successfully"}
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Rollback execution failed"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rollback deployment {deployment_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rollback deployment: {str(e)}"
        )
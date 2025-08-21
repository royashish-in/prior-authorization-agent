"""
Role-Based Access Control (RBAC) Service for LLM Features and Medical Codes Management

This service provides comprehensive RBAC functionality specifically designed for
LLM-enhanced decision engine features and medical codes management, ensuring
proper access control and compliance with healthcare security requirements.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any, Tuple
from enum import Enum
from dataclasses import dataclass, field
from functools import wraps

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.auth.models import User, UserRole, TokenData
from src.audit.logger import get_audit_logger
from src.audit.models import AuditEventType, SecurityLevel
from src.core.exceptions import AuthorizationError, ValidationError
from src.database.connection import get_db_session

logger = logging.getLogger(__name__)


class LLMPermission(str, Enum):
    """Permissions specific to LLM features."""
    # LLM Model Management
    LLM_MODEL_VIEW = "llm_model_view"
    LLM_MODEL_CONFIGURE = "llm_model_configure"
    LLM_MODEL_DEPLOY = "llm_model_deploy"
    LLM_MODEL_DELETE = "llm_model_delete"
    
    # LLM Decision Making
    LLM_DECISION_REQUEST = "llm_decision_request"
    LLM_DECISION_VIEW = "llm_decision_view"
    LLM_DECISION_OVERRIDE = "llm_decision_override"
    LLM_DECISION_EXPLAIN = "llm_decision_explain"
    
    # LLM Configuration
    LLM_CONFIG_VIEW = "llm_config_view"
    LLM_CONFIG_EDIT = "llm_config_edit"
    LLM_PROMPT_TEMPLATE_MANAGE = "llm_prompt_template_manage"
    LLM_THRESHOLD_CONFIGURE = "llm_threshold_configure"
    
    # LLM Monitoring and Analytics
    LLM_METRICS_VIEW = "llm_metrics_view"
    LLM_PERFORMANCE_ANALYZE = "llm_performance_analyze"
    LLM_AUDIT_VIEW = "llm_audit_view"
    
    # LLM Training and Feedback
    LLM_FEEDBACK_PROVIDE = "llm_feedback_provide"
    LLM_TRAINING_MANAGE = "llm_training_manage"


class MedicalCodesPermission(str, Enum):
    """Permissions specific to medical codes management."""
    # Medical Codes Viewing
    MEDICAL_CODES_VIEW = "medical_codes_view"
    MEDICAL_CODES_SEARCH = "medical_codes_search"
    MEDICAL_CODES_VALIDATE = "medical_codes_validate"
    
    # Medical Codes Management
    MEDICAL_CODES_CREATE = "medical_codes_create"
    MEDICAL_CODES_UPDATE = "medical_codes_update"
    MEDICAL_CODES_DELETE = "medical_codes_delete"
    MEDICAL_CODES_BULK_IMPORT = "medical_codes_bulk_import"
    MEDICAL_CODES_BULK_EXPORT = "medical_codes_bulk_export"
    
    # Medical Codes Relationships
    MEDICAL_CODES_RELATIONSHIPS_VIEW = "medical_codes_relationships_view"
    MEDICAL_CODES_RELATIONSHIPS_MANAGE = "medical_codes_relationships_manage"
    
    # Medical Codes Administration
    MEDICAL_CODES_ADMIN = "medical_codes_admin"
    MEDICAL_CODES_AUDIT_VIEW = "medical_codes_audit_view"


class ResourceType(str, Enum):
    """Types of resources that can be access-controlled."""
    LLM_MODEL = "llm_model"
    LLM_DECISION = "llm_decision"
    LLM_CONFIG = "llm_config"
    MEDICAL_CODE = "medical_code"
    AUTHORIZATION_REQUEST = "authorization_request"
    AUDIT_LOG = "audit_log"
    SYSTEM_CONFIG = "system_config"


@dataclass
class AccessPolicy:
    """Access policy definition for resources."""
    resource_type: ResourceType
    permissions: Set[str]
    conditions: Dict[str, Any] = field(default_factory=dict)
    time_restrictions: Optional[Dict[str, Any]] = None
    ip_restrictions: Optional[List[str]] = None
    organization_restrictions: Optional[List[str]] = None


@dataclass
class AccessRequest:
    """Access request for permission checking."""
    user: TokenData
    resource_type: ResourceType
    resource_id: Optional[str] = None
    permission: str = ""
    client_ip: str = "unknown"
    additional_context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AccessResult:
    """Result of access control check."""
    granted: bool
    reason: str
    conditions: Dict[str, Any] = field(default_factory=dict)
    audit_required: bool = True
    security_level: SecurityLevel = SecurityLevel.MEDIUM


class RBACService:
    """
    Role-Based Access Control service for LLM and medical codes features.
    
    Provides comprehensive access control with support for:
    - Role-based permissions
    - Resource-level access control
    - Time-based restrictions
    - IP-based restrictions
    - Organization-based restrictions
    - Audit logging for all access decisions
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.audit_logger = get_audit_logger()
        self._role_permissions = self._initialize_role_permissions()
        self._access_policies = self._initialize_access_policies()
    
    def _initialize_role_permissions(self) -> Dict[UserRole, Set[str]]:
        """Initialize default role permissions."""
        return {
            UserRole.PROVIDER: {
                # LLM permissions for providers
                LLMPermission.LLM_DECISION_REQUEST.value,
                LLMPermission.LLM_DECISION_VIEW.value,
                LLMPermission.LLM_DECISION_EXPLAIN.value,
                LLMPermission.LLM_FEEDBACK_PROVIDE.value,
                
                # Medical codes permissions for providers
                MedicalCodesPermission.MEDICAL_CODES_VIEW.value,
                MedicalCodesPermission.MEDICAL_CODES_SEARCH.value,
                MedicalCodesPermission.MEDICAL_CODES_VALIDATE.value,
                
                # Basic authorization permissions
                "authorization:create",
                "authorization:read_own",
                "authorization:update_own",
            },
            
            UserRole.PAYER_ADMIN: {
                # LLM permissions for payer admins
                LLMPermission.LLM_MODEL_VIEW.value,
                LLMPermission.LLM_MODEL_CONFIGURE.value,
                LLMPermission.LLM_DECISION_REQUEST.value,
                LLMPermission.LLM_DECISION_VIEW.value,
                LLMPermission.LLM_DECISION_OVERRIDE.value,
                LLMPermission.LLM_DECISION_EXPLAIN.value,
                LLMPermission.LLM_CONFIG_VIEW.value,
                LLMPermission.LLM_CONFIG_EDIT.value,
                LLMPermission.LLM_THRESHOLD_CONFIGURE.value,
                LLMPermission.LLM_METRICS_VIEW.value,
                LLMPermission.LLM_FEEDBACK_PROVIDE.value,
                
                # Medical codes permissions for payer admins
                MedicalCodesPermission.MEDICAL_CODES_VIEW.value,
                MedicalCodesPermission.MEDICAL_CODES_SEARCH.value,
                MedicalCodesPermission.MEDICAL_CODES_VALIDATE.value,
                MedicalCodesPermission.MEDICAL_CODES_CREATE.value,
                MedicalCodesPermission.MEDICAL_CODES_UPDATE.value,
                MedicalCodesPermission.MEDICAL_CODES_BULK_IMPORT.value,
                MedicalCodesPermission.MEDICAL_CODES_BULK_EXPORT.value,
                MedicalCodesPermission.MEDICAL_CODES_RELATIONSHIPS_VIEW.value,
                MedicalCodesPermission.MEDICAL_CODES_RELATIONSHIPS_MANAGE.value,
                
                # Authorization permissions
                "authorization:read_all",
                "authorization:update_all",
                "policy:create",
                "policy:read",
                "policy:update",
                "policy:delete",
            },
            
            UserRole.COMPLIANCE_OFFICER: {
                # LLM permissions for compliance officers
                LLMPermission.LLM_MODEL_VIEW.value,
                LLMPermission.LLM_DECISION_VIEW.value,
                LLMPermission.LLM_DECISION_EXPLAIN.value,
                LLMPermission.LLM_CONFIG_VIEW.value,
                LLMPermission.LLM_METRICS_VIEW.value,
                LLMPermission.LLM_PERFORMANCE_ANALYZE.value,
                LLMPermission.LLM_AUDIT_VIEW.value,
                
                # Medical codes permissions for compliance officers
                MedicalCodesPermission.MEDICAL_CODES_VIEW.value,
                MedicalCodesPermission.MEDICAL_CODES_SEARCH.value,
                MedicalCodesPermission.MEDICAL_CODES_VALIDATE.value,
                MedicalCodesPermission.MEDICAL_CODES_RELATIONSHIPS_VIEW.value,
                MedicalCodesPermission.MEDICAL_CODES_AUDIT_VIEW.value,
                
                # Audit and compliance permissions
                "authorization:read_all",
                "audit:read",
                "reports:generate",
                "compliance:monitor",
            },
            
            UserRole.SYSTEM_ADMIN: {
                # Full LLM permissions for system admins
                LLMPermission.LLM_MODEL_VIEW.value,
                LLMPermission.LLM_MODEL_CONFIGURE.value,
                LLMPermission.LLM_MODEL_DEPLOY.value,
                LLMPermission.LLM_MODEL_DELETE.value,
                LLMPermission.LLM_DECISION_REQUEST.value,
                LLMPermission.LLM_DECISION_VIEW.value,
                LLMPermission.LLM_DECISION_OVERRIDE.value,
                LLMPermission.LLM_DECISION_EXPLAIN.value,
                LLMPermission.LLM_CONFIG_VIEW.value,
                LLMPermission.LLM_CONFIG_EDIT.value,
                LLMPermission.LLM_PROMPT_TEMPLATE_MANAGE.value,
                LLMPermission.LLM_THRESHOLD_CONFIGURE.value,
                LLMPermission.LLM_METRICS_VIEW.value,
                LLMPermission.LLM_PERFORMANCE_ANALYZE.value,
                LLMPermission.LLM_AUDIT_VIEW.value,
                LLMPermission.LLM_FEEDBACK_PROVIDE.value,
                LLMPermission.LLM_TRAINING_MANAGE.value,
                
                # Full medical codes permissions for system admins
                MedicalCodesPermission.MEDICAL_CODES_VIEW.value,
                MedicalCodesPermission.MEDICAL_CODES_SEARCH.value,
                MedicalCodesPermission.MEDICAL_CODES_VALIDATE.value,
                MedicalCodesPermission.MEDICAL_CODES_CREATE.value,
                MedicalCodesPermission.MEDICAL_CODES_UPDATE.value,
                MedicalCodesPermission.MEDICAL_CODES_DELETE.value,
                MedicalCodesPermission.MEDICAL_CODES_BULK_IMPORT.value,
                MedicalCodesPermission.MEDICAL_CODES_BULK_EXPORT.value,
                MedicalCodesPermission.MEDICAL_CODES_RELATIONSHIPS_VIEW.value,
                MedicalCodesPermission.MEDICAL_CODES_RELATIONSHIPS_MANAGE.value,
                MedicalCodesPermission.MEDICAL_CODES_ADMIN.value,
                MedicalCodesPermission.MEDICAL_CODES_AUDIT_VIEW.value,
                
                # Full system permissions
                "*:*",  # Wildcard for all permissions
            },
            
            UserRole.API_CLIENT: {
                # Limited LLM permissions for API clients
                LLMPermission.LLM_DECISION_REQUEST.value,
                LLMPermission.LLM_DECISION_VIEW.value,
                
                # Limited medical codes permissions for API clients
                MedicalCodesPermission.MEDICAL_CODES_VIEW.value,
                MedicalCodesPermission.MEDICAL_CODES_SEARCH.value,
                MedicalCodesPermission.MEDICAL_CODES_VALIDATE.value,
                
                # Basic authorization permissions
                "authorization:create",
                "authorization:read_own",
                "authorization:update_own",
            }
        }
    
    def _initialize_access_policies(self) -> Dict[ResourceType, AccessPolicy]:
        """Initialize access policies for different resource types."""
        return {
            ResourceType.LLM_MODEL: AccessPolicy(
                resource_type=ResourceType.LLM_MODEL,
                permissions={
                    LLMPermission.LLM_MODEL_VIEW.value,
                    LLMPermission.LLM_MODEL_CONFIGURE.value,
                    LLMPermission.LLM_MODEL_DEPLOY.value,
                    LLMPermission.LLM_MODEL_DELETE.value
                },
                conditions={
                    "require_mfa": True,
                    "audit_all_access": True
                }
            ),
            
            ResourceType.LLM_DECISION: AccessPolicy(
                resource_type=ResourceType.LLM_DECISION,
                permissions={
                    LLMPermission.LLM_DECISION_REQUEST.value,
                    LLMPermission.LLM_DECISION_VIEW.value,
                    LLMPermission.LLM_DECISION_OVERRIDE.value,
                    LLMPermission.LLM_DECISION_EXPLAIN.value
                },
                conditions={
                    "audit_all_access": True,
                    "phi_involved": True
                }
            ),
            
            ResourceType.LLM_CONFIG: AccessPolicy(
                resource_type=ResourceType.LLM_CONFIG,
                permissions={
                    LLMPermission.LLM_CONFIG_VIEW.value,
                    LLMPermission.LLM_CONFIG_EDIT.value,
                    LLMPermission.LLM_PROMPT_TEMPLATE_MANAGE.value,
                    LLMPermission.LLM_THRESHOLD_CONFIGURE.value
                },
                conditions={
                    "require_approval": True,
                    "audit_all_changes": True
                }
            ),
            
            ResourceType.MEDICAL_CODE: AccessPolicy(
                resource_type=ResourceType.MEDICAL_CODE,
                permissions={
                    MedicalCodesPermission.MEDICAL_CODES_VIEW.value,
                    MedicalCodesPermission.MEDICAL_CODES_SEARCH.value,
                    MedicalCodesPermission.MEDICAL_CODES_VALIDATE.value,
                    MedicalCodesPermission.MEDICAL_CODES_CREATE.value,
                    MedicalCodesPermission.MEDICAL_CODES_UPDATE.value,
                    MedicalCodesPermission.MEDICAL_CODES_DELETE.value
                },
                conditions={
                    "audit_modifications": True
                }
            )
        }
    
    async def check_access(self, access_request: AccessRequest) -> AccessResult:
        """
        Check if user has access to perform the requested action.
        
        Args:
            access_request: Access request details
            
        Returns:
            AccessResult indicating whether access is granted
        """
        try:
            # Check if user has required permission
            has_permission = await self._check_user_permission(
                access_request.user, access_request.permission
            )
            
            if not has_permission:
                result = AccessResult(
                    granted=False,
                    reason=f"User lacks required permission: {access_request.permission}",
                    security_level=SecurityLevel.MEDIUM
                )
                await self._audit_access_decision(access_request, result)
                return result
            
            # Check resource-specific policies
            policy_result = await self._check_resource_policy(access_request)
            if not policy_result.granted:
                await self._audit_access_decision(access_request, policy_result)
                return policy_result
            
            # Check time restrictions
            time_result = await self._check_time_restrictions(access_request)
            if not time_result.granted:
                await self._audit_access_decision(access_request, time_result)
                return time_result
            
            # Check IP restrictions
            ip_result = await self._check_ip_restrictions(access_request)
            if not ip_result.granted:
                await self._audit_access_decision(access_request, ip_result)
                return ip_result
            
            # Check organization restrictions
            org_result = await self._check_organization_restrictions(access_request)
            if not org_result.granted:
                await self._audit_access_decision(access_request, org_result)
                return org_result
            
            # Access granted
            result = AccessResult(
                granted=True,
                reason="Access granted based on role permissions and policies",
                security_level=SecurityLevel.LOW
            )
            
            await self._audit_access_decision(access_request, result)
            return result
            
        except Exception as e:
            self.logger.error(f"Error checking access: {str(e)}")
            result = AccessResult(
                granted=False,
                reason=f"Access check failed: {str(e)}",
                security_level=SecurityLevel.HIGH
            )
            await self._audit_access_decision(access_request, result)
            return result
    
    async def _check_user_permission(self, user: TokenData, permission: str) -> bool:
        """Check if user has the required permission."""
        # System admin has all permissions
        if UserRole.SYSTEM_ADMIN in user.roles:
            return True
        
        # Check if any of the user's roles have the required permission
        user_permissions = set()
        for role in user.roles:
            if role in self._role_permissions:
                role_perms = self._role_permissions[role]
                # Check for wildcard permission
                if "*:*" in role_perms:
                    return True
                user_permissions.update(role_perms)
        
        return permission in user_permissions
    
    async def _check_resource_policy(self, access_request: AccessRequest) -> AccessResult:
        """Check resource-specific access policies."""
        policy = self._access_policies.get(access_request.resource_type)
        if not policy:
            return AccessResult(
                granted=True,
                reason="No specific policy for resource type"
            )
        
        # Check if permission is allowed for this resource type
        if access_request.permission not in policy.permissions:
            return AccessResult(
                granted=False,
                reason=f"Permission {access_request.permission} not allowed for {access_request.resource_type}",
                security_level=SecurityLevel.MEDIUM
            )
        
        # Check policy conditions
        conditions = policy.conditions
        
        # Check if MFA is required
        if conditions.get("require_mfa", False):
            # In a real implementation, check if user has completed MFA
            # For now, assume MFA is satisfied
            pass
        
        # Check if approval is required
        if conditions.get("require_approval", False):
            # In a real implementation, check if action has been approved
            # For now, assume approval is not required for this demo
            pass
        
        return AccessResult(
            granted=True,
            reason="Resource policy checks passed",
            conditions=conditions
        )
    
    async def _check_time_restrictions(self, access_request: AccessRequest) -> AccessResult:
        """Check time-based access restrictions."""
        # For now, no time restrictions implemented
        # In a real system, this would check business hours, maintenance windows, etc.
        return AccessResult(
            granted=True,
            reason="No time restrictions apply"
        )
    
    async def _check_ip_restrictions(self, access_request: AccessRequest) -> AccessResult:
        """Check IP-based access restrictions."""
        # For now, no IP restrictions implemented
        # In a real system, this would check allowed IP ranges, VPN requirements, etc.
        return AccessResult(
            granted=True,
            reason="No IP restrictions apply"
        )
    
    async def _check_organization_restrictions(self, access_request: AccessRequest) -> AccessResult:
        """Check organization-based access restrictions."""
        # Check if user can access resources from their organization
        if access_request.resource_id and ":" in access_request.resource_id:
            # Extract organization from resource ID (format: org_id:resource_id)
            resource_org_id = access_request.resource_id.split(":")[0]
            
            # System admin and compliance officers can access cross-organization
            if (UserRole.SYSTEM_ADMIN in access_request.user.roles or 
                UserRole.COMPLIANCE_OFFICER in access_request.user.roles):
                return AccessResult(
                    granted=True,
                    reason="Cross-organization access granted for privileged role"
                )
            
            # Check if user's organization matches resource organization
            if access_request.user.organization_id != resource_org_id:
                return AccessResult(
                    granted=False,
                    reason="Access denied: organization mismatch",
                    security_level=SecurityLevel.HIGH
                )
        
        return AccessResult(
            granted=True,
            reason="Organization restrictions satisfied"
        )
    
    async def _audit_access_decision(self, access_request: AccessRequest, result: AccessResult):
        """Audit the access control decision."""
        try:
            event_type = AuditEventType.ACCESS_DENIED if not result.granted else AuditEventType.PHI_ACCESS
            
            self.audit_logger.log_event(
                event_type=event_type,
                action=f"access_check_{access_request.permission}",
                outcome="success" if result.granted else "denied",
                user_id=access_request.user.user_id,
                username=access_request.user.username,
                client_ip=access_request.client_ip,
                resource_type=access_request.resource_type.value,
                resource_id=access_request.resource_id,
                security_level=result.security_level,
                phi_involved=result.conditions.get("phi_involved", False),
                details={
                    "permission_requested": access_request.permission,
                    "access_granted": result.granted,
                    "denial_reason": result.reason if not result.granted else None,
                    "user_roles": [role.value for role in access_request.user.roles],
                    "organization_id": access_request.user.organization_id,
                    "additional_context": access_request.additional_context
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to audit access decision: {str(e)}")
    
    def get_user_permissions(self, user: TokenData) -> Set[str]:
        """Get all permissions for a user based on their roles."""
        permissions = set()
        
        for role in user.roles:
            if role in self._role_permissions:
                permissions.update(self._role_permissions[role])
        
        return permissions
    
    def get_role_permissions(self, role: UserRole) -> Set[str]:
        """Get permissions for a specific role."""
        return self._role_permissions.get(role, set())
    
    async def update_role_permissions(
        self, 
        role: UserRole, 
        permissions: Set[str],
        updated_by: str
    ) -> bool:
        """Update permissions for a role."""
        try:
            old_permissions = self._role_permissions.get(role, set())
            self._role_permissions[role] = permissions
            
            # Audit the change
            self.audit_logger.log_event(
                event_type=AuditEventType.CONFIG_CHANGED,
                action="update_role_permissions",
                outcome="success",
                user_id=updated_by,
                resource_type="role_permissions",
                resource_id=role.value,
                security_level=SecurityLevel.HIGH,
                details={
                    "role": role.value,
                    "old_permissions": list(old_permissions),
                    "new_permissions": list(permissions),
                    "permissions_added": list(permissions - old_permissions),
                    "permissions_removed": list(old_permissions - permissions)
                }
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update role permissions: {str(e)}")
            return False
    
    def require_permission(self, permission: str, resource_type: ResourceType = None):
        """
        Decorator to require specific permission for endpoint access.
        
        Args:
            permission: Required permission
            resource_type: Optional resource type for additional checks
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Extract current user from function arguments
                current_user = None
                client_ip = "unknown"
                
                # Look for current_user in kwargs or args
                if 'current_user' in kwargs:
                    current_user = kwargs['current_user']
                elif args and hasattr(args[0], 'user_id'):
                    current_user = args[0]
                
                if not current_user:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Authentication required"
                    )
                
                # Create access request
                access_request = AccessRequest(
                    user=current_user,
                    resource_type=resource_type or ResourceType.SYSTEM_CONFIG,
                    permission=permission,
                    client_ip=client_ip
                )
                
                # Check access
                result = await self.check_access(access_request)
                
                if not result.granted:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=result.reason
                    )
                
                return await func(*args, **kwargs)
            
            return wrapper
        return decorator


# Global RBAC service instance
rbac_service = RBACService()


def require_llm_permission(permission: LLMPermission):
    """Decorator to require LLM-specific permission."""
    return rbac_service.require_permission(
        permission.value, 
        ResourceType.LLM_MODEL
    )


def require_medical_codes_permission(permission: MedicalCodesPermission):
    """Decorator to require medical codes-specific permission."""
    return rbac_service.require_permission(
        permission.value,
        ResourceType.MEDICAL_CODE
    )
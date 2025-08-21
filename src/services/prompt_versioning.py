"""
Prompt Versioning and Rollback System

This module provides version control and rollback capabilities for prompt templates
to support continuous improvement and safe deployment of prompt changes.
"""

import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging
import os
from pathlib import Path

from .prompt_engineering import PromptTemplate, PromptType, PromptVersion

logger = logging.getLogger(__name__)


class ChangeType(str, Enum):
    """Types of prompt template changes."""
    CREATED = "created"
    UPDATED = "updated"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    DELETED = "deleted"
    ROLLED_BACK = "rolled_back"


class DeploymentStatus(str, Enum):
    """Deployment status for prompt versions."""
    DRAFT = "draft"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


@dataclass
class PromptVersion:
    """Versioned prompt template."""
    version_id: str
    template_id: str
    version_number: str  # e.g., "1.0.0", "1.1.0", "2.0.0"
    template: PromptTemplate
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "system"
    change_type: ChangeType = ChangeType.CREATED
    change_description: str = ""
    deployment_status: DeploymentStatus = DeploymentStatus.DRAFT
    
    # Performance tracking
    usage_count: int = 0
    success_rate: float = 0.0
    avg_confidence: float = 0.0
    error_count: int = 0
    
    # Metadata
    tags: List[str] = field(default_factory=list)
    notes: str = ""
    
    def get_content_hash(self) -> str:
        """Generate hash of template content."""
        content = f"{self.template.template}{self.template.description}"
        return hashlib.sha256(content.encode()).hexdigest()


@dataclass
class PromptChangeLog:
    """Change log entry for prompt modifications."""
    change_id: str
    template_id: str
    version_from: Optional[str]
    version_to: str
    change_type: ChangeType
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    user: str = "system"
    description: str = ""
    rollback_info: Optional[Dict[str, Any]] = None


class PromptVersionManager:
    """Manages versioning and rollback for prompt templates."""
    
    def __init__(self, storage_path: str = "./prompt_versions"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)
        
        # In-memory storage
        self._versions: Dict[str, List[PromptVersion]] = {}  # template_id -> versions
        self._change_log: List[PromptChangeLog] = []
        self._current_versions: Dict[str, str] = {}  # template_id -> current_version_id
        
        # Load existing versions
        self._load_versions()
    
    def _load_versions(self) -> None:
        """Load versions from storage."""
        try:
            versions_file = self.storage_path / "versions.json"
            if versions_file.exists():
                with open(versions_file, 'r') as f:
                    data = json.load(f)
                    # TODO: Implement proper deserialization
                    logger.info("Loaded prompt versions from storage")
            
            changelog_file = self.storage_path / "changelog.json"
            if changelog_file.exists():
                with open(changelog_file, 'r') as f:
                    data = json.load(f)
                    # TODO: Implement proper deserialization
                    logger.info("Loaded change log from storage")
                    
        except Exception as e:
            logger.error(f"Error loading versions: {str(e)}")
    
    def _save_versions(self) -> None:
        """Save versions to storage."""
        try:
            # TODO: Implement proper serialization
            logger.info("Saved prompt versions to storage")
        except Exception as e:
            logger.error(f"Error saving versions: {str(e)}")
    
    def create_version(
        self,
        template: PromptTemplate,
        version_number: Optional[str] = None,
        change_description: str = "",
        created_by: str = "system",
        tags: Optional[List[str]] = None
    ) -> PromptVersion:
        """Create a new version of a prompt template."""
        
        template_id = template.template_id
        
        # Generate version number if not provided
        if not version_number:
            version_number = self._generate_version_number(template_id)
        
        # Create version ID
        version_id = f"{template_id}_v{version_number}"
        
        # Create prompt version
        prompt_version = PromptVersion(
            version_id=version_id,
            template_id=template_id,
            version_number=version_number,
            template=template,
            created_by=created_by,
            change_description=change_description,
            tags=tags or []
        )
        
        # Store version
        if template_id not in self._versions:
            self._versions[template_id] = []
        
        self._versions[template_id].append(prompt_version)
        
        # Set as current version if it's the first or if explicitly requested
        if len(self._versions[template_id]) == 1:
            self._current_versions[template_id] = version_id
        
        # Log change
        change_log = PromptChangeLog(
            change_id=f"change_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            template_id=template_id,
            version_from=None,
            version_to=version_id,
            change_type=ChangeType.CREATED,
            user=created_by,
            description=change_description
        )
        self._change_log.append(change_log)
        
        self._save_versions()
        logger.info(f"Created version {version_number} for template {template_id}")
        
        return prompt_version
    
    def _generate_version_number(self, template_id: str) -> str:
        """Generate next version number for a template."""
        if template_id not in self._versions or not self._versions[template_id]:
            return "1.0.0"
        
        # Get latest version
        versions = self._versions[template_id]
        latest_version = max(versions, key=lambda v: self._parse_version(v.version_number))
        
        # Increment patch version
        major, minor, patch = self._parse_version(latest_version.version_number)
        return f"{major}.{minor}.{patch + 1}"
    
    def _parse_version(self, version_str: str) -> Tuple[int, int, int]:
        """Parse version string into major, minor, patch."""
        try:
            parts = version_str.split('.')
            major = int(parts[0]) if len(parts) > 0 else 0
            minor = int(parts[1]) if len(parts) > 1 else 0
            patch = int(parts[2]) if len(parts) > 2 else 0
            return (major, minor, patch)
        except (ValueError, IndexError):
            return (0, 0, 0)
    
    def update_template(
        self,
        template_id: str,
        updated_template: PromptTemplate,
        change_description: str = "",
        updated_by: str = "system",
        version_type: str = "patch"  # patch, minor, major
    ) -> Optional[PromptVersion]:
        """Update a template and create a new version."""
        
        if template_id not in self._versions:
            logger.error(f"Template {template_id} not found")
            return None
        
        # Get current version
        current_version_id = self._current_versions.get(template_id)
        current_version = self.get_version(template_id, current_version_id)
        
        if not current_version:
            logger.error(f"Current version not found for template {template_id}")
            return None
        
        # Generate new version number
        major, minor, patch = self._parse_version(current_version.version_number)
        
        if version_type == "major":
            new_version_number = f"{major + 1}.0.0"
        elif version_type == "minor":
            new_version_number = f"{major}.{minor + 1}.0"
        else:  # patch
            new_version_number = f"{major}.{minor}.{patch + 1}"
        
        # Create new version
        new_version = self.create_version(
            template=updated_template,
            version_number=new_version_number,
            change_description=change_description,
            created_by=updated_by
        )
        
        # Update change log
        change_log = PromptChangeLog(
            change_id=f"change_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            template_id=template_id,
            version_from=current_version_id,
            version_to=new_version.version_id,
            change_type=ChangeType.UPDATED,
            user=updated_by,
            description=change_description
        )
        self._change_log.append(change_log)
        
        return new_version
    
    def activate_version(
        self,
        template_id: str,
        version_id: str,
        activated_by: str = "system"
    ) -> bool:
        """Activate a specific version as current."""
        
        version = self.get_version(template_id, version_id)
        if not version:
            logger.error(f"Version {version_id} not found for template {template_id}")
            return False
        
        # Update current version
        old_version_id = self._current_versions.get(template_id)
        self._current_versions[template_id] = version_id
        
        # Update deployment status
        version.deployment_status = DeploymentStatus.PRODUCTION
        
        # Log change
        change_log = PromptChangeLog(
            change_id=f"change_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            template_id=template_id,
            version_from=old_version_id,
            version_to=version_id,
            change_type=ChangeType.ACTIVATED,
            user=activated_by,
            description=f"Activated version {version.version_number}"
        )
        self._change_log.append(change_log)
        
        self._save_versions()
        logger.info(f"Activated version {version.version_number} for template {template_id}")
        
        return True
    
    def rollback_to_version(
        self,
        template_id: str,
        target_version_id: str,
        rollback_reason: str = "",
        rolled_back_by: str = "system"
    ) -> bool:
        """Rollback to a previous version."""
        
        target_version = self.get_version(template_id, target_version_id)
        if not target_version:
            logger.error(f"Target version {target_version_id} not found")
            return False
        
        current_version_id = self._current_versions.get(template_id)
        
        # Activate target version
        success = self.activate_version(template_id, target_version_id, rolled_back_by)
        
        if success:
            # Log rollback
            change_log = PromptChangeLog(
                change_id=f"rollback_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                template_id=template_id,
                version_from=current_version_id,
                version_to=target_version_id,
                change_type=ChangeType.ROLLED_BACK,
                user=rolled_back_by,
                description=f"Rolled back to version {target_version.version_number}: {rollback_reason}",
                rollback_info={
                    "reason": rollback_reason,
                    "from_version": current_version_id,
                    "to_version": target_version_id
                }
            )
            self._change_log.append(change_log)
            
            logger.info(f"Rolled back template {template_id} to version {target_version.version_number}")
        
        return success
    
    def get_version(self, template_id: str, version_id: Optional[str] = None) -> Optional[PromptVersion]:
        """Get a specific version of a template."""
        if template_id not in self._versions:
            return None
        
        if version_id is None:
            # Get current version
            version_id = self._current_versions.get(template_id)
            if not version_id:
                return None
        
        versions = self._versions[template_id]
        return next((v for v in versions if v.version_id == version_id), None)
    
    def get_current_version(self, template_id: str) -> Optional[PromptVersion]:
        """Get the current active version of a template."""
        return self.get_version(template_id)
    
    def list_versions(self, template_id: str) -> List[PromptVersion]:
        """List all versions of a template."""
        return self._versions.get(template_id, [])
    
    def get_version_history(self, template_id: str) -> List[Dict[str, Any]]:
        """Get version history for a template."""
        versions = self.list_versions(template_id)
        
        history = []
        for version in sorted(versions, key=lambda v: v.created_at, reverse=True):
            history.append({
                "version_id": version.version_id,
                "version_number": version.version_number,
                "created_at": version.created_at.isoformat(),
                "created_by": version.created_by,
                "change_type": version.change_type,
                "change_description": version.change_description,
                "deployment_status": version.deployment_status,
                "usage_count": version.usage_count,
                "success_rate": version.success_rate,
                "is_current": version.version_id == self._current_versions.get(template_id)
            })
        
        return history
    
    def get_change_log(self, template_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get change log, optionally filtered by template."""
        
        changes = self._change_log
        if template_id:
            changes = [c for c in changes if c.template_id == template_id]
        
        # Sort by timestamp, most recent first
        changes = sorted(changes, key=lambda c: c.timestamp, reverse=True)
        
        log = []
        for change in changes:
            log.append({
                "change_id": change.change_id,
                "template_id": change.template_id,
                "version_from": change.version_from,
                "version_to": change.version_to,
                "change_type": change.change_type,
                "timestamp": change.timestamp.isoformat(),
                "user": change.user,
                "description": change.description,
                "rollback_info": change.rollback_info
            })
        
        return log
    
    def update_version_metrics(
        self,
        template_id: str,
        version_id: str,
        success: bool,
        confidence_score: float
    ) -> None:
        """Update performance metrics for a version."""
        
        version = self.get_version(template_id, version_id)
        if not version:
            return
        
        version.usage_count += 1
        
        # Update success rate
        if version.usage_count == 1:
            version.success_rate = 1.0 if success else 0.0
        else:
            current_successes = version.success_rate * (version.usage_count - 1)
            new_successes = current_successes + (1 if success else 0)
            version.success_rate = new_successes / version.usage_count
        
        # Update average confidence
        if version.usage_count == 1:
            version.avg_confidence = confidence_score
        else:
            total_confidence = version.avg_confidence * (version.usage_count - 1)
            version.avg_confidence = (total_confidence + confidence_score) / version.usage_count
        
        if not success:
            version.error_count += 1
    
    def compare_versions(
        self,
        template_id: str,
        version1_id: str,
        version2_id: str
    ) -> Optional[Dict[str, Any]]:
        """Compare two versions of a template."""
        
        version1 = self.get_version(template_id, version1_id)
        version2 = self.get_version(template_id, version2_id)
        
        if not version1 or not version2:
            return None
        
        return {
            "template_id": template_id,
            "version1": {
                "version_id": version1.version_id,
                "version_number": version1.version_number,
                "created_at": version1.created_at.isoformat(),
                "usage_count": version1.usage_count,
                "success_rate": version1.success_rate,
                "content_hash": version1.get_content_hash()
            },
            "version2": {
                "version_id": version2.version_id,
                "version_number": version2.version_number,
                "created_at": version2.created_at.isoformat(),
                "usage_count": version2.usage_count,
                "success_rate": version2.success_rate,
                "content_hash": version2.get_content_hash()
            },
            "content_changed": version1.get_content_hash() != version2.get_content_hash(),
            "performance_comparison": {
                "usage_diff": version2.usage_count - version1.usage_count,
                "success_rate_diff": version2.success_rate - version1.success_rate,
                "confidence_diff": version2.avg_confidence - version1.avg_confidence
            }
        }
    
    def archive_old_versions(self, template_id: str, keep_count: int = 10) -> int:
        """Archive old versions, keeping only the most recent ones."""
        
        if template_id not in self._versions:
            return 0
        
        versions = self._versions[template_id]
        if len(versions) <= keep_count:
            return 0
        
        # Sort by creation date, keep most recent
        sorted_versions = sorted(versions, key=lambda v: v.created_at, reverse=True)
        to_keep = sorted_versions[:keep_count]
        to_archive = sorted_versions[keep_count:]
        
        # Update deployment status for archived versions
        archived_count = 0
        for version in to_archive:
            if version.deployment_status != DeploymentStatus.PRODUCTION:
                version.deployment_status = DeploymentStatus.ARCHIVED
                archived_count += 1
        
        logger.info(f"Archived {archived_count} old versions for template {template_id}")
        return archived_count


# Global version manager instance
prompt_version_manager = PromptVersionManager()
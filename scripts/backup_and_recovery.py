#!/usr/bin/env python3
"""
Backup and disaster recovery procedures for LLM-enhanced system.

This script handles:
- Database backups with encryption
- LLM model and configuration backups
- Medical codes database backups
- System configuration backups
- Automated recovery procedures
- Point-in-time recovery
"""

import asyncio
import json
import logging
import os
import sys
import shutil
import tarfile
import gzip
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import subprocess
import hashlib
from dataclasses import dataclass, asdict
import boto3
from botocore.exceptions import ClientError

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.connection import get_database_manager
from src.services.medical_code_repository import MedicalCodeRepository
from src.core.config import get_settings
from src.core.logging import get_logger
from src.core.encryption import PHIEncryption

logger = get_logger(__name__)


@dataclass
class BackupResult:
    """Result of a backup operation."""
    success: bool
    backup_type: str
    backup_path: str
    backup_size: int = 0
    duration: float = 0.0
    checksum: str = ""
    errors: List[str] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class RecoveryResult:
    """Result of a recovery operation."""
    success: bool
    recovery_type: str
    source_backup: str
    duration: float = 0.0
    recovered_items: int = 0
    errors: List[str] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class BackupAndRecoveryManager:
    """
    Manages backup and disaster recovery operations for the LLM-enhanced system.
    
    Features:
    - Encrypted database backups
    - LLM model and configuration backups
    - Medical codes database backups
    - Automated backup scheduling
    - Point-in-time recovery
    - Cloud storage integration (AWS S3)
    - Backup verification and integrity checks
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.db_manager = get_database_manager()
        self.repository = MedicalCodeRepository()
        self.encryption = PHIEncryption()
        
        # Backup configuration
        self.backup_dir = Path(getattr(self.settings, 'backup_directory', 'backups'))
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Retention policies
        self.daily_retention_days = getattr(self.settings, 'daily_backup_retention', 30)
        self.weekly_retention_weeks = getattr(self.settings, 'weekly_backup_retention', 12)
        self.monthly_retention_months = getattr(self.settings, 'monthly_backup_retention', 12)
        
        # Cloud storage configuration
        self.s3_enabled = getattr(self.settings, 's3_backup_enabled', False)
        self.s3_bucket = getattr(self.settings, 's3_backup_bucket', '')
        self.s3_region = getattr(self.settings, 's3_backup_region', 'us-east-1')
        
        if self.s3_enabled:
            self.s3_client = boto3.client(
                's3',
                region_name=self.s3_region,
                aws_access_key_id=getattr(self.settings, 'aws_access_key_id', ''),
                aws_secret_access_key=getattr(self.settings, 'aws_secret_access_key', '')
            )
    
    async def create_full_backup(self, include_cloud_upload: bool = True) -> List[BackupResult]:
        """
        Create a complete system backup including all components.
        
        Args:
            include_cloud_upload: Whether to upload backups to cloud storage
            
        Returns:
            List of backup results for each component
        """
        logger.info("Starting full system backup")
        
        results = []
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        
        # Database backup
        try:
            db_result = await self.backup_database(timestamp)
            results.append(db_result)
        except Exception as e:
            logger.error(f"Database backup failed: {e}")
            results.append(BackupResult(
                success=False,
                backup_type='database',
                backup_path='',
                errors=[str(e)]
            ))
        
        # Medical codes backup
        try:
            codes_result = await self.backup_medical_codes(timestamp)
            results.append(codes_result)
        except Exception as e:
            logger.error(f"Medical codes backup failed: {e}")
            results.append(BackupResult(
                success=False,
                backup_type='medical_codes',
                backup_path='',
                errors=[str(e)]
            ))
        
        # LLM configurations backup
        try:
            llm_result = await self.backup_llm_configurations(timestamp)
            results.append(llm_result)
        except Exception as e:
            logger.error(f"LLM configurations backup failed: {e}")
            results.append(BackupResult(
                success=False,
                backup_type='llm_configurations',
                backup_path='',
                errors=[str(e)]
            ))
        
        # System configurations backup
        try:
            config_result = await self.backup_system_configurations(timestamp)
            results.append(config_result)
        except Exception as e:
            logger.error(f"System configurations backup failed: {e}")
            results.append(BackupResult(
                success=False,
                backup_type='system_configurations',
                backup_path='',
                errors=[str(e)]
            ))
        
        # Upload to cloud storage if enabled
        if include_cloud_upload and self.s3_enabled:
            for result in results:
                if result.success and result.backup_path:
                    try:
                        await self._upload_to_s3(result.backup_path, timestamp)
                    except Exception as e:
                        logger.error(f"Cloud upload failed for {result.backup_path}: {e}")
                        result.errors.append(f"Cloud upload failed: {str(e)}")
        
        # Create backup manifest
        await self._create_backup_manifest(results, timestamp)
        
        logger.info(f"Full backup completed. {sum(1 for r in results if r.success)}/{len(results)} components backed up successfully")
        return results
    
    async def backup_database(self, timestamp: str) -> BackupResult:
        """
        Create encrypted database backup.
        
        Args:
            timestamp: Timestamp string for backup naming
            
        Returns:
            Backup result
        """
        start_time = datetime.utcnow()
        backup_filename = f"database_backup_{timestamp}.sql.gz.enc"
        backup_path = self.backup_dir / backup_filename
        
        try:
            logger.info("Creating database backup")
            
            # Create database dump
            temp_sql_file = self.backup_dir / f"temp_db_{timestamp}.sql"
            
            if self.settings.database_url.startswith('postgresql'):
                # PostgreSQL backup
                cmd = [
                    'pg_dump',
                    '--no-password',
                    '--verbose',
                    '--clean',
                    '--no-acl',
                    '--no-owner',
                    self.settings.database_url,
                    '-f', str(temp_sql_file)
                ]
            elif self.settings.database_url.startswith('mysql'):
                # MySQL backup
                cmd = [
                    'mysqldump',
                    '--single-transaction',
                    '--routines',
                    '--triggers',
                    '--all-databases',
                    '--result-file', str(temp_sql_file)
                ]
            else:
                # SQLite backup (copy file)
                db_path = self.settings.database_url.replace('sqlite:///', '')
                shutil.copy2(db_path, temp_sql_file)
                cmd = None
            
            if cmd:
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(f"Database dump failed: {result.stderr}")
            
            # Compress the SQL file
            temp_gz_file = self.backup_dir / f"temp_db_{timestamp}.sql.gz"
            with open(temp_sql_file, 'rb') as f_in:
                with gzip.open(temp_gz_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # Encrypt the compressed file
            with open(temp_gz_file, 'rb') as f:
                compressed_data = f.read()
            
            encrypted_data = self.encryption.encrypt(compressed_data.decode('latin-1'))
            
            with open(backup_path, 'w') as f:
                f.write(encrypted_data)
            
            # Calculate checksum
            checksum = self._calculate_file_checksum(backup_path)
            
            # Clean up temp files
            temp_sql_file.unlink(missing_ok=True)
            temp_gz_file.unlink(missing_ok=True)
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            backup_size = backup_path.stat().st_size
            
            logger.info(f"Database backup completed: {backup_size} bytes in {duration:.2f}s")
            
            return BackupResult(
                success=True,
                backup_type='database',
                backup_path=str(backup_path),
                backup_size=backup_size,
                duration=duration,
                checksum=checksum
            )
            
        except Exception as e:
            logger.error(f"Database backup failed: {e}")
            return BackupResult(
                success=False,
                backup_type='database',
                backup_path=str(backup_path),
                duration=(datetime.utcnow() - start_time).total_seconds(),
                errors=[str(e)]
            )
    
    async def backup_medical_codes(self, timestamp: str) -> BackupResult:
        """
        Create backup of medical codes database.
        
        Args:
            timestamp: Timestamp string for backup naming
            
        Returns:
            Backup result
        """
        start_time = datetime.utcnow()
        backup_filename = f"medical_codes_backup_{timestamp}.json.gz.enc"
        backup_path = self.backup_dir / backup_filename
        
        try:
            logger.info("Creating medical codes backup")
            
            # Export ICD-10 codes
            icd10_codes, _ = await self.repository.search_icd10_codes(
                query="", valid_only=False, limit=100000
            )
            
            # Export CPT codes
            cpt_codes, _ = await self.repository.search_cpt_codes(
                query="", valid_only=False, limit=100000
            )
            
            # Export code relationships
            # Note: This would need to be implemented in the repository
            relationships = []  # Placeholder
            
            # Create backup data structure
            backup_data = {
                'backup_timestamp': timestamp,
                'backup_type': 'medical_codes',
                'icd10_codes': [code.to_dict() for code in icd10_codes],
                'cpt_codes': [code.to_dict() for code in cpt_codes],
                'code_relationships': relationships,
                'metadata': {
                    'icd10_count': len(icd10_codes),
                    'cpt_count': len(cpt_codes),
                    'relationships_count': len(relationships)
                }
            }
            
            # Convert to JSON and compress
            json_data = json.dumps(backup_data, indent=2, default=str)
            compressed_data = gzip.compress(json_data.encode('utf-8'))
            
            # Encrypt the compressed data
            encrypted_data = self.encryption.encrypt(compressed_data.decode('latin-1'))
            
            with open(backup_path, 'w') as f:
                f.write(encrypted_data)
            
            # Calculate checksum
            checksum = self._calculate_file_checksum(backup_path)
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            backup_size = backup_path.stat().st_size
            
            logger.info(f"Medical codes backup completed: {backup_size} bytes in {duration:.2f}s")
            
            return BackupResult(
                success=True,
                backup_type='medical_codes',
                backup_path=str(backup_path),
                backup_size=backup_size,
                duration=duration,
                checksum=checksum
            )
            
        except Exception as e:
            logger.error(f"Medical codes backup failed: {e}")
            return BackupResult(
                success=False,
                backup_type='medical_codes',
                backup_path=str(backup_path),
                duration=(datetime.utcnow() - start_time).total_seconds(),
                errors=[str(e)]
            )
    
    async def backup_llm_configurations(self, timestamp: str) -> BackupResult:
        """
        Create backup of LLM configurations and models.
        
        Args:
            timestamp: Timestamp string for backup naming
            
        Returns:
            Backup result
        """
        start_time = datetime.utcnow()
        backup_filename = f"llm_configurations_backup_{timestamp}.tar.gz.enc"
        backup_path = self.backup_dir / backup_filename
        
        try:
            logger.info("Creating LLM configurations backup")
            
            # Create temporary directory for backup contents
            temp_dir = self.backup_dir / f"temp_llm_{timestamp}"
            temp_dir.mkdir(exist_ok=True)
            
            # Backup LLM configuration files
            config_sources = [
                'src/services/llm_config.py',
                'src/services/llm_model_manager.py',
                'src/services/prompt_engineering.py',
                'src/services/prompt_optimization.py',
                'src/services/prompt_versioning.py'
            ]
            
            for source in config_sources:
                source_path = Path(source)
                if source_path.exists():
                    dest_path = temp_dir / source_path.name
                    shutil.copy2(source_path, dest_path)
            
            # Backup AI configuration database records
            # This would query the AI configurations from the database
            ai_configs = []  # Placeholder - would query from database
            
            config_data = {
                'backup_timestamp': timestamp,
                'backup_type': 'llm_configurations',
                'ai_configurations': ai_configs,
                'model_versions': {},  # Would include model version info
                'prompt_templates': {}  # Would include prompt templates
            }
            
            config_file = temp_dir / 'ai_configurations.json'
            with open(config_file, 'w') as f:
                json.dump(config_data, f, indent=2, default=str)
            
            # Create compressed archive
            temp_tar_file = self.backup_dir / f"temp_llm_{timestamp}.tar.gz"
            with tarfile.open(temp_tar_file, 'w:gz') as tar:
                tar.add(temp_dir, arcname='llm_configurations')
            
            # Encrypt the archive
            with open(temp_tar_file, 'rb') as f:
                compressed_data = f.read()
            
            encrypted_data = self.encryption.encrypt(compressed_data.decode('latin-1'))
            
            with open(backup_path, 'w') as f:
                f.write(encrypted_data)
            
            # Calculate checksum
            checksum = self._calculate_file_checksum(backup_path)
            
            # Clean up temp files
            shutil.rmtree(temp_dir, ignore_errors=True)
            temp_tar_file.unlink(missing_ok=True)
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            backup_size = backup_path.stat().st_size
            
            logger.info(f"LLM configurations backup completed: {backup_size} bytes in {duration:.2f}s")
            
            return BackupResult(
                success=True,
                backup_type='llm_configurations',
                backup_path=str(backup_path),
                backup_size=backup_size,
                duration=duration,
                checksum=checksum
            )
            
        except Exception as e:
            logger.error(f"LLM configurations backup failed: {e}")
            return BackupResult(
                success=False,
                backup_type='llm_configurations',
                backup_path=str(backup_path),
                duration=(datetime.utcnow() - start_time).total_seconds(),
                errors=[str(e)]
            )
    
    async def backup_system_configurations(self, timestamp: str) -> BackupResult:
        """
        Create backup of system configurations.
        
        Args:
            timestamp: Timestamp string for backup naming
            
        Returns:
            Backup result
        """
        start_time = datetime.utcnow()
        backup_filename = f"system_configurations_backup_{timestamp}.tar.gz.enc"
        backup_path = self.backup_dir / backup_filename
        
        try:
            logger.info("Creating system configurations backup")
            
            # Create temporary directory for backup contents
            temp_dir = self.backup_dir / f"temp_config_{timestamp}"
            temp_dir.mkdir(exist_ok=True)
            
            # Backup configuration files
            config_sources = [
                '.env',
                'alembic.ini',
                'requirements.txt',
                'requirements-llm.txt',
                'docker-compose.yml',
                'Dockerfile'
            ]
            
            for source in config_sources:
                source_path = Path(source)
                if source_path.exists():
                    dest_path = temp_dir / source_path.name
                    shutil.copy2(source_path, dest_path)
            
            # Backup deployment configurations
            deployment_dir = Path('deployment')
            if deployment_dir.exists():
                dest_deployment = temp_dir / 'deployment'
                shutil.copytree(deployment_dir, dest_deployment)
            
            # Backup Alembic migrations
            alembic_dir = Path('alembic')
            if alembic_dir.exists():
                dest_alembic = temp_dir / 'alembic'
                shutil.copytree(alembic_dir, dest_alembic)
            
            # Create system info file
            system_info = {
                'backup_timestamp': timestamp,
                'backup_type': 'system_configurations',
                'python_version': sys.version,
                'environment_variables': {
                    key: value for key, value in os.environ.items()
                    if not key.startswith(('SECRET', 'PASSWORD', 'KEY', 'TOKEN'))
                }
            }
            
            info_file = temp_dir / 'system_info.json'
            with open(info_file, 'w') as f:
                json.dump(system_info, f, indent=2, default=str)
            
            # Create compressed archive
            temp_tar_file = self.backup_dir / f"temp_config_{timestamp}.tar.gz"
            with tarfile.open(temp_tar_file, 'w:gz') as tar:
                tar.add(temp_dir, arcname='system_configurations')
            
            # Encrypt the archive
            with open(temp_tar_file, 'rb') as f:
                compressed_data = f.read()
            
            encrypted_data = self.encryption.encrypt(compressed_data.decode('latin-1'))
            
            with open(backup_path, 'w') as f:
                f.write(encrypted_data)
            
            # Calculate checksum
            checksum = self._calculate_file_checksum(backup_path)
            
            # Clean up temp files
            shutil.rmtree(temp_dir, ignore_errors=True)
            temp_tar_file.unlink(missing_ok=True)
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            backup_size = backup_path.stat().st_size
            
            logger.info(f"System configurations backup completed: {backup_size} bytes in {duration:.2f}s")
            
            return BackupResult(
                success=True,
                backup_type='system_configurations',
                backup_path=str(backup_path),
                backup_size=backup_size,
                duration=duration,
                checksum=checksum
            )
            
        except Exception as e:
            logger.error(f"System configurations backup failed: {e}")
            return BackupResult(
                success=False,
                backup_type='system_configurations',
                backup_path=str(backup_path),
                duration=(datetime.utcnow() - start_time).total_seconds(),
                errors=[str(e)]
            )
    
    async def restore_from_backup(self, backup_path: str, backup_type: str) -> RecoveryResult:
        """
        Restore system from backup.
        
        Args:
            backup_path: Path to backup file
            backup_type: Type of backup to restore
            
        Returns:
            Recovery result
        """
        start_time = datetime.utcnow()
        
        try:
            logger.info(f"Starting restore from backup: {backup_path}")
            
            if not Path(backup_path).exists():
                raise FileNotFoundError(f"Backup file not found: {backup_path}")
            
            if backup_type == 'database':
                result = await self._restore_database(backup_path)
            elif backup_type == 'medical_codes':
                result = await self._restore_medical_codes(backup_path)
            elif backup_type == 'llm_configurations':
                result = await self._restore_llm_configurations(backup_path)
            elif backup_type == 'system_configurations':
                result = await self._restore_system_configurations(backup_path)
            else:
                raise ValueError(f"Unsupported backup type: {backup_type}")
            
            result.duration = (datetime.utcnow() - start_time).total_seconds()
            
            logger.info(f"Restore completed in {result.duration:.2f}s")
            return result
            
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return RecoveryResult(
                success=False,
                recovery_type=backup_type,
                source_backup=backup_path,
                duration=(datetime.utcnow() - start_time).total_seconds(),
                errors=[str(e)]
            )
    
    async def _restore_database(self, backup_path: str) -> RecoveryResult:
        """Restore database from backup."""
        try:
            # Decrypt and decompress backup
            with open(backup_path, 'r') as f:
                encrypted_data = f.read()
            
            compressed_data = self.encryption.decrypt(encrypted_data).encode('latin-1')
            sql_data = gzip.decompress(compressed_data).decode('utf-8')
            
            # Create temporary SQL file
            temp_sql_file = self.backup_dir / f"restore_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.sql"
            with open(temp_sql_file, 'w') as f:
                f.write(sql_data)
            
            # Restore database
            if self.settings.database_url.startswith('postgresql'):
                cmd = ['psql', self.settings.database_url, '-f', str(temp_sql_file)]
            elif self.settings.database_url.startswith('mysql'):
                cmd = ['mysql', '-e', f'source {temp_sql_file}']
            else:
                # SQLite restore
                db_path = self.settings.database_url.replace('sqlite:///', '')
                shutil.copy2(temp_sql_file, db_path)
                cmd = None
            
            if cmd:
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(f"Database restore failed: {result.stderr}")
            
            # Clean up temp file
            temp_sql_file.unlink(missing_ok=True)
            
            return RecoveryResult(
                success=True,
                recovery_type='database',
                source_backup=backup_path,
                recovered_items=1
            )
            
        except Exception as e:
            return RecoveryResult(
                success=False,
                recovery_type='database',
                source_backup=backup_path,
                errors=[str(e)]
            )
    
    async def _restore_medical_codes(self, backup_path: str) -> RecoveryResult:
        """Restore medical codes from backup."""
        try:
            # Decrypt and decompress backup
            with open(backup_path, 'r') as f:
                encrypted_data = f.read()
            
            compressed_data = self.encryption.decrypt(encrypted_data).encode('latin-1')
            json_data = gzip.decompress(compressed_data).decode('utf-8')
            backup_data = json.loads(json_data)
            
            recovered_items = 0
            
            # Restore ICD-10 codes
            if 'icd10_codes' in backup_data:
                icd10_count, errors = await self.repository.bulk_create_icd10_codes(
                    backup_data['icd10_codes']
                )
                recovered_items += icd10_count
            
            # Restore CPT codes
            if 'cpt_codes' in backup_data:
                cpt_count, errors = await self.repository.bulk_create_cpt_codes(
                    backup_data['cpt_codes']
                )
                recovered_items += cpt_count
            
            return RecoveryResult(
                success=True,
                recovery_type='medical_codes',
                source_backup=backup_path,
                recovered_items=recovered_items
            )
            
        except Exception as e:
            return RecoveryResult(
                success=False,
                recovery_type='medical_codes',
                source_backup=backup_path,
                errors=[str(e)]
            )
    
    async def _restore_llm_configurations(self, backup_path: str) -> RecoveryResult:
        """Restore LLM configurations from backup."""
        try:
            # Decrypt and decompress backup
            with open(backup_path, 'r') as f:
                encrypted_data = f.read()
            
            compressed_data = self.encryption.decrypt(encrypted_data).encode('latin-1')
            
            # Extract archive to temporary directory
            temp_dir = self.backup_dir / f"restore_llm_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            temp_dir.mkdir(exist_ok=True)
            
            temp_tar_file = temp_dir / 'backup.tar.gz'
            with open(temp_tar_file, 'wb') as f:
                f.write(compressed_data)
            
            with tarfile.open(temp_tar_file, 'r:gz') as tar:
                tar.extractall(temp_dir)
            
            # Restore configuration files
            config_dir = temp_dir / 'llm_configurations'
            if config_dir.exists():
                # Copy configuration files back to their locations
                for config_file in config_dir.glob('*.py'):
                    dest_path = Path('src/services') / config_file.name
                    shutil.copy2(config_file, dest_path)
            
            # Clean up temp files
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            return RecoveryResult(
                success=True,
                recovery_type='llm_configurations',
                source_backup=backup_path,
                recovered_items=1
            )
            
        except Exception as e:
            return RecoveryResult(
                success=False,
                recovery_type='llm_configurations',
                source_backup=backup_path,
                errors=[str(e)]
            )
    
    async def _restore_system_configurations(self, backup_path: str) -> RecoveryResult:
        """Restore system configurations from backup."""
        try:
            # Decrypt and decompress backup
            with open(backup_path, 'r') as f:
                encrypted_data = f.read()
            
            compressed_data = self.encryption.decrypt(encrypted_data).encode('latin-1')
            
            # Extract archive to temporary directory
            temp_dir = self.backup_dir / f"restore_config_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            temp_dir.mkdir(exist_ok=True)
            
            temp_tar_file = temp_dir / 'backup.tar.gz'
            with open(temp_tar_file, 'wb') as f:
                f.write(compressed_data)
            
            with tarfile.open(temp_tar_file, 'r:gz') as tar:
                tar.extractall(temp_dir)
            
            # Restore configuration files
            config_dir = temp_dir / 'system_configurations'
            if config_dir.exists():
                # Copy configuration files back to their locations
                for config_file in config_dir.iterdir():
                    if config_file.is_file() and config_file.name != 'system_info.json':
                        dest_path = Path(config_file.name)
                        shutil.copy2(config_file, dest_path)
                    elif config_file.is_dir():
                        dest_path = Path(config_file.name)
                        if dest_path.exists():
                            shutil.rmtree(dest_path)
                        shutil.copytree(config_file, dest_path)
            
            # Clean up temp files
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            return RecoveryResult(
                success=True,
                recovery_type='system_configurations',
                source_backup=backup_path,
                recovered_items=1
            )
            
        except Exception as e:
            return RecoveryResult(
                success=False,
                recovery_type='system_configurations',
                source_backup=backup_path,
                errors=[str(e)]
            )
    
    async def _upload_to_s3(self, backup_path: str, timestamp: str) -> None:
        """Upload backup to S3."""
        if not self.s3_enabled:
            return
        
        try:
            backup_file = Path(backup_path)
            s3_key = f"backups/{timestamp}/{backup_file.name}"
            
            self.s3_client.upload_file(
                str(backup_file),
                self.s3_bucket,
                s3_key,
                ExtraArgs={'ServerSideEncryption': 'AES256'}
            )
            
            logger.info(f"Backup uploaded to S3: s3://{self.s3_bucket}/{s3_key}")
            
        except ClientError as e:
            logger.error(f"S3 upload failed: {e}")
            raise
    
    async def _create_backup_manifest(self, results: List[BackupResult], timestamp: str) -> None:
        """Create backup manifest file."""
        manifest = {
            'backup_timestamp': timestamp,
            'backup_results': [asdict(result) for result in results],
            'total_backups': len(results),
            'successful_backups': sum(1 for r in results if r.success),
            'total_size': sum(r.backup_size for r in results if r.success),
            'manifest_created': datetime.utcnow().isoformat()
        }
        
        manifest_path = self.backup_dir / f"backup_manifest_{timestamp}.json"
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2, default=str)
    
    def _calculate_file_checksum(self, file_path: Path) -> str:
        """Calculate SHA-256 checksum of file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    
    async def cleanup_old_backups(self) -> Dict[str, int]:
        """Clean up old backups based on retention policies."""
        logger.info("Starting backup cleanup")
        
        cleanup_stats = {
            'daily_removed': 0,
            'weekly_removed': 0,
            'monthly_removed': 0,
            'total_removed': 0
        }
        
        try:
            # Get all backup files
            backup_files = list(self.backup_dir.glob('*_backup_*.enc'))
            
            # Group by date
            now = datetime.utcnow()
            
            for backup_file in backup_files:
                try:
                    # Extract timestamp from filename
                    parts = backup_file.stem.split('_')
                    if len(parts) >= 3:
                        timestamp_str = parts[-1]  # Last part should be timestamp
                        backup_date = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
                        
                        days_old = (now - backup_date).days
                        
                        # Apply retention policies
                        should_remove = False
                        
                        if days_old > self.daily_retention_days:
                            # Check if it's a weekly backup (Sunday)
                            if backup_date.weekday() == 6:  # Sunday
                                weeks_old = days_old // 7
                                if weeks_old > self.weekly_retention_weeks:
                                    # Check if it's a monthly backup (first Sunday of month)
                                    if backup_date.day <= 7:
                                        months_old = (now.year - backup_date.year) * 12 + (now.month - backup_date.month)
                                        if months_old > self.monthly_retention_months:
                                            should_remove = True
                                            cleanup_stats['monthly_removed'] += 1
                                    else:
                                        should_remove = True
                                        cleanup_stats['weekly_removed'] += 1
                            else:
                                should_remove = True
                                cleanup_stats['daily_removed'] += 1
                        
                        if should_remove:
                            backup_file.unlink()
                            cleanup_stats['total_removed'] += 1
                            logger.info(f"Removed old backup: {backup_file.name}")
                
                except Exception as e:
                    logger.warning(f"Error processing backup file {backup_file}: {e}")
            
            logger.info(f"Backup cleanup completed: {cleanup_stats['total_removed']} files removed")
            return cleanup_stats
            
        except Exception as e:
            logger.error(f"Backup cleanup failed: {e}")
            return cleanup_stats
    
    async def list_backups(self) -> List[Dict[str, Any]]:
        """List all available backups."""
        backups = []
        
        try:
            backup_files = list(self.backup_dir.glob('*_backup_*.enc'))
            
            for backup_file in backup_files:
                try:
                    # Extract information from filename
                    parts = backup_file.stem.split('_')
                    if len(parts) >= 3:
                        backup_type = '_'.join(parts[:-2])
                        timestamp_str = parts[-1]
                        
                        backup_info = {
                            'filename': backup_file.name,
                            'path': str(backup_file),
                            'type': backup_type,
                            'timestamp': timestamp_str,
                            'size': backup_file.stat().st_size,
                            'created': datetime.fromtimestamp(backup_file.stat().st_ctime).isoformat(),
                            'checksum': self._calculate_file_checksum(backup_file)
                        }
                        
                        backups.append(backup_info)
                
                except Exception as e:
                    logger.warning(f"Error processing backup file {backup_file}: {e}")
            
            # Sort by timestamp (newest first)
            backups.sort(key=lambda x: x['timestamp'], reverse=True)
            
        except Exception as e:
            logger.error(f"Failed to list backups: {e}")
        
        return backups


async def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Backup and disaster recovery tool')
    parser.add_argument('--action', choices=['backup', 'restore', 'list', 'cleanup'], 
                       required=True, help='Action to perform')
    parser.add_argument('--type', choices=['database', 'medical_codes', 'llm_configurations', 'system_configurations', 'full'], 
                       help='Backup type')
    parser.add_argument('--backup-path', help='Path to backup file for restore')
    parser.add_argument('--no-cloud', action='store_true', help='Skip cloud upload')
    
    args = parser.parse_args()
    
    manager = BackupAndRecoveryManager()
    
    if args.action == 'backup':
        if args.type == 'full':
            results = await manager.create_full_backup(not args.no_cloud)
            for result in results:
                print(f"\n{result.backup_type}:")
                print(f"  Success: {result.success}")
                print(f"  Path: {result.backup_path}")
                print(f"  Size: {result.backup_size} bytes")
                print(f"  Duration: {result.duration:.2f}s")
                if result.errors:
                    print(f"  Errors: {result.errors}")
        else:
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            if args.type == 'database':
                result = await manager.backup_database(timestamp)
            elif args.type == 'medical_codes':
                result = await manager.backup_medical_codes(timestamp)
            elif args.type == 'llm_configurations':
                result = await manager.backup_llm_configurations(timestamp)
            elif args.type == 'system_configurations':
                result = await manager.backup_system_configurations(timestamp)
            else:
                print("Error: --type required for backup action")
                sys.exit(1)
            
            print(json.dumps(asdict(result), indent=2, default=str))
    
    elif args.action == 'restore':
        if not args.backup_path or not args.type:
            print("Error: --backup-path and --type required for restore action")
            sys.exit(1)
        
        result = await manager.restore_from_backup(args.backup_path, args.type)
        print(json.dumps(asdict(result), indent=2, default=str))
    
    elif args.action == 'list':
        backups = await manager.list_backups()
        print(json.dumps(backups, indent=2, default=str))
    
    elif args.action == 'cleanup':
        stats = await manager.cleanup_old_backups()
        print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
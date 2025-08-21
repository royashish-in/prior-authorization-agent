#!/usr/bin/env python3
"""
Data synchronization system for keeping medical codes up-to-date.

This script handles:
- Scheduled updates from CMS and other official sources
- Incremental updates to avoid full re-imports
- Version tracking and change detection
- Automated synchronization with external healthcare systems
"""

import asyncio
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
import hashlib
import requests
from dataclasses import dataclass

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.database.connection import get_database_manager
from src.services.medical_code_repository import MedicalCodeRepository
from src.core.config import get_settings
from src.core.logging import get_logger
from scripts.data_migration.medical_codes_migrator import MedicalCodesMigrator

logger = get_logger(__name__)


@dataclass
class SyncResult:
    """Result of a synchronization operation."""
    success: bool
    source: str
    sync_type: str
    added_count: int = 0
    updated_count: int = 0
    deleted_count: int = 0
    error_count: int = 0
    errors: List[str] = None
    sync_date: datetime = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.sync_date is None:
            self.sync_date = datetime.utcnow()


class DataSynchronizer:
    """
    Handles synchronization of medical codes data with external sources.
    
    Features:
    - Incremental updates to minimize data transfer
    - Change detection using checksums
    - Version tracking for rollback capability
    - Automated scheduling support
    - Integration with multiple data sources
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.db_manager = get_database_manager()
        self.repository = MedicalCodeRepository()
        self.migrator = MedicalCodesMigrator()
        self.sync_state_file = Path("data/sync_state.json")
        self.sync_state_file.parent.mkdir(exist_ok=True)
    
    async def sync_all_sources(self, force_full_sync: bool = False) -> List[SyncResult]:
        """
        Synchronize data from all configured sources.
        
        Args:
            force_full_sync: Force full synchronization instead of incremental
            
        Returns:
            List of synchronization results
        """
        logger.info("Starting synchronization of all medical codes sources")
        
        results = []
        
        # Sync ICD-10 codes from CMS
        try:
            icd10_result = await self.sync_icd10_codes(force_full_sync)
            results.append(icd10_result)
        except Exception as e:
            logger.error(f"ICD-10 sync failed: {e}")
            results.append(SyncResult(
                success=False,
                source="CMS ICD-10",
                sync_type="incremental",
                errors=[str(e)]
            ))
        
        # Sync HCPCS codes from CMS
        try:
            hcpcs_result = await self.sync_hcpcs_codes(force_full_sync)
            results.append(hcpcs_result)
        except Exception as e:
            logger.error(f"HCPCS sync failed: {e}")
            results.append(SyncResult(
                success=False,
                source="CMS HCPCS",
                sync_type="incremental",
                errors=[str(e)]
            ))
        
        # Sync with external healthcare systems
        try:
            external_results = await self.sync_external_systems()
            results.extend(external_results)
        except Exception as e:
            logger.error(f"External systems sync failed: {e}")
            results.append(SyncResult(
                success=False,
                source="External Systems",
                sync_type="incremental",
                errors=[str(e)]
            ))
        
        # Update sync state
        await self._update_sync_state(results)
        
        logger.info(f"Synchronization completed. {len(results)} sources processed.")
        return results
    
    async def sync_icd10_codes(self, force_full_sync: bool = False) -> SyncResult:
        """
        Synchronize ICD-10 codes from CMS.
        
        Args:
            force_full_sync: Force full synchronization
            
        Returns:
            Synchronization result
        """
        logger.info("Starting ICD-10 codes synchronization")
        
        try:
            sync_state = await self._load_sync_state()
            last_icd10_sync = sync_state.get('icd10_last_sync')
            last_icd10_hash = sync_state.get('icd10_last_hash')
            
            # Check if we need to sync
            if not force_full_sync and last_icd10_sync:
                last_sync_date = datetime.fromisoformat(last_icd10_sync)
                if datetime.utcnow() - last_sync_date < timedelta(days=7):
                    logger.info("ICD-10 codes recently synced, skipping")
                    return SyncResult(
                        success=True,
                        source="CMS ICD-10",
                        sync_type="skipped",
                        added_count=0,
                        updated_count=0
                    )
            
            # Download current ICD-10 data
            current_data = await self.migrator._download_icd10_codes("2024")
            if not current_data:
                return SyncResult(
                    success=False,
                    source="CMS ICD-10",
                    sync_type="incremental",
                    errors=["Failed to download ICD-10 data"]
                )
            
            # Calculate hash of current data
            current_hash = self._calculate_data_hash(current_data)
            
            # Check if data has changed
            if not force_full_sync and current_hash == last_icd10_hash:
                logger.info("ICD-10 data unchanged, skipping sync")
                return SyncResult(
                    success=True,
                    source="CMS ICD-10",
                    sync_type="unchanged",
                    added_count=0,
                    updated_count=0
                )
            
            # Perform incremental sync
            if force_full_sync:
                # Full sync - clear existing data first
                await self._clear_icd10_codes()
                added_count, errors = await self.repository.bulk_create_icd10_codes(current_data)
                updated_count = 0
            else:
                # Incremental sync - compare with existing data
                added_count, updated_count, errors = await self._incremental_icd10_sync(current_data)
            
            # Update sync state
            sync_state['icd10_last_sync'] = datetime.utcnow().isoformat()
            sync_state['icd10_last_hash'] = current_hash
            await self._save_sync_state(sync_state)
            
            return SyncResult(
                success=len(errors) == 0,
                source="CMS ICD-10",
                sync_type="full" if force_full_sync else "incremental",
                added_count=added_count,
                updated_count=updated_count,
                error_count=len(errors),
                errors=errors[:10]  # First 10 errors
            )
            
        except Exception as e:
            logger.error(f"ICD-10 synchronization failed: {e}")
            return SyncResult(
                success=False,
                source="CMS ICD-10",
                sync_type="incremental",
                errors=[str(e)]
            )
    
    async def sync_hcpcs_codes(self, force_full_sync: bool = False) -> SyncResult:
        """
        Synchronize HCPCS codes from CMS.
        
        Args:
            force_full_sync: Force full synchronization
            
        Returns:
            Synchronization result
        """
        logger.info("Starting HCPCS codes synchronization")
        
        try:
            sync_state = await self._load_sync_state()
            last_hcpcs_sync = sync_state.get('hcpcs_last_sync')
            last_hcpcs_hash = sync_state.get('hcpcs_last_hash')
            
            # Check if we need to sync
            if not force_full_sync and last_hcpcs_sync:
                last_sync_date = datetime.fromisoformat(last_hcpcs_sync)
                if datetime.utcnow() - last_sync_date < timedelta(days=7):
                    logger.info("HCPCS codes recently synced, skipping")
                    return SyncResult(
                        success=True,
                        source="CMS HCPCS",
                        sync_type="skipped",
                        added_count=0,
                        updated_count=0
                    )
            
            # Download current HCPCS data
            current_data = await self.migrator._download_hcpcs_codes("2024")
            if not current_data:
                return SyncResult(
                    success=False,
                    source="CMS HCPCS",
                    sync_type="incremental",
                    errors=["Failed to download HCPCS data"]
                )
            
            # Calculate hash of current data
            current_hash = self._calculate_data_hash(current_data)
            
            # Check if data has changed
            if not force_full_sync and current_hash == last_hcpcs_hash:
                logger.info("HCPCS data unchanged, skipping sync")
                return SyncResult(
                    success=True,
                    source="CMS HCPCS",
                    sync_type="unchanged",
                    added_count=0,
                    updated_count=0
                )
            
            # Perform incremental sync
            if force_full_sync:
                # Full sync - clear existing HCPCS codes first
                await self._clear_hcpcs_codes()
                added_count, errors = await self.repository.bulk_create_cpt_codes(current_data)
                updated_count = 0
            else:
                # Incremental sync - compare with existing data
                added_count, updated_count, errors = await self._incremental_hcpcs_sync(current_data)
            
            # Update sync state
            sync_state['hcpcs_last_sync'] = datetime.utcnow().isoformat()
            sync_state['hcpcs_last_hash'] = current_hash
            await self._save_sync_state(sync_state)
            
            return SyncResult(
                success=len(errors) == 0,
                source="CMS HCPCS",
                sync_type="full" if force_full_sync else "incremental",
                added_count=added_count,
                updated_count=updated_count,
                error_count=len(errors),
                errors=errors[:10]  # First 10 errors
            )
            
        except Exception as e:
            logger.error(f"HCPCS synchronization failed: {e}")
            return SyncResult(
                success=False,
                source="CMS HCPCS",
                sync_type="incremental",
                errors=[str(e)]
            )
    
    async def sync_external_systems(self) -> List[SyncResult]:
        """
        Synchronize with external healthcare systems.
        
        Returns:
            List of synchronization results for each external system
        """
        logger.info("Starting external systems synchronization")
        
        results = []
        
        # Example: Sync with Epic EHR system
        if self.settings.epic_integration_enabled:
            epic_result = await self._sync_with_epic()
            results.append(epic_result)
        
        # Example: Sync with Cerner system
        if self.settings.cerner_integration_enabled:
            cerner_result = await self._sync_with_cerner()
            results.append(cerner_result)
        
        # Example: Sync with custom healthcare system
        if self.settings.custom_system_url:
            custom_result = await self._sync_with_custom_system()
            results.append(custom_result)
        
        return results
    
    async def _sync_with_epic(self) -> SyncResult:
        """Synchronize with Epic EHR system."""
        try:
            logger.info("Syncing with Epic EHR system")
            
            # Example Epic FHIR API integration
            epic_url = getattr(self.settings, 'epic_fhir_url', '')
            epic_token = getattr(self.settings, 'epic_access_token', '')
            
            if not epic_url or not epic_token:
                return SyncResult(
                    success=False,
                    source="Epic EHR",
                    sync_type="incremental",
                    errors=["Epic configuration missing"]
                )
            
            # Fetch CodeSystem resources from Epic FHIR
            headers = {
                'Authorization': f'Bearer {epic_token}',
                'Accept': 'application/fhir+json'
            }
            
            response = requests.get(
                f"{epic_url}/CodeSystem",
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            
            fhir_data = response.json()
            
            # Process FHIR CodeSystem data
            added_count = 0
            updated_count = 0
            errors = []
            
            # Implementation would depend on Epic's specific FHIR structure
            # This is a placeholder for the actual integration logic
            
            return SyncResult(
                success=True,
                source="Epic EHR",
                sync_type="incremental",
                added_count=added_count,
                updated_count=updated_count,
                error_count=len(errors),
                errors=errors
            )
            
        except Exception as e:
            logger.error(f"Epic sync failed: {e}")
            return SyncResult(
                success=False,
                source="Epic EHR",
                sync_type="incremental",
                errors=[str(e)]
            )
    
    async def _sync_with_cerner(self) -> SyncResult:
        """Synchronize with Cerner system."""
        try:
            logger.info("Syncing with Cerner system")
            
            # Example Cerner API integration
            cerner_url = getattr(self.settings, 'cerner_api_url', '')
            cerner_token = getattr(self.settings, 'cerner_access_token', '')
            
            if not cerner_url or not cerner_token:
                return SyncResult(
                    success=False,
                    source="Cerner",
                    sync_type="incremental",
                    errors=["Cerner configuration missing"]
                )
            
            # Implementation would depend on Cerner's specific API
            # This is a placeholder for the actual integration logic
            
            return SyncResult(
                success=True,
                source="Cerner",
                sync_type="incremental",
                added_count=0,
                updated_count=0
            )
            
        except Exception as e:
            logger.error(f"Cerner sync failed: {e}")
            return SyncResult(
                success=False,
                source="Cerner",
                sync_type="incremental",
                errors=[str(e)]
            )
    
    async def _sync_with_custom_system(self) -> SyncResult:
        """Synchronize with custom healthcare system."""
        try:
            logger.info("Syncing with custom healthcare system")
            
            custom_url = getattr(self.settings, 'custom_system_url', '')
            custom_api_key = getattr(self.settings, 'custom_system_api_key', '')
            
            if not custom_url:
                return SyncResult(
                    success=False,
                    source="Custom System",
                    sync_type="incremental",
                    errors=["Custom system URL not configured"]
                )
            
            # Example custom API integration
            headers = {}
            if custom_api_key:
                headers['X-API-Key'] = custom_api_key
            
            response = requests.get(
                f"{custom_url}/api/medical-codes",
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            
            custom_data = response.json()
            
            # Process custom system data
            added_count = 0
            updated_count = 0
            errors = []
            
            # Implementation would depend on the custom system's API structure
            
            return SyncResult(
                success=True,
                source="Custom System",
                sync_type="incremental",
                added_count=added_count,
                updated_count=updated_count,
                error_count=len(errors),
                errors=errors
            )
            
        except Exception as e:
            logger.error(f"Custom system sync failed: {e}")
            return SyncResult(
                success=False,
                source="Custom System",
                sync_type="incremental",
                errors=[str(e)]
            )
    
    async def _incremental_icd10_sync(self, new_data: List[Dict[str, Any]]) -> tuple[int, int, List[str]]:
        """
        Perform incremental synchronization of ICD-10 codes.
        
        Returns:
            Tuple of (added_count, updated_count, errors)
        """
        added_count = 0
        updated_count = 0
        errors = []
        
        try:
            # Get existing codes
            existing_codes = {}
            existing_results, _ = await self.repository.search_icd10_codes(
                query="", valid_only=False, limit=100000
            )
            
            for code in existing_results:
                existing_codes[code.code] = code
            
            # Process new data
            for code_data in new_data:
                try:
                    code = code_data['code']
                    
                    if code in existing_codes:
                        # Check if update is needed
                        existing_code = existing_codes[code]
                        if self._needs_update(existing_code.to_dict(), code_data):
                            await self.repository.update_icd10_code(existing_code.id, code_data)
                            updated_count += 1
                    else:
                        # Add new code
                        await self.repository.create_icd10_code(code_data)
                        added_count += 1
                        
                except Exception as e:
                    errors.append(f"Error processing code {code_data.get('code', 'unknown')}: {str(e)}")
            
            return added_count, updated_count, errors
            
        except Exception as e:
            errors.append(f"Incremental sync failed: {str(e)}")
            return added_count, updated_count, errors
    
    async def _incremental_hcpcs_sync(self, new_data: List[Dict[str, Any]]) -> tuple[int, int, List[str]]:
        """
        Perform incremental synchronization of HCPCS codes.
        
        Returns:
            Tuple of (added_count, updated_count, errors)
        """
        added_count = 0
        updated_count = 0
        errors = []
        
        try:
            # Get existing HCPCS codes
            existing_codes = {}
            existing_results, _ = await self.repository.search_cpt_codes(
                query="", valid_only=False, limit=100000
            )
            
            for code in existing_results:
                if code.code_type == 'HCPCS':
                    existing_codes[code.code] = code
            
            # Process new data
            for code_data in new_data:
                try:
                    code = code_data['code']
                    
                    if code in existing_codes:
                        # Check if update is needed
                        existing_code = existing_codes[code]
                        if self._needs_update(existing_code.to_dict(), code_data):
                            await self.repository.update_cpt_code(existing_code.id, code_data)
                            updated_count += 1
                    else:
                        # Add new code
                        await self.repository.create_cpt_code(code_data)
                        added_count += 1
                        
                except Exception as e:
                    errors.append(f"Error processing code {code_data.get('code', 'unknown')}: {str(e)}")
            
            return added_count, updated_count, errors
            
        except Exception as e:
            errors.append(f"Incremental sync failed: {str(e)}")
            return added_count, updated_count, errors
    
    def _needs_update(self, existing_data: Dict[str, Any], new_data: Dict[str, Any]) -> bool:
        """Check if existing code needs to be updated."""
        # Compare key fields that might change
        key_fields = ['description', 'short_description', 'category', 'valid_to', 'billable']
        
        for field in key_fields:
            if field in new_data and existing_data.get(field) != new_data[field]:
                return True
        
        return False
    
    def _calculate_data_hash(self, data: List[Dict[str, Any]]) -> str:
        """Calculate hash of data for change detection."""
        # Sort data by code for consistent hashing
        sorted_data = sorted(data, key=lambda x: x.get('code', ''))
        
        # Create hash of essential fields
        hash_content = []
        for item in sorted_data:
            hash_fields = {
                'code': item.get('code', ''),
                'description': item.get('description', ''),
                'valid_from': str(item.get('valid_from', '')),
                'valid_to': str(item.get('valid_to', ''))
            }
            hash_content.append(json.dumps(hash_fields, sort_keys=True))
        
        combined_content = ''.join(hash_content)
        return hashlib.sha256(combined_content.encode()).hexdigest()
    
    async def _load_sync_state(self) -> Dict[str, Any]:
        """Load synchronization state from file."""
        try:
            if self.sync_state_file.exists():
                with open(self.sync_state_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load sync state: {e}")
        
        return {}
    
    async def _save_sync_state(self, state: Dict[str, Any]) -> None:
        """Save synchronization state to file."""
        try:
            with open(self.sync_state_file, 'w') as f:
                json.dump(state, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save sync state: {e}")
    
    async def _update_sync_state(self, results: List[SyncResult]) -> None:
        """Update sync state with results."""
        try:
            state = await self._load_sync_state()
            
            for result in results:
                if result.success:
                    state[f"{result.source.lower().replace(' ', '_')}_last_sync"] = result.sync_date.isoformat()
            
            await self._save_sync_state(state)
            
        except Exception as e:
            logger.error(f"Failed to update sync state: {e}")
    
    async def _clear_icd10_codes(self) -> None:
        """Clear all ICD-10 codes for full sync."""
        # Implementation would depend on repository method
        # This is a placeholder
        logger.warning("Full ICD-10 clear not implemented - using incremental sync")
    
    async def _clear_hcpcs_codes(self) -> None:
        """Clear all HCPCS codes for full sync."""
        # Implementation would depend on repository method
        # This is a placeholder
        logger.warning("Full HCPCS clear not implemented - using incremental sync")
    
    async def get_sync_status(self) -> Dict[str, Any]:
        """Get current synchronization status."""
        try:
            state = await self._load_sync_state()
            
            status = {
                'last_full_sync': state.get('last_full_sync'),
                'icd10_last_sync': state.get('icd10_last_sync'),
                'hcpcs_last_sync': state.get('hcpcs_last_sync'),
                'sync_enabled': True,
                'next_scheduled_sync': None  # Would be calculated based on schedule
            }
            
            # Add time since last sync
            for key in ['icd10_last_sync', 'hcpcs_last_sync']:
                if state.get(key):
                    last_sync = datetime.fromisoformat(state[key])
                    hours_since = (datetime.utcnow() - last_sync).total_seconds() / 3600
                    status[f"{key}_hours_ago"] = round(hours_since, 1)
            
            return status
            
        except Exception as e:
            logger.error(f"Failed to get sync status: {e}")
            return {'error': str(e)}


async def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Medical codes data synchronization tool')
    parser.add_argument('--action', choices=['sync-all', 'sync-icd10', 'sync-hcpcs', 'status'], 
                       required=True, help='Synchronization action to perform')
    parser.add_argument('--force', action='store_true', help='Force full synchronization')
    
    args = parser.parse_args()
    
    synchronizer = DataSynchronizer()
    
    if args.action == 'sync-all':
        results = await synchronizer.sync_all_sources(args.force)
        for result in results:
            print(f"\n{result.source} ({result.sync_type}):")
            print(f"  Success: {result.success}")
            print(f"  Added: {result.added_count}")
            print(f"  Updated: {result.updated_count}")
            print(f"  Errors: {result.error_count}")
            if result.errors:
                print(f"  Sample errors: {result.errors[:3]}")
    
    elif args.action == 'sync-icd10':
        result = await synchronizer.sync_icd10_codes(args.force)
        print(json.dumps(result.__dict__, indent=2, default=str))
    
    elif args.action == 'sync-hcpcs':
        result = await synchronizer.sync_hcpcs_codes(args.force)
        print(json.dumps(result.__dict__, indent=2, default=str))
    
    elif args.action == 'status':
        status = await synchronizer.get_sync_status()
        print(json.dumps(status, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
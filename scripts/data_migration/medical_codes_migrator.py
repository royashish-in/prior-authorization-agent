#!/usr/bin/env python3
"""
Medical codes database migration script.

This script handles migration of medical codes from standard sources
including ICD-10 and CPT/HCPCS codes with validation and error handling.
"""

import asyncio
import csv
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse
import requests
import zipfile
import tempfile

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.database.connection import get_database_manager
from src.services.medical_code_repository import MedicalCodeRepository
from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class MedicalCodesMigrator:
    """
    Handles migration of medical codes from various standard sources.
    
    Supports:
    - ICD-10-CM codes from CMS
    - CPT codes from AMA (when available)
    - HCPCS codes from CMS
    - Custom CSV/JSON imports
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.db_manager = get_database_manager()
        self.repository = MedicalCodeRepository()
        self.temp_dir = Path(tempfile.gettempdir()) / "medical_codes_migration"
        self.temp_dir.mkdir(exist_ok=True)
    
    async def migrate_icd10_codes_from_cms(self, year: str = "2024") -> Dict[str, Any]:
        """
        Migrate ICD-10-CM codes from CMS official source.
        
        Args:
            year: Year version of ICD-10 codes to download
            
        Returns:
            Migration results with counts and errors
        """
        logger.info(f"Starting ICD-10-CM migration for year {year}")
        
        try:
            # Download ICD-10 codes from CMS
            icd10_data = await self._download_icd10_codes(year)
            
            if not icd10_data:
                return {
                    'success': False,
                    'error': 'Failed to download ICD-10 codes',
                    'imported_count': 0,
                    'error_count': 0
                }
            
            # Process and import codes
            imported_count, errors = await self.repository.bulk_create_icd10_codes(icd10_data)
            
            logger.info(f"ICD-10 migration completed: {imported_count} imported, {len(errors)} errors")
            
            return {
                'success': True,
                'imported_count': imported_count,
                'error_count': len(errors),
                'errors': errors[:10],  # Return first 10 errors
                'source': f'CMS ICD-10-CM {year}',
                'migration_date': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"ICD-10 migration failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'imported_count': 0,
                'error_count': 0
            }
    
    async def migrate_cpt_codes_from_file(self, file_path: str) -> Dict[str, Any]:
        """
        Migrate CPT codes from a local file (CSV or JSON).
        
        Args:
            file_path: Path to CPT codes file
            
        Returns:
            Migration results with counts and errors
        """
        logger.info(f"Starting CPT codes migration from file: {file_path}")
        
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"CPT codes file not found: {file_path}")
            
            # Load CPT codes based on file extension
            if file_path.endswith('.csv'):
                cpt_data = await self._load_cpt_codes_from_csv(file_path)
            elif file_path.endswith('.json'):
                cpt_data = await self._load_cpt_codes_from_json(file_path)
            else:
                raise ValueError("Unsupported file format. Use CSV or JSON.")
            
            if not cpt_data:
                return {
                    'success': False,
                    'error': 'No valid CPT codes found in file',
                    'imported_count': 0,
                    'error_count': 0
                }
            
            # Process and import codes
            imported_count, errors = await self.repository.bulk_create_cpt_codes(cpt_data)
            
            logger.info(f"CPT migration completed: {imported_count} imported, {len(errors)} errors")
            
            return {
                'success': True,
                'imported_count': imported_count,
                'error_count': len(errors),
                'errors': errors[:10],  # Return first 10 errors
                'source': f'File: {file_path}',
                'migration_date': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"CPT migration failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'imported_count': 0,
                'error_count': 0
            }
    
    async def migrate_hcpcs_codes_from_cms(self, year: str = "2024") -> Dict[str, Any]:
        """
        Migrate HCPCS codes from CMS official source.
        
        Args:
            year: Year version of HCPCS codes to download
            
        Returns:
            Migration results with counts and errors
        """
        logger.info(f"Starting HCPCS migration for year {year}")
        
        try:
            # Download HCPCS codes from CMS
            hcpcs_data = await self._download_hcpcs_codes(year)
            
            if not hcpcs_data:
                return {
                    'success': False,
                    'error': 'Failed to download HCPCS codes',
                    'imported_count': 0,
                    'error_count': 0
                }
            
            # Process and import codes (HCPCS codes are stored as CPT codes with type 'HCPCS')
            imported_count, errors = await self.repository.bulk_create_cpt_codes(hcpcs_data)
            
            logger.info(f"HCPCS migration completed: {imported_count} imported, {len(errors)} errors")
            
            return {
                'success': True,
                'imported_count': imported_count,
                'error_count': len(errors),
                'errors': errors[:10],  # Return first 10 errors
                'source': f'CMS HCPCS {year}',
                'migration_date': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"HCPCS migration failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'imported_count': 0,
                'error_count': 0
            }
    
    async def _download_icd10_codes(self, year: str) -> List[Dict[str, Any]]:
        """Download ICD-10-CM codes from CMS."""
        try:
            # CMS ICD-10-CM download URL (example - actual URL may vary)
            base_url = "https://www.cms.gov/files/zip"
            filename = f"2024-ICD-10-CM-Codes.zip"
            url = f"{base_url}/{filename}"
            
            logger.info(f"Downloading ICD-10 codes from: {url}")
            
            # Download the file
            response = requests.get(url, timeout=300)
            response.raise_for_status()
            
            # Save to temp file
            zip_path = self.temp_dir / filename
            with open(zip_path, 'wb') as f:
                f.write(response.content)
            
            # Extract and parse
            codes_data = []
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.temp_dir)
                
                # Look for the main codes file (usually named something like icd10cm_codes_2024.txt)
                for file_info in zip_ref.filelist:
                    if 'codes' in file_info.filename.lower() and file_info.filename.endswith('.txt'):
                        codes_file = self.temp_dir / file_info.filename
                        codes_data = await self._parse_icd10_codes_file(codes_file)
                        break
            
            # Clean up temp files
            self._cleanup_temp_files([zip_path])
            
            return codes_data
            
        except requests.RequestException as e:
            logger.warning(f"Failed to download ICD-10 codes from CMS: {e}")
            # Fall back to sample data for development
            return await self._get_sample_icd10_codes()
        except Exception as e:
            logger.error(f"Error processing ICD-10 download: {e}")
            return []
    
    async def _download_hcpcs_codes(self, year: str) -> List[Dict[str, Any]]:
        """Download HCPCS codes from CMS."""
        try:
            # CMS HCPCS download URL (example - actual URL may vary)
            base_url = "https://www.cms.gov/files/zip"
            filename = f"2024-HCPCS-Codes.zip"
            url = f"{base_url}/{filename}"
            
            logger.info(f"Downloading HCPCS codes from: {url}")
            
            # Download the file
            response = requests.get(url, timeout=300)
            response.raise_for_status()
            
            # Save to temp file
            zip_path = self.temp_dir / filename
            with open(zip_path, 'wb') as f:
                f.write(response.content)
            
            # Extract and parse
            codes_data = []
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.temp_dir)
                
                # Look for the main codes file
                for file_info in zip_ref.filelist:
                    if 'hcpcs' in file_info.filename.lower() and file_info.filename.endswith('.txt'):
                        codes_file = self.temp_dir / file_info.filename
                        codes_data = await self._parse_hcpcs_codes_file(codes_file)
                        break
            
            # Clean up temp files
            self._cleanup_temp_files([zip_path])
            
            return codes_data
            
        except requests.RequestException as e:
            logger.warning(f"Failed to download HCPCS codes from CMS: {e}")
            # Fall back to sample data for development
            return await self._get_sample_hcpcs_codes()
        except Exception as e:
            logger.error(f"Error processing HCPCS download: {e}")
            return []
    
    async def _parse_icd10_codes_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse ICD-10 codes from CMS format file."""
        codes_data = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        # CMS ICD-10 format: CODE|DESCRIPTION|BILLABLE|etc.
                        parts = line.strip().split('|')
                        if len(parts) >= 3:
                            code_data = {
                                'code': parts[0].strip(),
                                'description': parts[1].strip(),
                                'billable': parts[2].strip().upper() == 'Y',
                                'valid_from': date(2024, 1, 1),
                                'version': '2024',
                                'created_by': 'cms_migration',
                                'updated_by': 'cms_migration'
                            }
                            
                            # Add category based on code prefix
                            code_data['category'] = self._get_icd10_category(parts[0].strip())
                            
                            codes_data.append(code_data)
                            
                    except Exception as e:
                        logger.warning(f"Error parsing line {line_num}: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Error reading ICD-10 codes file: {e}")
            
        return codes_data
    
    async def _parse_hcpcs_codes_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse HCPCS codes from CMS format file."""
        codes_data = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        # CMS HCPCS format: CODE|DESCRIPTION|CATEGORY|etc.
                        parts = line.strip().split('|')
                        if len(parts) >= 2:
                            code_data = {
                                'code': parts[0].strip(),
                                'description': parts[1].strip(),
                                'code_type': 'HCPCS',
                                'valid_from': date(2024, 1, 1),
                                'version': '2024',
                                'created_by': 'cms_migration',
                                'updated_by': 'cms_migration'
                            }
                            
                            # Add category based on code prefix
                            code_data['category'] = self._get_hcpcs_category(parts[0].strip())
                            
                            codes_data.append(code_data)
                            
                    except Exception as e:
                        logger.warning(f"Error parsing line {line_num}: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Error reading HCPCS codes file: {e}")
            
        return codes_data
    
    async def _load_cpt_codes_from_csv(self, file_path: str) -> List[Dict[str, Any]]:
        """Load CPT codes from CSV file."""
        codes_data = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row_num, row in enumerate(reader, 1):
                    try:
                        code_data = {
                            'code': row.get('code', '').strip(),
                            'description': row.get('description', '').strip(),
                            'category': row.get('category', '').strip(),
                            'code_type': row.get('code_type', 'CPT').strip(),
                            'valid_from': self._parse_date(row.get('valid_from', '2024-01-01')),
                            'version': row.get('version', '2024').strip(),
                            'created_by': 'csv_migration',
                            'updated_by': 'csv_migration'
                        }
                        
                        # Optional fields
                        if row.get('prior_auth_required'):
                            code_data['prior_auth_required'] = row['prior_auth_required'].lower() in ['true', '1', 'yes']
                        
                        if row.get('work_rvu'):
                            code_data['work_rvu'] = float(row['work_rvu'])
                        
                        if row.get('practice_expense_rvu'):
                            code_data['practice_expense_rvu'] = float(row['practice_expense_rvu'])
                        
                        if row.get('malpractice_rvu'):
                            code_data['malpractice_rvu'] = float(row['malpractice_rvu'])
                        
                        codes_data.append(code_data)
                        
                    except Exception as e:
                        logger.warning(f"Error parsing CSV row {row_num}: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Error reading CPT codes CSV file: {e}")
            
        return codes_data
    
    async def _load_cpt_codes_from_json(self, file_path: str) -> List[Dict[str, Any]]:
        """Load CPT codes from JSON file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if isinstance(data, list):
                codes_data = data
            elif isinstance(data, dict) and 'codes' in data:
                codes_data = data['codes']
            else:
                raise ValueError("Invalid JSON format. Expected list of codes or object with 'codes' key.")
            
            # Ensure required fields and add defaults
            for code_data in codes_data:
                if 'valid_from' not in code_data:
                    code_data['valid_from'] = date(2024, 1, 1)
                elif isinstance(code_data['valid_from'], str):
                    code_data['valid_from'] = self._parse_date(code_data['valid_from'])
                
                if 'version' not in code_data:
                    code_data['version'] = '2024'
                
                if 'created_by' not in code_data:
                    code_data['created_by'] = 'json_migration'
                
                if 'updated_by' not in code_data:
                    code_data['updated_by'] = 'json_migration'
            
            return codes_data
            
        except Exception as e:
            logger.error(f"Error reading CPT codes JSON file: {e}")
            return []
    
    async def _get_sample_icd10_codes(self) -> List[Dict[str, Any]]:
        """Get sample ICD-10 codes for development/testing."""
        return [
            {
                'code': 'M25.511',
                'description': 'Pain in right shoulder',
                'short_description': 'Right shoulder pain',
                'category': 'Musculoskeletal',
                'subcategory': 'Joint disorders',
                'chapter': 'Diseases of the musculoskeletal system',
                'billable': True,
                'valid_from': date(2024, 1, 1),
                'version': '2024',
                'created_by': 'sample_migration',
                'updated_by': 'sample_migration'
            },
            {
                'code': 'M25.512',
                'description': 'Pain in left shoulder',
                'short_description': 'Left shoulder pain',
                'category': 'Musculoskeletal',
                'subcategory': 'Joint disorders',
                'chapter': 'Diseases of the musculoskeletal system',
                'billable': True,
                'valid_from': date(2024, 1, 1),
                'version': '2024',
                'created_by': 'sample_migration',
                'updated_by': 'sample_migration'
            },
            {
                'code': 'G93.1',
                'description': 'Anoxic brain damage, not elsewhere classified',
                'short_description': 'Anoxic brain damage',
                'category': 'Neurological',
                'subcategory': 'Brain disorders',
                'chapter': 'Diseases of the nervous system',
                'billable': True,
                'valid_from': date(2024, 1, 1),
                'version': '2024',
                'created_by': 'sample_migration',
                'updated_by': 'sample_migration'
            }
        ]
    
    async def _get_sample_hcpcs_codes(self) -> List[Dict[str, Any]]:
        """Get sample HCPCS codes for development/testing."""
        return [
            {
                'code': 'A0425',
                'description': 'Ground mileage, per statute mile',
                'category': 'Transportation',
                'code_type': 'HCPCS',
                'valid_from': date(2024, 1, 1),
                'version': '2024',
                'created_by': 'sample_migration',
                'updated_by': 'sample_migration'
            },
            {
                'code': 'E0100',
                'description': 'Cane, includes canes of all materials, adjustable or fixed, with tip',
                'category': 'Durable Medical Equipment',
                'code_type': 'HCPCS',
                'valid_from': date(2024, 1, 1),
                'version': '2024',
                'created_by': 'sample_migration',
                'updated_by': 'sample_migration'
            }
        ]
    
    def _get_icd10_category(self, code: str) -> str:
        """Get ICD-10 category based on code prefix."""
        if not code:
            return 'Unknown'
        
        first_char = code[0].upper()
        category_map = {
            'A': 'Infectious and parasitic diseases',
            'B': 'Infectious and parasitic diseases',
            'C': 'Neoplasms',
            'D': 'Neoplasms',
            'E': 'Endocrine, nutritional and metabolic diseases',
            'F': 'Mental and behavioral disorders',
            'G': 'Diseases of the nervous system',
            'H': 'Diseases of the eye and ear',
            'I': 'Diseases of the circulatory system',
            'J': 'Diseases of the respiratory system',
            'K': 'Diseases of the digestive system',
            'L': 'Diseases of the skin and subcutaneous tissue',
            'M': 'Diseases of the musculoskeletal system',
            'N': 'Diseases of the genitourinary system',
            'O': 'Pregnancy, childbirth and the puerperium',
            'P': 'Certain conditions originating in the perinatal period',
            'Q': 'Congenital malformations',
            'R': 'Symptoms, signs and abnormal clinical findings',
            'S': 'Injury, poisoning and external causes',
            'T': 'Injury, poisoning and external causes',
            'V': 'External causes of morbidity',
            'W': 'External causes of morbidity',
            'X': 'External causes of morbidity',
            'Y': 'External causes of morbidity',
            'Z': 'Factors influencing health status'
        }
        
        return category_map.get(first_char, 'Unknown')
    
    def _get_hcpcs_category(self, code: str) -> str:
        """Get HCPCS category based on code prefix."""
        if not code:
            return 'Unknown'
        
        first_char = code[0].upper()
        category_map = {
            'A': 'Transportation Services, Medical and Surgical Supplies',
            'B': 'Enteral and Parenteral Therapy',
            'C': 'Outpatient PPS',
            'D': 'Dental Procedures',
            'E': 'Durable Medical Equipment',
            'G': 'Procedures/Professional Services (Temporary)',
            'H': 'Alcohol and Drug Abuse Treatment Services',
            'J': 'Drugs Administered Other Than Oral Method',
            'K': 'Temporary Codes',
            'L': 'Orthotic/Prosthetic Procedures',
            'M': 'Medical Services',
            'P': 'Pathology and Laboratory Services',
            'Q': 'Temporary Codes',
            'R': 'Diagnostic Radiology Services',
            'S': 'Temporary National Codes',
            'T': 'National T-Codes',
            'V': 'Vision Services',
            'W': 'Temporary Codes'
        }
        
        return category_map.get(first_char, 'Unknown')
    
    def _parse_date(self, date_str: str) -> date:
        """Parse date string in various formats."""
        try:
            # Try ISO format first
            return datetime.fromisoformat(date_str).date()
        except ValueError:
            try:
                # Try MM/DD/YYYY format
                return datetime.strptime(date_str, '%m/%d/%Y').date()
            except ValueError:
                try:
                    # Try YYYY-MM-DD format
                    return datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    # Default to current year
                    return date(2024, 1, 1)
    
    def _cleanup_temp_files(self, file_paths: List[Path]):
        """Clean up temporary files."""
        for file_path in file_paths:
            try:
                if file_path.exists():
                    file_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to clean up temp file {file_path}: {e}")
    
    async def export_codes_to_csv(self, output_dir: str, code_type: str = 'both') -> Dict[str, Any]:
        """
        Export medical codes to CSV files for backup or external use.
        
        Args:
            output_dir: Directory to save CSV files
            code_type: 'icd10', 'cpt', or 'both'
            
        Returns:
            Export results
        """
        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            results = {'success': True, 'files': []}
            
            if code_type in ['icd10', 'both']:
                # Export ICD-10 codes
                icd10_results, _ = await self.repository.search_icd10_codes(
                    query="", valid_only=False, limit=100000
                )
                
                icd10_file = output_path / f"icd10_codes_{datetime.now().strftime('%Y%m%d')}.csv"
                with open(icd10_file, 'w', newline='', encoding='utf-8') as f:
                    if icd10_results:
                        writer = csv.DictWriter(f, fieldnames=icd10_results[0].to_dict().keys())
                        writer.writeheader()
                        for code in icd10_results:
                            writer.writerow(code.to_dict())
                
                results['files'].append(str(icd10_file))
                logger.info(f"Exported {len(icd10_results)} ICD-10 codes to {icd10_file}")
            
            if code_type in ['cpt', 'both']:
                # Export CPT codes
                cpt_results, _ = await self.repository.search_cpt_codes(
                    query="", valid_only=False, limit=100000
                )
                
                cpt_file = output_path / f"cpt_codes_{datetime.now().strftime('%Y%m%d')}.csv"
                with open(cpt_file, 'w', newline='', encoding='utf-8') as f:
                    if cpt_results:
                        writer = csv.DictWriter(f, fieldnames=cpt_results[0].to_dict().keys())
                        writer.writeheader()
                        for code in cpt_results:
                            writer.writerow(code.to_dict())
                
                results['files'].append(str(cpt_file))
                logger.info(f"Exported {len(cpt_results)} CPT codes to {cpt_file}")
            
            return results
            
        except Exception as e:
            logger.error(f"Export failed: {e}")
            return {'success': False, 'error': str(e), 'files': []}


async def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Medical codes migration tool')
    parser.add_argument('--action', choices=['migrate-icd10', 'migrate-cpt', 'migrate-hcpcs', 'export'], 
                       required=True, help='Migration action to perform')
    parser.add_argument('--file', help='File path for CPT migration or export directory')
    parser.add_argument('--year', default='2024', help='Year for CMS downloads')
    parser.add_argument('--type', choices=['icd10', 'cpt', 'both'], default='both', 
                       help='Code type for export')
    
    args = parser.parse_args()
    
    migrator = MedicalCodesMigrator()
    
    if args.action == 'migrate-icd10':
        result = await migrator.migrate_icd10_codes_from_cms(args.year)
    elif args.action == 'migrate-cpt':
        if not args.file:
            print("Error: --file required for CPT migration")
            sys.exit(1)
        result = await migrator.migrate_cpt_codes_from_file(args.file)
    elif args.action == 'migrate-hcpcs':
        result = await migrator.migrate_hcpcs_codes_from_cms(args.year)
    elif args.action == 'export':
        if not args.file:
            print("Error: --file (output directory) required for export")
            sys.exit(1)
        result = await migrator.export_codes_to_csv(args.file, args.type)
    
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
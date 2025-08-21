#!/usr/bin/env python3
"""
Healthcare system integration scripts.

This script handles integration with existing healthcare systems including:
- HL7 FHIR integration
- Epic EHR integration
- Cerner integration
- Custom healthcare system APIs
- Real-time data exchange
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urljoin
import base64

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.database.connection import get_database_manager
from src.services.medical_code_repository import MedicalCodeRepository
from src.core.config import get_settings
from src.core.logging import get_logger
from src.models.authorization import AuthorizationRequest, AuthorizationDecision

logger = get_logger(__name__)


@dataclass
class IntegrationConfig:
    """Configuration for healthcare system integration."""
    system_name: str
    system_type: str  # 'fhir', 'hl7', 'custom'
    base_url: str
    auth_type: str  # 'oauth2', 'basic', 'api_key'
    credentials: Dict[str, str]
    enabled: bool = True
    timeout: int = 30
    retry_attempts: int = 3
    rate_limit: int = 100  # requests per minute


@dataclass
class IntegrationResult:
    """Result of an integration operation."""
    success: bool
    system_name: str
    operation: str
    data_count: int = 0
    errors: List[str] = None
    response_time: float = 0.0
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class HealthcareSystemIntegrator:
    """
    Handles integration with various healthcare systems.
    
    Supports:
    - HL7 FHIR R4 integration
    - Epic EHR system integration
    - Cerner PowerChart integration
    - Custom healthcare system APIs
    - Real-time authorization request processing
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.db_manager = get_database_manager()
        self.repository = MedicalCodeRepository()
        self.integrations = self._load_integration_configs()
    
    def _load_integration_configs(self) -> Dict[str, IntegrationConfig]:
        """Load integration configurations from environment and config files."""
        configs = {}
        
        # Epic EHR integration
        if hasattr(self.settings, 'epic_enabled') and self.settings.epic_enabled:
            configs['epic'] = IntegrationConfig(
                system_name='Epic EHR',
                system_type='fhir',
                base_url=getattr(self.settings, 'epic_fhir_url', ''),
                auth_type='oauth2',
                credentials={
                    'client_id': getattr(self.settings, 'epic_client_id', ''),
                    'client_secret': getattr(self.settings, 'epic_client_secret', ''),
                    'access_token': getattr(self.settings, 'epic_access_token', '')
                }
            )
        
        # Cerner integration
        if hasattr(self.settings, 'cerner_enabled') and self.settings.cerner_enabled:
            configs['cerner'] = IntegrationConfig(
                system_name='Cerner PowerChart',
                system_type='fhir',
                base_url=getattr(self.settings, 'cerner_fhir_url', ''),
                auth_type='oauth2',
                credentials={
                    'client_id': getattr(self.settings, 'cerner_client_id', ''),
                    'client_secret': getattr(self.settings, 'cerner_client_secret', ''),
                    'access_token': getattr(self.settings, 'cerner_access_token', '')
                }
            )
        
        # Custom system integration
        if hasattr(self.settings, 'custom_system_enabled') and self.settings.custom_system_enabled:
            configs['custom'] = IntegrationConfig(
                system_name='Custom Healthcare System',
                system_type='custom',
                base_url=getattr(self.settings, 'custom_system_url', ''),
                auth_type='api_key',
                credentials={
                    'api_key': getattr(self.settings, 'custom_system_api_key', '')
                }
            )
        
        return configs
    
    async def test_all_integrations(self) -> List[IntegrationResult]:
        """Test connectivity to all configured healthcare systems."""
        logger.info("Testing all healthcare system integrations")
        
        results = []
        for system_name, config in self.integrations.items():
            if config.enabled:
                result = await self.test_integration(system_name)
                results.append(result)
        
        return results
    
    async def test_integration(self, system_name: str) -> IntegrationResult:
        """Test connectivity to a specific healthcare system."""
        if system_name not in self.integrations:
            return IntegrationResult(
                success=False,
                system_name=system_name,
                operation='test',
                errors=[f"Integration '{system_name}' not configured"]
            )
        
        config = self.integrations[system_name]
        start_time = datetime.utcnow()
        
        try:
            logger.info(f"Testing integration with {config.system_name}")
            
            if config.system_type == 'fhir':
                result = await self._test_fhir_integration(config)
            elif config.system_type == 'custom':
                result = await self._test_custom_integration(config)
            else:
                result = IntegrationResult(
                    success=False,
                    system_name=config.system_name,
                    operation='test',
                    errors=[f"Unsupported system type: {config.system_type}"]
                )
            
            result.response_time = (datetime.utcnow() - start_time).total_seconds()
            return result
            
        except Exception as e:
            logger.error(f"Integration test failed for {system_name}: {e}")
            return IntegrationResult(
                success=False,
                system_name=config.system_name,
                operation='test',
                errors=[str(e)],
                response_time=(datetime.utcnow() - start_time).total_seconds()
            )
    
    async def _test_fhir_integration(self, config: IntegrationConfig) -> IntegrationResult:
        """Test FHIR integration."""
        try:
            headers = await self._get_fhir_headers(config)
            
            # Test with CapabilityStatement endpoint
            response = requests.get(
                urljoin(config.base_url, 'metadata'),
                headers=headers,
                timeout=config.timeout
            )
            response.raise_for_status()
            
            capability_statement = response.json()
            
            return IntegrationResult(
                success=True,
                system_name=config.system_name,
                operation='test',
                data_count=1
            )
            
        except requests.RequestException as e:
            return IntegrationResult(
                success=False,
                system_name=config.system_name,
                operation='test',
                errors=[f"FHIR connection failed: {str(e)}"]
            )
    
    async def _test_custom_integration(self, config: IntegrationConfig) -> IntegrationResult:
        """Test custom system integration."""
        try:
            headers = await self._get_custom_headers(config)
            
            # Test with health check endpoint
            response = requests.get(
                urljoin(config.base_url, 'health'),
                headers=headers,
                timeout=config.timeout
            )
            response.raise_for_status()
            
            return IntegrationResult(
                success=True,
                system_name=config.system_name,
                operation='test',
                data_count=1
            )
            
        except requests.RequestException as e:
            return IntegrationResult(
                success=False,
                system_name=config.system_name,
                operation='test',
                errors=[f"Custom system connection failed: {str(e)}"]
            )
    
    async def send_authorization_request(
        self, 
        system_name: str, 
        auth_request: AuthorizationRequest
    ) -> IntegrationResult:
        """Send authorization request to external healthcare system."""
        if system_name not in self.integrations:
            return IntegrationResult(
                success=False,
                system_name=system_name,
                operation='send_auth_request',
                errors=[f"Integration '{system_name}' not configured"]
            )
        
        config = self.integrations[system_name]
        start_time = datetime.utcnow()
        
        try:
            logger.info(f"Sending authorization request to {config.system_name}")
            
            if config.system_type == 'fhir':
                result = await self._send_fhir_auth_request(config, auth_request)
            elif config.system_type == 'custom':
                result = await self._send_custom_auth_request(config, auth_request)
            else:
                result = IntegrationResult(
                    success=False,
                    system_name=config.system_name,
                    operation='send_auth_request',
                    errors=[f"Unsupported system type: {config.system_type}"]
                )
            
            result.response_time = (datetime.utcnow() - start_time).total_seconds()
            return result
            
        except Exception as e:
            logger.error(f"Failed to send authorization request to {system_name}: {e}")
            return IntegrationResult(
                success=False,
                system_name=config.system_name,
                operation='send_auth_request',
                errors=[str(e)],
                response_time=(datetime.utcnow() - start_time).total_seconds()
            )
    
    async def _send_fhir_auth_request(
        self, 
        config: IntegrationConfig, 
        auth_request: AuthorizationRequest
    ) -> IntegrationResult:
        """Send authorization request via FHIR."""
        try:
            headers = await self._get_fhir_headers(config)
            
            # Convert authorization request to FHIR CoverageEligibilityRequest
            fhir_request = self._convert_to_fhir_coverage_request(auth_request)
            
            response = requests.post(
                urljoin(config.base_url, 'CoverageEligibilityRequest'),
                headers=headers,
                json=fhir_request,
                timeout=config.timeout
            )
            response.raise_for_status()
            
            fhir_response = response.json()
            
            return IntegrationResult(
                success=True,
                system_name=config.system_name,
                operation='send_auth_request',
                data_count=1
            )
            
        except requests.RequestException as e:
            return IntegrationResult(
                success=False,
                system_name=config.system_name,
                operation='send_auth_request',
                errors=[f"FHIR request failed: {str(e)}"]
            )
    
    async def _send_custom_auth_request(
        self, 
        config: IntegrationConfig, 
        auth_request: AuthorizationRequest
    ) -> IntegrationResult:
        """Send authorization request to custom system."""
        try:
            headers = await self._get_custom_headers(config)
            
            # Convert authorization request to custom format
            custom_request = self._convert_to_custom_format(auth_request)
            
            response = requests.post(
                urljoin(config.base_url, 'api/authorization-requests'),
                headers=headers,
                json=custom_request,
                timeout=config.timeout
            )
            response.raise_for_status()
            
            custom_response = response.json()
            
            return IntegrationResult(
                success=True,
                system_name=config.system_name,
                operation='send_auth_request',
                data_count=1
            )
            
        except requests.RequestException as e:
            return IntegrationResult(
                success=False,
                system_name=config.system_name,
                operation='send_auth_request',
                errors=[f"Custom system request failed: {str(e)}"]
            )
    
    async def receive_authorization_response(
        self, 
        system_name: str, 
        request_id: str
    ) -> IntegrationResult:
        """Receive authorization response from external healthcare system."""
        if system_name not in self.integrations:
            return IntegrationResult(
                success=False,
                system_name=system_name,
                operation='receive_auth_response',
                errors=[f"Integration '{system_name}' not configured"]
            )
        
        config = self.integrations[system_name]
        start_time = datetime.utcnow()
        
        try:
            logger.info(f"Receiving authorization response from {config.system_name}")
            
            if config.system_type == 'fhir':
                result = await self._receive_fhir_auth_response(config, request_id)
            elif config.system_type == 'custom':
                result = await self._receive_custom_auth_response(config, request_id)
            else:
                result = IntegrationResult(
                    success=False,
                    system_name=config.system_name,
                    operation='receive_auth_response',
                    errors=[f"Unsupported system type: {config.system_type}"]
                )
            
            result.response_time = (datetime.utcnow() - start_time).total_seconds()
            return result
            
        except Exception as e:
            logger.error(f"Failed to receive authorization response from {system_name}: {e}")
            return IntegrationResult(
                success=False,
                system_name=config.system_name,
                operation='receive_auth_response',
                errors=[str(e)],
                response_time=(datetime.utcnow() - start_time).total_seconds()
            )
    
    async def _receive_fhir_auth_response(
        self, 
        config: IntegrationConfig, 
        request_id: str
    ) -> IntegrationResult:
        """Receive authorization response via FHIR."""
        try:
            headers = await self._get_fhir_headers(config)
            
            # Query for CoverageEligibilityResponse
            response = requests.get(
                urljoin(config.base_url, f'CoverageEligibilityResponse?request={request_id}'),
                headers=headers,
                timeout=config.timeout
            )
            response.raise_for_status()
            
            fhir_response = response.json()
            
            # Process FHIR response
            if 'entry' in fhir_response and fhir_response['entry']:
                return IntegrationResult(
                    success=True,
                    system_name=config.system_name,
                    operation='receive_auth_response',
                    data_count=len(fhir_response['entry'])
                )
            else:
                return IntegrationResult(
                    success=False,
                    system_name=config.system_name,
                    operation='receive_auth_response',
                    errors=["No response found for request ID"]
                )
            
        except requests.RequestException as e:
            return IntegrationResult(
                success=False,
                system_name=config.system_name,
                operation='receive_auth_response',
                errors=[f"FHIR response retrieval failed: {str(e)}"]
            )
    
    async def _receive_custom_auth_response(
        self, 
        config: IntegrationConfig, 
        request_id: str
    ) -> IntegrationResult:
        """Receive authorization response from custom system."""
        try:
            headers = await self._get_custom_headers(config)
            
            response = requests.get(
                urljoin(config.base_url, f'api/authorization-responses/{request_id}'),
                headers=headers,
                timeout=config.timeout
            )
            response.raise_for_status()
            
            custom_response = response.json()
            
            return IntegrationResult(
                success=True,
                system_name=config.system_name,
                operation='receive_auth_response',
                data_count=1
            )
            
        except requests.RequestException as e:
            return IntegrationResult(
                success=False,
                system_name=config.system_name,
                operation='receive_auth_response',
                errors=[f"Custom system response retrieval failed: {str(e)}"]
            )
    
    async def sync_medical_codes(self, system_name: str) -> IntegrationResult:
        """Synchronize medical codes with external healthcare system."""
        if system_name not in self.integrations:
            return IntegrationResult(
                success=False,
                system_name=system_name,
                operation='sync_medical_codes',
                errors=[f"Integration '{system_name}' not configured"]
            )
        
        config = self.integrations[system_name]
        start_time = datetime.utcnow()
        
        try:
            logger.info(f"Syncing medical codes with {config.system_name}")
            
            if config.system_type == 'fhir':
                result = await self._sync_fhir_medical_codes(config)
            elif config.system_type == 'custom':
                result = await self._sync_custom_medical_codes(config)
            else:
                result = IntegrationResult(
                    success=False,
                    system_name=config.system_name,
                    operation='sync_medical_codes',
                    errors=[f"Unsupported system type: {config.system_type}"]
                )
            
            result.response_time = (datetime.utcnow() - start_time).total_seconds()
            return result
            
        except Exception as e:
            logger.error(f"Failed to sync medical codes with {system_name}: {e}")
            return IntegrationResult(
                success=False,
                system_name=config.system_name,
                operation='sync_medical_codes',
                errors=[str(e)],
                response_time=(datetime.utcnow() - start_time).total_seconds()
            )
    
    async def _sync_fhir_medical_codes(self, config: IntegrationConfig) -> IntegrationResult:
        """Synchronize medical codes via FHIR."""
        try:
            headers = await self._get_fhir_headers(config)
            
            # Fetch CodeSystem resources
            response = requests.get(
                urljoin(config.base_url, 'CodeSystem'),
                headers=headers,
                timeout=config.timeout
            )
            response.raise_for_status()
            
            code_systems = response.json()
            
            # Process code systems and update local database
            updated_count = 0
            if 'entry' in code_systems:
                for entry in code_systems['entry']:
                    if 'resource' in entry:
                        # Process individual CodeSystem
                        updated_count += await self._process_fhir_code_system(entry['resource'])
            
            return IntegrationResult(
                success=True,
                system_name=config.system_name,
                operation='sync_medical_codes',
                data_count=updated_count
            )
            
        except requests.RequestException as e:
            return IntegrationResult(
                success=False,
                system_name=config.system_name,
                operation='sync_medical_codes',
                errors=[f"FHIR code sync failed: {str(e)}"]
            )
    
    async def _sync_custom_medical_codes(self, config: IntegrationConfig) -> IntegrationResult:
        """Synchronize medical codes with custom system."""
        try:
            headers = await self._get_custom_headers(config)
            
            response = requests.get(
                urljoin(config.base_url, 'api/medical-codes'),
                headers=headers,
                timeout=config.timeout
            )
            response.raise_for_status()
            
            medical_codes = response.json()
            
            # Process and update local database
            updated_count = await self._process_custom_medical_codes(medical_codes)
            
            return IntegrationResult(
                success=True,
                system_name=config.system_name,
                operation='sync_medical_codes',
                data_count=updated_count
            )
            
        except requests.RequestException as e:
            return IntegrationResult(
                success=False,
                system_name=config.system_name,
                operation='sync_medical_codes',
                errors=[f"Custom system code sync failed: {str(e)}"]
            )
    
    async def _get_fhir_headers(self, config: IntegrationConfig) -> Dict[str, str]:
        """Get headers for FHIR requests."""
        headers = {
            'Accept': 'application/fhir+json',
            'Content-Type': 'application/fhir+json'
        }
        
        if config.auth_type == 'oauth2':
            access_token = config.credentials.get('access_token')
            if access_token:
                headers['Authorization'] = f'Bearer {access_token}'
        elif config.auth_type == 'basic':
            username = config.credentials.get('username')
            password = config.credentials.get('password')
            if username and password:
                credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
                headers['Authorization'] = f'Basic {credentials}'
        
        return headers
    
    async def _get_custom_headers(self, config: IntegrationConfig) -> Dict[str, str]:
        """Get headers for custom system requests."""
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        
        if config.auth_type == 'api_key':
            api_key = config.credentials.get('api_key')
            if api_key:
                headers['X-API-Key'] = api_key
        elif config.auth_type == 'oauth2':
            access_token = config.credentials.get('access_token')
            if access_token:
                headers['Authorization'] = f'Bearer {access_token}'
        
        return headers
    
    def _convert_to_fhir_coverage_request(self, auth_request: AuthorizationRequest) -> Dict[str, Any]:
        """Convert authorization request to FHIR CoverageEligibilityRequest."""
        return {
            "resourceType": "CoverageEligibilityRequest",
            "status": "active",
            "purpose": ["auth-requirements"],
            "patient": {
                "reference": f"Patient/{auth_request.patient_info.patient_id}"
            },
            "servicedDate": auth_request.submitted_at.isoformat(),
            "item": [
                {
                    "category": {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/ex-benefitcategory",
                                "code": "medical"
                            }
                        ]
                    },
                    "productOrService": {
                        "coding": [
                            {
                                "system": "http://www.ama-assn.org/go/cpt",
                                "code": code
                            } for code in auth_request.procedure_codes
                        ]
                    },
                    "diagnosis": [
                        {
                            "diagnosisCodeableConcept": {
                                "coding": [
                                    {
                                        "system": "http://hl7.org/fhir/sid/icd-10-cm",
                                        "code": code
                                    }
                                ]
                            }
                        } for code in auth_request.diagnosis_codes
                    ]
                }
            ]
        }
    
    def _convert_to_custom_format(self, auth_request: AuthorizationRequest) -> Dict[str, Any]:
        """Convert authorization request to custom system format."""
        return {
            "request_id": auth_request.request_id,
            "patient": {
                "id": auth_request.patient_info.patient_id,
                "demographics": auth_request.patient_info.to_dict()
            },
            "provider": {
                "id": auth_request.provider_id,
                "info": auth_request.provider_info.to_dict() if auth_request.provider_info else {}
            },
            "procedure": {
                "codes": auth_request.procedure_codes,
                "type": auth_request.procedure_type,
                "urgency": auth_request.urgency_level
            },
            "diagnosis": {
                "codes": auth_request.diagnosis_codes
            },
            "clinical_notes": auth_request.clinical_notes,
            "submitted_at": auth_request.submitted_at.isoformat()
        }
    
    async def _process_fhir_code_system(self, code_system: Dict[str, Any]) -> int:
        """Process FHIR CodeSystem and update local database."""
        # Implementation would depend on specific CodeSystem structure
        # This is a placeholder for the actual processing logic
        return 0
    
    async def _process_custom_medical_codes(self, medical_codes: Dict[str, Any]) -> int:
        """Process custom medical codes and update local database."""
        # Implementation would depend on custom system structure
        # This is a placeholder for the actual processing logic
        return 0
    
    async def get_integration_status(self) -> Dict[str, Any]:
        """Get status of all healthcare system integrations."""
        status = {
            'total_integrations': len(self.integrations),
            'enabled_integrations': sum(1 for config in self.integrations.values() if config.enabled),
            'integrations': {}
        }
        
        for system_name, config in self.integrations.items():
            status['integrations'][system_name] = {
                'system_name': config.system_name,
                'system_type': config.system_type,
                'enabled': config.enabled,
                'base_url': config.base_url,
                'last_test': None,  # Would be loaded from database
                'status': 'unknown'  # Would be determined by last test result
            }
        
        return status


async def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Healthcare system integration tool')
    parser.add_argument('--action', choices=['test-all', 'test', 'sync-codes', 'status'], 
                       required=True, help='Integration action to perform')
    parser.add_argument('--system', help='Specific system name for targeted operations')
    
    args = parser.parse_args()
    
    integrator = HealthcareSystemIntegrator()
    
    if args.action == 'test-all':
        results = await integrator.test_all_integrations()
        for result in results:
            print(f"\n{result.system_name}:")
            print(f"  Success: {result.success}")
            print(f"  Response Time: {result.response_time:.2f}s")
            if result.errors:
                print(f"  Errors: {result.errors}")
    
    elif args.action == 'test':
        if not args.system:
            print("Error: --system required for test action")
            sys.exit(1)
        result = await integrator.test_integration(args.system)
        print(json.dumps(asdict(result), indent=2, default=str))
    
    elif args.action == 'sync-codes':
        if not args.system:
            print("Error: --system required for sync-codes action")
            sys.exit(1)
        result = await integrator.sync_medical_codes(args.system)
        print(json.dumps(asdict(result), indent=2, default=str))
    
    elif args.action == 'status':
        status = await integrator.get_integration_status()
        print(json.dumps(status, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
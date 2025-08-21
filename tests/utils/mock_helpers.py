"""
Mock helpers for common testing scenarios.

This module provides utilities for mocking external services, database
connections, and other dependencies used throughout the test suite.
"""

from unittest.mock import Mock, MagicMock, patch, AsyncMock
from typing import Dict, Any, List, Optional, Callable, Union
from datetime import datetime, timezone
import json
import asyncio
import httpx

from src.models.authorization import AuthorizationRequest, AuthorizationDecision
from src.models.enums import DecisionStatus, RequestStatus


class MockHelpers:
    """Utility class for creating consistent mocks across tests."""
    
    @staticmethod
    def mock_database_session():
        """Create a mock database session with common methods."""
        mock_session = MagicMock()
        mock_session.add = Mock()
        mock_session.commit = Mock()
        mock_session.rollback = Mock()
        mock_session.close = Mock()
        mock_session.query = Mock()
        mock_session.flush = Mock()
        return mock_session
    
    @staticmethod
    def mock_external_api_response(status_code: int = 200, 
                                 response_data: Optional[Dict[str, Any]] = None,
                                 headers: Optional[Dict[str, str]] = None,
                                 delay: Optional[float] = None):
        """Create a mock HTTP response for external API calls."""
        mock_response = Mock()
        mock_response.status_code = status_code
        mock_response.json.return_value = response_data or {}
        mock_response.headers = headers or {"Content-Type": "application/json"}
        mock_response.text = json.dumps(response_data) if response_data else ""
        mock_response.content = mock_response.text.encode('utf-8')
        mock_response.raise_for_status = Mock()
        
        if status_code >= 400:
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                f"HTTP {status_code}", request=Mock(), response=mock_response
            )
        
        # Add delay simulation for performance testing
        if delay:
            original_json = mock_response.json
            def delayed_json():
                import time
                time.sleep(delay)
                return original_json()
            mock_response.json = Mock(side_effect=delayed_json)
        
        return mock_response
    
    @staticmethod
    def mock_huggingface_client(responses: Optional[List[Dict[str, Any]]] = None,
                              simulate_failures: bool = False,
                              response_delay: Optional[float] = None):
        """Create a mock HuggingFace client with predefined responses."""
        mock_client = MagicMock()
        
        default_responses = [
            {
                "decision": "approved",
                "confidence": 0.95,
                "reasoning": ["Medical necessity criteria met", "Appropriate imaging request"],
                "model_id": "microsoft/DialoGPT-medium",
                "processing_time_ms": 1200.0
            }
        ]
        
        mock_responses = responses or default_responses
        
        if simulate_failures:
            # Add failure scenarios
            failure_responses = [
                httpx.TimeoutException("Request timeout"),
                httpx.ConnectError("Connection failed"),
                Exception("Model unavailable")
            ]
            mock_responses.extend(failure_responses)
        
        async def mock_generate_decision(*args, **kwargs):
            if response_delay:
                await asyncio.sleep(response_delay)
            
            if simulate_failures and len(mock_responses) > 1:
                # Randomly fail some requests
                import random
                if random.random() < 0.2:  # 20% failure rate
                    raise mock_responses[-1]
            
            return mock_responses[0] if mock_responses else default_responses[0]
        
        mock_client.generate_decision = AsyncMock(side_effect=mock_generate_decision)
        mock_client.is_available.return_value = not simulate_failures
        mock_client.get_model_info = AsyncMock(return_value={
            "model_id": "microsoft/DialoGPT-medium",
            "status": "available" if not simulate_failures else "unavailable"
        })
        
        return mock_client
    
    @staticmethod
    def mock_medical_code_validator(valid_codes: Optional[Dict[str, List[str]]] = None,
                                  simulate_failures: bool = False,
                                  response_delay: Optional[float] = None,
                                  failure_rate: float = 0.05):
        """Create a mock medical code validator with comprehensive code databases."""
        mock_validator = MagicMock()
        
        # Comprehensive valid code databases
        default_valid_codes = {
            "icd10": [
                # Musculoskeletal conditions
                "M25.511", "M25.512", "M25.519",  # Shoulder pain
                "M54.5", "M54.6", "M54.9",        # Back pain
                "M79.1", "M79.2", "M79.3",        # Muscle/soft tissue disorders
                # Neurological conditions  
                "G93.1", "G93.2", "G93.9",        # Brain disorders
                "G44.1", "G44.2", "G44.3",        # Headache disorders
                "G35", "G36.0", "G36.1",          # Demyelinating diseases
                # Injury codes
                "S43.001A", "S43.002A", "S43.009A",  # Shoulder dislocation
                "S72.001A", "S72.002A", "S72.009A",  # Femur fracture
                # Symptoms and signs
                "R50.9", "R51", "R52",             # Fever, headache, pain
                "R06.02", "R06.03", "R06.09",      # Shortness of breath
            ],
            "cpt": [
                # MRI procedures
                "70551", "70552", "70553",         # MRI Brain
                "72148", "72149", "72158",         # MRI Spine
                "73221", "73222", "73223",         # MRI Upper extremity
                "73718", "73719", "73720",         # MRI Lower extremity
                # CT procedures
                "70450", "70460", "70470",         # CT Head
                "72131", "72132", "72133",         # CT Spine
                "73200", "73201", "73202",         # CT Upper extremity
                # X-ray procedures
                "73030", "73060", "73090",         # Shoulder X-ray
                "72020", "72040", "72050",         # Spine X-ray
                # Ultrasound procedures
                "76700", "76705", "76770",         # Abdominal ultrasound
                "93306", "93307", "93308",         # Echocardiogram
            ],
            "hcpcs": [
                # Durable medical equipment
                "E0781", "E0782", "E0783",         # Ambulatory infusion pump
                "K0001", "K0002", "K0003",         # Standard wheelchair
                "L3806", "L3807", "L3808",         # Knee orthosis
                # Drugs and biologicals
                "J0135", "J0136", "J0137",         # Adalimumab injection
                "J1745", "J1746", "J1747",         # Infliximab injection
            ]
        }
        
        valid_codes_db = valid_codes or default_valid_codes
        
        # Comprehensive code descriptions
        code_descriptions = {
            # ICD-10 descriptions
            "M25.511": "Pain in right shoulder",
            "M25.512": "Pain in left shoulder", 
            "M25.519": "Pain in unspecified shoulder",
            "M54.5": "Low back pain",
            "M54.6": "Pain in thoracic spine",
            "G93.1": "Anoxic brain damage, not elsewhere classified",
            "G44.1": "Vascular headache, not elsewhere classified",
            "S43.001A": "Unspecified dislocation of right shoulder joint, initial encounter",
            "R51": "Headache",
            "R52": "Pain, unspecified",
            
            # CPT descriptions
            "70551": "Magnetic resonance (eg, proton) imaging, brain (including brain stem); without contrast material",
            "70552": "Magnetic resonance (eg, proton) imaging, brain (including brain stem); with contrast material(s)",
            "72148": "Magnetic resonance (eg, proton) imaging, spinal canal and contents, lumbar; without contrast material",
            "73221": "Magnetic resonance (eg, proton) imaging, any joint of upper extremity; without contrast material(s)",
            "70450": "Computed tomography, head or brain; without contrast material",
            "72131": "Computed tomography, lumbar spine; without contrast material",
            "73030": "Radiologic examination, shoulder; complete, minimum of 2 views",
            "76700": "Ultrasound, abdominal, real time with image documentation; complete",
            "93306": "Echocardiography, transthoracic, real-time with image documentation (2D), includes M-mode recording, when performed, complete, with spectral Doppler echocardiography, and with color flow Doppler echocardiography",
            
            # HCPCS descriptions
            "E0781": "Ambulatory infusion pump, single or multiple channels, electric or battery operated, with administrative equipment, worn by patient",
            "K0001": "Standard wheelchair",
            "L3806": "Knee orthosis, without knee joint, rigid, custom fabricated",
            "J0135": "Injection, adalimumab, 20 mg",
        }
        
        def validate_code(code: str, code_type: str) -> Dict[str, Any]:
            """Validate a medical code and return detailed results."""
            if simulate_failures:
                import random
                if random.random() < failure_rate:
                    raise Exception(f"Medical code validation service unavailable for {code_type}")
            
            # Simulate response delay
            if response_delay:
                import time
                time.sleep(response_delay)
            
            is_valid = code in valid_codes_db.get(code_type, [])
            description = code_descriptions.get(code, f"Description for {code}")
            
            result = {
                "code": code,
                "code_type": code_type,
                "is_valid": is_valid,
                "description": description,
                "effective_date": "2024-01-01",
                "status": "active" if is_valid else "invalid",
                "suggestions": []
            }
            
            # Add suggestions for invalid codes
            if not is_valid:
                # Simple fuzzy matching for suggestions
                suggestions = []
                valid_codes_list = valid_codes_db.get(code_type, [])
                
                # Find codes with similar prefixes
                for valid_code in valid_codes_list:
                    if len(code) >= 3 and len(valid_code) >= 3:
                        if valid_code.startswith(code[:3]) or code.startswith(valid_code[:3]):
                            suggestions.append({
                                "code": valid_code,
                                "description": code_descriptions.get(valid_code, f"Description for {valid_code}"),
                                "similarity_score": 0.8
                            })
                
                # Limit suggestions to top 5
                result["suggestions"] = suggestions[:5]
                result["error_message"] = f"Code {code} not found in {code_type.upper()} database"
            
            return result
        
        async def async_validate_code(code: str, code_type: str) -> Dict[str, Any]:
            """Async version of code validation."""
            if simulate_failures:
                import random
                if random.random() < failure_rate:
                    raise Exception(f"Async validation service timeout for {code}")
            
            # Simulate async delay
            delay = response_delay or 0.02
            await asyncio.sleep(delay)
            
            return validate_code(code, code_type)
        
        def batch_validate_codes(codes: List[Dict[str, str]]) -> List[Dict[str, Any]]:
            """Validate multiple codes in batch."""
            if simulate_failures:
                import random
                if random.random() < failure_rate * 0.5:  # Lower failure rate for batch
                    raise Exception("Batch validation service unavailable")
            
            results = []
            for code_info in codes:
                code = code_info.get("code", "")
                code_type = code_info.get("code_type", "").lower()
                
                try:
                    result = validate_code(code, code_type)
                    results.append(result)
                except Exception as e:
                    results.append({
                        "code": code,
                        "code_type": code_type,
                        "is_valid": False,
                        "error": str(e),
                        "suggestions": []
                    })
            
            return results
        
        def search_codes(query: str, code_type: str, limit: int = 10) -> List[Dict[str, Any]]:
            """Search for codes matching a query."""
            if simulate_failures:
                import random
                if random.random() < failure_rate:
                    raise Exception(f"Code search service unavailable for {code_type}")
            
            results = []
            valid_codes_list = valid_codes_db.get(code_type, [])
            
            # Simple search implementation
            for code in valid_codes_list:
                description = code_descriptions.get(code, f"Description for {code}")
                
                # Match code or description
                if (query.lower() in code.lower() or 
                    query.lower() in description.lower()):
                    results.append({
                        "code": code,
                        "description": description,
                        "code_type": code_type,
                        "relevance_score": 0.9 if query.lower() in code.lower() else 0.7
                    })
                
                if len(results) >= limit:
                    break
            
            return sorted(results, key=lambda x: x["relevance_score"], reverse=True)
        
        def get_code_relationships(code: str, code_type: str) -> Dict[str, Any]:
            """Get related codes and cross-references."""
            relationships = {
                "related_codes": [],
                "parent_codes": [],
                "child_codes": [],
                "cross_references": []
            }
            
            # Add some realistic relationships
            if code_type == "icd10":
                if code.startswith("M25.51"):  # Shoulder pain codes
                    relationships["related_codes"] = ["M25.512", "M25.519", "M79.1"]
                    relationships["cross_references"] = ["73221", "73222"]  # Related CPT codes
                elif code.startswith("G93"):  # Brain disorders
                    relationships["related_codes"] = ["G93.2", "G93.9"]
                    relationships["cross_references"] = ["70551", "70552", "70553"]
            
            elif code_type == "cpt":
                if code in ["70551", "70552", "70553"]:  # Brain MRI
                    relationships["related_codes"] = ["70551", "70552", "70553"]
                    relationships["cross_references"] = ["G93.1", "G44.1", "R51"]
                elif code in ["73221", "73222", "73223"]:  # Upper extremity MRI
                    relationships["related_codes"] = ["73221", "73222", "73223"]
                    relationships["cross_references"] = ["M25.511", "M25.512", "S43.001A"]
            
            return relationships
        
        # Configure mock methods
        mock_validator.validate_icd10_code = Mock(side_effect=lambda code: validate_code(code, "icd10"))
        mock_validator.validate_cpt_code = Mock(side_effect=lambda code: validate_code(code, "cpt"))
        mock_validator.validate_hcpcs_code = Mock(side_effect=lambda code: validate_code(code, "hcpcs"))
        mock_validator.validate_code = Mock(side_effect=validate_code)
        mock_validator.validate_code_async = AsyncMock(side_effect=async_validate_code)
        mock_validator.batch_validate_codes = Mock(side_effect=batch_validate_codes)
        mock_validator.search_codes = Mock(side_effect=search_codes)
        mock_validator.get_code_relationships = Mock(side_effect=get_code_relationships)
        mock_validator.get_code_description = Mock(side_effect=lambda code: code_descriptions.get(code, f"Description for {code}"))
        
        return mock_validator
    
    @staticmethod
    def mock_policy_engine(policy_decisions: Optional[Dict[str, bool]] = None):
        """Create a mock policy engine with predefined decisions."""
        mock_engine = MagicMock()
        
        default_decisions = {
            "M25.511_73221": True,  # Shoulder pain + MRI = covered
            "M54.5_72148": True,    # Back pain + MRI spine = covered
            "G93.1_70551": True,    # Brain injury + MRI brain = covered
        }
        
        decisions = policy_decisions or default_decisions
        
        def check_coverage(diagnosis_code: str, procedure_code: str) -> bool:
            key = f"{diagnosis_code}_{procedure_code}"
            return decisions.get(key, False)
        
        mock_engine.check_coverage = Mock(side_effect=check_coverage)
        mock_engine.get_policy_references = Mock(return_value=["CMS NCD 220.2"])
        
        return mock_engine
    
    @staticmethod
    def mock_notification_service():
        """Create a mock notification service."""
        mock_service = MagicMock()
        mock_service.send_notification = Mock(return_value=True)
        mock_service.send_email = Mock(return_value=True)
        mock_service.send_sms = Mock(return_value=True)
        mock_service.log_notification = Mock()
        
        return mock_service
    
    @staticmethod
    def mock_audit_logger():
        """Create a mock audit logger."""
        mock_logger = MagicMock()
        mock_logger.log_request = Mock()
        mock_logger.log_decision = Mock()
        mock_logger.log_access = Mock()
        mock_logger.log_error = Mock()
        
        return mock_logger
    
    @staticmethod
    def mock_cache_service(cache_data: Optional[Dict[str, Any]] = None):
        """Create a mock cache service with optional pre-populated data."""
        mock_cache = MagicMock()
        
        cache_store = cache_data or {}
        
        def get_cache(key: str):
            return cache_store.get(key)
        
        def set_cache(key: str, value: Any, ttl: Optional[int] = None):
            cache_store[key] = value
            return True
        
        def delete_cache(key: str):
            return cache_store.pop(key, None) is not None
        
        mock_cache.get = Mock(side_effect=get_cache)
        mock_cache.set = Mock(side_effect=set_cache)
        mock_cache.delete = Mock(side_effect=delete_cache)
        mock_cache.exists = Mock(lambda key: key in cache_store)
        mock_cache.clear = Mock(lambda: cache_store.clear())
        
        return mock_cache
    
    @staticmethod
    def mock_decision_engine(default_decision: DecisionStatus = DecisionStatus.APPROVED):
        """Create a mock decision engine with configurable default decision."""
        mock_engine = MagicMock()
        
        def make_decision(request: AuthorizationRequest) -> AuthorizationDecision:
            return AuthorizationDecision(
                decision_id=f"dec_{request.request_id.replace('req_', '')}",
                request_id=request.request_id,
                status=default_decision,
                reasoning=["Mock decision reasoning"],
                policy_references=["Mock policy reference"],
                confidence_score=0.95,
                authorization_number=f"auth_mock_{datetime.now(timezone.utc).strftime('%Y%m%d')}_123456" if default_decision == DecisionStatus.APPROVED else None
            )
        
        mock_engine.process_request = Mock(side_effect=make_decision)
        mock_engine.validate_request = Mock(return_value=True)
        mock_engine.get_policy_references = Mock(return_value=["Mock policy"])
        
        return mock_engine
    
    @staticmethod
    def create_mock_context_manager(mock_obj: Any):
        """Create a context manager wrapper for a mock object."""
        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=mock_obj)
        mock_context.__exit__ = Mock(return_value=None)
        return mock_context
    
    @staticmethod
    def mock_async_function(return_value: Any = None, side_effect: Optional[Exception] = None):
        """Create a mock async function."""
        async def async_mock(*args, **kwargs):
            if side_effect:
                raise side_effect
            return return_value
        
        return Mock(side_effect=async_mock)
    
    @staticmethod
    def setup_common_patches() -> Dict[str, Mock]:
        """Set up commonly used patches for integration tests."""
        patches = {
            'database_session': patch('src.database.connection.get_session'),
            'huggingface_client': patch('src.services.huggingface_client.HuggingFaceClient'),
            'medical_validator': patch('src.services.medical_code_validator.MedicalCodeValidator'),
            'policy_engine': patch('src.services.policy_validation.PolicyEngine'),
            'notification_service': patch('src.services.notification.NotificationService'),
            'audit_logger': patch('src.audit.logger.AuditLogger'),
            'cache_service': patch('src.services.cache.CacheService')
        }
        
        # Start all patches and configure with appropriate mocks
        started_patches = {}
        for name, patch_obj in patches.items():
            mock_obj = patch_obj.start()
            
            # Configure specific mocks based on service type
            if name == 'database_session':
                mock_obj.return_value = MockHelpers.mock_database_session()
            elif name == 'huggingface_client':
                mock_obj.return_value = MockHelpers.mock_huggingface_client()
            elif name == 'medical_validator':
                mock_obj.return_value = MockHelpers.mock_medical_code_validator()
            elif name == 'policy_engine':
                mock_obj.return_value = MockHelpers.mock_policy_engine()
            elif name == 'notification_service':
                mock_obj.return_value = MockHelpers.mock_notification_service()
            elif name == 'audit_logger':
                mock_obj.return_value = MockHelpers.mock_audit_logger()
            elif name == 'cache_service':
                mock_obj.return_value = MockHelpers.mock_cache_service()
            
            started_patches[name] = mock_obj
        
        return started_patches
    
    @staticmethod
    def cleanup_patches():
        """Clean up all active patches."""
        patch.stopall()
    
    @staticmethod
    def mock_httpx_client(responses: Optional[Dict[str, Any]] = None,
                         simulate_network_issues: bool = False,
                         response_delay: Optional[float] = None):
        """Create a comprehensive mock for httpx.AsyncClient."""
        mock_client = AsyncMock()
        
        default_responses = {
            "GET": MockHelpers.mock_external_api_response(200, {"status": "success"}),
            "POST": MockHelpers.mock_external_api_response(201, {"created": True}),
            "PUT": MockHelpers.mock_external_api_response(200, {"updated": True}),
            "DELETE": MockHelpers.mock_external_api_response(204, {})
        }
        
        configured_responses = responses or default_responses
        
        async def mock_request(method: str, url: str, **kwargs):
            if response_delay:
                await asyncio.sleep(response_delay)
            
            if simulate_network_issues:
                import random
                failure_chance = random.random()
                if failure_chance < 0.1:  # 10% timeout
                    raise httpx.TimeoutException("Request timeout")
                elif failure_chance < 0.15:  # 5% connection error
                    raise httpx.ConnectError("Connection failed")
            
            # Return appropriate response based on method
            response = configured_responses.get(method.upper(), default_responses["GET"])
            return response
        
        mock_client.request = AsyncMock(side_effect=mock_request)
        mock_client.get = AsyncMock(side_effect=lambda url, **kwargs: mock_request("GET", url, **kwargs))
        mock_client.post = AsyncMock(side_effect=lambda url, **kwargs: mock_request("POST", url, **kwargs))
        mock_client.put = AsyncMock(side_effect=lambda url, **kwargs: mock_request("PUT", url, **kwargs))
        mock_client.delete = AsyncMock(side_effect=lambda url, **kwargs: mock_request("DELETE", url, **kwargs))
        mock_client.aclose = AsyncMock()
        
        return mock_client
    
    @staticmethod
    def mock_cms_api_service(coverage_decisions: Optional[Dict[str, bool]] = None,
                           simulate_failures: bool = False,
                           response_delay: Optional[float] = None,
                           failure_rate: float = 0.1):
        """Create a mock CMS API service with realistic responses."""
        mock_service = MagicMock()
        
        # Enhanced default decisions with more realistic coverage patterns
        default_decisions = {
            "70551": True,   # MRI Brain - typically covered
            "70552": True,   # MRI Brain with contrast - typically covered
            "70553": True,   # MRI Brain with and without contrast - typically covered
            "72148": True,   # MRI Spine - typically covered
            "72149": True,   # MRI Spine with contrast - typically covered
            "73221": True,   # MRI Shoulder - typically covered
            "73222": True,   # MRI Shoulder with contrast - typically covered
            "70450": False,  # CT Head without contrast - often needs prior auth
            "70460": False,  # CT Head with contrast - often needs prior auth
            "72131": False,  # CT Spine - often needs prior auth
            "73200": False,  # CT Upper extremity - often needs prior auth
            "76700": True,   # Ultrasound abdomen - typically covered
            "93306": True,   # Echocardiogram - typically covered
        }
        
        decisions = coverage_decisions or default_decisions
        
        # Realistic NCD/LCD policy mappings
        policy_mappings = {
            "70551": {"ncd": "NCD_220.2", "lcd": "LCD_L33721", "description": "MRI Brain"},
            "70552": {"ncd": "NCD_220.2", "lcd": "LCD_L33721", "description": "MRI Brain with contrast"},
            "72148": {"ncd": "NCD_220.2", "lcd": "LCD_L33722", "description": "MRI Spine"},
            "73221": {"ncd": "NCD_220.2", "lcd": "LCD_L33723", "description": "MRI Upper extremity"},
            "70450": {"ncd": "NCD_220.1", "lcd": "LCD_L33724", "description": "CT Head"},
            "72131": {"ncd": "NCD_220.1", "lcd": "LCD_L33725", "description": "CT Spine"},
        }
        
        async def mock_check_coverage(procedure_code: str, diagnosis_code: str):
            if simulate_failures:
                import random
                if random.random() < failure_rate:
                    failure_types = [
                        Exception("CMS API service temporarily unavailable"),
                        Exception("Rate limit exceeded - too many requests"),
                        Exception("Authentication failed - invalid API key"),
                        Exception("Network timeout - request took too long"),
                        Exception("Invalid procedure code format"),
                    ]
                    raise random.choice(failure_types)
            
            # Simulate realistic API response time
            delay = response_delay or (0.05 + random.uniform(0, 0.15))  # 50-200ms
            await asyncio.sleep(delay)
            
            policy_info = policy_mappings.get(procedure_code, {
                "ncd": f"NCD_UNKNOWN_{procedure_code}",
                "lcd": f"LCD_UNKNOWN_{procedure_code}",
                "description": f"Unknown procedure {procedure_code}"
            })
            
            # Realistic coverage determination based on diagnosis-procedure combinations
            is_covered = decisions.get(procedure_code, False)
            
            # Add diagnosis-specific coverage logic
            if diagnosis_code and procedure_code:
                # Brain imaging for neurological conditions
                if procedure_code in ["70551", "70552", "70553"] and diagnosis_code.startswith("G"):
                    is_covered = True
                # Spine imaging for musculoskeletal conditions
                elif procedure_code in ["72148", "72149"] and diagnosis_code.startswith("M54"):
                    is_covered = True
                # Joint imaging for joint disorders
                elif procedure_code in ["73221", "73222"] and diagnosis_code.startswith("M25"):
                    is_covered = True
            
            return {
                "procedure_code": procedure_code,
                "diagnosis_code": diagnosis_code,
                "covered": is_covered,
                "policy_reference": policy_info["ncd"],
                "lcd_reference": policy_info["lcd"],
                "description": policy_info["description"],
                "effective_date": "2024-01-01",
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "coverage_criteria": [
                    "Medical necessity must be documented",
                    "Conservative treatment attempted when appropriate",
                    "Clinical indication supports imaging request"
                ] if is_covered else [
                    "Does not meet medical necessity criteria",
                    "Alternative imaging modalities should be considered first",
                    "Requires additional clinical documentation"
                ],
                "confidence_score": 0.95 if is_covered else 0.88
            }
        
        async def mock_get_policy_details(policy_id: str):
            if simulate_failures:
                import random
                if random.random() < failure_rate * 0.5:  # Lower failure rate for policy details
                    raise Exception(f"Policy details unavailable for {policy_id}")
            
            delay = response_delay or 0.08
            await asyncio.sleep(delay)
            
            # Realistic policy details based on common NCDs/LCDs
            policy_details = {
                "NCD_220.2": {
                    "policy_id": "NCD_220.2",
                    "title": "Magnetic Resonance Imaging (MRI)",
                    "description": "Coverage criteria for MRI procedures",
                    "coverage_criteria": [
                        "Medical necessity demonstrated through clinical presentation",
                        "Conservative treatment attempted when clinically appropriate",
                        "Imaging results will impact treatment decisions"
                    ],
                    "exclusions": [
                        "Routine screening without clinical indication",
                        "Repeat imaging without clinical change"
                    ],
                    "effective_date": "2024-01-01",
                    "revision_date": "2024-06-01"
                },
                "NCD_220.1": {
                    "policy_id": "NCD_220.1",
                    "title": "Computed Tomography (CT)",
                    "description": "Coverage criteria for CT procedures",
                    "coverage_criteria": [
                        "Clinical indication supports CT imaging",
                        "Less invasive imaging modalities considered",
                        "Results will guide clinical management"
                    ],
                    "exclusions": [
                        "Screening without clinical symptoms",
                        "Duplicate imaging within short timeframe"
                    ],
                    "effective_date": "2024-01-01",
                    "revision_date": "2024-06-01"
                }
            }
            
            return policy_details.get(policy_id, {
                "policy_id": policy_id,
                "title": f"Policy {policy_id}",
                "description": f"Coverage policy for {policy_id}",
                "coverage_criteria": ["Standard medical necessity criteria apply"],
                "exclusions": [],
                "effective_date": "2024-01-01",
                "revision_date": "2024-01-01"
            })
        
        async def mock_get_service_status():
            """Mock service health status endpoint."""
            if simulate_failures:
                import random
                if random.random() < 0.05:  # 5% chance of status check failure
                    raise Exception("Service status unavailable")
            
            return {
                "service": "CMS Guidelines API",
                "status": "operational" if not simulate_failures else "degraded",
                "version": "v2.1.0",
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "response_time_ms": (response_delay or 0.1) * 1000,
                "uptime_percentage": 99.9 if not simulate_failures else 95.2
            }
        
        mock_service.check_coverage = AsyncMock(side_effect=mock_check_coverage)
        mock_service.get_policy_details = AsyncMock(side_effect=mock_get_policy_details)
        mock_service.get_service_status = AsyncMock(side_effect=mock_get_service_status)
        
        return mock_service
    
    @staticmethod
    def mock_external_notification_service(delivery_failures: Optional[List[str]] = None):
        """Create a mock external notification service (email, SMS, etc.)."""
        mock_service = MagicMock()
        
        failed_addresses = delivery_failures or []
        
        async def mock_send_email(to_address: str, subject: str, body: str):
            if to_address in failed_addresses:
                raise Exception(f"Email delivery failed to {to_address}")
            
            await asyncio.sleep(0.05)  # Simulate send delay
            return {
                "message_id": f"msg_{datetime.now(timezone.utc).timestamp()}",
                "status": "sent",
                "recipient": to_address
            }
        
        async def mock_send_sms(phone_number: str, message: str):
            if phone_number in failed_addresses:
                raise Exception(f"SMS delivery failed to {phone_number}")
            
            await asyncio.sleep(0.03)  # Simulate send delay
            return {
                "message_id": f"sms_{datetime.now(timezone.utc).timestamp()}",
                "status": "delivered",
                "recipient": phone_number
            }
        
        mock_service.send_email = AsyncMock(side_effect=mock_send_email)
        mock_service.send_sms = AsyncMock(side_effect=mock_send_sms)
        mock_service.get_delivery_status = AsyncMock(return_value="delivered")
        
        return mock_service
    
    @staticmethod
    def mock_redis_cache(initial_data: Optional[Dict[str, Any]] = None,
                        simulate_connection_issues: bool = False):
        """Create a mock Redis cache with realistic behavior."""
        mock_redis = MagicMock()
        
        cache_store = initial_data or {}
        
        async def mock_get(key: str):
            if simulate_connection_issues:
                import random
                if random.random() < 0.05:  # 5% connection failure
                    raise Exception("Redis connection timeout")
            
            await asyncio.sleep(0.001)  # Simulate network delay
            value = cache_store.get(key)
            return json.dumps(value) if value is not None else None
        
        async def mock_set(key: str, value: Any, ex: Optional[int] = None):
            if simulate_connection_issues:
                import random
                if random.random() < 0.05:
                    raise Exception("Redis connection timeout")
            
            await asyncio.sleep(0.001)
            cache_store[key] = json.loads(value) if isinstance(value, str) else value
            return True
        
        async def mock_delete(key: str):
            await asyncio.sleep(0.001)
            return cache_store.pop(key, None) is not None
        
        mock_redis.get = AsyncMock(side_effect=mock_get)
        mock_redis.set = AsyncMock(side_effect=mock_set)
        mock_redis.delete = AsyncMock(side_effect=mock_delete)
        mock_redis.exists = AsyncMock(lambda key: key in cache_store)
        mock_redis.flushall = AsyncMock(lambda: cache_store.clear())
        mock_redis.ping = AsyncMock(return_value=not simulate_connection_issues)
        
        return mock_redis


class MockDataBuilder:
    """Builder pattern for creating complex mock data structures."""
    
    def __init__(self):
        self.data = {}
    
    def with_patient_demographics(self, **kwargs) -> 'MockDataBuilder':
        """Add patient demographics to mock data."""
        defaults = {
            "patient_id": "enc_pat_1234567",
            "age": 45,
            "gender": "MALE",
            "insurance_id": "enc_ins_1234567",
            "member_id": "enc_mem_1234567"
        }
        defaults.update(kwargs)
        self.data["patient_demographics"] = defaults
        return self
    
    def with_diagnosis_codes(self, codes: List[str]) -> 'MockDataBuilder':
        """Add diagnosis codes to mock data."""
        self.data["diagnosis_codes"] = [
            {"code": code, "description": f"Description for {code}"}
            for code in codes
        ]
        return self
    
    def with_procedure_codes(self, codes: List[str]) -> 'MockDataBuilder':
        """Add procedure codes to mock data."""
        self.data["procedure_codes"] = [
            {"code": code, "description": f"Description for {code}"}
            for code in codes
        ]
        return self
    
    def with_clinical_notes(self, notes: str) -> 'MockDataBuilder':
        """Add clinical notes to mock data."""
        self.data["clinical_notes"] = notes
        return self
    
    def build(self) -> Dict[str, Any]:
        """Build and return the mock data structure."""
        return self.data.copy()


# Convenience functions for common mock scenarios
def mock_successful_authorization_flow():
    """Set up mocks for a successful authorization flow."""
    return MockHelpers.setup_common_patches()


def mock_failed_external_service():
    """Set up mocks for external service failure scenarios."""
    patches = MockHelpers.setup_common_patches()
    
    # Configure failures
    patches['huggingface_client'].generate_decision.side_effect = Exception("Service unavailable")
    patches['notification_service'].send_notification.return_value = False
    
    return patches


def mock_database_error():
    """Set up mocks for database error scenarios."""
    patches = MockHelpers.setup_common_patches()
    
    # Configure database failures
    patches['database_session'].commit.side_effect = Exception("Database connection error")
    
    return patches


class ExternalServiceMockManager:
    """Manager for coordinating external service mocks across test scenarios."""
    
    def __init__(self):
        self.active_mocks = {}
        self.failure_scenarios = {}
        self.service_metrics = {}
    
    def setup_healthy_services(self) -> Dict[str, Any]:
        """Set up all external services in healthy state."""
        self.active_mocks = {
            'huggingface': MockHelpers.mock_huggingface_client(),
            'cms_api': MockHelpers.mock_cms_api_service(),
            'medical_validator': MockHelpers.mock_medical_code_validator(),
            'notification': MockHelpers.mock_external_notification_service(),
            'redis_cache': MockHelpers.mock_redis_cache(),
            'http_client': MockHelpers.mock_httpx_client()
        }
        
        # Initialize service metrics
        self._initialize_service_metrics()
        return self.active_mocks
    
    def setup_degraded_services(self, degraded_services: List[str]) -> Dict[str, Any]:
        """Set up services with some experiencing issues."""
        self.active_mocks = {
            'huggingface': MockHelpers.mock_huggingface_client(
                simulate_failures='huggingface' in degraded_services,
                response_delay=2.0 if 'huggingface' in degraded_services else None
            ),
            'cms_api': MockHelpers.mock_cms_api_service(
                simulate_failures='cms_api' in degraded_services,
                response_delay=1.0 if 'cms_api' in degraded_services else None,
                failure_rate=0.2 if 'cms_api' in degraded_services else 0.05
            ),
            'medical_validator': MockHelpers.mock_medical_code_validator(
                simulate_failures='medical_validator' in degraded_services,
                response_delay=0.5 if 'medical_validator' in degraded_services else None,
                failure_rate=0.15 if 'medical_validator' in degraded_services else 0.02
            ),
            'notification': MockHelpers.mock_external_notification_service(
                delivery_failures=['test@example.com'] if 'notification' in degraded_services else []
            ),
            'redis_cache': MockHelpers.mock_redis_cache(
                simulate_connection_issues='redis_cache' in degraded_services
            ),
            'http_client': MockHelpers.mock_httpx_client(
                simulate_network_issues='http_client' in degraded_services,
                response_delay=1.0 if 'http_client' in degraded_services else None
            )
        }
        
        self._initialize_service_metrics(degraded=degraded_services)
        return self.active_mocks
    
    def setup_failure_scenarios(self) -> Dict[str, Dict[str, Any]]:
        """Set up various failure scenarios for testing."""
        scenarios = {
            'all_services_down': {
                'huggingface': MockHelpers.mock_huggingface_client(simulate_failures=True),
                'cms_api': MockHelpers.mock_cms_api_service(simulate_failures=True, failure_rate=0.9),
                'medical_validator': MockHelpers.mock_medical_code_validator(simulate_failures=True, failure_rate=0.8),
                'notification': MockHelpers.mock_external_notification_service(
                    delivery_failures=['test@example.com', '+1234567890']
                ),
                'redis_cache': MockHelpers.mock_redis_cache(simulate_connection_issues=True),
                'http_client': MockHelpers.mock_httpx_client(simulate_network_issues=True)
            },
            'llm_service_timeout': {
                'huggingface': MockHelpers.mock_huggingface_client(
                    responses=[httpx.TimeoutException("LLM service timeout")],
                    simulate_failures=True
                ),
                'cms_api': MockHelpers.mock_cms_api_service(),
                'medical_validator': MockHelpers.mock_medical_code_validator(),
                'notification': MockHelpers.mock_external_notification_service(),
                'redis_cache': MockHelpers.mock_redis_cache(),
                'http_client': MockHelpers.mock_httpx_client()
            },
            'cache_unavailable': {
                'huggingface': MockHelpers.mock_huggingface_client(),
                'cms_api': MockHelpers.mock_cms_api_service(),
                'medical_validator': MockHelpers.mock_medical_code_validator(),
                'notification': MockHelpers.mock_external_notification_service(),
                'redis_cache': MockHelpers.mock_redis_cache(simulate_connection_issues=True),
                'http_client': MockHelpers.mock_httpx_client()
            },
            'partial_service_degradation': {
                'huggingface': MockHelpers.mock_huggingface_client(response_delay=3.0),
                'cms_api': MockHelpers.mock_cms_api_service(simulate_failures=True, failure_rate=0.3),
                'medical_validator': MockHelpers.mock_medical_code_validator(simulate_failures=True, failure_rate=0.2),
                'notification': MockHelpers.mock_external_notification_service(),
                'redis_cache': MockHelpers.mock_redis_cache(),
                'http_client': MockHelpers.mock_httpx_client(response_delay=1.5)
            },
            'intermittent_failures': {
                'huggingface': MockHelpers.mock_huggingface_client(simulate_failures=True, response_delay=0.5),
                'cms_api': MockHelpers.mock_cms_api_service(simulate_failures=True, failure_rate=0.1),
                'medical_validator': MockHelpers.mock_medical_code_validator(simulate_failures=True, failure_rate=0.05),
                'notification': MockHelpers.mock_external_notification_service(
                    delivery_failures=['flaky@example.com']
                ),
                'redis_cache': MockHelpers.mock_redis_cache(),
                'http_client': MockHelpers.mock_httpx_client(simulate_network_issues=True)
            },
            'rate_limiting': {
                'huggingface': MockHelpers.mock_huggingface_client(
                    responses=[httpx.HTTPStatusError("HTTP 429 Too Many Requests", request=Mock(), response=Mock(status_code=429))],
                    simulate_failures=True
                ),
                'cms_api': MockHelpers.mock_cms_api_service(simulate_failures=True, failure_rate=0.4),
                'medical_validator': MockHelpers.mock_medical_code_validator(simulate_failures=True, failure_rate=0.3),
                'notification': MockHelpers.mock_external_notification_service(),
                'redis_cache': MockHelpers.mock_redis_cache(),
                'http_client': MockHelpers.mock_httpx_client()
            },
            'authentication_failures': {
                'huggingface': MockHelpers.mock_huggingface_client(
                    responses=[httpx.HTTPStatusError("HTTP 401 Unauthorized", request=Mock(), response=Mock(status_code=401))],
                    simulate_failures=True
                ),
                'cms_api': MockHelpers.mock_cms_api_service(simulate_failures=True, failure_rate=0.5),
                'medical_validator': MockHelpers.mock_medical_code_validator(),
                'notification': MockHelpers.mock_external_notification_service(),
                'redis_cache': MockHelpers.mock_redis_cache(),
                'http_client': MockHelpers.mock_httpx_client()
            }
        }
        
        self.failure_scenarios = scenarios
        return scenarios
    
    def get_scenario(self, scenario_name: str) -> Dict[str, Any]:
        """Get a specific failure scenario."""
        if scenario_name not in self.failure_scenarios:
            self.setup_failure_scenarios()
        
        return self.failure_scenarios.get(scenario_name, self.setup_healthy_services())
    
    def _initialize_service_metrics(self, degraded: Optional[List[str]] = None):
        """Initialize service health metrics."""
        degraded = degraded or []
        
        self.service_metrics = {
            'huggingface': {
                'status': 'degraded' if 'huggingface' in degraded else 'healthy',
                'response_time_ms': 2000 if 'huggingface' in degraded else 150,
                'success_rate': 0.7 if 'huggingface' in degraded else 0.99,
                'last_check': datetime.now(timezone.utc).isoformat()
            },
            'cms_api': {
                'status': 'degraded' if 'cms_api' in degraded else 'healthy',
                'response_time_ms': 1000 if 'cms_api' in degraded else 80,
                'success_rate': 0.8 if 'cms_api' in degraded else 0.98,
                'last_check': datetime.now(timezone.utc).isoformat()
            },
            'medical_validator': {
                'status': 'degraded' if 'medical_validator' in degraded else 'healthy',
                'response_time_ms': 500 if 'medical_validator' in degraded else 20,
                'success_rate': 0.85 if 'medical_validator' in degraded else 0.99,
                'last_check': datetime.now(timezone.utc).isoformat()
            },
            'notification': {
                'status': 'degraded' if 'notification' in degraded else 'healthy',
                'response_time_ms': 300 if 'notification' in degraded else 50,
                'success_rate': 0.9 if 'notification' in degraded else 0.97,
                'last_check': datetime.now(timezone.utc).isoformat()
            },
            'redis_cache': {
                'status': 'degraded' if 'redis_cache' in degraded else 'healthy',
                'response_time_ms': 100 if 'redis_cache' in degraded else 1,
                'success_rate': 0.95 if 'redis_cache' in degraded else 0.999,
                'last_check': datetime.now(timezone.utc).isoformat()
            }
        }
    
    def get_service_metrics(self) -> Dict[str, Any]:
        """Get current service health metrics."""
        return self.service_metrics.copy()
    
    def simulate_service_recovery(self, service_name: str):
        """Simulate a service recovering from failure."""
        if service_name in self.active_mocks:
            # Update the mock to healthy state
            if service_name == 'huggingface':
                self.active_mocks[service_name] = MockHelpers.mock_huggingface_client()
            elif service_name == 'cms_api':
                self.active_mocks[service_name] = MockHelpers.mock_cms_api_service()
            elif service_name == 'medical_validator':
                self.active_mocks[service_name] = MockHelpers.mock_medical_code_validator()
            elif service_name == 'notification':
                self.active_mocks[service_name] = MockHelpers.mock_external_notification_service()
            elif service_name == 'redis_cache':
                self.active_mocks[service_name] = MockHelpers.mock_redis_cache()
            elif service_name == 'http_client':
                self.active_mocks[service_name] = MockHelpers.mock_httpx_client()
            
            # Update metrics
            if service_name in self.service_metrics:
                self.service_metrics[service_name].update({
                    'status': 'healthy',
                    'response_time_ms': 50,
                    'success_rate': 0.99,
                    'last_check': datetime.now(timezone.utc).isoformat()
                })
    
    def simulate_service_failure(self, service_name: str, failure_type: str = 'timeout'):
        """Simulate a specific service failure."""
        failure_configs = {
            'timeout': {'simulate_failures': True, 'failure_rate': 0.8, 'response_delay': 5.0},
            'rate_limit': {'simulate_failures': True, 'failure_rate': 0.6, 'response_delay': 0.1},
            'auth_error': {'simulate_failures': True, 'failure_rate': 0.9, 'response_delay': 0.05},
            'connection_error': {'simulate_failures': True, 'failure_rate': 0.7, 'response_delay': 2.0}
        }
        
        config = failure_configs.get(failure_type, failure_configs['timeout'])
        
        if service_name == 'huggingface':
            self.active_mocks[service_name] = MockHelpers.mock_huggingface_client(**config)
        elif service_name == 'cms_api':
            self.active_mocks[service_name] = MockHelpers.mock_cms_api_service(**config)
        elif service_name == 'medical_validator':
            self.active_mocks[service_name] = MockHelpers.mock_medical_code_validator(**config)
        
        # Update metrics
        if service_name in self.service_metrics:
            self.service_metrics[service_name].update({
                'status': 'failed',
                'response_time_ms': config.get('response_delay', 1.0) * 1000,
                'success_rate': 1.0 - config.get('failure_rate', 0.5),
                'last_check': datetime.now(timezone.utc).isoformat(),
                'failure_type': failure_type
            })
    
    def cleanup(self):
        """Clean up all active mocks."""
        self.active_mocks.clear()
        self.failure_scenarios.clear()
        self.service_metrics.clear()
        MockHelpers.cleanup_patches()


class RealisticResponseGenerator:
    """Generate realistic responses for external service mocks."""
    
    @staticmethod
    def generate_huggingface_responses(scenario: str = "standard") -> List[Dict[str, Any]]:
        """Generate realistic HuggingFace API responses."""
        responses = {
            "standard": [
                {
                    "decision": "approved",
                    "confidence": 0.92,
                    "reasoning": [
                        "Patient presents with chronic shoulder pain",
                        "Conservative treatment attempted for 6 weeks",
                        "MRI appropriate for further evaluation"
                    ],
                    "model_id": "microsoft/DialoGPT-medium",
                    "processing_time_ms": 1150.0
                }
            ],
            "denial": [
                {
                    "decision": "denied",
                    "confidence": 0.88,
                    "reasoning": [
                        "Insufficient documentation of conservative treatment",
                        "Alternative imaging modalities not considered",
                        "Clinical presentation does not meet medical necessity criteria"
                    ],
                    "model_id": "microsoft/DialoGPT-medium",
                    "processing_time_ms": 1320.0
                }
            ],
            "low_confidence": [
                {
                    "decision": "pending_review",
                    "confidence": 0.65,
                    "reasoning": [
                        "Clinical presentation is ambiguous",
                        "Additional clinical information may be needed",
                        "Recommend manual review by clinical staff"
                    ],
                    "model_id": "microsoft/DialoGPT-medium",
                    "processing_time_ms": 1890.0
                }
            ]
        }
        
        return responses.get(scenario, responses["standard"])
    
    @staticmethod
    def generate_cms_responses(coverage_type: str = "standard") -> Dict[str, bool]:
        """Generate realistic CMS coverage decisions."""
        coverage_maps = {
            "standard": {
                "70551": True,   # MRI Brain - covered
                "72148": True,   # MRI Spine - covered
                "73221": True,   # MRI Shoulder - covered
                "70450": False,  # CT Head - requires prior auth
                "72131": False,  # CT Spine - requires prior auth
            },
            "restrictive": {
                "70551": False,  # MRI Brain - denied
                "72148": False,  # MRI Spine - denied
                "73221": False,  # MRI Shoulder - denied
                "70450": False,  # CT Head - denied
                "72131": False,  # CT Spine - denied
            },
            "permissive": {
                "70551": True,   # MRI Brain - covered
                "72148": True,   # MRI Spine - covered
                "73221": True,   # MRI Shoulder - covered
                "70450": True,   # CT Head - covered
                "72131": True,   # CT Spine - covered
            }
        }
        
        return coverage_maps.get(coverage_type, coverage_maps["standard"])
    
    @staticmethod
    def generate_error_responses() -> Dict[str, Exception]:
        """Generate realistic error responses for testing."""
        return {
            "timeout": httpx.TimeoutException("Request timeout after 30 seconds"),
            "connection_error": httpx.ConnectError("Failed to establish connection"),
            "http_error": httpx.HTTPStatusError(
                "HTTP 503 Service Unavailable",
                request=Mock(),
                response=Mock(status_code=503)
            ),
            "rate_limit": httpx.HTTPStatusError(
                "HTTP 429 Too Many Requests",
                request=Mock(),
                response=Mock(status_code=429)
            ),
            "auth_error": httpx.HTTPStatusError(
                "HTTP 401 Unauthorized",
                request=Mock(),
                response=Mock(status_code=401)
            )
        }


# Convenience functions for common external service mock scenarios
def setup_external_services_healthy():
    """Set up all external services in healthy state."""
    manager = ExternalServiceMockManager()
    return manager.setup_healthy_services()


def setup_external_services_degraded(degraded_services: List[str]):
    """Set up external services with specified services degraded."""
    manager = ExternalServiceMockManager()
    return manager.setup_degraded_services(degraded_services)


def setup_external_services_failure_scenario(scenario: str):
    """Set up external services for a specific failure scenario."""
    manager = ExternalServiceMockManager()
    return manager.get_scenario(scenario)


def create_realistic_mock_responses(service: str, scenario: str = "standard"):
    """Create realistic mock responses for a specific service."""
    generator = RealisticResponseGenerator()
    
    if service == "huggingface":
        return generator.generate_huggingface_responses(scenario)
    elif service == "cms":
        return generator.generate_cms_responses(scenario)
    elif service == "errors":
        return generator.generate_error_responses()
    else:
        raise ValueError(f"Unknown service: {service}")
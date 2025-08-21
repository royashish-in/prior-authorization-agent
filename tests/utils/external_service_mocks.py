"""
Enhanced external service mocks for comprehensive testing.

This module provides realistic mock implementations for external services
including CMS API, medical code validation, and third-party integrations
with proper error simulation and response patterns.
"""

import asyncio
import json
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Union
from unittest.mock import Mock, AsyncMock, MagicMock
import httpx

from tests.utils.mock_helpers import MockHelpers


class RealisticCMSAPIMock:
    """Realistic CMS API mock with comprehensive coverage scenarios."""
    
    def __init__(self, failure_rate: float = 0.05, response_delay: float = 0.1):
        self.failure_rate = failure_rate
        self.response_delay = response_delay
        self.request_count = 0
        self.rate_limit_threshold = 1000  # requests per hour
        self.rate_limit_window = {}
        
        # Comprehensive NCD/LCD database
        self.ncd_database = {
            "220.2": {
                "title": "Magnetic Resonance Imaging (MRI)",
                "effective_date": "2024-01-01",
                "coverage_criteria": [
                    "Medical necessity must be documented",
                    "Conservative treatment attempted when appropriate",
                    "Clinical indication supports imaging request"
                ],
                "covered_procedures": ["70551", "70552", "70553", "72148", "72149", "73221", "73222"],
                "exclusions": ["Routine screening", "Repeat imaging without clinical change"]
            },
            "220.1": {
                "title": "Computed Tomography (CT)",
                "effective_date": "2024-01-01", 
                "coverage_criteria": [
                    "Clinical indication supports CT imaging",
                    "Less invasive imaging considered first",
                    "Results will guide clinical management"
                ],
                "covered_procedures": ["70450", "70460", "72131", "72132"],
                "exclusions": ["Screening without symptoms", "Duplicate imaging"]
            },
            "220.3": {
                "title": "Ultrasound Imaging",
                "effective_date": "2024-01-01",
                "coverage_criteria": [
                    "Appropriate clinical indication",
                    "Non-invasive diagnostic tool"
                ],
                "covered_procedures": ["76700", "76705", "93306", "93307"],
                "exclusions": ["Routine screening in asymptomatic patients"]
            }
        }
        
        # LCD (Local Coverage Determination) database
        self.lcd_database = {
            "L33721": {
                "title": "MRI Brain and Orbit",
                "contractor": "Novitas Solutions",
                "effective_date": "2024-01-01",
                "covered_diagnoses": ["G93.1", "G44.1", "G35", "R51"],
                "coverage_criteria": ["Neurological symptoms present", "Conservative treatment attempted"]
            },
            "L33722": {
                "title": "MRI Spine",
                "contractor": "Novitas Solutions", 
                "effective_date": "2024-01-01",
                "covered_diagnoses": ["M54.5", "M54.6", "M54.9"],
                "coverage_criteria": ["Back pain > 6 weeks", "Neurological deficits present"]
            },
            "L33723": {
                "title": "MRI Upper Extremity",
                "contractor": "Novitas Solutions",
                "effective_date": "2024-01-01",
                "covered_diagnoses": ["M25.511", "M25.512", "S43.001A"],
                "coverage_criteria": ["Joint pain > 4 weeks", "Physical therapy attempted"]
            }
        }
    
    def _check_rate_limit(self, client_id: str = "test_client") -> bool:
        """Check if client has exceeded rate limits."""
        current_time = datetime.now(timezone.utc)
        hour_key = current_time.strftime("%Y%m%d%H")
        
        if client_id not in self.rate_limit_window:
            self.rate_limit_window[client_id] = {}
        
        if hour_key not in self.rate_limit_window[client_id]:
            self.rate_limit_window[client_id][hour_key] = 0
        
        self.rate_limit_window[client_id][hour_key] += 1
        
        return self.rate_limit_window[client_id][hour_key] > self.rate_limit_threshold
    
    async def check_coverage(self, procedure_code: str, diagnosis_code: str, 
                           client_id: str = "test_client") -> Dict[str, Any]:
        """Check coverage for procedure/diagnosis combination."""
        self.request_count += 1
        
        # Check rate limiting
        if self._check_rate_limit(client_id):
            raise httpx.HTTPStatusError(
                "HTTP 429 Too Many Requests - Rate limit exceeded",
                request=Mock(),
                response=Mock(status_code=429)
            )
        
        # Simulate random failures
        if random.random() < self.failure_rate:
            failure_types = [
                httpx.TimeoutException("CMS API request timeout"),
                httpx.ConnectError("Failed to connect to CMS API"),
                Exception("CMS API service temporarily unavailable"),
                httpx.HTTPStatusError("HTTP 503 Service Unavailable", 
                                    request=Mock(), response=Mock(status_code=503))
            ]
            raise random.choice(failure_types)
        
        # Simulate response delay
        await asyncio.sleep(self.response_delay + random.uniform(0, 0.05))
        
        # Determine coverage based on NCD/LCD rules
        is_covered = False
        applicable_ncd = None
        applicable_lcd = None
        coverage_criteria = []
        
        # Check NCD coverage
        for ncd_id, ncd_data in self.ncd_database.items():
            if procedure_code in ncd_data["covered_procedures"]:
                applicable_ncd = ncd_id
                is_covered = True
                coverage_criteria.extend(ncd_data["coverage_criteria"])
                break
        
        # Check LCD coverage for additional criteria
        for lcd_id, lcd_data in self.lcd_database.items():
            if diagnosis_code in lcd_data["covered_diagnoses"]:
                applicable_lcd = lcd_id
                coverage_criteria.extend(lcd_data["coverage_criteria"])
                break
        
        # Special logic for common combinations
        if procedure_code in ["70551", "70552", "70553"] and diagnosis_code.startswith("G"):
            is_covered = True
        elif procedure_code in ["72148", "72149"] and diagnosis_code.startswith("M54"):
            is_covered = True
        elif procedure_code in ["73221", "73222"] and diagnosis_code.startswith("M25"):
            is_covered = True
        
        return {
            "request_id": f"cms_req_{self.request_count}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "procedure_code": procedure_code,
            "diagnosis_code": diagnosis_code,
            "is_covered": is_covered,
            "applicable_ncd": applicable_ncd,
            "applicable_lcd": applicable_lcd,
            "coverage_criteria": list(set(coverage_criteria)),
            "policy_references": [f"NCD_{applicable_ncd}" if applicable_ncd else None,
                                f"LCD_{applicable_lcd}" if applicable_lcd else None],
            "effective_date": "2024-01-01",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "confidence_score": 0.95 if is_covered else 0.88,
            "additional_requirements": [
                "Prior authorization required",
                "Clinical documentation must support medical necessity"
            ] if is_covered else [
                "Does not meet coverage criteria",
                "Consider alternative imaging modalities"
            ]
        }
    
    async def get_policy_details(self, policy_id: str) -> Dict[str, Any]:
        """Get detailed policy information."""
        await asyncio.sleep(self.response_delay)
        
        if random.random() < self.failure_rate * 0.5:
            raise Exception(f"Policy details unavailable for {policy_id}")
        
        # Check NCD database
        if policy_id in self.ncd_database:
            policy_data = self.ncd_database[policy_id].copy()
            policy_data["policy_id"] = policy_id
            policy_data["policy_type"] = "NCD"
            return policy_data
        
        # Check LCD database  
        if policy_id in self.lcd_database:
            policy_data = self.lcd_database[policy_id].copy()
            policy_data["policy_id"] = policy_id
            policy_data["policy_type"] = "LCD"
            return policy_data
        
        # Return generic policy for unknown IDs
        return {
            "policy_id": policy_id,
            "policy_type": "UNKNOWN",
            "title": f"Policy {policy_id}",
            "effective_date": "2024-01-01",
            "coverage_criteria": ["Standard medical necessity criteria apply"],
            "exclusions": []
        }
    
    async def batch_check_coverage(self, requests: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Check coverage for multiple procedure/diagnosis combinations."""
        if len(requests) > 50:
            raise Exception("Batch size exceeds maximum limit of 50 requests")
        
        results = []
        for request in requests:
            try:
                result = await self.check_coverage(
                    request.get("procedure_code", ""),
                    request.get("diagnosis_code", "")
                )
                results.append(result)
            except Exception as e:
                results.append({
                    "procedure_code": request.get("procedure_code", ""),
                    "diagnosis_code": request.get("diagnosis_code", ""),
                    "error": str(e),
                    "is_covered": False
                })
        
        return results
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get current service status and metrics."""
        return {
            "service": "CMS Guidelines API",
            "status": "operational",
            "version": "v2.1.0",
            "uptime_percentage": 99.5,
            "average_response_time_ms": self.response_delay * 1000,
            "requests_processed": self.request_count,
            "rate_limit_threshold": self.rate_limit_threshold,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }


class RealisticMedicalCodeValidatorMock:
    """Realistic medical code validator with comprehensive code databases."""
    
    def __init__(self, failure_rate: float = 0.02, response_delay: float = 0.01):
        self.failure_rate = failure_rate
        self.response_delay = response_delay
        self.validation_count = 0
        
        # Load comprehensive code databases
        self._load_code_databases()
    
    def _load_code_databases(self):
        """Load comprehensive medical code databases."""
        # ICD-10 codes with detailed information
        self.icd10_database = {
            # Musculoskeletal system (M00-M99)
            "M25.511": {
                "description": "Pain in right shoulder",
                "category": "Arthropathies",
                "subcategory": "Other joint disorders",
                "billable": True,
                "effective_date": "2024-01-01"
            },
            "M25.512": {
                "description": "Pain in left shoulder", 
                "category": "Arthropathies",
                "subcategory": "Other joint disorders",
                "billable": True,
                "effective_date": "2024-01-01"
            },
            "M54.5": {
                "description": "Low back pain",
                "category": "Dorsopathies",
                "subcategory": "Other dorsopathies", 
                "billable": True,
                "effective_date": "2024-01-01"
            },
            "M79.1": {
                "description": "Myalgia",
                "category": "Soft tissue disorders",
                "subcategory": "Other soft tissue disorders",
                "billable": True,
                "effective_date": "2024-01-01"
            },
            # Nervous system (G00-G99)
            "G93.1": {
                "description": "Anoxic brain damage, not elsewhere classified",
                "category": "Diseases of the nervous system",
                "subcategory": "Other disorders of the nervous system",
                "billable": True,
                "effective_date": "2024-01-01"
            },
            "G44.1": {
                "description": "Vascular headache, not elsewhere classified",
                "category": "Diseases of the nervous system", 
                "subcategory": "Episodic and paroxysmal disorders",
                "billable": True,
                "effective_date": "2024-01-01"
            },
            # Symptoms and signs (R00-R99)
            "R51": {
                "description": "Headache",
                "category": "Symptoms, signs and abnormal clinical and laboratory findings",
                "subcategory": "General symptoms and signs",
                "billable": True,
                "effective_date": "2024-01-01"
            },
            "R52": {
                "description": "Pain, unspecified",
                "category": "Symptoms, signs and abnormal clinical and laboratory findings",
                "subcategory": "General symptoms and signs", 
                "billable": True,
                "effective_date": "2024-01-01"
            }
        }
        
        # CPT codes with detailed information
        self.cpt_database = {
            # Radiology - Diagnostic Imaging (70000-79999)
            "70551": {
                "description": "Magnetic resonance (eg, proton) imaging, brain (including brain stem); without contrast material",
                "category": "Radiology",
                "subcategory": "Diagnostic Radiology",
                "rvu": 2.89,
                "effective_date": "2024-01-01"
            },
            "70552": {
                "description": "Magnetic resonance (eg, proton) imaging, brain (including brain stem); with contrast material(s)",
                "category": "Radiology",
                "subcategory": "Diagnostic Radiology", 
                "rvu": 3.45,
                "effective_date": "2024-01-01"
            },
            "72148": {
                "description": "Magnetic resonance (eg, proton) imaging, spinal canal and contents, lumbar; without contrast material",
                "category": "Radiology",
                "subcategory": "Diagnostic Radiology",
                "rvu": 2.67,
                "effective_date": "2024-01-01"
            },
            "73221": {
                "description": "Magnetic resonance (eg, proton) imaging, any joint of upper extremity; without contrast material(s)",
                "category": "Radiology",
                "subcategory": "Diagnostic Radiology",
                "rvu": 2.34,
                "effective_date": "2024-01-01"
            },
            "70450": {
                "description": "Computed tomography, head or brain; without contrast material",
                "category": "Radiology",
                "subcategory": "Diagnostic Radiology",
                "rvu": 1.89,
                "effective_date": "2024-01-01"
            },
            "76700": {
                "description": "Ultrasound, abdominal, real time with image documentation; complete",
                "category": "Radiology",
                "subcategory": "Diagnostic Ultrasound",
                "rvu": 1.23,
                "effective_date": "2024-01-01"
            },
            "93306": {
                "description": "Echocardiography, transthoracic, real-time with image documentation (2D), includes M-mode recording, when performed, complete",
                "category": "Medicine",
                "subcategory": "Cardiovascular",
                "rvu": 2.78,
                "effective_date": "2024-01-01"
            }
        }
        
        # HCPCS codes
        self.hcpcs_database = {
            "E0781": {
                "description": "Ambulatory infusion pump, single or multiple channels, electric or battery operated",
                "category": "Durable Medical Equipment",
                "subcategory": "Infusion Supplies",
                "effective_date": "2024-01-01"
            },
            "K0001": {
                "description": "Standard wheelchair",
                "category": "Durable Medical Equipment", 
                "subcategory": "Wheelchairs",
                "effective_date": "2024-01-01"
            },
            "J0135": {
                "description": "Injection, adalimumab, 20 mg",
                "category": "Drugs Administered Other Than Oral Method",
                "subcategory": "Drugs, Administered by Injection",
                "effective_date": "2024-01-01"
            }
        }
    
    async def validate_code(self, code: str, code_type: str) -> Dict[str, Any]:
        """Validate a single medical code."""
        self.validation_count += 1
        
        # Simulate random failures
        if random.random() < self.failure_rate:
            failure_types = [
                Exception("Medical code validation service timeout"),
                Exception("Code database temporarily unavailable"),
                Exception("Invalid request format")
            ]
            raise random.choice(failure_types)
        
        # Simulate response delay
        await asyncio.sleep(self.response_delay + random.uniform(0, 0.005))
        
        code_type = code_type.lower()
        database = None
        
        if code_type == "icd10":
            database = self.icd10_database
        elif code_type == "cpt":
            database = self.cpt_database
        elif code_type == "hcpcs":
            database = self.hcpcs_database
        else:
            return {
                "code": code,
                "code_type": code_type,
                "is_valid": False,
                "error": f"Unsupported code type: {code_type}",
                "suggestions": []
            }
        
        if code in database:
            code_info = database[code]
            return {
                "code": code,
                "code_type": code_type,
                "is_valid": True,
                "description": code_info["description"],
                "category": code_info["category"],
                "subcategory": code_info.get("subcategory", ""),
                "effective_date": code_info["effective_date"],
                "billable": code_info.get("billable", True),
                "rvu": code_info.get("rvu"),
                "validation_timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            # Generate suggestions for invalid codes
            suggestions = self._generate_suggestions(code, code_type, database)
            return {
                "code": code,
                "code_type": code_type,
                "is_valid": False,
                "error": f"Code {code} not found in {code_type.upper()} database",
                "suggestions": suggestions,
                "validation_timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def _generate_suggestions(self, invalid_code: str, code_type: str, 
                            database: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate code suggestions for invalid codes."""
        suggestions = []
        
        # Simple fuzzy matching based on code prefixes
        for valid_code, code_info in database.items():
            similarity_score = 0
            
            # Check prefix similarity
            if len(invalid_code) >= 3 and len(valid_code) >= 3:
                if valid_code.startswith(invalid_code[:3]):
                    similarity_score = 0.8
                elif invalid_code.startswith(valid_code[:3]):
                    similarity_score = 0.7
                elif valid_code[:2] == invalid_code[:2]:
                    similarity_score = 0.6
            
            # Check character similarity
            common_chars = set(invalid_code.upper()) & set(valid_code.upper())
            if len(common_chars) > 0:
                char_similarity = len(common_chars) / max(len(invalid_code), len(valid_code))
                similarity_score = max(similarity_score, char_similarity * 0.5)
            
            if similarity_score > 0.5:
                suggestions.append({
                    "code": valid_code,
                    "description": code_info["description"],
                    "similarity_score": similarity_score
                })
        
        # Sort by similarity and return top 5
        suggestions.sort(key=lambda x: x["similarity_score"], reverse=True)
        return suggestions[:5]
    
    async def batch_validate_codes(self, codes: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Validate multiple codes in batch."""
        if len(codes) > 100:
            raise Exception("Batch size exceeds maximum limit of 100 codes")
        
        results = []
        for code_info in codes:
            try:
                result = await self.validate_code(
                    code_info.get("code", ""),
                    code_info.get("code_type", "")
                )
                results.append(result)
            except Exception as e:
                results.append({
                    "code": code_info.get("code", ""),
                    "code_type": code_info.get("code_type", ""),
                    "is_valid": False,
                    "error": str(e),
                    "suggestions": []
                })
        
        return results
    
    async def search_codes(self, query: str, code_type: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for codes matching a query."""
        await asyncio.sleep(self.response_delay)
        
        if random.random() < self.failure_rate:
            raise Exception(f"Code search service unavailable for {code_type}")
        
        code_type = code_type.lower()
        database = None
        
        if code_type == "icd10":
            database = self.icd10_database
        elif code_type == "cpt":
            database = self.cpt_database
        elif code_type == "hcpcs":
            database = self.hcpcs_database
        else:
            return []
        
        results = []
        query_lower = query.lower()
        
        for code, code_info in database.items():
            relevance_score = 0
            
            # Check code match
            if query_lower in code.lower():
                relevance_score = 0.9
            
            # Check description match
            if query_lower in code_info["description"].lower():
                relevance_score = max(relevance_score, 0.7)
            
            # Check category match
            if query_lower in code_info["category"].lower():
                relevance_score = max(relevance_score, 0.5)
            
            if relevance_score > 0:
                results.append({
                    "code": code,
                    "description": code_info["description"],
                    "category": code_info["category"],
                    "code_type": code_type,
                    "relevance_score": relevance_score
                })
        
        # Sort by relevance and return top results
        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        return results[:limit]
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get current service status and metrics."""
        return {
            "service": "Medical Code Validation API",
            "status": "operational",
            "version": "v1.2.0",
            "databases": {
                "icd10_codes": len(self.icd10_database),
                "cpt_codes": len(self.cpt_database),
                "hcpcs_codes": len(self.hcpcs_database)
            },
            "validations_processed": self.validation_count,
            "average_response_time_ms": self.response_delay * 1000,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }


def create_comprehensive_external_service_mocks(scenario: str = "healthy") -> Dict[str, Any]:
    """Create comprehensive external service mocks for different scenarios."""
    
    scenarios = {
        "healthy": {
            "cms_api": RealisticCMSAPIMock(failure_rate=0.01, response_delay=0.08),
            "medical_validator": RealisticMedicalCodeValidatorMock(failure_rate=0.005, response_delay=0.02),
            "notification_service": MockHelpers.mock_external_notification_service(),
            "cache_service": MockHelpers.mock_redis_cache()
        },
        "degraded": {
            "cms_api": RealisticCMSAPIMock(failure_rate=0.15, response_delay=0.5),
            "medical_validator": RealisticMedicalCodeValidatorMock(failure_rate=0.1, response_delay=0.1),
            "notification_service": MockHelpers.mock_external_notification_service(
                delivery_failures=["flaky@example.com"]
            ),
            "cache_service": MockHelpers.mock_redis_cache(simulate_connection_issues=True)
        },
        "failing": {
            "cms_api": RealisticCMSAPIMock(failure_rate=0.8, response_delay=2.0),
            "medical_validator": RealisticMedicalCodeValidatorMock(failure_rate=0.6, response_delay=1.0),
            "notification_service": MockHelpers.mock_external_notification_service(
                delivery_failures=["test@example.com", "+1234567890"]
            ),
            "cache_service": MockHelpers.mock_redis_cache(simulate_connection_issues=True)
        }
    }
    
    return scenarios.get(scenario, scenarios["healthy"])
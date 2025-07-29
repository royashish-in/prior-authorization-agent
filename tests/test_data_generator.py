"""
Test data generator for creating comprehensive mock medical scenarios.
"""

import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from src.models.authorization import AuthorizationRequest, AuthorizationDecision
from src.models.patient import PatientDemographics
from src.models.medical_codes import ICD10Code, CPTCode
from src.models.enums import (
    RequestStatus, DecisionStatus, UrgencyLevel, Gender, ProcedureType
)


@dataclass
class MedicalScenario:
    """Represents a complete medical scenario for testing."""
    name: str
    patient: PatientDemographics
    diagnosis_codes: List[ICD10Code]
    procedure_codes: List[CPTCode]
    clinical_notes: str
    urgency_level: UrgencyLevel
    procedure_type: ProcedureType
    expected_decision: DecisionStatus
    expected_reasoning: List[str]
    policy_references: List[str]


class TestDataGenerator:
    """Generates comprehensive test data for various medical scenarios."""
    
    # Common ICD-10 codes for imaging
    COMMON_DIAGNOSIS_CODES = {
        "M25.511": "Pain in right shoulder",
        "M25.512": "Pain in left shoulder", 
        "M54.5": "Low back pain",
        "G93.1": "Anoxic brain damage, not elsewhere classified",
        "S72.001A": "Fracture of unspecified part of neck of right femur, initial encounter",
        "M79.3": "Panniculitis, unspecified",
        "R06.02": "Shortness of breath",
        "M25.561": "Pain in right knee",
        "G44.1": "Vascular headache, not elsewhere classified",
        "M47.816": "Spondylosis without myelopathy or radiculopathy, lumbar region"
    }
    
    # Common CPT codes for imaging
    COMMON_PROCEDURE_CODES = {
        "70551": "MRI brain without contrast",
        "70552": "MRI brain with contrast", 
        "72148": "MRI lumbar spine without contrast",
        "72149": "MRI lumbar spine with contrast",
        "73221": "MRI upper extremity without contrast",
        "73222": "MRI upper extremity with contrast",
        "74177": "CT abdomen and pelvis with contrast",
        "71250": "CT chest without contrast",
        "72128": "CT lumbar spine without contrast",
        "76700": "Ultrasound abdomen complete"
    }
    
    def __init__(self):
        """Initialize the test data generator."""
        self.scenario_counter = 0
    
    def generate_patient_demographics(self, age_range: tuple = (18, 80)) -> PatientDemographics:
        """Generate realistic patient demographics."""
        age = random.randint(*age_range)
        gender = random.choice([Gender.MALE, Gender.FEMALE])
        
        return PatientDemographics(
            patient_id=f"enc_pat_{random.randint(1000000, 9999999):07d}",
            age=age,
            gender=gender,
            insurance_id=f"enc_ins_{random.randint(1000000, 9999999):07d}",
            member_id=f"enc_mem_{random.randint(1000000, 9999999):07d}"
        )
    
    def generate_diagnosis_codes(self, count: int = 1) -> List[ICD10Code]:
        """Generate realistic diagnosis codes."""
        codes = random.sample(list(self.COMMON_DIAGNOSIS_CODES.keys()), min(count, len(self.COMMON_DIAGNOSIS_CODES)))
        return [
            ICD10Code(code=code, description=self.COMMON_DIAGNOSIS_CODES[code])
            for code in codes
        ]
    
    def generate_procedure_codes(self, count: int = 1) -> List[CPTCode]:
        """Generate realistic procedure codes."""
        codes = random.sample(list(self.COMMON_PROCEDURE_CODES.keys()), min(count, len(self.COMMON_PROCEDURE_CODES)))
        return [
            CPTCode(code=code, description=self.COMMON_PROCEDURE_CODES[code])
            for code in codes
        ]
    
    def generate_clinical_notes(self, diagnosis_code: str, procedure_code: str) -> str:
        """Generate realistic clinical notes based on diagnosis and procedure."""
        templates = {
            "M25.511": "Patient reports persistent right shoulder pain for {duration} weeks following {cause}. Conservative treatment with {treatment} has provided limited relief. Physical examination reveals {findings}.",
            "M54.5": "Patient presents with chronic low back pain lasting {duration} months. Pain is described as {quality} and radiates to {location}. Previous treatments include {treatment}.",
            "G93.1": "Patient with history of {cause} presenting with neurological symptoms including {symptoms}. Urgent imaging required to assess extent of brain injury.",
            "S72.001A": "Patient sustained right femoral neck fracture following {mechanism}. Requires immediate imaging to assess fracture pattern and plan surgical intervention.",
            "G44.1": "Patient reports severe headaches with {characteristics} lasting {duration}. Associated symptoms include {symptoms}. Neuroimaging indicated to rule out secondary causes."
        }
        
        # Generate random values for template placeholders
        duration = random.randint(2, 12)
        causes = ["sports injury", "fall", "motor vehicle accident", "work-related injury"]
        treatments = ["physical therapy", "NSAIDs", "rest", "ice therapy"]
        findings = ["limited range of motion", "tenderness", "swelling", "muscle spasm"]
        qualities = ["sharp", "dull", "burning", "aching"]
        locations = ["bilateral legs", "right leg", "left leg", "buttocks"]
        symptoms = ["confusion", "memory loss", "weakness", "dizziness"]
        mechanisms = ["fall from height", "motor vehicle accident", "sports injury"]
        characteristics = ["throbbing quality", "photophobia", "nausea", "visual disturbances"]
        
        template = templates.get(diagnosis_code, "Patient presents with {condition} requiring imaging evaluation.")
        
        return template.format(
            duration=duration,
            cause=random.choice(causes),
            treatment=random.choice(treatments),
            findings=random.choice(findings),
            quality=random.choice(qualities),
            location=random.choice(locations),
            symptoms=random.choice(symptoms),
            mechanism=random.choice(mechanisms),
            characteristics=random.choice(characteristics),
            condition="medical condition"
        )
    
    def generate_authorization_request(self, scenario_type: str = "routine") -> AuthorizationRequest:
        """Generate a complete authorization request."""
        self.scenario_counter += 1
        
        patient = self.generate_patient_demographics()
        diagnosis_codes = self.generate_diagnosis_codes(random.randint(1, 2))
        procedure_codes = self.generate_procedure_codes(1)
        
        # Determine procedure type from CPT code
        procedure_type = self._determine_procedure_type(procedure_codes[0].code)
        
        # Determine urgency based on scenario type
        urgency_mapping = {
            "routine": UrgencyLevel.ROUTINE,
            "urgent": UrgencyLevel.URGENT,
            "emergent": UrgencyLevel.EMERGENT
        }
        urgency = urgency_mapping.get(scenario_type, UrgencyLevel.ROUTINE)
        
        clinical_notes = self.generate_clinical_notes(
            diagnosis_codes[0].code,
            procedure_codes[0].code
        )
        
        return AuthorizationRequest(
            request_id=f"req_test_{self.scenario_counter:06d}",
            provider_id=f"prov_{random.randint(1000, 9999)}",
            patient_demographics=patient,
            diagnosis_codes=diagnosis_codes,
            procedure_codes=procedure_codes,
            clinical_notes=clinical_notes,
            procedure_type=procedure_type,
            urgency_level=urgency,
            status=RequestStatus.SUBMITTED
        )
    
    def generate_authorization_decision(self, request: AuthorizationRequest, 
                                     decision_type: str = "approved") -> AuthorizationDecision:
        """Generate an authorization decision for a request."""
        decision_mapping = {
            "approved": DecisionStatus.APPROVED,
            "denied": DecisionStatus.DENIED,
            "more_info": DecisionStatus.MORE_INFO_NEEDED
        }
        
        status = decision_mapping.get(decision_type, DecisionStatus.APPROVED)
        
        # Generate reasoning based on decision type
        reasoning = self._generate_decision_reasoning(status, request)
        
        # Generate policy references
        policy_references = self._generate_policy_references(request)
        
        decision_data = {
            "decision_id": f"dec_{request.request_id.replace('req_', '')}",
            "request_id": request.request_id,
            "status": status,
            "reasoning": reasoning,
            "policy_references": policy_references,
            "confidence_score": random.uniform(0.7, 0.99)
        }
        
        if status == DecisionStatus.APPROVED:
            decision_data.update({
                "authorization_number": f"auth_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{random.randint(100000, 999999)}",
                "valid_until": datetime.now(timezone.utc) + timedelta(days=30)
            })
        elif status == DecisionStatus.MORE_INFO_NEEDED:
            decision_data["additional_info_needed"] = [
                "Physical therapy notes from past 6 weeks",
                "Specialist consultation report"
            ]
        elif status == DecisionStatus.DENIED:
            decision_data["alternative_procedures"] = [
                "Consider conservative treatment for additional 4 weeks",
                "Physical therapy evaluation recommended"
            ]
        
        return AuthorizationDecision(**decision_data)
    
    def generate_medical_scenarios(self, count: int = 10) -> List[MedicalScenario]:
        """Generate a variety of medical scenarios for comprehensive testing."""
        scenarios = []
        scenario_types = ["routine", "urgent", "emergent"]
        decision_types = ["approved", "denied", "more_info"]
        
        for i in range(count):
            scenario_type = random.choice(scenario_types)
            decision_type = random.choice(decision_types)
            
            request = self.generate_authorization_request(scenario_type)
            decision = self.generate_authorization_decision(request, decision_type)
            
            scenario = MedicalScenario(
                name=f"scenario_{i+1}_{scenario_type}_{decision_type}",
                patient=request.patient_demographics,
                diagnosis_codes=request.diagnosis_codes,
                procedure_codes=request.procedure_codes,
                clinical_notes=request.clinical_notes,
                urgency_level=request.urgency_level,
                procedure_type=request.procedure_type,
                expected_decision=decision.status,
                expected_reasoning=decision.reasoning,
                policy_references=decision.policy_references
            )
            
            scenarios.append(scenario)
        
        return scenarios
    
    def generate_edge_case_scenarios(self) -> List[Dict[str, Any]]:
        """Generate edge case scenarios for testing."""
        return [
            {
                "name": "invalid_diagnosis_code",
                "diagnosis_codes": ["INVALID123"],
                "expected_outcome": "validation_error"
            },
            {
                "name": "invalid_procedure_code", 
                "procedure_codes": ["99999"],
                "expected_outcome": "validation_error"
            },
            {
                "name": "missing_clinical_notes",
                "clinical_notes": "",
                "expected_outcome": "more_info_needed"
            },
            {
                "name": "elderly_patient_high_risk",
                "patient_age": 85,
                "urgency": UrgencyLevel.EMERGENT,
                "expected_outcome": "approved_with_warnings"
            },
            {
                "name": "pediatric_patient",
                "patient_age": 12,
                "expected_outcome": "special_handling"
            }
        ]
    
    def generate_performance_test_data(self, request_count: int = 1000) -> List[AuthorizationRequest]:
        """Generate data for performance testing."""
        requests = []
        scenario_types = ["routine", "urgent", "emergent"]
        
        for i in range(request_count):
            scenario_type = random.choice(scenario_types)
            request = self.generate_authorization_request(scenario_type)
            requests.append(request)
        
        return requests
    
    def _determine_procedure_type(self, cpt_code: str) -> ProcedureType:
        """Determine procedure type from CPT code."""
        if cpt_code.startswith("705"):  # MRI brain codes
            return ProcedureType.MRI
        elif cpt_code.startswith("721"):  # MRI spine codes
            return ProcedureType.MRI
        elif cpt_code.startswith("732"):  # MRI extremity codes
            return ProcedureType.MRI
        elif cpt_code.startswith("712") or cpt_code.startswith("741"):  # CT codes
            return ProcedureType.CT_SCAN
        elif cpt_code.startswith("767"):  # Ultrasound codes
            return ProcedureType.ULTRASOUND
        else:
            return ProcedureType.X_RAY
    
    def _generate_decision_reasoning(self, status: DecisionStatus, 
                                   request: AuthorizationRequest) -> List[str]:
        """Generate realistic decision reasoning."""
        if status == DecisionStatus.APPROVED:
            return [
                f"Patient meets medical necessity criteria for {request.procedure_codes[0].description}",
                f"Diagnosis {request.diagnosis_codes[0].code} is covered under current policy",
                "Conservative treatment duration is adequate",
                "Clinical documentation supports imaging request"
            ]
        elif status == DecisionStatus.DENIED:
            return [
                "Insufficient conservative treatment trial",
                "Clinical documentation does not support medical necessity",
                "Alternative diagnostic methods should be considered first"
            ]
        else:  # MORE_INFO_NEEDED
            return [
                "Additional clinical documentation required",
                "Physical therapy records needed to assess treatment response",
                "Specialist consultation recommended before imaging approval"
            ]
    
    def _generate_policy_references(self, request: AuthorizationRequest) -> List[str]:
        """Generate realistic policy references."""
        references = ["CMS NCD 220.2 - Magnetic Resonance Imaging"]
        
        if request.procedure_type == ProcedureType.MRI:
            references.append("LCD L33721 - MRI Upper Extremity")
        elif request.procedure_type == ProcedureType.CT_SCAN:
            references.append("LCD L33822 - Computed Tomography")
        
        references.append("Payer Policy IMG-001 - Imaging Services")
        
        return references


# Utility functions for test data
def create_test_request_batch(count: int = 100) -> List[AuthorizationRequest]:
    """Create a batch of test requests for load testing."""
    generator = TestDataGenerator()
    return [generator.generate_authorization_request() for _ in range(count)]


def create_validation_test_cases() -> List[Dict[str, Any]]:
    """Create test cases for validation testing."""
    return [
        {
            "name": "valid_request",
            "data": TestDataGenerator().generate_authorization_request(),
            "expected_valid": True
        },
        {
            "name": "invalid_diagnosis_code",
            "modifications": {"diagnosis_codes": [{"code": "INVALID", "description": "Invalid"}]},
            "expected_valid": False
        },
        {
            "name": "missing_procedure_code",
            "modifications": {"procedure_codes": []},
            "expected_valid": False
        }
    ]


def create_policy_test_scenarios() -> List[Dict[str, Any]]:
    """Create scenarios for policy validation testing."""
    return [
        {
            "name": "covered_procedure",
            "procedure_code": "73221",
            "diagnosis_code": "M25.511",
            "expected_covered": True
        },
        {
            "name": "experimental_procedure",
            "procedure_code": "99999",
            "diagnosis_code": "M25.511", 
            "expected_covered": False
        },
        {
            "name": "off_label_use",
            "procedure_code": "73221",
            "diagnosis_code": "Z00.00",
            "expected_covered": False
        }
    ]
"""
Policy configuration service for managing coverage policies.

This service handles policy creation, updates, version control,
bulk import/validation, and sandbox testing functionality.
"""

import json
import logging
from datetime import date, datetime, timezone
from typing import List, Dict, Optional, Any, Tuple
from uuid import uuid4
from dataclasses import dataclass

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

from src.database.models import CoveragePolicyDB
from src.services.policy_validation import PolicyValidationService, PolicyType
from src.services.medical_code_validator import MedicalCodeValidator
from src.models.authorization import AuthorizationRequest
from src.models.patient import PatientDemographics
from src.models.medical_codes import ICD10Code, CPTCode


logger = logging.getLogger(__name__)


@dataclass
class PolicyVersion:
    """Policy version information."""
    policy_id: str
    version: str
    created_at: datetime
    created_by: str
    update_reason: Optional[str]
    is_current: bool


@dataclass
class BulkImportResult:
    """Result of bulk policy import operation."""
    total_policies: int
    successful_imports: int
    failed_imports: int
    validation_errors: List[Dict[str, Any]]
    import_summary: Dict[str, Any]


@dataclass
class PolicyTestResult:
    """Result of policy testing in sandbox."""
    policy_id: str
    test_results: List[Dict[str, Any]]
    overall_success: bool
    recommendations: List[str]


class PolicyConfigurationService:
    """
    Service for managing policy configuration with version control.
    
    Provides functionality for creating, updating, and testing policies
    with comprehensive validation and conflict detection.
    """
    
    def __init__(self, db_session: Session):
        """Initialize the policy configuration service."""
        self.db_session = db_session
        self.logger = logging.getLogger(__name__)
        self.policy_validation_service = PolicyValidationService(db_session)
        self.medical_code_validator = MedicalCodeValidator()
    
    async def create_policy(
        self,
        policy_data: Dict[str, Any],
        created_by: str
    ) -> str:
        """
        Create a new coverage policy with validation.
        
        Args:
            policy_data: Policy configuration data
            created_by: User ID who created the policy
            
        Returns:
            Policy ID of the created policy
        """
        try:
            # Validate policy data
            validation_result = await self._validate_policy_data(policy_data)
            if not validation_result['is_valid']:
                raise ValueError(f"Policy validation failed: {validation_result['errors']}")
            
            # Check for conflicts with existing policies
            conflicts = await self._check_policy_conflicts(policy_data)
            if conflicts:
                self.logger.warning(f"Policy conflicts detected: {conflicts}")
                # For now, log conflicts but allow creation
                # In production, this might require approval workflow
            
            # Generate policy ID
            policy_id = f"pol_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
            
            # Create policy record
            policy = CoveragePolicyDB(
                policy_id=policy_id,
                payer_id=policy_data['payer_id'],
                procedure_code=policy_data['procedure_code'],
                diagnosis_codes=policy_data.get('diagnosis_codes', []),
                coverage_criteria=policy_data['coverage_criteria'],
                policy_type=policy_data['policy_type'],
                policy_name=policy_data['policy_name'],
                policy_version="1.0",
                effective_date=policy_data.get('effective_date', date.today()),
                expiration_date=policy_data.get('expiration_date'),
                is_active=policy_data.get('is_active', True),
                created_by=created_by,
                updated_by=created_by
            )
            
            self.db_session.add(policy)
            self.db_session.commit()
            
            # Create initial version record
            await self._create_version_record(
                policy_id=policy_id,
                version="1.0",
                created_by=created_by,
                update_reason="Initial policy creation"
            )
            
            self.logger.info(f"Policy created successfully: {policy_id}")
            return policy_id
            
        except Exception as e:
            self.db_session.rollback()
            self.logger.error(f"Failed to create policy: {str(e)}")
            raise
    
    async def update_policy(
        self,
        policy_id: str,
        update_data: Dict[str, Any],
        updated_by: str,
        update_reason: str
    ) -> Optional[CoveragePolicyDB]:
        """
        Update an existing policy with version control.
        
        Args:
            policy_id: Policy identifier
            update_data: Fields to update
            updated_by: User ID who updated the policy
            update_reason: Reason for the update
            
        Returns:
            Updated policy record or None if not found
        """
        try:
            # Get existing policy
            policy = self.get_policy_by_id(policy_id)
            if not policy:
                return None
            
            # Validate update data
            if 'coverage_criteria' in update_data:
                validation_result = await self._validate_coverage_criteria(
                    update_data['coverage_criteria']
                )
                if not validation_result['is_valid']:
                    raise ValueError(f"Coverage criteria validation failed: {validation_result['errors']}")
            
            # Check for conflicts if procedure code or criteria changed
            if 'procedure_code' in update_data or 'coverage_criteria' in update_data:
                test_data = {
                    'payer_id': policy.payer_id,
                    'procedure_code': update_data.get('procedure_code', policy.procedure_code),
                    'coverage_criteria': update_data.get('coverage_criteria', policy.coverage_criteria),
                    'policy_type': policy.policy_type
                }
                conflicts = await self._check_policy_conflicts(test_data, exclude_policy_id=policy_id)
                if conflicts:
                    self.logger.warning(f"Policy update conflicts detected: {conflicts}")
            
            # Update policy fields
            for field, value in update_data.items():
                if hasattr(policy, field) and field not in ['policy_id', 'created_at', 'created_by']:
                    setattr(policy, field, value)
            
            # Update metadata
            policy.updated_by = updated_by
            policy.updated_at = datetime.now(timezone.utc)
            
            # Increment version
            current_version = float(policy.policy_version)
            new_version = f"{current_version + 0.1:.1f}"
            policy.policy_version = new_version
            
            self.db_session.commit()
            
            # Create version record
            await self._create_version_record(
                policy_id=policy_id,
                version=new_version,
                created_by=updated_by,
                update_reason=update_reason
            )
            
            self.logger.info(f"Policy updated successfully: {policy_id} to version {new_version}")
            return policy
            
        except Exception as e:
            self.db_session.rollback()
            self.logger.error(f"Failed to update policy {policy_id}: {str(e)}")
            raise
    
    async def deactivate_policy(
        self,
        policy_id: str,
        deactivated_by: str
    ) -> bool:
        """
        Deactivate a policy (soft delete).
        
        Args:
            policy_id: Policy identifier
            deactivated_by: User ID who deactivated the policy
            
        Returns:
            True if successful, False if policy not found
        """
        try:
            policy = self.get_policy_by_id(policy_id)
            if not policy:
                return False
            
            policy.is_active = False
            policy.updated_by = deactivated_by
            policy.updated_at = datetime.now(timezone.utc)
            
            self.db_session.commit()
            
            # Create version record
            await self._create_version_record(
                policy_id=policy_id,
                version=policy.policy_version,
                created_by=deactivated_by,
                update_reason="Policy deactivated"
            )
            
            self.logger.info(f"Policy deactivated successfully: {policy_id}")
            return True
            
        except Exception as e:
            self.db_session.rollback()
            self.logger.error(f"Failed to deactivate policy {policy_id}: {str(e)}")
            raise
    
    def get_policy_by_id(self, policy_id: str) -> Optional[CoveragePolicyDB]:
        """
        Retrieve a policy by its ID.
        
        Args:
            policy_id: Policy identifier
            
        Returns:
            Policy record or None if not found
        """
        return self.db_session.query(CoveragePolicyDB).filter(
            CoveragePolicyDB.policy_id == policy_id
        ).first()
    
    def list_policies(
        self,
        payer_id: Optional[str] = None,
        policy_type: Optional[str] = None,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0
    ) -> List[CoveragePolicyDB]:
        """
        List policies with filtering options.
        
        Args:
            payer_id: Filter by payer ID
            policy_type: Filter by policy type
            active_only: Whether to return only active policies
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of policy records
        """
        query = self.db_session.query(CoveragePolicyDB)
        
        # Apply filters
        if payer_id:
            query = query.filter(CoveragePolicyDB.payer_id == payer_id)
        
        if policy_type:
            query = query.filter(CoveragePolicyDB.policy_type == policy_type)
        
        if active_only:
            query = query.filter(
                and_(
                    CoveragePolicyDB.is_active == True,
                    CoveragePolicyDB.effective_date <= date.today(),
                    or_(
                        CoveragePolicyDB.expiration_date.is_(None),
                        CoveragePolicyDB.expiration_date >= date.today()
                    )
                )
            )
        
        # Apply pagination and ordering
        query = query.order_by(desc(CoveragePolicyDB.updated_at))
        query = query.offset(offset).limit(limit)
        
        return query.all()
    
    def get_policy_versions(self, policy_id: str) -> List[PolicyVersion]:
        """
        Get version history for a policy.
        
        Args:
            policy_id: Policy identifier
            
        Returns:
            List of policy versions
        """
        # This would typically query a separate policy_versions table
        # For now, we'll return a mock version based on the current policy
        policy = self.get_policy_by_id(policy_id)
        if not policy:
            return []
        
        return [
            PolicyVersion(
                policy_id=policy.policy_id,
                version=policy.policy_version,
                created_at=policy.updated_at,
                created_by=policy.updated_by,
                update_reason="Current version",
                is_current=True
            )
        ]
    
    async def bulk_import_policies(
        self,
        policies_data: List[Dict[str, Any]],
        import_mode: str,
        imported_by: str
    ) -> Dict[str, Any]:
        """
        Bulk import policies with validation.
        
        Args:
            policies_data: List of policy configurations
            import_mode: Import mode (validate, import, replace)
            imported_by: User ID who initiated the import
            
        Returns:
            Import result summary
        """
        try:
            total_policies = len(policies_data)
            successful_imports = 0
            failed_imports = 0
            validation_errors = []
            import_summary = {
                'new_policies': 0,
                'updated_policies': 0,
                'skipped_policies': 0,
                'policy_types': {},
                'payers': set()
            }
            
            for i, policy_data in enumerate(policies_data):
                try:
                    # Validate policy data
                    validation_result = await self._validate_policy_data(policy_data)
                    if not validation_result['is_valid']:
                        validation_errors.append({
                            'index': i,
                            'policy_data': policy_data,
                            'errors': validation_result['errors']
                        })
                        failed_imports += 1
                        continue
                    
                    # Check if policy already exists
                    existing_policy = self._find_existing_policy(
                        payer_id=policy_data['payer_id'],
                        procedure_code=policy_data['procedure_code'],
                        policy_type=policy_data['policy_type']
                    )
                    
                    if import_mode == "validate":
                        # Only validate, don't import
                        successful_imports += 1
                        continue
                    
                    elif import_mode == "import":
                        if existing_policy:
                            # Skip existing policies
                            import_summary['skipped_policies'] += 1
                            continue
                        else:
                            # Create new policy
                            await self.create_policy(policy_data, imported_by)
                            import_summary['new_policies'] += 1
                    
                    elif import_mode == "replace":
                        if existing_policy:
                            # Update existing policy
                            await self.update_policy(
                                policy_id=existing_policy.policy_id,
                                update_data=policy_data,
                                updated_by=imported_by,
                                update_reason="Bulk import replacement"
                            )
                            import_summary['updated_policies'] += 1
                        else:
                            # Create new policy
                            await self.create_policy(policy_data, imported_by)
                            import_summary['new_policies'] += 1
                    
                    successful_imports += 1
                    
                    # Update summary statistics
                    policy_type = policy_data['policy_type']
                    import_summary['policy_types'][policy_type] = import_summary['policy_types'].get(policy_type, 0) + 1
                    import_summary['payers'].add(policy_data['payer_id'])
                    
                except Exception as e:
                    validation_errors.append({
                        'index': i,
                        'policy_data': policy_data,
                        'errors': [f"Import error: {str(e)}"]
                    })
                    failed_imports += 1
            
            # Convert set to list for JSON serialization
            import_summary['payers'] = list(import_summary['payers'])
            
            result = {
                'total_policies': total_policies,
                'successful_imports': successful_imports,
                'failed_imports': failed_imports,
                'validation_errors': validation_errors,
                'import_summary': import_summary
            }
            
            self.logger.info(
                f"Bulk import completed: {successful_imports}/{total_policies} successful, "
                f"{failed_imports} failed, mode: {import_mode}"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Bulk import failed: {str(e)}")
            raise
    
    async def test_policy_sandbox(
        self,
        policy_config: Dict[str, Any],
        test_scenarios: List[Dict[str, Any]],
        tested_by: str
    ) -> Dict[str, Any]:
        """
        Test policy configuration in sandbox environment.
        
        Args:
            policy_config: Policy configuration to test
            test_scenarios: List of test scenarios
            tested_by: User ID who initiated the test
            
        Returns:
            Test results
        """
        try:
            # Generate temporary policy ID for testing
            test_policy_id = f"test_{uuid4().hex[:8]}"
            
            # Validate policy configuration
            validation_result = await self._validate_policy_data(policy_config)
            if not validation_result['is_valid']:
                return {
                    'policy_id': test_policy_id,
                    'test_results': [],
                    'overall_success': False,
                    'recommendations': [f"Policy validation failed: {validation_result['errors']}"]
                }
            
            test_results = []
            overall_success = True
            recommendations = []
            
            # Run each test scenario
            for i, scenario in enumerate(test_scenarios):
                try:
                    # Create mock authorization request from scenario
                    mock_request = self._create_mock_request(scenario)
                    
                    # Create temporary policy for testing
                    temp_policy = self._create_temp_policy(policy_config, test_policy_id)
                    
                    # Test policy validation
                    validation_result = self.policy_validation_service._validate_against_policy(
                        mock_request, temp_policy
                    )
                    
                    test_result = {
                        'scenario_index': i,
                        'scenario_name': scenario.get('name', f"Test Scenario {i+1}"),
                        'expected_outcome': scenario.get('expected_outcome', 'approve'),
                        'actual_outcome': 'approve' if validation_result.is_covered else 'deny',
                        'reasoning': validation_result.reasoning,
                        'confidence_score': validation_result.confidence_score,
                        'success': (
                            scenario.get('expected_outcome', 'approve') == 
                            ('approve' if validation_result.is_covered else 'deny')
                        )
                    }
                    
                    test_results.append(test_result)
                    
                    if not test_result['success']:
                        overall_success = False
                        recommendations.append(
                            f"Scenario '{test_result['scenario_name']}' failed: "
                            f"expected {test_result['expected_outcome']}, "
                            f"got {test_result['actual_outcome']}"
                        )
                
                except Exception as e:
                    test_results.append({
                        'scenario_index': i,
                        'scenario_name': scenario.get('name', f"Test Scenario {i+1}"),
                        'error': str(e),
                        'success': False
                    })
                    overall_success = False
                    recommendations.append(f"Scenario {i+1} failed with error: {str(e)}")
            
            # Add general recommendations
            if overall_success:
                recommendations.append("All test scenarios passed successfully")
            else:
                recommendations.append("Review failed scenarios and adjust policy configuration")
            
            result = {
                'policy_id': test_policy_id,
                'test_results': test_results,
                'overall_success': overall_success,
                'recommendations': recommendations
            }
            
            self.logger.info(
                f"Policy sandbox testing completed: {test_policy_id}, "
                f"success: {overall_success}, scenarios: {len(test_scenarios)}"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Policy sandbox testing failed: {str(e)}")
            raise
    
    async def validate_policy_configuration(
        self,
        policy_id: str
    ) -> Dict[str, Any]:
        """
        Validate policy configuration and check for conflicts.
        
        Args:
            policy_id: Policy identifier
            
        Returns:
            Validation result
        """
        try:
            policy = self.get_policy_by_id(policy_id)
            if not policy:
                return {
                    'is_valid': False,
                    'validation_errors': ['Policy not found'],
                    'warnings': [],
                    'recommendations': []
                }
            
            validation_errors = []
            warnings = []
            recommendations = []
            
            # Validate coverage criteria
            criteria_validation = await self._validate_coverage_criteria(policy.coverage_criteria)
            if not criteria_validation['is_valid']:
                validation_errors.extend(criteria_validation['errors'])
            
            # Check for policy conflicts
            policy_data = {
                'payer_id': policy.payer_id,
                'procedure_code': policy.procedure_code,
                'coverage_criteria': policy.coverage_criteria,
                'policy_type': policy.policy_type
            }
            conflicts = await self._check_policy_conflicts(policy_data, exclude_policy_id=policy_id)
            if conflicts:
                warnings.extend([f"Policy conflict detected: {conflict}" for conflict in conflicts])
                recommendations.append("Review conflicting policies and resolve inconsistencies")
            
            # Check medical code validity
            if policy.diagnosis_codes:
                for dx_code in policy.diagnosis_codes:
                    if not self.medical_code_validator.validate_icd10_code(dx_code):
                        validation_errors.append(f"Invalid ICD-10 code: {dx_code}")
            
            # Validate procedure code
            if not self.medical_code_validator.validate_cpt_code(policy.procedure_code):
                validation_errors.append(f"Invalid CPT/HCPCS code: {policy.procedure_code}")
            
            # Check date validity
            if policy.expiration_date and policy.expiration_date <= policy.effective_date:
                validation_errors.append("Expiration date must be after effective date")
            
            # Add recommendations based on policy type
            if policy.policy_type == 'PAYER' and not policy.diagnosis_codes:
                recommendations.append("Consider specifying diagnosis codes for payer-specific policies")
            
            is_valid = len(validation_errors) == 0
            
            return {
                'is_valid': is_valid,
                'validation_errors': validation_errors,
                'warnings': warnings,
                'recommendations': recommendations
            }
            
        except Exception as e:
            self.logger.error(f"Policy validation failed for {policy_id}: {str(e)}")
            return {
                'is_valid': False,
                'validation_errors': [f"Validation error: {str(e)}"],
                'warnings': [],
                'recommendations': []
            }
    
    async def _validate_policy_data(self, policy_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate policy data structure and content."""
        errors = []
        
        # Required fields
        required_fields = ['payer_id', 'procedure_code', 'policy_name', 'policy_type', 'coverage_criteria']
        for field in required_fields:
            if field not in policy_data or not policy_data[field]:
                errors.append(f"Missing required field: {field}")
        
        # Validate policy type
        if 'policy_type' in policy_data:
            if policy_data['policy_type'] not in ['NCD', 'LCD', 'PAYER']:
                errors.append("Policy type must be NCD, LCD, or PAYER")
        
        # Validate coverage criteria
        if 'coverage_criteria' in policy_data:
            criteria_validation = await self._validate_coverage_criteria(policy_data['coverage_criteria'])
            if not criteria_validation['is_valid']:
                errors.extend(criteria_validation['errors'])
        
        # Validate medical codes
        if 'procedure_code' in policy_data:
            if not self.medical_code_validator.validate_cpt_code(policy_data['procedure_code']):
                errors.append(f"Invalid CPT/HCPCS code: {policy_data['procedure_code']}")
        
        if 'diagnosis_codes' in policy_data and policy_data['diagnosis_codes']:
            for dx_code in policy_data['diagnosis_codes']:
                if not self.medical_code_validator.validate_icd10_code(dx_code):
                    errors.append(f"Invalid ICD-10 code: {dx_code}")
        
        return {
            'is_valid': len(errors) == 0,
            'errors': errors
        }
    
    async def _validate_coverage_criteria(self, coverage_criteria: Dict[str, Any]) -> Dict[str, Any]:
        """Validate coverage criteria structure."""
        errors = []
        
        if not isinstance(coverage_criteria, dict):
            errors.append("Coverage criteria must be a dictionary")
            return {'is_valid': False, 'errors': errors}
        
        # Validate age range if present
        if 'age_range' in coverage_criteria:
            age_range = coverage_criteria['age_range']
            if not isinstance(age_range, dict):
                errors.append("Age range must be a dictionary")
            else:
                if 'min_age' in age_range and not isinstance(age_range['min_age'], int):
                    errors.append("Minimum age must be an integer")
                if 'max_age' in age_range and not isinstance(age_range['max_age'], int):
                    errors.append("Maximum age must be an integer")
                if ('min_age' in age_range and 'max_age' in age_range and 
                    age_range['min_age'] >= age_range['max_age']):
                    errors.append("Minimum age must be less than maximum age")
        
        # Validate medical necessity criteria
        if 'medical_necessity' in coverage_criteria:
            necessity = coverage_criteria['medical_necessity']
            if not isinstance(necessity, dict):
                errors.append("Medical necessity criteria must be a dictionary")
        
        return {
            'is_valid': len(errors) == 0,
            'errors': errors
        }
    
    async def _check_policy_conflicts(
        self,
        policy_data: Dict[str, Any],
        exclude_policy_id: Optional[str] = None
    ) -> List[str]:
        """Check for conflicts with existing policies."""
        conflicts = []
        
        try:
            # Find policies with same payer and procedure code
            query = self.db_session.query(CoveragePolicyDB).filter(
                and_(
                    CoveragePolicyDB.payer_id == policy_data['payer_id'],
                    CoveragePolicyDB.procedure_code == policy_data['procedure_code'],
                    CoveragePolicyDB.is_active == True
                )
            )
            
            if exclude_policy_id:
                query = query.filter(CoveragePolicyDB.policy_id != exclude_policy_id)
            
            existing_policies = query.all()
            
            for existing_policy in existing_policies:
                # Check for overlapping effective dates
                effective_date = policy_data.get('effective_date', date.today())
                expiration_date = policy_data.get('expiration_date')
                
                # Simple conflict detection - same payer, procedure, and overlapping dates
                if (not existing_policy.expiration_date or 
                    existing_policy.expiration_date >= effective_date):
                    if (not expiration_date or 
                        expiration_date >= existing_policy.effective_date):
                        conflicts.append(
                            f"Overlapping policy found: {existing_policy.policy_id} "
                            f"({existing_policy.policy_name})"
                        )
            
        except Exception as e:
            self.logger.error(f"Error checking policy conflicts: {str(e)}")
        
        return conflicts
    
    def _find_existing_policy(
        self,
        payer_id: str,
        procedure_code: str,
        policy_type: str
    ) -> Optional[CoveragePolicyDB]:
        """Find existing policy with same payer, procedure, and type."""
        return self.db_session.query(CoveragePolicyDB).filter(
            and_(
                CoveragePolicyDB.payer_id == payer_id,
                CoveragePolicyDB.procedure_code == procedure_code,
                CoveragePolicyDB.policy_type == policy_type,
                CoveragePolicyDB.is_active == True
            )
        ).first()
    
    async def _create_version_record(
        self,
        policy_id: str,
        version: str,
        created_by: str,
        update_reason: str
    ):
        """Create a version record for policy changes."""
        # This would typically insert into a policy_versions table
        # For now, we'll just log the version creation
        self.logger.info(
            f"Policy version created: {policy_id} v{version} by {created_by} - {update_reason}"
        )
    
    def _create_mock_request(self, scenario: Dict[str, Any]) -> AuthorizationRequest:
        """Create mock authorization request from test scenario."""
        # Create mock patient demographics
        patient_demographics = PatientDemographics(
            patient_id="test_patient",
            age=scenario.get('patient_age', 45),
            gender=scenario.get('patient_gender', 'F'),
            insurance_id="test_insurance",
            member_id="test_member"
        )
        
        # Create mock diagnosis codes
        diagnosis_codes = [
            ICD10Code(code=dx_code, description=f"Test diagnosis {dx_code}")
            for dx_code in scenario.get('diagnosis_codes', ['M25.511'])
        ]
        
        # Create mock procedure codes
        procedure_codes = [
            CPTCode(code=proc_code, description=f"Test procedure {proc_code}")
            for proc_code in scenario.get('procedure_codes', ['73721'])
        ]
        
        # Create mock authorization request
        return AuthorizationRequest(
            request_id=f"test_req_{uuid4().hex[:8]}",
            provider_id="test_provider",
            patient_demographics=patient_demographics,
            diagnosis_codes=diagnosis_codes,
            procedure_codes=procedure_codes,
            clinical_notes=scenario.get('clinical_notes', "Test clinical notes"),
            urgency_level=scenario.get('urgency_level', 'ROUTINE'),
            procedure_type=scenario.get('procedure_type', 'MRI'),
            submitted_at=datetime.now(timezone.utc)
        )
    
    def _create_temp_policy(
        self,
        policy_config: Dict[str, Any],
        policy_id: str
    ) -> CoveragePolicyDB:
        """Create temporary policy object for testing."""
        return CoveragePolicyDB(
            policy_id=policy_id,
            payer_id=policy_config['payer_id'],
            procedure_code=policy_config['procedure_code'],
            diagnosis_codes=policy_config.get('diagnosis_codes', []),
            coverage_criteria=policy_config['coverage_criteria'],
            policy_type=policy_config['policy_type'],
            policy_name=policy_config['policy_name'],
            policy_version="test",
            effective_date=policy_config.get('effective_date', date.today()),
            expiration_date=policy_config.get('expiration_date'),
            is_active=True,
            created_by="test_user",
            updated_by="test_user"
        )
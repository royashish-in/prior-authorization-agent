"""
Repository layer for medical codes database operations.

Implements the repository pattern for ICD-10 and CPT codes with
comprehensive CRUD operations, search, and validation capabilities.
"""

from typing import List, Optional, Dict, Any, Tuple
from datetime import date, datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, text, desc, asc
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.models.medical_codes import ICD10CodeDB, CPTCodeDB, CodeRelationshipDB
from src.database.connection import get_db_session
from src.core.exceptions import (
    DatabaseError, ValidationError, NotFoundError, DuplicateError
)


class MedicalCodeRepository:
    """
    Repository for medical codes database operations.
    
    Provides comprehensive CRUD operations, search capabilities,
    and validation for ICD-10 and CPT codes.
    """
    
    def __init__(self, db_session: Optional[Session] = None):
        """Initialize repository with optional database session."""
        self.db_session = db_session
    
    def _get_session(self) -> Session:
        """Get database session, creating one if not provided."""
        if self.db_session:
            return self.db_session
        # If no session provided, create a new one
        from src.database.connection import get_database_manager
        db_manager = get_database_manager()
        return db_manager.session_factory()
    
    # ICD-10 Code Operations
    
    async def create_icd10_code(self, code_data: Dict[str, Any]) -> ICD10CodeDB:
        """
        Create a new ICD-10 code.
        
        Args:
            code_data: Dictionary containing ICD-10 code information
            
        Returns:
            Created ICD10CodeDB instance
            
        Raises:
            ValidationError: If code data is invalid
            DuplicateError: If code already exists
            DatabaseError: If database operation fails
        """
        try:
            session = self._get_session()
            
            # Check if code already exists
            existing = session.query(ICD10CodeDB).filter(
                ICD10CodeDB.code == code_data['code'].upper()
            ).first()
            
            if existing:
                raise DuplicateError(f"ICD-10 code {code_data['code']} already exists")
            
            # Create new code
            icd10_code = ICD10CodeDB(**code_data)
            session.add(icd10_code)
            session.commit()
            session.refresh(icd10_code)
            
            return icd10_code
            
        except IntegrityError as e:
            session.rollback()
            raise DuplicateError(f"ICD-10 code {code_data['code']} already exists") from e
        except SQLAlchemyError as e:
            session.rollback()
            raise DatabaseError(f"Failed to create ICD-10 code: {str(e)}") from e
    
    async def get_icd10_code_by_code(self, code: str) -> Optional[ICD10CodeDB]:
        """
        Get ICD-10 code by code string.
        
        Args:
            code: ICD-10 code string
            
        Returns:
            ICD10CodeDB instance or None if not found
        """
        try:
            session = self._get_session()
            return session.query(ICD10CodeDB).filter(
                ICD10CodeDB.code == code.upper()
            ).first()
        except SQLAlchemyError as e:
            raise DatabaseError(f"Failed to retrieve ICD-10 code: {str(e)}") from e
    
    async def get_icd10_code_by_id(self, code_id: int) -> Optional[ICD10CodeDB]:
        """Get ICD-10 code by ID."""
        try:
            session = self._get_session()
            return session.query(ICD10CodeDB).filter(
                ICD10CodeDB.id == code_id
            ).first()
        except SQLAlchemyError as e:
            raise DatabaseError(f"Failed to retrieve ICD-10 code: {str(e)}") from e
    
    async def search_icd10_codes(
        self, 
        query: str, 
        category: Optional[str] = None,
        billable_only: bool = False,
        valid_only: bool = True,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[ICD10CodeDB], int]:
        """
        Search ICD-10 codes with fuzzy matching.
        
        Args:
            query: Search query string
            category: Filter by category
            billable_only: Only return billable codes
            valid_only: Only return currently valid codes
            limit: Maximum number of results
            offset: Pagination offset
            
        Returns:
            Tuple of (results list, total count)
        """
        try:
            session = self._get_session()
            
            # Build base query
            base_query = session.query(ICD10CodeDB)
            
            # Add search conditions
            if query:
                search_conditions = or_(
                    ICD10CodeDB.code.ilike(f"%{query}%"),
                    ICD10CodeDB.description.ilike(f"%{query}%")
                )
                base_query = base_query.filter(search_conditions)
            
            # Add filters
            if category:
                base_query = base_query.filter(ICD10CodeDB.category == category)
            
            if billable_only:
                base_query = base_query.filter(ICD10CodeDB.billable == True)
            
            if valid_only:
                today = date.today()
                base_query = base_query.filter(
                    and_(
                        ICD10CodeDB.valid_from <= today,
                        or_(
                            ICD10CodeDB.valid_to.is_(None),
                            ICD10CodeDB.valid_to >= today
                        )
                    )
                )
            
            # Get total count
            total_count = base_query.count()
            
            # Apply pagination and ordering
            results = base_query.order_by(
                ICD10CodeDB.code
            ).offset(offset).limit(limit).all()
            
            return results, total_count
            
        except SQLAlchemyError as e:
            raise DatabaseError(f"Failed to search ICD-10 codes: {str(e)}") from e
    
    async def update_icd10_code(self, code_id: int, update_data: Dict[str, Any]) -> ICD10CodeDB:
        """Update an existing ICD-10 code."""
        try:
            session = self._get_session()
            
            icd10_code = session.query(ICD10CodeDB).filter(
                ICD10CodeDB.id == code_id
            ).first()
            
            if not icd10_code:
                raise NotFoundError(f"ICD-10 code with ID {code_id} not found")
            
            # Update fields
            for key, value in update_data.items():
                if hasattr(icd10_code, key):
                    setattr(icd10_code, key, value)
            
            icd10_code.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(icd10_code)
            
            return icd10_code
            
        except SQLAlchemyError as e:
            session.rollback()
            raise DatabaseError(f"Failed to update ICD-10 code: {str(e)}") from e
    
    # CPT Code Operations
    
    async def create_cpt_code(self, code_data: Dict[str, Any]) -> CPTCodeDB:
        """Create a new CPT code."""
        try:
            session = self._get_session()
            
            # Check if code already exists
            existing = session.query(CPTCodeDB).filter(
                CPTCodeDB.code == code_data['code'].upper()
            ).first()
            
            if existing:
                raise DuplicateError(f"CPT code {code_data['code']} already exists")
            
            # Create new code
            cpt_code = CPTCodeDB(**code_data)
            
            # Calculate total RVU if components are provided
            cpt_code.calculate_total_rvu()
            
            session.add(cpt_code)
            session.commit()
            session.refresh(cpt_code)
            
            return cpt_code
            
        except IntegrityError as e:
            session.rollback()
            raise DuplicateError(f"CPT code {code_data['code']} already exists") from e
        except SQLAlchemyError as e:
            session.rollback()
            raise DatabaseError(f"Failed to create CPT code: {str(e)}") from e
    
    async def get_cpt_code_by_code(self, code: str) -> Optional[CPTCodeDB]:
        """Get CPT code by code string."""
        try:
            session = self._get_session()
            return session.query(CPTCodeDB).filter(
                CPTCodeDB.code == code.upper()
            ).first()
        except SQLAlchemyError as e:
            raise DatabaseError(f"Failed to retrieve CPT code: {str(e)}") from e
    
    async def get_cpt_code_by_id(self, code_id: int) -> Optional[CPTCodeDB]:
        """Get CPT code by ID."""
        try:
            session = self._get_session()
            return session.query(CPTCodeDB).filter(
                CPTCodeDB.id == code_id
            ).first()
        except SQLAlchemyError as e:
            raise DatabaseError(f"Failed to retrieve CPT code: {str(e)}") from e
    
    async def search_cpt_codes(
        self, 
        query: str, 
        category: Optional[str] = None,
        procedure_type: Optional[str] = None,
        prior_auth_only: bool = False,
        valid_only: bool = True,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[CPTCodeDB], int]:
        """Search CPT codes with fuzzy matching."""
        try:
            session = self._get_session()
            
            # Build base query
            base_query = session.query(CPTCodeDB)
            
            # Add search conditions
            if query:
                search_conditions = or_(
                    CPTCodeDB.code.ilike(f"%{query}%"),
                    CPTCodeDB.description.ilike(f"%{query}%"),
                    CPTCodeDB.short_description.ilike(f"%{query}%"),
                    CPTCodeDB.search_terms.ilike(f"%{query}%")
                )
                base_query = base_query.filter(search_conditions)
            
            # Add filters
            if category:
                base_query = base_query.filter(CPTCodeDB.category == category)
            
            if procedure_type:
                base_query = base_query.filter(CPTCodeDB.procedure_type == procedure_type)
            
            if prior_auth_only:
                base_query = base_query.filter(CPTCodeDB.prior_auth_required == True)
            
            if valid_only:
                today = date.today()
                base_query = base_query.filter(
                    and_(
                        CPTCodeDB.valid_from <= today,
                        or_(
                            CPTCodeDB.valid_to.is_(None),
                            CPTCodeDB.valid_to >= today
                        )
                    )
                )
            
            # Get total count
            total_count = base_query.count()
            
            # Apply pagination and ordering
            results = base_query.order_by(
                CPTCodeDB.code
            ).offset(offset).limit(limit).all()
            
            return results, total_count
            
        except SQLAlchemyError as e:
            raise DatabaseError(f"Failed to search CPT codes: {str(e)}") from e
    
    async def update_cpt_code(self, code_id: int, update_data: Dict[str, Any]) -> CPTCodeDB:
        """Update an existing CPT code."""
        try:
            session = self._get_session()
            
            cpt_code = session.query(CPTCodeDB).filter(
                CPTCodeDB.id == code_id
            ).first()
            
            if not cpt_code:
                raise NotFoundError(f"CPT code with ID {code_id} not found")
            
            # Update fields
            for key, value in update_data.items():
                if hasattr(cpt_code, key):
                    setattr(cpt_code, key, value)
            
            # Recalculate total RVU if RVU components were updated
            if any(key in update_data for key in ['work_rvu', 'practice_expense_rvu', 'malpractice_rvu']):
                cpt_code.calculate_total_rvu()
            
            cpt_code.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(cpt_code)
            
            return cpt_code
            
        except SQLAlchemyError as e:
            session.rollback()
            raise DatabaseError(f"Failed to update CPT code: {str(e)}") from e
    
    # Code Relationship Operations
    
    async def create_code_relationship(self, relationship_data: Dict[str, Any]) -> CodeRelationshipDB:
        """Create a new code relationship."""
        try:
            session = self._get_session()
            
            # Validate that the referenced codes exist
            if relationship_data['primary_code_type'] == 'ICD10':
                primary_exists = session.query(ICD10CodeDB).filter(
                    ICD10CodeDB.id == relationship_data['primary_code_id']
                ).first()
            else:
                primary_exists = session.query(CPTCodeDB).filter(
                    CPTCodeDB.id == relationship_data['primary_code_id']
                ).first()
            
            if not primary_exists:
                raise ValidationError(f"Primary code ID {relationship_data['primary_code_id']} not found")
            
            if relationship_data['related_code_type'] == 'ICD10':
                related_exists = session.query(ICD10CodeDB).filter(
                    ICD10CodeDB.id == relationship_data['related_code_id']
                ).first()
            else:
                related_exists = session.query(CPTCodeDB).filter(
                    CPTCodeDB.id == relationship_data['related_code_id']
                ).first()
            
            if not related_exists:
                raise ValidationError(f"Related code ID {relationship_data['related_code_id']} not found")
            
            # Create relationship
            relationship = CodeRelationshipDB(**relationship_data)
            session.add(relationship)
            session.commit()
            session.refresh(relationship)
            
            return relationship
            
        except SQLAlchemyError as e:
            session.rollback()
            raise DatabaseError(f"Failed to create code relationship: {str(e)}") from e
    
    async def get_code_relationships(
        self, 
        code_id: int, 
        code_type: str,
        relationship_type: Optional[str] = None,
        active_only: bool = True
    ) -> List[CodeRelationshipDB]:
        """Get relationships for a specific code."""
        try:
            session = self._get_session()
            
            # Query relationships where the code is either primary or related
            query = session.query(CodeRelationshipDB).filter(
                or_(
                    and_(
                        CodeRelationshipDB.primary_code_id == code_id,
                        CodeRelationshipDB.primary_code_type == code_type
                    ),
                    and_(
                        CodeRelationshipDB.related_code_id == code_id,
                        CodeRelationshipDB.related_code_type == code_type
                    )
                )
            )
            
            if relationship_type:
                query = query.filter(CodeRelationshipDB.relationship_type == relationship_type)
            
            if active_only:
                today = date.today()
                query = query.filter(
                    and_(
                        CodeRelationshipDB.is_active == True,
                        CodeRelationshipDB.valid_from <= today,
                        or_(
                            CodeRelationshipDB.valid_to.is_(None),
                            CodeRelationshipDB.valid_to >= today
                        )
                    )
                )
            
            return query.order_by(desc(CodeRelationshipDB.strength)).all()
            
        except SQLAlchemyError as e:
            raise DatabaseError(f"Failed to get code relationships: {str(e)}") from e
    
    # Bulk Operations
    
    async def bulk_create_icd10_codes(self, codes_data: List[Dict[str, Any]]) -> Tuple[int, List[str]]:
        """
        Bulk create ICD-10 codes.
        
        Returns:
            Tuple of (successful_count, error_messages)
        """
        try:
            session = self._get_session()
            successful_count = 0
            error_messages = []
            
            for code_data in codes_data:
                try:
                    # Check if code already exists
                    existing = session.query(ICD10CodeDB).filter(
                        ICD10CodeDB.code == code_data['code'].upper()
                    ).first()
                    
                    if existing:
                        error_messages.append(f"ICD-10 code {code_data['code']} already exists")
                        continue
                    
                    # Ensure required fields are present and properly formatted
                    if 'valid_from' not in code_data:
                        code_data['valid_from'] = date.today()
                    elif isinstance(code_data['valid_from'], str):
                        from datetime import datetime
                        code_data['valid_from'] = datetime.fromisoformat(code_data['valid_from']).date()
                    
                    # Create new code
                    icd10_code = ICD10CodeDB(**code_data)
                    session.add(icd10_code)
                    successful_count += 1
                    
                except Exception as e:
                    error_messages.append(f"Error creating code {code_data.get('code', 'unknown')}: {str(e)}")
            
            session.commit()
            return successful_count, error_messages
            
        except SQLAlchemyError as e:
            session.rollback()
            raise DatabaseError(f"Failed to bulk create ICD-10 codes: {str(e)}") from e
    
    async def bulk_create_cpt_codes(self, codes_data: List[Dict[str, Any]]) -> Tuple[int, List[str]]:
        """
        Bulk create CPT codes.
        
        Returns:
            Tuple of (successful_count, error_messages)
        """
        try:
            session = self._get_session()
            successful_count = 0
            error_messages = []
            
            for code_data in codes_data:
                try:
                    # Check if code already exists
                    existing = session.query(CPTCodeDB).filter(
                        CPTCodeDB.code == code_data['code'].upper()
                    ).first()
                    
                    if existing:
                        error_messages.append(f"CPT code {code_data['code']} already exists")
                        continue
                    
                    # Ensure required fields are present and properly formatted
                    if 'valid_from' not in code_data:
                        code_data['valid_from'] = date.today()
                    elif isinstance(code_data['valid_from'], str):
                        from datetime import datetime
                        code_data['valid_from'] = datetime.fromisoformat(code_data['valid_from']).date()
                    
                    # Create new code
                    cpt_code = CPTCodeDB(**code_data)
                    cpt_code.calculate_total_rvu()
                    session.add(cpt_code)
                    successful_count += 1
                    
                except Exception as e:
                    error_messages.append(f"Error creating code {code_data.get('code', 'unknown')}: {str(e)}")
            
            session.commit()
            return successful_count, error_messages
            
        except SQLAlchemyError as e:
            session.rollback()
            raise DatabaseError(f"Failed to bulk create CPT codes: {str(e)}") from e
    
    # Validation and Suggestions
    
    async def validate_code(self, code: str, code_type: str) -> Dict[str, Any]:
        """
        Validate a medical code and provide suggestions if invalid.
        
        Args:
            code: Code to validate
            code_type: 'ICD10' or 'CPT'
            
        Returns:
            Dictionary with validation results and suggestions
        """
        try:
            session = self._get_session()
            
            if code_type == 'ICD10':
                exact_match = session.query(ICD10CodeDB).filter(
                    ICD10CodeDB.code == code.upper()
                ).first()
                
                if exact_match:
                    return {
                        'valid': True,
                        'code': exact_match.to_dict(),
                        'suggestions': []
                    }
                
                # Find similar codes
                suggestions = session.query(ICD10CodeDB).filter(
                    ICD10CodeDB.code.ilike(f"%{code[:3]}%")
                ).limit(5).all()
                
            else:  # CPT
                exact_match = session.query(CPTCodeDB).filter(
                    CPTCodeDB.code == code.upper()
                ).first()
                
                if exact_match:
                    return {
                        'valid': True,
                        'code': exact_match.to_dict(),
                        'suggestions': []
                    }
                
                # Find similar codes
                suggestions = session.query(CPTCodeDB).filter(
                    CPTCodeDB.code.ilike(f"%{code[:3]}%")
                ).limit(5).all()
            
            return {
                'valid': False,
                'code': None,
                'suggestions': [s.to_dict() for s in suggestions],
                'error': f"Invalid {code_type} code: {code}"
            }
            
        except SQLAlchemyError as e:
            raise DatabaseError(f"Failed to validate code: {str(e)}") from e
    
    async def get_code_suggestions(self, partial_code: str, code_type: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get code suggestions based on partial input."""
        try:
            session = self._get_session()
            
            if code_type == 'ICD10':
                suggestions = session.query(ICD10CodeDB).filter(
                    ICD10CodeDB.code.ilike(f"{partial_code}%")
                ).limit(limit).all()
            else:  # CPT
                suggestions = session.query(CPTCodeDB).filter(
                    CPTCodeDB.code.ilike(f"{partial_code}%")
                ).limit(limit).all()
            
            return [s.to_dict() for s in suggestions]
            
        except SQLAlchemyError as e:
            raise DatabaseError(f"Failed to get code suggestions: {str(e)}") from e
    
    async def get_fuzzy_code_suggestions(
        self, 
        partial_code: str, 
        code_type: str, 
        limit: int = 10,
        category_filter: Optional[str] = None,
        include_descriptions: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get enhanced code suggestions with fuzzy matching.
        
        Args:
            partial_code: Partial code input
            code_type: Type of code (ICD10 or CPT)
            limit: Maximum number of suggestions
            category_filter: Optional category filter
            include_descriptions: Whether to include descriptions in search
            
        Returns:
            List of enhanced code suggestions with fuzzy matching
        """
        try:
            session = self._get_session()
            
            if code_type == 'ICD10':
                query = session.query(ICD10CodeDB)
                
                # Build fuzzy search conditions
                search_conditions = [
                    ICD10CodeDB.code.ilike(f"{partial_code}%"),  # Exact prefix match
                    ICD10CodeDB.code.ilike(f"%{partial_code}%"),  # Contains match
                ]
                
                if include_descriptions:
                    search_conditions.extend([
                        ICD10CodeDB.description.ilike(f"%{partial_code}%"),
                        ICD10CodeDB.short_description.ilike(f"%{partial_code}%"),
                        ICD10CodeDB.search_terms.ilike(f"%{partial_code}%")
                    ])
                
                query = query.filter(or_(*search_conditions))
                
                if category_filter:
                    query = query.filter(ICD10CodeDB.category == category_filter)
                
                # Order by relevance (exact prefix first, then contains)
                suggestions = query.order_by(
                    ICD10CodeDB.code
                ).limit(limit).all()
                
            else:  # CPT
                query = session.query(CPTCodeDB)
                
                # Build fuzzy search conditions
                search_conditions = [
                    CPTCodeDB.code.ilike(f"{partial_code}%"),  # Exact prefix match
                    CPTCodeDB.code.ilike(f"%{partial_code}%"),  # Contains match
                ]
                
                if include_descriptions:
                    search_conditions.extend([
                        CPTCodeDB.description.ilike(f"%{partial_code}%"),
                        CPTCodeDB.short_description.ilike(f"%{partial_code}%"),
                        CPTCodeDB.search_terms.ilike(f"%{partial_code}%")
                    ])
                
                query = query.filter(or_(*search_conditions))
                
                if category_filter:
                    query = query.filter(CPTCodeDB.category == category_filter)
                
                # Order by relevance (exact prefix first, then contains)
                suggestions = query.order_by(
                    CPTCodeDB.code
                ).limit(limit).all()
            
            # Convert to enhanced suggestion format
            enhanced_suggestions = []
            for suggestion in suggestions:
                suggestion_dict = suggestion.to_dict()
                
                # Add relevance score based on match type
                if suggestion.code.upper().startswith(partial_code.upper()):
                    suggestion_dict['relevance_score'] = 1.0
                elif partial_code.upper() in suggestion.code.upper():
                    suggestion_dict['relevance_score'] = 0.8
                elif include_descriptions and partial_code.upper() in suggestion.description.upper():
                    suggestion_dict['relevance_score'] = 0.6
                else:
                    suggestion_dict['relevance_score'] = 0.4
                
                # Add match type indicator
                if suggestion.code.upper().startswith(partial_code.upper()):
                    suggestion_dict['match_type'] = 'code_prefix'
                elif partial_code.upper() in suggestion.code.upper():
                    suggestion_dict['match_type'] = 'code_contains'
                else:
                    suggestion_dict['match_type'] = 'description_match'
                
                enhanced_suggestions.append(suggestion_dict)
            
            return enhanced_suggestions
            
        except SQLAlchemyError as e:
            raise DatabaseError(f"Failed to get fuzzy code suggestions: {str(e)}") from e
    
    async def delete_icd10_code(self, code_id: int) -> bool:
        """Delete an ICD-10 code."""
        try:
            session = self._get_session()
            
            icd10_code = session.query(ICD10CodeDB).filter(
                ICD10CodeDB.id == code_id
            ).first()
            
            if not icd10_code:
                raise NotFoundError(f"ICD-10 code with ID {code_id} not found")
            
            session.delete(icd10_code)
            session.commit()
            
            return True
            
        except SQLAlchemyError as e:
            session.rollback()
            raise DatabaseError(f"Failed to delete ICD-10 code: {str(e)}") from e
    
    async def delete_cpt_code(self, code_id: int) -> bool:
        """Delete a CPT code."""
        try:
            session = self._get_session()
            
            cpt_code = session.query(CPTCodeDB).filter(
                CPTCodeDB.id == code_id
            ).first()
            
            if not cpt_code:
                raise NotFoundError(f"CPT code with ID {code_id} not found")
            
            session.delete(cpt_code)
            session.commit()
            
            return True
            
        except SQLAlchemyError as e:
            session.rollback()
            raise DatabaseError(f"Failed to delete CPT code: {str(e)}") from e


# Global repository instance
medical_code_repository = MedicalCodeRepository()

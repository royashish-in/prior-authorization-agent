"""
Medical codes API endpoints for Prior Authorization Agent.

This module provides comprehensive REST endpoints for medical code validation,
search, management, and relationship handling for ICD-10 and CPT codes.
"""

import asyncio
from typing import List, Optional, Dict, Any, Union
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, status, Query, Depends, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session

from src.services.medical_code_repository import MedicalCodeRepository
from src.services.medical_code_validator import MedicalCodeValidator, ValidationResult
from src.models.medical_codes import ICD10Code, CPTCode, HCPCSCode
from src.database.connection import get_db_session
from src.core.logging import get_logger
from src.core.exceptions import ValidationError, NotFoundError, DatabaseError

logger = get_logger(__name__)
router = APIRouter(tags=["medical-codes"])

# Initialize services
medical_code_validator = MedicalCodeValidator()


# Pydantic models for API requests/responses

class CodeValidationRequest(BaseModel):
    """Request model for code validation."""
    code: str = Field(..., description="Medical code to validate")
    code_type: str = Field(..., description="Type of code: ICD10, CPT, or HCPCS")
    
    @validator('code_type')
    def validate_code_type(cls, v):
        if v.upper() not in ['ICD10', 'CPT', 'HCPCS']:
            raise ValueError('code_type must be ICD10, CPT, or HCPCS')
        return v.upper()


class CodeValidationResponse(BaseModel):
    """Response model for code validation."""
    code: str
    code_type: str
    valid: bool
    description: Optional[str] = None
    suggestions: List[str] = []
    effective_date: Optional[str] = None
    expiration_date: Optional[str] = None
    error_message: Optional[str] = None


class CodeSearchRequest(BaseModel):
    """Request model for code search."""
    query: str = Field(..., description="Search query")
    code_type: str = Field(..., description="Type of code: ICD10, CPT, or HCPCS")
    category: Optional[str] = Field(None, description="Filter by category")
    limit: int = Field(50, ge=1, le=100, description="Maximum number of results")
    offset: int = Field(0, ge=0, description="Pagination offset")
    
    @validator('code_type')
    def validate_code_type(cls, v):
        if v.upper() not in ['ICD10', 'CPT', 'HCPCS']:
            raise ValueError('code_type must be ICD10, CPT, or HCPCS')
        return v.upper()


class CodeSearchResponse(BaseModel):
    """Response model for code search."""
    results: List[Dict[str, Any]]
    total_count: int
    query: str
    code_type: str
    limit: int
    offset: int


class CodeSuggestionResponse(BaseModel):
    """Response model for code suggestions."""
    suggestions: List[Dict[str, Any]]
    partial_code: str
    code_type: str


class BulkCodeImportRequest(BaseModel):
    """Request model for bulk code import."""
    codes: List[Dict[str, Any]] = Field(..., description="List of codes to import")
    code_type: str = Field(..., description="Type of codes: ICD10 or CPT")
    overwrite_existing: bool = Field(False, description="Whether to overwrite existing codes")
    
    @validator('code_type')
    def validate_code_type(cls, v):
        if v.upper() not in ['ICD10', 'CPT']:
            raise ValueError('code_type must be ICD10 or CPT')
        return v.upper()


class BulkCodeImportResponse(BaseModel):
    """Response model for bulk code import."""
    successful_count: int
    failed_count: int
    errors: List[str]
    total_processed: int


class CodeRelationshipRequest(BaseModel):
    """Request model for creating code relationships."""
    primary_code_id: int = Field(..., description="Primary code ID")
    primary_code_type: str = Field(..., description="Primary code type: ICD10 or CPT")
    related_code_id: int = Field(..., description="Related code ID")
    related_code_type: str = Field(..., description="Related code type: ICD10 or CPT")
    relationship_type: str = Field(..., description="Type of relationship")
    strength: float = Field(1.0, ge=0.0, le=1.0, description="Relationship strength (0.0-1.0)")
    clinical_rationale: Optional[str] = Field(None, description="Clinical reasoning")
    
    @validator('primary_code_type', 'related_code_type')
    def validate_code_type(cls, v):
        if v.upper() not in ['ICD10', 'CPT']:
            raise ValueError('code_type must be ICD10 or CPT')
        return v.upper()
    
    @validator('relationship_type')
    def validate_relationship_type(cls, v):
        valid_types = ['contraindicated', 'recommended', 'alternative', 'prerequisite', 'followup']
        if v.lower() not in valid_types:
            raise ValueError(f'relationship_type must be one of: {valid_types}')
        return v.lower()


class CodeRelationshipResponse(BaseModel):
    """Response model for code relationships."""
    relationships: List[Dict[str, Any]]
    code_id: int
    code_type: str


def get_repository() -> MedicalCodeRepository:
    """Get medical code repository dependency."""
    return MedicalCodeRepository()


# API Endpoints

@router.post("/validate", response_model=CodeValidationResponse)
async def validate_medical_code(
    request: CodeValidationRequest
) -> CodeValidationResponse:
    """
    Validate a single medical code.
    
    Validates the format and existence of ICD-10, CPT, or HCPCS codes
    and provides suggestions if the code is invalid.
    """
    try:
        logger.info(f"Validating {request.code_type} code: {request.code}")
        
        # Create appropriate code object
        if request.code_type == 'ICD10':
            code_obj = ICD10Code(code=request.code)
            validation_result = await medical_code_validator.validate_icd10_code(code_obj)
        elif request.code_type == 'CPT':
            code_obj = CPTCode(code=request.code)
            validation_result = await medical_code_validator.validate_cpt_code(code_obj)
        else:  # HCPCS
            code_obj = HCPCSCode(code=request.code)
            validation_result = await medical_code_validator.validate_hcpcs_code(code_obj)
        
        # Convert validation result to response
        response = CodeValidationResponse(
            code=validation_result.code,
            code_type=request.code_type,
            valid=validation_result.result.value == "valid",
            description=validation_result.description,
            suggestions=validation_result.suggestions,
            effective_date=validation_result.effective_date.isoformat() if validation_result.effective_date else None,
            expiration_date=validation_result.expiration_date.isoformat() if validation_result.expiration_date else None,
            error_message=None if validation_result.result.value == "valid" else f"Invalid {request.code_type} code"
        )
        
        logger.info(f"Code validation completed: {request.code} - {validation_result.result.value}")
        return response
        
    except Exception as e:
        logger.error(f"Error validating code {request.code}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error validating code: {str(e)}"
        )


@router.post("/validate/batch")
async def validate_codes_batch(
    codes: List[CodeValidationRequest]
) -> Dict[str, CodeValidationResponse]:
    """
    Validate multiple medical codes in batch for better performance.
    
    Accepts a list of codes and returns validation results for each.
    """
    try:
        logger.info(f"Batch validating {len(codes)} codes")
        
        # Prepare codes for batch validation
        code_tuples = [(req.code_type, req.code) for req in codes]
        
        # Perform batch validation
        validation_results = await medical_code_validator.validate_codes_batch(code_tuples)
        
        # Convert results to response format
        responses = {}
        for req in codes:
            validation_result = validation_results.get(req.code)
            if validation_result:
                responses[req.code] = CodeValidationResponse(
                    code=validation_result.code,
                    code_type=req.code_type,
                    valid=validation_result.result.value == "valid",
                    description=validation_result.description,
                    suggestions=validation_result.suggestions,
                    effective_date=validation_result.effective_date.isoformat() if validation_result.effective_date else None,
                    expiration_date=validation_result.expiration_date.isoformat() if validation_result.expiration_date else None,
                    error_message=None if validation_result.result.value == "valid" else f"Invalid {req.code_type} code"
                )
        
        logger.info(f"Batch validation completed for {len(responses)} codes")
        return responses
        
    except Exception as e:
        logger.error(f"Error in batch validation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error in batch validation: {str(e)}"
        )


@router.get("/search", response_model=CodeSearchResponse)
async def search_medical_codes(
    query: str = Query(..., description="Search query"),
    code_type: str = Query(..., description="Type of code: ICD10, CPT, or HCPCS"),
    category: Optional[str] = Query(None, description="Filter by category"),
    billable_only: bool = Query(False, description="Only return billable codes (ICD-10 only)"),
    prior_auth_only: bool = Query(False, description="Only return codes requiring prior auth (CPT only)"),
    valid_only: bool = Query(True, description="Only return currently valid codes"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    repository: MedicalCodeRepository = Depends(get_repository)
) -> CodeSearchResponse:
    """
    Search medical codes with fuzzy matching and filtering.
    
    Supports full-text search across code descriptions and provides
    filtering options based on code properties.
    """
    try:
        logger.info(f"Searching {code_type} codes with query: {query}")
        
        code_type = code_type.upper()
        if code_type not in ['ICD10', 'CPT', 'HCPCS']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="code_type must be ICD10, CPT, or HCPCS"
            )
        
        if code_type == 'ICD10':
            results, total_count = await repository.search_icd10_codes(
                query=query,
                category=category,
                billable_only=billable_only,
                valid_only=valid_only,
                limit=limit,
                offset=offset
            )
            results_dict = [result.to_dict() for result in results]
        elif code_type in ['CPT', 'HCPCS']:
            results, total_count = await repository.search_cpt_codes(
                query=query,
                category=category,
                prior_auth_only=prior_auth_only,
                valid_only=valid_only,
                limit=limit,
                offset=offset
            )
            results_dict = [result.to_dict() for result in results]
        
        response = CodeSearchResponse(
            results=results_dict,
            total_count=total_count,
            query=query,
            code_type=code_type,
            limit=limit,
            offset=offset
        )
        
        logger.info(f"Search completed: {total_count} total results, {len(results_dict)} returned")
        return response
        
    except Exception as e:
        logger.error(f"Error searching codes: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching codes: {str(e)}"
        )


@router.get("/suggestions", response_model=CodeSuggestionResponse)
async def get_code_suggestions(
    partial_code: str = Query(..., description="Partial code input"),
    code_type: str = Query(..., description="Type of code: ICD10, CPT, or HCPCS"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of suggestions"),
    fuzzy_match: bool = Query(True, description="Enable fuzzy matching for suggestions"),
    include_descriptions: bool = Query(True, description="Include code descriptions in suggestions"),
    category_filter: Optional[str] = Query(None, description="Filter suggestions by category")
) -> CodeSuggestionResponse:
    """
    Get real-time code suggestions with enhanced fuzzy matching.
    
    Provides intelligent code completion and suggestions as users type,
    with advanced fuzzy matching capabilities to handle typos and variations.
    Supports filtering by category and includes detailed descriptions.
    """
    repository = MedicalCodeRepository()
    try:
        logger.info(f"Getting enhanced suggestions for {code_type} partial code: {partial_code}")
        
        code_type = code_type.upper()
        if code_type not in ['ICD10', 'CPT', 'HCPCS']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="code_type must be ICD10, CPT, or HCPCS"
            )
        
        # Get enhanced suggestions from repository with fuzzy matching
        if fuzzy_match:
            suggestions = await repository.get_fuzzy_code_suggestions(
                partial_code, code_type, limit, category_filter, include_descriptions
            )
        else:
            suggestions = await repository.get_code_suggestions(partial_code, code_type, limit)
        
        response = CodeSuggestionResponse(
            suggestions=suggestions,
            partial_code=partial_code,
            code_type=code_type
        )
        
        logger.info(f"Returned {len(suggestions)} enhanced suggestions for {partial_code}")
        return response
        
    except Exception as e:
        logger.error(f"Error getting code suggestions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting code suggestions: {str(e)}"
        )


@router.post("/bulk/import", response_model=BulkCodeImportResponse)
async def bulk_import_codes(
    request: BulkCodeImportRequest,
    repository: MedicalCodeRepository = Depends(get_repository)
) -> BulkCodeImportResponse:
    """
    Bulk import medical codes for administrative functions.
    
    Allows administrators to import large numbers of codes from
    external sources or update existing code databases.
    """
    try:
        logger.info(f"Bulk importing {len(request.codes)} {request.code_type} codes")
        
        if request.code_type == 'ICD10':
            successful_count, errors = await repository.bulk_create_icd10_codes(request.codes)
        else:  # CPT
            successful_count, errors = await repository.bulk_create_cpt_codes(request.codes)
        
        failed_count = len(request.codes) - successful_count
        
        response = BulkCodeImportResponse(
            successful_count=successful_count,
            failed_count=failed_count,
            errors=errors,
            total_processed=len(request.codes)
        )
        
        logger.info(f"Bulk import completed: {successful_count} successful, {failed_count} failed")
        return response
        
    except Exception as e:
        logger.error(f"Error in bulk import: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error in bulk import: {str(e)}"
        )


@router.post("/bulk/import/file")
async def bulk_import_codes_from_file(
    file: UploadFile = File(...),
    code_type: str = Query(..., description="Type of codes: ICD10 or CPT"),
    overwrite_existing: bool = Query(False, description="Whether to overwrite existing codes"),
    repository: MedicalCodeRepository = Depends(get_repository)
) -> BulkCodeImportResponse:
    """
    Bulk import medical codes from uploaded file (CSV or JSON).
    
    Supports importing codes from standard healthcare data formats
    for easy integration with external code databases.
    """
    try:
        logger.info(f"Bulk importing {code_type} codes from file: {file.filename}")
        
        code_type = code_type.upper()
        if code_type not in ['ICD10', 'CPT']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="code_type must be ICD10 or CPT"
            )
        
        # Read file content
        content = await file.read()
        
        # Parse file based on extension
        if file.filename.endswith('.json'):
            import json
            codes_data = json.loads(content.decode('utf-8'))
        elif file.filename.endswith('.csv'):
            import csv
            import io
            
            # Parse CSV file
            csv_reader = csv.DictReader(io.StringIO(content.decode('utf-8')))
            codes_data = list(csv_reader)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be JSON or CSV format"
            )
        
        # Import codes
        if code_type == 'ICD10':
            successful_count, errors = await repository.bulk_create_icd10_codes(codes_data)
        else:  # CPT
            successful_count, errors = await repository.bulk_create_cpt_codes(codes_data)
        
        failed_count = len(codes_data) - successful_count
        
        response = BulkCodeImportResponse(
            successful_count=successful_count,
            failed_count=failed_count,
            errors=errors,
            total_processed=len(codes_data)
        )
        
        logger.info(f"File import completed: {successful_count} successful, {failed_count} failed")
        return response
        
    except Exception as e:
        logger.error(f"Error importing from file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error importing from file: {str(e)}"
        )


@router.get("/relationships/{code_id}")
async def get_code_relationships(
    code_id: int,
    code_type: str = Query(..., description="Type of code: ICD10 or CPT"),
    relationship_type: Optional[str] = Query(None, description="Filter by relationship type"),
    active_only: bool = Query(True, description="Only return active relationships"),
    include_details: bool = Query(True, description="Include detailed code information"),
    repository: MedicalCodeRepository = Depends(get_repository)
) -> CodeRelationshipResponse:
    """
    Get relationships for a specific medical code with enhanced details.
    
    Returns contraindications, alternatives, and other clinical relationships
    that help inform medical decision-making, with detailed code information.
    """
    try:
        logger.info(f"Getting relationships for {code_type} code ID: {code_id}")
        
        code_type = code_type.upper()
        if code_type not in ['ICD10', 'CPT']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="code_type must be ICD10 or CPT"
            )
        
        relationships = await repository.get_code_relationships(
            code_id=code_id,
            code_type=code_type,
            relationship_type=relationship_type,
            active_only=active_only
        )
        
        relationships_dict = []
        for rel in relationships:
            rel_dict = rel.to_dict()
            
            # Add detailed code information if requested
            if include_details:
                # Get primary code details
                if rel.primary_code_type == 'ICD10':
                    primary_code = await repository.get_icd10_code_by_id(rel.primary_code_id)
                else:
                    primary_code = await repository.get_cpt_code_by_id(rel.primary_code_id)
                
                # Get related code details
                if rel.related_code_type == 'ICD10':
                    related_code = await repository.get_icd10_code_by_id(rel.related_code_id)
                else:
                    related_code = await repository.get_cpt_code_by_id(rel.related_code_id)
                
                rel_dict['primary_code_details'] = primary_code.to_dict() if primary_code else None
                rel_dict['related_code_details'] = related_code.to_dict() if related_code else None
            
            relationships_dict.append(rel_dict)
        
        response = CodeRelationshipResponse(
            relationships=relationships_dict,
            code_id=code_id,
            code_type=code_type
        )
        
        logger.info(f"Found {len(relationships_dict)} relationships for code {code_id}")
        return response
        
    except Exception as e:
        logger.error(f"Error getting code relationships: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting code relationships: {str(e)}"
        )


@router.get("/contraindications/{code_id}")
async def get_code_contraindications(
    code_id: int,
    code_type: str = Query(..., description="Type of code: ICD10 or CPT"),
    severity_threshold: float = Query(0.5, ge=0.0, le=1.0, description="Minimum severity threshold")
) -> Dict[str, Any]:
    """
    Get contraindications for a specific medical code.
    
    Returns codes that are contraindicated with the specified code,
    helping to identify potential conflicts in treatment plans.
    """
    repository = MedicalCodeRepository()
    try:
        logger.info(f"Getting contraindications for {code_type} code ID: {code_id}")
        
        code_type = code_type.upper()
        if code_type not in ['ICD10', 'CPT']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="code_type must be ICD10 or CPT"
            )
        
        relationships = await repository.get_code_relationships(
            code_id=code_id,
            code_type=code_type,
            relationship_type='contraindicated',
            active_only=True
        )
        
        # Filter by severity threshold
        contraindications = []
        for rel in relationships:
            if rel.strength >= severity_threshold:
                rel_dict = rel.to_dict()
                
                # Get contraindicated code details
                if rel.related_code_type == 'ICD10':
                    contraindicated_code = await repository.get_icd10_code_by_id(rel.related_code_id)
                else:
                    contraindicated_code = await repository.get_cpt_code_by_id(rel.related_code_id)
                
                rel_dict['contraindicated_code'] = contraindicated_code.to_dict() if contraindicated_code else None
                contraindications.append(rel_dict)
        
        return {
            'code_id': code_id,
            'code_type': code_type,
            'contraindications': contraindications,
            'total_count': len(contraindications),
            'severity_threshold': severity_threshold
        }
        
    except Exception as e:
        logger.error(f"Error getting contraindications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting contraindications: {str(e)}"
        )


@router.get("/alternatives/{code_id}")
async def get_code_alternatives(
    code_id: int,
    code_type: str = Query(..., description="Type of code: ICD10 or CPT"),
    min_confidence: float = Query(0.7, ge=0.0, le=1.0, description="Minimum confidence threshold"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of alternatives")
) -> Dict[str, Any]:
    """
    Get alternative codes for a specific medical code.
    
    Returns alternative codes that can be used instead of the specified code,
    helping with treatment planning and authorization alternatives.
    """
    repository = MedicalCodeRepository()
    try:
        logger.info(f"Getting alternatives for {code_type} code ID: {code_id}")
        
        code_type = code_type.upper()
        if code_type not in ['ICD10', 'CPT']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="code_type must be ICD10 or CPT"
            )
        
        relationships = await repository.get_code_relationships(
            code_id=code_id,
            code_type=code_type,
            relationship_type='alternative',
            active_only=True
        )
        
        # Filter by confidence and sort by strength
        alternatives = []
        for rel in relationships:
            if rel.confidence >= min_confidence:
                rel_dict = rel.to_dict()
                
                # Get alternative code details
                if rel.related_code_type == 'ICD10':
                    alternative_code = await repository.get_icd10_code_by_id(rel.related_code_id)
                else:
                    alternative_code = await repository.get_cpt_code_by_id(rel.related_code_id)
                
                rel_dict['alternative_code'] = alternative_code.to_dict() if alternative_code else None
                alternatives.append(rel_dict)
        
        # Sort by strength (highest first) and limit results
        alternatives.sort(key=lambda x: x['strength'], reverse=True)
        alternatives = alternatives[:limit]
        
        return {
            'code_id': code_id,
            'code_type': code_type,
            'alternatives': alternatives,
            'total_count': len(alternatives),
            'min_confidence': min_confidence,
            'limit': limit
        }
        
    except Exception as e:
        logger.error(f"Error getting alternatives: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting alternatives: {str(e)}"
        )


@router.post("/relationships", response_model=Dict[str, Any])
async def create_code_relationship(
    request: CodeRelationshipRequest,
    repository: MedicalCodeRepository = Depends(get_repository)
) -> Dict[str, Any]:
    """
    Create a new relationship between medical codes.
    
    Allows administrators to define clinical relationships like
    contraindications and alternatives between codes.
    """
    try:
        logger.info(f"Creating relationship: {request.primary_code_id}:{request.primary_code_type} -> {request.related_code_id}:{request.related_code_type}")
        
        relationship_data = {
            'primary_code_id': request.primary_code_id,
            'primary_code_type': request.primary_code_type,
            'related_code_id': request.related_code_id,
            'related_code_type': request.related_code_type,
            'relationship_type': request.relationship_type,
            'strength': request.strength,
            'clinical_rationale': request.clinical_rationale
        }
        
        relationship = await repository.create_code_relationship(relationship_data)
        
        logger.info(f"Created relationship with ID: {relationship.id}")
        return {
            'id': relationship.id,
            'message': 'Relationship created successfully',
            'relationship': relationship.to_dict()
        }
        
    except ValidationError as e:
        logger.error(f"Validation error creating relationship: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating code relationship: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating code relationship: {str(e)}"
        )


@router.get("/stats")
async def get_medical_codes_stats(
    repository: MedicalCodeRepository = Depends(get_repository)
) -> Dict[str, Any]:
    """
    Get statistics about the medical codes database.
    
    Provides information about code counts, validation cache performance,
    and system health metrics.
    """
    try:
        logger.info("Getting medical codes statistics")
        
        # Get cache stats from validator
        cache_stats = medical_code_validator.get_cache_stats()
        
        # TODO: Add database statistics when repository methods are available
        # For now, return cache stats and basic info
        stats = {
            'cache_statistics': cache_stats,
            'database_statistics': {
                'icd10_codes': 'Available via search endpoint',
                'cpt_codes': 'Available via search endpoint',
                'relationships': 'Available via relationships endpoint'
            },
            'system_info': {
                'validator_initialized': True,
                'repository_available': True
            }
        }
        
        logger.info("Medical codes statistics retrieved")
        return stats
        
    except Exception as e:
        logger.error(f"Error getting medical codes stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting statistics: {str(e)}"
        )


@router.post("/bulk/export")
async def bulk_export_codes(
    code_type: str = Query(..., description="Type of codes to export: ICD10 or CPT"),
    format: str = Query("json", description="Export format: json or csv"),
    category: Optional[str] = Query(None, description="Filter by category"),
    valid_only: bool = Query(True, description="Only export currently valid codes")
) -> Dict[str, Any]:
    """
    Bulk export medical codes for administrative functions.
    
    Allows administrators to export codes in various formats for
    backup, analysis, or integration with external systems.
    """
    repository = MedicalCodeRepository()
    try:
        logger.info(f"Bulk exporting {code_type} codes in {format} format")
        
        code_type = code_type.upper()
        if code_type not in ['ICD10', 'CPT']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="code_type must be ICD10 or CPT"
            )
        
        # Get codes for export
        if code_type == 'ICD10':
            codes, total_count = await repository.search_icd10_codes(
                query="",
                category=category,
                valid_only=valid_only,
                limit=10000,  # Large limit for export
                offset=0
            )
        else:  # CPT
            codes, total_count = await repository.search_cpt_codes(
                query="",
                category=category,
                valid_only=valid_only,
                limit=10000,  # Large limit for export
                offset=0
            )
        
        codes_data = [code.to_dict() for code in codes]
        
        if format.lower() == 'csv':
            # Convert to CSV format
            import csv
            import io
            
            output = io.StringIO()
            if codes_data:
                writer = csv.DictWriter(output, fieldnames=codes_data[0].keys())
                writer.writeheader()
                writer.writerows(codes_data)
            
            csv_content = output.getvalue()
            output.close()
            
            return {
                'format': 'csv',
                'content': csv_content,
                'total_exported': len(codes_data),
                'export_timestamp': datetime.utcnow().isoformat()
            }
        else:
            # JSON format
            return {
                'format': 'json',
                'codes': codes_data,
                'total_exported': len(codes_data),
                'export_timestamp': datetime.utcnow().isoformat()
            }
        
    except Exception as e:
        logger.error(f"Error in bulk export: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error in bulk export: {str(e)}"
        )


@router.put("/bulk/update")
async def bulk_update_codes(
    code_type: str = Query(..., description="Type of codes to update: ICD10 or CPT"),
    updates: List[Dict[str, Any]] = ...,
    repository: MedicalCodeRepository = Depends(get_repository)
) -> Dict[str, Any]:
    """
    Bulk update medical codes for administrative functions.
    
    Allows administrators to update multiple codes simultaneously,
    useful for applying systematic changes or corrections.
    """
    try:
        logger.info(f"Bulk updating {len(updates)} {code_type} codes")
        
        code_type = code_type.upper()
        if code_type not in ['ICD10', 'CPT']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="code_type must be ICD10 or CPT"
            )
        
        successful_updates = 0
        failed_updates = 0
        errors = []
        
        for update_data in updates:
            try:
                code_id = update_data.get('id')
                if not code_id:
                    errors.append("Missing 'id' field in update data")
                    failed_updates += 1
                    continue
                
                # Remove id from update data
                update_fields = {k: v for k, v in update_data.items() if k != 'id'}
                
                if code_type == 'ICD10':
                    await repository.update_icd10_code(code_id, update_fields)
                else:  # CPT
                    await repository.update_cpt_code(code_id, update_fields)
                
                successful_updates += 1
                
            except Exception as e:
                errors.append(f"Error updating code ID {update_data.get('id', 'unknown')}: {str(e)}")
                failed_updates += 1
        
        return {
            'successful_updates': successful_updates,
            'failed_updates': failed_updates,
            'total_processed': len(updates),
            'errors': errors,
            'update_timestamp': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in bulk update: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error in bulk update: {str(e)}"
        )


@router.delete("/bulk/delete")
async def bulk_delete_codes(
    code_type: str = Query(..., description="Type of codes to delete: ICD10 or CPT"),
    code_ids: List[int] = ...,
    repository: MedicalCodeRepository = Depends(get_repository)
) -> Dict[str, Any]:
    """
    Bulk delete medical codes for administrative functions.
    
    Allows administrators to delete multiple codes simultaneously.
    Use with caution as this operation cannot be undone.
    """
    try:
        logger.info(f"Bulk deleting {len(code_ids)} {code_type} codes")
        
        code_type = code_type.upper()
        if code_type not in ['ICD10', 'CPT']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="code_type must be ICD10 or CPT"
            )
        
        successful_deletes = 0
        failed_deletes = 0
        errors = []
        
        for code_id in code_ids:
            try:
                if code_type == 'ICD10':
                    await repository.delete_icd10_code(code_id)
                else:  # CPT
                    await repository.delete_cpt_code(code_id)
                
                successful_deletes += 1
                
            except Exception as e:
                errors.append(f"Error deleting code ID {code_id}: {str(e)}")
                failed_deletes += 1
        
        return {
            'successful_deletes': successful_deletes,
            'failed_deletes': failed_deletes,
            'total_processed': len(code_ids),
            'errors': errors,
            'delete_timestamp': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in bulk delete: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error in bulk delete: {str(e)}"
        )


@router.delete("/cache")
async def clear_validation_cache() -> Dict[str, str]:
    """
    Clear the medical code validation cache.
    
    Administrative endpoint to clear cached validation results,
    useful after code database updates.
    """
    try:
        logger.info("Clearing medical code validation cache")
        
        medical_code_validator.clear_cache()
        
        logger.info("Medical code validation cache cleared")
        return {'message': 'Validation cache cleared successfully'}
        
    except Exception as e:
        logger.error(f"Error clearing cache: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error clearing cache: {str(e)}"
        )
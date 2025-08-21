"""
Focused tests for Medical Code Repository to increase coverage.

This module provides targeted testing for the medical code repository
focusing on the most commonly used methods to maximize coverage impact.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, date
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from src.services.medical_code_repository import MedicalCodeRepository
from src.models.medical_codes import ICD10CodeDB, CPTCodeDB


@pytest.fixture
def mock_session():
    """Create mock database session."""
    session = Mock(spec=Session)
    session.query = Mock()
    session.query.return_value = session
    session.filter = Mock()
    session.filter.return_value = session
    session.filter_by = Mock()
    session.filter_by.return_value = session
    session.first = Mock()
    session.first.return_value = None
    session.all = Mock()
    session.all.return_value = []
    session.limit = Mock()
    session.limit.return_value = session
    session.order_by = Mock()
    session.order_by.return_value = session
    session.join = Mock()
    session.join.return_value = session
    session.distinct = Mock()
    session.distinct.return_value = session
    session.add = Mock()
    session.commit = Mock()
    session.rollback = Mock()
    session.close = Mock()
    return session


@pytest.fixture
def sample_icd10():
    """Create sample ICD-10 code."""
    return ICD10CodeDB(
        code="G93.1",
        description="Anoxic brain damage, not elsewhere classified",
        category="Diseases of the nervous system",
        subcategory="Other disorders of brain",
        chapter="Diseases of the nervous system and sense organs",
        billable=True,
        valid_from=date(2015, 10, 1)
    )


@pytest.fixture
def sample_cpt():
    """Create sample CPT code."""
    return CPTCodeDB(
        code="70551",
        description="Magnetic resonance (eg, proton) imaging, brain (including brain stem); without contrast material",
        category="Radiology",
        subcategory="Diagnostic Radiology (Diagnostic Imaging)",
        section="Nervous System",
        work_rvu=2.5,
        practice_expense_rvu=2.0,
        malpractice_rvu=1.0,
        total_rvu=5.5,
        valid_from=date(2020, 1, 1)
    )


class TestMedicalCodeRepositoryCore:
    """Test core functionality of medical code repository."""
    
    def test_init_basic(self):
        """Test basic initialization."""
        repo = MedicalCodeRepository()
        assert repo.db_session is None
    
    def test_init_with_session(self, mock_session):
        """Test initialization with session."""
        repo = MedicalCodeRepository(db_session=mock_session)
        assert repo.db_session == mock_session
    
    def test_get_session_with_provided(self, mock_session):
        """Test _get_session with provided session."""
        repo = MedicalCodeRepository(db_session=mock_session)
        session = repo._get_session()
        assert session == mock_session
    
    @patch('src.database.connection.get_database_manager')
    def test_get_session_without_provided(self, mock_get_db_manager):
        """Test _get_session without provided session."""
        mock_db_manager = Mock()
        mock_session = Mock()
        mock_db_manager.session_factory.return_value = mock_session
        mock_get_db_manager.return_value = mock_db_manager
        
        repo = MedicalCodeRepository()
        session = repo._get_session()
        
        assert session == mock_session
        mock_get_db_manager.assert_called_once()


class TestICD10Operations:
    """Test ICD-10 code operations."""
    
    @patch.object(MedicalCodeRepository, '_get_session')
    @pytest.mark.asyncio

    async def test_get_icd10_code_by_code_success(self, mock_get_session, sample_icd10):
        """Test successful ICD-10 code retrieval by code."""
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = sample_icd10
        
        repo = MedicalCodeRepository()
        result = await repo.get_icd10_code_by_code("G93.1")
        
        assert result == sample_icd10
        mock_session.query.assert_called_with(ICD10CodeDB)
    
    @patch.object(MedicalCodeRepository, '_get_session')
    @pytest.mark.asyncio

    async def test_get_icd10_code_by_code_not_found(self, mock_get_session):
        """Test ICD-10 code retrieval when not found."""
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = None
        
        repo = MedicalCodeRepository()
        result = await repo.get_icd10_code_by_code("INVALID")
        
        assert result is None
    
    @patch.object(MedicalCodeRepository, '_get_session')
    @pytest.mark.asyncio

    async def test_get_icd10_code_by_code_database_error(self, mock_get_session):
        """Test ICD-10 code retrieval with database error."""
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        mock_session.query.side_effect = SQLAlchemyError("Database error")
        
        repo = MedicalCodeRepository()
        
        with pytest.raises(Exception):
            await repo.get_icd10_code_by_code("G93.1")
    
    @patch.object(MedicalCodeRepository, '_get_session')
    @pytest.mark.asyncio

    async def test_search_icd10_codes_success(self, mock_get_session, sample_icd10):
        """Test successful ICD-10 code search."""
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        mock_session.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [sample_icd10]
        mock_session.query.return_value.count.return_value = 1
        
        repo = MedicalCodeRepository()
        results, total = await repo.search_icd10_codes("brain", limit=10)
        
        assert len(results) == 1
        assert results[0] == sample_icd10
        assert total == 1


class TestCPTOperations:
    """Test CPT code operations."""
    
    @patch.object(MedicalCodeRepository, '_get_session')
    @pytest.mark.asyncio

    async def test_get_cpt_code_by_code_success(self, mock_get_session, sample_cpt):
        """Test successful CPT code retrieval by code."""
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = sample_cpt
        
        repo = MedicalCodeRepository()
        result = await repo.get_cpt_code_by_code("70551")
        
        assert result == sample_cpt
        mock_session.query.assert_called_with(CPTCodeDB)
    
    @patch.object(MedicalCodeRepository, '_get_session')
    @pytest.mark.asyncio

    async def test_get_cpt_code_by_code_not_found(self, mock_get_session):
        """Test CPT code retrieval when not found."""
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = None
        
        repo = MedicalCodeRepository()
        result = await repo.get_cpt_code_by_code("99999")
        
        assert result is None
    
    @patch.object(MedicalCodeRepository, '_get_session')
    @pytest.mark.asyncio

    async def test_search_cpt_codes_success(self, mock_get_session, sample_cpt):
        """Test successful CPT code search."""
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        mock_session.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [sample_cpt]
        mock_session.query.return_value.count.return_value = 1
        
        repo = MedicalCodeRepository()
        results, total = await repo.search_cpt_codes("MRI", limit=10)
        
        assert len(results) == 1
        assert results[0] == sample_cpt
        assert total == 1


class TestCodeValidation:
    """Test code validation functionality."""
    
    def test_validate_code_icd10_valid(self):
        """Test ICD-10 code validation for valid codes."""
        repo = MedicalCodeRepository()
        
        valid_codes = ["G93.1", "A00.0", "Z99.89", "S72.001A"]
        
        for code in valid_codes:
            result = repo.validate_code(code, "ICD10")
            assert result is True
    
    def test_validate_code_icd10_invalid(self):
        """Test ICD-10 code validation for invalid codes."""
        repo = MedicalCodeRepository()
        
        invalid_codes = ["G93", "G93.1.2", "INVALID", "123", ""]
        
        for code in invalid_codes:
            result = repo.validate_code(code, "ICD10")
            assert result is False
    
    def test_validate_code_cpt_valid(self):
        """Test CPT code validation for valid codes."""
        repo = MedicalCodeRepository()
        
        valid_codes = ["70551", "99213", "00100", "99999"]
        
        for code in valid_codes:
            result = repo.validate_code(code, "CPT")
            assert result is True
    
    def test_validate_code_cpt_invalid(self):
        """Test CPT code validation for invalid codes."""
        repo = MedicalCodeRepository()
        
        invalid_codes = ["7055", "705511", "INVALID", "G93.1", ""]
        
        for code in invalid_codes:
            result = repo.validate_code(code, "CPT")
            assert result is False
    
    def test_validate_code_unknown_type(self):
        """Test code validation for unknown code type."""
        repo = MedicalCodeRepository()
        
        result = repo.validate_code("70551", "UNKNOWN")
        assert result is False


class TestCodeSuggestions:
    """Test code suggestion functionality."""
    
    @patch.object(MedicalCodeRepository, '_get_session')
    def test_get_code_suggestions_icd10(self, mock_get_session, sample_icd10):
        """Test code suggestions for ICD-10 codes."""
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        mock_session.query.return_value.filter.return_value.limit.return_value.all.return_value = [sample_icd10]
        
        repo = MedicalCodeRepository()
        suggestions = repo.get_code_suggestions("G93", "ICD10", limit=5)
        
        assert len(suggestions) == 1
        assert suggestions[0] == sample_icd10
    
    @patch.object(MedicalCodeRepository, '_get_session')
    def test_get_code_suggestions_cpt(self, mock_get_session, sample_cpt):
        """Test code suggestions for CPT codes."""
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        mock_session.query.return_value.filter.return_value.limit.return_value.all.return_value = [sample_cpt]
        
        repo = MedicalCodeRepository()
        suggestions = repo.get_code_suggestions("705", "CPT", limit=5)
        
        assert len(suggestions) == 1
        assert suggestions[0] == sample_cpt
    
    def test_get_code_suggestions_invalid_type(self):
        """Test code suggestions with invalid code type."""
        repo = MedicalCodeRepository()
        
        suggestions = repo.get_code_suggestions("123", "INVALID", limit=5)
        
        assert suggestions == []
    
    def test_get_code_suggestions_empty_partial(self):
        """Test code suggestions with empty partial code."""
        repo = MedicalCodeRepository()
        
        suggestions = repo.get_code_suggestions("", "ICD10", limit=5)
        
        assert suggestions == []


class TestImportAndBasicFunctionality:
    """Test basic import and functionality."""
    
    def test_medical_code_repository_import(self):
        """Test that MedicalCodeRepository can be imported."""
        from src.services.medical_code_repository import MedicalCodeRepository
        assert MedicalCodeRepository is not None
    
    def test_repository_has_expected_methods(self):
        """Test that repository has expected methods."""
        repo = MedicalCodeRepository()
        
        # Test core methods exist
        assert hasattr(repo, 'get_icd10_code_by_code')
        assert hasattr(repo, 'get_cpt_code_by_code')
        assert hasattr(repo, 'search_icd10_codes')
        assert hasattr(repo, 'search_cpt_codes')
        assert hasattr(repo, 'get_code_suggestions')
        assert hasattr(repo, 'validate_code')
        
        # Test methods are callable
        assert callable(repo.get_icd10_code_by_code)
        assert callable(repo.get_cpt_code_by_code)
        assert callable(repo.search_icd10_codes)
        assert callable(repo.search_cpt_codes)
        assert callable(repo.get_code_suggestions)
        assert callable(repo.validate_code)
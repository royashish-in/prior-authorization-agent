"""
Database module for the Prior Authorization Agent.

This module provides SQLAlchemy models, database connection management,
and migration support for the healthcare authorization system.
"""

from .models import (
    Base,
    AuthorizationRequestDB,
    AuthorizationDecisionDB,
    CoveragePolicyDB
)
from .connection import (
    DatabaseManager,
    get_database_manager,
    get_session
)

__all__ = [
    "Base",
    "AuthorizationRequestDB", 
    "AuthorizationDecisionDB",
    "CoveragePolicyDB",
    "DatabaseManager",
    "get_database_manager",
    "get_session"
]
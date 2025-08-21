"""
SQLAlchemy base class for database models.

This module provides the declarative base class that all database models
should inherit from to avoid circular import issues.
"""

from sqlalchemy.orm import declarative_base

# Create the declarative base class
Base = declarative_base()
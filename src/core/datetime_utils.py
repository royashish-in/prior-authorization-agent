"""
Datetime utilities for Prior Authorization Agent.

Provides timezone-aware datetime functions to replace deprecated datetime.now(timezone.utc).
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """
    Get current UTC datetime with timezone awareness.
    
    This replaces the deprecated datetime.now(timezone.utc) function.
    
    Returns:
        Current UTC datetime with timezone information
    """
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    """
    Get current UTC datetime as ISO format string.
    
    Returns:
        Current UTC datetime in ISO format
    """
    return utcnow().isoformat()
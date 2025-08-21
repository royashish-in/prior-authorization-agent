"""
Bcrypt Compatibility Module

This module provides a compatibility layer for bcrypt to suppress version detection warnings
that occur with newer bcrypt versions and passlib.
"""

import warnings
import sys
import os
from typing import Any


def suppress_bcrypt_warnings():
    """Suppress bcrypt version detection warnings."""
    # Filter out the specific bcrypt warning
    warnings.filterwarnings(
        "ignore",
        message=".*bcrypt.*version.*",
        category=UserWarning,
        module="passlib.*",
    )

    # Filter out passlib warnings about bcrypt
    warnings.filterwarnings(
        "ignore", message=".*error reading bcrypt version.*", category=UserWarning
    )

    # Filter out any bcrypt-related warnings
    warnings.filterwarnings(
        "ignore", message=".*trapped.*error.*bcrypt.*", category=UserWarning
    )


def fix_bcrypt_module():
    """Fix bcrypt module to have the expected structure."""
    try:
        import bcrypt

        # Get the actual version
        actual_version = getattr(bcrypt, "__version__", "4.0.1")

        # Create a proper __about__ module if it doesn't exist
        if not hasattr(bcrypt, "__about__"):

            class MockAbout:
                __version__ = actual_version
                __title__ = "bcrypt"
                __description__ = (
                    "Modern password hashing for your software and your servers"
                )

            bcrypt.__about__ = MockAbout()

        # Ensure __about__ has __version__
        elif not hasattr(bcrypt.__about__, "__version__"):
            bcrypt.__about__.__version__ = actual_version

        # Ensure the module itself has __version__
        if not hasattr(bcrypt, "__version__"):
            bcrypt.__version__ = actual_version

    except ImportError:
        # bcrypt not installed, ignore
        pass


# Apply fixes immediately when this module is imported
suppress_bcrypt_warnings()
fix_bcrypt_module()


def get_bcrypt_version() -> str:
    """Get bcrypt version safely."""
    try:
        import bcrypt

        if hasattr(bcrypt, "__version__"):
            return bcrypt.__version__
        elif hasattr(bcrypt, "__about__") and hasattr(bcrypt.__about__, "__version__"):
            return bcrypt.__about__.__version__
        else:
            return "unknown"
    except ImportError:
        return "not installed"


def initialize_bcrypt_compat():
    """Initialize bcrypt compatibility fixes."""
    suppress_bcrypt_warnings()
    fix_bcrypt_module()

    # Additional runtime fixes
    try:
        # Redirect stderr temporarily to suppress the trapped error message
        import sys
        from io import StringIO

        # Store original stderr
        original_stderr = sys.stderr

        # Create a custom stderr that filters bcrypt messages
        class FilteredStderr:
            def __init__(self, original):
                self.original = original

            def write(self, text):
                # Filter out bcrypt version error messages
                if not (
                    "trapped" in text.lower()
                    and "bcrypt" in text.lower()
                    and "version" in text.lower()
                ):
                    self.original.write(text)

            def flush(self):
                self.original.flush()

            def __getattr__(self, name):
                return getattr(self.original, name)

        # Apply the filter
        sys.stderr = FilteredStderr(original_stderr)

    except Exception:
        # If anything goes wrong, just continue
        pass


# Auto-initialize when imported
initialize_bcrypt_compat()

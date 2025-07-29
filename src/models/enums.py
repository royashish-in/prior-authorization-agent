"""
Enumerations for healthcare data models.
"""

from enum import Enum


class RequestStatus(str, Enum):
    """Status of an authorization request."""
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    DENIED = "denied"
    MORE_INFO_NEEDED = "more_info_needed"
    EXPIRED = "expired"


class DecisionStatus(str, Enum):
    """Status of an authorization decision."""
    APPROVED = "approved"
    DENIED = "denied"
    MORE_INFO_NEEDED = "more_info_needed"


class UrgencyLevel(str, Enum):
    """Urgency level for authorization requests."""
    ROUTINE = "routine"
    URGENT = "urgent"
    EMERGENT = "emergent"


class Gender(str, Enum):
    """Patient gender options."""
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNKNOWN = "unknown"


class ProcedureType(str, Enum):
    """Types of imaging procedures."""
    MRI = "mri"
    CT_SCAN = "ct_scan"
    X_RAY = "x_ray"
    ULTRASOUND = "ultrasound"
    MAMMOGRAPHY = "mammography"
    NUCLEAR_MEDICINE = "nuclear_medicine"
"""
Request tracking service for authorization requests.

This module provides functionality for storing, retrieving, and tracking
the status of authorization requests throughout their lifecycle.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from src.models.authorization import AuthorizationRequest, AuthorizationDecision
from src.models.enums import RequestStatus
from src.core.logging import get_logger
from src.core.datetime_utils import utcnow

logger = get_logger(__name__)


@dataclass
class RequestStatusInfo:
    """Information about request status and progress."""

    request_id: str
    status: RequestStatus
    submitted_at: datetime
    updated_at: datetime
    estimated_completion: Optional[datetime]
    current_stage: str
    progress_percentage: int
    next_actions: Optional[List[str]]


@dataclass
class RequestsResult:
    """Result of bulk request query."""

    requests: List[RequestStatusInfo]
    total_count: int
    status_summary: Dict[str, int]


@dataclass
class ProviderRequestsResponse:
    """Response for provider requests query."""

    requests: List[RequestStatusInfo]
    total_count: int
    status_summary: Dict[str, int]


class TrackingService:
    """
    Service for tracking authorization requests.

    Provides functionality for:
    - Storing new requests
    - Retrieving request status
    - Updating request information
    - Bulk queries by provider
    """

    def __init__(self):
        """Initialize tracking service."""
        self.logger = get_logger(self.__class__.__name__)

        # In-memory storage for demo (in production, this would use database)
        self._requests: Dict[str, AuthorizationRequest] = {}
        self._request_status: Dict[str, RequestStatusInfo] = {}

    async def store_request(self, request: AuthorizationRequest) -> None:
        """
        Store a new authorization request.

        Args:
            request: Authorization request to store
        """
        try:
            # Store the request
            self._requests[request.request_id] = request

            # Create initial status info
            status_info = RequestStatusInfo(
                request_id=request.request_id,
                status=RequestStatus.SUBMITTED,
                submitted_at=request.submitted_at,
                updated_at=request.updated_at,
                estimated_completion=self._calculate_estimated_completion(request),
                current_stage="Initial Review",
                progress_percentage=10,
                next_actions=[
                    "Awaiting medical code validation",
                    "Awaiting policy review",
                ],
            )

            self._request_status[request.request_id] = status_info

            self.logger.info(
                "Request stored successfully",
                request_id=request.request_id,
                provider_id=request.provider_id,
                procedure_type=request.procedure_type,
            )

        except Exception as e:
            self.logger.error(
                "Error storing request",
                request_id=request.request_id,
                error=str(e),
                exc_info=True,
            )
            raise

    async def store_decision(self, decision: 'AuthorizationDecision') -> None:
        """
        Store an authorization decision.

        Args:
            decision: Authorization decision to store
        """
        try:
            # Store the decision (in a real implementation, this would go to database)
            if not hasattr(self, '_decisions'):
                self._decisions = {}
            
            self._decisions[decision.decision_id] = decision
            
            self.logger.info(
                "Decision stored successfully",
                decision_id=decision.decision_id,
                request_id=decision.request_id,
                status=decision.status.value
            )
            
        except Exception as e:
            self.logger.error(
                "Error storing decision",
                decision_id=decision.decision_id,
                request_id=decision.request_id,
                error=str(e),
                exc_info=True,
            )
            raise

    async def update_request_status(self, request_id: str, new_status: RequestStatus) -> None:
        """
        Update the status of an authorization request.

        Args:
            request_id: Unique request identifier
            new_status: New status to set
        """
        try:
            # Update the request status
            if request_id in self._requests:
                self._requests[request_id].status = new_status
                self._requests[request_id].updated_at = datetime.now(timezone.utc)
            
            # Update status info
            if request_id in self._request_status:
                status_info = self._request_status[request_id]
                status_info.status = new_status
                status_info.updated_at = datetime.now(timezone.utc)
                
                # Update stage and progress based on status
                if new_status == RequestStatus.APPROVED:
                    status_info.current_stage = "Approved"
                    status_info.progress_percentage = 100
                    status_info.next_actions = ["Authorization number generated"]
                elif new_status == RequestStatus.DENIED:
                    status_info.current_stage = "Denied"
                    status_info.progress_percentage = 100
                    status_info.next_actions = ["Review denial reason"]
                elif new_status == RequestStatus.MORE_INFO_NEEDED:
                    status_info.current_stage = "Additional Information Required"
                    status_info.progress_percentage = 50
                    status_info.next_actions = ["Provide additional documentation"]
                elif new_status == RequestStatus.IN_REVIEW:
                    status_info.current_stage = "Manual Review"
                    status_info.progress_percentage = 30
                    status_info.next_actions = ["Awaiting manual review"]
                
                self._request_status[request_id] = status_info
            
            self.logger.info(
                "Request status updated successfully",
                request_id=request_id,
                new_status=new_status.value
            )
            
        except Exception as e:
            self.logger.error(
                "Error updating request status",
                request_id=request_id,
                new_status=new_status.value,
                error=str(e),
                exc_info=True,
            )
            raise

    async def get_decision(self, decision_id: str) -> Optional['AuthorizationDecision']:
        """
        Retrieve a decision by its ID.

        Args:
            decision_id: Unique decision identifier

        Returns:
            AuthorizationDecision if found, None otherwise
        """
        try:
            if not hasattr(self, '_decisions'):
                self._decisions = {}
            
            decision = self._decisions.get(decision_id)
            
            if decision:
                self.logger.info(
                    "Decision retrieved successfully",
                    decision_id=decision_id,
                    request_id=decision.request_id
                )
            
            return decision
            
        except Exception as e:
            self.logger.error(
                "Error retrieving decision",
                decision_id=decision_id,
                error=str(e),
                exc_info=True,
            )
            return None

    async def get_decision_by_request(self, request_id: str) -> Optional['AuthorizationDecision']:
        """
        Retrieve a decision by request ID.

        Args:
            request_id: Authorization request identifier

        Returns:
            AuthorizationDecision if found, None otherwise
        """
        try:
            if not hasattr(self, '_decisions'):
                self._decisions = {}
            
            # Find decision by request_id
            for decision in self._decisions.values():
                if decision.request_id == request_id:
                    self.logger.info(
                        "Decision found for request",
                        decision_id=decision.decision_id,
                        request_id=request_id
                    )
                    return decision
            
            self.logger.info(
                "No decision found for request",
                request_id=request_id
            )
            return None
            
        except Exception as e:
            self.logger.error(
                "Error retrieving decision by request",
                request_id=request_id,
                error=str(e),
                exc_info=True,
            )
            return None

    async def get_request_status(self, request_id: str) -> Optional[RequestStatusInfo]:
        """
        Get the current status of a request.

        Args:
            request_id: Unique request identifier

        Returns:
            Request status information or None if not found
        """
        try:
            status_info = self._request_status.get(request_id)

            if status_info:
                # Update progress if request is still processing
                updated_status = self._update_progress(status_info)
                self._request_status[request_id] = updated_status
                return updated_status

            return None

        except Exception as e:
            self.logger.error(
                "Error retrieving request status",
                request_id=request_id,
                error=str(e),
                exc_info=True,
            )
            return None

    async def get_requests_by_provider(
        self,
        provider_id: str,
        status_filter: Optional[RequestStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ProviderRequestsResponse:
        """
        Get requests for a specific provider.

        Args:
            provider_id: Healthcare provider identifier
            status_filter: Optional status filter
            limit: Maximum number of requests to return
            offset: Number of requests to skip

        Returns:
            Filtered and paginated requests result
        """
        try:
            # Filter requests by provider
            provider_requests = [
                request
                for request in self._requests.values()
                if request.provider_id == provider_id
            ]

            # Apply status filter if provided
            if status_filter:
                filtered_requests = []
                for request in provider_requests:
                    status_info = self._request_status.get(request.request_id)
                    if status_info and status_info.status == status_filter:
                        filtered_requests.append(request)
                provider_requests = filtered_requests

            # Sort by submission date (newest first)
            provider_requests.sort(key=lambda r: r.submitted_at, reverse=True)

            # Apply pagination
            total_count = len(provider_requests)
            paginated_requests = provider_requests[offset : offset + limit]

            # Convert to status info objects
            status_list = []
            for request in paginated_requests:
                status_info = await self.get_request_status(request.request_id)
                if status_info:
                    status_list.append(status_info)

            # Calculate status summary
            status_summary = self._calculate_status_summary(provider_requests)

            self.logger.info(
                "Provider requests retrieved",
                provider_id=provider_id,
                total_count=total_count,
                returned_count=len(status_list),
                status_filter=status_filter.value if status_filter else None,
            )

            return ProviderRequestsResponse(
                requests=status_list,
                total_count=total_count,
                status_summary=status_summary,
            )

        except Exception as e:
            self.logger.error(
                "Error retrieving provider requests",
                provider_id=provider_id,
                error=str(e),
                exc_info=True,
            )
            raise

    async def update_request_info(
        self, request_id: str, additional_info: Dict[str, Any]
    ) -> None:
        """
        Update request with additional information.

        Args:
            request_id: Unique request identifier
            additional_info: Additional information to add
        """
        try:
            # Get existing request
            request = self._requests.get(request_id)
            if not request:
                raise ValueError(f"Request {request_id} not found")

            # Update request with additional info (simplified for demo)
            # In production, this would properly merge the additional information
            request.updated_at = utcnow()

            # Update status
            status_info = self._request_status.get(request_id)
            if status_info:
                status_info.status = RequestStatus.IN_REVIEW
                status_info.updated_at = request.updated_at
                status_info.current_stage = "Additional Information Review"
                status_info.progress_percentage = 60
                status_info.next_actions = [
                    "Reviewing additional information",
                    "Awaiting final decision",
                ]

                self._request_status[request_id] = status_info

            self.logger.info(
                "Request updated with additional information",
                request_id=request_id,
                info_fields=list(additional_info.keys()),
            )

        except Exception as e:
            self.logger.error(
                "Error updating request information",
                request_id=request_id,
                error=str(e),
                exc_info=True,
            )
            raise

    def _calculate_estimated_completion(
        self, request: AuthorizationRequest
    ) -> datetime:
        """
        Calculate estimated completion time for a request.

        Args:
            request: Authorization request

        Returns:
            Estimated completion datetime
        """
        # Base processing time: 2 hours for routine, 30 minutes for urgent
        if request.urgency_level.value == "urgent":
            processing_hours = 0.5
        elif request.urgency_level.value == "emergent":
            processing_hours = 0.25
        else:  # routine
            processing_hours = 2.0

        # Add complexity factors
        complexity_factor = 1.0

        # Multiple procedures add complexity
        if len(request.procedure_codes) > 1:
            complexity_factor += 0.5

        # Multiple diagnoses add complexity
        if len(request.diagnosis_codes) > 2:
            complexity_factor += 0.3

        # Missing clinical notes may require follow-up
        if not request.clinical_notes:
            complexity_factor += 0.5

        total_hours = processing_hours * complexity_factor

        return request.submitted_at + timedelta(hours=total_hours)

    def _update_progress(self, status_info: RequestStatusInfo) -> RequestStatusInfo:
        """
        Update progress based on elapsed time and current status.

        Args:
            status_info: Current status information

        Returns:
            Updated status information
        """
        current_time = utcnow()
        elapsed_time = current_time - status_info.submitted_at

        # Simulate progress based on elapsed time and status
        if status_info.status == RequestStatus.SUBMITTED:
            # Progress from 10% to 40% in first 30 minutes
            minutes_elapsed = elapsed_time.total_seconds() / 60
            if minutes_elapsed < 30:
                progress = 10 + int((minutes_elapsed / 30) * 30)
                status_info.progress_percentage = min(progress, 40)
            else:
                # Move to in_review status after 30 minutes
                status_info.status = RequestStatus.IN_REVIEW
                status_info.current_stage = "Policy Validation"
                status_info.progress_percentage = 50
                status_info.next_actions = [
                    "Validating against coverage policies",
                    "Checking medical necessity",
                ]

        elif status_info.status == RequestStatus.IN_REVIEW:
            # Progress from 50% to 90% during review
            total_estimated_minutes = (
                status_info.estimated_completion - status_info.submitted_at
            ).total_seconds() / 60
            minutes_elapsed = elapsed_time.total_seconds() / 60

            if minutes_elapsed < total_estimated_minutes:
                progress = 50 + int(
                    ((minutes_elapsed - 30) / (total_estimated_minutes - 30)) * 40
                )
                status_info.progress_percentage = min(max(progress, 50), 90)
            else:
                # Simulate completion for demo
                import random

                decision = random.choice(["approved", "denied", "more_info_needed"])

                if decision == "approved":
                    status_info.status = RequestStatus.APPROVED
                    status_info.current_stage = "Approved"
                    status_info.progress_percentage = 100
                    status_info.next_actions = None
                elif decision == "denied":
                    status_info.status = RequestStatus.DENIED
                    status_info.current_stage = "Denied"
                    status_info.progress_percentage = 100
                    status_info.next_actions = None
                else:
                    status_info.status = RequestStatus.MORE_INFO_NEEDED
                    status_info.current_stage = "Awaiting Additional Information"
                    status_info.progress_percentage = 75
                    status_info.next_actions = [
                        "Submit additional clinical documentation"
                    ]

        status_info.updated_at = current_time
        return status_info

    def _calculate_status_summary(
        self, requests: List[AuthorizationRequest]
    ) -> Dict[str, int]:
        """
        Calculate summary of request statuses.

        Args:
            requests: List of requests to summarize

        Returns:
            Dictionary with status counts
        """
        summary = {status.value: 0 for status in RequestStatus}

        for request in requests:
            status_info = self._request_status.get(request.request_id)
            if status_info:
                summary[status_info.status.value] += 1

        return summary

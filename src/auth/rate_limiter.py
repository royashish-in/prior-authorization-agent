"""
Rate limiting implementation for Prior Authorization Agent.

This module provides request throttling and rate limiting
to protect against abuse and ensure system stability.
"""

import logging
import time
from collections import defaultdict, deque
from typing import Dict, Optional, Tuple

from fastapi import HTTPException, Request, status

from src.core.config import get_settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    In-memory rate limiter with sliding window algorithm.

    Implements rate limiting per client IP and user to prevent abuse
    and ensure fair resource allocation.
    """

    def __init__(self):
        """Initialize rate limiter with empty tracking structures."""
        # Track requests per IP address
        self._ip_requests: Dict[str, deque] = defaultdict(deque)

        # Track requests per authenticated user
        self._user_requests: Dict[str, deque] = defaultdict(deque)

        # Track failed authentication attempts
        self._auth_failures: Dict[str, deque] = defaultdict(deque)

        # Lock for thread safety (in production, use Redis)
        self._cleanup_last_run = time.time()
        self._cleanup_interval = 300  # 5 minutes

    def _cleanup_old_entries(self) -> None:
        """
        Clean up old entries to prevent memory leaks.

        This is a simple cleanup for in-memory storage.
        In production, use Redis with TTL.
        """
        current_time = time.time()

        # Only run cleanup every 5 minutes
        if current_time - self._cleanup_last_run < self._cleanup_interval:
            return

        settings = get_settings()
        window_seconds = settings.rate_limit_window
        cutoff_time = current_time - (window_seconds * 2)  # Keep extra buffer

        # Clean IP requests
        for ip, requests in list(self._ip_requests.items()):
            while requests and requests[0] < cutoff_time:
                requests.popleft()
            if not requests:
                del self._ip_requests[ip]

        # Clean user requests
        for user_id, requests in list(self._user_requests.items()):
            while requests and requests[0] < cutoff_time:
                requests.popleft()
            if not requests:
                del self._user_requests[user_id]

        # Clean auth failures
        for ip, failures in list(self._auth_failures.items()):
            while failures and failures[0] < cutoff_time:
                failures.popleft()
            if not failures:
                del self._auth_failures[ip]

        self._cleanup_last_run = current_time

        logger.debug("Rate limiter cleanup completed")

    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP address from request.

        Args:
            request: FastAPI request object

        Returns:
            Client IP address string
        """
        # Check for forwarded headers (behind proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fallback to direct connection
        return request.client.host if request.client else "unknown"

    def check_rate_limit(
        self,
        request: Request,
        user_id: Optional[str] = None,
        custom_limit: Optional[int] = None,
        custom_window: Optional[int] = None,
    ) -> Tuple[bool, Dict[str, int]]:
        """
        Check if request should be rate limited.

        Args:
            request: FastAPI request object
            user_id: Optional authenticated user ID
            custom_limit: Optional custom rate limit
            custom_window: Optional custom time window

        Returns:
            Tuple of (is_allowed, rate_limit_info)

        Raises:
            HTTPException: If rate limit exceeded
        """
        self._cleanup_old_entries()

        settings = get_settings()
        current_time = time.time()

        # Use custom limits or defaults
        limit = custom_limit or settings.rate_limit_requests
        window = custom_window or settings.rate_limit_window

        client_ip = self._get_client_ip(request)

        # Check IP-based rate limit
        ip_requests = self._ip_requests[client_ip]

        # Remove old requests outside the window
        while ip_requests and ip_requests[0] < current_time - window:
            ip_requests.popleft()

        # Check if IP limit exceeded
        if len(ip_requests) >= limit:
            logger.warning(
                "Rate limit exceeded for IP",
                extra={
                    "client_ip": client_ip,
                    "request_count": len(ip_requests),
                    "limit": limit,
                    "window": window,
                },
            )

            rate_info = {
                "limit": limit,
                "remaining": 0,
                "reset_time": int(current_time + window),
                "retry_after": window,
            }

            return False, rate_info

        # Check user-based rate limit if authenticated
        user_requests = None
        if user_id:
            user_requests = self._user_requests[user_id]

            # Remove old requests outside the window
            while user_requests and user_requests[0] < current_time - window:
                user_requests.popleft()

            # Check if user limit exceeded (higher limit for authenticated users)
            user_limit = limit * 2  # Authenticated users get double the limit
            if len(user_requests) >= user_limit:
                logger.warning(
                    "Rate limit exceeded for user",
                    extra={
                        "user_id": user_id,
                        "client_ip": client_ip,
                        "request_count": len(user_requests),
                        "limit": user_limit,
                        "window": window,
                    },
                )

                rate_info = {
                    "limit": user_limit,
                    "remaining": 0,
                    "reset_time": int(current_time + window),
                    "retry_after": window,
                }

                return False, rate_info

        # Record the request
        ip_requests.append(current_time)
        if user_requests is not None:
            user_requests.append(current_time)

        # Calculate remaining requests
        remaining = limit - len(ip_requests)
        if user_requests is not None:
            user_limit = limit * 2
            remaining = min(remaining, user_limit - len(user_requests))

        rate_info = {
            "limit": limit,
            "remaining": max(0, remaining),
            "reset_time": int(current_time + window),
            "retry_after": 0,
        }

        logger.debug(
            "Rate limit check passed",
            extra={"client_ip": client_ip, "user_id": user_id, "remaining": remaining},
        )

        return True, rate_info

    def record_auth_failure(self, request: Request) -> bool:
        """
        Record authentication failure and check for brute force attempts.

        Args:
            request: FastAPI request object

        Returns:
            True if request should be blocked, False otherwise
        """
        self._cleanup_old_entries()

        current_time = time.time()
        client_ip = self._get_client_ip(request)

        # Record the failure
        failures = self._auth_failures[client_ip]
        failures.append(current_time)

        # Remove old failures (5 minute window for auth failures)
        auth_window = 300  # 5 minutes
        while failures and failures[0] < current_time - auth_window:
            failures.popleft()

        # Block if too many failures (5 failures in 5 minutes)
        max_auth_failures = 5
        if len(failures) >= max_auth_failures:
            logger.warning(
                "Authentication brute force detected",
                extra={
                    "client_ip": client_ip,
                    "failure_count": len(failures),
                    "window": auth_window,
                },
            )
            return True

        return False

    def clear_auth_failures(self, request: Request) -> None:
        """
        Clear authentication failures for successful login.

        Args:
            request: FastAPI request object
        """
        client_ip = self._get_client_ip(request)
        if client_ip in self._auth_failures:
            del self._auth_failures[client_ip]

            logger.debug(
                "Cleared authentication failures for successful login",
                extra={"client_ip": client_ip},
            )

    def reset_for_testing(self) -> None:
        """
        Reset all rate limiting data for testing purposes.

        WARNING: This should only be used in test environments.
        """
        self._ip_requests.clear()
        self._user_requests.clear()
        self._auth_failures.clear()
        self._cleanup_last_run = time.time()

        logger.debug("Rate limiter reset for testing")


# Global rate limiter instance
rate_limiter = RateLimiter()


def check_rate_limit_dependency(request: Request) -> None:
    """
    FastAPI dependency for rate limiting.

    Args:
        request: FastAPI request object

    Raises:
        HTTPException: If rate limit exceeded
    """
    is_allowed, rate_info = rate_limiter.check_rate_limit(request)

    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={
                "X-RateLimit-Limit": str(rate_info["limit"]),
                "X-RateLimit-Remaining": str(rate_info["remaining"]),
                "X-RateLimit-Reset": str(rate_info["reset_time"]),
                "Retry-After": str(rate_info["retry_after"]),
            },
        )

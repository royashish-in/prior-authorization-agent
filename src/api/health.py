"""
Health check endpoints for Prior Authorization Agent.

This module provides health monitoring endpoints for system status,
database connectivity, and external service availability.
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    timestamp: datetime
    version: str
    environment: str
    checks: Dict[str, Any]


class DetailedHealthResponse(BaseModel):
    """Detailed health check response model."""
    status: str
    timestamp: datetime
    version: str
    environment: str
    uptime_seconds: float
    checks: Dict[str, Dict[str, Any]]


# Track application start time for uptime calculation
_start_time = datetime.now(timezone.utc)


async def check_database() -> Dict[str, Any]:
    """
    Check database connectivity and health.
    
    Returns:
        Dictionary with database health status
    """
    try:
        # TODO: Implement actual database health check when database is set up
        # For now, return a mock healthy status
        return {
            "status": "healthy",
            "response_time_ms": 5,
            "details": "Database connection successful"
        }
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "error": str(e),
            "details": "Database connection failed"
        }


async def check_external_services() -> Dict[str, Any]:
    """
    Check external service connectivity (CMS API, etc.).
    
    Returns:
        Dictionary with external services health status
    """
    settings = get_settings()
    
    try:
        # TODO: Implement actual external service health checks
        # For now, return a mock healthy status
        return {
            "cms_api": {
                "status": "healthy",
                "url": settings.cms_api_url,
                "response_time_ms": 150,
                "details": "CMS API accessible"
            }
        }
    except Exception as e:
        logger.error("External services health check failed", error=str(e))
        return {
            "cms_api": {
                "status": "unhealthy",
                "error": str(e),
                "details": "CMS API connection failed"
            }
        }


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Basic health check endpoint for load balancers and monitoring.
    
    Returns:
        Basic health status information
        
    Raises:
        HTTPException: If critical systems are unhealthy
    """
    settings = get_settings()
    
    # Perform basic health checks
    db_check = await check_database()
    
    # Determine overall status
    overall_status = "healthy" if db_check["status"] == "healthy" else "unhealthy"
    
    response = HealthResponse(
        status=overall_status,
        timestamp=datetime.now(timezone.utc),
        version="1.0.0",
        environment=settings.environment,
        checks={
            "database": db_check["status"]
        }
    )
    
    # Return 503 if unhealthy
    if overall_status == "unhealthy":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response.dict()
        )
    
    return response


@router.get("/health/detailed", response_model=DetailedHealthResponse)
async def detailed_health_check() -> DetailedHealthResponse:
    """
    Detailed health check endpoint with comprehensive system status.
    
    Returns:
        Detailed health status including all subsystems
        
    Raises:
        HTTPException: If critical systems are unhealthy
    """
    settings = get_settings()
    current_time = datetime.now(timezone.utc)
    uptime = (current_time - _start_time).total_seconds()
    
    # Perform all health checks concurrently
    db_check, external_checks = await asyncio.gather(
        check_database(),
        check_external_services()
    )
    
    # Compile all checks
    all_checks = {
        "database": db_check,
        "external_services": external_checks
    }
    
    # Determine overall status
    unhealthy_checks = [
        name for name, check in all_checks.items()
        if (isinstance(check, dict) and check.get("status") == "unhealthy") or
           (isinstance(check, dict) and any(
               service.get("status") == "unhealthy" 
               for service in check.values() 
               if isinstance(service, dict)
           ))
    ]
    
    overall_status = "healthy" if not unhealthy_checks else "unhealthy"
    
    response = DetailedHealthResponse(
        status=overall_status,
        timestamp=current_time,
        version="1.0.0",
        environment=settings.environment,
        uptime_seconds=uptime,
        checks=all_checks
    )
    
    # Log health check results
    logger.info(
        "Health check performed",
        status=overall_status,
        uptime_seconds=uptime,
        unhealthy_checks=unhealthy_checks
    )
    
    # Return 503 if unhealthy
    if overall_status == "unhealthy":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response.dict()
        )
    
    return response


@router.get("/health/ready")
async def readiness_check() -> Dict[str, str]:
    """
    Kubernetes readiness probe endpoint.
    
    Returns:
        Simple ready status
        
    Raises:
        HTTPException: If application is not ready to serve traffic
    """
    # Check if application is ready to serve requests
    db_check = await check_database()
    
    if db_check["status"] == "healthy":
        return {"status": "ready"}
    else:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not ready", "reason": "Database unavailable"}
        )


@router.get("/health/live")
async def liveness_check() -> Dict[str, str]:
    """
    Kubernetes liveness probe endpoint.
    
    Returns:
        Simple alive status
    """
    return {"status": "alive"}
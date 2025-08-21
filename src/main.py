"""
Prior Authorization Agent - Main Application

This module contains the FastAPI application setup and configuration
for the healthcare prior authorization automation system.
"""

# Load environment variables first
from dotenv import load_dotenv
load_dotenv()

# Initialize bcrypt compatibility fixes first
from src.core.bcrypt_compat import initialize_bcrypt_compat
initialize_bcrypt_compat()

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import ValidationError

from src.api.auth import router as auth_router
from src.api.dashboard import router as dashboard_router
from src.api.decisions import router as decisions_router
from src.api.health import router as health_router
from src.api.intake import router as intake_router
from src.api.llm_decisions import router as llm_decisions_router
from src.api.manual_decisions import router as manual_decisions_router
from src.api.medical_codes import router as medical_codes_router
from src.api.openapi import get_custom_openapi
from src.audit.middleware import AuditMiddleware
from src.core.config import get_settings
from src.core.logging import setup_logging
from src.core.exceptions import (
    custom_http_exception_handler,
    validation_exception_handler,
    general_exception_handler
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager for startup and shutdown events.
    
    Args:
        app: FastAPI application instance
        
    Yields:
        None during application runtime
    """
    # Startup
    settings = get_settings()
    setup_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    logger.info("Prior Authorization Agent starting up...")
    
    yield
    
    # Shutdown
    logger.info("Prior Authorization Agent shutting down...")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        Configured FastAPI application instance
    """
    settings = get_settings()
    
    app = FastAPI(
        title="Prior Authorization Agent",
        description="Healthcare automation system for processing prior authorization requests",
        version="1.0.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
        lifespan=lifespan
    )
    
    # Security middleware
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_hosts
    )
    
    # CORS middleware for API access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins + ["file://"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    
    # Audit middleware for comprehensive logging
    app.add_middleware(
        AuditMiddleware,
        exclude_paths=["/health", "/docs", "/redoc", "/openapi.json"]
    )
    
    # Include routers
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(decisions_router, prefix="/api/v1")
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(intake_router, prefix="/api/v1")
    app.include_router(llm_decisions_router, prefix="/api/v1")
    app.include_router(manual_decisions_router, prefix="/api/v1")
    app.include_router(medical_codes_router, prefix="/api/v1/medical-codes")
    
    # Set custom OpenAPI schema
    app.openapi = lambda: get_custom_openapi(app)
    
    # Add custom exception handlers
    app.add_exception_handler(HTTPException, custom_http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
    
    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
        log_level=settings.log_level.lower()
    )
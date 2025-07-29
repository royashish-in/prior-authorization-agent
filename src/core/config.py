"""
Configuration management for Prior Authorization Agent.

This module handles environment variables, security settings,
and application configuration using Pydantic settings.
"""

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All sensitive configuration should be provided via environment variables
    to maintain security best practices for healthcare applications.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="PA_"
    )
    
    # Application settings
    environment: str = Field(default="development", description="Application environment")
    debug: bool = Field(default=False, description="Enable debug mode")
    host: str = Field(default="127.0.0.1", description="Application host")
    port: int = Field(default=8000, description="Application port")
    
    # Security settings
    secret_key: str = Field(default="dev-secret-key-change-in-production", description="Secret key for JWT tokens")
    allowed_hosts: List[str] = Field(default=["localhost", "127.0.0.1", "testserver"], description="Allowed hosts for security")
    cors_origins: List[str] = Field(default=["http://localhost:3000"], description="CORS allowed origins")
    
    # Database settings
    database_url: str = Field(default="sqlite:///./prior_auth.db", description="Database connection URL")
    db_driver: str = Field(default="sqlite", description="Database driver")
    db_host: str = Field(default="localhost", description="Database host")
    db_port: int = Field(default=3306, description="Database port")
    db_name: str = Field(default="prior_auth", description="Database name")
    db_username: str = Field(default="root", description="Database username")
    db_password: str = Field(default="", description="Database password")
    database_echo: bool = Field(default=False, description="Enable SQLAlchemy query logging")
    db_echo: bool = Field(default=False, description="Enable SQLAlchemy query logging (alias for database_echo)")
    db_pool_size: int = Field(default=10, description="Database connection pool size")
    db_max_overflow: int = Field(default=20, description="Database connection pool max overflow")
    
    # Logging settings
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format (json or text)")
    
    # Security and encryption
    encryption_key: str = Field(default="dev-encryption-key-32-chars-long", description="AES encryption key for PHI")
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_expiration_hours: int = Field(default=24, description="JWT token expiration in hours")
    
    # PHI encryption (note: this is accessed directly from environment, not through PA_ prefix)
    phi_master_key: str = Field(default="", description="Master key for PHI encryption", alias="PHI_MASTER_KEY")
    
    # Rate limiting
    rate_limit_requests: int = Field(default=100, description="Rate limit requests per minute")
    rate_limit_window: int = Field(default=60, description="Rate limit window in seconds")
    
    # External services
    cms_api_url: str = Field(default="https://api.cms.gov", description="CMS API base URL")
    cms_api_timeout: int = Field(default=30, description="CMS API timeout in seconds")
    cms_api_key: str = Field(default="", description="CMS API authentication key")
    
    # Medical code validation service
    medical_codes_api_url: str = Field(default="https://api.aapc.com", description="Medical codes API base URL")
    medical_codes_api_key: str = Field(default="", description="Medical codes API key")
    medical_codes_timeout: int = Field(default=15, description="Medical codes API timeout in seconds")
    
    # Policy service
    policy_service_url: str = Field(default="https://api.policyservice.com", description="Policy service base URL")
    policy_service_api_key: str = Field(default="", description="Policy service API key")
    policy_service_timeout: int = Field(default=20, description="Policy service timeout in seconds")
    
    # Cache settings
    redis_url: str = Field(default="redis://localhost:6379", description="Redis cache URL")
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=0, description="Redis database number")
    redis_password: str = Field(default="", description="Redis password")
    redis_max_connections: int = Field(default=20, description="Redis connection pool max connections")
    redis_socket_timeout: int = Field(default=5, description="Redis socket timeout in seconds")
    redis_socket_connect_timeout: int = Field(default=5, description="Redis socket connect timeout in seconds")
    cache_default_ttl: int = Field(default=3600, description="Default cache TTL in seconds")
    cache_enabled: bool = Field(default=True, description="Enable caching system")
    
    # Performance settings
    max_concurrent_requests: int = Field(default=1000, description="Maximum concurrent requests")
    request_timeout: int = Field(default=120, description="Request timeout in seconds")


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached application settings.
    
    Returns:
        Settings instance with current configuration
    """
    return Settings()
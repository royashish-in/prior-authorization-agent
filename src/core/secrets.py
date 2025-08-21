"""
Secrets Management

Handles secure retrieval of API keys, tokens, and other sensitive configuration
from environment variables and secure storage systems.
"""

import os
import logging
from typing import Optional
from src.core.config import get_settings


class LLMSecretsManager:
    """Manages LLM-related secrets and API keys."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.settings = get_settings()

    def get_huggingface_token(self) -> Optional[str]:
        """Get Hugging Face API token."""
        # Try environment variable first
        token = os.getenv("HUGGINGFACE_API_TOKEN")
        if token:
            self.logger.debug("Hugging Face token loaded from environment")
            return token

        # Try alternative environment variable names
        token = os.getenv("HF_TOKEN")
        if token:
            self.logger.debug("Hugging Face token loaded from HF_TOKEN")
            return token

        token = os.getenv("HUGGINGFACE_TOKEN")
        if token:
            self.logger.debug("Hugging Face token loaded from HUGGINGFACE_TOKEN")
            return token

        # Log warning if no token found
        self.logger.warning("No Hugging Face API token found in environment variables")
        return None

    def get_openai_api_key(self) -> Optional[str]:
        """Get OpenAI API key for fallback models."""
        token = os.getenv("OPENAI_API_KEY")
        if token:
            self.logger.debug("OpenAI API key loaded from environment")
            return token

        self.logger.warning("No OpenAI API key found in environment variables")
        return None

    def get_anthropic_api_key(self) -> Optional[str]:
        """Get Anthropic API key for Claude models."""
        token = os.getenv("ANTHROPIC_API_KEY")
        if token:
            self.logger.debug("Anthropic API key loaded from environment")
            return token

        self.logger.warning("No Anthropic API key found in environment variables")
        return None

    def get_database_encryption_key(self) -> str:
        """Get database encryption key."""
        key = os.getenv("PHI_MASTER_KEY")
        if not key:
            key = self.settings.phi_master_key

        if not key:
            raise ValueError("PHI_MASTER_KEY must be set for database encryption")

        return key

    def get_jwt_secret_key(self) -> str:
        """Get JWT secret key."""
        key = os.getenv("JWT_SECRET_KEY")
        if not key:
            key = self.settings.secret_key

        if not key or key == "dev-secret-key-change-in-production":
            self.logger.warning("Using default JWT secret key - change in production!")

        return key

    def get_redis_password(self) -> Optional[str]:
        """Get Redis password."""
        password = os.getenv("REDIS_PASSWORD")
        if password:
            self.logger.debug("Redis password loaded from environment")
            return password

        return (
            self.settings.redis_password
            if hasattr(self.settings, "redis_password")
            else None
        )

    def validate_required_secrets(self) -> bool:
        """Validate that all required secrets are available."""
        required_secrets = {
            "PHI_MASTER_KEY": self.get_database_encryption_key(),
            "JWT_SECRET_KEY": self.get_jwt_secret_key(),
        }

        missing_secrets = []
        for secret_name, secret_value in required_secrets.items():
            if not secret_value:
                missing_secrets.append(secret_name)

        if missing_secrets:
            self.logger.error(f"Missing required secrets: {', '.join(missing_secrets)}")
            return False

        # Warn about optional but recommended secrets
        optional_secrets = {"HUGGINGFACE_API_TOKEN": self.get_huggingface_token()}

        missing_optional = []
        for secret_name, secret_value in optional_secrets.items():
            if not secret_value:
                missing_optional.append(secret_name)

        if missing_optional:
            self.logger.warning(
                f"Missing optional secrets (LLM features may be limited): {', '.join(missing_optional)}"
            )

        return True


# Global secrets manager instance
llm_secrets_manager = LLMSecretsManager()

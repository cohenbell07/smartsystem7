"""
Secrets management service.
Stores and retrieves API keys and tokens securely.
"""

import logging
import os
from typing import Dict, Optional
from sqlmodel import Session, select
from app.models import Secret
from app.database import engine

logger = logging.getLogger(__name__)


class SecretsService:
    """Manages user secrets (API keys, tokens)."""

    def __init__(self, user_id: str = "dev_user"):
        self.user_id = user_id

    def get_secret(self, key: str) -> Optional[str]:
        """
        Get a secret value.

        Args:
            key: Secret key (e.g., "OPENAI_API_KEY")

        Returns:
            Secret value or None
        """
        # First check environment variables
        env_value = os.getenv(key)
        if env_value:
            return env_value

        # Then check database
        with Session(engine) as session:
            statement = select(Secret).where(
                Secret.user_id == self.user_id,
                Secret.key == key
            )
            secret = session.exec(statement).first()

            if secret:
                return secret.value

        return None

    def set_secret(self, key: str, value: str) -> bool:
        """
        Set a secret value.

        Args:
            key: Secret key
            value: Secret value

        Returns:
            True if successful
        """
        try:
            with Session(engine) as session:
                # Check if exists
                statement = select(Secret).where(
                    Secret.user_id == self.user_id,
                    Secret.key == key
                )
                secret = session.exec(statement).first()

                if secret:
                    # Update existing
                    secret.value = value
                    from datetime import datetime
                    secret.updated_at = datetime.utcnow()
                else:
                    # Create new
                    secret = Secret(
                        user_id=self.user_id,
                        key=key,
                        value=value,
                    )

                session.add(secret)
                session.commit()

                logger.info(f"Set secret: {key}")
                return True

        except Exception as e:
            logger.error(f"Failed to set secret {key}: {e}")
            return False

    def get_all_secrets(self, redact: bool = True) -> Dict[str, str]:
        """
        Get all secrets for user.

        Args:
            redact: If True, return redacted values (e.g., "sk-...***xyz")

        Returns:
            Dict of key -> value
        """
        secrets = {}

        # Include environment variables
        common_keys = [
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "BING_SEARCH_API_KEY",
            "SERPAPI_KEY",
            "GITHUB_TOKEN",
            "SMTP_USER",
            "SMTP_PASSWORD",
            "DISCORD_WEBHOOK_URL",
        ]

        for key in common_keys:
            value = self.get_secret(key)
            if value:
                if redact:
                    secrets[key] = self._redact_value(value)
                else:
                    secrets[key] = value
            else:
                secrets[key] = None

        return secrets

    def _redact_value(self, value: str) -> str:
        """
        Redact a secret value for display.

        Args:
            value: Full value

        Returns:
            Redacted value (e.g., "sk-...***xyz")
        """
        if not value:
            return ""

        if len(value) <= 8:
            return "***"

        # Show first 3 and last 3 characters
        return f"{value[:3]}...***{value[-3:]}"

    def delete_secret(self, key: str) -> bool:
        """
        Delete a secret.

        Args:
            key: Secret key

        Returns:
            True if successful
        """
        try:
            with Session(engine) as session:
                statement = select(Secret).where(
                    Secret.user_id == self.user_id,
                    Secret.key == key
                )
                secret = session.exec(statement).first()

                if secret:
                    session.delete(secret)
                    session.commit()
                    logger.info(f"Deleted secret: {key}")
                    return True
                else:
                    logger.warning(f"Secret not found: {key}")
                    return False

        except Exception as e:
            logger.error(f"Failed to delete secret {key}: {e}")
            return False

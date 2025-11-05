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

    def set_secret(self, key: str, value: str, save_to_env: bool = True) -> bool:
        """
        Set a secret value.

        Args:
            key: Secret key
            value: Secret value
            save_to_env: If True, also save to .env file

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

                # Save to .env file if requested
                if save_to_env:
                    self._save_to_env_file(key, value)

                # Update runtime environment variable
                os.environ[key] = value

                logger.info(f"Set secret: {key}")
                return True

        except Exception as e:
            logger.error(f"Failed to set secret {key}: {e}")
            return False

    def _save_to_env_file(self, key: str, value: str):
        """
        Save or update a key in the .env file.

        Args:
            key: Environment variable key
            value: Environment variable value
        """
        try:
            # Find .env file (typically in the backend directory)
            env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")

            # Read existing .env content
            env_lines = []
            key_exists = False

            if os.path.exists(env_path):
                with open(env_path, 'r') as f:
                    env_lines = f.readlines()

                # Update existing key or mark that it needs to be added
                for i, line in enumerate(env_lines):
                    if line.strip().startswith(f"{key}="):
                        # Update existing line
                        env_lines[i] = f"{key}={value}\n"
                        key_exists = True
                        break

            # Add new key if it doesn't exist
            if not key_exists:
                # Add newline before if file doesn't end with one
                if env_lines and not env_lines[-1].endswith('\n'):
                    env_lines[-1] += '\n'
                env_lines.append(f"{key}={value}\n")

            # Write back to .env file
            with open(env_path, 'w') as f:
                f.writelines(env_lines)

            logger.info(f"Saved {key} to .env file at {env_path}")

        except Exception as e:
            logger.error(f"Failed to save {key} to .env file: {e}")
            # Don't fail the whole operation if .env update fails
            pass

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

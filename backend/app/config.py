"""
Application Configuration using Pydantic Settings.

Loads configuration from environment variables (.env file).
Never logs sensitive values like API keys and tokens.
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/smartsystem",
        description="PostgreSQL database connection URL"
    )

    # Redis
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for background jobs"
    )

    # LLM API Keys
    OPENAI_API_KEY: Optional[str] = Field(
        default=None,
        description="OpenAI API key for GPT models"
    )
    ANTHROPIC_API_KEY: Optional[str] = Field(
        default=None,
        description="Anthropic API key for Claude models"
    )
    GEMINI_API_KEY: Optional[str] = Field(
        default=None,
        description="Google Gemini API key"
    )

    # Default LLM Settings
    DEFAULT_LLM: str = Field(
        default="gpt-4o-mini",
        description="Default LLM model to use"
    )
    MODEL_ROUTER_DEFAULT_MODEL: str = Field(
        default="gpt-4o-mini",
        description="Default model for model router"
    )

    # GitHub Integration
    GITHUB_TOKEN: Optional[str] = Field(
        default=None,
        description="GitHub personal access token for repo creation"
    )
    GITHUB_OWNER: str = Field(
        default="cohenbell07",
        description="GitHub username/organization for created repos"
    )
    GITHUB_REPO_PREFIX: str = Field(
        default="agent-build-",
        description="Prefix for auto-generated repository names"
    )

    # Vercel Deployment
    VERCEL_TOKEN: Optional[str] = Field(
        default=None,
        description="Vercel API token for deployments"
    )
    VERCEL_TEAM_ID: Optional[str] = Field(
        default=None,
        description="Vercel team ID (optional, for team deployments)"
    )
    VERCEL_PROJECT_PREFIX: str = Field(
        default="agent-build-",
        description="Prefix for auto-generated Vercel project names"
    )

    # Search APIs
    SERPAPI_API_KEY: Optional[str] = Field(
        default=None,
        description="SerpAPI key for web search"
    )
    TAVILY_API_KEY: Optional[str] = Field(
        default=None,
        description="Tavily API key for web search"
    )

    # Email Configuration
    SMTP_HOST: Optional[str] = Field(
        default=None,
        description="SMTP server hostname"
    )
    SMTP_PORT: int = Field(
        default=587,
        description="SMTP server port"
    )
    SMTP_USER: Optional[str] = Field(
        default=None,
        description="SMTP username"
    )
    SMTP_PASSWORD: Optional[str] = Field(
        default=None,
        description="SMTP password"
    )
    SMTP_FROM: Optional[str] = Field(
        default=None,
        description="Email sender address"
    )

    # Application Settings
    DEBUG: bool = Field(
        default=False,
        description="Enable debug mode"
    )
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )

    # CORS
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:3001",
        description="Comma-separated list of allowed CORS origins"
    )

    # Docker Execution (for safe code execution)
    DOCKER_ENABLED: bool = Field(
        default=True,
        description="Enable Docker-based code execution for validation"
    )
    DOCKER_TIMEOUT: int = Field(
        default=300,
        description="Docker execution timeout in seconds (default 5 minutes)"
    )
    DOCKER_MEMORY_LIMIT: str = Field(
        default="2g",
        description="Docker container memory limit"
    )
    DOCKER_CPU_LIMIT: float = Field(
        default=1.0,
        description="Docker container CPU limit (cores)"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

    def get_allowed_origins_list(self) -> list[str]:
        """Parse allowed origins from comma-separated string."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]

    def is_github_configured(self) -> bool:
        """Check if GitHub integration is configured."""
        return bool(self.GITHUB_TOKEN)

    def is_vercel_configured(self) -> bool:
        """Check if Vercel deployment is configured."""
        return bool(self.VERCEL_TOKEN)

    def is_docker_available(self) -> bool:
        """Check if Docker execution is enabled."""
        return self.DOCKER_ENABLED

    def __repr__(self) -> str:
        """Safe representation that doesn't expose secrets."""
        safe_fields = {
            "DATABASE_URL": "***" if self.DATABASE_URL else None,
            "REDIS_URL": "***" if self.REDIS_URL else None,
            "OPENAI_API_KEY": "***" if self.OPENAI_API_KEY else None,
            "ANTHROPIC_API_KEY": "***" if self.ANTHROPIC_API_KEY else None,
            "GEMINI_API_KEY": "***" if self.GEMINI_API_KEY else None,
            "GITHUB_TOKEN": "***" if self.GITHUB_TOKEN else None,
            "VERCEL_TOKEN": "***" if self.VERCEL_TOKEN else None,
            "GITHUB_OWNER": self.GITHUB_OWNER,
            "DEFAULT_LLM": self.DEFAULT_LLM,
            "DEBUG": self.DEBUG,
            "DOCKER_ENABLED": self.DOCKER_ENABLED,
        }
        return f"Settings({safe_fields})"


# Global settings instance
settings = Settings()

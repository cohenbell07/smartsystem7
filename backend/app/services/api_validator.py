"""
API key validation service for agent runs.
"""

import logging
import os
from typing import Dict, List, Tuple
from app.services.secrets import SecretsService

logger = logging.getLogger(__name__)


class APIKeyValidator:
    """Validates that required API keys are present for agent execution."""

    # Map of tool/service names to required API keys
    REQUIRED_KEYS_MAP = {
        "github": ["GITHUB_TOKEN"],
        "github_ops": ["GITHUB_TOKEN"],
        "githubops": ["GITHUB_TOKEN"],
        "openai": ["OPENAI_API_KEY"],
        "anthropic": ["ANTHROPIC_API_KEY"],
        "claude": ["ANTHROPIC_API_KEY"],
        "gpt": ["OPENAI_API_KEY"],
        "email": ["SMTP_USER", "SMTP_PASSWORD"],
        "emailer": ["SMTP_USER", "SMTP_PASSWORD"],
        "search": ["SERPAPI_KEY", "BING_SEARCH_API_KEY"],  # At least one required
        "web_search": ["SERPAPI_KEY", "BING_SEARCH_API_KEY"],
    }

    def __init__(self):
        self.secrets_service = SecretsService()

    def validate_agent_keys(self, agent_spec: dict) -> Tuple[bool, List[str], Dict[str, bool]]:
        """
        Validate that all required API keys are present for an agent.

        Args:
            agent_spec: Agent specification dict with 'tools', 'apis', 'nodes' fields

        Returns:
            Tuple of (is_valid, missing_keys, key_status)
                - is_valid: True if all required keys are present
                - missing_keys: List of missing key names
                - key_status: Dict of {key_name: is_present}
        """
        required_keys = set()

        # Check tools field
        if "tools" in agent_spec and agent_spec["tools"]:
            for tool in agent_spec["tools"]:
                tool_lower = tool.lower()
                if tool_lower in self.REQUIRED_KEYS_MAP:
                    required_keys.update(self.REQUIRED_KEYS_MAP[tool_lower])

        # Check apis field
        if "apis" in agent_spec and agent_spec["apis"]:
            for api in agent_spec["apis"]:
                if isinstance(api, dict):
                    api_name = api.get("name", "").lower()
                elif isinstance(api, str):
                    api_name = api.lower()
                else:
                    continue

                if api_name in self.REQUIRED_KEYS_MAP:
                    required_keys.update(self.REQUIRED_KEYS_MAP[api_name])

        # Check nodes field for LLM models
        if "nodes" in agent_spec:
            for node in agent_spec["nodes"]:
                if node.get("type") == "llm":
                    model = node.get("model", "").lower()
                    if "gpt" in model or "openai" in model:
                        required_keys.add("OPENAI_API_KEY")
                    elif "claude" in model or "anthropic" in model:
                        required_keys.add("ANTHROPIC_API_KEY")

                # Check tool nodes
                elif node.get("type") == "tool":
                    tool_name = node.get("tool", "").lower()
                    if tool_name in self.REQUIRED_KEYS_MAP:
                        required_keys.update(self.REQUIRED_KEYS_MAP[tool_name])

        # Check which keys are present
        key_status = {}
        missing_keys = []

        for key in required_keys:
            # Handle "at least one" case (e.g., search APIs)
            if key in ["SERPAPI_KEY", "BING_SEARCH_API_KEY"]:
                # Check if at least one search key is present
                has_serpapi = bool(self.secrets_service.get_secret("SERPAPI_KEY"))
                has_bing = bool(self.secrets_service.get_secret("BING_SEARCH_API_KEY"))

                if has_serpapi or has_bing:
                    key_status["SERPAPI_KEY"] = has_serpapi
                    key_status["BING_SEARCH_API_KEY"] = has_bing
                else:
                    key_status["SERPAPI_KEY"] = False
                    key_status["BING_SEARCH_API_KEY"] = False
                    if "SERPAPI_KEY" not in missing_keys:
                        missing_keys.append("SERPAPI_KEY (or BING_SEARCH_API_KEY)")
            else:
                value = self.secrets_service.get_secret(key)
                is_present = bool(value)
                key_status[key] = is_present

                if not is_present:
                    missing_keys.append(key)

        is_valid = len(missing_keys) == 0

        if not is_valid:
            logger.warning(f"Missing API keys for agent: {missing_keys}")
        else:
            logger.info(f"All required API keys present for agent")

        return is_valid, missing_keys, key_status

    def get_key_instructions(self, key: str) -> Dict[str, str]:
        """
        Get instructions for obtaining an API key.

        Args:
            key: API key name

        Returns:
            Dict with 'url' and 'description' fields
        """
        instructions = {
            "OPENAI_API_KEY": {
                "url": "https://platform.openai.com/api-keys",
                "description": "Sign up for OpenAI and create an API key"
            },
            "ANTHROPIC_API_KEY": {
                "url": "https://console.anthropic.com/settings/keys",
                "description": "Sign up for Anthropic and create an API key"
            },
            "GITHUB_TOKEN": {
                "url": "https://github.com/settings/tokens",
                "description": "Generate a Personal Access Token with repo permissions"
            },
            "SERPAPI_KEY": {
                "url": "https://serpapi.com/manage-api-key",
                "description": "Sign up for SerpAPI and get your API key"
            },
            "BING_SEARCH_API_KEY": {
                "url": "https://www.microsoft.com/en-us/bing/apis/bing-web-search-api",
                "description": "Sign up for Bing Search API on Azure"
            },
            "SMTP_USER": {
                "url": "https://support.google.com/mail/answer/185833",
                "description": "Use your Gmail address or SMTP server credentials"
            },
            "SMTP_PASSWORD": {
                "url": "https://support.google.com/mail/answer/185833",
                "description": "Use Gmail app password or SMTP server password"
            },
        }

        return instructions.get(key, {
            "url": "",
            "description": "Configure this API key in settings"
        })

    def get_validation_report(self, agent_spec: dict) -> Dict:
        """
        Get a detailed validation report for an agent.

        Args:
            agent_spec: Agent specification dict

        Returns:
            Dict with validation details
        """
        is_valid, missing_keys, key_status = self.validate_agent_keys(agent_spec)

        # Get instructions for missing keys
        missing_with_instructions = []
        for key in missing_keys:
            # Handle special case
            if "(" in key:  # e.g., "SERPAPI_KEY (or BING_SEARCH_API_KEY)"
                main_key = key.split(" ")[0]
                instructions = self.get_key_instructions(main_key)
            else:
                instructions = self.get_key_instructions(key)

            missing_with_instructions.append({
                "key": key,
                **instructions
            })

        return {
            "valid": is_valid,
            "missing_keys": missing_keys,
            "key_status": key_status,
            "missing_with_instructions": missing_with_instructions,
            "message": "All required API keys are configured" if is_valid else f"Missing {len(missing_keys)} required API key(s)"
        }

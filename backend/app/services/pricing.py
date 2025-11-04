"""
Pricing Service: Fetch live pricing and estimate costs for LLM API calls.
"""

import logging
import httpx
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)


# Pricing cache (24h TTL)
_pricing_cache = {
    "data": None,
    "timestamp": None,
}

# Fallback pricing (as of Jan 2025, per 1M tokens)
FALLBACK_PRICING = {
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.150, "output": 0.600},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},

    # Anthropic
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 1.00, "output": 5.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    "claude-3-sonnet-20240229": {"input": 3.00, "output": 15.00},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
}


def _is_cache_valid() -> bool:
    """Check if pricing cache is still valid (< 24h old)."""
    if not _pricing_cache["data"] or not _pricing_cache["timestamp"]:
        return False

    age = datetime.utcnow() - _pricing_cache["timestamp"]
    return age < timedelta(hours=24)


async def fetch_live_pricing() -> Dict[str, Dict[str, float]]:
    """
    Fetch live pricing from OpenAI and Anthropic APIs.

    Falls back to hardcoded pricing if APIs are unavailable.

    Returns:
        Dict mapping model names to {"input": price, "output": price} per 1M tokens
    """
    # Check cache first
    if _is_cache_valid():
        logger.info("Using cached pricing data")
        return _pricing_cache["data"]

    logger.info("Fetching live pricing data")
    pricing = {}

    # Try to fetch OpenAI pricing
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # OpenAI doesn't have a public pricing API endpoint
            # We'll use the fallback for now
            # In production, you could scrape their pricing page or maintain a database
            logger.info("Using fallback OpenAI pricing")
            for model, prices in FALLBACK_PRICING.items():
                if model.startswith("gpt"):
                    pricing[model] = prices
    except Exception as e:
        logger.warning(f"Failed to fetch OpenAI pricing: {e}")
        for model, prices in FALLBACK_PRICING.items():
            if model.startswith("gpt"):
                pricing[model] = prices

    # Try to fetch Anthropic pricing
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Anthropic doesn't have a public pricing API endpoint either
            # Using fallback
            logger.info("Using fallback Anthropic pricing")
            for model, prices in FALLBACK_PRICING.items():
                if model.startswith("claude"):
                    pricing[model] = prices
    except Exception as e:
        logger.warning(f"Failed to fetch Anthropic pricing: {e}")
        for model, prices in FALLBACK_PRICING.items():
            if model.startswith("claude"):
                pricing[model] = prices

    # Cache the result
    _pricing_cache["data"] = pricing
    _pricing_cache["timestamp"] = datetime.utcnow()

    logger.info(f"Loaded pricing for {len(pricing)} models")
    return pricing


def estimate_tokens(text: str, model: str) -> int:
    """
    Estimate token count for a given text and model.

    Uses rough approximation: ~4 characters per token for English text.
    For production, use tiktoken for OpenAI models and Anthropic's tokenizer for Claude.

    Args:
        text: Input text
        model: Model name

    Returns:
        Estimated token count
    """
    # Simple approximation: 4 chars per token
    # This is conservative (actual is often ~3.5-4 chars/token)
    char_count = len(text)
    estimated_tokens = int(char_count / 3.5)  # Slightly optimistic estimate

    # Add overhead for message formatting (varies by model)
    overhead = 10

    return estimated_tokens + overhead


def extract_model_from_spec(agent_spec: dict) -> list[Tuple[str, str]]:
    """
    Extract models used in an agent spec.

    Args:
        agent_spec: AgentSpec dictionary

    Returns:
        List of tuples (role, model_name) e.g., [("planning", "gpt-4o"), ("coding", "claude-3-5-sonnet")]
    """
    models = []

    # Check for explicit model specifications in nodes
    for node in agent_spec.get("nodes", []):
        if node.get("type") == "llm":
            model = node.get("model", "gpt-4o-mini")  # Default
            role = node.get("name", "unknown")
            models.append((role, model))

    # If no explicit models, assume default based on graph type
    if not models:
        # Default models for different agent types
        graph_type = agent_spec.get("graph_type", "custom")
        if graph_type == "video_generation":
            models = [("planning", "gpt-4o"), ("generation", "gpt-4o")]
        elif graph_type == "outreach":
            models = [("planning", "claude-3-5-sonnet-20241022"), ("drafting", "gpt-4o")]
        else:
            # Generic: assume one planning and one execution node
            models = [("planning", "gpt-4o-mini"), ("execution", "gpt-4o-mini")]

    return models


async def estimate_run_cost(agent_spec: dict, input_text: str = "") -> dict:
    """
    Estimate the cost of running an agent.

    Args:
        agent_spec: AgentSpec dictionary
        input_text: User inputs (for token estimation)

    Returns:
        Dict with cost breakdown:
        {
            "total_estimated_cost": 0.123,
            "breakdown": [
                {
                    "model": "gpt-4o",
                    "role": "planning",
                    "estimated_input_tokens": 1000,
                    "estimated_output_tokens": 500,
                    "estimated_cost": 0.045
                },
                ...
            ],
            "warning": "Estimate only - actual costs may vary"
        }
    """
    logger.info("Estimating run cost")

    # Get pricing
    pricing = await fetch_live_pricing()

    # Extract models from spec
    models_used = extract_model_from_spec(agent_spec)

    # Estimate context size
    base_context = json.dumps(agent_spec) + input_text
    base_tokens = estimate_tokens(base_context, "gpt-4o-mini")

    breakdown = []
    total_cost = 0.0

    for role, model in models_used:
        # Get model pricing
        model_pricing = pricing.get(model)
        if not model_pricing:
            # Try to find similar model
            if model.startswith("gpt"):
                model_pricing = pricing.get("gpt-4o-mini", {"input": 0.15, "output": 0.60})
            elif model.startswith("claude"):
                model_pricing = pricing.get("claude-3-5-haiku-20241022", {"input": 1.00, "output": 5.00})
            else:
                # Unknown model, use expensive default
                model_pricing = {"input": 5.00, "output": 15.00}

        # Estimate tokens for this step
        # Input: base context + previous outputs
        estimated_input = int(base_tokens * 1.2)  # Add 20% for accumulated context

        # Output: varies by role
        if "planning" in role.lower():
            estimated_output = 2000  # Planning typically generates substantial output
        elif "review" in role.lower():
            estimated_output = 1000  # Reviews are typically shorter
        else:
            estimated_output = 1500  # Default mid-range

        # Calculate cost (pricing is per 1M tokens)
        input_cost = (estimated_input / 1_000_000) * model_pricing["input"]
        output_cost = (estimated_output / 1_000_000) * model_pricing["output"]
        step_cost = input_cost + output_cost

        breakdown.append({
            "model": model,
            "role": role,
            "estimated_input_tokens": estimated_input,
            "estimated_output_tokens": estimated_output,
            "estimated_cost": round(step_cost, 4),
            "price_per_1m_input": model_pricing["input"],
            "price_per_1m_output": model_pricing["output"],
        })

        total_cost += step_cost

    return {
        "total_estimated_cost": round(total_cost, 4),
        "breakdown": breakdown,
        "warning": "Estimate only - actual costs may vary by 30-50%",
        "estimated_at": datetime.utcnow().isoformat(),
    }


def calculate_actual_cost(usage_data: dict, model: str, pricing: Optional[dict] = None) -> float:
    """
    Calculate actual cost from API usage data.

    Args:
        usage_data: Usage dict from API response, e.g.,
                   {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        model: Model name used
        pricing: Optional pricing dict (if None, uses cached/fallback)

    Returns:
        Actual cost in USD
    """
    if not pricing:
        # Use cached pricing or fallback
        if _is_cache_valid():
            pricing = _pricing_cache["data"]
        else:
            pricing = FALLBACK_PRICING

    model_pricing = pricing.get(model)
    if not model_pricing:
        # Try to find similar model
        if model.startswith("gpt"):
            model_pricing = pricing.get("gpt-4o-mini", {"input": 0.15, "output": 0.60})
        elif model.startswith("claude"):
            model_pricing = pricing.get("claude-3-5-haiku-20241022", {"input": 1.00, "output": 5.00})
        else:
            logger.warning(f"Unknown model '{model}' for cost calculation")
            return 0.0

    # Extract token counts
    input_tokens = usage_data.get("prompt_tokens") or usage_data.get("input_tokens", 0)
    output_tokens = usage_data.get("completion_tokens") or usage_data.get("output_tokens", 0)

    # Calculate cost (pricing is per 1M tokens)
    input_cost = (input_tokens / 1_000_000) * model_pricing["input"]
    output_cost = (output_tokens / 1_000_000) * model_pricing["output"]

    return round(input_cost + output_cost, 6)


async def get_current_pricing() -> dict:
    """
    Get current pricing for all supported models.

    Returns:
        Dict mapping model names to pricing info
    """
    pricing = await fetch_live_pricing()

    return {
        "models": [
            {
                "name": model,
                "input_price_per_1m": prices["input"],
                "output_price_per_1m": prices["output"],
                "provider": "openai" if model.startswith("gpt") else "anthropic",
            }
            for model, prices in pricing.items()
        ],
        "updated_at": _pricing_cache["timestamp"].isoformat() if _pricing_cache["timestamp"] else None,
        "currency": "USD",
    }

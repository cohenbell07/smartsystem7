"""
Tests for pricing service.
"""

import pytest
from app.services.pricing import (
    estimate_tokens,
    extract_model_from_spec,
    estimate_run_cost,
    calculate_actual_cost,
    FALLBACK_PRICING,
)


def test_estimate_tokens():
    """Test token estimation for text."""
    text = "Hello, this is a test message."
    tokens = estimate_tokens(text, "gpt-4o")

    # Should be roughly 10-15 tokens
    assert tokens > 0
    assert tokens < 50  # Conservative upper bound


def test_extract_model_from_spec_with_explicit_models():
    """Test extracting models from agent spec with explicit model definitions."""
    spec = {
        "name": "Test Agent",
        "nodes": [
            {"type": "llm", "name": "planning", "model": "gpt-4o"},
            {"type": "llm", "name": "coding", "model": "claude-3-5-sonnet-20241022"},
        ],
        "edges": [],
    }

    models = extract_model_from_spec(spec)
    assert len(models) == 2
    assert models[0] == ("planning", "gpt-4o")
    assert models[1] == ("coding", "claude-3-5-sonnet-20241022")


def test_extract_model_from_spec_defaults():
    """Test extracting models from agent spec with default models."""
    spec = {
        "name": "Test Agent",
        "graph_type": "video_generation",
        "nodes": [],
        "edges": [],
    }

    models = extract_model_from_spec(spec)
    assert len(models) == 2
    assert "planning" in models[0][0] or "generation" in models[0][0]


@pytest.mark.asyncio
async def test_estimate_run_cost():
    """Test cost estimation for a run."""
    spec = {
        "name": "Test Agent",
        "description": "Test agent for cost estimation",
        "nodes": [
            {"type": "llm", "name": "planning", "model": "gpt-4o-mini"},
        ],
        "edges": [],
        "graph_type": "custom",
    }

    input_text = "This is a test input"

    result = await estimate_run_cost(spec, input_text)

    assert "total_estimated_cost" in result
    assert "breakdown" in result
    assert "warning" in result
    assert result["total_estimated_cost"] > 0
    assert len(result["breakdown"]) == 1
    assert result["breakdown"][0]["model"] == "gpt-4o-mini"


def test_calculate_actual_cost_openai():
    """Test calculating actual cost from OpenAI usage data."""
    usage_data = {
        "prompt_tokens": 1000,
        "completion_tokens": 500,
        "total_tokens": 1500,
    }

    model = "gpt-4o-mini"
    cost = calculate_actual_cost(usage_data, model, FALLBACK_PRICING)

    # Cost should be: (1000/1M * 0.15) + (500/1M * 0.60) = 0.00015 + 0.0003 = 0.00045
    assert cost > 0
    assert cost < 0.001  # Should be very small for mini model


def test_calculate_actual_cost_anthropic():
    """Test calculating actual cost from Anthropic usage data."""
    usage_data = {
        "input_tokens": 1000,
        "output_tokens": 500,
    }

    model = "claude-3-5-haiku-20241022"
    cost = calculate_actual_cost(usage_data, model, FALLBACK_PRICING)

    # Cost should be: (1000/1M * 1.00) + (500/1M * 5.00) = 0.001 + 0.0025 = 0.0035
    assert cost > 0
    assert cost < 0.01


def test_calculate_actual_cost_unknown_model():
    """Test calculating cost for unknown model (should not crash)."""
    usage_data = {
        "prompt_tokens": 1000,
        "completion_tokens": 500,
    }

    model = "unknown-model-xyz"
    cost = calculate_actual_cost(usage_data, model, FALLBACK_PRICING)

    # Should return 0 for unknown model
    assert cost == 0.0


@pytest.mark.asyncio
async def test_estimate_run_cost_multiple_nodes():
    """Test cost estimation with multiple LLM nodes."""
    spec = {
        "name": "Multi-step Agent",
        "description": "Agent with multiple steps",
        "nodes": [
            {"type": "llm", "name": "planning", "model": "gpt-4o"},
            {"type": "llm", "name": "execution", "model": "claude-3-5-sonnet-20241022"},
            {"type": "llm", "name": "review", "model": "gpt-4o-mini"},
        ],
        "edges": [],
        "graph_type": "custom",
    }

    result = await estimate_run_cost(spec, "Test input")

    assert len(result["breakdown"]) == 3
    assert result["total_estimated_cost"] > 0

    # Verify all three models are in the breakdown
    models = [item["model"] for item in result["breakdown"]]
    assert "gpt-4o" in models
    assert "claude-3-5-sonnet-20241022" in models
    assert "gpt-4o-mini" in models

    # Verify cost increases with more steps
    assert result["total_estimated_cost"] > 0.001  # Should be at least 0.1 cents


def test_pricing_consistency():
    """Test that pricing is consistent between estimate and calculate."""
    model = "gpt-4o-mini"

    # Use the same token counts
    input_tokens = 1000
    output_tokens = 500

    # Estimate approach (from estimate_run_cost logic)
    pricing = FALLBACK_PRICING[model]
    estimated_cost = (input_tokens / 1_000_000) * pricing["input"] + \
                     (output_tokens / 1_000_000) * pricing["output"]

    # Actual approach (from calculate_actual_cost)
    usage_data = {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
    }
    actual_cost = calculate_actual_cost(usage_data, model, FALLBACK_PRICING)

    # Should be equal within rounding
    assert abs(estimated_cost - actual_cost) < 0.000001

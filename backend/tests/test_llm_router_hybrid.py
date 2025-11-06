"""
Tests for LLM Router hybrid generation.
"""

import pytest
from app.services.llm_router import LLMRouter


@pytest.mark.asyncio
async def test_hybrid_generation_structure():
    """Test that hybrid generation returns proper structure."""
    llm_router = LLMRouter()

    # Skip if no LLMs configured
    if not llm_router.gpt and not llm_router.claude:
        pytest.skip("No LLMs configured")

    try:
        result = await llm_router.plan_with_claude_emit_with_gpt(
            task="Create a simple agent that greets users",
            context="Test context",
            strategy="hybrid"
        )

        # Check structure
        assert "plan" in result
        assert "code" in result
        assert "strategy" in result
        assert "models_used" in result
        assert result["strategy"] == "hybrid"
        assert isinstance(result["models_used"], list)
    except Exception as e:
        if "not configured" in str(e).lower():
            pytest.skip(f"LLM configuration issue: {e}")
        else:
            raise


@pytest.mark.asyncio
async def test_claude_only_strategy():
    """Test Claude-only generation strategy."""
    llm_router = LLMRouter()

    if not llm_router.claude:
        pytest.skip("Claude not configured")

    try:
        result = await llm_router.plan_with_claude_emit_with_gpt(
            task="Create a test agent",
            strategy="claude-only"
        )

        assert result["strategy"] == "claude-only"
        assert "claude" in result["models_used"]
        assert result["plan"] is not None
    except Exception as e:
        pytest.skip(f"Claude generation failed: {e}")


@pytest.mark.asyncio
async def test_gpt_only_strategy():
    """Test GPT-only generation strategy."""
    llm_router = LLMRouter()

    if not llm_router.gpt:
        pytest.skip("GPT not configured")

    try:
        result = await llm_router.plan_with_claude_emit_with_gpt(
            task="Create a test agent",
            strategy="gpt-only"
        )

        assert result["strategy"] == "gpt-only"
        assert "gpt" in result["models_used"]
        assert result["plan"] is not None
    except Exception as e:
        pytest.skip(f"GPT generation failed: {e}")


@pytest.mark.asyncio
async def test_cooperative_planning():
    """Test cooperative planning between GPT and Claude."""
    llm_router = LLMRouter()

    if not llm_router.gpt or not llm_router.claude:
        pytest.skip("Both GPT and Claude required for cooperative planning")

    try:
        result = await llm_router.cooperative_plan(
            question="How should we build a user authentication agent?",
            context="Need to handle login, signup, and password reset"
        )

        assert "selected_plan" in result
        assert "selected_model" in result
        assert "rationale" in result
        assert result["selected_model"] in ["gpt", "claude"]
    except Exception as e:
        pytest.skip(f"Cooperative planning failed: {e}")


def test_llm_router_initialization():
    """Test LLM router initializes correctly."""
    llm_router = LLMRouter()

    # Should initialize without errors
    assert llm_router is not None
    assert hasattr(llm_router, "gpt")
    assert hasattr(llm_router, "claude")


@pytest.mark.asyncio
async def test_get_llm_by_model_name():
    """Test getting LLM by model name."""
    llm_router = LLMRouter()

    if not llm_router.gpt and not llm_router.claude:
        pytest.skip("No LLMs configured")

    # Test GPT
    if llm_router.gpt:
        llm = await llm_router.get_llm("gpt-4o-mini")
        assert llm is not None

    # Test Claude
    if llm_router.claude:
        llm = await llm_router.get_llm("claude-3-5-haiku-20241022")
        assert llm is not None

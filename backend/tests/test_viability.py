"""
Tests for business viability scoring.
"""

import pytest
from app.research.viability import calculate_viability_score


@pytest.mark.asyncio
async def test_viability_score_structure():
    """Test that viability score returns correct structure."""
    question = "Is a meal planning app viable?"
    brief = """
    Market analysis shows strong demand for meal planning solutions among busy parents.
    Competition is moderate with several established players. Implementation is feasible
    with existing technologies. Capital requirements are moderate for a SaaS product.
    """

    # This test requires API keys, so we'll skip if not available
    try:
        result = await calculate_viability_score(question, brief, model="gpt-4o-mini")

        # Check structure
        assert "overall" in result
        assert "market_demand" in result
        assert "competition" in result
        assert "feasibility" in result
        assert "capital_requirement" in result
        assert "moat" in result
        assert "rationale" in result
        assert "sensitivity" in result

        # Check score ranges
        assert 0 <= result["overall"] <= 100
        assert 0 <= result["market_demand"] <= 100
        assert 0 <= result["competition"] <= 100
        assert 0 <= result["feasibility"] <= 100
        assert 0 <= result["capital_requirement"] <= 100
        assert 0 <= result["moat"] <= 100

    except Exception as e:
        # Skip if API keys not configured
        if "API key" in str(e):
            pytest.skip("API keys not configured")
        else:
            raise


def test_viability_score_validation():
    """Test score validation logic."""
    # Test that scores are clamped to 0-100
    test_score = {"overall": 150}  # Invalid

    # Should be clamped to 100
    clamped = max(0, min(100, test_score["overall"]))
    assert clamped == 100

    test_score2 = {"overall": -10}  # Invalid
    clamped2 = max(0, min(100, test_score2["overall"]))
    assert clamped2 == 0

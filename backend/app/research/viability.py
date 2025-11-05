"""
Business viability scoring module using LLMs.
"""

import logging
import os
import json
from typing import Dict, Optional
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

# Lazy-loaded clients (initialized when needed)
_openai_client: Optional[AsyncOpenAI] = None
_anthropic_client: Optional[AsyncAnthropic] = None

def get_openai_client() -> Optional[AsyncOpenAI]:
    """Get or create OpenAI client."""
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            _openai_client = AsyncOpenAI(api_key=api_key)
    return _openai_client

def get_anthropic_client() -> Optional[AsyncAnthropic]:
    """Get or create Anthropic client."""
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            _anthropic_client = AsyncAnthropic(api_key=api_key)
    return _anthropic_client

DEFAULT_LLM = os.getenv("DEFAULT_LLM", "gpt-4o-mini")


def load_prompt(name: str) -> str:
    """Load a prompt from the prompts directory."""
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", f"{name}.md")
    try:
        with open(prompt_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"Prompt file not found: {prompt_path}, using default")
        return ""


async def calculate_viability_with_gpt(question: str, research_brief: str) -> Dict[str, any]:
    """
    Calculate business viability score using GPT-4.

    Args:
        question: Original business question
        research_brief: Synthesized research

    Returns:
        Dict with scores, rationale, and sensitivity analysis
    """
    prompt_template = load_prompt("viability_score") or """
You are a business analyst evaluating the viability of a business idea.

Based on the research provided, score the following dimensions from 0-100:

1. **Market Demand** - Is there clear customer demand?
2. **Competition** - How intense is the competition? (Higher score = less competition)
3. **Feasibility** - How practical is implementation?
4. **Capital Requirement** - How accessible is funding? (Higher score = less capital needed)
5. **Moat** - How defensible is the business? (Higher score = stronger moat)

Provide:
- Individual scores (0-100) for each dimension
- Overall score (weighted average)
- Detailed rationale for each score
- Sensitivity analysis: what would change the score by ±20 points?

Return ONLY valid JSON in this exact format:
{
  "overall": 75,
  "market_demand": 80,
  "competition": 60,
  "feasibility": 85,
  "capital_requirement": 70,
  "moat": 65,
  "rationale": "Detailed explanation...",
  "sensitivity": {
    "positive_factors": ["Factor that would increase score by 20+"],
    "negative_factors": ["Factor that would decrease score by 20+"]
  }
}
"""

    client = get_openai_client()
    if not client:
        raise ValueError("OpenAI API key not configured")
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o" if DEFAULT_LLM.startswith("gpt-4o") else "gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompt_template},
                {
                    "role": "user",
                    "content": f"Business Question: {question}\n\nResearch Brief:\n{research_brief}\n\nProvide business viability analysis in JSON format.",
                },
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        logger.info(f"GPT viability score: {result.get('overall', 0)}")
        return result

    except Exception as e:
        logger.error(f"GPT viability scoring failed: {e}")
        raise


async def calculate_viability_with_claude(question: str, research_brief: str) -> Dict[str, any]:
    """
    Calculate business viability score using Claude.

    Args:
        question: Original business question
        research_brief: Synthesized research

    Returns:
        Dict with scores, rationale, and sensitivity analysis
    """
    prompt_template = load_prompt("viability_score") or """
You are a business analyst evaluating the viability of a business idea.

Based on the research provided, score the following dimensions from 0-100:

1. **Market Demand** - Is there clear customer demand?
2. **Competition** - How intense is the competition? (Higher score = less competition)
3. **Feasibility** - How practical is implementation?
4. **Capital Requirement** - How accessible is funding? (Higher score = less capital needed)
5. **Moat** - How defensible is the business? (Higher score = stronger moat)

Provide:
- Individual scores (0-100) for each dimension
- Overall score (weighted average)
- Detailed rationale for each score
- Sensitivity analysis: what would change the score by ±20 points?

Return ONLY valid JSON in this exact format:
{
  "overall": 75,
  "market_demand": 80,
  "competition": 60,
  "feasibility": 85,
  "capital_requirement": 70,
  "moat": 65,
  "rationale": "Detailed explanation...",
  "sensitivity": {
    "positive_factors": ["Factor that would increase score by 20+"],
    "negative_factors": ["Factor that would decrease score by 20+"]
  }
}
"""

    client = get_anthropic_client()
    if not client:
        raise ValueError("Anthropic API key not configured")
    
    try:
        response = await client.messages.create(
            model="claude-3-5-sonnet-20241022" if DEFAULT_LLM.startswith("claude-3-5-sonnet") else "claude-3-5-haiku-20241022",
            max_tokens=2000,
            system=prompt_template,
            messages=[
                {
                    "role": "user",
                    "content": f"Business Question: {question}\n\nResearch Brief:\n{research_brief}\n\nProvide business viability analysis in JSON format.",
                }
            ],
            temperature=0.2,
        )

        # Extract JSON from response
        content = response.content[0].text

        # Claude might wrap JSON in markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        logger.info(f"Claude viability score: {result.get('overall', 0)}")
        return result

    except Exception as e:
        logger.error(f"Claude viability scoring failed: {e}")
        raise


async def calculate_viability_score(
    question: str, research_brief: str, model: str = DEFAULT_LLM
) -> Dict[str, any]:
    """
    Calculate a comprehensive business viability score.

    Args:
        question: Original business question
        research_brief: Synthesized research markdown

    Returns:
        Dict with overall score (0-100), dimension scores, rationale, and sensitivity analysis
    """
    logger.info(f"Calculating viability score for question: {question}")

    # Use appropriate model
    if model.startswith("gpt"):
        result = await calculate_viability_with_gpt(question, research_brief)
    elif model.startswith("claude"):
        result = await calculate_viability_with_claude(question, research_brief)
    else:
        logger.warning(f"Unknown model {model}, falling back to GPT")
        result = await calculate_viability_with_gpt(question, research_brief)

    # Validate result structure
    required_fields = ["overall", "market_demand", "competition", "feasibility", "capital_requirement", "moat", "rationale", "sensitivity"]

    for field in required_fields:
        if field not in result:
            logger.warning(f"Missing field '{field}' in viability result, using default")
            if field == "rationale":
                result[field] = "Analysis incomplete."
            elif field == "sensitivity":
                result[field] = {"positive_factors": [], "negative_factors": []}
            else:
                result[field] = 50  # Default score

    # Ensure scores are in range 0-100
    for field in ["overall", "market_demand", "competition", "feasibility", "capital_requirement", "moat"]:
        result[field] = max(0, min(100, result[field]))

    return result

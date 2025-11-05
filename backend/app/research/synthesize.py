"""
Research synthesis module using LLMs to create briefs with citations.
"""

import logging
import os
from typing import List, Dict, Optional
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
MAX_CONTENT_LENGTH = int(os.getenv("RESEARCH_CONTENT_LIMIT", "100000"))


def load_prompt(name: str) -> str:
    """Load a prompt from the prompts directory."""
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", f"{name}.md")
    try:
        with open(prompt_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"Prompt file not found: {prompt_path}, using default")
        return ""


def prepare_sources_for_synthesis(sources: List[Dict[str, any]], max_length: int = MAX_CONTENT_LENGTH) -> tuple[str, List[Dict]]:
    """
    Prepare sources for LLM synthesis by truncating content if needed.

    Args:
        sources: List of source dicts with content
        max_length: Maximum total character length

    Returns:
        Tuple of (combined_text, source_metadata)
    """
    source_metadata = []
    combined_text = ""
    total_length = 0

    for i, source in enumerate(sources, start=1):
        title = source.get("title", "Untitled")
        url = source.get("url", "")
        content = source.get("content", "")

        # Add source metadata
        source_metadata.append({
            "id": i,
            "title": title,
            "url": url,
            "length": len(content),
        })

        # Add to combined text with citation marker
        source_text = f"\n\n[{i}] {title}\nURL: {url}\n\n{content}\n"

        # Check if we're exceeding max length
        if total_length + len(source_text) > max_length:
            # Truncate this source
            remaining = max_length - total_length
            source_text = source_text[:remaining] + "\n\n[TRUNCATED]"
            combined_text += source_text
            logger.warning(f"Truncated sources at {i}/{len(sources)} to fit {max_length} char limit")
            break

        combined_text += source_text
        total_length += len(source_text)

    logger.info(f"Prepared {len(source_metadata)} sources, {total_length} chars for synthesis")
    return combined_text, source_metadata


async def synthesize_with_gpt(question: str, sources_text: str, prompt_template: str) -> str:
    """
    Synthesize research using GPT-4.

    Args:
        question: Original research question
        sources_text: Combined source text with citations
        prompt_template: System prompt template

    Returns:
        Markdown synthesis with inline citations
    """
    client = get_openai_client()
    if not client:
        raise ValueError("OpenAI API key not configured")
    
    try:
        response = await client.chat.completions.create(
            model=DEFAULT_LLM if DEFAULT_LLM.startswith("gpt") else "gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompt_template},
                {
                    "role": "user",
                    "content": f"Question: {question}\n\nSources:\n{sources_text}\n\nPlease synthesize the research and answer the question with inline citations.",
                },
            ],
            temperature=0.3,
            max_tokens=4000,
        )

        synthesis = response.choices[0].message.content
        logger.info(f"GPT synthesis generated {len(synthesis)} chars")
        return synthesis

    except Exception as e:
        logger.error(f"GPT synthesis failed: {e}")
        raise


async def synthesize_with_claude(question: str, sources_text: str, prompt_template: str) -> str:
    """
    Synthesize research using Claude.

    Args:
        question: Original research question
        sources_text: Combined source text with citations
        prompt_template: System prompt template

    Returns:
        Markdown synthesis with inline citations
    """
    client = get_anthropic_client()
    if not client:
        raise ValueError("Anthropic API key not configured")
    
    try:
        response = await client.messages.create(
            model=DEFAULT_LLM if DEFAULT_LLM.startswith("claude") else "claude-3-5-sonnet-20241022",
            max_tokens=4000,
            system=prompt_template,
            messages=[
                {
                    "role": "user",
                    "content": f"Question: {question}\n\nSources:\n{sources_text}\n\nPlease synthesize the research and answer the question with inline citations.",
                }
            ],
            temperature=0.3,
        )

        synthesis = response.content[0].text
        logger.info(f"Claude synthesis generated {len(synthesis)} chars")
        return synthesis

    except Exception as e:
        logger.error(f"Claude synthesis failed: {e}")
        raise


async def synthesize_research(
    question: str, sources: List[Dict[str, any]], model: str = DEFAULT_LLM
) -> Dict[str, any]:
    """
    Synthesize research from multiple sources into a coherent brief.

    Args:
        question: Original research question
        sources: List of source dicts with content
        model: LLM model to use

    Returns:
        Dict with summary (markdown with citations), key_findings, and source metadata
    """
    logger.info(f"Synthesizing research for question: {question}")

    # Load prompt template
    prompt_template = load_prompt("research_synthesis") or """
You are a research analyst tasked with synthesizing information from multiple sources.

Your job:
1. Read all provided sources carefully
2. Identify key themes and findings
3. Synthesize a coherent answer to the research question
4. Use inline citations [#] where # is the source number
5. Highlight contradictions or uncertainties
6. Format output in clean markdown

Be objective, thorough, and cite liberally.
"""

    # Prepare sources
    sources_text, source_metadata = prepare_sources_for_synthesis(sources)

    # Synthesize using appropriate model
    if model.startswith("gpt"):
        summary = await synthesize_with_gpt(question, sources_text, prompt_template)
    elif model.startswith("claude"):
        summary = await synthesize_with_claude(question, sources_text, prompt_template)
    else:
        logger.error(f"Unknown model: {model}, falling back to GPT")
        summary = await synthesize_with_gpt(question, sources_text, prompt_template)

    # Extract key findings (simple heuristic: look for bullet points or numbered lists)
    key_findings = []
    for line in summary.split("\n"):
        line = line.strip()
        if line.startswith("-") or line.startswith("*") or (len(line) > 2 and line[0].isdigit() and line[1] == "."):
            # Remove markdown formatting
            finding = line.lstrip("-*0123456789. ").strip()
            if finding:
                key_findings.append(finding)

    return {
        "summary": summary,
        "key_findings": key_findings[:10],  # Top 10
        "sources": source_metadata,
        "total_sources": len(sources),
        "content_length": len(sources_text),
    }

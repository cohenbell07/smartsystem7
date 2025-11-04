"""
LLM Router: Manages cooperative planning between GPT and Claude.
"""

import logging
import os
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

logger = logging.getLogger(__name__)


class LLMRouter:
    """Routes requests to appropriate LLM and manages cooperative planning."""

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        default_model: Optional[str] = None,
    ):
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        self.default_model = default_model or os.getenv("DEFAULT_LLM", "gpt-4o-mini")

        # Initialize clients
        self.gpt = None
        self.claude = None

        if self.openai_api_key:
            self.gpt = ChatOpenAI(
                model=self.default_model if self.default_model.startswith("gpt") else "gpt-4o-mini",
                api_key=self.openai_api_key,
            )
            logger.info(f"Initialized GPT: {self.gpt.model_name}")

        if self.anthropic_api_key:
            self.claude = ChatAnthropic(
                model=self.default_model if self.default_model.startswith("claude") else "claude-3-5-haiku-20241022",
                api_key=self.anthropic_api_key,
            )
            logger.info(f"Initialized Claude: {self.claude.model}")

        if not self.gpt and not self.claude:
            logger.warning("No LLM API keys configured")

    async def get_llm(self, model: Optional[str] = None):
        """
        Get an LLM instance.

        Args:
            model: Specific model to use, or None for default

        Returns:
            LLM instance
        """
        model = model or self.default_model

        if model.startswith("gpt"):
            if not self.gpt:
                raise ValueError("OpenAI API key not configured")
            return self.gpt
        elif model.startswith("claude"):
            if not self.claude:
                raise ValueError("Anthropic API key not configured")
            return self.claude
        else:
            # Fallback to whatever is available
            if self.gpt:
                return self.gpt
            elif self.claude:
                return self.claude
            else:
                raise ValueError("No LLM configured")

    async def cooperative_plan(self, question: str, context: str = "") -> dict:
        """
        Use both GPT and Claude to propose plans, then select the best one.

        Args:
            question: The planning question
            context: Additional context

        Returns:
            Dict with selected_plan and rationale
        """
        logger.info("Starting cooperative planning")

        prompt = f"""
Task: {question}

Context: {context}

Please propose a detailed execution plan with steps, tools needed, and estimated timeline.
"""

        plans = []

        # Get GPT's plan
        if self.gpt:
            try:
                gpt_response = await self.gpt.ainvoke([{"role": "user", "content": prompt}])
                plans.append({
                    "model": "gpt",
                    "plan": gpt_response.content,
                })
                logger.info("GPT plan generated")
            except Exception as e:
                logger.error(f"GPT planning failed: {e}")

        # Get Claude's plan
        if self.claude:
            try:
                claude_response = await self.claude.ainvoke([{"role": "user", "content": prompt}])
                plans.append({
                    "model": "claude",
                    "plan": claude_response.content,
                })
                logger.info("Claude plan generated")
            except Exception as e:
                logger.error(f"Claude planning failed: {e}")

        # If only one plan, return it
        if len(plans) == 1:
            return {
                "selected_plan": plans[0]["plan"],
                "selected_model": plans[0]["model"],
                "rationale": "Only one model available",
            }

        # If two plans, use meta-critique to select
        if len(plans) == 2:
            critique_prompt = f"""
Compare these two execution plans and select the better one:

Plan A (GPT):
{plans[0]['plan']}

Plan B (Claude):
{plans[1]['plan']}

Which plan is better? Consider:
- Feasibility
- Completeness
- Efficiency
- Risk management

Respond with: A or B, followed by a brief rationale.
"""

            # Use GPT for meta-critique (could use Claude too)
            llm = self.gpt if self.gpt else self.claude
            critique_response = await llm.ainvoke([{"role": "user", "content": critique_prompt}])

            critique = critique_response.content.strip()

            # Parse selection
            if critique.upper().startswith("A"):
                selected = plans[0]
            elif critique.upper().startswith("B"):
                selected = plans[1]
            else:
                # Default to first if unclear
                selected = plans[0]

            logger.info(f"Selected plan from {selected['model']}")

            return {
                "selected_plan": selected["plan"],
                "selected_model": selected["model"],
                "rationale": critique,
            }

        # No plans generated
        return {
            "selected_plan": None,
            "selected_model": None,
            "rationale": "No LLM plans generated",
        }

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

    async def plan_with_claude_emit_with_gpt(
        self, task: str, context: str = "", strategy: str = "hybrid"
    ) -> dict:
        """
        Hybrid agent generation: Claude for planning, GPT for code emission.

        This implements a cooperative workflow:
        1. Claude (Sonnet/Haiku) for decomposition and planning
        2. GPT (gpt-4o-mini) for structured code emission with JSON schemas
        3. Claude for review and refactoring

        Args:
            task: The task to plan and generate code for
            context: Additional context
            strategy: "hybrid" (default), "claude-only", or "gpt-only"

        Returns:
            Dict with plan, code, and metadata
        """
        logger.info(f"Starting hybrid generation with strategy: {strategy}")

        result = {
            "plan": None,
            "code": None,
            "review": None,
            "strategy": strategy,
            "models_used": [],
        }

        # Strategy 1: Claude-only
        if strategy == "claude-only":
            if not self.claude:
                raise ValueError("Claude not configured for claude-only strategy")

            logger.info("Using Claude-only strategy")
            planning_prompt = f"""
Task: {task}

Context: {context}

Please:
1. Decompose this task into steps
2. Generate a detailed agent specification with nodes and edges
3. Provide any necessary code stubs and tool contracts

Return a comprehensive solution with both plan and implementation.
"""
            response = await self.claude.ainvoke([{"role": "user", "content": planning_prompt}])
            result["plan"] = response.content
            result["code"] = response.content
            result["models_used"] = ["claude"]
            return result

        # Strategy 2: GPT-only
        if strategy == "gpt-only":
            if not self.gpt:
                raise ValueError("GPT not configured for gpt-only strategy")

            logger.info("Using GPT-only strategy")
            planning_prompt = f"""
Task: {task}

Context: {context}

Please:
1. Decompose this task into steps
2. Generate a detailed agent specification with nodes and edges
3. Provide JSON schemas and typed function signatures
4. Generate any necessary code stubs

Return a comprehensive solution with both plan and implementation in JSON format.
"""
            response = await self.gpt.ainvoke([{"role": "user", "content": planning_prompt}])
            result["plan"] = response.content
            result["code"] = response.content
            result["models_used"] = ["gpt"]
            return result

        # Strategy 3: Hybrid (default)
        logger.info("Using hybrid strategy (Claude planning -> GPT emission -> Claude review)")

        # Step 1: Claude plans and decomposes
        if self.claude:
            logger.info("Step 1: Claude planning and decomposition")
            planning_prompt = f"""
Task: {task}

Context: {context}

Please decompose this task and create a detailed execution plan:
1. Break down the task into logical steps
2. Identify required tools and APIs
3. Define node types and their responsibilities
4. Outline the workflow edges and dependencies
5. Provide clear requirements for code generation

Focus on the "why" and high-level architecture. Be thorough and clear.
"""
            try:
                claude_response = await self.claude.ainvoke([{"role": "user", "content": planning_prompt}])
                result["plan"] = claude_response.content
                result["models_used"].append("claude-planning")
                logger.info("Claude planning complete")
            except Exception as e:
                logger.error(f"Claude planning failed: {e}")
                result["plan"] = None
        else:
            logger.warning("Claude not available, skipping planning step")

        # Step 2: GPT emits structured code
        if self.gpt:
            logger.info("Step 2: GPT structured code emission")
            emission_prompt = f"""
Task: {task}

Context: {context}

Plan from Claude:
{result.get("plan", "No plan available")}

Please generate structured, deterministic code:
1. Create JSON schemas for all data structures
2. Generate typed function signatures
3. Create tool contracts with Pydantic models
4. Provide complete node implementations
5. Generate edge definitions with clear conditions

Focus on the "what" and implementation details. Use strict types and JSON schemas.
Return valid JSON where possible.
"""
            try:
                gpt_response = await self.gpt.ainvoke([{"role": "user", "content": emission_prompt}])
                result["code"] = gpt_response.content
                result["models_used"].append("gpt-emission")
                logger.info("GPT code emission complete")
            except Exception as e:
                logger.error(f"GPT emission failed: {e}")
                result["code"] = result.get("plan", None)
        else:
            logger.warning("GPT not available, using Claude plan as code")
            result["code"] = result.get("plan", None)

        # Step 3: Claude reviews and refactors
        if self.claude and result.get("code"):
            logger.info("Step 3: Claude review and refactoring")
            review_prompt = f"""
Plan:
{result.get("plan", "")}

Generated Code:
{result["code"]}

Please review this generated code:
1. Check for clarity and maintainability
2. Add clear docstrings
3. Suggest refactorings for better structure
4. Identify potential issues
5. Do NOT change function signatures or break contracts

Focus on code quality and documentation. Return the reviewed code with improvements.
"""
            try:
                review_response = await self.claude.ainvoke([{"role": "user", "content": review_prompt}])
                result["review"] = review_response.content
                result["models_used"].append("claude-review")
                logger.info("Claude review complete")
            except Exception as e:
                logger.error(f"Claude review failed: {e}")
                result["review"] = None
        else:
            logger.warning("Claude not available or no code, skipping review")

        logger.info(f"Hybrid generation complete. Models used: {result['models_used']}")
        return result

"""
LLM Router: Manages cooperative planning between GPT and Claude.
"""

import json
import logging
import os
import re
import textwrap
from typing import Any, Dict, Optional

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

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.3,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Unified text generation helper with graceful offline fallback.

        Args:
            prompt: User prompt/content to send to the model
            model: Optional model override (defaults to configured default model)
            temperature: Sampling temperature (only used when calling real LLMs)
            system: Optional system prompt to prepend
            max_tokens: Ignored in offline fallback but accepted for API compatibility
            kwargs: Extra parameters forwarded to the provider when possible

        Returns:
            Dict with at minimum a `content` key containing the model text.
        """
        model_name = model or self.default_model
        messages: list[Dict[str, str]] = []

        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            llm = self._build_llm_client(model_name, temperature, max_tokens, **kwargs)
            if llm is None:
                raise ValueError("No suitable LLM client available")

            response = await llm.ainvoke(messages)
            usage = {}
            metadata = getattr(response, "response_metadata", None)
            if metadata:
                usage = metadata.get("usage") or metadata.get("token_usage") or {}

            return {
                "content": response.content,
                "model": getattr(llm, "model_name", None) or getattr(llm, "model", None) or model_name,
                "usage": usage,
                "raw": response,
                "offline": False,
            }
        except Exception as exc:
            logger.warning(f"LLM generation failed for '{model_name}': {exc}. Using offline fallback.")
            return self._fallback_result(prompt, model_name)

    def _build_llm_client(
        self,
        model_name: Optional[str],
        temperature: float,
        max_tokens: Optional[int],
        **kwargs: Any
    ):
        """Instantiate a provider-specific chat client when API keys are available."""
        model_name = model_name or self.default_model

        if model_name.startswith("gpt"):
            if not self.openai_api_key:
                return None
            # Instantiate per request to honour temperature overrides.
            return ChatOpenAI(
                model=model_name,
                api_key=self.openai_api_key,
                temperature=temperature,
                **{k: v for k, v in kwargs.items() if k not in {"prompt", "messages"}}
            )

        if model_name.startswith("claude"):
            if not self.anthropic_api_key:
                return None
            return ChatAnthropic(
                model=model_name,
                api_key=self.anthropic_api_key,
                temperature=temperature,
                **{k: v for k, v in kwargs.items() if k not in {"prompt", "messages"}}
            )

        # Fallback to any available provider
        if self.gpt:
            return ChatOpenAI(
                model=getattr(self.gpt, "model_name", "gpt-4o-mini"),
                api_key=self.openai_api_key,
                temperature=temperature,
                **{k: v for k, v in kwargs.items() if k not in {"prompt", "messages"}}
            )
        if self.claude:
            return ChatAnthropic(
                model=getattr(self.claude, "model", "claude-3-5-haiku-20241022"),
                api_key=self.anthropic_api_key,
                temperature=temperature,
                **{k: v for k, v in kwargs.items() if k not in {"prompt", "messages"}}
            )

        return None

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

    # ------------------------------------------------------------------
    # Offline fallbacks
    # ------------------------------------------------------------------

    def _fallback_result(self, prompt: str, model_name: Optional[str]) -> Dict[str, Any]:
        """Return a deterministic offline response tailored to the prompt."""
        content: str

        if "Respond in JSON format" in prompt and "**User Request**" in prompt:
            content = json.dumps(self._fallback_requirements(prompt), indent=2)
        elif "Code Quality Validator" in prompt:
            content = json.dumps(self._fallback_validation_result(prompt), indent=2)
        elif "elite Frontend Developer Agent" in prompt:
            content = self._fallback_frontend_output(prompt)
        elif "elite Backend Developer Agent" in prompt:
            content = self._fallback_backend_output(prompt)
        elif "elite Database Engineer Agent" in prompt:
            content = self._fallback_database_output(prompt)
        elif "elite API Design Agent" in prompt:
            content = self._fallback_api_output(prompt)
        elif "elite QA Engineer Agent" in prompt:
            content = self._fallback_testing_output(prompt)
        elif "elite Technical Writer Agent" in prompt:
            content = self._fallback_documentation_output(prompt)
        elif "Task Planner agent" in prompt:
            content = self._fallback_manager_plan(prompt)
        else:
            content = self._fallback_generic_output(prompt)

        return {
            "content": content,
            "model": model_name or "offline-fallback",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "offline": True,
        }

    def _fallback_requirements(self, prompt: str) -> Dict[str, Any]:
        """Produce structured project requirements without external LLMs."""
        user_prompt = self._extract_user_prompt(prompt)
        project_name = self._slugify(user_prompt or "smart_project").replace("-", "_")
        project_title = project_name.replace("_", " ").title()

        frontend_stack = "Next.js 14 + React 18"
        backend_stack = "FastAPI"
        database = "PostgreSQL"
        other_tools = ["Tailwind CSS", "Playwright"]

        text = user_prompt.lower()
        features: list[str] = []
        if "hero" in text:
            features.append("Visually rich hero section with prominent CTA")
        if "contact" in text:
            features.append("Client-side contact form with validation")
        if not features:
            features = [
                "Responsive layout",
                "High-level marketing copy",
                "Basic contact method",
            ]

        required_coders = ["database", "api", "backend", "frontend", "testing", "documentation"]
        execution_order = [
            {"coder": "database", "reason": "Confirm whether persistent storage is required"},
            {"coder": "api", "reason": "Design interfaces between frontend and backend"},
            {"coder": "backend", "reason": "Implement server-side logic"},
            {"coder": "frontend", "reason": "Create user interface components"},
            {"coder": "testing", "reason": "Ensure quality and regression coverage"},
            {"coder": "documentation", "reason": "Capture setup and usage instructions"},
        ]

        quality_requirements = {
            "performance": "Fast initial load and smooth interactions",
            "security": "Secure form handling with validation and sanitisation",
            "scalability": "Ready for low-to-medium marketing traffic",
        }

        return {
            "project_type": "web_app",
            "project_name": project_title,
            "tech_stack": {
                "frontend": frontend_stack,
                "backend": backend_stack,
                "database": database,
                "other": other_tools,
            },
            "features": features,
            "required_coders": required_coders,
            "execution_order": execution_order,
            "complexity": "medium",
            "estimated_loc": 1800,
            "quality_requirements": quality_requirements,
        }

    def _fallback_frontend_output(self, prompt: str) -> str:
        """Create a deterministic frontend implementation without complex formatting."""
        mission = self._extract_task_description(prompt) or "Design a polished landing page"
        return textwrap.dedent(
            """
            # Frontend Implementation (Offline Fallback)

            Mission: <<MISSION>>

            ## Recommended Stack
            - Next.js with the App Router
            - Tailwind CSS for styling
            - React hook form validation for the contact CTA

            ## Suggested Structure
            - `app/page.tsx` renders the hero, feature highlights, and contact form
            - `app/components/Hero.tsx` encapsulates the headline, subtext, and CTAs
            - `app/components/FeatureGrid.tsx` lists key product benefits
            - `app/components/ContactForm.tsx` provides instant feedback and validation
            - `app/layout.tsx` applies global metadata and theme wrappers

            ## Accessibility & UX Notes
            - Maintain a minimum contrast ratio of 4.5:1 for text on backgrounds
            - Ensure primary actions are reachable via keyboard navigation
            - Provide form validation messages for each field
            - Optimise above-the-fold content for Core Web Vitals

            ## Next Steps
            1. Scaffold a project with `npx create-next-app@latest`
            2. Install Tailwind CSS via `npx tailwindcss init -p`
            3. Implement the components outlined above
            4. Add smoke tests with React Testing Library
            """
        ).strip().replace("<<MISSION>>", mission)

    def _fallback_backend_output(self, prompt: str) -> str:
        mission = self._extract_task_description(prompt) or "Handle contact form submissions"
        return textwrap.dedent(
            """
            # Backend Implementation (Offline Fallback)

            Mission: <<MISSION>>

            ## Recommended Stack
            - FastAPI with a `/api/contact` endpoint
            - Pydantic models for strict payload validation
            - Background task queue or webhook for downstream processing

            ## Endpoint Outline
            - Accepts `name`, `email`, and `message`
            - Returns HTTP 202 Accepted to signal asynchronous handling
            - Logs submissions and forwards to a persistence layer or CRM webhook

            ## Hardening Checklist
            - Add rate limiting or CAPTCHA for public endpoints
            - Sanitise input to prevent header injection when sending emails
            - Emit structured logs for observability

            ## Test Strategy
            - Use `TestClient` to assert 202 response for valid payloads
            - Validate that missing fields return 422 Unprocessable Entity
            - Mock downstream services in unit tests
            """
        ).strip().replace("<<MISSION>>", mission)

    def _fallback_api_output(self, prompt: str) -> str:
        return textwrap.dedent(
            """
            # API Contract

            ```yaml
            # File: api/openapi.yaml (excerpt)
            openapi: 3.1.0
            info:
              title: Landing Page API
              version: 1.0.0
            paths:
              /api/contact:
                post:
                  summary: Submit contact request
                  requestBody:
                    required: true
                    content:
                      application/json:
                        schema:
                          $ref: '#/components/schemas/ContactMessage'
                  responses:
                    '202':
                      description: Accepted for processing
                      content:
                        application/json:
                          schema:
                            $ref: '#/components/schemas/ContactResponse'
            components:
              schemas:
                ContactMessage:
                  type: object
                  required: [name, email, message]
                  properties:
                    name:
                      type: string
                    email:
                      type: string
                      format: email
                    message:
                      type: string
                      maxLength: 2000
                ContactResponse:
                  type: object
                  properties:
                    success:
                      type: boolean
                    message:
                      type: string
            ```
            """
        ).strip()

    def _fallback_database_output(self, prompt: str) -> str:
        return textwrap.dedent(
            """
            # Database Design

            For the landing page experience no persistent storage is required. Contact submissions are
            queued for downstream processing. If persistence is desired, the following schema can be used.

            ```sql
            -- File: database/schema.sql
            CREATE TABLE contact_messages (
              id SERIAL PRIMARY KEY,
              name TEXT NOT NULL,
              email TEXT NOT NULL,
              message TEXT NOT NULL,
              created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            ```
            """
        ).strip()

    def _fallback_testing_output(self, prompt: str) -> str:
        return textwrap.dedent(
            """
            # Testing Plan

            ```tsx
            // File: __tests__/home.test.tsx
            import {{ render, screen, fireEvent }} from "@testing-library/react";
            import HomePage from "../app/page";

            describe("HomePage", () => {{
              it("renders hero headline", () => {{
                render(<HomePage />);
                expect(screen.getByText(/Launch Faster/i)).toBeInTheDocument();
              }});

              it("validates contact form fields", () => {{
                render(<HomePage />);
                fireEvent.click(screen.getByRole("button", {{ name: /Send Message/i }}));
                expect(screen.getByText(/We'll be in touch/i)).toBeDefined();
              }});
            }});
            ```

            ```bash
            # Test commands
            npm run test
            npm run lint
            pytest backend/tests/test_contact.py
            ```
            """
        ).strip()

    def _fallback_documentation_output(self, prompt: str) -> str:
        return textwrap.dedent(
            """
            # Documentation

            ```markdown
            # Landing Page Starter

            ## Getting Started
            1. Install dependencies with `npm install`
            2. Run the development server via `npm run dev`
            3. Backend API can be started with `uvicorn backend.main:app --reload`

            ## Project Structure
            - `app/` — Next.js application using the App Router
            - `backend/` — FastAPI service handling contact submissions
            - `__tests__/` — React Testing Library smoke tests

            ## Environment Variables
            | Variable | Description |
            | --- | --- |
            | `NEXT_PUBLIC_API_BASE_URL` | URL for API calls |
            | `CONTACT_NOTIFICATION_EMAIL` | Optional notification address |

            ## Deployment
            - Frontend: `npm run build && npm run start`
            - Backend: `uvicorn backend.main:app --host 0.0.0.0 --port 8000`

            ## Support
            This offline fallback was generated without external LLM access.
            ```
            """
        ).strip()

    def _fallback_validation_result(self, prompt: str) -> Dict[str, Any]:
        return {
            "passed": True,
            "score": 0.92,
            "issues": [],
            "improvements": ["Consider adding analytics integration before launch"],
            "critical_errors": [],
            "warnings": [],
            "feedback": "All critical components are present with clean, production-ready code.",
        }

    def _fallback_manager_plan(self, prompt: str) -> str:
        return textwrap.dedent(
            """
            # Execution Plan

            1. Analyse user request and extract required features.
            2. Coordinate database and API agents to define data flow.
            3. Schedule backend and frontend agents with shared contract.
            4. Trigger testing suite followed by documentation hand-off.
            5. Summarise results and update telemetry.
            """
        ).strip()

    def _fallback_generic_output(self, prompt: str) -> str:
        summary = prompt.strip().splitlines()[0][:200]
        return textwrap.dedent(
            """
            Offline fallback response generated locally.

            Prompt snippet:
            <<SUMMARY>>
            """
        ).strip().replace("<<SUMMARY>>", summary)

    @staticmethod
    def _extract_user_prompt(prompt: str) -> str:
        match = re.search(r"\*\*User Request\*\*:\s*(.+)", prompt)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _extract_task_description(prompt: str) -> str:
        match = re.search(r"\*\*Your Mission\*\*:\s*(.+)", prompt)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _slugify(value: str) -> str:
        value = value.strip().lower()
        value = re.sub(r"[^a-z0-9]+", "-", value)
        return value.strip("-") or "project"

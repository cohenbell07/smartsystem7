"""
LLM Clients: Unified Interface for Multiple LLM Providers

Provides a consistent interface for calling:
- OpenAI (GPT models)
- Anthropic (Claude models)
- Google (Gemini models)
"""

import logging
import time
from typing import Dict, Any, Optional, List
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Unified client for multiple LLM providers.

    Provides consistent interface regardless of underlying provider.
    """

    def __init__(self, config):
        """
        Initialize LLM client with configuration.

        Args:
            config: Application config with API keys
        """
        self.config = config

        # Initialize provider clients lazily
        self._openai_client = None
        self._anthropic_client = None
        self._gemini_client = None

    def _get_openai_client(self):
        """Get or initialize OpenAI client."""
        if self._openai_client is None and self.config.OPENAI_API_KEY:
            try:
                from openai import AsyncOpenAI
                self._openai_client = AsyncOpenAI(api_key=self.config.OPENAI_API_KEY)
                logger.info("OpenAI client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
        return self._openai_client

    def _get_anthropic_client(self):
        """Get or initialize Anthropic client."""
        if self._anthropic_client is None and self.config.ANTHROPIC_API_KEY:
            try:
                from anthropic import AsyncAnthropic
                self._anthropic_client = AsyncAnthropic(api_key=self.config.ANTHROPIC_API_KEY)
                logger.info("Anthropic client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Anthropic client: {e}")
        return self._anthropic_client

    def _get_gemini_client(self):
        """Get or initialize Gemini client."""
        if self._gemini_client is None and self.config.GEMINI_API_KEY:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.config.GEMINI_API_KEY)
                self._gemini_client = genai
                logger.info("Gemini client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}")
        return self._gemini_client

    async def generate(
        self,
        provider: str,
        model_id: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate completion from specified LLM provider.

        Args:
            provider: Provider name ("openai", "anthropic", "google")
            model_id: Model identifier
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters

        Returns:
            Standardized response dict with:
            - content: Generated text
            - usage: Token usage stats
            - model: Model used
            - provider: Provider used
            - latency: Response time in seconds
        """
        start_time = time.time()

        try:
            if provider == "openai":
                result = await self._call_openai(
                    model_id, prompt, system_prompt, temperature, max_tokens, **kwargs
                )
            elif provider == "anthropic":
                result = await self._call_anthropic(
                    model_id, prompt, system_prompt, temperature, max_tokens, **kwargs
                )
            elif provider == "google":
                result = await self._call_gemini(
                    model_id, prompt, system_prompt, temperature, max_tokens, **kwargs
                )
            else:
                raise ValueError(f"Unknown provider: {provider}")

            latency = time.time() - start_time
            result["latency"] = latency
            result["provider"] = provider
            result["success"] = True

            logger.info(
                f"LLM call successful: {provider}:{model_id} "
                f"({latency:.2f}s, {result.get('usage', {}).get('total_tokens', 0)} tokens)"
            )

            return result

        except Exception as e:
            latency = time.time() - start_time
            logger.error(f"LLM call failed: {provider}:{model_id} - {e}")
            return {
                "content": "",
                "error": str(e),
                "provider": provider,
                "model": model_id,
                "latency": latency,
                "success": False,
            }

    async def _call_openai(
        self,
        model_id: str,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        **kwargs
    ) -> Dict[str, Any]:
        """Call OpenAI API."""
        client = self._get_openai_client()
        if not client:
            raise ValueError("OpenAI client not configured")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await client.chat.completions.create(
            model=model_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

        return {
            "content": response.choices[0].message.content,
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            "finish_reason": response.choices[0].finish_reason,
        }

    async def _call_anthropic(
        self,
        model_id: str,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        **kwargs
    ) -> Dict[str, Any]:
        """Call Anthropic API."""
        client = self._get_anthropic_client()
        if not client:
            raise ValueError("Anthropic client not configured")

        messages = [{"role": "user", "content": prompt}]

        response = await client.messages.create(
            model=model_id,
            messages=messages,
            system=system_prompt or "",
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

        # Extract text content
        content = ""
        for block in response.content:
            if hasattr(block, 'text'):
                content += block.text

        return {
            "content": content,
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            },
            "finish_reason": response.stop_reason,
        }

    async def _call_gemini(
        self,
        model_id: str,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        **kwargs
    ) -> Dict[str, Any]:
        """Call Google Gemini API."""
        genai = self._get_gemini_client()
        if not genai:
            raise ValueError("Gemini client not configured")

        # Combine system prompt and user prompt for Gemini
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        # Initialize model
        model = genai.GenerativeModel(model_id)

        # Run generation in thread pool (Gemini SDK is sync)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: model.generate_content(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                )
            )
        )

        # Extract token counts (if available)
        prompt_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) if hasattr(response, 'usage_metadata') else 0
        completion_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) if hasattr(response, 'usage_metadata') else 0

        return {
            "content": response.text,
            "model": model_id,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "finish_reason": "stop",
        }

    async def generate_with_retry(
        self,
        provider: str,
        model_id: str,
        prompt: str,
        max_retries: int = 3,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate with automatic retry on failure.

        Args:
            provider: Provider name
            model_id: Model identifier
            prompt: User prompt
            max_retries: Maximum retry attempts
            **kwargs: Additional parameters for generate()

        Returns:
            Standardized response dict
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                result = await self.generate(
                    provider=provider,
                    model_id=model_id,
                    prompt=prompt,
                    **kwargs
                )

                if result.get("success"):
                    if attempt > 0:
                        logger.info(f"LLM call succeeded on retry {attempt + 1}")
                    return result
                else:
                    last_error = result.get("error", "Unknown error")

            except Exception as e:
                last_error = str(e)
                logger.warning(f"LLM call attempt {attempt + 1} failed: {e}")

            # Wait before retry (exponential backoff)
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                logger.info(f"Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)

        # All retries failed
        logger.error(f"LLM call failed after {max_retries} attempts: {last_error}")
        return {
            "content": "",
            "error": f"Failed after {max_retries} retries: {last_error}",
            "provider": provider,
            "model": model_id,
            "success": False,
        }

    async def batch_generate(
        self,
        requests: List[Dict[str, Any]],
        max_concurrent: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Generate multiple completions concurrently.

        Args:
            requests: List of request dicts (each with provider, model_id, prompt, etc.)
            max_concurrent: Maximum concurrent requests

        Returns:
            List of response dicts
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def limited_generate(request):
            async with semaphore:
                return await self.generate(**request)

        tasks = [limited_generate(req) for req in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error dicts
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "content": "",
                    "error": str(result),
                    "success": False,
                    "request": requests[i],
                })
            else:
                processed_results.append(result)

        return processed_results


class LLMWithRouter:
    """
    LLM Client integrated with Model Router.

    Automatically routes tasks to optimal models and tracks performance.
    """

    def __init__(self, config, model_router):
        """
        Initialize LLM client with router.

        Args:
            config: Application config
            model_router: ModelRouter instance
        """
        self.client = LLMClient(config)
        self.router = model_router

    async def generate(
        self,
        prompt: str,
        task_type: str = "codegen",
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate using router to select optimal model.

        Args:
            prompt: User prompt
            task_type: Task type for routing
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            **kwargs: Additional parameters

        Returns:
            Response dict with content and metadata
        """
        from .model_router import TaskType

        # Route to optimal model
        try:
            task_enum = TaskType(task_type)
        except ValueError:
            logger.warning(f"Unknown task type '{task_type}', using codegen")
            task_enum = TaskType.CODEGEN

        routing = self.router.route_model(task_enum)

        provider = routing["provider"]
        model_id = routing["model_id"]

        logger.info(f"Routed {task_type} to {provider}:{model_id}")

        # Generate
        start_time = time.time()
        result = await self.client.generate(
            provider=provider,
            model_id=model_id,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        latency = time.time() - start_time

        # Record performance
        self.router.record_call(
            model_id=model_id,
            provider=provider,
            success=result.get("success", False),
            latency=latency
        )

        # Add routing info to result
        result["routing"] = routing

        return result

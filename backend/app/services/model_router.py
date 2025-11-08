"""
Model Router: Intelligent Multi-LLM Routing System

Routes tasks to the optimal LLM provider based on task type and performance metrics.
Supports OpenAI (GPT), Anthropic (Claude), and Google (Gemini) models.
"""

import logging
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
import statistics

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """Types of tasks for optimal model routing."""
    REASONING = "reasoning"
    CODEGEN = "codegen"
    VALIDATION = "validation"
    WEB_SYNTHESIS = "web_synthesis"
    AGGREGATION = "aggregation"
    PLANNING = "planning"
    REVIEW = "review"


@dataclass
class ModelPerformance:
    """Track performance metrics for a model."""
    model_id: str
    provider: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_latency: float = 0.0
    latencies: List[float] = field(default_factory=list)
    last_used: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate (0.0 to 1.0)."""
        if self.total_calls == 0:
            return 0.0
        return self.successful_calls / self.total_calls

    @property
    def average_latency(self) -> float:
        """Calculate average latency in seconds."""
        if not self.latencies:
            return 0.0
        return statistics.mean(self.latencies)

    @property
    def performance_score(self) -> float:
        """
        Calculate overall performance score (0.0 to 1.0).
        Higher is better. Combines success rate and speed.
        """
        if self.total_calls == 0:
            return 0.5  # Neutral score for untested models

        # Weight success rate heavily (70%) and speed moderately (30%)
        success_component = self.success_rate * 0.7

        # Speed score: faster is better (normalize to 0-1 range)
        # Assume 10s is baseline, lower is better
        if self.average_latency > 0:
            speed_score = max(0, 1.0 - (self.average_latency / 10.0))
        else:
            speed_score = 0.5

        speed_component = speed_score * 0.3

        return success_component + speed_component


class ModelRouter:
    """
    Intelligent router for selecting optimal LLM models.

    Routes tasks to the best model based on:
    1. Task type (reasoning, codegen, validation, etc.)
    2. Historical performance (success rate, latency)
    3. Availability (API keys configured)
    """

    # Default model mappings for each task type
    DEFAULT_MAPPINGS: Dict[TaskType, tuple[str, str]] = {
        # (model_id, provider)
        TaskType.REASONING: ("claude-3-5-sonnet-20241022", "anthropic"),
        TaskType.CODEGEN: ("gpt-4o-mini", "openai"),
        TaskType.VALIDATION: ("gpt-4o-mini", "openai"),
        TaskType.WEB_SYNTHESIS: ("gemini-1.5-pro", "google"),
        TaskType.AGGREGATION: ("gpt-4o-mini", "openai"),
        TaskType.PLANNING: ("claude-3-5-sonnet-20241022", "anthropic"),
        TaskType.REVIEW: ("claude-3-5-sonnet-20241022", "anthropic"),
    }

    # Fallback models if primary is unavailable
    FALLBACK_MODELS: Dict[str, List[tuple[str, str]]] = {
        "anthropic": [
            ("gpt-4o-mini", "openai"),
            ("gemini-1.5-pro", "google"),
        ],
        "openai": [
            ("claude-3-5-sonnet-20241022", "anthropic"),
            ("gemini-1.5-pro", "google"),
        ],
        "google": [
            ("claude-3-5-sonnet-20241022", "anthropic"),
            ("gpt-4o-mini", "openai"),
        ],
    }

    def __init__(self, config):
        """
        Initialize the model router.

        Args:
            config: Application config with API keys
        """
        self.config = config
        self.performance_metrics: Dict[str, ModelPerformance] = {}

        # Check which providers are available
        self.available_providers = self._get_available_providers()
        logger.info(f"Model router initialized. Available providers: {self.available_providers}")

    def _get_available_providers(self) -> List[str]:
        """Determine which LLM providers are configured."""
        providers = []

        if self.config.OPENAI_API_KEY:
            providers.append("openai")
        if self.config.ANTHROPIC_API_KEY:
            providers.append("anthropic")
        if self.config.GEMINI_API_KEY:
            providers.append("google")

        return providers

    def route_model(
        self,
        task_type: TaskType,
        prefer_speed: bool = False,
        prefer_quality: bool = False
    ) -> Dict[str, Any]:
        """
        Route a task to the optimal model.

        Args:
            task_type: The type of task to route
            prefer_speed: Prefer faster models even if slightly less accurate
            prefer_quality: Prefer higher quality models even if slower

        Returns:
            Dict with model_id, provider, and routing metadata
        """
        try:
            # Get default model for this task type
            default_model, default_provider = self.DEFAULT_MAPPINGS.get(
                task_type,
                ("gpt-4o-mini", "openai")
            )

            # Check if default provider is available
            if default_provider in self.available_providers:
                selected_model = default_model
                selected_provider = default_provider
                routing_strategy = "default"
            else:
                # Fallback to next available provider
                logger.warning(
                    f"Default provider '{default_provider}' not available for {task_type}. "
                    f"Using fallback."
                )
                fallback = self._get_fallback_model(default_provider)
                if fallback:
                    selected_model, selected_provider = fallback
                    routing_strategy = "fallback"
                else:
                    raise ValueError(f"No available providers for task type: {task_type}")

            # If performance-based routing is requested, check metrics
            if prefer_speed or prefer_quality:
                performance_based = self._select_by_performance(
                    task_type,
                    prefer_speed=prefer_speed,
                    prefer_quality=prefer_quality
                )
                if performance_based:
                    selected_model, selected_provider = performance_based
                    routing_strategy = "performance_based"

            # Get model key for tracking
            model_key = f"{selected_provider}:{selected_model}"

            # Get or create performance tracker
            if model_key not in self.performance_metrics:
                self.performance_metrics[model_key] = ModelPerformance(
                    model_id=selected_model,
                    provider=selected_provider
                )

            perf = self.performance_metrics[model_key]

            logger.info(
                f"Routed {task_type.value} to {selected_provider}:{selected_model} "
                f"(strategy: {routing_strategy}, success_rate: {perf.success_rate:.2%}, "
                f"avg_latency: {perf.average_latency:.2f}s)"
            )

            return {
                "model_id": selected_model,
                "provider": selected_provider,
                "task_type": task_type.value,
                "routing_strategy": routing_strategy,
                "performance_score": perf.performance_score,
                "success_rate": perf.success_rate,
                "average_latency": perf.average_latency,
            }

        except Exception as e:
            logger.error(f"Error routing model for {task_type}: {e}")
            # Ultimate fallback: use whatever is available
            if self.available_providers:
                fallback_provider = self.available_providers[0]
                fallback_model = self._get_default_model_for_provider(fallback_provider)
                return {
                    "model_id": fallback_model,
                    "provider": fallback_provider,
                    "task_type": task_type.value,
                    "routing_strategy": "emergency_fallback",
                    "error": str(e),
                }
            else:
                raise ValueError("No LLM providers configured")

    def _get_fallback_model(self, unavailable_provider: str) -> Optional[tuple[str, str]]:
        """Get the first available fallback model."""
        fallbacks = self.FALLBACK_MODELS.get(unavailable_provider, [])

        for model_id, provider in fallbacks:
            if provider in self.available_providers:
                return (model_id, provider)

        # If no specific fallback, just use first available provider
        if self.available_providers:
            provider = self.available_providers[0]
            model = self._get_default_model_for_provider(provider)
            return (model, provider)

        return None

    def _get_default_model_for_provider(self, provider: str) -> str:
        """Get default model ID for a provider."""
        defaults = {
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-5-sonnet-20241022",
            "google": "gemini-1.5-pro",
        }
        return defaults.get(provider, "gpt-4o-mini")

    def _select_by_performance(
        self,
        task_type: TaskType,
        prefer_speed: bool = False,
        prefer_quality: bool = False
    ) -> Optional[tuple[str, str]]:
        """
        Select model based on historical performance.

        Args:
            task_type: Task type
            prefer_speed: Prioritize low latency
            prefer_quality: Prioritize high success rate

        Returns:
            (model_id, provider) tuple or None
        """
        # Filter to available models only
        candidates = []
        for model_key, perf in self.performance_metrics.items():
            if perf.provider in self.available_providers and perf.total_calls >= 3:
                candidates.append((perf, model_key))

        if not candidates:
            return None

        # Sort by appropriate metric
        if prefer_speed:
            # Sort by latency (ascending)
            candidates.sort(key=lambda x: x[0].average_latency)
        elif prefer_quality:
            # Sort by success rate (descending)
            candidates.sort(key=lambda x: x[0].success_rate, reverse=True)
        else:
            # Sort by overall performance score (descending)
            candidates.sort(key=lambda x: x[0].performance_score, reverse=True)

        # Return best performer
        if candidates:
            best_perf, _ = candidates[0]
            return (best_perf.model_id, best_perf.provider)

        return None

    def record_call(
        self,
        model_id: str,
        provider: str,
        success: bool,
        latency: float
    ):
        """
        Record a model call for performance tracking.

        Args:
            model_id: Model identifier
            provider: Provider name
            success: Whether the call succeeded
            latency: Call latency in seconds
        """
        model_key = f"{provider}:{model_id}"

        if model_key not in self.performance_metrics:
            self.performance_metrics[model_key] = ModelPerformance(
                model_id=model_id,
                provider=provider
            )

        perf = self.performance_metrics[model_key]
        perf.total_calls += 1
        if success:
            perf.successful_calls += 1
        else:
            perf.failed_calls += 1

        perf.total_latency += latency
        perf.latencies.append(latency)

        # Keep only last 100 latencies to prevent unbounded growth
        if len(perf.latencies) > 100:
            perf.latencies = perf.latencies[-100:]

        perf.last_used = datetime.utcnow()

        logger.debug(
            f"Recorded call for {model_key}: success={success}, "
            f"latency={latency:.2f}s, performance_score={perf.performance_score:.2f}"
        )

    def get_performance_report(self) -> Dict[str, Any]:
        """
        Generate a performance report for all tracked models.

        Returns:
            Dict with performance stats for each model
        """
        report = {}

        for model_key, perf in self.performance_metrics.items():
            report[model_key] = {
                "model_id": perf.model_id,
                "provider": perf.provider,
                "total_calls": perf.total_calls,
                "success_rate": perf.success_rate,
                "average_latency": perf.average_latency,
                "performance_score": perf.performance_score,
                "last_used": perf.last_used.isoformat() if perf.last_used else None,
            }

        return report

    def reset_metrics(self):
        """Reset all performance metrics (useful for testing)."""
        self.performance_metrics.clear()
        logger.info("Model router metrics reset")

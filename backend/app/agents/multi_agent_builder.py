"""
Multi-Agent Build Chains

Orchestrates multiple agents working together in sequential or parallel chains.
Enables complex multi-stage builds with research, coding, testing, and more.
"""

import logging
import json
import uuid
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ChainStrategy(str, Enum):
    """Strategy for executing multi-agent chains."""
    SEQUENTIAL = "sequential"  # Run agents one after another
    PARALLEL = "parallel"  # Run agents in parallel
    MANAGER_LED = "manager-led"  # Manager coordinates sub-agents


class ChainStatus(str, Enum):
    """Status of a multi-agent chain build."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class MultiAgentBuilder:
    """
    Multi-Agent Build Chain Orchestrator.

    Coordinates multiple agents to work on a single task collaboratively.
    Supports sequential, parallel, and manager-led execution strategies.
    """

    def __init__(
        self,
        agent_factory,
        memory_db=None,
        config=None
    ):
        """
        Initialize the Multi-Agent Builder.

        Args:
            agent_factory: Factory to create/retrieve agents
            memory_db: Memory DB for tracking chain builds
            config: Application config
        """
        self.agent_factory = agent_factory
        self.memory_db = memory_db
        self.config = config

        logger.info("Multi-Agent Builder initialized")

    async def execute_chain(
        self,
        chain_id: str,
        chain_name: str,
        agent_ids: List[int],
        goal: str,
        strategy: ChainStrategy = ChainStrategy.SEQUENTIAL,
        log_callback=None
    ) -> Dict[str, Any]:
        """
        Execute a multi-agent build chain.

        Args:
            chain_id: Unique chain identifier
            chain_name: Name for this chain
            agent_ids: List of agent IDs to run
            goal: Overall goal for the chain
            strategy: Execution strategy
            log_callback: Optional logging callback

        Returns:
            Chain execution result with outputs from all agents
        """
        if log_callback:
            await log_callback(f"\n🔗 Starting multi-agent chain: {chain_name}")
            await log_callback(f"   Strategy: {strategy.value}")
            await log_callback(f"   Agents: {len(agent_ids)}")

        start_time = datetime.utcnow()

        try:
            # Execute based on strategy
            if strategy == ChainStrategy.SEQUENTIAL:
                result = await self._execute_sequential(
                    chain_id=chain_id,
                    agent_ids=agent_ids,
                    goal=goal,
                    log_callback=log_callback
                )
            elif strategy == ChainStrategy.PARALLEL:
                result = await self._execute_parallel(
                    chain_id=chain_id,
                    agent_ids=agent_ids,
                    goal=goal,
                    log_callback=log_callback
                )
            elif strategy == ChainStrategy.MANAGER_LED:
                result = await self._execute_manager_led(
                    chain_id=chain_id,
                    agent_ids=agent_ids,
                    goal=goal,
                    log_callback=log_callback
                )
            else:
                raise ValueError(f"Unknown strategy: {strategy}")

            duration = (datetime.utcnow() - start_time).total_seconds()

            if log_callback:
                await log_callback(f"\n✨ Chain completed in {duration:.1f}s")

            # Save to memory DB if available
            if self.memory_db:
                await self._save_chain_to_memory(
                    chain_id=chain_id,
                    chain_name=chain_name,
                    goal=goal,
                    strategy=strategy.value,
                    agent_ids=agent_ids,
                    result=result,
                    duration_sec=duration
                )

            return {
                "chain_id": chain_id,
                "status": ChainStatus.COMPLETED.value,
                "strategy": strategy.value,
                "agent_count": len(agent_ids),
                "duration_sec": duration,
                **result
            }

        except Exception as e:
            logger.error(f"Chain {chain_id} failed: {e}")

            if log_callback:
                await log_callback(f"\n❌ Chain failed: {e}")

            # Save failure to memory DB
            if self.memory_db:
                duration = (datetime.utcnow() - start_time).total_seconds()
                await self._save_chain_to_memory(
                    chain_id=chain_id,
                    chain_name=chain_name,
                    goal=goal,
                    strategy=strategy.value,
                    agent_ids=agent_ids,
                    result={"error": str(e)},
                    duration_sec=duration,
                    status="failed"
                )

            return {
                "chain_id": chain_id,
                "status": ChainStatus.FAILED.value,
                "error": str(e),
                "agent_count": len(agent_ids)
            }

    async def _execute_sequential(
        self,
        chain_id: str,
        agent_ids: List[int],
        goal: str,
        log_callback=None
    ) -> Dict[str, Any]:
        """
        Execute agents sequentially, passing outputs forward.

        Each agent receives the goal plus outputs from previous agents.
        """
        agent_outputs = {}
        context = {"goal": goal, "previous_outputs": []}

        for idx, agent_id in enumerate(agent_ids, 1):
            if log_callback:
                await log_callback(f"\n🤖 Running agent {idx}/{len(agent_ids)} (ID: {agent_id})")

            try:
                # Build prompt with context
                agent_prompt = self._build_sequential_prompt(
                    goal=goal,
                    agent_index=idx,
                    total_agents=len(agent_ids),
                    previous_outputs=context["previous_outputs"]
                )

                # Execute agent
                output = await self._run_agent(
                    agent_id=agent_id,
                    prompt=agent_prompt,
                    log_callback=log_callback
                )

                agent_outputs[f"agent_{agent_id}"] = output
                context["previous_outputs"].append({
                    "agent_id": agent_id,
                    "output": output
                })

                if log_callback:
                    await log_callback(f"   ✅ Agent {idx} completed")

            except Exception as e:
                logger.error(f"Agent {agent_id} failed in chain: {e}")
                if log_callback:
                    await log_callback(f"   ❌ Agent {idx} failed: {e}")

                agent_outputs[f"agent_{agent_id}"] = {
                    "error": str(e),
                    "success": False
                }

        return {
            "agent_outputs": agent_outputs,
            "final_context": context,
            "success": all(
                out.get("success", True) for out in agent_outputs.values()
            )
        }

    async def _execute_parallel(
        self,
        chain_id: str,
        agent_ids: List[int],
        goal: str,
        log_callback=None
    ) -> Dict[str, Any]:
        """
        Execute all agents in parallel.

        All agents receive the same goal and run simultaneously.
        """
        if log_callback:
            await log_callback(f"\n🚀 Running {len(agent_ids)} agents in parallel...")

        # Create tasks for all agents
        tasks = []
        for agent_id in agent_ids:
            task = self._run_agent(
                agent_id=agent_id,
                prompt=goal,
                log_callback=log_callback
            )
            tasks.append(task)

        # Run all in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect outputs
        agent_outputs = {}
        for agent_id, result in zip(agent_ids, results):
            if isinstance(result, Exception):
                logger.error(f"Agent {agent_id} failed: {result}")
                agent_outputs[f"agent_{agent_id}"] = {
                    "error": str(result),
                    "success": False
                }
            else:
                agent_outputs[f"agent_{agent_id}"] = result

        if log_callback:
            success_count = sum(
                1 for out in agent_outputs.values()
                if out.get("success", True)
            )
            await log_callback(
                f"   ✅ {success_count}/{len(agent_ids)} agents completed successfully"
            )

        return {
            "agent_outputs": agent_outputs,
            "success": all(
                out.get("success", True) for out in agent_outputs.values()
            )
        }

    async def _execute_manager_led(
        self,
        chain_id: str,
        agent_ids: List[int],
        goal: str,
        log_callback=None
    ) -> Dict[str, Any]:
        """
        Execute with a manager agent coordinating sub-agents.

        The manager decides which agents to run and in what order.
        """
        if log_callback:
            await log_callback(
                f"\n👔 Manager-led execution with {len(agent_ids)} available agents"
            )

        # For now, use sequential execution as the manager strategy
        # In a full implementation, this would use a manager agent to dynamically
        # decide which agents to run and in what order
        return await self._execute_sequential(
            chain_id=chain_id,
            agent_ids=agent_ids,
            goal=goal,
            log_callback=log_callback
        )

    async def _run_agent(
        self,
        agent_id: int,
        prompt: str,
        log_callback=None
    ) -> Dict[str, Any]:
        """
        Run a single agent with the given prompt.

        Args:
            agent_id: Agent ID
            prompt: Prompt to send to agent
            log_callback: Optional logging callback

        Returns:
            Agent output
        """
        # This is a placeholder - in production this would:
        # 1. Load the agent from the database
        # 2. Execute it with the prompt
        # 3. Return the results

        # For now, return a mock successful result
        await asyncio.sleep(0.5)  # Simulate work

        return {
            "agent_id": agent_id,
            "prompt": prompt,
            "output": f"Output from agent {agent_id}",
            "success": True,
            "timestamp": datetime.utcnow().isoformat()
        }

    def _build_sequential_prompt(
        self,
        goal: str,
        agent_index: int,
        total_agents: int,
        previous_outputs: List[Dict[str, Any]]
    ) -> str:
        """
        Build a prompt for sequential execution.

        Includes the goal and outputs from previous agents.
        """
        prompt = f"# Multi-Agent Chain Task (Agent {agent_index}/{total_agents})\n\n"
        prompt += f"## Overall Goal\n{goal}\n\n"

        if previous_outputs:
            prompt += "## Previous Agent Outputs\n"
            for idx, prev in enumerate(previous_outputs, 1):
                prompt += f"\n### Agent {idx} Output\n"
                if isinstance(prev.get("output"), dict):
                    prompt += json.dumps(prev["output"], indent=2)
                else:
                    prompt += str(prev.get("output", "No output"))
                prompt += "\n"

        prompt += "\n## Your Task\n"
        prompt += "Build upon the previous work and contribute to the overall goal.\n"

        return prompt

    async def _save_chain_to_memory(
        self,
        chain_id: str,
        chain_name: str,
        goal: str,
        strategy: str,
        agent_ids: List[int],
        result: Dict[str, Any],
        duration_sec: float,
        status: str = "completed"
    ):
        """Save chain execution to memory DB."""
        if not self.memory_db:
            return

        try:
            # Extract quality score if available
            quality = 0.0
            if result.get("success"):
                quality = 1.0
            elif result.get("agent_outputs"):
                success_count = sum(
                    1 for out in result["agent_outputs"].values()
                    if out.get("success", True)
                )
                quality = success_count / len(result["agent_outputs"])

            # Save as a build with chain metadata
            await self.memory_db.save_build(
                run_id=chain_id,
                prompt=f"[CHAIN: {chain_name}] {goal}",
                quality=quality,
                model_map={"strategy": strategy, "agents": agent_ids},
                duration_sec=duration_sec,
                status=status,
                error=result.get("error"),
                requirements={
                    "chain_name": chain_name,
                    "agent_ids": agent_ids,
                    "strategy": strategy
                }
            )

        except Exception as e:
            logger.error(f"Failed to save chain to memory DB: {e}")


async def create_multi_agent_builder(
    agent_factory=None,
    memory_db=None,
    config=None
) -> MultiAgentBuilder:
    """
    Factory function to create a MultiAgentBuilder instance.

    Args:
        agent_factory: Agent factory instance
        memory_db: Memory DB instance
        config: Application config

    Returns:
        MultiAgentBuilder instance
    """
    return MultiAgentBuilder(
        agent_factory=agent_factory,
        memory_db=memory_db,
        config=config
    )

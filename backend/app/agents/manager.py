"""
Agent Manager for coordinating multi-agent runtime with sub-agents.
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class SubAgentType(str, Enum):
    """Types of sub-agents available for orchestration."""
    PLANNER = "planner"
    IMPLEMENTER = "implementer"
    OPTIMIZER = "optimizer"
    TESTER = "tester"
    DEPLOYER = "deployer"
    RESEARCHER = "researcher"
    MONITOR = "monitor"


@dataclass
class SubAgentDefinition:
    """Definition of a sub-agent with its role and capabilities."""
    type: SubAgentType
    name: str
    description: str
    prompt_template: str
    tools: List[str]
    parallel_capable: bool = False


class SubAgentRegistry:
    """
    Registry of sub-agents with their definitions and roles.
    Each agent type can define which sub-agents it uses.
    """

    # Define all available sub-agents
    DEFINITIONS = {
        SubAgentType.PLANNER: SubAgentDefinition(
            type=SubAgentType.PLANNER,
            name="Task Planner",
            description="Analyzes requirements and creates detailed execution plans",
            prompt_template="""You are a Task Planner agent. Your role is to:
1. Analyze the user's request: {user_prompt}
2. Break it down into actionable steps
3. Identify required resources and tools
4. Create a detailed execution plan
5. Estimate complexity and potential challenges

Context from memory:
{recalled_memory}

Provide a structured plan with clear steps.""",
            tools=["vector_memory"],
            parallel_capable=False
        ),
        SubAgentType.RESEARCHER: SubAgentDefinition(
            type=SubAgentType.RESEARCHER,
            name="Research Agent",
            description="Gathers information from web, APIs, and documentation",
            prompt_template="""You are a Research Agent. Your role is to:
1. Research the topic: {user_prompt}
2. Gather relevant information from available sources
3. Synthesize findings
4. Provide context for implementation

Context from memory:
{recalled_memory}

Use available tools to research thoroughly.""",
            tools=["browser", "api_caller", "vector_memory"],
            parallel_capable=True
        ),
        SubAgentType.IMPLEMENTER: SubAgentDefinition(
            type=SubAgentType.IMPLEMENTER,
            name="Implementation Agent",
            description="Executes the plan and implements solutions",
            prompt_template="""You are an Implementation Agent. Your role is to:
1. Execute the plan: {plan_steps}
2. Implement the solution for: {user_prompt}
3. Use available tools effectively
4. Document your actions
5. Handle errors gracefully

Context from memory:
{recalled_memory}

Implement the solution step by step.""",
            tools=["github", "code_executor", "api_caller", "vector_memory"],
            parallel_capable=False
        ),
        SubAgentType.OPTIMIZER: SubAgentDefinition(
            type=SubAgentType.OPTIMIZER,
            name="Optimization Agent",
            description="Reviews and optimizes the implementation",
            prompt_template="""You are an Optimization Agent. Your role is to:
1. Review the implementation: {implementation_result}
2. Identify optimization opportunities
3. Suggest improvements for performance, readability, and maintainability
4. Apply optimizations where beneficial

Context from memory:
{recalled_memory}

Provide optimization recommendations and apply them.""",
            tools=["code_executor", "vector_memory"],
            parallel_capable=False
        ),
        SubAgentType.TESTER: SubAgentDefinition(
            type=SubAgentType.TESTER,
            name="Testing Agent",
            description="Tests the implementation and validates results",
            prompt_template="""You are a Testing Agent. Your role is to:
1. Test the implementation: {implementation_result}
2. Verify functionality
3. Check edge cases
4. Report bugs and issues
5. Validate against requirements: {user_prompt}

Context from memory:
{recalled_memory}

Run comprehensive tests and report results.""",
            tools=["code_executor", "browser", "vector_memory"],
            parallel_capable=True
        ),
        SubAgentType.DEPLOYER: SubAgentDefinition(
            type=SubAgentType.DEPLOYER,
            name="Deployment Agent",
            description="Handles deployment and publishing",
            prompt_template="""You are a Deployment Agent. Your role is to:
1. Deploy the solution: {implementation_result}
2. Configure deployment settings
3. Verify deployment success
4. Document deployment process

Context from memory:
{recalled_memory}

Deploy the solution safely.""",
            tools=["github", "api_caller", "vector_memory"],
            parallel_capable=False
        ),
        SubAgentType.MONITOR: SubAgentDefinition(
            type=SubAgentType.MONITOR,
            name="Monitoring Agent",
            description="Monitors execution and collects metrics",
            prompt_template="""You are a Monitoring Agent. Your role is to:
1. Monitor the process
2. Collect execution metrics
3. Report on progress
4. Alert on issues

Context from memory:
{recalled_memory}

Provide monitoring insights.""",
            tools=["vector_memory"],
            parallel_capable=True
        ),
    }

    @classmethod
    def get_definition(cls, sub_agent_type: SubAgentType) -> SubAgentDefinition:
        """Get the definition for a sub-agent type."""
        return cls.DEFINITIONS.get(sub_agent_type)

    @classmethod
    def get_all_definitions(cls) -> Dict[SubAgentType, SubAgentDefinition]:
        """Get all sub-agent definitions."""
        return cls.DEFINITIONS


class AgentManager:
    """
    Manages multi-agent runtime coordination.

    Responsibilities:
    - Parse incoming prompts
    - Determine which sub-agents to activate
    - Coordinate sub-agent execution (sequential or parallel)
    - Integrate memory recall
    - Collect and return results
    """

    def __init__(self, llm_router, tools: Dict[str, Any], vector_memory):
        """
        Initialize the Agent Manager.

        Args:
            llm_router: LLM router for parsing intents and generating responses
            tools: Dictionary of available tools
            vector_memory: VectorMemoryTool instance for memory operations
        """
        self.llm_router = llm_router
        self.tools = tools
        self.vector_memory = vector_memory
        self.registry = SubAgentRegistry()

    async def parse_intent(self, user_prompt: str, agent_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse user prompt to determine intent and required sub-agents.

        Args:
            user_prompt: The user's input prompt
            agent_context: Context about the current agent

        Returns:
            Dict with parsed intent, required sub-agents, and execution strategy
        """
        try:
            # Create intent parsing prompt
            intent_prompt = f"""Analyze this user request and determine the best execution strategy.

User Request: {user_prompt}

Agent Context:
- Agent Name: {agent_context.get('name', 'Unknown')}
- Agent Description: {agent_context.get('description', 'N/A')}
- Available Tools: {', '.join(agent_context.get('tools', []))}

Available Sub-Agents:
{self._format_subagent_list()}

Based on the request, determine:
1. Primary intent (e.g., implement, research, test, deploy, analyze)
2. Which sub-agents should be activated (in order)
3. Whether any sub-agents can run in parallel
4. Estimated complexity (low/medium/high)

Respond in JSON format:
{{
    "intent": "brief description of intent",
    "complexity": "low|medium|high",
    "sub_agents": [
        {{"type": "planner", "parallel": false}},
        {{"type": "implementer", "parallel": false}}
    ],
    "execution_strategy": "sequential or parallel description"
}}"""

            # Call LLM to parse intent
            response = await self.llm_router.generate(
                prompt=intent_prompt,
                model="gpt-4",
                temperature=0.3
            )

            # Parse response (simplified - in production would use structured output)
            import json
            # Extract JSON from response
            content = response.get("content", "")

            # Try to find JSON in the response
            start_idx = content.find("{")
            end_idx = content.rfind("}") + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = content[start_idx:end_idx]
                parsed_intent = json.loads(json_str)
            else:
                # Fallback to default strategy
                logger.warning("Could not parse intent JSON, using default strategy")
                parsed_intent = self._default_intent_strategy(user_prompt)

            logger.info(f"Parsed intent: {parsed_intent.get('intent', 'unknown')}")
            return parsed_intent

        except Exception as e:
            logger.error(f"Error parsing intent: {e}")
            # Return default strategy on error
            return self._default_intent_strategy(user_prompt)

    def _format_subagent_list(self) -> str:
        """Format sub-agent definitions for display."""
        lines = []
        for agent_type, definition in self.registry.get_all_definitions().items():
            lines.append(f"- {definition.name} ({agent_type.value}): {definition.description}")
        return "\n".join(lines)

    def _default_intent_strategy(self, user_prompt: str) -> Dict[str, Any]:
        """
        Provide a default intent strategy when parsing fails.
        """
        # Simple heuristic-based strategy
        prompt_lower = user_prompt.lower()

        if any(word in prompt_lower for word in ["research", "find", "search", "learn"]):
            sub_agents = [
                {"type": "researcher", "parallel": False},
                {"type": "planner", "parallel": False}
            ]
        elif any(word in prompt_lower for word in ["test", "verify", "check"]):
            sub_agents = [
                {"type": "tester", "parallel": False}
            ]
        elif any(word in prompt_lower for word in ["deploy", "publish", "release"]):
            sub_agents = [
                {"type": "planner", "parallel": False},
                {"type": "deployer", "parallel": False}
            ]
        else:
            # Default: plan -> implement -> test
            sub_agents = [
                {"type": "planner", "parallel": False},
                {"type": "implementer", "parallel": False},
                {"type": "tester", "parallel": False}
            ]

        return {
            "intent": "Execute user request",
            "complexity": "medium",
            "sub_agents": sub_agents,
            "execution_strategy": "Sequential execution with planning, implementation, and testing"
        }

    async def recall_context(self, user_prompt: str, agent_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Recall relevant context from memory before execution.

        Args:
            user_prompt: The user's prompt to find relevant context
            agent_id: Optional agent ID to filter memories

        Returns:
            List of recalled memory items
        """
        try:
            recalled = self.vector_memory.recall(
                context_query=user_prompt,
                n_results=5,
                agent_id=agent_id
            )

            logger.info(f"Recalled {len(recalled)} context items from memory")
            return recalled
        except Exception as e:
            logger.error(f"Error recalling context: {e}")
            return []

    async def execute_sub_agent(
        self,
        sub_agent_type: str,
        context: Dict[str, Any],
        recalled_memory: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Execute a single sub-agent.

        Args:
            sub_agent_type: Type of sub-agent to execute
            context: Execution context (user prompt, previous results, etc.)
            recalled_memory: Recalled context from memory

        Returns:
            Sub-agent execution result
        """
        try:
            # Get sub-agent definition
            agent_type_enum = SubAgentType(sub_agent_type)
            definition = self.registry.get_definition(agent_type_enum)

            if not definition:
                return {"error": f"Unknown sub-agent type: {sub_agent_type}"}

            logger.info(f"Executing sub-agent: {definition.name}")

            # Format recalled memory for prompt
            memory_context = self._format_recalled_memory(recalled_memory)

            # Build sub-agent prompt
            prompt = definition.prompt_template.format(
                user_prompt=context.get("user_prompt", ""),
                recalled_memory=memory_context,
                plan_steps=context.get("plan_steps", ""),
                implementation_result=context.get("implementation_result", "")
            )

            # Execute with LLM
            response = await self.llm_router.generate(
                prompt=prompt,
                model=context.get("model", "gpt-4"),
                temperature=0.7
            )

            result = {
                "sub_agent": definition.name,
                "type": sub_agent_type,
                "output": response.get("content", ""),
                "tokens_used": response.get("usage", {}),
                "success": True
            }

            logger.info(f"Sub-agent {definition.name} completed successfully")
            return result

        except Exception as e:
            logger.error(f"Error executing sub-agent {sub_agent_type}: {e}")
            return {
                "sub_agent": sub_agent_type,
                "type": sub_agent_type,
                "error": str(e),
                "success": False
            }

    def _format_recalled_memory(self, recalled: List[Dict[str, Any]]) -> str:
        """Format recalled memories for injection into prompts."""
        if not recalled:
            return "No relevant context found in memory."

        lines = ["Relevant context from past executions:"]
        for i, item in enumerate(recalled, 1):
            score = item.get("relevance_score", 0)
            text = item.get("text", "")
            lines.append(f"\n{i}. [Relevance: {score:.2f}] {text[:200]}...")

        return "\n".join(lines)

    async def execute_workflow(
        self,
        user_prompt: str,
        agent_id: Optional[int] = None,
        agent_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute complete multi-agent workflow.

        Args:
            user_prompt: The user's prompt
            agent_id: Optional agent ID for memory filtering
            agent_context: Optional agent context information

        Returns:
            Complete workflow execution results
        """
        try:
            logger.info(f"Starting multi-agent workflow for prompt: {user_prompt[:100]}...")

            # Initialize results structure
            workflow_results = {
                "status": "running",
                "user_prompt": user_prompt,
                "steps": [],
                "logs": [],
                "output": "",
                "recalled_memory": [],
                "sub_agent_results": [],
                "errors": []
            }

            # Step 1: Recall relevant context
            workflow_results["logs"].append("Recalling relevant context from memory...")
            recalled_memory = await self.recall_context(user_prompt, agent_id)
            workflow_results["recalled_memory"] = recalled_memory
            workflow_results["logs"].append(f"Recalled {len(recalled_memory)} relevant context items")

            # Step 2: Parse intent and determine sub-agents
            workflow_results["logs"].append("Parsing intent and determining execution strategy...")
            intent = await self.parse_intent(user_prompt, agent_context or {})
            workflow_results["intent"] = intent
            workflow_results["logs"].append(f"Intent: {intent.get('intent', 'unknown')}")
            workflow_results["logs"].append(f"Strategy: {intent.get('execution_strategy', 'default')}")

            # Step 3: Execute sub-agents
            sub_agents = intent.get("sub_agents", [])
            execution_context = {
                "user_prompt": user_prompt,
                "agent_id": agent_id,
                "model": "gpt-4"
            }

            for i, sub_agent_config in enumerate(sub_agents):
                sub_agent_type = sub_agent_config.get("type")
                workflow_results["logs"].append(f"Executing sub-agent {i+1}/{len(sub_agents)}: {sub_agent_type}")

                # Execute sub-agent
                result = await self.execute_sub_agent(
                    sub_agent_type=sub_agent_type,
                    context=execution_context,
                    recalled_memory=recalled_memory
                )

                workflow_results["sub_agent_results"].append(result)
                workflow_results["steps"].append({
                    "step": i + 1,
                    "sub_agent": sub_agent_type,
                    "status": "completed" if result.get("success") else "failed"
                })

                # Update context with result for next sub-agent
                if result.get("success"):
                    if sub_agent_type == "planner":
                        execution_context["plan_steps"] = result.get("output", "")
                    elif sub_agent_type in ["implementer", "researcher"]:
                        execution_context["implementation_result"] = result.get("output", "")

                    workflow_results["logs"].append(f"✓ {sub_agent_type} completed successfully")
                else:
                    workflow_results["errors"].append(f"Sub-agent {sub_agent_type} failed: {result.get('error')}")
                    workflow_results["logs"].append(f"✗ {sub_agent_type} failed")

            # Step 4: Compile final output
            workflow_results["logs"].append("Compiling final results...")
            final_outputs = []
            for result in workflow_results["sub_agent_results"]:
                if result.get("success"):
                    final_outputs.append(f"\n## {result['sub_agent']}:\n{result['output']}")

            workflow_results["output"] = "\n".join(final_outputs)
            workflow_results["status"] = "completed" if not workflow_results["errors"] else "completed_with_errors"

            # Step 5: Store results in memory for future recall
            workflow_results["logs"].append("Storing results in memory for future recall...")
            await self._store_workflow_memory(user_prompt, workflow_results, agent_id)

            logger.info(f"Workflow completed with status: {workflow_results['status']}")
            return workflow_results

        except Exception as e:
            logger.error(f"Error in workflow execution: {e}")
            return {
                "status": "failed",
                "user_prompt": user_prompt,
                "steps": [],
                "logs": [f"Error: {str(e)}"],
                "output": "",
                "recalled_memory": [],
                "sub_agent_results": [],
                "errors": [str(e)]
            }

    async def _store_workflow_memory(
        self,
        user_prompt: str,
        results: Dict[str, Any],
        agent_id: Optional[int]
    ):
        """Store workflow results in memory for future recall."""
        try:
            # Create memory documents
            documents = [
                f"User Request: {user_prompt}\n\nIntent: {results.get('intent', {}).get('intent', 'N/A')}\n\nOutcome: {results['status']}\n\nSummary: {results['output'][:500]}..."
            ]

            # Add individual sub-agent outputs
            for result in results.get("sub_agent_results", []):
                if result.get("success"):
                    documents.append(
                        f"Sub-Agent {result['sub_agent']} output:\n{result['output'][:300]}..."
                    )

            # Store in memory
            metadatas = [
                {"type": "workflow", "status": results["status"], "prompt": user_prompt[:100]}
                for _ in documents
            ]

            self.vector_memory.remember(
                documents=documents,
                metadatas=metadatas,
                agent_id=agent_id
            )

            logger.info(f"Stored {len(documents)} workflow memories")

        except Exception as e:
            logger.error(f"Error storing workflow memory: {e}")

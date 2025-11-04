"""
Agent Factory: Converts AgentSpec JSON into executable LangGraph workflows.
"""

import logging
from typing import TypedDict, Annotated, Any, Dict
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage
import operator

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    """State for agent execution."""

    messages: Annotated[list, operator.add]
    inputs: dict
    outputs: dict
    artifacts: list
    step_count: int
    errors: list
    token_usage: list  # Track token usage per step
    total_cost: float  # Accumulated cost in USD


def create_llm_node(node_spec: dict, llm_router):
    """Create an LLM node from spec."""

    async def llm_node(state: AgentState) -> AgentState:
        logger.info(f"Executing LLM node: {node_spec['name']}")

        try:
            # Get the appropriate LLM
            model_name = node_spec.get("model")
            llm = await llm_router.get_llm(model_name)

            # Build prompt from state
            messages = state.get("messages", [])
            prompt = f"{node_spec.get('description', '')}\n\nContext: {state.get('inputs', {})}"

            # Add to messages
            messages.append(HumanMessage(content=prompt))

            # Invoke LLM
            response = await llm.ainvoke(messages)

            # Update state
            messages.append(AIMessage(content=response.content))

            # Track token usage and cost
            token_usage = state.get("token_usage", [])
            total_cost = state.get("total_cost", 0.0)

            # Extract usage info from response (if available)
            usage_metadata = {}
            if hasattr(response, "response_metadata"):
                usage_metadata = response.response_metadata.get("usage", {})
            elif hasattr(response, "usage_metadata"):
                usage_metadata = response.usage_metadata or {}

            if usage_metadata:
                # Calculate cost for this step
                from app.services.pricing import calculate_actual_cost

                # Get the actual model name from LLM
                actual_model = llm.model_name if hasattr(llm, "model_name") else (llm.model if hasattr(llm, "model") else "unknown")

                step_cost = calculate_actual_cost(usage_metadata, actual_model)
                total_cost += step_cost

                token_usage.append({
                    "node": node_spec["name"],
                    "model": actual_model,
                    "usage": usage_metadata,
                    "cost": step_cost,
                })

                logger.info(f"Node {node_spec['name']} used {usage_metadata.get('total_tokens', 0)} tokens, cost: ${step_cost:.6f}")

            return {
                "messages": messages,
                "step_count": state.get("step_count", 0) + 1,
                "token_usage": token_usage,
                "total_cost": total_cost,
            }

        except Exception as e:
            logger.error(f"LLM node {node_spec['name']} failed: {e}")
            errors = state.get("errors", [])
            errors.append({"node": node_spec["name"], "error": str(e)})
            return {"errors": errors}

    return llm_node


def create_tool_node(node_spec: dict, tools: dict):
    """Create a tool node from spec."""

    async def tool_node(state: AgentState) -> AgentState:
        logger.info(f"Executing tool node: {node_spec['name']}")

        try:
            tool_name = node_spec.get("tool")
            tool = tools.get(tool_name)

            if not tool:
                raise ValueError(f"Tool '{tool_name}' not found")

            # Extract inputs from state
            inputs = state.get("inputs", {})

            # Execute tool
            result = await tool.execute(inputs)

            # Update outputs
            outputs = state.get("outputs", {})
            outputs[node_spec["name"]] = result

            return {
                "outputs": outputs,
                "step_count": state.get("step_count", 0) + 1,
            }

        except Exception as e:
            logger.error(f"Tool node {node_spec['name']} failed: {e}")
            errors = state.get("errors", [])
            errors.append({"node": node_spec["name"], "error": str(e)})
            return {"errors": errors}

    return tool_node


def create_human_node(node_spec: dict, approval_callback):
    """Create a human approval node from spec."""

    async def human_node(state: AgentState) -> AgentState:
        logger.info(f"Executing human approval node: {node_spec['name']}")

        try:
            # Request approval via callback
            approved = await approval_callback(
                step_id=node_spec["name"],
                action=node_spec.get("description", ""),
                details=state.get("outputs", {}),
            )

            if not approved:
                raise Exception("User rejected approval")

            return {"step_count": state.get("step_count", 0) + 1}

        except Exception as e:
            logger.error(f"Human node {node_spec['name']} failed: {e}")
            errors = state.get("errors", [])
            errors.append({"node": node_spec["name"], "error": str(e)})
            return {"errors": errors}

    return human_node


def create_agent_from_spec(
    spec: dict, llm_router, tools: dict, approval_callback=None
) -> StateGraph:
    """
    Create a LangGraph agent from an AgentSpec.

    Args:
        spec: AgentSpec dict with nodes, edges, etc.
        llm_router: LLM router service
        tools: Dict of available tools {tool_name: tool_instance}
        approval_callback: Async function for human approvals

    Returns:
        Compiled StateGraph
    """
    logger.info(f"Building agent: {spec.get('name', 'unnamed')}")

    # Initialize graph
    workflow = StateGraph(AgentState)

    # Create nodes
    for node_spec in spec.get("nodes", []):
        node_name = node_spec["name"]
        node_type = node_spec["type"]

        if node_type == "llm":
            node_fn = create_llm_node(node_spec, llm_router)
        elif node_type == "tool":
            node_fn = create_tool_node(node_spec, tools)
        elif node_type == "human":
            if not approval_callback:
                logger.warning(f"Human node {node_name} defined but no approval_callback provided")
                continue
            node_fn = create_human_node(node_spec, approval_callback)
        else:
            logger.warning(f"Unknown node type '{node_type}' for node '{node_name}'")
            continue

        workflow.add_node(node_name, node_fn)

    # Add edges
    entry_point = None
    for edge_spec in spec.get("edges", []):
        from_node = edge_spec["from"]
        to_node = edge_spec["to"]
        condition = edge_spec.get("condition")

        # Track entry point (node with no incoming edges)
        if entry_point is None:
            entry_point = from_node

        if to_node == "END":
            workflow.add_edge(from_node, END)
        elif condition:
            # TODO: Support conditional edges
            logger.warning(f"Conditional edges not yet supported: {from_node} -> {to_node}")
            workflow.add_edge(from_node, to_node)
        else:
            workflow.add_edge(from_node, to_node)

    # Set entry point
    if entry_point:
        workflow.set_entry_point(entry_point)
    else:
        logger.warning("No entry point found for agent graph")

    # Compile and return
    compiled = workflow.compile()
    logger.info(f"Agent compiled successfully: {spec.get('name', 'unnamed')}")
    return compiled

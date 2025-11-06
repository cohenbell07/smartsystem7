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


def create_final_output_node():
    """Create a terminal FinalOutput node that aggregates results."""

    async def final_output_node(state: AgentState) -> AgentState:
        logger.info("Executing FinalOutput terminal node")

        # Aggregate outputs and artifacts into final result
        result = {
            "result": state.get("outputs", {}),
            "artifacts": state.get("artifacts", []),
            "step_count": state.get("step_count", 0),
            "errors": state.get("errors", []),
        }

        return {
            "outputs": {"final_output": result},
            "step_count": state.get("step_count", 0) + 1,
        }

    return final_output_node


def ensure_terminal(workflow: StateGraph, spec: dict) -> None:
    """
    Ensure the workflow has a proper terminal node.

    Adds a FinalOutput node if no terminal node exists and wires
    unreachable terminal candidates to it.

    Args:
        workflow: The StateGraph being built
        spec: The agent spec dict
    """
    logger.info("Ensuring terminal node for workflow")

    # Collect all nodes and edges
    nodes = {node["name"] for node in spec.get("nodes", [])}
    edges = spec.get("edges", [])

    # Find nodes with outgoing edges
    nodes_with_outgoing = {edge["from"] for edge in edges}

    # Find terminal candidates (nodes with no outgoing edges or edges to END)
    terminal_candidates = []
    for node_name in nodes:
        if node_name not in nodes_with_outgoing:
            terminal_candidates.append(node_name)
        else:
            # Check if this node only has edges to END
            outgoing_edges = [e for e in edges if e["from"] == node_name]
            if all(e["to"] == "END" for e in outgoing_edges):
                terminal_candidates.append(node_name)

    # If no terminal candidates, use the last node in the spec
    if not terminal_candidates and nodes:
        last_node = list(nodes)[-1]
        terminal_candidates.append(last_node)
        logger.warning(f"No terminal node found, using last node: {last_node}")

    # Add FinalOutput node
    final_output_node = create_final_output_node()
    workflow.add_node("FinalOutput", final_output_node)

    # Wire terminal candidates to FinalOutput
    for candidate in terminal_candidates:
        if candidate in nodes:
            logger.info(f"Wiring terminal candidate '{candidate}' to FinalOutput")
            # Remove existing END edges from this node
            spec["edges"] = [e for e in spec["edges"] if not (e["from"] == candidate and e["to"] == "END")]
            # Add edge to FinalOutput
            workflow.add_edge(candidate, "FinalOutput")

    # Wire FinalOutput to END
    workflow.add_edge("FinalOutput", END)
    logger.info("Terminal node wiring complete")


def linearize_when_disconnected(workflow: StateGraph, spec: dict) -> None:
    """
    Linearize disconnected nodes by connecting them in declaration order.

    This is a fallback mechanism when the spec has unreferenced nodes
    or disconnected components.

    Args:
        workflow: The StateGraph being built
        spec: The agent spec dict
    """
    logger.info("Checking for disconnected nodes")

    nodes = [node["name"] for node in spec.get("nodes", [])]
    edges = spec.get("edges", [])

    # Build adjacency list
    incoming = {node: [] for node in nodes}
    outgoing = {node: [] for node in nodes}

    for edge in edges:
        from_node = edge["from"]
        to_node = edge["to"]
        if to_node != "END" and to_node in nodes:
            outgoing[from_node].append(to_node)
            incoming[to_node].append(from_node)

    # Find disconnected nodes (no incoming or outgoing edges)
    disconnected = [
        node for node in nodes
        if len(incoming[node]) == 0 and len(outgoing[node]) == 0
    ]

    if disconnected:
        logger.warning(f"Found {len(disconnected)} disconnected nodes: {disconnected}")
        logger.info("Linearizing disconnected nodes by declaration order")

        # Connect disconnected nodes in sequence
        for i, node in enumerate(disconnected):
            if i == 0:
                # Find entry point or first connected node
                connected_nodes = [n for n in nodes if n not in disconnected]
                if connected_nodes:
                    # Connect first disconnected to last connected node with no outgoing
                    candidates = [n for n in connected_nodes if len(outgoing[n]) == 0]
                    if candidates:
                        prev_node = candidates[0]
                        logger.info(f"Connecting {prev_node} -> {node}")
                        workflow.add_edge(prev_node, node)
                        spec["edges"].append({"from": prev_node, "to": node})
            else:
                # Connect to previous disconnected node
                prev_node = disconnected[i - 1]
                logger.info(f"Connecting {prev_node} -> {node}")
                workflow.add_edge(prev_node, node)
                spec["edges"].append({"from": prev_node, "to": node})
    else:
        logger.info("No disconnected nodes found")


def generate_tool_stub(tool_name: str) -> Any:
    """
    Generate a minimal, typed tool stub for missing tools.

    Args:
        tool_name: Name of the missing tool

    Returns:
        Tool stub instance
    """
    logger.info(f"Generating stub for missing tool: {tool_name}")

    class ToolStub:
        """Minimal tool stub with error handling."""

        def __init__(self, name: str):
            self.name = name

        async def execute(self, inputs: dict) -> dict:
            """Execute stub (returns error message)."""
            logger.warning(f"Executing stub for tool '{self.name}' - tool not implemented")
            return {
                "success": False,
                "error": f"Tool '{self.name}' is not implemented (using stub)",
                "message": f"The agent requested tool '{self.name}' but it is not available. "
                           f"Please implement this tool or remove it from the agent spec.",
                "inputs": inputs,
            }

    return ToolStub(tool_name)


def verify_and_generate_tools(spec: dict, tools: dict) -> dict:
    """
    Verify tools exist and generate stubs for missing ones.

    Args:
        spec: Agent spec
        tools: Available tools dict

    Returns:
        Updated tools dict with stubs for missing tools
    """
    logger.info("Verifying tools and generating stubs if needed")

    updated_tools = tools.copy()
    required_tools = set()

    # Collect all tools referenced in nodes
    for node_spec in spec.get("nodes", []):
        if node_spec.get("type") == "tool":
            tool_name = node_spec.get("tool")
            if tool_name:
                required_tools.add(tool_name)

    # Check for missing tools and generate stubs
    missing_tools = required_tools - set(tools.keys())

    if missing_tools:
        logger.warning(f"Missing tools detected: {missing_tools}")
        for tool_name in missing_tools:
            logger.info(f"Generating stub for tool: {tool_name}")
            updated_tools[tool_name] = generate_tool_stub(tool_name)

    return updated_tools


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

    # Verify tools and generate stubs for missing ones
    tools = verify_and_generate_tools(spec, tools)

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
            # Don't add END edges yet - will be handled by ensure_terminal
            continue
        elif condition:
            # TODO: Support conditional edges
            logger.warning(f"Conditional edges not yet supported: {from_node} -> {to_node}")
            workflow.add_edge(from_node, to_node)
        else:
            workflow.add_edge(from_node, to_node)

    # Linearize disconnected nodes if needed
    linearize_when_disconnected(workflow, spec)

    # Ensure terminal node exists and is properly wired
    ensure_terminal(workflow, spec)

    # Set entry point
    if entry_point:
        workflow.set_entry_point(entry_point)
    else:
        # If no entry point found, use first node
        nodes = spec.get("nodes", [])
        if nodes:
            entry_point = nodes[0]["name"]
            workflow.set_entry_point(entry_point)
            logger.warning(f"No entry point found, using first node: {entry_point}")
        else:
            raise ValueError("No nodes found in agent spec")

    # Compile and return
    try:
        compiled = workflow.compile()
        logger.info(f"Agent compiled successfully: {spec.get('name', 'unnamed')}")
        return compiled
    except Exception as e:
        logger.error(f"Failed to compile agent: {e}")
        logger.error(f"Spec: {spec}")
        raise ValueError(f"Agent compilation failed: {e}. This may indicate disconnected nodes or invalid graph structure.")

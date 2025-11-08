"""
Agent Factory: Converts AgentSpec JSON into executable LangGraph workflows.
"""

import logging
from datetime import datetime
from typing import TypedDict, Annotated, Any, Dict, List, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage
import operator
import json
import asyncio

logger = logging.getLogger(__name__)


def merge_dicts(existing: Optional[dict], new_value: Optional[dict]) -> dict:
    merged: Dict[str, Any] = {}
    if existing:
        merged.update(existing)
    if new_value:
        merged.update(new_value)
    return merged


class AgentState(TypedDict):
    """State for agent execution."""

    messages: Annotated[list, operator.add]
    inputs: dict
    outputs: Annotated[dict, merge_dicts]
    artifacts: Annotated[list, operator.add]
    step_count: Annotated[int, operator.add]
    errors: Annotated[list, operator.add]
    token_usage: Annotated[list, operator.add]  # Track token usage per step
    total_cost: float  # Accumulated cost in USD
    node_metrics: Annotated[list, operator.add]  # Rich metrics per node
    node_status: Annotated[dict, merge_dicts]  # Node execution status map


def create_llm_node(node_spec: dict, llm_router, log_callback=None):
    """Create an LLM node from spec."""

    async def llm_node(state: AgentState) -> AgentState:
        node_name = node_spec["name"]
        logger.info(f"Executing LLM node: {node_name}")

        started_at = datetime.utcnow()
        if log_callback:
            await log_callback(f"🧠 Starting LLM node '{node_name}'")

        try:
            # Get the appropriate LLM
            model_name = node_spec.get("model")
            llm = await llm_router.get_llm(model_name)

            # Build prompt from state and prior outputs
            prior_messages = list(state.get("messages", []))
            context_inputs = state.get("inputs", {})
            context_outputs = state.get("outputs", {})

            prompt = node_spec.get("prompt_template") or node_spec.get("description") or ""
            if not prompt:
                prompt = "Respond to the user instructions using the provided context."

            payload = {
                "inputs": context_inputs,
                "outputs": context_outputs,
            }

            formatted_prompt = prompt.format(
                **{
                    "inputs": json.dumps(context_inputs, ensure_ascii=False, default=str),
                    "context": json.dumps(payload, ensure_ascii=False, default=str),
                    "outputs": json.dumps(context_outputs, ensure_ascii=False, default=str),
                }
            ) if "{" in prompt else (
                f"{prompt}\n\nInputs:\n{json.dumps(context_inputs, ensure_ascii=False, default=str)}"
                f"\n\nPrior Outputs:\n{json.dumps(context_outputs, ensure_ascii=False, default=str)}"
            )

            messages = prior_messages + [HumanMessage(content=formatted_prompt)]

            # Invoke LLM
            response = await llm.ainvoke(messages)

            # Update conversation
            messages.append(AIMessage(content=response.content))

            # Track token usage and cost
            token_usage = list(state.get("token_usage", []))
            total_cost = state.get("total_cost", 0.0)

            usage_metadata: Dict[str, Any] = {}
            if hasattr(response, "response_metadata"):
                usage_metadata = response.response_metadata.get("usage", {}) or {}
            elif hasattr(response, "usage_metadata"):
                usage_metadata = response.usage_metadata or {}

            step_cost: Optional[float] = None
            total_tokens: Optional[int] = None
            actual_model = getattr(llm, "model_name", None) or getattr(llm, "model", None) or model_name or "unknown"

            if usage_metadata:
                from app.services.pricing import calculate_actual_cost

                step_cost = calculate_actual_cost(usage_metadata, actual_model)
                total_cost += step_cost
                total_tokens = usage_metadata.get("total_tokens")

                token_usage.append({
                    "node": node_name,
                    "model": actual_model,
                    "usage": usage_metadata,
                    "cost": step_cost,
                })

                logger.info(
                    f"Node {node_name} used {usage_metadata.get('total_tokens', 0)} tokens, cost: ${step_cost:.6f}"
                )

            node_output = {
                "type": "llm",
                "content": response.content,
                "model": model_name or getattr(llm, "model_name", None),
                "usage": usage_metadata or None,
            }

            completed_at = datetime.utcnow()
            node_metrics: List[dict] = list(state.get("node_metrics", []))
            metric = {
                "node": node_name,
                "type": "llm",
                "status": "completed",
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "duration": (completed_at - started_at).total_seconds(),
            }
            if step_cost is not None:
                metric["cost"] = step_cost
            if total_tokens is not None:
                metric["tokens"] = total_tokens
            if usage_metadata:
                metric["prompt_tokens"] = usage_metadata.get("prompt_tokens")
                metric["completion_tokens"] = usage_metadata.get("completion_tokens")
                metric["model"] = usage_metadata.get("model") or actual_model
            elif actual_model:
                metric["model"] = actual_model
            node_metrics.append(metric)

            if log_callback:
                await log_callback(f"✅ LLM node '{node_name}' completed")

            return {
                "messages": messages,
                "step_count": state.get("step_count", 0) + 1,
                "token_usage": token_usage,
                "total_cost": total_cost,
                "outputs": {node_name: node_output},
                "node_metrics": node_metrics,
                "node_status": {node_name: "completed"},
            }

        except Exception as e:
            logger.error(f"LLM node {node_name} failed: {e}", exc_info=True)
            errors = list(state.get("errors", []))
            errors.append({"node": node_name, "error": str(e)})

            node_metrics = list(state.get("node_metrics", []))
            failed_at = datetime.utcnow()
            node_metrics.append({
                "node": node_name,
                "type": "llm",
                "status": "failed",
                "started_at": started_at.isoformat(),
                "completed_at": failed_at.isoformat(),
                "duration": (failed_at - started_at).total_seconds(),
                "error": str(e),
            })

            if log_callback:
                await log_callback(f"❌ LLM node '{node_name}' failed: {e}")

            return {
                "errors": errors,
                "node_metrics": node_metrics,
                "node_status": {node_name: "failed"},
            }

    return llm_node


def create_tool_node(node_spec: dict, tools: dict, log_callback=None):
    """Create a tool node from spec."""

    async def tool_node(state: AgentState) -> AgentState:
        node_name = node_spec["name"]
        logger.info(f"Executing tool node: {node_name}")

        started_at = datetime.utcnow()
        try:
            tool_name = node_spec.get("tool")
            tool = tools.get(tool_name)

            if not tool:
                raise ValueError(f"Tool '{tool_name}' not found")

            # Extract inputs from state
            inputs = dict(state.get("inputs", {}))
            inputs.setdefault("context", state.get("outputs", {}))

            # Execute tool
            if log_callback:
                await log_callback(f"🛠️ Executing tool node '{node_name}' with tool '{tool_name}'")
            result = await tool.execute(inputs)

            if log_callback:
                await log_callback(f"✅ Tool node '{node_name}' completed")

            completed_at = datetime.utcnow()
            node_metrics = list(state.get("node_metrics", []))
            metric = {
                "node": node_name,
                "type": "tool",
                "tool": tool_name,
                "status": "completed",
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "duration": (completed_at - started_at).total_seconds(),
            }
            if isinstance(result, dict):
                if "duration" in result:
                    metric["duration"] = result["duration"]
                if "cost" in result:
                    metric["cost"] = result["cost"]
            node_metrics.append(metric)

            return {
                "outputs": {node_name: result},
                "step_count": state.get("step_count", 0) + 1,
                "node_metrics": node_metrics,
                "node_status": {node_name: "completed"},
            }

        except Exception as e:
            logger.error(f"Tool node {node_name} failed: {e}", exc_info=True)
            errors = list(state.get("errors", []))
            errors.append({"node": node_name, "error": str(e)})

            node_metrics = list(state.get("node_metrics", []))
            failed_at = datetime.utcnow()
            node_metrics.append({
                "node": node_name,
                "type": "tool",
                "tool": node_spec.get("tool"),
                "status": "failed",
                "started_at": started_at.isoformat(),
                "completed_at": failed_at.isoformat(),
                "duration": (failed_at - started_at).total_seconds(),
                "error": str(e),
            })

            if log_callback:
                await log_callback(f"❌ Tool node '{node_name}' failed: {e}")
            return {
                "errors": errors,
                "node_metrics": node_metrics,
                "node_status": {node_name: "failed"},
            }

    return tool_node


def create_human_node(node_spec: dict, approval_callback, log_callback=None):
    """Create a human approval node from spec."""

    async def human_node(state: AgentState) -> AgentState:
        node_name = node_spec["name"]
        logger.info(f"Executing human approval node: {node_name}")

        started_at = datetime.utcnow()

        try:
            # Request approval via callback
            approved = await approval_callback(
                step_id=node_name,
                action=node_spec.get("description", ""),
                details=state.get("outputs", {}),
            )

            if not approved:
                raise Exception("User rejected approval")

            if log_callback:
                await log_callback(f"✅ Human approval node '{node_name}' approved")

            completed_at = datetime.utcnow()
            node_metrics = list(state.get("node_metrics", []))
            node_metrics.append({
                "node": node_name,
                "type": "human",
                "status": "approved",
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "duration": (completed_at - started_at).total_seconds(),
            })

            node_status = dict(state.get("node_status", {}))
            node_status[node_name] = "completed"

            return {
                "step_count": state.get("step_count", 0) + 1,
                "node_metrics": node_metrics,
                "node_status": node_status,
            }

        except Exception as e:
            logger.error(f"Human node {node_name} failed: {e}", exc_info=True)
            errors = list(state.get("errors", []))
            errors.append({"node": node_name, "error": str(e)})

            failed_at = datetime.utcnow()
            node_metrics = list(state.get("node_metrics", []))
            node_metrics.append({
                "node": node_name,
                "type": "human",
                "status": "failed",
                "started_at": started_at.isoformat(),
                "completed_at": failed_at.isoformat(),
                "duration": (failed_at - started_at).total_seconds(),
                "error": str(e),
            })

            node_status = dict(state.get("node_status", {}))
            node_status[node_name] = "failed"

            if log_callback:
                await log_callback(f"❌ Human node '{node_name}' failed: {e}")
            return {
                "errors": errors,
                "node_metrics": node_metrics,
                "node_status": node_status,
            }

    return human_node


def _append_node_metric(state: AgentState, metric: dict) -> List[dict]:
    metrics = list(state.get("node_metrics", []))
    metrics.append(metric)
    return metrics


def create_validator_node(node_spec: dict, llm_router, log_callback=None):
    """Create a validator node that reviews previous outputs."""

    async def validator_node(state: AgentState) -> AgentState:
        node_name = node_spec["name"]
        logger.info(f"Executing validator node: {node_name}")

        started_at = datetime.utcnow()
        if log_callback:
            await log_callback(f"🔎 Starting validator node '{node_name}'")

        try:
            model_name = node_spec.get("model", "gpt-4o-mini")
            validator_llm = await llm_router.get_llm(model_name)

            outputs = state.get("outputs", {})
            target_nodes = node_spec.get("inputs_from") or node_spec.get("target_nodes") or ["ReasoningLLM"]
            candidate_fragments = []
            for target in target_nodes:
                candidate_fragments.append(f"{target}:\n{json.dumps(outputs.get(target), ensure_ascii=False, default=str)}")
            candidate_answer = outputs.get(target_nodes[0], {}).get("content") if target_nodes else None

            tool_feedback = []
            for tool_node in node_spec.get("tool_nodes", []):
                if tool_node in outputs:
                    tool_feedback.append(f"{tool_node} -> {json.dumps(outputs[tool_node], ensure_ascii=False, default=str)}")

            context_payload = "\n\n".join(candidate_fragments + tool_feedback) or "No prior outputs were captured."

            validator_prompt = node_spec.get("prompt_template") or (
                "You are a quality assurance assistant. Analyse the candidate answer and related "
                "evidence. Respond in JSON with fields: verdict ('pass'|'fail'), issues (array), "
                "improvements (array), confidence (0-1)."
            )
            formatted_prompt = validator_prompt.format(
                candidate_answer=candidate_answer or "",
                context=context_payload,
            )

            messages = [
                HumanMessage(content=formatted_prompt)
            ]

            response = await validator_llm.ainvoke(messages)

            usage_metadata = {}
            if hasattr(response, "response_metadata"):
                usage_metadata = response.response_metadata.get("usage", {})
            elif hasattr(response, "usage_metadata"):
                usage_metadata = response.usage_metadata or {}

            step_cost = None
            total_cost = state.get("total_cost", 0.0)
            token_usage = list(state.get("token_usage", []))

            if usage_metadata:
                from app.services.pricing import calculate_actual_cost

                actual_model = getattr(validator_llm, "model_name", None) or getattr(validator_llm, "model", None) or model_name
                step_cost = calculate_actual_cost(usage_metadata, actual_model)
                total_cost += step_cost
                token_usage.append({
                    "node": node_name,
                    "model": actual_model,
                    "usage": usage_metadata,
                    "cost": step_cost,
                })

            try:
                parsed = json.loads(response.content)
                verdict = parsed if isinstance(parsed, dict) else {"verdict": "review", "raw": parsed}
            except json.JSONDecodeError:
                verdict = {
                    "verdict": "review",
                    "raw": response.content,
                }

            node_output = {
                "type": "validator",
                "model": model_name,
                "content": response.content,
                "verdict": verdict.get("verdict"),
                "issues": verdict.get("issues"),
                "improvements": verdict.get("improvements"),
                "confidence": verdict.get("confidence"),
                "parsed": verdict,
                "usage": usage_metadata or None,
            }

            completed_at = datetime.utcnow()
            metric = {
                "node": node_name,
                "type": "validator",
                "model": model_name,
                "status": "completed",
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "duration": (completed_at - started_at).total_seconds(),
                "cost": step_cost,
                "tokens": usage_metadata.get("total_tokens") if usage_metadata else None,
            }
            node_metrics = _append_node_metric(state, metric)

            if log_callback:
                await log_callback(f"✅ Validator node '{node_name}' completed (verdict: {verdict.get('verdict')})")

            return {
                "outputs": {node_name: node_output},
                "step_count": state.get("step_count", 0) + 1,
                "total_cost": total_cost,
                "token_usage": token_usage,
                "node_metrics": node_metrics,
                "node_status": {node_name: "completed"},
            }

        except Exception as e:
            logger.error(f"Validator node {node_name} failed: {e}", exc_info=True)
            errors = list(state.get("errors", []))
            errors.append({"node": node_name, "error": str(e)})

            failed_at = datetime.utcnow()
            node_metrics = _append_node_metric(state, {
                "node": node_name,
                "type": "validator",
                "status": "failed",
                "started_at": started_at.isoformat(),
                "completed_at": failed_at.isoformat(),
                "duration": (failed_at - started_at).total_seconds(),
                "error": str(e),
            })

            if log_callback:
                await log_callback(f"❌ Validator node '{node_name}' failed: {e}")

            return {
                "errors": errors,
                "node_metrics": node_metrics,
                "node_status": {node_name: "failed"},
            }

    return validator_node


def create_aggregator_node(node_spec: dict, llm_router, log_callback=None):
    """Create an aggregator node that synthesises the workflow outputs."""

    async def aggregator_node(state: AgentState) -> AgentState:
        node_name = node_spec["name"]
        logger.info(f"Executing aggregator node: {node_name}")

        started_at = datetime.utcnow()
        if log_callback:
            await log_callback(f"🧩 Aggregating results in '{node_name}'")

        try:
            model_name = node_spec.get("model") or node_spec.get("fallback_model") or "gpt-4o-mini"
            aggregator_llm = await llm_router.get_llm(model_name)

            reasoning_node = node_spec.get("reasoning_node", "ReasoningLLM")
            validator_node = node_spec.get("validator_node", "Validator")
            tool_nodes = node_spec.get("tool_nodes", [])

            outputs_snapshot = state.get("outputs", {}) or {}

            reasoning_content = outputs_snapshot.get(reasoning_node, {}).get("content")
            validator_feedback = outputs_snapshot.get(validator_node)

            tool_summaries = []
            for tool_node in tool_nodes:
                if tool_node in outputs_snapshot:
                    tool_summaries.append(f"{tool_node}: {json.dumps(outputs_snapshot[tool_node], ensure_ascii=False, default=str)}")

            aggregation_prompt = node_spec.get("prompt_template") or (
                "You are compiling the final answer for the user. Combine the reasoning, tool outputs, "
                "and validator feedback into a clear, actionable response. Return JSON with fields "
                "'final_answer', 'summary', 'actions', 'warnings'."
            )

            payload = {
                "reasoning": reasoning_content,
                "tools": tool_summaries,
                "validator": validator_feedback,
                "inputs": state.get("inputs", {}),
            }

            formatted_prompt = aggregation_prompt.format(
                reasoning=reasoning_content or "",
                tools="\n".join(tool_summaries),
                validator=json.dumps(validator_feedback, ensure_ascii=False, default=str),
                context=json.dumps(payload, ensure_ascii=False, default=str),
            )

            messages = [
                HumanMessage(content=formatted_prompt)
            ]

            response = await aggregator_llm.ainvoke(messages)

            usage_metadata = {}
            if hasattr(response, "response_metadata"):
                usage_metadata = response.response_metadata.get("usage", {})
            elif hasattr(response, "usage_metadata"):
                usage_metadata = response.usage_metadata or {}

            step_cost = None
            total_cost = state.get("total_cost", 0.0)
            token_usage = list(state.get("token_usage", []))

            if usage_metadata:
                from app.services.pricing import calculate_actual_cost

                actual_model = getattr(aggregator_llm, "model_name", None) or getattr(aggregator_llm, "model", None) or model_name
                step_cost = calculate_actual_cost(usage_metadata, actual_model)
                total_cost += step_cost
                token_usage.append({
                    "node": node_name,
                    "model": actual_model,
                    "usage": usage_metadata,
                    "cost": step_cost,
                })

            aggregated = {
                "final_answer": response.content,
                "raw": response.content,
                "reasoning": reasoning_content,
                "tool_feedback": tool_summaries,
                "validator": validator_feedback,
            }
            try:
                parsed = json.loads(response.content)
                if isinstance(parsed, dict):
                    aggregated.update(parsed)
            except json.JSONDecodeError:
                pass

            # Capture artifacts emitted by previous nodes (e.g., file writer)
            artifacts = []
            for node_output in outputs_snapshot.values():
                if isinstance(node_output, dict):
                    artifact_payload = node_output.get("artifact")
                    if artifact_payload and artifact_payload.get("content"):
                        artifacts.append({
                            "name": artifact_payload.get("name", f"{node_name}_artifact"),
                            "artifact_type": artifact_payload.get("type", "text"),
                            "content": artifact_payload.get("content"),
                            "metadata": artifact_payload.get("metadata"),
                        })

            node_output = {
                "type": "aggregator",
                "model": model_name,
                "aggregated": aggregated,
            }
            final_payload = aggregated.get("final_answer") or aggregated.get("summary") or response.content

            messages = list(state.get("messages", []))
            messages.append(AIMessage(content=aggregated.get("final_answer") or response.content))

            completed_at = datetime.utcnow()
            metric = {
                "node": node_name,
                "type": "aggregator",
                "model": model_name,
                "status": "completed",
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "duration": (completed_at - started_at).total_seconds(),
                "cost": step_cost,
                "tokens": usage_metadata.get("total_tokens") if usage_metadata else None,
            }
            node_metrics = _append_node_metric(state, metric)

            if log_callback:
                await log_callback(f"✅ Aggregator node '{node_name}' produced final answer.")

            return {
                "messages": messages,
                "outputs": {
                    node_name: node_output,
                    "final_output": final_payload,
                    "aggregated_result": aggregated,
                },
                "artifacts": artifacts,
                "step_count": state.get("step_count", 0) + 1,
                "token_usage": token_usage,
                "total_cost": total_cost,
                "node_metrics": node_metrics,
                "node_status": {node_name: "completed"},
            }

        except Exception as e:
            logger.error(f"Aggregator node {node_name} failed: {e}", exc_info=True)
            errors = list(state.get("errors", []))
            errors.append({"node": node_name, "error": str(e)})

            failed_at = datetime.utcnow()
            node_metrics = _append_node_metric(state, {
                "node": node_name,
                "type": "aggregator",
                "status": "failed",
                "started_at": started_at.isoformat(),
                "completed_at": failed_at.isoformat(),
                "duration": (failed_at - started_at).total_seconds(),
                "error": str(e),
            })

            if log_callback:
                await log_callback(f"❌ Aggregator node '{node_name}' failed: {e}")

            return {
                "errors": errors,
                "node_metrics": node_metrics,
                "node_status": {node_name: "failed"},
            }

    return aggregator_node


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
            "node_metrics": state.get("node_metrics", []),
            "node_status": state.get("node_status", {}),
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
    spec: dict,
    llm_router,
    tools: dict,
    approval_callback=None,
    log_callback=None,
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
            node_fn = create_llm_node(node_spec, llm_router, log_callback)
        elif node_type == "tool":
            node_fn = create_tool_node(node_spec, tools, log_callback)
        elif node_type == "human":
            if not approval_callback:
                logger.warning(f"Human node {node_name} defined but no approval_callback provided")
                continue
            node_fn = create_human_node(node_spec, approval_callback, log_callback)
        elif node_type == "validator":
            node_fn = create_validator_node(node_spec, llm_router, log_callback)
        elif node_type == "aggregator":
            node_fn = create_aggregator_node(node_spec, llm_router, log_callback)
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

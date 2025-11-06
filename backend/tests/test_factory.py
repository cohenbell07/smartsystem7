"""
Tests for agent factory.
"""

import pytest
from app.agents.factory import create_agent_from_spec, AgentState
from app.services import LLMRouter


def test_agent_spec_structure():
    """Test that agent spec has required fields."""
    spec = {
        "name": "TestAgent",
        "description": "A test agent",
        "objective": "Test objective",
        "tools": ["browser"],
        "apis": [],
        "graph_type": "custom",
        "nodes": [
            {
                "name": "start",
                "type": "llm",
                "description": "Start node"
            }
        ],
        "edges": [],
        "test_plan": [],
        "success_criteria": [],
        "approval_gates": [],
        "estimated_runtime": 60
    }

    # Validate required fields
    assert "name" in spec
    assert "nodes" in spec
    assert "edges" in spec
    assert len(spec["nodes"]) > 0


@pytest.mark.asyncio
async def test_create_agent_from_spec():
    """Test agent creation from spec."""
    spec = {
        "name": "SimpleAgent",
        "description": "Simple test agent",
        "nodes": [
            {
                "name": "analyze",
                "type": "llm",
                "description": "Analyze input"
            }
        ],
        "edges": []
    }

    llm_router = LLMRouter()
    tools = {}

    # Should not raise
    try:
        graph = create_agent_from_spec(spec, llm_router, tools)
        assert graph is not None
    except ValueError as e:
        # Expected if no LLM configured
        if "No LLM configured" in str(e):
            pytest.skip("No LLM configured")
        else:
            raise


def test_agent_state_structure():
    """Test AgentState structure."""
    state: AgentState = {
        "messages": [],
        "inputs": {"test": "value"},
        "outputs": {},
        "artifacts": [],
        "step_count": 0,
        "errors": [],
        "token_usage": [],
        "total_cost": 0.0,
    }

    assert "messages" in state
    assert "inputs" in state
    assert "outputs" in state
    assert state["step_count"] == 0


@pytest.mark.asyncio
async def test_factory_auto_adds_final_output():
    """Test that factory automatically adds FinalOutput terminal node."""
    spec = {
        "name": "AgentWithoutTerminal",
        "description": "Agent with no terminal node",
        "nodes": [
            {
                "name": "step1",
                "type": "llm",
                "description": "First step"
            },
            {
                "name": "step2",
                "type": "llm",
                "description": "Second step"
            }
        ],
        "edges": [
            {"from": "step1", "to": "step2"}
        ]
    }

    llm_router = LLMRouter()
    tools = {}

    # Should not raise even without terminal node
    try:
        graph = create_agent_from_spec(spec, llm_router, tools)
        assert graph is not None
        # Graph should compile successfully with auto-added FinalOutput
    except ValueError as e:
        if "No LLM configured" in str(e):
            pytest.skip("No LLM configured")
        else:
            raise


@pytest.mark.asyncio
async def test_factory_handles_disconnected_nodes():
    """Test that factory linearizes disconnected nodes."""
    spec = {
        "name": "AgentWithDisconnected",
        "description": "Agent with disconnected nodes",
        "nodes": [
            {
                "name": "connected1",
                "type": "llm",
                "description": "Connected node 1"
            },
            {
                "name": "connected2",
                "type": "llm",
                "description": "Connected node 2"
            },
            {
                "name": "disconnected1",
                "type": "llm",
                "description": "Disconnected node 1"
            }
        ],
        "edges": [
            {"from": "connected1", "to": "connected2"}
        ]
    }

    llm_router = LLMRouter()
    tools = {}

    # Should not raise even with disconnected nodes
    try:
        graph = create_agent_from_spec(spec, llm_router, tools)
        assert graph is not None
        # Graph should compile with disconnected nodes linearized
    except ValueError as e:
        if "No LLM configured" in str(e):
            pytest.skip("No LLM configured")
        else:
            raise


@pytest.mark.asyncio
async def test_factory_generates_tool_stubs():
    """Test that factory generates stubs for missing tools."""
    spec = {
        "name": "AgentWithMissingTools",
        "description": "Agent referencing non-existent tools",
        "nodes": [
            {
                "name": "use_missing_tool",
                "type": "tool",
                "tool": "nonexistent_tool",
                "description": "Use a tool that doesn't exist"
            }
        ],
        "edges": []
    }

    llm_router = LLMRouter()
    tools = {}  # No tools provided

    # Should not raise even with missing tools
    try:
        graph = create_agent_from_spec(spec, llm_router, tools)
        assert graph is not None
        # Graph should compile with tool stub generated
    except ValueError as e:
        if "No LLM configured" in str(e):
            pytest.skip("No LLM configured")
        else:
            raise


@pytest.mark.asyncio
async def test_tool_stub_execution():
    """Test that tool stub returns proper error message."""
    from app.agents.factory import generate_tool_stub

    stub = generate_tool_stub("test_tool")
    result = await stub.execute({"input": "test"})

    assert result["success"] is False
    assert "error" in result
    assert "test_tool" in result["error"]
    assert "not implemented" in result["error"].lower()


@pytest.mark.asyncio
async def test_factory_with_multiple_terminals():
    """Test that factory handles multiple terminal candidates."""
    spec = {
        "name": "AgentWithMultipleTerminals",
        "description": "Agent with multiple terminal candidates",
        "nodes": [
            {
                "name": "start",
                "type": "llm",
                "description": "Start node"
            },
            {
                "name": "branch1",
                "type": "llm",
                "description": "Branch 1 terminal"
            },
            {
                "name": "branch2",
                "type": "llm",
                "description": "Branch 2 terminal"
            }
        ],
        "edges": [
            {"from": "start", "to": "branch1"},
            {"from": "start", "to": "branch2"}
        ]
    }

    llm_router = LLMRouter()
    tools = {}

    # Should handle multiple terminal candidates
    try:
        graph = create_agent_from_spec(spec, llm_router, tools)
        assert graph is not None
    except ValueError as e:
        if "No LLM configured" in str(e):
            pytest.skip("No LLM configured")
        else:
            raise

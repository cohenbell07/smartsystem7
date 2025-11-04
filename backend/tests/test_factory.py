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
        "errors": []
    }

    assert "messages" in state
    assert "inputs" in state
    assert "outputs" in state
    assert state["step_count"] == 0

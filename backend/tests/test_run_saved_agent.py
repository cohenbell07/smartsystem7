"""
Tests for running saved agents.
"""

import pytest
from sqlmodel import Session, create_engine, SQLModel
from app.models import Agent, Run, RunStatus
from app.agents.factory import create_agent_from_spec
from app.services.llm_router import LLMRouter


@pytest.fixture
def test_db():
    """Create test database."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def test_session(test_db):
    """Create test session."""
    with Session(test_db) as session:
        yield session


def test_create_saved_agent(test_session):
    """Test creating a saved agent."""
    agent_spec = {
        "name": "TestAgent",
        "description": "Test agent for validation",
        "objective": "Test",
        "tools": [],
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
        "test_plan": ["Test 1"],
        "success_criteria": ["Success 1"],
        "approval_gates": [],
        "estimated_runtime": 60
    }

    agent = Agent(
        name="TestAgent",
        description="A test agent",
        agent_spec=agent_spec,
        user_id="test_user"
    )

    test_session.add(agent)
    test_session.commit()
    test_session.refresh(agent)

    assert agent.id is not None
    assert agent.name == "TestAgent"
    assert agent.agent_spec == agent_spec


def test_create_run_for_saved_agent(test_session):
    """Test creating a run for a saved agent."""
    agent_spec = {
        "name": "TestAgent",
        "description": "Test agent",
        "nodes": [],
        "edges": []
    }

    agent = Agent(
        name="TestAgent",
        description="Test agent",
        agent_spec=agent_spec,
        user_id="test_user"
    )
    test_session.add(agent)
    test_session.commit()
    test_session.refresh(agent)

    # Create run with prompt
    run = Run(
        agent_id=agent.id,
        status=RunStatus.QUEUED,
        prompt="Test prompt",
        inputs={"key": "value"}
    )
    test_session.add(run)
    test_session.commit()
    test_session.refresh(run)

    assert run.id is not None
    assert run.agent_id == agent.id
    assert run.prompt == "Test prompt"
    assert run.status == RunStatus.QUEUED


def test_run_execution_flow(test_session):
    """Test run execution state flow."""
    agent_spec = {
        "name": "TestAgent",
        "description": "Test agent",
        "nodes": [],
        "edges": []
    }

    agent = Agent(
        name="TestAgent",
        description="Test agent",
        agent_spec=agent_spec,
        user_id="test_user"
    )
    test_session.add(agent)
    test_session.commit()
    test_session.refresh(agent)

    run = Run(
        agent_id=agent.id,
        status=RunStatus.QUEUED
    )
    test_session.add(run)
    test_session.commit()

    # Transition to RUNNING
    run.status = RunStatus.RUNNING
    test_session.add(run)
    test_session.commit()
    assert run.status == RunStatus.RUNNING

    # Transition to COMPLETED
    run.status = RunStatus.COMPLETED
    run.outputs = {"result": "success"}
    test_session.add(run)
    test_session.commit()
    assert run.status == RunStatus.COMPLETED
    assert run.outputs["result"] == "success"


@pytest.mark.asyncio
async def test_agent_compiles_from_saved_spec():
    """Test that a saved agent spec can be compiled."""
    agent_spec = {
        "name": "SimpleAgent",
        "description": "Simple test agent",
        "nodes": [
            {
                "name": "step1",
                "type": "llm",
                "description": "First step"
            }
        ],
        "edges": []
    }

    llm_router = LLMRouter()
    tools = {}

    # Should compile successfully
    try:
        graph = create_agent_from_spec(agent_spec, llm_router, tools)
        assert graph is not None
    except ValueError as e:
        if "No LLM configured" in str(e):
            pytest.skip("No LLM configured")
        else:
            raise


def test_run_with_both_prompt_and_inputs(test_session):
    """Test run can have both prompt and inputs."""
    agent_spec = {
        "name": "TestAgent",
        "description": "Test agent",
        "nodes": [],
        "edges": []
    }

    agent = Agent(
        name="TestAgent",
        description="Test agent",
        agent_spec=agent_spec,
        user_id="test_user"
    )
    test_session.add(agent)
    test_session.commit()
    test_session.refresh(agent)

    # Create run with both prompt and inputs
    run = Run(
        agent_id=agent.id,
        status=RunStatus.QUEUED,
        prompt="Do something with this data",
        inputs={"data": [1, 2, 3]}
    )
    test_session.add(run)
    test_session.commit()
    test_session.refresh(run)

    assert run.prompt == "Do something with this data"
    assert run.inputs == {"data": [1, 2, 3]}


def test_run_cost_tracking(test_session):
    """Test that runs track costs properly."""
    agent_spec = {
        "name": "TestAgent",
        "description": "Test agent",
        "nodes": [],
        "edges": []
    }

    agent = Agent(
        name="TestAgent",
        description="Test agent",
        agent_spec=agent_spec,
        user_id="test_user"
    )
    test_session.add(agent)
    test_session.commit()
    test_session.refresh(agent)

    run = Run(
        agent_id=agent.id,
        status=RunStatus.COMPLETED,
        cost_estimate=0.05,
        actual_cost=0.048,
        total_tokens=1200,
        cost_breakdown={
            "estimated": {"total": 0.05},
            "actual": {"total": 0.048}
        }
    )
    test_session.add(run)
    test_session.commit()
    test_session.refresh(run)

    assert run.cost_estimate == 0.05
    assert run.actual_cost == 0.048
    assert run.total_tokens == 1200
    assert run.cost_breakdown is not None

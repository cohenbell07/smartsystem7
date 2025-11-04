"""
Video generation agent graph example.
"""

import logging
from langgraph.graph import StateGraph, END
from app.agents.factory import AgentState

logger = logging.getLogger(__name__)


def create_video_generation_graph(llm_router, tools: dict):
    """
    Create a video generation agent graph.

    Flow:
    1. Analyze requirements
    2. Generate script
    3. Create storyboard
    4. Generate assets (images, audio)
    5. Assemble video
    6. Review and export
    """
    workflow = StateGraph(AgentState)

    # Node 1: Analyze requirements
    async def analyze_requirements(state: AgentState):
        logger.info("Analyzing video requirements")
        inputs = state.get("inputs", {})
        topic = inputs.get("topic", "")

        llm = await llm_router.get_llm()
        prompt = f"Analyze requirements for a video about: {topic}. What should we cover?"

        response = await llm.ainvoke([{"role": "user", "content": prompt}])

        outputs = state.get("outputs", {})
        outputs["requirements"] = response.content

        return {"outputs": outputs, "step_count": state.get("step_count", 0) + 1}

    # Node 2: Generate script
    async def generate_script(state: AgentState):
        logger.info("Generating video script")

        llm = await llm_router.get_llm()
        requirements = state.get("outputs", {}).get("requirements", "")
        prompt = f"Write a video script based on: {requirements}"

        response = await llm.ainvoke([{"role": "user", "content": prompt}])

        outputs = state.get("outputs", {})
        outputs["script"] = response.content

        return {"outputs": outputs, "step_count": state.get("step_count", 0) + 1}

    # Node 3: Create storyboard
    async def create_storyboard(state: AgentState):
        logger.info("Creating storyboard")

        llm = await llm_router.get_llm()
        script = state.get("outputs", {}).get("script", "")
        prompt = f"Create a shot-by-shot storyboard for script: {script}"

        response = await llm.ainvoke([{"role": "user", "content": prompt}])

        outputs = state.get("outputs", {})
        outputs["storyboard"] = response.content

        return {"outputs": outputs, "step_count": state.get("step_count", 0) + 1}

    # Node 4: Finalize
    async def finalize(state: AgentState):
        logger.info("Finalizing video plan")

        outputs = state.get("outputs", {})
        outputs["status"] = "completed"
        outputs["message"] = "Video generation plan ready. Manual asset creation and assembly required."

        return {"outputs": outputs, "step_count": state.get("step_count", 0) + 1}

    # Add nodes
    workflow.add_node("analyze", analyze_requirements)
    workflow.add_node("script", generate_script)
    workflow.add_node("storyboard", create_storyboard)
    workflow.add_node("finalize", finalize)

    # Add edges
    workflow.set_entry_point("analyze")
    workflow.add_edge("analyze", "script")
    workflow.add_edge("script", "storyboard")
    workflow.add_edge("storyboard", "finalize")
    workflow.add_edge("finalize", END)

    return workflow.compile()

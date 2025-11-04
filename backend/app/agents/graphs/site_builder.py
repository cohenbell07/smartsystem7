"""
Site builder agent graph example.
"""

import logging
from langgraph.graph import StateGraph, END
from app.agents.factory import AgentState

logger = logging.getLogger(__name__)


def create_site_builder_graph(llm_router, tools: dict):
    """
    Create a site builder agent graph.

    Flow:
    1. Analyze requirements
    2. Design sitemap
    3. Generate content
    4. Create HTML/CSS
    5. Deploy (with approval)
    """
    workflow = StateGraph(AgentState)

    # Node 1: Analyze requirements
    async def analyze_requirements(state: AgentState):
        logger.info("Analyzing site requirements")
        inputs = state.get("inputs", {})
        description = inputs.get("description", "")

        llm = await llm_router.get_llm()
        prompt = f"Analyze requirements for a website: {description}. What pages are needed?"

        response = await llm.ainvoke([{"role": "user", "content": prompt}])

        outputs = state.get("outputs", {})
        outputs["requirements"] = response.content

        return {"outputs": outputs, "step_count": state.get("step_count", 0) + 1}

    # Node 2: Design sitemap
    async def design_sitemap(state: AgentState):
        logger.info("Designing sitemap")

        llm = await llm_router.get_llm()
        requirements = state.get("outputs", {}).get("requirements", "")
        prompt = f"Create a sitemap based on: {requirements}"

        response = await llm.ainvoke([{"role": "user", "content": prompt}])

        outputs = state.get("outputs", {})
        outputs["sitemap"] = response.content

        return {"outputs": outputs, "step_count": state.get("step_count", 0) + 1}

    # Node 3: Generate content
    async def generate_content(state: AgentState):
        logger.info("Generating page content")

        llm = await llm_router.get_llm()
        sitemap = state.get("outputs", {}).get("sitemap", "")
        prompt = f"Write content for these pages: {sitemap}"

        response = await llm.ainvoke([{"role": "user", "content": prompt}])

        outputs = state.get("outputs", {})
        outputs["content"] = response.content

        return {"outputs": outputs, "step_count": state.get("step_count", 0) + 1}

    # Node 4: Create HTML
    async def create_html(state: AgentState):
        logger.info("Creating HTML/CSS")

        llm = await llm_router.get_llm()
        content = state.get("outputs", {}).get("content", "")
        prompt = f"Generate HTML/CSS for this content: {content}"

        response = await llm.ainvoke([{"role": "user", "content": prompt}])

        outputs = state.get("outputs", {})
        outputs["html"] = response.content
        outputs["status"] = "completed"
        outputs["message"] = "Website code generated. Ready for deployment."

        # Create artifact
        artifacts = state.get("artifacts", [])
        artifacts.append({
            "name": "index.html",
            "type": "code",
            "content": response.content,
        })

        return {
            "outputs": outputs,
            "artifacts": artifacts,
            "step_count": state.get("step_count", 0) + 1
        }

    # Add nodes
    workflow.add_node("analyze", analyze_requirements)
    workflow.add_node("sitemap", design_sitemap)
    workflow.add_node("content", generate_content)
    workflow.add_node("html", create_html)

    # Add edges
    workflow.set_entry_point("analyze")
    workflow.add_edge("analyze", "sitemap")
    workflow.add_edge("sitemap", "content")
    workflow.add_edge("content", "html")
    workflow.add_edge("html", END)

    return workflow.compile()

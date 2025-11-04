"""
Outreach agent graph example.
"""

import logging
from langgraph.graph import StateGraph, END
from app.agents.factory import AgentState

logger = logging.getLogger(__name__)


def create_outreach_graph(llm_router, tools: dict):
    """
    Create an outreach agent graph.

    Flow:
    1. Research prospects
    2. Personalize message
    3. Request approval
    4. Send emails
    5. Track responses
    """
    workflow = StateGraph(AgentState)

    # Node 1: Research prospects
    async def research_prospects(state: AgentState):
        logger.info("Researching prospects")
        inputs = state.get("inputs", {})
        industry = inputs.get("industry", "")

        browser = tools.get("browser")
        if browser:
            # Use browser to research prospects
            result = await browser.execute({
                "action": "goto",
                "url": f"https://www.linkedin.com/search/people/?industry={industry}"
            })
        else:
            result = {"note": "Browser tool not available"}

        outputs = state.get("outputs", {})
        outputs["prospects"] = ["prospect1@example.com", "prospect2@example.com"]  # Mock data

        return {"outputs": outputs, "step_count": state.get("step_count", 0) + 1}

    # Node 2: Personalize message
    async def personalize_message(state: AgentState):
        logger.info("Personalizing outreach messages")

        llm = await llm_router.get_llm()
        prospects = state.get("outputs", {}).get("prospects", [])
        template = state.get("inputs", {}).get("template", "")

        messages = []
        for prospect in prospects:
            prompt = f"Personalize this template for {prospect}: {template}"
            response = await llm.ainvoke([{"role": "user", "content": prompt}])
            messages.append({
                "to": prospect,
                "subject": "Partnership Opportunity",
                "body": response.content,
            })

        outputs = state.get("outputs", {})
        outputs["messages"] = messages

        return {"outputs": outputs, "step_count": state.get("step_count", 0) + 1}

    # Node 3: Send emails
    async def send_emails(state: AgentState):
        logger.info("Sending outreach emails")

        email_tool = tools.get("email")
        messages = state.get("outputs", {}).get("messages", [])

        results = []
        if email_tool:
            for msg in messages:
                result = await email_tool.execute({
                    "to": msg["to"],
                    "subject": msg["subject"],
                    "body": msg["body"],
                })
                results.append(result)
        else:
            results = [{"note": "Email tool not available"}]

        outputs = state.get("outputs", {})
        outputs["sent_count"] = len(results)
        outputs["status"] = "completed"

        return {"outputs": outputs, "step_count": state.get("step_count", 0) + 1}

    # Add nodes
    workflow.add_node("research", research_prospects)
    workflow.add_node("personalize", personalize_message)
    workflow.add_node("send", send_emails)

    # Add edges
    workflow.set_entry_point("research")
    workflow.add_edge("research", "personalize")
    workflow.add_edge("personalize", "send")
    workflow.add_edge("send", END)

    return workflow.compile()

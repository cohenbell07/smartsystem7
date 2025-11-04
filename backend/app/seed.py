"""
Database seed script to create demo data.
"""

import logging
from sqlmodel import Session
from app.database import engine, create_db_and_tables
from app.models import Agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def seed_database():
    """Seed database with demo agent."""
    logger.info("Seeding database...")

    create_db_and_tables()

    with Session(engine) as session:
        # Create demo OutreachAgent
        outreach_agent = Agent(
            name="OutreachAgent",
            description="Automated outreach agent for partnerships and sales",
            agent_spec={
                "name": "OutreachAgent",
                "description": "Researches prospects, personalizes messages, and manages outreach campaigns",
                "objective": "Send personalized outreach emails to target prospects",
                "tools": ["browser", "email"],
                "apis": [],
                "graph_type": "outreach",
                "nodes": [
                    {
                        "name": "research",
                        "type": "tool",
                        "description": "Research prospects",
                        "tool": "browser"
                    },
                    {
                        "name": "personalize",
                        "type": "llm",
                        "description": "Personalize outreach messages"
                    },
                    {
                        "name": "send",
                        "type": "tool",
                        "description": "Send emails",
                        "tool": "email"
                    }
                ],
                "edges": [
                    {"from": "research", "to": "personalize", "condition": None},
                    {"from": "personalize", "to": "send", "condition": None}
                ],
                "test_plan": [
                    {
                        "input": {"industry": "SaaS", "template": "Hi {name}..."},
                        "expected_output": "5 emails sent",
                        "pass_criteria": "All emails delivered"
                    }
                ],
                "success_criteria": [
                    "Research 10+ prospects",
                    "Personalize messages with 80%+ relevance",
                    "Send within 5 minutes"
                ],
                "approval_gates": ["send"],
                "estimated_runtime": 300
            }
        )

        session.add(outreach_agent)
        session.commit()

        logger.info(f"Created demo agent: {outreach_agent.name}")

    logger.info("Database seeded successfully!")


if __name__ == "__main__":
    seed_database()

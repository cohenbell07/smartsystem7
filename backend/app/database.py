"""
Database connection and session management.
"""

import os
from sqlmodel import create_engine, SQLModel, Session
from sqlalchemy.pool import StaticPool

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agent_factory.db")

# SQLite specific configuration for dev
connect_args = {}
poolclass = None

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    poolclass = StaticPool

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    poolclass=poolclass,
    echo=os.getenv("ENVIRONMENT") == "development",
)


def create_db_and_tables():
    """Create all database tables."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Get a database session. Use as dependency in FastAPI routes."""
    with Session(engine) as session:
        yield session

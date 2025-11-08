"""
Memory + Telemetry Database

Persistent storage for build history, model performance, and telemetry data.
Uses SQLite for local storage with async support.
"""

import logging
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
import aiosqlite
from pathlib import Path

logger = logging.getLogger(__name__)


class MemoryDB:
    """
    Memory and Telemetry Database for SmartSystem7.

    Tracks:
    - Build history with outcomes and quality metrics
    - Model performance statistics (latency, success rate)
    - Deployment records (GitHub, Vercel)
    """

    def __init__(self, db_path: str = "backend/data/memory.sqlite3"):
        """
        Initialize the Memory DB.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

        # Ensure parent directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Memory DB initialized at {db_path}")

    async def initialize(self):
        """Create database tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            # Build history table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS build_history (
                    run_id TEXT PRIMARY KEY,
                    prompt TEXT NOT NULL,
                    quality REAL DEFAULT 0.0,
                    model_map TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    repo_url TEXT,
                    vercel_url TEXT,
                    duration_sec REAL,
                    status TEXT DEFAULT 'completed',
                    error TEXT,
                    requirements TEXT,
                    tech_stack TEXT,
                    project_type TEXT,
                    iterations INTEGER DEFAULT 1,
                    docker_validated BOOLEAN DEFAULT 0,
                    github_deployed BOOLEAN DEFAULT 0,
                    vercel_deployed BOOLEAN DEFAULT 0
                )
            """)

            # Model statistics table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS model_stats (
                    model_name TEXT PRIMARY KEY,
                    provider TEXT,
                    avg_latency REAL DEFAULT 0.0,
                    avg_quality REAL DEFAULT 0.0,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    total_calls INTEGER DEFAULT 0,
                    last_used TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Model call logs table (detailed telemetry)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS model_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    task_type TEXT,
                    success BOOLEAN DEFAULT 1,
                    latency REAL,
                    tokens_used INTEGER,
                    cost REAL,
                    run_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES build_history(run_id)
                )
            """)

            # Create indexes for performance
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_build_created
                ON build_history(created_at DESC)
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_model_calls_run
                ON model_calls(run_id)
            """)

            await db.commit()
            logger.info("Memory DB tables initialized successfully")

    async def save_build(
        self,
        run_id: str,
        prompt: str,
        quality: float,
        model_map: Dict[str, str],
        duration_sec: float,
        status: str = "completed",
        repo_url: Optional[str] = None,
        vercel_url: Optional[str] = None,
        error: Optional[str] = None,
        requirements: Optional[Dict[str, Any]] = None,
        iterations: int = 1,
        docker_validated: bool = False,
        github_deployed: bool = False,
        vercel_deployed: bool = False
    ):
        """
        Save a build record to the database.

        Args:
            run_id: Unique run identifier
            prompt: User's original prompt
            quality: Quality score (0.0 to 1.0)
            model_map: Dict mapping task types to models used
            duration_sec: Build duration in seconds
            status: Build status (completed, failed, etc.)
            repo_url: GitHub repository URL
            vercel_url: Vercel deployment URL
            error: Error message if failed
            requirements: Parsed requirements dict
            iterations: Number of iterations
            docker_validated: Whether Docker validation passed
            github_deployed: Whether GitHub deployment succeeded
            vercel_deployed: Whether Vercel deployment succeeded
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO build_history (
                        run_id, prompt, quality, model_map, duration_sec,
                        status, repo_url, vercel_url, error, requirements,
                        tech_stack, project_type, iterations,
                        docker_validated, github_deployed, vercel_deployed,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    run_id,
                    prompt,
                    quality,
                    json.dumps(model_map),
                    duration_sec,
                    status,
                    repo_url,
                    vercel_url,
                    error,
                    json.dumps(requirements) if requirements else None,
                    json.dumps(requirements.get("tech_stack", {})) if requirements else None,
                    requirements.get("project_type") if requirements else None,
                    iterations,
                    docker_validated,
                    github_deployed,
                    vercel_deployed,
                    datetime.utcnow().isoformat()
                ))
                await db.commit()

            logger.info(f"Saved build {run_id} to memory DB (quality: {quality:.2%})")

        except Exception as e:
            logger.error(f"Failed to save build {run_id}: {e}")

    async def log_model_call(
        self,
        model_name: str,
        provider: str,
        success: bool,
        latency: float,
        task_type: Optional[str] = None,
        tokens_used: Optional[int] = None,
        cost: Optional[float] = None,
        run_id: Optional[str] = None
    ):
        """
        Log a model call for telemetry.

        Args:
            model_name: Model identifier
            provider: Provider name (openai, anthropic, google)
            success: Whether the call succeeded
            latency: Call latency in seconds
            task_type: Type of task
            tokens_used: Number of tokens used
            cost: Estimated cost
            run_id: Associated build run ID
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Log the call
                await db.execute("""
                    INSERT INTO model_calls (
                        model_name, provider, task_type, success, latency,
                        tokens_used, cost, run_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    model_name,
                    provider,
                    task_type,
                    success,
                    latency,
                    tokens_used,
                    cost,
                    run_id,
                    datetime.utcnow().isoformat()
                ))

                # Update model stats
                await db.execute("""
                    INSERT INTO model_stats (
                        model_name, provider, avg_latency, success_count,
                        fail_count, total_calls, last_used, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(model_name) DO UPDATE SET
                        total_calls = total_calls + 1,
                        success_count = success_count + ?,
                        fail_count = fail_count + ?,
                        avg_latency = (avg_latency * total_calls + ?) / (total_calls + 1),
                        last_used = ?,
                        updated_at = ?
                """, (
                    model_name,
                    provider,
                    latency,
                    1 if success else 0,
                    0 if success else 1,
                    datetime.utcnow().isoformat(),
                    datetime.utcnow().isoformat(),
                    1 if success else 0,
                    0 if success else 1,
                    latency,
                    datetime.utcnow().isoformat(),
                    datetime.utcnow().isoformat()
                ))

                await db.commit()

        except Exception as e:
            logger.error(f"Failed to log model call for {model_name}: {e}")

    async def get_builds(
        self,
        limit: int = 20,
        offset: int = 0,
        status_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get build history with pagination.

        Args:
            limit: Maximum number of records to return
            offset: Offset for pagination
            status_filter: Filter by status (optional)

        Returns:
            List of build records
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row

                query = """
                    SELECT * FROM build_history
                """
                params = []

                if status_filter:
                    query += " WHERE status = ?"
                    params.append(status_filter)

                query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()

                    builds = []
                    for row in rows:
                        build = dict(row)
                        # Parse JSON fields
                        if build.get("model_map"):
                            build["model_map"] = json.loads(build["model_map"])
                        if build.get("requirements"):
                            build["requirements"] = json.loads(build["requirements"])
                        if build.get("tech_stack"):
                            build["tech_stack"] = json.loads(build["tech_stack"])
                        builds.append(build)

                    return builds

        except Exception as e:
            logger.error(f"Failed to get builds: {e}")
            return []

    async def get_build_by_id(self, run_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific build by run ID.

        Args:
            run_id: Build run ID

        Returns:
            Build record or None
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row

                async with db.execute(
                    "SELECT * FROM build_history WHERE run_id = ?",
                    (run_id,)
                ) as cursor:
                    row = await cursor.fetchone()

                    if row:
                        build = dict(row)
                        # Parse JSON fields
                        if build.get("model_map"):
                            build["model_map"] = json.loads(build["model_map"])
                        if build.get("requirements"):
                            build["requirements"] = json.loads(build["requirements"])
                        if build.get("tech_stack"):
                            build["tech_stack"] = json.loads(build["tech_stack"])
                        return build

                    return None

        except Exception as e:
            logger.error(f"Failed to get build {run_id}: {e}")
            return None

    async def get_model_stats(self) -> List[Dict[str, Any]]:
        """
        Get performance statistics for all models.

        Returns:
            List of model stats
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row

                async with db.execute("""
                    SELECT
                        model_name,
                        provider,
                        avg_latency,
                        avg_quality,
                        success_count,
                        fail_count,
                        total_calls,
                        CASE
                            WHEN total_calls > 0
                            THEN CAST(success_count AS REAL) / total_calls
                            ELSE 0.0
                        END as success_rate,
                        last_used,
                        created_at,
                        updated_at
                    FROM model_stats
                    ORDER BY total_calls DESC
                """) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get model stats: {e}")
            return []

    async def get_model_calls_for_run(self, run_id: str) -> List[Dict[str, Any]]:
        """
        Get all model calls for a specific run.

        Args:
            run_id: Build run ID

        Returns:
            List of model call records
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row

                async with db.execute("""
                    SELECT * FROM model_calls
                    WHERE run_id = ?
                    ORDER BY created_at ASC
                """, (run_id,)) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get model calls for run {run_id}: {e}")
            return []

    async def get_stats_summary(self) -> Dict[str, Any]:
        """
        Get overall statistics summary.

        Returns:
            Dict with summary statistics
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Total builds
                async with db.execute("SELECT COUNT(*) as count FROM build_history") as cursor:
                    row = await cursor.fetchone()
                    total_builds = row[0] if row else 0

                # Successful builds
                async with db.execute(
                    "SELECT COUNT(*) as count FROM build_history WHERE status = 'completed'"
                ) as cursor:
                    row = await cursor.fetchone()
                    successful_builds = row[0] if row else 0

                # Average quality
                async with db.execute(
                    "SELECT AVG(quality) as avg_quality FROM build_history WHERE status = 'completed'"
                ) as cursor:
                    row = await cursor.fetchone()
                    avg_quality = row[0] if row and row[0] else 0.0

                # Total model calls
                async with db.execute("SELECT SUM(total_calls) as total FROM model_stats") as cursor:
                    row = await cursor.fetchone()
                    total_model_calls = row[0] if row and row[0] else 0

                # Deployments
                async with db.execute(
                    "SELECT COUNT(*) as count FROM build_history WHERE github_deployed = 1"
                ) as cursor:
                    row = await cursor.fetchone()
                    github_deployments = row[0] if row else 0

                async with db.execute(
                    "SELECT COUNT(*) as count FROM build_history WHERE vercel_deployed = 1"
                ) as cursor:
                    row = await cursor.fetchone()
                    vercel_deployments = row[0] if row else 0

                return {
                    "total_builds": total_builds,
                    "successful_builds": successful_builds,
                    "failed_builds": total_builds - successful_builds,
                    "success_rate": successful_builds / total_builds if total_builds > 0 else 0.0,
                    "average_quality": avg_quality,
                    "total_model_calls": total_model_calls,
                    "github_deployments": github_deployments,
                    "vercel_deployments": vercel_deployments,
                }

        except Exception as e:
            logger.error(f"Failed to get stats summary: {e}")
            return {
                "total_builds": 0,
                "successful_builds": 0,
                "failed_builds": 0,
                "success_rate": 0.0,
                "average_quality": 0.0,
                "total_model_calls": 0,
                "github_deployments": 0,
                "vercel_deployments": 0,
            }


# Global instance
_memory_db: Optional[MemoryDB] = None


async def get_memory_db(db_path: str = "backend/data/memory.sqlite3") -> MemoryDB:
    """
    Get or create the global Memory DB instance.

    Args:
        db_path: Path to SQLite database

    Returns:
        MemoryDB instance
    """
    global _memory_db

    if _memory_db is None:
        _memory_db = MemoryDB(db_path)
        await _memory_db.initialize()

    return _memory_db

"""
Docker Executor: Safe Code Execution in Isolated Containers

Executes code and tests safely in Docker containers with:
- Resource limits (CPU, memory, timeout)
- Network isolation
- Automatic cleanup
"""

import logging
import json
import tempfile
import os
import shutil
from typing import Dict, Any, Optional, List
from pathlib import Path
import asyncio

logger = logging.getLogger(__name__)


class DockerExecutor:
    """
    Execute code safely in Docker containers.

    Provides isolated execution environment for validation and testing.
    """

    def __init__(self, config):
        """
        Initialize Docker executor.

        Args:
            config: Application config with Docker settings
        """
        self.config = config
        self.docker_client = None
        self.docker_available = False

        # Initialize Docker client
        self._init_docker_client()

    def _init_docker_client(self):
        """Initialize Docker client if available."""
        if not self.config.is_docker_available():
            logger.warning("Docker execution disabled in config")
            return

        try:
            import docker
            self.docker_client = docker.from_env()
            # Test connection
            self.docker_client.ping()
            self.docker_available = True
            logger.info("Docker client initialized successfully")
        except Exception as e:
            logger.warning(f"Docker not available: {e}")
            self.docker_available = False

    def is_available(self) -> bool:
        """Check if Docker is available for execution."""
        return self.docker_available

    async def execute_python(
        self,
        code_files: Dict[str, str],
        requirements: Optional[List[str]] = None,
        test_command: str = "pytest",
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute Python code in Docker container.

        Args:
            code_files: Dict mapping file paths to content
            requirements: List of pip packages to install
            test_command: Command to run tests (default: "pytest")
            timeout: Execution timeout in seconds (uses config default if None)

        Returns:
            Dict with execution results:
            - success: bool
            - stdout: str
            - stderr: str
            - exit_code: int
            - tests_passed: bool (if running tests)
            - error: str (if error occurred)
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "docker_unavailable",
                "message": "Docker is not available or not configured",
                "stdout": "",
                "stderr": "",
            }

        timeout = timeout or self.config.DOCKER_TIMEOUT

        # Create temporary directory for code
        temp_dir = None
        container = None

        try:
            # Create temp workspace
            temp_dir = tempfile.mkdtemp(prefix="docker_exec_")
            workspace = Path(temp_dir)

            # Write code files
            for file_path, content in code_files.items():
                file_full_path = workspace / file_path
                file_full_path.parent.mkdir(parents=True, exist_ok=True)
                file_full_path.write_text(content)

            # Create requirements.txt if needed
            if requirements:
                req_file = workspace / "requirements.txt"
                req_file.write_text("\n".join(requirements))

            # Create execution script
            exec_script = self._create_execution_script(
                has_requirements=bool(requirements),
                test_command=test_command
            )
            (workspace / "run.sh").write_text(exec_script)
            os.chmod(workspace / "run.sh", 0o755)

            # Run in Docker
            logger.info(f"Executing code in Docker (timeout: {timeout}s)")
            result = await self._run_container(
                workspace=temp_dir,
                timeout=timeout
            )

            return result

        except asyncio.TimeoutError:
            logger.error(f"Docker execution timed out after {timeout}s")
            return {
                "success": False,
                "error": "timeout",
                "message": f"Execution timed out after {timeout}s",
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
            }

        except Exception as e:
            logger.error(f"Docker execution error: {e}", exc_info=True)
            return {
                "success": False,
                "error": "execution_error",
                "message": str(e),
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
            }

        finally:
            # Cleanup container
            if container:
                try:
                    container.stop(timeout=5)
                    container.remove()
                except Exception as e:
                    logger.warning(f"Failed to cleanup container: {e}")

            # Cleanup temp directory
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp dir: {e}")

    def _create_execution_script(
        self,
        has_requirements: bool,
        test_command: str
    ) -> str:
        """Create bash script for execution inside container."""
        script = """#!/bin/bash
set -e

cd /workspace

"""

        if has_requirements:
            script += """
# Install requirements
if [ -f requirements.txt ]; then
    echo "Installing requirements..."
    pip install -q -r requirements.txt
fi

"""

        script += f"""
# Run tests
echo "Running tests..."
{test_command} -v 2>&1

echo "Tests completed with exit code: $?"
"""

        return script

    async def _run_container(
        self,
        workspace: str,
        timeout: int
    ) -> Dict[str, Any]:
        """
        Run Docker container with code.

        Args:
            workspace: Path to workspace directory
            timeout: Execution timeout

        Returns:
            Execution result dict
        """
        import docker

        try:
            # Pull image if needed
            image_name = "python:3.11-slim"
            logger.info(f"Using Docker image: {image_name}")

            # Run container in thread pool (docker-py is sync)
            loop = asyncio.get_event_loop()
            container = await loop.run_in_executor(
                None,
                lambda: self.docker_client.containers.run(
                    image=image_name,
                    command="/bin/bash /workspace/run.sh",
                    volumes={
                        workspace: {"bind": "/workspace", "mode": "rw"}
                    },
                    working_dir="/workspace",
                    mem_limit=self.config.DOCKER_MEMORY_LIMIT,
                    cpu_quota=int(self.config.DOCKER_CPU_LIMIT * 100000),
                    cpu_period=100000,
                    network_mode="none",  # No network access
                    detach=True,
                    remove=False,  # We'll remove manually
                )
            )

            # Wait for completion with timeout
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: container.wait(timeout=timeout)
                    ),
                    timeout=timeout
                )

                exit_code = result.get("StatusCode", -1)

                # Get logs
                logs = await loop.run_in_executor(
                    None,
                    lambda: container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
                )

                # Parse stdout/stderr (Docker combines them)
                stdout = logs
                stderr = ""

                # Determine if tests passed (exit code 0)
                tests_passed = exit_code == 0

                logger.info(f"Container execution completed: exit_code={exit_code}")

                return {
                    "success": True,
                    "exit_code": exit_code,
                    "stdout": stdout,
                    "stderr": stderr,
                    "tests_passed": tests_passed,
                }

            except asyncio.TimeoutError:
                # Kill container if timeout
                await loop.run_in_executor(None, lambda: container.kill())
                raise

            finally:
                # Cleanup container
                try:
                    await loop.run_in_executor(None, lambda: container.remove())
                except Exception as e:
                    logger.warning(f"Failed to remove container: {e}")

        except docker.errors.ImageNotFound:
            logger.error(f"Docker image not found: {image_name}")
            return {
                "success": False,
                "error": "image_not_found",
                "message": f"Docker image '{image_name}' not found",
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
            }

        except docker.errors.APIError as e:
            logger.error(f"Docker API error: {e}")
            return {
                "success": False,
                "error": "docker_api_error",
                "message": str(e),
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
            }

    async def validate_codebase(
        self,
        codebase: Dict[str, Any],
        language: str = "python"
    ) -> Dict[str, Any]:
        """
        Validate a complete codebase by running its tests.

        Args:
            codebase: Dict with code structure
                - files: Dict[str, str] - file paths to content
                - requirements: List[str] - dependencies
                - test_command: str - command to run tests
            language: Programming language (currently only "python" supported)

        Returns:
            Validation result dict
        """
        if language != "python":
            return {
                "success": False,
                "error": "unsupported_language",
                "message": f"Language '{language}' not yet supported for validation",
            }

        files = codebase.get("files", {})
        requirements = codebase.get("requirements", [])
        test_command = codebase.get("test_command", "pytest")

        if not files:
            return {
                "success": False,
                "error": "no_files",
                "message": "No files provided for validation",
            }

        logger.info(f"Validating codebase with {len(files)} files")

        result = await self.execute_python(
            code_files=files,
            requirements=requirements,
            test_command=test_command
        )

        # Enhance result with validation-specific info
        if result.get("success"):
            result["validation"] = {
                "passed": result.get("tests_passed", False),
                "files_count": len(files),
                "dependencies_count": len(requirements),
            }

        return result

    async def run_security_scan(
        self,
        code_files: Dict[str, str],
        requirements: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Run security scan on code using bandit and safety.

        Args:
            code_files: Dict mapping file paths to content
            requirements: List of dependencies to scan

        Returns:
            Security scan results
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "docker_unavailable",
                "message": "Docker is not available",
            }

        # Add security scanning packages
        scan_requirements = (requirements or []) + [
            "bandit[toml]",
            "safety",
        ]

        # Create scanning script
        scan_script = """#!/bin/bash
set -e

cd /workspace

# Install requirements
pip install -q -r requirements.txt

# Run bandit (SAST for Python)
echo "=== Running Bandit Security Scan ==="
bandit -r . -f json -o bandit_report.json || true
cat bandit_report.json

# Run safety (dependency vulnerability scan)
echo "=== Running Safety Dependency Scan ==="
safety check --json > safety_report.json || true
cat safety_report.json
"""

        # Add scan script to files
        all_files = {**code_files, "run.sh": scan_script}

        try:
            result = await self.execute_python(
                code_files=all_files,
                requirements=scan_requirements,
                test_command="/bin/bash run.sh"
            )

            # Parse scan results from stdout
            stdout = result.get("stdout", "")

            return {
                "success": result.get("success", False),
                "scan_output": stdout,
                "vulnerabilities_found": "CRITICAL" in stdout or "HIGH" in stdout,
            }

        except Exception as e:
            logger.error(f"Security scan error: {e}")
            return {
                "success": False,
                "error": str(e),
            }

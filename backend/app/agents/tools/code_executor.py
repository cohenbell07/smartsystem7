"""
Secure code execution tool with sandboxing and detailed logging.
"""

import logging
import os
import tempfile
import subprocess
import sys
from typing import Dict, Any, Optional
from pathlib import Path
import time

logger = logging.getLogger(__name__)


class CodeExecutor:
    """Tool for secure code execution with sandboxing."""

    def __init__(self, timeout: int = 30, max_output_size: int = 100000):
        """
        Initialize code executor.

        Args:
            timeout: Maximum execution time in seconds
            max_output_size: Maximum output size in bytes
        """
        self.timeout = timeout
        self.max_output_size = max_output_size

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute code securely.

        Supported actions:
        - python: Execute Python code
        - shell: Execute shell command (limited)
        - file: Execute code from file

        Args:
            inputs: Dict with 'action' and action-specific params:
                - code: Code string to execute
                - language: Programming language (python, shell, etc.)
                - args: Command-line arguments
                - env: Environment variables dict
                - working_dir: Working directory path

        Returns:
            Dict with execution results including stdout, stderr, exit_code, duration
        """
        action = inputs.get("action", "python")

        try:
            if action == "python":
                return await self._execute_python(
                    inputs.get("code", ""),
                    inputs.get("args", []),
                    inputs.get("env", {}),
                    inputs.get("working_dir")
                )
            elif action == "shell":
                return await self._execute_shell(
                    inputs.get("command", ""),
                    inputs.get("env", {}),
                    inputs.get("working_dir")
                )
            elif action == "file":
                return await self._execute_file(
                    inputs.get("file_path", ""),
                    inputs.get("args", []),
                    inputs.get("env", {}),
                )
            else:
                return {"error": f"Unknown action: {action}"}

        except Exception as e:
            logger.error(f"Code execution error: {e}", exc_info=True)
            return {"error": str(e), "success": False}

    async def _execute_python(
        self,
        code: str,
        args: list = None,
        env: dict = None,
        working_dir: str = None
    ) -> Dict[str, Any]:
        """Execute Python code in a secure sandbox."""
        if not code:
            return {"error": "No code provided", "success": False}

        args = args or []
        env_vars = os.environ.copy()
        if env:
            env_vars.update(env)

        # Create temporary file for code
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.py',
            delete=False,
            dir=working_dir
        ) as temp_file:
            temp_file.write(code)
            temp_path = temp_file.name

        try:
            # Build command
            cmd = [sys.executable, temp_path] + args

            # Execute with timeout and capture output
            start_time = time.time()

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env_vars,
                cwd=working_dir,
            )

            duration = time.time() - start_time

            # Limit output size
            stdout = result.stdout[:self.max_output_size] if result.stdout else ""
            stderr = result.stderr[:self.max_output_size] if result.stderr else ""

            # Check if output was truncated
            stdout_truncated = len(result.stdout) > self.max_output_size if result.stdout else False
            stderr_truncated = len(result.stderr) > self.max_output_size if result.stderr else False

            logger.info(
                f"Python code executed: exit_code={result.returncode}, "
                f"duration={duration:.2f}s, stdout_len={len(stdout)}, stderr_len={len(stderr)}"
            )

            return {
                "success": result.returncode == 0,
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "duration": duration,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
            }

        except subprocess.TimeoutExpired:
            logger.error(f"Python code execution timeout after {self.timeout}s")
            return {
                "success": False,
                "error": f"Execution timeout after {self.timeout} seconds",
                "timeout": True,
            }

        except Exception as e:
            logger.error(f"Python execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
            }

        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_path}: {e}")

    async def _execute_shell(
        self,
        command: str,
        env: dict = None,
        working_dir: str = None
    ) -> Dict[str, Any]:
        """Execute shell command with restrictions."""
        if not command:
            return {"error": "No command provided", "success": False}

        # Blacklist dangerous commands
        dangerous_commands = [
            'rm -rf /',
            'mkfs',
            'dd if=/dev/zero',
            ':(){:|:&};:',  # Fork bomb
            'chmod -R 777 /',
            'chown -R',
        ]

        for dangerous in dangerous_commands:
            if dangerous in command:
                logger.warning(f"Blocked dangerous command: {command}")
                return {
                    "success": False,
                    "error": f"Dangerous command blocked: contains '{dangerous}'"
                }

        env_vars = os.environ.copy()
        if env:
            env_vars.update(env)

        try:
            start_time = time.time()

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env_vars,
                cwd=working_dir,
            )

            duration = time.time() - start_time

            stdout = result.stdout[:self.max_output_size] if result.stdout else ""
            stderr = result.stderr[:self.max_output_size] if result.stderr else ""

            logger.info(
                f"Shell command executed: '{command[:50]}...', "
                f"exit_code={result.returncode}, duration={duration:.2f}s"
            )

            return {
                "success": result.returncode == 0,
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "duration": duration,
                "command": command,
            }

        except subprocess.TimeoutExpired:
            logger.error(f"Shell command timeout: {command}")
            return {
                "success": False,
                "error": f"Command timeout after {self.timeout} seconds",
                "timeout": True,
            }

        except Exception as e:
            logger.error(f"Shell execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
            }

    async def _execute_file(
        self,
        file_path: str,
        args: list = None,
        env: dict = None,
    ) -> Dict[str, Any]:
        """Execute code from a file."""
        if not file_path:
            return {"error": "No file path provided", "success": False}

        path = Path(file_path)
        if not path.exists():
            return {"error": f"File not found: {file_path}", "success": False}

        if not path.is_file():
            return {"error": f"Not a file: {file_path}", "success": False}

        # Read file content
        try:
            with open(path, 'r') as f:
                code = f.read()
        except Exception as e:
            return {"error": f"Failed to read file: {e}", "success": False}

        # Determine language based on extension
        suffix = path.suffix.lower()

        if suffix == '.py':
            return await self._execute_python(
                code,
                args=args,
                env=env,
                working_dir=str(path.parent)
            )
        elif suffix in ['.sh', '.bash']:
            return await self._execute_shell(
                f"bash {file_path}",
                env=env,
                working_dir=str(path.parent)
            )
        else:
            return {
                "error": f"Unsupported file type: {suffix}",
                "success": False
            }

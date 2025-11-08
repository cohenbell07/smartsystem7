"""
Enhanced Coding Orchestrator with Docker Validation, GitHub & Vercel Deployment.

This module extends the base CodingOrchestrator with:
- Model Router integration for intelligent LLM selection
- Docker-based execution validation
- Automatic GitHub repository creation
- Automatic Vercel deployment
- Memory DB integration for build history tracking
"""

import logging
import json
from typing import Dict, Any, Optional
import re
import uuid
import time

from .coding_orchestrator import CodingOrchestrator

logger = logging.getLogger(__name__)


class EnhancedCodingOrchestrator(CodingOrchestrator):
    """
    Enhanced Coding Orchestrator with deployment capabilities.

    Extends the base orchestrator with:
    - Multi-model routing
    - Docker validation
    - GitHub integration
    - Vercel deployment
    """

    def __init__(
        self,
        llm_router,
        tools: Dict[str, Any],
        vector_memory,
        config=None,
        model_router=None,
        docker_executor=None,
        github_client=None,
        vercel_client=None,
        memory_db=None
    ):
        """
        Initialize enhanced orchestrator.

        Args:
            llm_router: Base LLM router
            tools: Available tools
            vector_memory: Memory system
            config: Application config
            model_router: Model router for intelligent routing
            docker_executor: Docker executor for validation
            github_client: GitHub client for repo creation
            vercel_client: Vercel client for deployment
            memory_db: Memory DB for build history tracking
        """
        super().__init__(llm_router, tools, vector_memory)

        self.config = config
        self.model_router = model_router
        self.docker_executor = docker_executor
        self.github_client = github_client
        self.vercel_client = vercel_client
        self.memory_db = memory_db

        logger.info("Enhanced Coding Orchestrator initialized")

    async def validate_with_docker(
        self,
        build_outputs: Dict[str, Any],
        requirements: Dict[str, Any],
        log_callback=None
    ) -> Dict[str, Any]:
        """
        Validate build using Docker executor.

        Args:
            build_outputs: Build outputs from coders
            requirements: Build requirements
            log_callback: Optional logging callback

        Returns:
            Validation result with runtime test results
        """
        if not self.docker_executor or not self.docker_executor.is_available():
            if log_callback:
                await log_callback("⚠️  Docker validation skipped (Docker not available)")
            return {
                "docker_validation": "skipped",
                "reason": "docker_unavailable"
            }

        try:
            if log_callback:
                await log_callback("\n🐳 Running Docker validation...")

            # Extract code files from build outputs
            code_files = self._extract_code_files(build_outputs)

            if not code_files:
                if log_callback:
                    await log_callback("   No code files to validate")
                return {
                    "docker_validation": "skipped",
                    "reason": "no_code_files"
                }

            # Extract requirements
            python_requirements = self._extract_python_requirements(build_outputs)

            # Run validation
            result = await self.docker_executor.execute_python(
                code_files=code_files,
                requirements=python_requirements,
                test_command="pytest -v || python -m pytest -v || echo 'No tests found'"
            )

            if log_callback:
                if result.get("success") and result.get("tests_passed"):
                    await log_callback("   ✅ Docker validation passed!")
                elif result.get("success"):
                    await log_callback("   ⚠️  Docker execution completed but tests failed")
                else:
                    await log_callback(f"   ❌ Docker validation failed: {result.get('error', 'unknown')}")

            return {
                "docker_validation": "completed",
                "success": result.get("success", False),
                "tests_passed": result.get("tests_passed", False),
                "exit_code": result.get("exit_code"),
                "stdout": result.get("stdout", "")[:500],  # Truncate for storage
                "stderr": result.get("stderr", "")[:500],
            }

        except Exception as e:
            logger.error(f"Docker validation error: {e}")
            if log_callback:
                await log_callback(f"   ❌ Docker validation error: {e}")
            return {
                "docker_validation": "error",
                "error": str(e)
            }

    def _extract_code_files(self, build_outputs: Dict[str, Any]) -> Dict[str, str]:
        """Extract code files from build outputs."""
        files = {}

        # Look for file patterns in outputs
        for coder, output in build_outputs.items():
            if not isinstance(output, dict) or not output.get("success"):
                continue

            content = output.get("output", "")

            # Extract code blocks with filenames
            # Pattern: ```filename or ```python:filename
            pattern = r'```(?:python:|javascript:|typescript:)?([^\n]+)\n(.*?)```'
            matches = re.findall(pattern, content, re.DOTALL)

            for filename, code in matches:
                filename = filename.strip()
                # Skip if it looks like a language specifier
                if filename.lower() in ['python', 'javascript', 'typescript', 'bash', 'json', 'yaml']:
                    continue

                if '/' in filename or '.' in filename:
                    files[filename] = code.strip()

        return files

    def _extract_python_requirements(self, build_outputs: Dict[str, Any]) -> list[str]:
        """Extract Python requirements from build outputs."""
        requirements = set()

        for coder, output in build_outputs.items():
            if not isinstance(output, dict) or not output.get("success"):
                continue

            content = output.get("output", "")

            # Look for requirements.txt content
            req_pattern = r'requirements\.txt[:\n]+((?:[^\n]+\n?)+)'
            matches = re.findall(req_pattern, content, re.MULTILINE)

            for match in matches:
                for line in match.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('#'):
                        requirements.add(line)

            # Also look for pip install commands
            pip_pattern = r'pip install ([\w\-\[\]>=<,. ]+)'
            pip_matches = re.findall(pip_pattern, content)
            for match in pip_matches:
                for pkg in match.split():
                    if pkg and pkg not in ['install', '-r', 'requirements.txt']:
                        requirements.add(pkg)

        return list(requirements)

    async def deploy_to_github_and_vercel(
        self,
        run_id: str,
        project_name: str,
        build_outputs: Dict[str, Any],
        log_callback=None
    ) -> Dict[str, Any]:
        """
        Deploy build to GitHub and Vercel.

        Args:
            run_id: Unique run identifier
            project_name: Project name
            build_outputs: Build outputs with code
            log_callback: Optional logging callback

        Returns:
            Deployment result with URLs
        """
        deployment_result = {}

        # Extract code files
        code_files = self._extract_code_files(build_outputs)

        if not code_files:
            if log_callback:
                await log_callback("   ⚠️  No code files to deploy")
            return {
                "deployment": "skipped",
                "reason": "no_code_files"
            }

        # Step 1: Deploy to GitHub
        if self.github_client and self.github_client.is_available():
            try:
                if log_callback:
                    await log_callback("\n📦 Creating GitHub repository...")

                github_result = await self.github_client.create_and_push_repository(
                    run_id=run_id,
                    project_slug=project_name.lower().replace(' ', '-'),
                    code_files=code_files,
                    description=f"AI-generated codebase from SmartSystem (Run #{run_id})",
                    private=True
                )

                if github_result.get("success"):
                    repo_url = github_result["repo_url"]
                    deployment_result["github_deployed"] = True
                    deployment_result["repo_url"] = repo_url

                    if log_callback:
                        await log_callback(f"   ✅ GitHub repository created: {repo_url}")
                else:
                    if log_callback:
                        await log_callback(f"   ❌ GitHub deployment failed: {github_result.get('message', 'unknown')}")
                    deployment_result["github_deployed"] = False
                    deployment_result["github_error"] = github_result.get("message", "unknown")

            except Exception as e:
                logger.error(f"GitHub deployment error: {e}")
                if log_callback:
                    await log_callback(f"   ❌ GitHub deployment error: {e}")
                deployment_result["github_deployed"] = False
                deployment_result["github_error"] = str(e)
        else:
            if log_callback:
                await log_callback("   ⚠️  GitHub deployment skipped (not configured)")
            deployment_result["github_deployed"] = False
            deployment_result["github_skipped"] = True

        # Step 2: Deploy to Vercel (only if GitHub succeeded)
        if deployment_result.get("github_deployed") and deployment_result.get("repo_url"):
            if self.vercel_client and self.vercel_client.is_available():
                try:
                    if log_callback:
                        await log_callback("\n🚀 Deploying to Vercel...")

                    # Determine framework from code
                    framework = self._detect_framework(code_files)

                    # Extract repo name from URL
                    repo_url = deployment_result["repo_url"]
                    # Extract owner/repo from GitHub URL
                    repo_match = re.search(r'github\.com/([^/]+/[^/]+)', repo_url)
                    if repo_match:
                        github_repo = repo_match.group(1)

                        vercel_result = await self.vercel_client.create_project_and_deploy(
                            run_id=run_id,
                            project_slug=project_name.lower().replace(' ', '-'),
                            github_repo=github_repo,
                            framework=framework
                        )

                        if vercel_result.get("success"):
                            deployment_url = vercel_result.get("deployment_url")
                            deployment_result["vercel_deployed"] = True
                            deployment_result["vercel_url"] = deployment_url
                            deployment_result["vercel_project_url"] = vercel_result.get("project_url")

                            if log_callback:
                                await log_callback(f"   ✅ Vercel deployment initiated: {deployment_url}")
                        else:
                            if log_callback:
                                await log_callback(f"   ⚠️  Vercel deployment warning: {vercel_result.get('deployment_warning', 'unknown')}")
                            deployment_result["vercel_deployed"] = False
                            deployment_result["vercel_warning"] = vercel_result.get("deployment_warning")
                    else:
                        if log_callback:
                            await log_callback("   ❌ Could not extract GitHub repo from URL")
                        deployment_result["vercel_deployed"] = False

                except Exception as e:
                    logger.error(f"Vercel deployment error: {e}")
                    if log_callback:
                        await log_callback(f"   ❌ Vercel deployment error: {e}")
                    deployment_result["vercel_deployed"] = False
                    deployment_result["vercel_error"] = str(e)
            else:
                if log_callback:
                    await log_callback("   ⚠️  Vercel deployment skipped (not configured)")
                deployment_result["vercel_deployed"] = False
                deployment_result["vercel_skipped"] = True

        return deployment_result

    def _detect_framework(self, code_files: Dict[str, str]) -> str:
        """Detect framework from code files."""
        # Check for Next.js
        if any('next' in f.lower() for f in code_files.keys()):
            return "nextjs"

        # Check for package.json
        for path, content in code_files.items():
            if 'package.json' in path.lower():
                if 'next' in content.lower():
                    return "nextjs"
                if 'react' in content.lower():
                    return "react"
                if 'vue' in content.lower():
                    return "vue"

        # Default to Next.js for modern projects
        return "nextjs"

    async def orchestrate_build_enhanced(
        self,
        user_prompt: str,
        project_context: Optional[Dict[str, Any]] = None,
        log_callback=None,
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Enhanced orchestration with validation and deployment.

        This extends the base orchestrate_build with:
        - Docker validation
        - GitHub repository creation
        - Vercel deployment
        - Memory DB logging

        Args:
            user_prompt: What to build
            project_context: Additional context
            log_callback: Logging callback
            run_id: Optional run ID for tracking

        Returns:
            Complete build result with deployment URLs
        """
        # Track build duration
        start_time = time.time()

        # Run base orchestration
        result = await self.orchestrate_build(
            user_prompt=user_prompt,
            project_context=project_context,
            log_callback=log_callback
        )

        if result.get("status") != "completed":
            # Save failed build to memory DB
            if self.memory_db and run_id:
                duration_sec = time.time() - start_time
                await self.memory_db.save_build(
                    run_id=run_id,
                    prompt=user_prompt,
                    quality=0.0,
                    model_map={},
                    duration_sec=duration_sec,
                    status="failed",
                    error=result.get("error", "Unknown error")
                )
            return result

        # Get build outputs
        build_outputs = result.get("outputs", {})
        requirements = result.get("requirements", {})
        final_score = result.get("final_score", 0.0)

        # Only proceed with validation/deployment if quality is acceptable
        if final_score < 0.7:  # 70% threshold for deployment
            if log_callback:
                await log_callback(f"\n⚠️  Quality score too low ({final_score:.2%}) - skipping deployment")
            result["deployment_skipped"] = True
            result["deployment_skip_reason"] = f"quality_too_low ({final_score:.2%})"

            # Save to memory DB (without deployment)
            if self.memory_db and run_id:
                duration_sec = time.time() - start_time
                await self.memory_db.save_build(
                    run_id=run_id,
                    prompt=user_prompt,
                    quality=final_score,
                    model_map=result.get("model_usage", {}),
                    duration_sec=duration_sec,
                    status="completed",
                    requirements=requirements,
                    iterations=result.get("iterations", 1)
                )

            return result

        # Step 1: Docker validation
        docker_result = await self.validate_with_docker(
            build_outputs=build_outputs,
            requirements=requirements,
            log_callback=log_callback
        )
        result["docker_validation"] = docker_result

        # Step 2: Deploy to GitHub + Vercel
        if run_id is None:
            run_id = str(uuid.uuid4())

        project_name = requirements.get("project_name", "ai-generated-project")

        deployment_result = await self.deploy_to_github_and_vercel(
            run_id=run_id,
            project_name=project_name,
            build_outputs=build_outputs,
            log_callback=log_callback
        )

        result["deployment"] = deployment_result

        # Add URLs to outputs for frontend display
        if not isinstance(result.get("outputs"), dict):
            result["outputs"] = {}

        if deployment_result.get("repo_url"):
            result["outputs"]["repo_url"] = deployment_result["repo_url"]

        if deployment_result.get("vercel_url"):
            result["outputs"]["vercel_url"] = deployment_result["vercel_url"]

        if deployment_result.get("vercel_project_url"):
            result["outputs"]["vercel_project_url"] = deployment_result["vercel_project_url"]

        # Quality metrics
        result["outputs"]["quality"] = final_score

        # Save build to memory DB
        if self.memory_db:
            duration_sec = time.time() - start_time
            await self.memory_db.save_build(
                run_id=run_id,
                prompt=user_prompt,
                quality=final_score,
                model_map=result.get("model_usage", {}),
                duration_sec=duration_sec,
                status="completed",
                repo_url=deployment_result.get("repo_url"),
                vercel_url=deployment_result.get("vercel_url"),
                requirements=requirements,
                iterations=result.get("iterations", 1),
                docker_validated=docker_result.get("success", False),
                github_deployed=deployment_result.get("github_deployed", False),
                vercel_deployed=deployment_result.get("vercel_deployed", False)
            )

            if log_callback:
                await log_callback("\n💾 Build saved to memory database")

        if log_callback:
            await log_callback("\n✨ Enhanced orchestration complete!")
            if deployment_result.get("repo_url"):
                await log_callback(f"   📦 GitHub: {deployment_result['repo_url']}")
            if deployment_result.get("vercel_url"):
                await log_callback(f"   🚀 Vercel: {deployment_result['vercel_url']}")

        return result

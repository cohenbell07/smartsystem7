"""
Vercel Client: Automated Deployment to Vercel

Handles:
- Creating Vercel projects
- Linking GitHub repositories
- Triggering deployments
- Getting deployment status
"""

import logging
import asyncio
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)


class VercelClient:
    """
    Client for Vercel deployment operations.

    Automates project creation, GitHub linking, and deployments.
    """

    API_BASE_URL = "https://api.vercel.com"

    def __init__(self, config):
        """
        Initialize Vercel client.

        Args:
            config: Application config with Vercel settings
        """
        self.config = config
        self.token = config.VERCEL_TOKEN
        self.team_id = config.VERCEL_TEAM_ID

        if not self.is_available():
            logger.warning("Vercel token not configured")

    def is_available(self) -> bool:
        """Check if Vercel client is configured."""
        return bool(self.token)

    def _get_headers(self) -> Dict[str, str]:
        """Get API request headers."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _get_api_url(self, endpoint: str) -> str:
        """
        Build API URL with optional team ID.

        Args:
            endpoint: API endpoint path

        Returns:
            Full API URL
        """
        url = f"{self.API_BASE_URL}{endpoint}"

        # Add team ID if configured
        if self.team_id:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}teamId={self.team_id}"

        return url

    async def create_project(
        self,
        name: str,
        github_repo: str,
        framework: Optional[str] = None,
        build_command: Optional[str] = None,
        output_directory: Optional[str] = None,
        install_command: Optional[str] = None,
        root_directory: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a Vercel project linked to GitHub repository.

        Args:
            name: Project name (will be prefixed with config.VERCEL_PROJECT_PREFIX)
            github_repo: GitHub repository (owner/repo format)
            framework: Framework preset (nextjs, react, vue, etc.)
            build_command: Custom build command
            output_directory: Output directory for built files
            install_command: Custom install command
            root_directory: Root directory of the project

        Returns:
            Dict with project info:
            - success: bool
            - project_id: str
            - project_url: str
            - error: str (if failed)
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "vercel_not_configured",
                "message": "Vercel token not configured",
            }

        # Add prefix to name
        full_name = f"{self.config.VERCEL_PROJECT_PREFIX}{name}"

        try:
            logger.info(f"Creating Vercel project: {full_name}")

            # Parse GitHub repo
            if "/" not in github_repo:
                raise ValueError(f"Invalid GitHub repo format: {github_repo}")

            repo_owner, repo_name = github_repo.split("/", 1)

            # Build project payload
            payload = {
                "name": full_name,
                "gitRepository": {
                    "type": "github",
                    "repo": github_repo,
                }
            }

            # Add optional framework settings
            if framework or build_command or output_directory or install_command or root_directory:
                payload["framework"] = framework

                build_settings = {}
                if build_command:
                    build_settings["buildCommand"] = build_command
                if output_directory:
                    build_settings["outputDirectory"] = output_directory
                if install_command:
                    build_settings["installCommand"] = install_command
                if root_directory:
                    build_settings["rootDirectory"] = root_directory

                if build_settings:
                    payload["buildCommand"] = build_command
                    payload["outputDirectory"] = output_directory
                    payload["installCommand"] = install_command
                    payload["rootDirectory"] = root_directory

            # Create project via API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._get_api_url("/v9/projects"),
                    headers=self._get_headers(),
                    json=payload,
                    timeout=30.0
                )

                if response.status_code == 200 or response.status_code == 201:
                    data = response.json()
                    project_id = data.get("id")
                    project_name = data.get("name")

                    logger.info(f"Vercel project created: {project_name} ({project_id})")

                    return {
                        "success": True,
                        "project_id": project_id,
                        "project_name": project_name,
                        "project_url": f"https://vercel.com/{repo_owner}/{project_name}",
                    }
                else:
                    error_msg = response.json().get("error", {}).get("message", "Unknown error")
                    logger.error(f"Vercel project creation failed: {error_msg}")
                    return {
                        "success": False,
                        "error": "creation_failed",
                        "message": error_msg,
                        "status_code": response.status_code,
                    }

        except Exception as e:
            logger.error(f"Failed to create Vercel project: {e}")
            return {
                "success": False,
                "error": "creation_failed",
                "message": str(e),
            }

    async def trigger_deployment(
        self,
        project_name: str,
        github_repo: str,
        target: str = "production"
    ) -> Dict[str, Any]:
        """
        Trigger a deployment for a project.

        Args:
            project_name: Vercel project name
            github_repo: GitHub repository (owner/repo)
            target: Deployment target ("production" or "preview")

        Returns:
            Dict with deployment info
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "vercel_not_configured",
            }

        try:
            logger.info(f"Triggering Vercel deployment for {project_name}")

            payload = {
                "name": project_name,
                "gitSource": {
                    "type": "github",
                    "repo": github_repo,
                    "ref": "main",  # Deploy from main branch
                },
                "target": target,
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._get_api_url("/v13/deployments"),
                    headers=self._get_headers(),
                    json=payload,
                    timeout=30.0
                )

                if response.status_code == 200 or response.status_code == 201:
                    data = response.json()
                    deployment_id = data.get("id")
                    deployment_url = data.get("url")

                    logger.info(f"Deployment triggered: {deployment_url}")

                    return {
                        "success": True,
                        "deployment_id": deployment_id,
                        "deployment_url": f"https://{deployment_url}",
                        "status": data.get("readyState", "QUEUED"),
                    }
                else:
                    error_msg = response.json().get("error", {}).get("message", "Unknown error")
                    logger.error(f"Deployment trigger failed: {error_msg}")
                    return {
                        "success": False,
                        "error": "deployment_failed",
                        "message": error_msg,
                        "status_code": response.status_code,
                    }

        except Exception as e:
            logger.error(f"Failed to trigger deployment: {e}")
            return {
                "success": False,
                "error": "deployment_failed",
                "message": str(e),
            }

    async def get_deployment_status(
        self,
        deployment_id: str
    ) -> Dict[str, Any]:
        """
        Get deployment status.

        Args:
            deployment_id: Vercel deployment ID

        Returns:
            Dict with deployment status
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "vercel_not_configured",
            }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self._get_api_url(f"/v13/deployments/{deployment_id}"),
                    headers=self._get_headers(),
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()

                    return {
                        "success": True,
                        "deployment_id": deployment_id,
                        "status": data.get("readyState", "UNKNOWN"),
                        "url": f"https://{data.get('url', '')}",
                        "created_at": data.get("createdAt"),
                    }
                else:
                    return {
                        "success": False,
                        "error": "status_fetch_failed",
                        "status_code": response.status_code,
                    }

        except Exception as e:
            logger.error(f"Failed to get deployment status: {e}")
            return {
                "success": False,
                "error": "status_fetch_failed",
                "message": str(e),
            }

    async def create_project_and_deploy(
        self,
        run_id: str,
        project_slug: str,
        github_repo: str,
        framework: Optional[str] = "nextjs"
    ) -> Dict[str, Any]:
        """
        Create project and trigger initial deployment (all-in-one).

        Args:
            run_id: Unique run identifier
            project_slug: Project name slug
            github_repo: GitHub repository (owner/repo)
            framework: Framework preset

        Returns:
            Dict with complete result including deployment URL
        """
        # Generate project name
        project_name_suffix = f"{project_slug}-{run_id[:8]}"

        # Step 1: Create project
        create_result = await self.create_project(
            name=project_name_suffix,
            github_repo=github_repo,
            framework=framework
        )

        if not create_result.get("success"):
            return create_result

        project_name = create_result["project_name"]

        # Step 2: Trigger deployment
        # Note: Vercel automatically deploys when project is created from GitHub
        # But we can trigger explicitly to ensure deployment happens
        deploy_result = await self.trigger_deployment(
            project_name=project_name,
            github_repo=github_repo,
            target="production"
        )

        if not deploy_result.get("success"):
            logger.warning(f"Project created but deployment trigger failed: {project_name}")
            return {
                "success": True,  # Project creation succeeded
                "project_id": create_result["project_id"],
                "project_url": create_result["project_url"],
                "deployment_warning": "Deployment trigger failed, but auto-deploy should occur",
            }

        logger.info(f"Successfully created project and triggered deployment: {project_name}")

        return {
            "success": True,
            "project_id": create_result["project_id"],
            "project_name": project_name,
            "project_url": create_result["project_url"],
            "deployment_id": deploy_result.get("deployment_id"),
            "deployment_url": deploy_result.get("deployment_url"),
        }

    async def get_project_info(self, project_id_or_name: str) -> Dict[str, Any]:
        """
        Get project information.

        Args:
            project_id_or_name: Project ID or name

        Returns:
            Project info dict
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "vercel_not_configured",
            }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self._get_api_url(f"/v9/projects/{project_id_or_name}"),
                    headers=self._get_headers(),
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()

                    return {
                        "success": True,
                        "project_id": data.get("id"),
                        "name": data.get("name"),
                        "framework": data.get("framework"),
                        "created_at": data.get("createdAt"),
                        "updated_at": data.get("updatedAt"),
                    }
                else:
                    return {
                        "success": False,
                        "error": "fetch_failed",
                        "status_code": response.status_code,
                    }

        except Exception as e:
            logger.error(f"Failed to get project info: {e}")
            return {
                "success": False,
                "error": "fetch_failed",
                "message": str(e),
            }

    async def delete_project(self, project_id_or_name: str) -> Dict[str, Any]:
        """
        Delete a Vercel project.

        Args:
            project_id_or_name: Project ID or name

        Returns:
            Deletion result dict
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "vercel_not_configured",
            }

        try:
            logger.warning(f"Deleting Vercel project: {project_id_or_name}")

            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    self._get_api_url(f"/v9/projects/{project_id_or_name}"),
                    headers=self._get_headers(),
                    timeout=30.0
                )

                if response.status_code == 200 or response.status_code == 204:
                    logger.info(f"Project deleted: {project_id_or_name}")

                    return {
                        "success": True,
                        "project_id": project_id_or_name,
                    }
                else:
                    return {
                        "success": False,
                        "error": "deletion_failed",
                        "status_code": response.status_code,
                    }

        except Exception as e:
            logger.error(f"Failed to delete project: {e}")
            return {
                "success": False,
                "error": "deletion_failed",
                "message": str(e),
            }

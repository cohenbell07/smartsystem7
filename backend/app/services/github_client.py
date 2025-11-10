"""
GitHub Client: Automated Repository Creation and Management

Handles:
- Creating new repositories
- Committing and pushing code
- Managing repository settings
"""

import logging
import tempfile
import shutil
from typing import Dict, Any, Optional, List
from pathlib import Path
import asyncio

logger = logging.getLogger(__name__)


class GitHubClient:
    """
    Client for GitHub repository operations.

    Automates repository creation, code commits, and deployment setup.
    """

    def __init__(self, config):
        """
        Initialize GitHub client.

        Args:
            config: Application config with GitHub settings
        """
        self.config = config
        self.token = config.GITHUB_TOKEN
        self.github = None
        self.user = None
        self.org = None
        self.owner_login: Optional[str] = None

        self._init_client()

    def _init_client(self):
        """Initialize PyGithub client."""
        if not self.config.is_github_configured():
            logger.warning("GitHub token not configured")
            return

        try:
            from github import Github

            self.github = Github(self.token)
            self.user = self.github.get_user()
            self.owner_login = self.user.login if self.user else None

            configured_owner = getattr(self.config, "GITHUB_OWNER", None)
            if configured_owner and self.user and configured_owner != self.user.login:
                try:
                    self.org = self.github.get_organization(configured_owner)
                    self.owner_login = configured_owner
                    logger.info("GitHub client initialized for organization: %s", configured_owner)
                except Exception as exc:
                    logger.warning("Unable to access configured GitHub owner '%s': %s", configured_owner, exc)
                    logger.info(f"GitHub client initialized for user: {self.user.login}")
            else:
                logger.info(f"GitHub client initialized for user: {self.user.login}")
        except Exception as e:
            logger.error(f"Failed to initialize GitHub client: {e}")
            self.github = None

    def is_available(self) -> bool:
        """Check if GitHub client is available."""
        return self.github is not None

    def get_token_scopes(self) -> list[str]:
        """Return the scopes associated with the configured PAT."""
        if not self.token:
            return []

        try:
            import requests

            response = requests.get(
                "https://api.github.com/rate_limit",
                headers={"Authorization": f"token {self.token}"},
                timeout=10,
            )
            response.raise_for_status()
            scopes_header = response.headers.get("X-OAuth-Scopes", "")
            scopes = [scope.strip() for scope in scopes_header.split(",") if scope.strip()]
            logger.info("GitHub token scopes: %s", scopes)
            return scopes
        except Exception as exc:
            logger.error("Failed to retrieve GitHub token scopes: %s", exc)
            return []

    def validate_scopes(self, required_scopes: list[str]) -> Dict[str, Any]:
        """Validate that token includes required scopes."""
        scopes = set(self.get_token_scopes())
        missing = [scope for scope in required_scopes if scope not in scopes]
        return {
            "valid": not missing,
            "scopes": list(scopes),
            "missing": missing,
        }

    async def create_repository(
        self,
        name: str,
        description: str = "",
        private: bool = True,
        auto_init: bool = False
    ) -> Dict[str, Any]:
        """
        Create a new GitHub repository.

        Args:
            name: Repository name (will be prefixed with config.GITHUB_REPO_PREFIX)
            description: Repository description
            private: Whether repository should be private
            auto_init: Whether to initialize with README

        Returns:
            Dict with repository info:
            - success: bool
            - repo_url: str (HTML URL)
            - clone_url: str (Git URL)
            - repo_name: str
            - error: str (if failed)
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "github_not_configured",
                "message": "GitHub client not configured",
            }

        # Add prefix to name
        full_name = f"{self.config.GITHUB_REPO_PREFIX}{name}"

        try:
            logger.info(f"Creating GitHub repository: {full_name}")

            # Run in thread pool (PyGithub is sync)
            loop = asyncio.get_event_loop()

            def _create_repo():
                owner = self.org if self.org is not None else self.user
                if owner is None:
                    raise RuntimeError("GitHub owner context not available")
                return owner.create_repo(
                    name=full_name,
                    description=description,
                    private=private,
                    auto_init=auto_init,
                )

            repo = await loop.run_in_executor(None, _create_repo)

            logger.info(f"Repository created: {repo.html_url}")

            return {
                "success": True,
                "repo_url": repo.html_url,
                "clone_url": repo.clone_url,
                "git_url": repo.git_url,
                "ssh_url": repo.ssh_url,
                "repo_name": repo.full_name,
                "owner": repo.owner.login,
            }

        except Exception as e:
            logger.error(f"Failed to create repository: {e}")
            return {
                "success": False,
                "error": "creation_failed",
                "message": str(e),
            }

    async def push_code_to_repo(
        self,
        repo_name: str,
        code_files: Dict[str, str],
        commit_message: str = "Initial commit from SmartSystem AI",
        branch: str = "main"
    ) -> Dict[str, Any]:
        """
        Push code files to a GitHub repository.

        Args:
            repo_name: Full repository name (owner/repo)
            code_files: Dict mapping file paths to content
            commit_message: Commit message
            branch: Branch name (default: "main")

        Returns:
            Dict with push result
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "github_not_configured",
            }

        try:
            logger.info(f"Pushing {len(code_files)} files to {repo_name}")

            # Get repository
            loop = asyncio.get_event_loop()
            repo = await loop.run_in_executor(
                None,
                lambda: self.github.get_repo(repo_name)
            )

            # Create or update files
            for file_path, content in code_files.items():
                try:
                    # Try to get existing file
                    try:
                        existing_file = await loop.run_in_executor(
                            None,
                            lambda: repo.get_contents(file_path, ref=branch)
                        )
                        # Update existing file
                        await loop.run_in_executor(
                            None,
                            lambda: repo.update_file(
                                path=file_path,
                                message=commit_message,
                                content=content,
                                sha=existing_file.sha,
                                branch=branch
                            )
                        )
                        logger.debug(f"Updated file: {file_path}")
                    except:
                        # File doesn't exist, create it
                        await loop.run_in_executor(
                            None,
                            lambda: repo.create_file(
                                path=file_path,
                                message=commit_message,
                                content=content,
                                branch=branch
                            )
                        )
                        logger.debug(f"Created file: {file_path}")

                except Exception as e:
                    logger.warning(f"Failed to create/update file {file_path}: {e}")

            logger.info(f"Successfully pushed code to {repo_name}")

            return {
                "success": True,
                "repo_url": repo.html_url,
                "commit_count": len(code_files),
            }

        except Exception as e:
            logger.error(f"Failed to push code: {e}")
            return {
                "success": False,
                "error": "push_failed",
                "message": str(e),
            }

    async def create_and_push_repository(
        self,
        run_id: str,
        project_slug: str,
        code_files: Dict[str, str],
        description: str = "AI-generated codebase from SmartSystem",
        private: bool = True
    ) -> Dict[str, Any]:
        """
        Create a new repository and push code to it (all-in-one).

        Args:
            run_id: Unique run identifier
            project_slug: Project name slug
            code_files: Dict mapping file paths to content
            description: Repository description
            private: Whether repository should be private

        Returns:
            Dict with complete result including repo URL
        """
        # Generate unique repository name
        repo_name_suffix = f"{project_slug}-{run_id[:8]}"

        # Step 1: Create repository
        create_result = await self.create_repository(
            name=repo_name_suffix,
            description=description,
            private=private,
            auto_init=False  # We'll push code ourselves
        )

        if not create_result.get("success"):
            return create_result

        repo_full_name = create_result["repo_name"]
        repo_url = create_result["repo_url"]

        # Step 2: Push code
        push_result = await self.push_code_to_repo(
            repo_name=repo_full_name,
            code_files=code_files,
            commit_message="Initial commit: AI-generated codebase"
        )

        if not push_result.get("success"):
            logger.warning(f"Repository created but push failed: {repo_url}")
            return {
                "success": False,
                "error": "push_failed",
                "repo_url": repo_url,
                "message": f"Repository created at {repo_url} but failed to push code",
            }

        logger.info(f"Successfully created and populated repository: {repo_url}")

        return {
            "success": True,
            "repo_url": repo_url,
            "repo_name": repo_full_name,
            "clone_url": create_result["clone_url"],
            "files_pushed": len(code_files),
        }

    async def update_repository_settings(
        self,
        repo_name: str,
        settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update repository settings.

        Args:
            repo_name: Full repository name (owner/repo)
            settings: Dict of settings to update
                - description: str
                - homepage: str
                - private: bool
                - has_issues: bool
                - has_wiki: bool
                - has_downloads: bool

        Returns:
            Update result dict
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "github_not_configured",
            }

        try:
            loop = asyncio.get_event_loop()
            repo = await loop.run_in_executor(
                None,
                lambda: self.github.get_repo(repo_name)
            )

            # Update settings
            await loop.run_in_executor(
                None,
                lambda: repo.edit(**settings)
            )

            logger.info(f"Updated settings for {repo_name}")

            return {
                "success": True,
                "repo_name": repo_name,
            }

        except Exception as e:
            logger.error(f"Failed to update repository settings: {e}")
            return {
                "success": False,
                "error": "update_failed",
                "message": str(e),
            }

    async def get_repository_info(self, repo_name: str) -> Dict[str, Any]:
        """
        Get repository information.

        Args:
            repo_name: Full repository name (owner/repo)

        Returns:
            Repository info dict
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "github_not_configured",
            }

        try:
            loop = asyncio.get_event_loop()
            repo = await loop.run_in_executor(
                None,
                lambda: self.github.get_repo(repo_name)
            )

            return {
                "success": True,
                "name": repo.name,
                "full_name": repo.full_name,
                "description": repo.description,
                "html_url": repo.html_url,
                "clone_url": repo.clone_url,
                "private": repo.private,
                "created_at": repo.created_at.isoformat() if repo.created_at else None,
                "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
                "size": repo.size,
                "language": repo.language,
                "default_branch": repo.default_branch,
            }

        except Exception as e:
            logger.error(f"Failed to get repository info: {e}")
            return {
                "success": False,
                "error": "fetch_failed",
                "message": str(e),
            }

    async def delete_repository(self, repo_name: str) -> Dict[str, Any]:
        """
        Delete a repository.

        Args:
            repo_name: Full repository name (owner/repo)

        Returns:
            Deletion result dict
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "github_not_configured",
            }

        try:
            logger.warning(f"Deleting repository: {repo_name}")

            loop = asyncio.get_event_loop()
            repo = await loop.run_in_executor(
                None,
                lambda: self.github.get_repo(repo_name)
            )

            await loop.run_in_executor(
                None,
                lambda: repo.delete()
            )

            logger.info(f"Repository deleted: {repo_name}")

            return {
                "success": True,
                "repo_name": repo_name,
            }

        except Exception as e:
            logger.error(f"Failed to delete repository: {e}")
            return {
                "success": False,
                "error": "deletion_failed",
                "message": str(e),
            }

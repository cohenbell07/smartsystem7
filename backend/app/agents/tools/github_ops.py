"""
GitHub operations tool using PyGithub.
"""

import logging
import os
from typing import Dict, Any, Optional
from github import Github, GithubException

logger = logging.getLogger(__name__)


class GitHubTool:
    """Tool for GitHub operations."""

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.client = None

        if self.token:
            self.client = Github(self.token)
        else:
            logger.warning("GITHUB_TOKEN not set, GitHub operations will be limited")

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute GitHub action.

        Supported actions:
        - create_repo: Create new repository
        - create_issue: Create issue
        - create_pr: Create pull request
        - get_repo: Get repository info
        - list_repos: List user repositories

        Args:
            inputs: Dict with 'action' and action-specific params

        Returns:
            Dict with action result
        """
        if not self.client:
            return {"error": "GitHub client not initialized (missing token)"}

        action = inputs.get("action")

        try:
            if action == "create_repo":
                return self._create_repo(inputs.get("name"), inputs.get("description"), inputs.get("private", False))
            elif action == "create_issue":
                return self._create_issue(inputs.get("repo"), inputs.get("title"), inputs.get("body"))
            elif action == "create_pr":
                return self._create_pr(inputs.get("repo"), inputs.get("title"), inputs.get("body"), inputs.get("head"), inputs.get("base", "main"))
            elif action == "get_repo":
                return self._get_repo(inputs.get("repo"))
            elif action == "list_repos":
                return self._list_repos()
            else:
                return {"error": f"Unknown action: {action}"}

        except GithubException as e:
            logger.error(f"GitHub API error: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return {"error": str(e)}

    def _create_repo(self, name: str, description: str = "", private: bool = False) -> Dict[str, Any]:
        """Create a new repository."""
        user = self.client.get_user()
        repo = user.create_repo(name, description=description, private=private, auto_init=True)

        logger.info(f"Created repository: {repo.full_name}")
        return {
            "success": True,
            "repo": repo.full_name,
            "url": repo.html_url,
            "clone_url": repo.clone_url,
        }

    def _create_issue(self, repo_name: str, title: str, body: str = "") -> Dict[str, Any]:
        """Create an issue."""
        repo = self.client.get_repo(repo_name)
        issue = repo.create_issue(title=title, body=body)

        logger.info(f"Created issue #{issue.number} in {repo_name}")
        return {
            "success": True,
            "issue_number": issue.number,
            "url": issue.html_url,
        }

    def _create_pr(self, repo_name: str, title: str, body: str, head: str, base: str = "main") -> Dict[str, Any]:
        """Create a pull request."""
        repo = self.client.get_repo(repo_name)
        pr = repo.create_pull(title=title, body=body, head=head, base=base)

        logger.info(f"Created PR #{pr.number} in {repo_name}")
        return {
            "success": True,
            "pr_number": pr.number,
            "url": pr.html_url,
        }

    def _get_repo(self, repo_name: str) -> Dict[str, Any]:
        """Get repository information."""
        repo = self.client.get_repo(repo_name)

        return {
            "success": True,
            "name": repo.name,
            "full_name": repo.full_name,
            "description": repo.description,
            "url": repo.html_url,
            "stars": repo.stargazers_count,
            "forks": repo.forks_count,
            "language": repo.language,
        }

    def _list_repos(self) -> Dict[str, Any]:
        """List user repositories."""
        user = self.client.get_user()
        repos = user.get_repos()

        repo_list = []
        for repo in repos[:20]:  # Limit to 20
            repo_list.append({
                "name": repo.name,
                "full_name": repo.full_name,
                "url": repo.html_url,
                "private": repo.private,
            })

        logger.info(f"Listed {len(repo_list)} repositories")
        return {
            "success": True,
            "repos": repo_list,
        }

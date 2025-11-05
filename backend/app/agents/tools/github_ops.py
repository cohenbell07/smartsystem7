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
        - read_file: Read file content from repository
        - write_file: Write/update file in repository
        - delete_file: Delete file from repository
        - commit: Commit changes to repository
        - create_branch: Create new branch
        - list_branches: List repository branches
        - get_commits: Get recent commits
        - clone_repo: Clone repository locally

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
            elif action == "read_file":
                return self._read_file(inputs.get("repo"), inputs.get("path"), inputs.get("ref", "main"))
            elif action == "write_file":
                return self._write_file(
                    inputs.get("repo"),
                    inputs.get("path"),
                    inputs.get("content"),
                    inputs.get("message"),
                    inputs.get("branch", "main")
                )
            elif action == "delete_file":
                return self._delete_file(
                    inputs.get("repo"),
                    inputs.get("path"),
                    inputs.get("message"),
                    inputs.get("branch", "main")
                )
            elif action == "create_branch":
                return self._create_branch(inputs.get("repo"), inputs.get("branch"), inputs.get("from_branch", "main"))
            elif action == "list_branches":
                return self._list_branches(inputs.get("repo"))
            elif action == "get_commits":
                return self._get_commits(inputs.get("repo"), inputs.get("branch", "main"), inputs.get("limit", 10))
            elif action == "clone_repo":
                return await self._clone_repo(inputs.get("repo"), inputs.get("path"), inputs.get("branch"))
            else:
                return {"error": f"Unknown action: {action}"}

        except GithubException as e:
            logger.error(f"GitHub API error: {e}")
            return {"error": str(e), "success": False}
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return {"error": str(e), "success": False}

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

    def _read_file(self, repo_name: str, file_path: str, ref: str = "main") -> Dict[str, Any]:
        """Read file content from repository."""
        repo = self.client.get_repo(repo_name)

        try:
            file_content = repo.get_contents(file_path, ref=ref)

            # Handle if it's a list (directory)
            if isinstance(file_content, list):
                return {
                    "error": f"Path is a directory, not a file: {file_path}",
                    "success": False
                }

            # Decode content
            content = file_content.decoded_content.decode('utf-8')

            logger.info(f"Read file {file_path} from {repo_name} ({len(content)} chars)")
            return {
                "success": True,
                "content": content,
                "path": file_path,
                "sha": file_content.sha,
                "size": file_content.size,
                "encoding": file_content.encoding,
            }

        except Exception as e:
            logger.error(f"Failed to read file {file_path} from {repo_name}: {e}")
            return {
                "error": str(e),
                "success": False
            }

    def _write_file(
        self,
        repo_name: str,
        file_path: str,
        content: str,
        message: str = None,
        branch: str = "main"
    ) -> Dict[str, Any]:
        """Write or update file in repository."""
        if not content:
            return {"error": "No content provided", "success": False}

        repo = self.client.get_repo(repo_name)

        if not message:
            message = f"Update {file_path}"

        try:
            # Check if file exists
            try:
                existing_file = repo.get_contents(file_path, ref=branch)
                # Update existing file
                result = repo.update_file(
                    path=file_path,
                    message=message,
                    content=content,
                    sha=existing_file.sha,
                    branch=branch
                )
                operation = "updated"
            except:
                # Create new file
                result = repo.create_file(
                    path=file_path,
                    message=message,
                    content=content,
                    branch=branch
                )
                operation = "created"

            logger.info(f"{operation.capitalize()} file {file_path} in {repo_name}")
            return {
                "success": True,
                "operation": operation,
                "path": file_path,
                "commit_sha": result["commit"].sha,
                "commit_url": result["commit"].html_url,
            }

        except Exception as e:
            logger.error(f"Failed to write file {file_path} to {repo_name}: {e}")
            return {
                "error": str(e),
                "success": False
            }

    def _delete_file(
        self,
        repo_name: str,
        file_path: str,
        message: str = None,
        branch: str = "main"
    ) -> Dict[str, Any]:
        """Delete file from repository."""
        repo = self.client.get_repo(repo_name)

        if not message:
            message = f"Delete {file_path}"

        try:
            # Get file to get its SHA
            file_content = repo.get_contents(file_path, ref=branch)

            if isinstance(file_content, list):
                return {
                    "error": f"Path is a directory, not a file: {file_path}",
                    "success": False
                }

            # Delete file
            result = repo.delete_file(
                path=file_path,
                message=message,
                sha=file_content.sha,
                branch=branch
            )

            logger.info(f"Deleted file {file_path} from {repo_name}")
            return {
                "success": True,
                "path": file_path,
                "commit_sha": result["commit"].sha,
                "commit_url": result["commit"].html_url,
            }

        except Exception as e:
            logger.error(f"Failed to delete file {file_path} from {repo_name}: {e}")
            return {
                "error": str(e),
                "success": False
            }

    def _create_branch(self, repo_name: str, branch_name: str, from_branch: str = "main") -> Dict[str, Any]:
        """Create a new branch."""
        repo = self.client.get_repo(repo_name)

        try:
            # Get the source branch
            source_branch = repo.get_branch(from_branch)
            source_sha = source_branch.commit.sha

            # Create new branch
            ref = repo.create_git_ref(
                ref=f"refs/heads/{branch_name}",
                sha=source_sha
            )

            logger.info(f"Created branch {branch_name} in {repo_name} from {from_branch}")
            return {
                "success": True,
                "branch": branch_name,
                "sha": source_sha,
                "from_branch": from_branch,
            }

        except Exception as e:
            logger.error(f"Failed to create branch {branch_name} in {repo_name}: {e}")
            return {
                "error": str(e),
                "success": False
            }

    def _list_branches(self, repo_name: str) -> Dict[str, Any]:
        """List repository branches."""
        repo = self.client.get_repo(repo_name)

        try:
            branches = repo.get_branches()

            branch_list = []
            for branch in branches:
                branch_list.append({
                    "name": branch.name,
                    "sha": branch.commit.sha,
                    "protected": branch.protected,
                })

            logger.info(f"Listed {len(branch_list)} branches in {repo_name}")
            return {
                "success": True,
                "branches": branch_list,
                "count": len(branch_list),
            }

        except Exception as e:
            logger.error(f"Failed to list branches in {repo_name}: {e}")
            return {
                "error": str(e),
                "success": False
            }

    def _get_commits(self, repo_name: str, branch: str = "main", limit: int = 10) -> Dict[str, Any]:
        """Get recent commits."""
        repo = self.client.get_repo(repo_name)

        try:
            commits = repo.get_commits(sha=branch)

            commit_list = []
            for commit in commits[:limit]:
                commit_list.append({
                    "sha": commit.sha,
                    "message": commit.commit.message,
                    "author": commit.commit.author.name,
                    "date": commit.commit.author.date.isoformat(),
                    "url": commit.html_url,
                })

            logger.info(f"Retrieved {len(commit_list)} commits from {repo_name}/{branch}")
            return {
                "success": True,
                "commits": commit_list,
                "count": len(commit_list),
            }

        except Exception as e:
            logger.error(f"Failed to get commits from {repo_name}: {e}")
            return {
                "error": str(e),
                "success": False
            }

    async def _clone_repo(self, repo_name: str, local_path: str = None, branch: str = None) -> Dict[str, Any]:
        """Clone repository locally using git command."""
        import subprocess
        import tempfile
        from pathlib import Path

        repo = self.client.get_repo(repo_name)
        clone_url = repo.clone_url

        # Use authenticated clone URL if token available
        if self.token:
            clone_url = clone_url.replace("https://", f"https://{self.token}@")

        # Use temp directory if no path specified
        if not local_path:
            local_path = tempfile.mkdtemp(prefix="github_clone_")

        try:
            # Build git clone command
            cmd = ["git", "clone", clone_url, local_path]
            if branch:
                cmd.extend(["-b", branch])

            # Execute clone
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes timeout
            )

            if result.returncode != 0:
                logger.error(f"Git clone failed: {result.stderr}")
                return {
                    "success": False,
                    "error": f"Git clone failed: {result.stderr}",
                }

            logger.info(f"Cloned {repo_name} to {local_path}")
            return {
                "success": True,
                "repo": repo_name,
                "path": local_path,
                "branch": branch or "default",
                "url": repo.html_url,
            }

        except subprocess.TimeoutExpired:
            logger.error(f"Git clone timeout for {repo_name}")
            return {
                "success": False,
                "error": "Clone operation timeout after 5 minutes",
            }

        except Exception as e:
            logger.error(f"Failed to clone {repo_name}: {e}")
            return {
                "success": False,
                "error": str(e),
            }

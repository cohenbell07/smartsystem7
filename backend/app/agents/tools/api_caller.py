"""
Universal HTTP/JSON API caller with retry logic and comprehensive error handling.
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List
import aiohttp
from aiohttp import ClientTimeout, ClientError
import json

logger = logging.getLogger(__name__)


class APICaller:
    """Tool for making HTTP API calls with retry logic."""

    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        retry_backoff: float = 2.0,
    ):
        """
        Initialize API caller.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries in seconds
            retry_backoff: Backoff multiplier for retry delay
        """
        self.timeout = ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.retry_backoff = retry_backoff

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute HTTP request.

        Args:
            inputs: Dict with:
                - url: Target URL (required)
                - method: HTTP method (GET, POST, PUT, DELETE, PATCH) default: GET
                - headers: Dict of HTTP headers
                - params: Dict of query parameters
                - json: Dict to send as JSON body
                - data: Dict to send as form data
                - auth: Dict with username/password for basic auth
                - retry: Bool to enable retry logic (default: True)
                - verify_ssl: Bool to verify SSL certificates (default: True)

        Returns:
            Dict with response data including status, headers, body, etc.
        """
        url = inputs.get("url")
        if not url:
            return {"error": "No URL provided", "success": False}

        method = inputs.get("method", "GET").upper()
        headers = inputs.get("headers", {})
        params = inputs.get("params", {})
        json_data = inputs.get("json")
        form_data = inputs.get("data")
        auth = inputs.get("auth")
        enable_retry = inputs.get("retry", True)
        verify_ssl = inputs.get("verify_ssl", True)

        # Build auth
        auth_obj = None
        if auth and isinstance(auth, dict):
            username = auth.get("username")
            password = auth.get("password")
            if username and password:
                auth_obj = aiohttp.BasicAuth(username, password)

        # Make request with retry logic
        if enable_retry:
            return await self._request_with_retry(
                url=url,
                method=method,
                headers=headers,
                params=params,
                json_data=json_data,
                form_data=form_data,
                auth=auth_obj,
                verify_ssl=verify_ssl,
            )
        else:
            return await self._make_request(
                url=url,
                method=method,
                headers=headers,
                params=params,
                json_data=json_data,
                form_data=form_data,
                auth=auth_obj,
                verify_ssl=verify_ssl,
            )

    async def _make_request(
        self,
        url: str,
        method: str,
        headers: dict,
        params: dict,
        json_data: Optional[dict],
        form_data: Optional[dict],
        auth: Optional[aiohttp.BasicAuth],
        verify_ssl: bool,
    ) -> Dict[str, Any]:
        """Make a single HTTP request."""
        try:
            connector = aiohttp.TCPConnector(ssl=verify_ssl)

            async with aiohttp.ClientSession(
                timeout=self.timeout,
                connector=connector,
            ) as session:
                request_kwargs = {
                    "headers": headers,
                    "params": params,
                    "auth": auth,
                }

                if json_data:
                    request_kwargs["json"] = json_data
                elif form_data:
                    request_kwargs["data"] = form_data

                async with session.request(method, url, **request_kwargs) as response:
                    # Read response body
                    body_text = await response.text()

                    # Try to parse as JSON
                    try:
                        body_json = json.loads(body_text)
                    except json.JSONDecodeError:
                        body_json = None

                    # Build result
                    result = {
                        "success": response.status < 400,
                        "status_code": response.status,
                        "status": response.reason,
                        "headers": dict(response.headers),
                        "body": body_json if body_json is not None else body_text,
                        "url": str(response.url),
                        "method": method,
                    }

                    if response.status >= 400:
                        result["error"] = f"HTTP {response.status}: {response.reason}"

                    logger.info(
                        f"API call: {method} {url} -> {response.status} "
                        f"(body_len={len(body_text)})"
                    )

                    return result

        except asyncio.TimeoutError:
            logger.error(f"Request timeout: {method} {url}")
            return {
                "success": False,
                "error": f"Request timeout after {self.timeout.total}s",
                "timeout": True,
            }

        except ClientError as e:
            logger.error(f"Client error: {method} {url}: {e}")
            return {
                "success": False,
                "error": f"Client error: {str(e)}",
            }

        except Exception as e:
            logger.error(f"Unexpected error: {method} {url}: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
            }

    async def _request_with_retry(
        self,
        url: str,
        method: str,
        headers: dict,
        params: dict,
        json_data: Optional[dict],
        form_data: Optional[dict],
        auth: Optional[aiohttp.BasicAuth],
        verify_ssl: bool,
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic."""
        last_error = None
        delay = self.retry_delay

        for attempt in range(self.max_retries):
            result = await self._make_request(
                url=url,
                method=method,
                headers=headers,
                params=params,
                json_data=json_data,
                form_data=form_data,
                auth=auth,
                verify_ssl=verify_ssl,
            )

            # Success - return immediately
            if result.get("success"):
                if attempt > 0:
                    logger.info(f"Request succeeded on attempt {attempt + 1}")
                return result

            # Check if error is retryable
            status_code = result.get("status_code", 0)
            timeout = result.get("timeout", False)

            # Retry on 5xx errors, timeouts, or network errors
            retryable = (
                status_code >= 500 or
                timeout or
                result.get("error", "").startswith("Client error") or
                result.get("error", "").startswith("Unexpected error")
            )

            if not retryable:
                logger.info(f"Error not retryable: {result.get('error')}")
                return result

            last_error = result

            # Don't sleep after last attempt
            if attempt < self.max_retries - 1:
                logger.warning(
                    f"Request failed (attempt {attempt + 1}/{self.max_retries}), "
                    f"retrying in {delay:.1f}s: {result.get('error')}"
                )
                await asyncio.sleep(delay)
                delay *= self.retry_backoff

        # All retries exhausted
        logger.error(
            f"Request failed after {self.max_retries} attempts: {url}"
        )

        if last_error:
            last_error["retries_exhausted"] = True
            last_error["attempts"] = self.max_retries
            return last_error

        return {
            "success": False,
            "error": "All retry attempts failed",
            "retries_exhausted": True,
            "attempts": self.max_retries,
        }

    async def batch_request(self, requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Execute multiple requests concurrently.

        Args:
            requests: List of request input dicts

        Returns:
            List of response dicts in same order as requests
        """
        tasks = [self.execute(req) for req in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error dicts
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Batch request {i} failed: {result}")
                processed_results.append({
                    "success": False,
                    "error": str(result),
                    "request_index": i,
                })
            else:
                processed_results.append(result)

        return processed_results

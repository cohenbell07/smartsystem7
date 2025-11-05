"""
Lightweight web scraping tool using requests + BeautifulSoup.
"""

import logging
from typing import Dict, Any, Optional, List
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time

logger = logging.getLogger(__name__)


class WebScraper:
    """Lightweight web scraping tool for fetching and parsing web content."""

    def __init__(self, timeout: int = 30, max_retries: int = 3):
        """
        Initialize web scraper.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute web scraping action.

        Supported actions:
        - fetch: Fetch HTML content from URL
        - extract_text: Extract all text from URL
        - extract_links: Extract all links from URL
        - extract_metadata: Extract page metadata (title, description, etc.)
        - extract_elements: Extract specific HTML elements by selector

        Args:
            inputs: Dict with 'action' and action-specific params:
                - url: Target URL (required)
                - selector: CSS selector for element extraction
                - headers: Custom HTTP headers dict
                - verify_ssl: Bool to verify SSL (default: True)

        Returns:
            Dict with scraped data
        """
        url = inputs.get("url")
        if not url:
            return {"error": "No URL provided", "success": False}

        action = inputs.get("action", "fetch")
        custom_headers = inputs.get("headers", {})
        verify_ssl = inputs.get("verify_ssl", True)

        # Update session headers
        if custom_headers:
            self.session.headers.update(custom_headers)

        try:
            if action == "fetch":
                return await self._fetch_html(url, verify_ssl)
            elif action == "extract_text":
                return await self._extract_text(url, verify_ssl)
            elif action == "extract_links":
                return await self._extract_links(url, verify_ssl)
            elif action == "extract_metadata":
                return await self._extract_metadata(url, verify_ssl)
            elif action == "extract_elements":
                selector = inputs.get("selector")
                if not selector:
                    return {"error": "No selector provided for extract_elements", "success": False}
                return await self._extract_elements(url, selector, verify_ssl)
            else:
                return {"error": f"Unknown action: {action}", "success": False}

        except Exception as e:
            logger.error(f"Web scraping error: {e}", exc_info=True)
            return {"error": str(e), "success": False}

    async def _fetch_html(self, url: str, verify_ssl: bool) -> Dict[str, Any]:
        """Fetch HTML content from URL."""
        try:
            response = self.session.get(url, timeout=self.timeout, verify=verify_ssl)
            response.raise_for_status()

            logger.info(f"Fetched {url}: {response.status_code}, {len(response.text)} chars")

            return {
                "success": True,
                "url": url,
                "status_code": response.status_code,
                "html": response.text,
                "encoding": response.encoding,
                "content_type": response.headers.get('Content-Type', ''),
            }

        except requests.exceptions.Timeout:
            logger.error(f"Request timeout: {url}")
            return {
                "success": False,
                "error": f"Request timeout after {self.timeout}s",
                "timeout": True,
            }

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error for {url}: {e}")
            return {
                "success": False,
                "error": f"HTTP {e.response.status_code}: {e.response.reason}",
                "status_code": e.response.status_code,
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Request error for {url}: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    async def _extract_text(self, url: str, verify_ssl: bool) -> Dict[str, Any]:
        """Extract all text content from URL."""
        result = await self._fetch_html(url, verify_ssl)

        if not result.get("success"):
            return result

        try:
            soup = BeautifulSoup(result["html"], 'html.parser')

            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.extract()

            # Get text
            text = soup.get_text()

            # Clean up text
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)

            logger.info(f"Extracted {len(text)} chars of text from {url}")

            return {
                "success": True,
                "url": url,
                "text": text,
                "length": len(text),
            }

        except Exception as e:
            logger.error(f"Failed to extract text from {url}: {e}")
            return {
                "success": False,
                "error": f"Text extraction failed: {str(e)}",
            }

    async def _extract_links(self, url: str, verify_ssl: bool) -> Dict[str, Any]:
        """Extract all links from URL."""
        result = await self._fetch_html(url, verify_ssl)

        if not result.get("success"):
            return result

        try:
            soup = BeautifulSoup(result["html"], 'html.parser')

            links = []
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']

                # Convert relative URLs to absolute
                absolute_url = urljoin(url, href)

                # Get link text
                text = a_tag.get_text(strip=True)

                links.append({
                    "url": absolute_url,
                    "text": text,
                    "href": href,
                })

            logger.info(f"Extracted {len(links)} links from {url}")

            return {
                "success": True,
                "url": url,
                "links": links,
                "count": len(links),
            }

        except Exception as e:
            logger.error(f"Failed to extract links from {url}: {e}")
            return {
                "success": False,
                "error": f"Link extraction failed: {str(e)}",
            }

    async def _extract_metadata(self, url: str, verify_ssl: bool) -> Dict[str, Any]:
        """Extract page metadata (title, description, etc.)."""
        result = await self._fetch_html(url, verify_ssl)

        if not result.get("success"):
            return result

        try:
            soup = BeautifulSoup(result["html"], 'html.parser')

            metadata = {
                "url": url,
                "title": None,
                "description": None,
                "keywords": None,
                "author": None,
                "og_title": None,
                "og_description": None,
                "og_image": None,
            }

            # Extract title
            title_tag = soup.find('title')
            if title_tag:
                metadata["title"] = title_tag.get_text(strip=True)

            # Extract meta tags
            meta_tags = soup.find_all('meta')
            for tag in meta_tags:
                name = tag.get('name', '').lower()
                property_val = tag.get('property', '').lower()
                content = tag.get('content', '')

                if name == 'description':
                    metadata["description"] = content
                elif name == 'keywords':
                    metadata["keywords"] = content
                elif name == 'author':
                    metadata["author"] = content
                elif property_val == 'og:title':
                    metadata["og_title"] = content
                elif property_val == 'og:description':
                    metadata["og_description"] = content
                elif property_val == 'og:image':
                    metadata["og_image"] = content

            logger.info(f"Extracted metadata from {url}")

            return {
                "success": True,
                **metadata
            }

        except Exception as e:
            logger.error(f"Failed to extract metadata from {url}: {e}")
            return {
                "success": False,
                "error": f"Metadata extraction failed: {str(e)}",
            }

    async def _extract_elements(self, url: str, selector: str, verify_ssl: bool) -> Dict[str, Any]:
        """Extract specific HTML elements by CSS selector."""
        result = await self._fetch_html(url, verify_ssl)

        if not result.get("success"):
            return result

        try:
            soup = BeautifulSoup(result["html"], 'html.parser')

            elements = soup.select(selector)

            extracted = []
            for elem in elements:
                extracted.append({
                    "tag": elem.name,
                    "text": elem.get_text(strip=True),
                    "html": str(elem),
                    "attrs": dict(elem.attrs),
                })

            logger.info(f"Extracted {len(extracted)} elements matching '{selector}' from {url}")

            return {
                "success": True,
                "url": url,
                "selector": selector,
                "elements": extracted,
                "count": len(extracted),
            }

        except Exception as e:
            logger.error(f"Failed to extract elements from {url}: {e}")
            return {
                "success": False,
                "error": f"Element extraction failed: {str(e)}",
            }

    def close(self):
        """Close session."""
        self.session.close()

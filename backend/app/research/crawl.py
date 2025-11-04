"""
Content crawling and extraction module using Playwright and Trafilatura.
"""

import logging
import asyncio
from typing import Optional, Dict
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import trafilatura
from bs4 import BeautifulSoup
import httpx
import os

logger = logging.getLogger(__name__)

MAX_TIMEOUT = int(os.getenv("MAX_CRAWL_TIMEOUT", "30"))
PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"


async def fetch_with_playwright(url: str, timeout: int = MAX_TIMEOUT) -> Optional[str]:
    """
    Fetch page content using Playwright (for JS-heavy sites).

    Args:
        url: URL to fetch
        timeout: Timeout in seconds

    Returns:
        HTML content or None if failed
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
            page = await browser.new_page()

            await page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
            content = await page.content()

            await browser.close()

            logger.info(f"Playwright fetched {len(content)} chars from {url}")
            return content

    except PlaywrightTimeout:
        logger.warning(f"Playwright timeout for {url}")
        return None
    except Exception as e:
        logger.error(f"Playwright error for {url}: {e}")
        return None


async def fetch_with_httpx(url: str, timeout: int = MAX_TIMEOUT) -> Optional[str]:
    """
    Fetch page content using HTTPX (faster, but doesn't execute JS).

    Args:
        url: URL to fetch
        timeout: Timeout in seconds

    Returns:
        HTML content or None if failed
    """
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()

            logger.info(f"HTTPX fetched {len(response.text)} chars from {url}")
            return response.text

    except httpx.HTTPError as e:
        logger.warning(f"HTTPX error for {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching {url}: {e}")
        return None


def extract_text_with_trafilatura(html: str) -> Optional[str]:
    """
    Extract main text content using Trafilatura.

    Args:
        html: HTML content

    Returns:
        Extracted text or None
    """
    try:
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
        if text:
            logger.debug(f"Trafilatura extracted {len(text)} chars")
        return text
    except Exception as e:
        logger.error(f"Trafilatura extraction failed: {e}")
        return None


def extract_metadata(html: str) -> Dict[str, Optional[str]]:
    """
    Extract metadata from HTML using BeautifulSoup.

    Args:
        html: HTML content

    Returns:
        Dict with title, description, author, etc.
    """
    try:
        soup = BeautifulSoup(html, "lxml")

        # Extract title
        title = None
        if soup.title:
            title = soup.title.string
        elif soup.find("meta", property="og:title"):
            title = soup.find("meta", property="og:title").get("content")

        # Extract description
        description = None
        desc_tag = soup.find("meta", attrs={"name": "description"})
        if desc_tag:
            description = desc_tag.get("content")
        elif soup.find("meta", property="og:description"):
            description = soup.find("meta", property="og:description").get("content")

        # Extract author
        author = None
        author_tag = soup.find("meta", attrs={"name": "author"})
        if author_tag:
            author = author_tag.get("content")

        return {
            "title": title,
            "description": description,
            "author": author,
        }

    except Exception as e:
        logger.error(f"Metadata extraction failed: {e}")
        return {}


async def crawl_url(
    url: str, use_playwright: bool = False, timeout: int = MAX_TIMEOUT
) -> Optional[Dict[str, any]]:
    """
    Crawl a URL and extract content.

    Args:
        url: URL to crawl
        use_playwright: Use Playwright instead of HTTPX (slower but handles JS)
        timeout: Timeout in seconds

    Returns:
        Dict with url, title, content, and metadata, or None if failed
    """
    logger.info(f"Crawling {url} (playwright={use_playwright})")

    # Fetch HTML
    if use_playwright:
        html = await fetch_with_playwright(url, timeout)
    else:
        html = await fetch_with_httpx(url, timeout)

    if not html:
        return None

    # Extract text content
    content = extract_text_with_trafilatura(html)
    if not content:
        logger.warning(f"No content extracted from {url}")
        return None

    # Extract metadata
    metadata = extract_metadata(html)

    return {
        "url": url,
        "title": metadata.get("title"),
        "content": content,
        "metadata": metadata,
        "length": len(content),
    }


async def crawl_urls(
    urls: list[str], use_playwright: bool = False, max_concurrent: int = 5
) -> list[Dict[str, any]]:
    """
    Crawl multiple URLs concurrently.

    Args:
        urls: List of URLs to crawl
        use_playwright: Use Playwright for all URLs
        max_concurrent: Maximum concurrent requests

    Returns:
        List of crawl results (excluding failed ones)
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def crawl_with_semaphore(url: str):
        async with semaphore:
            return await crawl_url(url, use_playwright=use_playwright)

    tasks = [crawl_with_semaphore(url) for url in urls]
    results = await asyncio.gather(*tasks)

    # Filter out None results
    valid_results = [r for r in results if r is not None]

    logger.info(f"Crawled {len(valid_results)}/{len(urls)} URLs successfully")
    return valid_results

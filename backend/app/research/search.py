"""
Web search module supporting multiple providers.
Default: SerpAPI with Bing engine.
"""

import os
import logging
from typing import List, Dict, Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "serpapi")
BING_API_KEY = os.getenv("BING_SEARCH_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")


class SearchResult:
    """A search result."""

    def __init__(self, title: str, url: str, snippet: str):
        self.title = title
        self.url = url
        self.snippet = snippet

    def to_dict(self) -> dict:
        return {"title": self.title, "url": self.url, "snippet": self.snippet}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def search_bing(query: str, count: int = 50) -> List[SearchResult]:
    """Search using Bing Search API."""
    if not BING_API_KEY:
        logger.warning("BING_SEARCH_API_KEY not set, returning empty results")
        return []

    url = "https://api.bing.microsoft.com/v7.0/search"
    headers = {"Ocp-Apim-Subscription-Key": BING_API_KEY}
    params = {"q": query, "count": min(count, 50), "responseFilter": "Webpages"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("webPages", {}).get("value", []):
                results.append(
                    SearchResult(
                        title=item.get("name", ""),
                        url=item.get("url", ""),
                        snippet=item.get("snippet", ""),
                    )
                )

            logger.info(f"Bing search returned {len(results)} results for query: {query}")
            return results

        except httpx.HTTPError as e:
            logger.error(f"Bing search failed: {e}")
            raise


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def search_serpapi(query: str, count: int = 50) -> List[SearchResult]:
    """Search using SerpAPI with Bing engine."""
    if not SERPAPI_KEY:
        logger.warning("SERPAPI_KEY not set, returning empty results")
        return []

    url = "https://serpapi.com/search.json"
    params = {
        "q": query,
        "api_key": SERPAPI_KEY,
        "engine": "bing",
        "num": min(count, 100),
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("organic_results", []):
                results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        url=item.get("link", ""),
                        snippet=item.get("snippet", ""),
                    )
                )

            logger.info(f"SerpAPI search returned {len(results)} results for query: {query}")
            return results

        except httpx.HTTPError as e:
            logger.error(f"SerpAPI search failed: {e}")
            raise


async def search_web(
    query: str, count: int = 50, provider: Optional[str] = None
) -> List[Dict[str, str]]:
    """
    Search the web for a query using configured provider.

    Args:
        query: Search query
        count: Number of results to return (max 50 for Bing API, 100 for SerpAPI)
        provider: Override default provider ("bing" or "serpapi", default: "serpapi")

    Returns:
        List of search results with title, url, and snippet
    """
    provider = provider or SEARCH_PROVIDER

    logger.info(f"Searching web with provider={provider}, query='{query}', count={count}")

    if provider == "bing":
        results = await search_bing(query, count)
    elif provider == "serpapi":
        results = await search_serpapi(query, count)
    else:
        logger.error(f"Unknown search provider: {provider}")
        return []

    return [r.to_dict() for r in results]


async def multi_query_search(queries: List[str], count_per_query: int = 20) -> List[Dict[str, str]]:
    """
    Execute multiple search queries and combine results.

    Args:
        queries: List of search queries
        count_per_query: Results per query

    Returns:
        Combined list of search results
    """
    all_results = []
    seen_urls = set()

    for query in queries:
        results = await search_web(query, count=count_per_query)

        # Deduplicate by URL
        for result in results:
            url = result["url"]
            if url not in seen_urls:
                seen_urls.add(url)
                all_results.append(result)

    logger.info(f"Multi-query search returned {len(all_results)} unique results from {len(queries)} queries")
    return all_results

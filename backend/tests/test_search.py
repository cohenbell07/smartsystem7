"""
Tests for web search functionality.

To run these tests with actual API calls:
    SERPAPI_KEY=your_key pytest tests/test_search.py -v

Without API key, tests will be skipped.
"""
import pytest
import os
from app.research.search import search_web, search_serpapi, search_bing


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("SERPAPI_KEY"), reason="SERPAPI_KEY not set")
async def test_serpapi_search():
    """Test SerpAPI search with Bing engine."""
    results = await search_serpapi("python programming", count=5)

    assert len(results) > 0, "Should return results"
    assert all(hasattr(r, 'title') for r in results), "All results should have title"
    assert all(hasattr(r, 'url') for r in results), "All results should have url"
    assert all(hasattr(r, 'snippet') for r in results), "All results should have snippet"


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("BING_SEARCH_API_KEY"), reason="BING_SEARCH_API_KEY not set")
async def test_bing_search():
    """Test direct Bing Search API."""
    results = await search_bing("python programming", count=5)

    assert len(results) > 0, "Should return results"
    assert all(hasattr(r, 'title') for r in results), "All results should have title"
    assert all(hasattr(r, 'url') for r in results), "All results should have url"
    assert all(hasattr(r, 'snippet') for r in results), "All results should have snippet"


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("SERPAPI_KEY"), reason="SERPAPI_KEY not set")
async def test_search_web_default_provider():
    """Test search_web with default provider (SerpAPI)."""
    results = await search_web("artificial intelligence", count=5)

    assert len(results) > 0, "Should return results"

    # Verify structure
    for result in results:
        assert 'title' in result, "Result should have title"
        assert 'url' in result, "Result should have url"
        assert 'snippet' in result, "Result should have snippet"
        assert result['title'], "Title should not be empty"
        assert result['url'].startswith('http'), "URL should be valid"


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("SERPAPI_KEY"), reason="SERPAPI_KEY not set")
async def test_search_web_explicit_serpapi():
    """Test search_web with explicit serpapi provider."""
    results = await search_web("python", count=3, provider="serpapi")

    assert len(results) > 0, "Should return results"
    assert len(results) <= 3, "Should respect count limit"


@pytest.mark.asyncio
async def test_search_web_no_api_key():
    """Test search_web without API key returns empty results."""
    # Temporarily unset keys
    old_serpapi = os.environ.get("SERPAPI_KEY")
    old_bing = os.environ.get("BING_SEARCH_API_KEY")

    if old_serpapi:
        del os.environ["SERPAPI_KEY"]
    if old_bing:
        del os.environ["BING_SEARCH_API_KEY"]

    # Import after unsetting to get fresh config
    from importlib import reload
    from app.research import search as search_module
    reload(search_module)

    results = await search_module.search_web("test query")
    assert results == [], "Should return empty list without API key"

    # Restore keys
    if old_serpapi:
        os.environ["SERPAPI_KEY"] = old_serpapi
    if old_bing:
        os.environ["BING_SEARCH_API_KEY"] = old_bing


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("SERPAPI_KEY"), reason="SERPAPI_KEY not set")
async def test_organic_results_format():
    """Test that organic_results format is correctly parsed."""
    results = await search_serpapi("machine learning", count=2)

    assert len(results) > 0, "Should return results"

    # Verify SearchResult objects have correct attributes
    for result in results:
        assert hasattr(result, 'title'), "Should have title attribute"
        assert hasattr(result, 'url'), "Should have url attribute"
        assert hasattr(result, 'snippet'), "Should have snippet attribute"

        # Verify not None or empty
        assert result.title, "Title should not be empty"
        assert result.url, "URL should not be empty"

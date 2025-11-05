"""
Test script for SerpAPI search integration.
"""
import asyncio
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.research.search import search_web, search_serpapi


async def test_search():
    """Test SerpAPI search with Bing engine."""
    print("=" * 60)
    print("Testing SerpAPI Search Integration")
    print("=" * 60)

    # Check for API key
    serpapi_key = os.getenv("SERPAPI_KEY")
    if not serpapi_key:
        print("❌ SERPAPI_KEY not set in environment")
        print("Please set SERPAPI_KEY in your .env file or environment")
        return False

    print(f"✓ SERPAPI_KEY found: {serpapi_key[:10]}...")
    print()

    # Test query
    test_query = "artificial intelligence 2024"
    print(f"Test Query: '{test_query}'")
    print("-" * 60)

    try:
        # Test with provider explicitly set to serpapi
        results = await search_web(test_query, count=5, provider="serpapi")

        if not results:
            print("❌ No results returned")
            return False

        print(f"✅ SUCCESS: Received {len(results)} results\n")

        # Display first 3 results
        for i, result in enumerate(results[:3], 1):
            print(f"Result {i}:")
            print(f"  Title: {result['title'][:80]}...")
            print(f"  URL: {result['url']}")
            print(f"  Snippet: {result['snippet'][:100]}...")
            print()

        # Verify JSON structure
        print("-" * 60)
        print("JSON Structure Validation:")
        required_fields = ['title', 'url', 'snippet']
        for field in required_fields:
            has_field = all(field in r for r in results)
            status = "✅" if has_field else "❌"
            print(f"  {status} All results have '{field}' field")

        print()
        print("=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_direct_serpapi():
    """Test SerpAPI function directly."""
    print("\n" + "=" * 60)
    print("Testing Direct SerpAPI Function Call")
    print("=" * 60)

    try:
        results = await search_serpapi("python programming", count=3)
        print(f"✅ Direct call successful: {len(results)} results")
        return True
    except Exception as e:
        print(f"❌ Direct call failed: {e}")
        return False


if __name__ == "__main__":
    # Run tests
    success1 = asyncio.run(test_search())
    success2 = asyncio.run(test_direct_serpapi())

    if success1 and success2:
        print("\n🎉 All tests passed! SerpAPI integration is working correctly.")
        sys.exit(0)
    else:
        print("\n⚠️  Some tests failed. Please check the output above.")
        sys.exit(1)

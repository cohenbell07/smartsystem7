"""
Test script to verify SerpAPI configuration changes.
"""
import os
import sys

print("=" * 60)
print("Verifying SerpAPI Migration Configuration")
print("=" * 60)

# Read the search.py file
search_file = "/home/user/smartsystem7/backend/app/research/search.py"

with open(search_file, 'r') as f:
    content = f.read()

# Verify changes
tests = []

# Test 1: Check default provider is serpapi
if 'SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "serpapi")' in content:
    tests.append(("✅", "Default provider set to 'serpapi'"))
else:
    tests.append(("❌", "Default provider NOT set to 'serpapi'"))

# Test 2: Check SerpAPI URL is .json endpoint
if 'url = "https://serpapi.com/search.json"' in content:
    tests.append(("✅", "SerpAPI URL uses .json endpoint"))
else:
    tests.append(("❌", "SerpAPI URL missing .json endpoint"))

# Test 3: Check engine is set to bing
if '"engine": "bing"' in content:
    tests.append(("✅", "SerpAPI engine set to 'bing'"))
else:
    tests.append(("❌", "SerpAPI engine NOT set to 'bing'"))

# Test 4: Check organic_results parsing
if 'data.get("organic_results"' in content:
    tests.append(("✅", "Using organic_results for JSON parsing"))
else:
    tests.append(("❌", "organic_results parsing not found"))

# Test 5: Check SERPAPI_KEY environment variable
if 'SERPAPI_KEY = os.getenv("SERPAPI_KEY")' in content:
    tests.append(("✅", "SERPAPI_KEY environment variable configured"))
else:
    tests.append(("❌", "SERPAPI_KEY not configured"))

# Test 6: Check updated docstring
if 'SerpAPI with Bing engine' in content:
    tests.append(("✅", "Documentation updated for Bing engine"))
else:
    tests.append(("❌", "Documentation not updated"))

print()
for status, message in tests:
    print(f"{status} {message}")

# Summary
passed = sum(1 for status, _ in tests if status == "✅")
total = len(tests)

print()
print("=" * 60)
if passed == total:
    print(f"✅ All {total} configuration tests passed!")
    print("=" * 60)
    print()
    print("Migration Summary:")
    print("  • Default provider: SerpAPI")
    print("  • Search engine: Bing")
    print("  • API endpoint: https://serpapi.com/search.json")
    print("  • Response format: organic_results")
    print()
    print("Next Steps:")
    print("  1. Set SERPAPI_KEY in your .env file")
    print("  2. Test with: make dev")
    print("  3. Submit a research query to verify end-to-end")
    sys.exit(0)
else:
    print(f"⚠️  {total - passed} test(s) failed")
    print("=" * 60)
    sys.exit(1)

"""
Deduplication module using URL normalization and content simhash.
"""

import logging
import hashlib
from typing import List, Dict
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from simhash import Simhash

logger = logging.getLogger(__name__)


def normalize_url(url: str) -> str:
    """
    Normalize URL for deduplication.

    - Remove fragments
    - Sort query parameters
    - Remove common tracking parameters
    - Lowercase scheme and domain

    Args:
        url: URL to normalize

    Returns:
        Normalized URL
    """
    parsed = urlparse(url)

    # Lowercase scheme and netloc
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Remove www prefix
    if netloc.startswith("www."):
        netloc = netloc[4:]

    # Parse and filter query parameters
    params = parse_qs(parsed.query)

    # Remove common tracking parameters
    tracking_params = {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "fbclid",
        "gclid",
        "ref",
        "source",
    }

    filtered_params = {k: v for k, v in params.items() if k not in tracking_params}

    # Sort parameters for consistency
    sorted_query = urlencode(sorted(filtered_params.items()), doseq=True)

    # Reconstruct URL without fragment
    normalized = urlunparse((scheme, netloc, parsed.path, parsed.params, sorted_query, ""))

    return normalized


def content_hash(text: str) -> str:
    """
    Generate a simhash for content similarity detection.

    Args:
        text: Text content

    Returns:
        Hex string of simhash
    """
    if not text:
        return ""

    # Use simhash for fuzzy matching
    hash_value = Simhash(text).value

    # Convert to hex string
    return format(hash_value, "016x")


def compute_similarity(hash1: str, hash2: str) -> int:
    """
    Compute Hamming distance between two simhashes.

    Args:
        hash1: First hash (hex string)
        hash2: Second hash (hex string)

    Returns:
        Hamming distance (lower = more similar)
    """
    if not hash1 or not hash2:
        return 64  # Maximum distance

    try:
        val1 = int(hash1, 16)
        val2 = int(hash2, 16)

        # Count differing bits
        xor = val1 ^ val2
        distance = bin(xor).count("1")

        return distance

    except ValueError:
        return 64


def deduplicate_sources(
    sources: List[Dict[str, any]], similarity_threshold: int = 3
) -> List[Dict[str, any]]:
    """
    Deduplicate sources by URL and content similarity.

    Args:
        sources: List of source dicts with 'url' and 'content'
        similarity_threshold: Max Hamming distance to consider duplicates (lower = stricter)

    Returns:
        Deduplicated list of sources
    """
    logger.info(f"Deduplicating {len(sources)} sources...")

    seen_urls = set()
    seen_hashes = []
    unique_sources = []

    for source in sources:
        url = source.get("url", "")
        content = source.get("content", "")

        # Normalize URL
        normalized_url = normalize_url(url)

        # Skip if URL already seen
        if normalized_url in seen_urls:
            logger.debug(f"Skipping duplicate URL: {url}")
            continue

        # Compute content hash
        hash_val = content_hash(content)

        # Check similarity to existing content
        is_duplicate = False
        for existing_hash in seen_hashes:
            distance = compute_similarity(hash_val, existing_hash)
            if distance <= similarity_threshold:
                logger.debug(f"Skipping similar content (distance={distance}): {url}")
                is_duplicate = True
                break

        if not is_duplicate:
            seen_urls.add(normalized_url)
            seen_hashes.append(hash_val)
            unique_sources.append({**source, "content_hash": hash_val})

    logger.info(
        f"Deduplicated {len(sources)} -> {len(unique_sources)} sources "
        f"({len(sources) - len(unique_sources)} duplicates removed)"
    )

    return unique_sources


def deduplicate_by_url_only(sources: List[Dict[str, any]]) -> List[Dict[str, any]]:
    """
    Deduplicate sources by normalized URL only (faster, less strict).

    Args:
        sources: List of source dicts with 'url'

    Returns:
        Deduplicated list of sources
    """
    logger.info(f"Deduplicating {len(sources)} sources by URL only...")

    seen_urls = set()
    unique_sources = []

    for source in sources:
        url = source.get("url", "")
        normalized_url = normalize_url(url)

        if normalized_url not in seen_urls:
            seen_urls.add(normalized_url)
            unique_sources.append(source)

    logger.info(
        f"Deduplicated {len(sources)} -> {len(unique_sources)} sources by URL "
        f"({len(sources) - len(unique_sources)} duplicates removed)"
    )

    return unique_sources

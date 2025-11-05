"""Research pipeline modules."""

from .search import search_web
from .crawl import crawl_url, crawl_urls
from .dedupe import deduplicate_sources
from .synthesize import synthesize_research
from .viability import calculate_viability_score

__all__ = [
    "search_web",
    "crawl_url",
    "crawl_urls",
    "deduplicate_sources",
    "synthesize_research",
    "calculate_viability_score",
]

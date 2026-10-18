"""OPTIONAL live Tavily test — never runs in the normal suite.

Enable explicitly with BOTH conditions (then exactly one real request):

    TAVILY_LIVE_TEST=true TAVILY_API_KEY=<key> \
        python -m pytest worker/tests/test_tavily_live.py -v

Single controlled query, max 2 results. Persists nothing, calls no Gemini,
touches no database. Skips cleanly otherwise. Never prints the key.
"""

import os

import pytest

from worker.search.tavily import TavilySearchProvider

pytestmark = pytest.mark.skipif(
    os.getenv("TAVILY_LIVE_TEST", "").strip().lower() != "true"
    or not os.getenv("TAVILY_API_KEY", "").strip(),
    reason="live Tavily only (TAVILY_LIVE_TEST=true + TAVILY_API_KEY required)",
)


def test_live_single_query_smoke():
    provider = TavilySearchProvider()
    assert provider.is_configured()
    results = provider.search("Java Developer Intern Chennai India", max_results=2)
    assert isinstance(results, list)  # empty is a valid outcome
    for result in results:
        assert result.source_name == "tavily"
        assert result.url.startswith("http")

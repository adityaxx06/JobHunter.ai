"""OPTIONAL live ingestion test — never runs in the normal suite.

Enable explicitly with ALL conditions (then a small real run, DRY RUN only):

    TAVILY_LIVE_TEST=true TAVILY_API_KEY=<key> \
        python -m pytest worker/tests/test_ingestion_live.py -v

Uses at most 1 Tavily query and 2 boards, resolves real ATS URLs, fetches
real ATS data through the existing connectors. Persists NOTHING (persist is
never requested here), calls no AI, touches no database. Skips cleanly
otherwise. Never prints keys.
"""

import os

import pytest

from worker.pipelines.ingestion_pipeline import run_ingestion
from worker.search.query_generator import SearchProfile
from worker.search.tavily import TavilySearchProvider

pytestmark = pytest.mark.skipif(
    os.getenv("TAVILY_LIVE_TEST", "").strip().lower() != "true"
    or not os.getenv("TAVILY_API_KEY", "").strip(),
    reason="live ingestion only (TAVILY_LIVE_TEST=true + TAVILY_API_KEY required)",
)


def test_live_ingestion_dry_run_tiny():
    provider = TavilySearchProvider()
    assert provider.is_configured()
    profile = SearchProfile(
        roles=["Software Developer"],
        locations=["India"],
        remote_ok=True,
        experience_level="Fresher",
    )
    result = run_ingestion(
        profile=profile,
        provider=provider,
        max_queries=1,
        max_results_per_query=5,
        persist_requested=False,  # dry run: zero writes by construction
        max_boards=2,
    )
    assert result.queries_executed <= 1
    assert result.boards_attempted <= 2
    assert result.writes_performed is False
    assert result.gemini_calls == 0

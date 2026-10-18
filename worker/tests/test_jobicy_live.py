"""OPTIONAL live Jobicy smoke test — never runs in the normal suite.

Enable explicitly with:

    JOBICY_LIVE_TEST=true \
        python -m pytest worker/tests/test_jobicy_live.py -v

Makes exactly two public read-only requests (one search + one field probe)
against the free keyless API. Skips cleanly when disabled. Never writes to
any database, never calls Gemini.
"""

import os

import pytest

from worker.sources.jobicy.source import JobicySource

pytestmark = pytest.mark.skipif(
    os.getenv("JOBICY_LIVE_TEST", "").strip().lower() != "true",
    reason="live smoke test only (JOBICY_LIVE_TEST != true)",
)


def test_live_search_smoke():
    source = JobicySource(tags=["intern"], enabled=True)
    jobs = source.discover_jobs(limit=5)
    assert isinstance(jobs, list)  # empty result is a valid outcome
    for job in jobs:
        assert job.source_type == "job_board" and job.source_name == "jobicy"
        assert job.apply_url.startswith("http")


def test_live_field_probe():
    """Second request: confirm date/link fields on a fresh fetch (read-only)."""
    source = JobicySource(tags=["python"], enabled=True)
    jobs = source.discover_jobs(limit=3)
    dated = sum(1 for job in jobs if job.posted_at is not None)
    linked = sum(1 for job in jobs if job.apply_url.startswith("http"))
    assert linked == len(jobs)
    assert dated >= 0  # reported, not required — API may omit dates
    print(f"\nlive probe: {len(jobs)} jobs, {dated} dated, {linked} linked")

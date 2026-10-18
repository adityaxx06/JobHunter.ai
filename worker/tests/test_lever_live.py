"""OPTIONAL live Lever smoke test — never runs in the normal suite.

Enable explicitly with BOTH variables (no hard-coded company anywhere):

    LEVER_LIVE_TEST=true LEVER_BOARDS=<public-company-handle> \
        python -m pytest worker/tests/test_lever_live.py -v

Makes exactly one public read-only request to the first configured company.
Skips cleanly when disabled or when no company is configured.
"""

import os

import pytest

from worker.sources.lever import config as lever_config
from worker.sources.lever.source import LeverSource

pytestmark = pytest.mark.skipif(
    os.getenv("LEVER_LIVE_TEST", "").strip().lower() != "true",
    reason="live smoke test only (LEVER_LIVE_TEST != true)",
)


def test_live_company_smoke():
    boards = lever_config.get_boards()
    if not boards:
        pytest.skip("no LEVER_BOARDS configured")
    source = LeverSource(boards=boards[:1], enabled=True)
    jobs = source.discover_jobs(limit=5)
    assert isinstance(jobs, list)  # empty board is a valid outcome
    for job in jobs:
        assert job.source_type == "lever"
        assert job.apply_url.startswith("http")

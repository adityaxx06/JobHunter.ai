"""OPTIONAL live Greenhouse smoke test — never runs in the normal suite.

Enable explicitly with BOTH variables (no hard-coded company anywhere):

    GREENHOUSE_LIVE_TEST=true GREENHOUSE_BOARDS=<public-board-token> \
        python -m pytest worker/tests/test_greenhouse_live.py -v

Makes exactly one public read-only request to the first configured board.
Skips cleanly when disabled or when no board is configured.
"""

import os

import pytest

from worker.sources.greenhouse import config as gh_config
from worker.sources.greenhouse.source import GreenhouseSource

pytestmark = pytest.mark.skipif(
    os.getenv("GREENHOUSE_LIVE_TEST", "").strip().lower() != "true",
    reason="live smoke test only (GREENHOUSE_LIVE_TEST != true)",
)


def test_live_board_smoke():
    boards = gh_config.get_boards()
    if not boards:
        pytest.skip("no GREENHOUSE_BOARDS configured")
    source = GreenhouseSource(boards=boards[:1], enabled=True)
    jobs = source.discover_jobs(limit=5)
    assert isinstance(jobs, list)  # empty board is a valid outcome
    for job in jobs:
        assert job.source_type == "greenhouse"
        assert job.apply_url.startswith("http")

"""OPTIONAL live Ashby smoke test — never runs in the normal suite.

Enable explicitly with BOTH variables (no hard-coded company anywhere):

    ASHBY_LIVE_TEST=true ASHBY_BOARDS=<public-board-name> \
        python -m pytest worker/tests/test_ashby_live.py -v

Makes exactly one public read-only request to the first configured board.
Skips cleanly when disabled or when no board is configured.
"""

import os

import pytest

from worker.sources.ashby import config as ashby_config
from worker.sources.ashby.source import AshbySource

pytestmark = pytest.mark.skipif(
    os.getenv("ASHBY_LIVE_TEST", "").strip().lower() != "true",
    reason="live smoke test only (ASHBY_LIVE_TEST != true)",
)


def test_live_board_smoke():
    boards = ashby_config.get_boards()
    if not boards:
        pytest.skip("no ASHBY_BOARDS configured")
    source = AshbySource(boards=boards[:1], enabled=True)
    jobs = source.discover_jobs(limit=5)
    assert isinstance(jobs, list)  # empty board is a valid outcome
    for job in jobs:
        assert job.source_type == "ashby"
        assert job.apply_url.startswith("http")

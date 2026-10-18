"""Greenhouse JobSource: multi-board public discovery (Phase 4.2A).

Sequential, conservative, disabled-safe: with GREENHOUSE_ENABLED unset (or
no boards configured) this source returns [] and reports so via
``health_check`` — the pipeline and ``python -m worker.main`` stay healthy.
Per-board failures are captured in ``last_errors`` (board tokens are public,
safe to log) while other boards still contribute jobs.
"""

import logging
from typing import Optional

from worker.models.job import SourceHealth
from worker.sources.base import JobSource
from worker.sources.greenhouse import config as gh_config
from worker.sources.greenhouse.client import GreenhouseClient
from worker.sources.greenhouse.parser import parse_board_jobs

logger = logging.getLogger("ai-jobhunter.greenhouse")


class GreenhouseSource(JobSource):
    """Aggregate source over the configured public Greenhouse boards."""

    source_type = "greenhouse"
    source_name = "greenhouse"

    def __init__(
        self,
        boards: Optional[list] = None,
        enabled: Optional[bool] = None,
        timeout: Optional[float] = None,
        client_factory=None,
        max_retries: int = 0,
    ) -> None:
        self.boards = list(boards) if boards is not None else gh_config.get_boards()
        self.enabled = bool(enabled) if enabled is not None else gh_config.is_enabled()
        self.timeout = float(timeout) if timeout is not None else gh_config.get_timeout()
        self.client_factory = client_factory or (lambda board: GreenhouseClient(board, timeout=self.timeout, max_retries=max_retries))
        self.max_retries = max_retries
        self.last_errors: list = []

    def discover_jobs(self, query: str = "", location: str = "", limit: int = 50) -> list:
        """Fetch each board sequentially; failures become ``last_errors``."""
        self.last_errors = []
        if not self.enabled or not self.boards:
            return []
        collected = []
        remaining = max(0, int(limit))
        for board in self.boards:
            if remaining <= 0:
                break
            try:
                client = self.client_factory(board)
                jobs = parse_board_jobs(board, client.fetch_jobs())
            except Exception as exc:
                message = f"board '{board}': {type(exc).__name__}: {exc}"
                self.last_errors.append(message)
                logger.warning("greenhouse %s", message)
                continue
            jobs = self._apply_filters(jobs, query, location)
            collected.extend(jobs[:remaining])
            remaining -= min(len(jobs), remaining)
        return collected[: max(0, int(limit))]

    @staticmethod
    def _apply_filters(jobs: list, query: str, location: str) -> list:
        """Naive client-side substring filter (same semantics as mock source)."""
        if query.strip():
            q = query.strip().lower()
            jobs = [j for j in jobs if q in (j.title or "").lower()]
        if location.strip():
            loc = location.strip().lower()
            jobs = [j for j in jobs if loc in (j.location or "").lower()]
        return jobs

    def health_check(self) -> SourceHealth:
        """Report configured state without touching the network."""
        if not self.enabled:
            return SourceHealth(ok=False, message="greenhouse disabled (GREENHOUSE_ENABLED is not true)")
        if not self.boards:
            return SourceHealth(ok=False, message="greenhouse has no boards configured (GREENHOUSE_BOARDS empty)")
        suffix = f"{len(self.last_errors)} board error(s)" if self.last_errors else "no errors"
        return SourceHealth(ok=True, message=f"greenhouse ready ({len(self.boards)} board(s), {suffix})")

"""Lever JobSource: multi-company public discovery (Phase 4.2B).

Sequential, conservative, disabled-safe: with LEVER_ENABLED unset (or no
companies configured) this source returns [] and reports so via
``health_check`` — the pipeline and ``python -m worker.main`` stay healthy.
Per-company failures are captured in ``last_errors`` (handles are public,
safe to log) while other companies still contribute jobs.
"""

import logging
from typing import Optional

from worker.models.job import SourceHealth
from worker.sources.base import JobSource
from worker.sources.lever import config as lever_config
from worker.sources.lever.client import LeverClient
from worker.sources.lever.parser import parse_company_postings

logger = logging.getLogger("ai-jobhunter.lever")


class LeverSource(JobSource):
    """Aggregate source over the configured public Lever companies."""

    source_type = "lever"
    source_name = "lever"

    def __init__(
        self,
        boards: Optional[list] = None,
        enabled: Optional[bool] = None,
        timeout: Optional[float] = None,
        client_factory=None,
        max_retries: int = 0,
    ) -> None:
        self.boards = list(boards) if boards is not None else lever_config.get_boards()
        self.enabled = bool(enabled) if enabled is not None else lever_config.is_enabled()
        self.timeout = float(timeout) if timeout is not None else lever_config.get_timeout()
        self.client_factory = client_factory or (lambda company: LeverClient(company, timeout=self.timeout, max_retries=max_retries))
        self.max_retries = max_retries
        self.last_errors: list = []

    def discover_jobs(self, query: str = "", location: str = "", limit: int = 50) -> list:
        """Fetch each company sequentially; failures become ``last_errors``."""
        self.last_errors = []
        if not self.enabled or not self.boards:
            return []
        collected = []
        remaining = max(0, int(limit))
        for company in self.boards:
            if remaining <= 0:
                break
            try:
                client = self.client_factory(company)
                jobs = parse_company_postings(company, client.fetch_postings())
            except Exception as exc:
                message = f"company '{company}': {type(exc).__name__}: {exc}"
                self.last_errors.append(message)
                logger.warning("lever %s", message)
                continue
            jobs = self._apply_filters(jobs, query, location)
            collected.extend(jobs[:remaining])
            remaining -= min(len(jobs), remaining)
        return collected[: max(0, int(limit))]

    @staticmethod
    def _apply_filters(jobs: list, query: str, location: str) -> list:
        """Naive client-side substring filter (same semantics as other sources)."""
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
            return SourceHealth(ok=False, message="lever disabled (LEVER_ENABLED is not true)")
        if not self.boards:
            return SourceHealth(ok=False, message="lever has no companies configured (LEVER_BOARDS empty)")
        suffix = f"{len(self.last_errors)} company error(s)" if self.last_errors else "no errors"
        return SourceHealth(ok=True, message=f"lever ready ({len(self.boards)} companie(s), {suffix})")

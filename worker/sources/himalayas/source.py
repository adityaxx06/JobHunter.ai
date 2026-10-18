"""Himalayas JobSource: keyword-filtered public search (Phase 10C-2).

Sequential, conservative, disabled-safe: with HIMALAYA_ENABLED unset (or no
keywords configured) this source returns [] and reports so via
``health_check`` — the pipeline and ``python -m worker.main`` stay healthy.
One bounded search page per keyword (no cursor walking); per-keyword
failures are captured in ``last_errors`` while other keywords still
contribute jobs.
"""

import logging
from typing import Optional

from worker.models.job import SourceHealth
from worker.sources.base import JobSource
from worker.sources.himalayas import config as himalaya_config
from worker.sources.himalayas.client import HimalayaClient
from worker.sources.himalayas.parser import parse_search_jobs

logger = logging.getLogger("ai-jobhunter.himalayas")


class HimalayaSource(JobSource):
    """Filtered source over Himalayas' public search endpoint."""

    source_type = "job_board"
    source_name = "himalaya"

    def __init__(
        self,
        keywords: Optional[list] = None,
        employment_types: Optional[list] = None,
        enabled: Optional[bool] = None,
        timeout: Optional[float] = None,
        client_factory=None,
        max_retries: int = 0,
    ) -> None:
        self.keywords = list(keywords) if keywords is not None else himalaya_config.get_keywords()
        self.employment_types = (
            list(employment_types) if employment_types is not None
            else himalaya_config.get_employment_types()
        )
        self.enabled = bool(enabled) if enabled is not None else himalaya_config.is_enabled()
        self.timeout = float(timeout) if timeout is not None else himalaya_config.get_timeout()
        self.client_factory = client_factory or (
            lambda keyword: HimalayaClient(
                keyword, employment_types=self.employment_types,
                timeout=self.timeout, max_retries=max_retries))
        self.max_retries = max_retries
        self.last_errors: list = []

    def discover_jobs(self, query: str = "", location: str = "", limit: int = 50) -> list:
        """Search each keyword sequentially; failures become ``last_errors``."""
        self.last_errors = []
        keywords = [query.strip()] if query.strip() else list(self.keywords)
        if not self.enabled or not keywords:
            return []
        collected = []
        remaining = max(0, int(limit))
        for keyword in keywords:
            if remaining <= 0:
                break
            try:
                client = self.client_factory(keyword)
                jobs = parse_search_jobs(client.fetch_jobs())
            except Exception as exc:
                message = f"keyword '{keyword}': {type(exc).__name__}: {exc}"
                self.last_errors.append(message)
                logger.warning("himalaya %s", message)
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
            return SourceHealth(ok=False, message="himalaya disabled (HIMALAYA_ENABLED is not true)")
        if not self.keywords:
            return SourceHealth(ok=False, message="himalaya has no keywords configured (HIMALAYA_KEYWORDS empty)")
        suffix = f"{len(self.last_errors)} keyword error(s)" if self.last_errors else "no errors"
        return SourceHealth(ok=True, message=f"himalaya ready ({len(self.keywords)} keyword(s), {suffix})")

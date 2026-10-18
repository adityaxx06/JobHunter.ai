"""Jobicy JobSource: tag-filtered public listings (Phase 10C-3).

Sequential, conservative, disabled-safe: with JOBICY_ENABLED unset (or no
tags configured) this source returns [] and reports so via
``health_check`` — the pipeline and ``python -m worker.main`` stay healthy.
One bounded listing page per tag (no cursor walking); per-tag failures are
captured in ``last_errors`` while other tags still contribute jobs.
"""

import logging
from typing import Optional

from worker.models.job import SourceHealth
from worker.sources.base import JobSource
from worker.sources.jobicy import config as jobicy_config
from worker.sources.jobicy.client import JobicyClient
from worker.sources.jobicy.parser import parse_search_jobs

logger = logging.getLogger("ai-jobhunter.jobicy")


class JobicySource(JobSource):
    """Filtered source over Jobicy's public listing endpoint."""

    source_type = "job_board"
    source_name = "jobicy"

    def __init__(
        self,
        tags: Optional[list] = None,
        geo: Optional[str] = None,
        industry: Optional[str] = None,
        enabled: Optional[bool] = None,
        timeout: Optional[float] = None,
        client_factory=None,
        max_retries: int = 0,
    ) -> None:
        self.tags = list(tags) if tags is not None else jobicy_config.get_tags()
        self.geo = str(geo).strip() if geo is not None else jobicy_config.get_geo()
        self.industry = str(industry).strip() if industry is not None else jobicy_config.get_industry()
        self.enabled = bool(enabled) if enabled is not None else jobicy_config.is_enabled()
        self.timeout = float(timeout) if timeout is not None else jobicy_config.get_timeout()
        self.client_factory = client_factory or (
            lambda tag: JobicyClient(
                tag, geo=self.geo, industry=self.industry,
                timeout=self.timeout, max_retries=max_retries))
        self.max_retries = max_retries
        self.last_errors: list = []

    def discover_jobs(self, query: str = "", location: str = "", limit: int = 50) -> list:
        """Search each tag sequentially; failures become ``last_errors``."""
        self.last_errors = []
        tags = [query.strip()] if query.strip() else list(self.tags)
        if not self.enabled or not tags:
            return []
        collected = []
        remaining = max(0, int(limit))
        for tag in tags:
            if remaining <= 0:
                break
            try:
                client = self.client_factory(tag)
                jobs = parse_search_jobs(client.fetch_jobs())
            except Exception as exc:
                message = f"tag '{tag}': {type(exc).__name__}: {exc}"
                self.last_errors.append(message)
                logger.warning("jobicy %s", message)
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
            return SourceHealth(ok=False, message="jobicy disabled (JOBICY_ENABLED is not true)")
        if not self.tags:
            return SourceHealth(ok=False, message="jobicy has no tags configured (JOBICY_TAGS empty)")
        suffix = f"{len(self.last_errors)} tag error(s)" if self.last_errors else "no errors"
        return SourceHealth(ok=True, message=f"jobicy ready ({len(self.tags)} tag(s), {suffix})")

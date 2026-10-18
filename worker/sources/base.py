"""Common source-adapter contract (Phase 4.1).

Replaces the Phase 1 placeholder. Every job source (company career pages,
Greenhouse, Lever, Ashby, search-engine discovery, manual/mock) implements
:class:`JobSource` so new sources plug in without touching the pipeline.
No scraping, login automation, or CAPTCHA bypass belongs in any adapter.
"""

from abc import ABC, abstractmethod
from typing import Optional

from worker.models.job import DiscoveredJob, SourceHealth


class JobSource(ABC):
    """Abstract job source. Adapters fetch; the pipeline normalizes."""

    #: Machine key matching DB ``job_sources.source_type`` values
    #: (company_careers | greenhouse | lever | ashby | search_engine | manual).
    source_type: str = ""
    #: Unique human key used by the registry (e.g. "mock", "greenhouse-prod").
    source_name: str = ""

    @abstractmethod
    def discover_jobs(
        self,
        query: str = "",
        location: str = "",
        limit: int = 50,
    ) -> list:
        """Return up to ``limit`` :class:`DiscoveredJob` objects.

        Must never raise for empty results — return []. May raise on
        transport/config errors; the pipeline isolates per-source failures.
        """
        raise NotImplementedError

    def health_check(self) -> SourceHealth:
        """Self check (default: healthy). Override for live sources."""
        return SourceHealth(ok=True, message=f"{self.source_name or type(self).__name__} ready")

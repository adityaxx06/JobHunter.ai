"""Search-layer models (Phase 4.3). Distinct from canonical jobs on purpose.

Search results are *leads*: a title/URL/snippet triple that still needs
classification into a discovery target (and, later, parsing by the matching
source adapter). Nothing here claims to be a job posting.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utcnow() -> datetime:
    """Timezone-aware UTC now (default for discovered_at)."""
    return datetime.now(timezone.utc)


@dataclass
class SearchResult:
    """One raw hit from a search provider (lead, not a job)."""

    title: str = ""
    url: str = ""
    snippet: str = ""
    source_name: str = ""  # provider that returned it (e.g. "mock")
    discovered_at: datetime = field(default_factory=_utcnow)
    raw_data: dict = field(default_factory=dict)


@dataclass
class DiscoveryTarget:
    """A classified search result: where to look, with which parser, later."""

    url: str = ""
    classified_source: str = "unknown"  # greenhouse | lever | ashby | company_career | unknown
    title: str = ""
    snippet: str = ""


@dataclass
class SearchQuery:
    """One generated query plus the profile facets that produced it."""

    query: str = ""
    role: str = ""
    location: str = ""
    site_hint: str = ""  # e.g. "site:jobs.lever.co", "" when generic


@dataclass
class SearchHealth:
    """Result of a provider's self check."""

    ok: bool = True
    message: str = ""


@dataclass
class SearchPipelineResult:
    """Structured outcome of a search-discovery run."""

    queries_generated: int = 0
    queries_executed: int = 0
    results_found: int = 0
    targets_found: int = 0
    junk_removed: int = 0  # obvious non-job URLs dropped before targeting
    classification_stats: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    targets: list = field(default_factory=list)

    def summary(self) -> dict:
        """Plain-dict summary (handy for logging and tests)."""
        return {
            "queries_generated": self.queries_generated,
            "queries_executed": self.queries_executed,
            "results_found": self.results_found,
            "targets_found": self.targets_found,
            "junk_removed": self.junk_removed,
            "errors": len(self.errors),
        }

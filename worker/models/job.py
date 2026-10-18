"""Canonical internal job representation for discovered jobs (Phase 4.1).

Every source adapter produces :class:`DiscoveredJob` objects; the pipeline
normalizes them into :class:`NormalizedJob` (original + normalized values).
Dataclasses are used (stdlib only, consistent with the lightweight MVP style).
No secrets are stored here.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _utcnow() -> datetime:
    """Timezone-aware UTC now (default for discovered_at)."""
    return datetime.now(timezone.utc)


@dataclass
class DiscoveredJob:
    """Raw-but-structured posting as returned by a source adapter."""

    external_id: str = ""
    title: str = ""
    company_name: str = ""
    company_domain: str = ""
    location: str = ""
    locations: list = field(default_factory=list)
    is_remote: bool = False
    employment_type: str = ""
    experience_level: str = ""
    description: str = ""
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "INR"
    skills: list = field(default_factory=list)
    source_type: str = ""
    source_name: str = ""
    source_url: str = ""
    apply_url: str = ""
    posted_at: Optional[datetime] = None
    discovered_at: datetime = field(default_factory=_utcnow)
    raw_data: dict = field(default_factory=dict)


@dataclass
class NormalizedJob:
    """A discovered job plus its normalized values and fingerprint.

    Both original and normalized values are kept: matching/display code can
    use whichever is appropriate, and normalization stays auditable.
    """

    original: DiscoveredJob
    normalized_title: str = ""
    normalized_company: str = ""
    normalized_location: str = ""
    primary_location: str = ""
    normalized_employment_type: str = ""
    normalized_skills: list = field(default_factory=list)
    is_remote: bool = False
    fingerprint: str = ""


@dataclass
class SourceHealth:
    """Result of a source's self check (no network required for mock)."""

    ok: bool = True
    message: str = ""


@dataclass
class DedupeResult:
    """Outcome of in-memory deduplication over normalized jobs."""

    unique_jobs: list = field(default_factory=list)
    duplicate_count: int = 0
    duplicates: list = field(default_factory=list)


@dataclass
class SourceStats:
    """Per-source outcome inside a discovery run."""

    name: str = ""
    type: str = ""
    status: str = "ok"  # "ok" | "error"
    discovered: int = 0
    error: str = ""


@dataclass
class DiscoveryResult:
    """Structured outcome of a full discovery run (sources -> unique jobs)."""

    discovered_count: int = 0
    normalized_count: int = 0
    unique_count: int = 0
    jobs: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    source_stats: list = field(default_factory=list)

    def summary(self) -> dict:
        """Plain-dict summary (handy for logging and tests)."""
        return {
            "sources": len(self.source_stats),
            "discovered": self.discovered_count,
            "normalized": self.normalized_count,
            "unique": self.unique_count,
            "errors": len(self.errors),
        }

"""Ranking models (Phase 5.3). Dataclasses, matching project style.

RankedJob is the API-ready unit Phase 5.4 will serve: identity, position,
deterministic score with its component reasons, and display fields.
RankingPipelineResult reports received/ranked/excluded counts plus errors —
excluded rows are counted, never silently discarded.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RankedJob:
    """One analyzed job with its deterministic rank and score breakdown."""

    job_id: str = ""
    profile_id: str = ""
    rank: int = 0
    ranking_score: float = 0.0
    match_score: int = 0
    trust_score: int = 0
    recommendation: str = "REVIEW"
    priority_reasons: list = field(default_factory=list)
    title: str = ""
    company_name: str = ""
    location: str = ""
    is_remote: bool = False
    apply_url: str = ""
    strengths: list = field(default_factory=list)
    missing_skills: list = field(default_factory=list)
    reason: str = ""
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    employment_type: str = ""


@dataclass
class RankingFilter:
    """Optional pre-ranking filters (all None = rank every valid job)."""

    min_match_score: Optional[int] = None
    min_trust_score: Optional[int] = None
    recommendation: Optional[str] = None
    employment_type: Optional[str] = None
    location: Optional[str] = None
    remote: Optional[bool] = None


@dataclass
class RankingPipelineResult:
    """Structured outcome of a ranking run (deterministic, no AI)."""

    jobs_received: int = 0
    jobs_ranked: int = 0
    jobs_excluded: int = 0  # invalid rows (missing/bad intelligence), counted
    ineligible_count: int = 0  # eligible_only runs: failed Latest-feed gates
    ranking_errors: list = field(default_factory=list)
    ranked_jobs: list = field(default_factory=list)

    def summary(self) -> dict:
        """Plain-dict summary (handy for logging and tests)."""
        return {
            "received": self.jobs_received,
            "ranked": self.jobs_ranked,
            "excluded": self.jobs_excluded,
            "ineligible": self.ineligible_count,
            "errors": len(self.ranking_errors),
        }

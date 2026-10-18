"""Intelligence models (Phase 5.2). Dataclasses, matching project style.

JobIntelligence is the validated unit produced per (profile, job): scores,
recommendation, skill sets, strengths/concerns, eligibility, and reason.
Recommendation/eligibility vocabularies are strict — anything else is
rejected by the validator, never persisted.
"""

from dataclasses import dataclass, field
from typing import Optional

# Strict vocabularies (validator enforces exact membership).
RECOMMENDATIONS = ("APPLY", "CONSIDER", "REVIEW", "AVOID")
ELIGIBILITIES = ("ELIGIBLE", "LIKELY_ELIGIBLE", "UNCERTAIN", "NOT_ELIGIBLE")

MIN_SCORE = 0
MAX_SCORE = 100


@dataclass
class JobIntelligence:
    """Validated intelligence for one (profile, job) pair."""

    match_score: int = 0
    trust_score: int = 0
    recommendation: str = "REVIEW"
    matching_skills: list = field(default_factory=list)
    missing_skills: list = field(default_factory=list)
    strengths: list = field(default_factory=list)
    concerns: list = field(default_factory=list)
    eligibility: str = "UNCERTAIN"
    reason: str = ""


@dataclass
class PrefilterResult:
    """Deterministic rule-engine outcome deciding whether AI is warranted."""

    eligible_for_ai: bool = False
    reasons: list = field(default_factory=list)
    flags: list = field(default_factory=list)
    preliminary_match: Optional[int] = None
    preliminary_trust: Optional[int] = None


@dataclass
class IntelligencePipelineResult:
    """Structured outcome of an intelligence run (counts + errors)."""

    jobs_received: int = 0
    jobs_prefiltered: int = 0  # passed the rules, AI candidates
    jobs_sent_to_ai: int = 0
    jobs_rejected_by_rules: int = 0
    jobs_analyzed: int = 0  # scored fresh + reused from cache
    matches_saved: int = 0  # newly inserted rows
    matches_updated: int = 0  # refreshed existing rows
    cached_results: int = 0  # reused without an AI call
    skipped_mock: int = 0  # demo fixtures never consume quota
    jobs_would_analyze: int = 0  # dry-run only: eligible uncached jobs within cap
    errors: list = field(default_factory=list)
    recommendations: dict = field(default_factory=dict)

    def summary(self) -> dict:
        """Plain-dict summary (handy for logging and tests)."""
        return {
            "received": self.jobs_received,
            "prefiltered": self.jobs_prefiltered,
            "sent_to_ai": self.jobs_sent_to_ai,
            "rejected": self.jobs_rejected_by_rules,
            "analyzed": self.jobs_analyzed,
            "saved": self.matches_saved,
            "updated": self.matches_updated,
            "cached": self.cached_results,
            "skipped_mock": self.skipped_mock,
            "would_analyze": self.jobs_would_analyze,
            "errors": len(self.errors),
        }

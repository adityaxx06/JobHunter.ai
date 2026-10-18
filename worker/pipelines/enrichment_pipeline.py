"""Post-ingestion enrichment: intelligence -> ranking (Phase 6.2).

Explicit stage composing the two existing Phase 5 pipelines, nothing more:

    persisted jobs
      -> run_intelligence (prefilter -> Gemini -> job_matches; unchanged defaults)
      -> rank_jobs_for_profile (stored intelligence -> ranked list; zero AI)

The ingestion pipeline stays AI-free (this module never imports search,
discovery sources, or ingestion — it consumes the database only). Ranking always reads
STORED intelligence, so it still runs usefully when the intelligence step
is gated off (AI disabled) or partially failed. Dry run previews selection
with zero AI calls and zero writes, and skips ranking (preview only).
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from worker.models.intelligence import IntelligencePipelineResult
from worker.models.ranking import RankingPipelineResult
from worker.pipelines.intelligence_pipeline import run_intelligence
from worker.pipelines.ranking_pipeline import rank_jobs_for_profile

logger = logging.getLogger("ai-jobhunter.enrichment")


@dataclass
class EnrichmentResult:
    """Structured outcome of one enrichment run (intelligence + ranking)."""

    profile_id: str = ""
    dry_run: bool = False
    intelligence: IntelligencePipelineResult = field(default_factory=IntelligencePipelineResult)
    ranking: Optional[RankingPipelineResult] = None
    ranking_skipped: str = ""

    @property
    def gemini_calls(self) -> int:
        """Billable AI calls made (dry run is always 0)."""
        return 0 if self.dry_run else self.intelligence.jobs_sent_to_ai

    @property
    def intelligence_writes(self) -> int:
        """job_matches rows created or refreshed."""
        if self.dry_run:
            return 0
        return self.intelligence.matches_saved + self.intelligence.matches_updated

    def summary(self) -> dict:
        """Plain-dict summary (handy for logging, CLI, and tests)."""
        ranked = len(self.ranking.ranked_jobs) if self.ranking else 0
        return {
            "profile": self.profile_id,
            "dry_run": self.dry_run,
            "received": self.intelligence.jobs_received,
            "rejected": self.intelligence.jobs_rejected_by_rules,
            "eligible": self.intelligence.jobs_prefiltered,
            "cached": self.intelligence.cached_results,
            "sent_to_ai": self.gemini_calls,
            "would_analyze": self.intelligence.jobs_would_analyze,
            "analyzed": self.intelligence.jobs_analyzed,
            "writes": self.intelligence_writes,
            "ranked": ranked,
            "ranking_skipped": self.ranking_skipped,
            "errors": len(self.intelligence.errors),
        }


def run_enrichment(profile_id: Optional[str] = None, job_limit: int = 50,
                   dry_run: bool = False, run_ranking: bool = True,
                   ranking_limit: int = 20, provider=None,
                   max_ai_jobs: Optional[int] = None,
                   refresh: bool = False) -> EnrichmentResult:
    """Run intelligence (existing) then ranking (existing) for one profile.

    Never raises on job-level failures — both stages isolate per-job errors
    internally and the combined summary always reports what happened.
    """
    outcome = EnrichmentResult(profile_id=profile_id or "", dry_run=bool(dry_run))
    outcome.intelligence = run_intelligence(
        profile_id=profile_id,
        job_limit=job_limit,
        provider=provider,
        refresh=refresh,
        max_ai_jobs=max_ai_jobs,
        dry_run=outcome.dry_run,
    )
    if outcome.dry_run:
        outcome.ranking_skipped = "dry run previews selection only"
        return outcome
    if not run_ranking:
        outcome.ranking_skipped = "ranking disabled for this run (--no-rank)"
        return outcome
    try:
        outcome.ranking = rank_jobs_for_profile(profile_id=profile_id, limit=ranking_limit)
        if outcome.ranking.ranked_jobs and not outcome.profile_id:
            outcome.profile_id = outcome.ranking.ranked_jobs[0].profile_id
    except Exception as exc:  # defensive: ranking must never break enrichment
        outcome.ranking = None
        outcome.ranking_skipped = f"ranking failed: {type(exc).__name__}"
        logger.warning("enrichment ranking failed: %s", exc)
    return outcome

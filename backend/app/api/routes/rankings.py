"""Ranking endpoint (Phase 5.4). THE read path for the future dashboard.

Route -> ranking service -> existing worker ranking pipeline (repository +
deterministic scorer) -> database. Nothing here scores, discovers, writes,
or calls Gemini — Gemini calls during ranking requests are architecturally
impossible (the imported pipeline never touches the AI providers).
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import db_unavailable
from app.schemas.jobs import RankedJobResponse, RankingResponse
from app.services import ranking_service as service

router = APIRouter()


@router.get("/rankings/{profile_id}", response_model=RankingResponse)
def get_ranking(profile_id: UUID, limit: int = Query(20, ge=1, le=100),
                min_match_score: Optional[int] = Query(None, ge=0, le=100),
                min_trust_score: Optional[int] = Query(None, ge=0, le=100),
                recommendation: Optional[str] = Query(None, pattern="^(APPLY|CONSIDER|REVIEW|AVOID)$"),
                employment_type: Optional[str] = None,
                location: Optional[str] = None,
                remote: Optional[bool] = None,
                eligible_only: bool = Query(False)) -> RankingResponse:
    """Deterministically ranked opportunities for a profile (zero AI calls).

    With ``eligible_only=true``, only Latest-feed-eligible rows (fresh,
    geography-fit, role-fit) rank; ineligible rows are counted, not ranked.
    """
    ranking_filter = service.build_filter(
        min_match_score=min_match_score, min_trust_score=min_trust_score,
        recommendation=recommendation, employment_type=employment_type,
        location=location, remote=remote,
    )
    try:
        result = service.rank_jobs_for_profile(
            str(profile_id), limit=limit, filters=ranking_filter,
            eligible_only=eligible_only)
    except Exception as exc:
        raise db_unavailable(exc)
    for error in result.ranking_errors:
        if "database not configured" in error:
            raise HTTPException(status_code=503, detail="database not configured")
    if any("no candidate profile" in error for error in result.ranking_errors):
        raise HTTPException(status_code=404, detail="profile not found")
    items = [
        RankedJobResponse(
            rank=ranked.rank, job_id=ranked.job_id, title=ranked.title or None,
            company=ranked.company_name or None, location=ranked.location or None,
            match_score=ranked.match_score, trust_score=ranked.trust_score,
            recommendation=ranked.recommendation, ranking_score=ranked.ranking_score,
            strengths=list(ranked.strengths or []), missing_skills=list(ranked.missing_skills or []),
            reason=ranked.reason or None,
            reasons=[str(reason) for reason in (ranked.priority_reasons or []) if str(reason).strip()],
            apply_url=ranked.apply_url or None,
            salary_min=ranked.salary_min, salary_max=ranked.salary_max,
            salary_currency=ranked.salary_currency, is_remote=ranked.is_remote,
            employment_type=ranked.employment_type or None,
        )
        for ranked in result.ranked_jobs
    ]
    return RankingResponse(profile_id=profile_id, items=items, limit=limit, count=result.jobs_ranked)

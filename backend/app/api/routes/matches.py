"""Analyzed-matches endpoint (Phase 5.4). Stored evaluations only.

Reads the existing ``job_matches`` rows via the repository — never triggers
analysis and never calls Gemini.
"""

from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import db_unavailable
from app.db.repositories import matches as repo
from app.schemas.jobs import MatchListItem, MatchListResponse

router = APIRouter()


@router.get("/matches/{profile_id}", response_model=MatchListResponse)
def list_matches(profile_id: UUID, limit: int = Query(20, ge=1, le=100),
                 offset: int = Query(0, ge=0)) -> MatchListResponse:
    """Paged stored match evaluations for a profile."""
    try:
        rows = repo.list_profile_matches(str(profile_id), limit, offset)
        total = repo.count_profile_matches(str(profile_id))
    except Exception as exc:
        raise db_unavailable(exc)
    items = [
        MatchListItem(
            job_id=row["job_id"], title=row.get("title"), company=row.get("company_name"),
            location=row.get("location"), match_score=row.get("match_score"),
            trust_score=row.get("trust_score"), recommendation=row.get("recommendation"),
            strengths=list(row.get("strengths") or []) if isinstance(row.get("strengths"), list) else [],
            missing_skills=list(row.get("missing_skills") or []) if isinstance(row.get("missing_skills"), list) else [],
            reason=row.get("reason"), apply_url=row.get("apply_url"),
        )
        for row in rows
    ]
    return MatchListResponse(profile_id=profile_id, items=items, limit=limit, offset=offset, count=total)

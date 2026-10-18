"""Jobs endpoints (Phase 5.4 list/detail + Phase 5.5C explorer filters).

Read-only persisted jobs. The list endpoint supports server-side search,
filters, whitelisted sorting, and pagination — the browser never downloads
the full dataset. Intelligence columns/filters/sorts require ``profile_id``
(they read that profile's ``job_matches``); otherwise those fields are null.
No AI scoring, no Gemini, no discovery here.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import db_unavailable
from app.db.repositories import jobs as repo
from app.db.repositories import matches as matches_repo
from app.schemas.jobs import JobDetail, JobIntelligenceResponse, JobListItem, JobListResponse

router = APIRouter()


def _primary_source(sources: list) -> Optional[str]:
    """Earliest discovery source type (None when never sourced)."""
    if not sources:
        return None
    return sources[0].get("source_type")


def _as_string_list(value) -> list[str]:
    return list(value) if isinstance(value, list) else []


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(limit: int = Query(20, ge=1, le=50),
              offset: int = Query(0, ge=0),
              profile_id: Optional[str] = None,
              search: Optional[str] = Query(None, max_length=100),
              role: Optional[str] = Query(None, max_length=100),
              location: Optional[str] = Query(None, max_length=100),
              remote: Optional[bool] = None,
              min_match: Optional[int] = Query(None, ge=0, le=100),
              min_trust: Optional[int] = Query(None, ge=0, le=100),
              recommendation: Optional[str] = Query(None, pattern="^(APPLY|CONSIDER|REVIEW|AVOID)$"),
              employment_type: Optional[str] = Query(None, max_length=50),
              sort: str = Query("newest", pattern="^(match|trust|newest)$")) -> JobListResponse:
    """Paged, filtered, sorted jobs. Intelligence params need ``profile_id``."""
    needs_profile = (
        min_match is not None or min_trust is not None or recommendation is not None
        or sort in ("match", "trust")
    )
    if needs_profile and not profile_id:
        raise HTTPException(
            status_code=422,
            detail="min_match, min_trust, recommendation, and match/trust sorting require profile_id",
        )
    if profile_id:
        try:
            UUID(profile_id)
        except (ValueError, AttributeError, TypeError):
            raise HTTPException(status_code=422, detail="invalid profile_id")
    try:
        rows = repo.search_jobs_page(
            limit, offset, search=search, role=role, location=location,
            remote=remote, min_match=min_match, min_trust=min_trust,
            recommendation=recommendation, employment_type=employment_type,
            sort=sort, profile_id=profile_id)
        total = repo.count_search_jobs(
            search=search, role=role, location=location, remote=remote,
            min_match=min_match, min_trust=min_trust, recommendation=recommendation,
            employment_type=employment_type, profile_id=profile_id)
    except Exception as exc:
        raise db_unavailable(exc)
    items = []
    for row in rows:
        try:
            sources = repo.list_job_sources(row["id"])
        except Exception:
            sources = []
        items.append(JobListItem(
            id=row["id"], title=row.get("title") or "",
            company=row.get("company_name"), location=row.get("location"),
            is_remote=row.get("is_remote"), employment_type=row.get("employment_type"),
            apply_url=row.get("apply_url"),
            source=_primary_source(sources),
            salary_min=row.get("salary_min"), salary_max=row.get("salary_max"),
            salary_currency=row.get("salary_currency"),
            match_score=row.get("match_score"), trust_score=row.get("trust_score"),
            recommendation=row.get("recommendation"),
            strengths=_as_string_list(row.get("strengths")),
            missing_skills=_as_string_list(row.get("missing_skills")),
            reason=row.get("reason"),
            posted_at=row.get("posted_at"),
            created_at=row.get("created_at"), updated_at=row.get("updated_at"),
        ))
    return JobListResponse(items=items, limit=limit, offset=offset, count=total)


@router.get("/jobs/{job_id}", response_model=JobDetail)
def get_job_detail(job_id: UUID, profile_id: Optional[UUID] = None) -> JobDetail:
    """One persisted job plus its stored intelligence for ``profile_id`` (null when unanalyzed)."""
    try:
        row = repo.get_job(str(job_id))
    except Exception as exc:
        raise db_unavailable(exc)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    try:
        sources = repo.list_job_sources(str(job_id))
    except Exception:
        sources = []
    intelligence = None
    if profile_id is not None:
        try:
            match = matches_repo.get_match(str(profile_id), str(job_id))
        except Exception as exc:
            raise db_unavailable(exc)
        if match is not None and match.get("match_score") is not None:
            intelligence = JobIntelligenceResponse(
                match_score=match.get("match_score"), trust_score=match.get("trust_score"),
                recommendation=match.get("recommendation"),
                strengths=list(match.get("strengths") or []) if isinstance(match.get("strengths"), list) else [],
                missing_skills=list(match.get("missing_skills") or []) if isinstance(match.get("missing_skills"), list) else [],
                reason=match.get("reason"),
            )
    skills = row.get("skills")
    return JobDetail(
        id=row["id"], title=row.get("title") or "", company=row.get("company_name"),
        location=row.get("location"), is_remote=row.get("is_remote"),
        employment_type=row.get("employment_type"),
        description=row.get("description"),
        skills=list(skills) if isinstance(skills, list) else [],
        salary_min=row.get("salary_min"), salary_max=row.get("salary_max"),
        currency=row.get("salary_currency"), apply_url=row.get("apply_url"),
        posted_at=row.get("posted_at"),
        source=_primary_source(sources), intelligence=intelligence,
    )

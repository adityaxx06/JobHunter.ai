"""Application-tracker endpoints (Phase 5.4 list + Phase 5.5E write paths).

List reads plus minimal create/patch for the tracker UI. Writes are scoped
to (profile_id, job_id); duplicates return the existing row. Status
vocabulary comes from the database CHECK constraint — nothing invented.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import db_unavailable
from app.db.repositories import applications as repo
from app.db.repositories import jobs as jobs_repo
from app.schemas.jobs import (
    ApplicationCreate,
    ApplicationListItem,
    ApplicationListResponse,
    ApplicationUpdate,
)

router = APIRouter()

APPLICATION_STATUSES = ("saved", "applied", "assessment", "interview", "offer", "rejected", "withdrawn")


def _to_item(row: dict) -> ApplicationListItem:
    """Map a joined tracker row (missing job tolerated — never crash)."""
    return ApplicationListItem(
        id=row["id"], job_id=row["job_id"],
        title=row.get("title"), company=row.get("company_name"),
        location=row.get("location"), is_remote=row.get("is_remote"),
        employment_type=row.get("employment_type"), status=row.get("status"),
        applied_at=row.get("applied_at"), notes=row.get("notes"),
        apply_url=row.get("apply_url"), updated_at=row.get("updated_at"),
    )


@router.get("/applications/{profile_id}", response_model=ApplicationListResponse)
def list_applications(profile_id: UUID, limit: int = Query(20, ge=1, le=100),
                      offset: int = Query(0, ge=0),
                      status: Optional[str] = Query(None, pattern="^(saved|applied|assessment|interview|offer|rejected|withdrawn)$")
                      ) -> ApplicationListResponse:
    """Paged tracker rows for a profile, optionally one status."""
    try:
        rows = repo.list_applications(str(profile_id), limit, offset, status)
        total = repo.count_applications(str(profile_id), status)
    except Exception as exc:
        raise db_unavailable(exc)
    items = [_to_item(row) for row in rows]
    return ApplicationListResponse(profile_id=profile_id, items=items, limit=limit, offset=offset, count=total)


@router.get("/applications/{profile_id}/{job_id}", response_model=ApplicationListItem)
def get_application(profile_id: UUID, job_id: UUID) -> ApplicationListItem:
    """One tracker row with job context (404 when not tracked)."""
    try:
        row = repo.get_application(str(profile_id), str(job_id))
        if row is None:
            raise HTTPException(status_code=404, detail="application not found")
        job = jobs_repo.get_job(str(job_id))
    except HTTPException:
        raise
    except Exception as exc:
        raise db_unavailable(exc)
    merged = dict(row)
    if job is not None:
        merged.update({key: job.get(key) for key in
                       ("title", "location", "is_remote", "employment_type", "apply_url")})
        merged["company_name"] = job.get("company_name")
    return _to_item(merged)


@router.post("/applications/{profile_id}", response_model=ApplicationListItem,
             status_code=status.HTTP_201_CREATED)
def create_application(profile_id: UUID, payload: ApplicationCreate):
    """Track a job (duplicate profile+job returns the existing row with 200)."""
    from fastapi.responses import JSONResponse

    try:
        if jobs_repo.get_job(str(payload.job_id)) is None:
            raise HTTPException(status_code=404, detail="job not found")
        existing = repo.get_application(str(profile_id), str(payload.job_id))
        if existing is not None:
            item = _enriched(profile_id, payload.job_id, existing)
            return JSONResponse(status_code=status.HTTP_200_OK,
                                content=item.model_dump(mode="json"))
        row = repo.create_application(str(profile_id), str(payload.job_id),
                                      status=payload.status, notes=payload.notes)
    except HTTPException:
        raise
    except Exception as exc:
        raise db_unavailable(exc)
    if row is None:  # lost a race with another create — return the winner
        existing = repo.get_application(str(profile_id), str(payload.job_id))
        if existing is None:
            raise HTTPException(status_code=500, detail="could not create application")
        return _enriched(profile_id, payload.job_id, existing)
    return _created(profile_id, payload.job_id, row)


def _enriched(profile_id: UUID, job_id: UUID, row: dict) -> ApplicationListItem:
    """Attach job context to a bare tracker row (duplicate path)."""
    try:
        job = jobs_repo.get_job(str(job_id))
    except Exception as exc:
        raise db_unavailable(exc)
    merged = dict(row)
    if job is not None:
        merged.update({key: job.get(key) for key in
                       ("title", "location", "is_remote", "employment_type", "apply_url")})
        merged["company_name"] = job.get("company_name")
    return _to_item(merged)


def _created(profile_id: UUID, job_id: UUID, row: dict):
    """201 wrapper that keeps the duplicate path importable for tests."""
    from fastapi.responses import JSONResponse

    item = _enriched(profile_id, job_id, row)
    return JSONResponse(status_code=status.HTTP_201_CREATED,
                        content=item.model_dump(mode="json"))


@router.patch("/applications/{profile_id}/{job_id}", response_model=ApplicationListItem)
def update_application(profile_id: UUID, job_id: UUID,
                       payload: ApplicationUpdate) -> ApplicationListItem:
    """Change status and/or notes (404 when not tracked; applied_at set once)."""
    try:
        row = repo.update_application(
            str(profile_id), str(job_id),
            status=payload.status,
            notes=payload.notes if "notes" in payload.model_fields_set else repo.UNCHANGED,
        )
    except Exception as exc:
        raise db_unavailable(exc)
    if row is None:
        raise HTTPException(status_code=404, detail="application not found")
    return _enriched(profile_id, job_id, row)

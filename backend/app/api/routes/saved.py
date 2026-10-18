"""Saved-jobs endpoints (Phase 5.5B, additive).

Minimal REST over the existing ``saved_jobs`` table for the dashboard Save
button: list saved IDs, save (idempotent), unsave. UUID path params yield
422 when malformed; unknown saves yield 404 on delete.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import db_unavailable
from app.db.repositories import saved as repo
from app.schemas.jobs import SavedJobIdsResponse, SavedJobResponse

router = APIRouter()


@router.get("/saved-jobs/{profile_id}", response_model=SavedJobIdsResponse)
def list_saved(profile_id: UUID) -> SavedJobIdsResponse:
    """Job IDs saved by a profile (for Save-button initial state)."""
    try:
        ids = repo.list_saved_job_ids(str(profile_id))
    except Exception as exc:
        raise db_unavailable(exc)
    return SavedJobIdsResponse(profile_id=profile_id, job_ids=ids)


@router.post("/saved-jobs/{profile_id}/{job_id}", response_model=SavedJobResponse,
             status_code=status.HTTP_201_CREATED)
def save(profile_id: UUID, job_id: UUID) -> SavedJobResponse:
    """Save a job (re-saving the same job stays saved — no duplicates)."""
    try:
        row = repo.save_job(str(profile_id), str(job_id))
    except Exception as exc:
        raise db_unavailable(exc)
    if row is None:
        # ON CONFLICT DO NOTHING returned nothing: already saved.
        return SavedJobResponse(profile_id=profile_id, job_id=job_id, saved=True)
    return SavedJobResponse(profile_id=profile_id, job_id=job_id, saved=True)


@router.delete("/saved-jobs/{profile_id}/{job_id}", response_model=SavedJobResponse)
def unsave(profile_id: UUID, job_id: UUID) -> SavedJobResponse:
    """Remove a save (404 when the job was never saved)."""
    try:
        row = repo.unsave_job(str(profile_id), str(job_id))
    except Exception as exc:
        raise db_unavailable(exc)
    if row is None:
        raise HTTPException(status_code=404, detail="job not saved")
    return SavedJobResponse(profile_id=profile_id, job_id=job_id, saved=False)

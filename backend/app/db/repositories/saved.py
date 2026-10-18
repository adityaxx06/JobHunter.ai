"""Saved-jobs repository (Phase 5.5B, additive).

Thin parameterized access over the existing ``saved_jobs`` table
(UNIQUE(profile_id, job_id) — re-saving is a no-op, never a duplicate).
No schema change; follows the existing repository conventions.
"""

from typing import Optional

from app.db import connection as db


def list_saved_job_ids(profile_id: str) -> list[str]:
    """Job IDs the profile saved, newest first."""
    rows = db.fetch_all(
        """SELECT job_id FROM public.saved_jobs
           WHERE profile_id = %s
           ORDER BY created_at DESC""",
        (profile_id,),
    )
    return [str(row["job_id"]) for row in (rows or []) if row.get("job_id")]


def save_job(profile_id: str, job_id: str) -> Optional[dict]:
    """Save a job (idempotent — existing save is returned unchanged)."""
    return db.execute(
        """INSERT INTO public.saved_jobs (profile_id, job_id)
           VALUES (%s, %s)
           ON CONFLICT (profile_id, job_id) DO NOTHING
           RETURNING id, profile_id, job_id, created_at""",
        (profile_id, job_id),
    )


def unsave_job(profile_id: str, job_id: str) -> Optional[dict]:
    """Remove a save (None when there was nothing saved)."""
    return db.execute(
        """DELETE FROM public.saved_jobs
           WHERE profile_id = %s AND job_id = %s
           RETURNING id""",
        (profile_id, job_id),
    )

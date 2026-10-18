"""Application-tracker repository (Phase 3; extended Phase 5.5E).

One row per profile+job (UNIQUE). Writes use parameterized SQL only;
``updated_at`` is maintained by the database trigger.
"""

from typing import Optional

from app.db import connection as db

_APP_COLS = (
    "id, profile_id, job_id, status, applied_at, notes, created_at, updated_at"
)

#: Sentinel distinguishing "notes not provided" from "notes set to null".
UNCHANGED: object = object()


def get_application(profile_id: str, job_id: str) -> Optional[dict]:
    """Fetch one tracker row (None when absent)."""
    return db.fetch_one(
        f"""SELECT {_APP_COLS} FROM public.applications
            WHERE profile_id = %s AND job_id = %s""",
        (profile_id, job_id),
    )


def create_application(
    profile_id: str,
    job_id: str,
    status: str = "saved",
    notes: Optional[str] = None,
) -> Optional[dict]:
    """Create a tracker row (existing row for profile+job is returned)."""
    return db.execute(
        f"""INSERT INTO public.applications (profile_id, job_id, status, notes)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (profile_id, job_id) DO NOTHING
            RETURNING {_APP_COLS}""",
        (profile_id, job_id, status, notes),
    )


def update_application_status(
    profile_id: str,
    job_id: str,
    status: str,
    notes: Optional[str] = None,
) -> Optional[dict]:
    """Transition a tracker row to a new status (sets applied_at on 'applied')."""
    if notes is None:
        return db.execute(
            f"""UPDATE public.applications
                SET status = %s,
                    applied_at = CASE WHEN %s = 'applied' THEN COALESCE(applied_at, NOW())
                                      ELSE applied_at END
                WHERE profile_id = %s AND job_id = %s
                RETURNING {_APP_COLS}""",
            (status, status, profile_id, job_id),
        )
    return db.execute(
        f"""UPDATE public.applications
            SET status = %s, notes = %s,
                applied_at = CASE WHEN %s = 'applied' THEN COALESCE(applied_at, NOW())
                                  ELSE applied_at END
            WHERE profile_id = %s AND job_id = %s
            RETURNING {_APP_COLS}""",
        (status, notes, status, profile_id, job_id),
    )


def update_application(profile_id: str, job_id: str, status: Optional[str] = None,
                       notes: object = UNCHANGED) -> Optional[dict]:
    """Update only provided fields (None = row absent). ``applied_at`` is set
    the first time a row transitions to 'applied', never overwritten after."""
    sets: list[str] = []
    params: list = []
    if status is not None:
        sets.append("status = %s")
        params.append(status)
        sets.append("applied_at = CASE WHEN %s = 'applied' THEN COALESCE(applied_at, NOW()) "
                    "ELSE applied_at END")
        params.append(status)
    if notes is not UNCHANGED:
        sets.append("notes = %s")
        params.append(notes)
    if not sets:
        return get_application(profile_id, job_id)
    params.extend([profile_id, job_id])
    return db.execute(
        f"""UPDATE public.applications SET {", ".join(sets)}
            WHERE profile_id = %s AND job_id = %s
            RETURNING {_APP_COLS}""",
        tuple(params),
    )


def list_applications(profile_id: str, limit: int = 100, offset: int = 0,
                        status: Optional[str] = None) -> list:
    """Tracker rows for a profile with job info, newest first (Phase 5.4: paged + status filter)."""
    safe_limit = max(1, min(int(limit), 100))
    safe_offset = max(0, int(offset))
    cols = ("a.id, a.profile_id, a.job_id, a.status, a.applied_at, a.notes, "
            "a.created_at, a.updated_at, j.title, j.location, j.is_remote, "
            "j.employment_type, j.apply_url, c.name AS company_name")
    base = (f"""SELECT {cols} FROM public.applications a
               JOIN public.jobs j ON j.id = a.job_id
               LEFT JOIN public.companies c ON c.id = j.company_id
               WHERE a.profile_id = %s""")
    if status is None:
        return db.fetch_all(
            base + " ORDER BY a.updated_at DESC LIMIT %s OFFSET %s",
            (profile_id, safe_limit, safe_offset),
        )
    return db.fetch_all(
        base + " AND a.status = %s ORDER BY a.updated_at DESC LIMIT %s OFFSET %s",
        (profile_id, status, safe_limit, safe_offset),
    )


def count_applications(profile_id: str, status: Optional[str] = None) -> int:
    """Total tracker rows for a profile (optionally one status)."""
    if status is None:
        row = db.fetch_one(
            "SELECT COUNT(*) AS total FROM public.applications WHERE profile_id = %s",
            (profile_id,),
        )
    else:
        row = db.fetch_one(
            "SELECT COUNT(*) AS total FROM public.applications WHERE profile_id = %s AND status = %s",
            (profile_id, status),
        )
    return int((row or {}).get("total") or 0)

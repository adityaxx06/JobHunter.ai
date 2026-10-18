"""Worker-side candidate-profile reads (Phase 5.2). Read-only SELECTs.

Loads the single source of truth — profiles/profile_skills/target_roles/
target_locations — into the candidate payload the prompt builder expects.
Hardcoded values appear only in tests, never here. Parameterized SQL only.
"""

from typing import Optional

from worker.db import client as db


def get_profile(profile_id: Optional[str] = None) -> Optional[dict]:
    """Fetch one profile (the first when id is None — single-user MVP)."""
    if profile_id:
        return db.fetch_one(
            """SELECT id, user_id, full_name, education, experience_level,
                      preferred_work_mode, relocation_allowed, minimum_stipend
               FROM public.profiles WHERE id = %s""",
            (profile_id,),
        )
    return db.fetch_one(
        """SELECT id, user_id, full_name, education, experience_level,
                  preferred_work_mode, relocation_allowed, minimum_stipend
           FROM public.profiles ORDER BY created_at ASC LIMIT 1"""
    )


def list_skills(profile_id: str) -> tuple:
    """(owned skills, learning skills) as name lists."""
    rows = db.fetch_all(
        """SELECT skill_name, skill_level, is_learning FROM public.profile_skills
           WHERE profile_id = %s ORDER BY skill_name ASC""",
        (profile_id,),
    )
    owned, learning = [], []
    for row in rows or []:
        name = (row.get("skill_name") or "").strip()
        if not name:
            continue
        (learning if row.get("is_learning") else owned).append(name)
    return owned, learning


def list_target_roles(profile_id: str) -> list:
    """Wanted role names, highest priority first."""
    rows = db.fetch_all(
        """SELECT role_name FROM public.target_roles
           WHERE profile_id = %s ORDER BY priority ASC, role_name ASC""",
        (profile_id,),
    )
    return [(r.get("role_name") or "").strip() for r in (rows or []) if (r.get("role_name") or "").strip()]


def list_target_locations(profile_id: str) -> tuple:
    """(location names, remote_ok) — remote tracked via the is_remote flag."""
    rows = db.fetch_all(
        """SELECT location_name, is_remote FROM public.target_locations
           WHERE profile_id = %s ORDER BY priority ASC, location_name ASC""",
        (profile_id,),
    )
    names = [(r.get("location_name") or "").strip() for r in (rows or []) if (r.get("location_name") or "").strip()]
    return names, any(r.get("is_remote") for r in (rows or []))


def load_candidate(profile_id: Optional[str] = None) -> Optional[dict]:
    """Assemble the prompt-ready candidate payload (None when no profile)."""
    profile = get_profile(profile_id)
    if profile is None:
        return None
    skills, learning = list_skills(profile["id"])
    locations, remote_ok = list_target_locations(profile["id"])
    return {
        "profile_id": profile["id"],
        "education": profile.get("education") or "Unknown",
        "status": profile.get("experience_level") or "Unknown",
        "skills": skills,
        "learning": learning,
        "target_roles": list_target_roles(profile["id"]),
        "target_locations": locations,
        "locations": locations,  # alias the prefilter reads
        "remote_ok": bool(remote_ok),
        "relocation_ok": bool(profile.get("relocation_allowed", True)),
    }

"""Profile repository: profiles + skills + target roles/locations (Phase 3).

All statements are parameterized (values passed as params, never formatted
into SQL text).
"""

from typing import Optional

from app.db import connection as db

_PROFILE_COLS = (
    "id, user_id, full_name, education, experience_level, "
    "preferred_work_mode, relocation_allowed, minimum_stipend, "
    "created_at, updated_at"
)


def get_profile(profile_id: str) -> Optional[dict]:
    """Fetch one profile by id (None when not found)."""
    return db.fetch_one(
        f"SELECT {_PROFILE_COLS} FROM public.profiles WHERE id = %s",
        (profile_id,),
    )


def create_profile(
    full_name: Optional[str] = None,
    education: Optional[str] = None,
    experience_level: Optional[str] = None,
    preferred_work_mode: Optional[str] = None,
    relocation_allowed: bool = True,
    minimum_stipend: Optional[int] = None,
    user_id: Optional[str] = None,
) -> Optional[dict]:
    """Insert a profile and return the new row."""
    return db.execute(
        """INSERT INTO public.profiles
           (full_name, education, experience_level, preferred_work_mode,
            relocation_allowed, minimum_stipend, user_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           RETURNING id, user_id, full_name, education, experience_level,
                     preferred_work_mode, relocation_allowed, minimum_stipend,
                     created_at, updated_at""",
        (
            full_name,
            education,
            experience_level,
            preferred_work_mode,
            relocation_allowed,
            minimum_stipend,
            user_id,
        ),
    )


def update_profile(profile_id: str, **fields) -> Optional[dict]:
    """Update allowed profile columns; returns the updated row (or None)."""
    allowed = {
        "full_name",
        "education",
        "experience_level",
        "preferred_work_mode",
        "relocation_allowed",
        "minimum_stipend",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_profile(profile_id)
    names = list(updates.keys())
    set_clause = ", ".join(f"{name} = %s" for name in names)
    params = [updates[name] for name in names] + [profile_id]
    return db.execute(
        f"""UPDATE public.profiles SET {set_clause}
            WHERE id = %s
            RETURNING {_PROFILE_COLS}""",
        tuple(params),
    )


def list_profile_skills(profile_id: str) -> list:
    """All skills for a profile, owned first then learning."""
    return db.fetch_all(
        """SELECT id, profile_id, skill_name, skill_level, is_learning, created_at
           FROM public.profile_skills
           WHERE profile_id = %s
           ORDER BY is_learning ASC, skill_name ASC""",
        (profile_id,),
    )


def add_profile_skill(
    profile_id: str,
    skill_name: str,
    skill_level: Optional[str] = None,
    is_learning: bool = False,
) -> Optional[dict]:
    """Add a skill (existing skill for the profile is returned unchanged)."""
    return db.execute(
        """INSERT INTO public.profile_skills (profile_id, skill_name, skill_level, is_learning)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (profile_id, skill_name) DO NOTHING
           RETURNING id, profile_id, skill_name, skill_level, is_learning, created_at""",
        (profile_id, skill_name, skill_level, is_learning),
    )


def list_target_roles(profile_id: str) -> list:
    """Wanted roles for a profile, highest priority first."""
    return db.fetch_all(
        """SELECT id, profile_id, role_name, priority, created_at
           FROM public.target_roles
           WHERE profile_id = %s
           ORDER BY priority ASC, role_name ASC""",
        (profile_id,),
    )


def list_target_locations(profile_id: str) -> list:
    """Wanted locations for a profile, highest priority first."""
    return db.fetch_all(
        """SELECT id, profile_id, location_name, is_remote, priority, created_at
            FROM public.target_locations
            WHERE profile_id = %s
            ORDER BY priority ASC, location_name ASC""",
        (profile_id,),
    )


def remove_profile_skill(profile_id: str, skill_id: str) -> bool:
    """Delete one skill (profile-scoped). True when a row was removed."""
    row = db.execute(
        """DELETE FROM public.profile_skills
            WHERE id = %s AND profile_id = %s
            RETURNING id""",
        (skill_id, profile_id),
    )
    return row is not None


def update_profile_skill(
    profile_id: str,
    skill_id: str,
    skill_level: Optional[str] = None,
    is_learning: Optional[bool] = None,
) -> Optional[dict]:
    """Update a skill's level/learning status (profile-scoped, None when missing)."""
    updates = {}
    if skill_level is not None:
        updates["skill_level"] = skill_level
    if is_learning is not None:
        updates["is_learning"] = bool(is_learning)
    if not updates:
        return db.fetch_one(
            """SELECT id, profile_id, skill_name, skill_level, is_learning, created_at
                FROM public.profile_skills WHERE id = %s AND profile_id = %s""",
            (skill_id, profile_id),
        )
    names = list(updates.keys())
    set_clause = ", ".join(f"{name} = %s" for name in names)
    params = [updates[name] for name in names] + [skill_id, profile_id]
    return db.execute(
        f"""UPDATE public.profile_skills SET {set_clause}
            WHERE id = %s AND profile_id = %s
            RETURNING id, profile_id, skill_name, skill_level, is_learning, created_at""",
        tuple(params),
    )


def add_target_role(profile_id: str, role_name: str, priority: int = 1) -> Optional[dict]:
    """Add a role (duplicate name inserts nothing — caller resolves existing)."""
    return db.execute(
        """INSERT INTO public.target_roles (profile_id, role_name, priority)
            VALUES (%s, %s, %s)
            ON CONFLICT (profile_id, role_name) DO NOTHING
            RETURNING id, profile_id, role_name, priority, created_at""",
        (profile_id, role_name, priority),
    )


def remove_target_role(profile_id: str, role_id: str) -> bool:
    """Delete one role (profile-scoped). True when a row was removed."""
    row = db.execute(
        """DELETE FROM public.target_roles
            WHERE id = %s AND profile_id = %s
            RETURNING id""",
        (role_id, profile_id),
    )
    return row is not None


def update_target_role(
    profile_id: str,
    role_id: str,
    role_name: Optional[str] = None,
    priority: Optional[int] = None,
) -> Optional[dict]:
    """Rename a role and/or change priority (None when the role is missing)."""
    updates = {}
    if role_name is not None:
        updates["role_name"] = role_name
    if priority is not None:
        updates["priority"] = priority
    if not updates:
        return db.fetch_one(
            """SELECT id, profile_id, role_name, priority, created_at
                FROM public.target_roles WHERE id = %s AND profile_id = %s""",
            (role_id, profile_id),
        )
    names = list(updates.keys())
    set_clause = ", ".join(f"{name} = %s" for name in names)
    params = [updates[name] for name in names] + [role_id, profile_id]
    return db.execute(
        f"""UPDATE public.target_roles SET {set_clause}
            WHERE id = %s AND profile_id = %s
            RETURNING id, profile_id, role_name, priority, created_at""",
        tuple(params),
    )


def add_target_location(
    profile_id: str, location_name: str, is_remote: bool = False, priority: int = 1
) -> Optional[dict]:
    """Add a location (duplicate name inserts nothing — caller resolves existing)."""
    return db.execute(
        """INSERT INTO public.target_locations (profile_id, location_name, is_remote, priority)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (profile_id, location_name) DO NOTHING
            RETURNING id, profile_id, location_name, is_remote, priority, created_at""",
        (profile_id, location_name, bool(is_remote), priority),
    )


def remove_target_location(profile_id: str, location_id: str) -> bool:
    """Delete one location (profile-scoped). True when a row was removed."""
    row = db.execute(
        """DELETE FROM public.target_locations
            WHERE id = %s AND profile_id = %s
            RETURNING id""",
        (location_id, profile_id),
    )
    return row is not None


def update_target_location(
    profile_id: str,
    location_id: str,
    location_name: Optional[str] = None,
    is_remote: Optional[bool] = None,
    priority: Optional[int] = None,
) -> Optional[dict]:
    """Rename a location and/or change remote flag/priority (None when missing)."""
    updates = {}
    if location_name is not None:
        updates["location_name"] = location_name
    if is_remote is not None:
        updates["is_remote"] = bool(is_remote)
    if priority is not None:
        updates["priority"] = priority
    if not updates:
        return db.fetch_one(
            """SELECT id, profile_id, location_name, is_remote, priority, created_at
                FROM public.target_locations WHERE id = %s AND profile_id = %s""",
            (location_id, profile_id),
        )
    names = list(updates.keys())
    set_clause = ", ".join(f"{name} = %s" for name in names)
    params = [updates[name] for name in names] + [location_id, profile_id]
    return db.execute(
        f"""UPDATE public.target_locations SET {set_clause}
            WHERE id = %s AND profile_id = %s
            RETURNING id, profile_id, location_name, is_remote, priority, created_at""",
        tuple(params),
    )

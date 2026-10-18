"""Lightweight row shapes for the DB layer (Phase 3).

Plain dataclasses for readability at API boundaries. The repositories return
dicts from psycopg; these models document the important columns without
introducing a full ORM (no SQLAlchemy by design for this MVP).
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Profile:
    id: str
    user_id: Optional[str] = None
    full_name: Optional[str] = None
    education: Optional[str] = None
    experience_level: Optional[str] = None
    preferred_work_mode: Optional[str] = None
    relocation_allowed: bool = True
    minimum_stipend: Optional[int] = None


@dataclass
class Company:
    id: str
    name: str
    normalized_name: str
    website_url: Optional[str] = None
    careers_url: Optional[str] = None


@dataclass
class Job:
    id: str
    title: str
    company_id: Optional[str] = None
    location: Optional[str] = None
    apply_url: Optional[str] = None
    extra: dict = field(default_factory=dict)


@dataclass
class Match:
    profile_id: str
    job_id: str
    match_score: Optional[int] = None
    trust_score: Optional[int] = None
    recommendation: Optional[str] = None
    extra: dict = field(default_factory=dict)


@dataclass
class Application:
    profile_id: str
    job_id: str
    status: str = "saved"
    extra: dict = field(default_factory=dict)


def to_dict(obj: Any) -> dict:
    """Best-effort dataclass/dict normalizer for API responses."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "__dataclass_fields__"):
        import dataclasses

        return dataclasses.asdict(obj)
    return dict(obj)

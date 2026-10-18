"""Phase 5.4 API response models. Read shapes over existing tables only.

No new database columns are referenced anywhere here; every field maps to a
column the Phase 2 schema already provides.
"""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class JobListItem(BaseModel):
    """One row of the paged job list (intelligence fields present only when
    the request joined a profile's matches; otherwise null)."""

    id: UUID
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    is_remote: Optional[bool] = None
    employment_type: Optional[str] = None
    apply_url: Optional[str] = None
    source: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    match_score: Optional[int] = None
    trust_score: Optional[int] = None
    recommendation: Optional[str] = None
    strengths: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    reason: Optional[str] = None
    posted_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class JobListResponse(BaseModel):
    """Paged ``GET /api/jobs`` envelope."""

    items: list[JobListItem] = Field(default_factory=list)
    limit: int = 20
    offset: int = 0
    count: int = 0


class JobIntelligenceResponse(BaseModel):
    """Stored intelligence block inside the job detail (null when unanalyzed)."""

    match_score: int
    trust_score: int
    recommendation: str
    strengths: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    reason: Optional[str] = None


class JobDetail(BaseModel):
    """Full ``GET /api/jobs/{job_id}`` payload."""

    id: UUID
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    is_remote: Optional[bool] = None
    employment_type: Optional[str] = None
    description: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency: Optional[str] = None
    apply_url: Optional[str] = None
    posted_at: Optional[datetime] = None
    source: Optional[str] = None
    intelligence: Optional[JobIntelligenceResponse] = None


class MatchListItem(BaseModel):
    """One analyzed match for a profile."""

    job_id: UUID
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    match_score: Optional[int] = None
    trust_score: Optional[int] = None
    recommendation: Optional[str] = None
    strengths: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    reason: Optional[str] = None
    apply_url: Optional[str] = None


class MatchListResponse(BaseModel):
    """Paged ``GET /api/matches/{profile_id}`` envelope."""

    profile_id: UUID
    items: list[MatchListItem] = Field(default_factory=list)
    limit: int = 20
    offset: int = 0
    count: int = 0


class RankedJobResponse(BaseModel):
    """One entry of the deterministic ranking (Phase 5.3 scorer output)."""

    rank: int
    job_id: UUID
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    match_score: int
    trust_score: int
    recommendation: str
    ranking_score: float
    strengths: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    reason: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)
    apply_url: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    is_remote: Optional[bool] = None
    employment_type: Optional[str] = None


class RankingResponse(BaseModel):
    """``GET /api/rankings/{profile_id}`` envelope (zero AI calls)."""

    profile_id: UUID
    items: list[RankedJobResponse] = Field(default_factory=list)
    limit: int = 20
    count: int = 0


class ApplicationListItem(BaseModel):
    """One tracker row with its job context."""

    id: UUID
    job_id: UUID
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    is_remote: Optional[bool] = None
    employment_type: Optional[str] = None
    status: str
    applied_at: Optional[datetime] = None
    notes: Optional[str] = None
    apply_url: Optional[str] = None
    updated_at: Optional[datetime] = None


class ApplicationListResponse(BaseModel):
    """Paged ``GET /api/applications/{profile_id}`` envelope."""

    profile_id: UUID
    items: list[ApplicationListItem] = Field(default_factory=list)
    limit: int = 20
    offset: int = 0
    count: int = 0


class SavedJobIdsResponse(BaseModel):
    """Saved job IDs for a profile (Save-button initial state)."""

    profile_id: UUID
    job_ids: list[UUID] = Field(default_factory=list)


class SavedJobResponse(BaseModel):
    """Result of a save/unsave action."""

    profile_id: UUID
    job_id: UUID
    saved: bool


ApplicationStatus = Literal["saved", "applied", "assessment", "interview", "offer", "rejected", "withdrawn"]


class ApplicationCreate(BaseModel):
    """Body for creating a tracker row (duplicate profile+job returns existing)."""

    job_id: UUID
    status: ApplicationStatus = "applied"
    notes: Optional[str] = Field(None, max_length=5000)


class ApplicationUpdate(BaseModel):
    """Body for patching a tracker row (only provided fields change)."""

    status: Optional[ApplicationStatus] = None
    notes: Optional[str] = Field(None, max_length=5000)

    @model_validator(mode="after")
    def _require_a_change(self):
        if self.status is None and self.notes is None and "notes" not in self.model_fields_set:
            raise ValueError("provide status and/or notes")
        return self

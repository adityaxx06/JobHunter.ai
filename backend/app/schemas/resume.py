"""Phase 7B resume parse response models. Persistable subset mirrors the
existing profile tables; everything else (email/phone/summary/experience
detail) is display-only and never written to the profile.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ResumeExperience(BaseModel):
    """One work/education-adjacent entry (display only)."""

    title: str = Field(max_length=200)
    organization: Optional[str] = Field(None, max_length=200)
    duration: Optional[str] = Field(None, max_length=100)


class ResumeSkill(BaseModel):
    """One extracted skill (maps to profile_skills on approval)."""

    name: str = Field(min_length=1, max_length=120)


class ResumeExtraction(BaseModel):
    """Validated structured resume parse (extra AI keys ignored, never stored)."""

    model_config = {"extra": "ignore"}

    full_name: Optional[str] = Field(None, max_length=200)
    email: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=100)
    education: list[str] = Field(default_factory=list)
    experience: list[ResumeExperience] = Field(default_factory=list)
    skills: list[ResumeSkill] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    experience_level: Optional[str] = Field(None, max_length=100)
    summary: Optional[str] = Field(None, max_length=2000)


class ResumeParseMeta(BaseModel):
    """Safe file metadata (never paths, never content)."""

    file_type: str
    file_size: int
    text_chars: int
    truncated: bool


class ResumeParseError(BaseModel):
    """Controlled failure (kinds only — never resume content, never secrets)."""

    code: Literal["ai_unavailable", "invalid_output", "extraction_failed"]
    message: str


class ResumeParseResponse(BaseModel):
    """Parse-only response: extraction or a controlled error, never both."""

    extraction: Optional[ResumeExtraction] = None
    parse_error: Optional[ResumeParseError] = None
    meta: ResumeParseMeta

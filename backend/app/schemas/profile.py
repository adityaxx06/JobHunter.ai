"""Phase 7A profile write models. Scalar bodies only — no new columns anywhere."""

from typing import Optional

from pydantic import BaseModel, Field, model_validator


class ProfileUpdate(BaseModel):
    """Body for patching scalar profile fields (only provided fields change)."""

    full_name: Optional[str] = Field(None, max_length=200)
    education: Optional[str] = Field(None, max_length=200)
    experience_level: Optional[str] = Field(None, max_length=200)
    preferred_work_mode: Optional[str] = Field(None, max_length=200)
    relocation_allowed: Optional[bool] = None
    minimum_stipend: Optional[int] = Field(None, ge=0)

    @model_validator(mode="after")
    def _require_a_change(self):
        if not self.model_fields_set:
            raise ValueError("provide at least one profile field")
        return self


class SkillCreate(BaseModel):
    """Body for adding a skill (duplicate name returns the existing row)."""

    skill_name: str = Field(min_length=1, max_length=120)
    skill_level: Optional[str] = Field(None, max_length=60)
    is_learning: bool = False


class SkillUpdate(BaseModel):
    """Body for editing a skill's level/learning status."""

    skill_level: Optional[str] = Field(None, max_length=60)
    is_learning: Optional[bool] = None

    @model_validator(mode="after")
    def _require_a_change(self):
        if not self.model_fields_set:
            raise ValueError("provide skill_level and/or is_learning")
        return self


class RoleCreate(BaseModel):
    """Body for adding a target role (duplicate name returns the existing row)."""

    role_name: str = Field(min_length=1, max_length=200)
    priority: int = Field(1, ge=1, le=100)


class RoleUpdate(BaseModel):
    """Body for renaming a role and/or changing its priority."""

    role_name: Optional[str] = Field(None, min_length=1, max_length=200)
    priority: Optional[int] = Field(None, ge=1, le=100)

    @model_validator(mode="after")
    def _require_a_change(self):
        if not self.model_fields_set:
            raise ValueError("provide role_name and/or priority")
        return self


class LocationCreate(BaseModel):
    """Body for adding a target location (duplicate name returns existing)."""

    location_name: str = Field(min_length=1, max_length=200)
    is_remote: bool = False
    priority: int = Field(1, ge=1, le=100)


class LocationUpdate(BaseModel):
    """Body for renaming a location and/or changing remote flag/priority."""

    location_name: Optional[str] = Field(None, min_length=1, max_length=200)
    is_remote: Optional[bool] = None
    priority: Optional[int] = Field(None, ge=1, le=100)

    @model_validator(mode="after")
    def _require_a_change(self):
        if not self.model_fields_set:
            raise ValueError("provide location_name, is_remote and/or priority")
        return self

"""Profile endpoints (Phase 3 read + Phase 7A writes + Phase 7B resume parse). No auth yet.

Reads return the profile bundle; writes are profile-scoped CRUD over the
existing tables only — no new columns, no new tables. Duplicate child names
return the existing row instead of inserting. Resume parsing is parse-only:
upload -> validate -> extract -> structure, bytes discarded, profile untouched.
Approval reuses the CRUD endpoints above.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.deps import db_unavailable, require_uuid
from app.db.repositories import profiles as repo
from app.schemas.profile import (
    LocationCreate,
    LocationUpdate,
    ProfileUpdate,
    RoleCreate,
    RoleUpdate,
    SkillCreate,
    SkillUpdate,
)
from app.schemas.resume import ResumeParseMeta, ResumeParseResponse
from app.services import resume_service

router = APIRouter()

logger = logging.getLogger("ai-jobhunter.resume.api")


def _require_profile(profile_id: str) -> None:
    """404 when the profile does not exist (checked before child writes)."""
    try:
        exists = repo.get_profile(profile_id) is not None
    except Exception as exc:
        raise db_unavailable(exc)
    if not exists:
        raise HTTPException(status_code=404, detail="profile not found")


def _clean_name(value: str, field: str) -> str:
    """Trimmed name (422 when blank after trimming)."""
    name = (value or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail=f"{field} must not be blank")
    return name


@router.get("/profiles/{profile_id}")
def read_profile(profile_id: str) -> dict:
    """Return a profile with its skills, target roles, and locations."""
    require_uuid(profile_id, "profile_id")
    try:
        profile = repo.get_profile(profile_id)
        if profile is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="profile not found")
        return {
            "profile": profile,
            "skills": repo.list_profile_skills(profile_id),
            "target_roles": repo.list_target_roles(profile_id),
            "target_locations": repo.list_target_locations(profile_id),
        }
    except Exception as exc:
        if getattr(exc, "status_code", None) in (400, 404):
            raise
        raise db_unavailable(exc)


@router.patch("/profiles/{profile_id}")
def patch_profile(profile_id: UUID, body: ProfileUpdate) -> dict:
    """Update scalar profile fields (only provided fields change)."""
    try:
        updated = repo.update_profile(str(profile_id), **body.model_dump(exclude_unset=True))
    except Exception as exc:
        raise db_unavailable(exc)
    if updated is None:
        raise HTTPException(status_code=404, detail="profile not found")
    return updated


@router.post("/profiles/{profile_id}/skills")
def add_skill(profile_id: UUID, body: SkillCreate) -> dict:
    """Add a skill (duplicate name returns the existing row)."""
    pid = str(profile_id)
    name = _clean_name(body.skill_name, "skill_name")
    _require_profile(pid)
    try:
        rows = repo.list_profile_skills(pid)
        existing = next((s for s in rows or []
                         if (s.get("skill_name") or "").strip().lower() == name.lower()), None)
        if existing is not None:
            return {"skill": existing, "duplicate": True}
        created = repo.add_profile_skill(pid, name, body.skill_level, body.is_learning)
    except Exception as exc:
        raise db_unavailable(exc)
    return {"skill": created, "duplicate": False}


@router.patch("/profiles/{profile_id}/skills/{skill_id}")
def patch_skill(profile_id: UUID, skill_id: UUID, body: SkillUpdate) -> dict:
    """Edit a skill's level/learning status (404 when the skill is missing)."""
    try:
        updated = repo.update_profile_skill(
            str(profile_id), str(skill_id),
            skill_level=body.skill_level, is_learning=body.is_learning)
    except Exception as exc:
        raise db_unavailable(exc)
    if updated is None:
        raise HTTPException(status_code=404, detail="skill not found")
    return updated


@router.delete("/profiles/{profile_id}/skills/{skill_id}")
def delete_skill(profile_id: UUID, skill_id: UUID) -> dict:
    """Remove a skill (404 when the skill is missing)."""
    try:
        removed = repo.remove_profile_skill(str(profile_id), str(skill_id))
    except Exception as exc:
        raise db_unavailable(exc)
    if not removed:
        raise HTTPException(status_code=404, detail="skill not found")
    return {"deleted": True}


@router.post("/profiles/{profile_id}/roles")
def add_role(profile_id: UUID, body: RoleCreate) -> dict:
    """Add a target role (duplicate name returns the existing row)."""
    pid = str(profile_id)
    name = _clean_name(body.role_name, "role_name")
    _require_profile(pid)
    try:
        rows = repo.list_target_roles(pid)
        existing = next((r for r in rows or []
                         if (r.get("role_name") or "").strip().lower() == name.lower()), None)
        if existing is not None:
            return {"role": existing, "duplicate": True}
        created = repo.add_target_role(pid, name, body.priority)
    except Exception as exc:
        raise db_unavailable(exc)
    return {"role": created, "duplicate": False}


@router.patch("/profiles/{profile_id}/roles/{role_id}")
def patch_role(profile_id: UUID, role_id: UUID, body: RoleUpdate) -> dict:
    """Rename a role and/or change its priority (409 on name conflict)."""
    pid = str(profile_id)
    name = _clean_name(body.role_name, "role_name") if body.role_name is not None else None
    try:
        if name is not None:
            rows = repo.list_target_roles(pid)
            clash = next((r for r in rows or []
                          if (r.get("role_name") or "").strip().lower() == name.lower()
                          and str(r.get("id")) != str(role_id)), None)
            if clash is not None:
                raise HTTPException(status_code=409, detail="role name already exists")
        updated = repo.update_target_role(pid, str(role_id), role_name=name, priority=body.priority)
    except HTTPException:
        raise
    except Exception as exc:
        raise db_unavailable(exc)
    if updated is None:
        raise HTTPException(status_code=404, detail="role not found")
    return updated


@router.delete("/profiles/{profile_id}/roles/{role_id}")
def delete_role(profile_id: UUID, role_id: UUID) -> dict:
    """Remove a target role (404 when the role is missing)."""
    try:
        removed = repo.remove_target_role(str(profile_id), str(role_id))
    except Exception as exc:
        raise db_unavailable(exc)
    if not removed:
        raise HTTPException(status_code=404, detail="role not found")
    return {"deleted": True}


@router.post("/profiles/{profile_id}/locations")
def add_location(profile_id: UUID, body: LocationCreate) -> dict:
    """Add a target location (duplicate name returns the existing row)."""
    pid = str(profile_id)
    name = _clean_name(body.location_name, "location_name")
    _require_profile(pid)
    try:
        rows = repo.list_target_locations(pid)
        existing = next((loc for loc in rows or []
                         if (loc.get("location_name") or "").strip().lower() == name.lower()), None)
        if existing is not None:
            return {"location": existing, "duplicate": True}
        created = repo.add_target_location(pid, name, body.is_remote, body.priority)
    except Exception as exc:
        raise db_unavailable(exc)
    return {"location": created, "duplicate": False}


@router.patch("/profiles/{profile_id}/locations/{location_id}")
def patch_location(profile_id: UUID, location_id: UUID, body: LocationUpdate) -> dict:
    """Rename a location and/or change remote flag/priority (409 on conflict)."""
    pid = str(profile_id)
    name = _clean_name(body.location_name, "location_name") if body.location_name is not None else None
    try:
        if name is not None:
            rows = repo.list_target_locations(pid)
            clash = next((loc for loc in rows or []
                          if (loc.get("location_name") or "").strip().lower() == name.lower()
                          and str(loc.get("id")) != str(location_id)), None)
            if clash is not None:
                raise HTTPException(status_code=409, detail="location name already exists")
        updated = repo.update_target_location(
            pid, str(location_id), location_name=name,
            is_remote=body.is_remote, priority=body.priority)
    except HTTPException:
        raise
    except Exception as exc:
        raise db_unavailable(exc)
    if updated is None:
        raise HTTPException(status_code=404, detail="location not found")
    return updated


@router.delete("/profiles/{profile_id}/locations/{location_id}")
def delete_location(profile_id: UUID, location_id: UUID) -> dict:
    """Remove a target location (404 when the location is missing)."""
    try:
        removed = repo.remove_target_location(str(profile_id), str(location_id))
    except Exception as exc:
        raise db_unavailable(exc)
    if not removed:
        raise HTTPException(status_code=404, detail="location not found")
    return {"deleted": True}


@router.post("/profiles/{profile_id}/resume/parse", response_model=ResumeParseResponse)
async def parse_resume(profile_id: UUID, file: UploadFile = File(...)) -> ResumeParseResponse:
    """Parse an uploaded resume into a reviewable extraction (never mutates).

    Flow: profile check -> bounded read -> validation -> text extraction ->
    Gemini structuring. Bytes are discarded after the response; no table,
    bucket, or profile row is touched. Approval uses the CRUD endpoints.
    """
    pid = str(profile_id)
    _require_profile(pid)
    # Bounded read first: cap+1 detects oversize without unbounded buffering.
    try:
        data = await file.read(resume_service.MAX_RESUME_BYTES + 1)
    except Exception:
        raise HTTPException(status_code=422, detail="Could not read the uploaded file.")
    size, suffix = len(data), (file.filename or "").rsplit(".", 1)[-1][:10]
    try:
        extension = resume_service.validate_upload(file.filename, file.content_type, size)
        text = resume_service.extract_text(data, extension)
    except resume_service.ResumeError as exc:
        logger.info("resume rejected (ext=%s size=%d kind=%s)", suffix, size, type(exc).__name__)
        raise HTTPException(status_code=exc.status, detail=str(exc))
    finally:
        data = b""
    chars, truncated = len(text), len(text) > resume_service.MAX_PROMPT_CHARS
    extraction, parse_error = resume_service.parse_resume_text(text)
    text = ""
    logger.info("resume parsed (chars=%d truncated=%s ok=%s)", chars, truncated, extraction is not None)
    return ResumeParseResponse(
        extraction=extraction,
        parse_error=parse_error,
        meta=ResumeParseMeta(
            file_type=extension, file_size=size, text_chars=chars, truncated=truncated,
        ),
    )

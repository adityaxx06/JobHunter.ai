"""Strict validation of Gemini intelligence JSON (Phase 5.2).

Nothing unvalidated reaches the database: scores must be true integers
(bools rejected) within 0-100, recommendation/eligibility must match the
strict vocabularies exactly, arrays must contain strings, reason must be
non-empty. Unknown top-level keys are ignored. Any violation raises
ValidationError with a credential-free message.
"""

from worker.models.intelligence import (
    ELIGIBILITIES,
    MAX_SCORE,
    MIN_SCORE,
    RECOMMENDATIONS,
    JobIntelligence,
)

_REQUIRED_FIELDS = (
    "match_score", "trust_score", "recommendation", "matching_skills",
    "missing_skills", "strengths", "concerns", "eligibility", "reason",
)


class ValidationError(Exception):
    """Malformed or out-of-contract Gemini output."""


def _score(value: object, field: str) -> int:
    """True int within range (bools, floats, strings, null all rejected)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field} must be an integer 0-100")
    if not (MIN_SCORE <= value <= MAX_SCORE):
        raise ValidationError(f"{field} must be an integer 0-100")
    return value


def _string_list(value: object, field: str) -> list:
    """List of non-empty strings (non-string items rejected)."""
    if not isinstance(value, list):
        raise ValidationError(f"{field} must be an array of strings")
    cleaned = []
    for item in value:
        if not isinstance(item, str):
            raise ValidationError(f"{field} must be an array of strings")
        item = item.strip()
        if item:
            cleaned.append(item)
    return cleaned


def validate_intelligence(payload: object) -> JobIntelligence:
    """Validate a decoded JSON object into JobIntelligence (raises ValidationError)."""
    if not isinstance(payload, dict):
        raise ValidationError("intelligence must be a JSON object")
    missing = [f for f in _REQUIRED_FIELDS if f not in payload]
    if missing:
        raise ValidationError(f"missing required field(s): {', '.join(missing)}")
    recommendation = payload["recommendation"]
    if recommendation not in RECOMMENDATIONS:
        raise ValidationError(f"recommendation must be one of {', '.join(RECOMMENDATIONS)}")
    eligibility = payload["eligibility"]
    if eligibility not in ELIGIBILITIES:
        raise ValidationError(f"eligibility must be one of {', '.join(ELIGIBILITIES)}")
    reason = payload["reason"]
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError("reason must be a non-empty string")
    return JobIntelligence(
        match_score=_score(payload["match_score"], "match_score"),
        trust_score=_score(payload["trust_score"], "trust_score"),
        recommendation=recommendation,
        matching_skills=_string_list(payload["matching_skills"], "matching_skills"),
        missing_skills=_string_list(payload["missing_skills"], "missing_skills"),
        strengths=_string_list(payload["strengths"], "strengths"),
        concerns=_string_list(payload["concerns"], "concerns"),
        eligibility=eligibility,
        reason=reason.strip(),
    )

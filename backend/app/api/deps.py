"""Shared API helpers (Phase 3): UUID validation + DB error mapping."""

import uuid

from fastapi import HTTPException


def require_uuid(value: str, field: str = "id") -> str:
    """Validate a UUID path param; 400 when malformed."""
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail=f"invalid {field}")
    return value


def db_unavailable(exc: Exception) -> HTTPException:
    """Map DB-layer failures to 503s without leaking details."""
    message = str(exc)
    if "not configured" in message:
        return HTTPException(status_code=503, detail="database not configured")
    return HTTPException(status_code=503, detail="database unreachable")

"""Deterministic job fingerprint (Phase 3).

Fingerprint = SHA-256 over canonical job identity:

    normalized company + normalized title + normalized location
    + canonical apply URL when available

Normalization: lowercase, trim, collapse inner whitespace; URLs get scheme/host
lowercased with trailing slashes stripped. No AI involved.

This is intentionally simple. Fingerprinting will be improved during the
Phase 5 normalization/deduplication work (e.g. URL canonicalization rules,
fuzzy title handling, content hashing). The function contract (stable string
for identical canonical input) will not change.
"""

import hashlib
import re
from urllib.parse import urlparse, urlunparse

_WS = re.compile(r"\s+")


def _norm_text(value: object) -> str:
    """Lowercase, trim, collapse whitespace. Non-strings become ''."""
    if not isinstance(value, str):
        return ""
    return _WS.sub(" ", value.strip().lower())


def _norm_url(value: object) -> str:
    """Normalize a URL for fingerprinting ('' when absent/invalid)."""
    if not isinstance(value, str) or not value.strip():
        return ""
    raw = value.strip()
    try:
        parts = urlparse(raw if "://" in raw else "https://" + raw)
    except Exception:
        return _norm_text(raw)
    host = (parts.hostname or "").lower()
    if not host:
        return _norm_text(raw)
    port = f":{parts.port}" if parts.port else ""
    path = parts.path.rstrip("/") or ""
    rebuilt = urlunparse(
        (
            (parts.scheme or "https").lower(),
            host + port,
            path,
            "",
            parts.query,
            "",
        )
    )
    return rebuilt.lower()


def build_fingerprint(
    company: object,
    title: object,
    location: object,
    apply_url: object = "",
    canonical_url: object = "",
) -> str:
    """Build a stable SHA-256 hex fingerprint for a canonical job posting."""
    link = _norm_url(apply_url) or _norm_url(canonical_url)
    payload = "\u0000".join(
        [_norm_text(company), _norm_text(title), _norm_text(location), link]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

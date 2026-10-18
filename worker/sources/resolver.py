"""Source/ATS resolver: DiscoveryTarget -> ResolvedSource (Phase 6.1).

Tavily is a DISCOVERY layer, never the authoritative job source. This module
decides, from a discovered URL alone, which ATS connector (if any) owns it
and which board/company handle to fetch. Only exact, infrastructure-grade
hostname rules route to a connector:

- greenhouse: boards.greenhouse.io/{board}, job-boards.greenhouse.io/{board}
  (the project's own Greenhouse parser treats job-boards.greenhouse.io as
  canonical), plus *.boards.greenhouse.io subdomains (mirrors classifier).
- lever: jobs.lever.co/{company} (plus lever.co / *.lever.co, as classified).
- ashby: jobs.ashbyhq.com/{board} (plus *.jobs.ashbyhq.com, as classified).

Everything else resolves to company_career / unknown and is NEVER handed to
a connector. In particular a URL that merely *mentions* an ATS
(e.g. example.com/careers/greenhouse) stays unresolved: false positives are
worse than misses.

SSRF posture: this module only PARSES strings. The ingestion pipeline only
ever calls the existing ATS clients (fixed API hosts) with the extracted
handle — there is intentionally no generic fetch(discovered_url) path.
"""

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from worker.search.classifier import COMPANY_CAREER, UNKNOWN, classify_url

GREENHOUSE = "greenhouse"
LEVER = "lever"
ASHBY = "ashby"

#: Hosts that prove ATS ownership (exact match -> high confidence).
_GREENHOUSE_EXACT = ("boards.greenhouse.io", "job-boards.greenhouse.io")
_LEVER_EXACT = ("jobs.lever.co", "lever.co")
_ASHBY_EXACT = ("jobs.ashbyhq.com",)

#: Subdomain suffixes accepted with medium confidence (mirror classifier).
_GREENHOUSE_SUFFIX = ".boards.greenhouse.io"
_LEVER_SUFFIX = ".lever.co"
_ASHBY_SUFFIX = ".jobs.ashbyhq.com"

#: Board/company handle shape (public handles: lowercase slug).
_HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

#: Query params stripped as tracking (everything else is preserved).
_TRACKING_PARAMS = ("utm_", "gclid", "gbraid", "wbraid", "fbclid", "msclkid", "mc_", "igshid", "_ga", "vero_")


def _is_tracking(name: str) -> bool:
    """True for known tracking params (prefix match, case-insensitive)."""
    lowered = (name or "").lower()
    return any(lowered == key.rstrip("_") or lowered.startswith(key) for key in _TRACKING_PARAMS)


def normalize_url(url: object) -> str:
    """Canonicalize a discovered URL for matching/dedup ("" when unusable).

    Lowercases the host, drops fragments, strips one trailing slash,
    removes tracking query params, keeps everything else. Never fetches.
    """
    if not isinstance(url, str) or not url.strip():
        return ""
    try:
        parts = urlsplit(url.strip())
    except Exception:
        return ""
    if parts.scheme.lower() not in ("http", "https"):
        return ""
    host = (parts.hostname or "").lower()
    if not host:
        return ""
    path = parts.path or ""
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    try:
        kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _is_tracking(k)]
    except Exception:
        kept = []
    query = urlencode(kept)
    netloc = host
    if parts.port and parts.port not in (80, 443):
        netloc = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme.lower(), netloc, path, query, ""))


def _first_segment(path: str) -> str:
    """First non-empty path segment, lowercased ("" when absent)."""
    for segment in (path or "").split("/"):
        if segment.strip():
            return segment.strip().lower()
    return ""


def _valid_handle(value: str) -> bool:
    """Public board/company handles are short lowercase slugs."""
    return bool(_HANDLE_RE.match(value or ""))


@dataclass
class ResolvedSource:
    """Resolver verdict for one discovery target (pure data, no fetching)."""

    source_type: str = UNKNOWN  # greenhouse | lever | ashby | company_career | unknown
    identifier: str = ""  # board/company handle for ATS types, else ""
    original_url: str = ""  # normalized discovered URL
    confidence: str = ""  # high | medium | "" (unresolved)
    reason: str = ""  # human-readable verdict for logs/summaries

    @property
    def is_ats(self) -> bool:
        """True only for a fetchable ATS target (type + valid handle)."""
        return self.source_type in (GREENHOUSE, LEVER, ASHBY) and bool(self.identifier)


def _resolve_ats(host: str, path: str) -> "tuple":
    """Match (host, path) against ATS infrastructure. Returns (type, handle, confidence, reason)."""
    if host in _GREENHOUSE_EXACT:
        handle = _first_segment(path)
        if _valid_handle(handle):
            return GREENHOUSE, handle, "high", f"greenhouse board '{handle}'"
        return UNKNOWN, "", "", "greenhouse host without a board handle"
    if host.endswith(_GREENHOUSE_SUFFIX):
        handle = _first_segment(path)
        if _valid_handle(handle):
            return GREENHOUSE, handle, "medium", f"greenhouse board '{handle}' (subdomain)"
        return UNKNOWN, "", "", "greenhouse subdomain without a board handle"
    if host in _LEVER_EXACT or host.endswith(_LEVER_SUFFIX):
        handle = _first_segment(path)
        if _valid_handle(handle):
            confidence = "high" if host in _LEVER_EXACT else "medium"
            return LEVER, handle, confidence, f"lever company '{handle}'"
        return UNKNOWN, "", "", "lever host without a company handle"
    if host in _ASHBY_EXACT or host.endswith(_ASHBY_SUFFIX):
        handle = _first_segment(path)
        if _valid_handle(handle):
            confidence = "high" if host in _ASHBY_EXACT else "medium"
            return ASHBY, handle, confidence, f"ashby board '{handle}'"
        return UNKNOWN, "", "", "ashby host without a board handle"
    return None


def resolve_url(url: object) -> ResolvedSource:
    """Resolve one URL string to a ResolvedSource (parse-only, no network)."""
    cleaned = normalize_url(url)
    if not cleaned:
        return ResolvedSource(source_type=UNKNOWN, original_url="", reason="missing or malformed URL")
    try:
        parts = urlsplit(cleaned)
    except Exception:
        return ResolvedSource(source_type=UNKNOWN, original_url="", reason="unparseable URL")
    host = (parts.hostname or "").lower()
    verdict = _resolve_ats(host, parts.path or "")
    if verdict is not None:
        source_type, identifier, confidence, reason = verdict
        return ResolvedSource(
            source_type=source_type,
            identifier=identifier,
            original_url=cleaned,
            confidence=confidence,
            reason=reason,
        )
    label = classify_url(cleaned)
    if label == COMPANY_CAREER:
        return ResolvedSource(source_type=COMPANY_CAREER, original_url=cleaned, reason="career page — queued for future resolution")
    return ResolvedSource(source_type=UNKNOWN, original_url=cleaned, reason="no recognized ATS infrastructure")


def resolve_target(target) -> ResolvedSource:
    """Resolve a DiscoveryTarget (or anything with a .url) to a ResolvedSource."""
    url = getattr(target, "url", target if isinstance(target, str) else "")
    return resolve_url(url)


def resolve_targets(targets: list) -> list:
    """Resolve many targets (order preserved; never raises on bad items)."""
    resolved = []
    for target in targets or []:
        try:
            resolved.append(resolve_target(target))
        except Exception:
            resolved.append(ResolvedSource(source_type=UNKNOWN, reason="resolver failure"))
    return resolved

"""Himalayas payload -> DiscoveredJob mapping (Phase 10C-2, pure functions).

Only fields Himalayas actually provides are mapped — nothing is fabricated:
- ``company_name`` is the documented ``companyName``; ``company_domain``
  stays empty (not provided).
- ``posted_at`` comes from ``pubDate`` (Unix epoch, seconds or millis);
  ``expiryDate`` and discovery time are NEVER substituted — absent/invalid
  means None.
- ``apply_url``/``source_url`` use ``applicationLink`` only when it parses
  as an http(s) URL; URL-less items are skipped (a lead without a URL
  cannot become a job).
- ``location`` joins ``locationRestrictions`` names; empty restrictions mean
  worldwide, reported as "Remote".
- ``experience_level`` joins the ``seniority`` array (list or string).
- Descriptions are sanitized HTML per the docs; shared stdlib html-to-text
  applies. The full original item is preserved in ``raw_data``.
- Attribution: displayed jobs link back to the Himalayas ``applicationLink``
  itself (the visible link the API terms require); ``source_name`` stays
  ``himalaya`` so attribution survives into job_sources rows.
"""

import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from worker.models.job import DiscoveredJob
from worker.sources.html_text import html_to_text

_WS = re.compile(r"\s+")
#: DB job_sources.source_type for Himalayas rows (existing CHECK value —
#: the constraint allows job_board; the board identity lives in source_name).
SOURCE_TYPE = "job_board"
SOURCE_NAME = "himalaya"


def _text(value: object) -> str:
    """Trimmed string ("" for missing/non-string input)."""
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _valid_url(value: object) -> str:
    """http(s) URL with a host ("" when absent/unusable — never fabricated)."""
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        parts = urlsplit(value.strip())
    except Exception:
        return ""
    if parts.scheme.lower() not in ("http", "https") or not (parts.hostname or ""):
        return ""
    return value.strip()


def _posted_at(value: object):
    """Unix epoch (seconds or millis) -> aware datetime (None when unusable).

    Only ``pubDate`` is consulted — expiry/discovery timestamps are never
    substituted, so a missing date stays missing instead of looking fresh.
    """
    if isinstance(value, bool):
        return None
    try:
        epoch = float(value)
    except (TypeError, ValueError):
        return None
    if epoch > 1e14:  # microseconds — beyond supported precision, reject
        return None
    if epoch > 1e12:  # millis
        epoch = epoch / 1000.0
    if epoch <= 0 or epoch > 4102444800:  # 2100-01-01 upper sanity bound
        return None
    try:
        return datetime.fromtimestamp(epoch, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _as_int(value: object):
    """Plain ints only (bools/floats/strings rejected — never coerced)."""
    if isinstance(value, bool):
        return None
    return int(value) if isinstance(value, int) else None


def _location(item: dict) -> tuple:
    """(location text, is_remote) from locationRestrictions (objects or names)."""
    restrictions = item.get("locationRestrictions")
    names = []
    if isinstance(restrictions, list):
        for entry in restrictions:
            if isinstance(entry, dict):
                name = _text(entry.get("name"))
            else:
                name = _text(entry)
            if name:
                names.append(name)
    if not names:
        return "Remote", True  # empty restrictions mean worldwide
    text = ", ".join(names)
    return text, "remote" in text.lower()


def _experience(item: dict) -> str:
    """Seniority list (or string) joined for display ("" when absent)."""
    seniority = item.get("seniority")
    if isinstance(seniority, str):
        return _text(seniority)
    if isinstance(seniority, list):
        return ", ".join(_text(level) for level in seniority if _text(level))
    return ""


def parse_job(item: dict) -> DiscoveredJob:
    """Map one documented Himalayas job object (raises ValueError when unusable)."""
    if not isinstance(item, dict):
        raise ValueError("job item must be an object")
    title = _text(item.get("title"))
    if not title:
        raise ValueError("job item has no title")
    apply_url = _valid_url(item.get("applicationLink"))
    if not apply_url:
        raise ValueError("job item has no usable application link")
    location, is_remote = _location(item)
    description = html_to_text(item.get("description"))
    currency = _text(item.get("currency")) or "INR"
    return DiscoveredJob(
        external_id=str(item.get("guid") or ""),
        title=title,
        company_name=_text(item.get("companyName")),
        company_domain="",
        location=location,
        locations=[],
        is_remote=is_remote,
        employment_type=_text(item.get("employmentType")),
        experience_level=_experience(item),
        description=description,
        salary_min=_as_int(item.get("minSalary")),
        salary_max=_as_int(item.get("maxSalary")),
        salary_currency=currency,
        skills=[],
        source_type=SOURCE_TYPE,
        source_name=SOURCE_NAME,
        source_url=apply_url,
        apply_url=apply_url,
        posted_at=_posted_at(item.get("pubDate")),
        raw_data=dict(item),
    )


def parse_search_jobs(payload: dict) -> list:
    """Map a search response's ``jobs`` array (skips unusable items)."""
    if not isinstance(payload, dict):
        return []
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        return []
    parsed = []
    for item in jobs:
        try:
            parsed.append(parse_job(item))
        except (ValueError, AttributeError, TypeError):
            continue
    return parsed

"""Jobicy payload -> DiscoveredJob mapping (Phase 10C-3, pure functions).

Only fields Jobicy actually provides are mapped — nothing is fabricated:
- ``company_name`` is the documented ``companyName``; ``company_domain``
  stays empty (not provided).
- ``posted_at`` comes from ``pubDate`` (ISO-8601 string) only. Expiry time,
  retrieval time, and discovery time are NEVER substituted — a missing or
  invalid date stays None instead of looking fresh.
- ``apply_url``/``source_url`` use ``url`` (the canonical Jobicy listing
  URL for keyless requests) only when it parses as http(s); URL-less items
  are skipped (a lead without a URL cannot become a job). The paid direct
  ATS-link tier is deliberately unused.
- ``location`` uses ``jobGeo`` (eligibility text); every row comes from a
  remote-only board, so ``is_remote`` is True by construction.
- ``experience_level`` uses ``jobLevel``; ``employment_type`` joins the
  ``jobType`` array. Full HTML ``jobDescription`` is cleaned with the shared
  stdlib helper (``jobExcerpt`` is NOT used — the full description survives).
- Attribution: the canonical listing URL is preserved verbatim and
  ``source_name`` stays ``jobicy`` so attribution survives into job_sources
  rows. The full original item is preserved in ``raw_data``.
"""

import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from worker.models.job import DiscoveredJob
from worker.sources.html_text import html_to_text

_WS = re.compile(r"\s+")
#: DB job_sources.source_type for Jobicy rows (existing CHECK value —
#: the constraint allows job_board; the board identity lives in source_name).
SOURCE_TYPE = "job_board"
SOURCE_NAME = "jobicy"


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
    """ISO-8601 ``pubDate`` -> aware datetime (None when absent/invalid)."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except (ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if parsed.year < 2000 or parsed.year > 2100:
        return None
    return parsed


def _as_int(value: object):
    """Plain ints only (bools/floats/strings rejected — never coerced)."""
    if isinstance(value, bool):
        return None
    return int(value) if isinstance(value, int) else None


def _join_list(value: object) -> str:
    """String list joined for display (plain string passed through)."""
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, list):
        return ", ".join(_text(item) for item in value if _text(item))
    return ""


def parse_job(item: dict) -> DiscoveredJob:
    """Map one documented Jobicy job object (raises ValueError when unusable)."""
    if not isinstance(item, dict):
        raise ValueError("job item must be an object")
    title = _text(item.get("jobTitle"))
    if not title:
        raise ValueError("job item has no title")
    apply_url = _valid_url(item.get("url"))
    if not apply_url:
        raise ValueError("job item has no usable URL")
    description = html_to_text(item.get("jobDescription")) or _text(item.get("jobExcerpt"))
    currency = _text(item.get("salaryCurrency")) or "INR"
    location = _text(item.get("jobGeo")) or "Remote"
    return DiscoveredJob(
        external_id=str(item.get("id") or ""),
        title=title,
        company_name=_text(item.get("companyName")),
        company_domain="",
        location=location,
        locations=[],
        is_remote=True,  # remote-only board by documentation
        employment_type=_join_list(item.get("jobType")),
        experience_level=_text(item.get("jobLevel")),
        description=description,
        salary_min=_as_int(item.get("salaryMin")),
        salary_max=_as_int(item.get("salaryMax")),
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
    """Map a listing response's ``jobs`` array (skips unusable items)."""
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

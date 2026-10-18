"""Lever payload -> DiscoveredJob mapping (Phase 4.2B, pure functions).

Only fields Lever actually provides are mapped — nothing is fabricated:
- ``company_name`` is derived from the public company handle (humanized) and
  documented as such; ``company_domain`` stays "" (not provided).
- ``skills`` stays [] (no structured skills in postings); salary stays None
  unless plainly numeric ``salaryMin/salaryMax`` values exist.
- ``posted_at`` comes from ``createdAt`` epoch millis when present, else None.
- The complete original posting is preserved in ``raw_data``.
Descriptions prefer ``descriptionPlain`` when present, else the HTML
``description`` is cleaned via the shared stdlib helper.
"""

import re
from datetime import datetime, timezone

from worker.models.job import DiscoveredJob
from worker.sources.html_text import html_to_text

_WS = re.compile(r"\s+")


def humanize_company_handle(company: str) -> str:
    """Derive a display name from a public company handle (documented guess)."""
    return _WS.sub(" ", re.sub(r"[-_]+", " ", (company or "").strip().lower())).strip().title()


def detect_remote(location_text: object, categories: object = None) -> bool:
    """Remote only on explicit signals: 'remote' in location text or a
    workplace/category field saying so. Missing location is NOT remote."""
    if isinstance(location_text, str) and "remote" in location_text.lower():
        return True
    if isinstance(categories, dict):
        for key in ("workplaceType", "workplace", "location"):
            value = categories.get(key)
            if isinstance(value, str) and "remote" in value.lower():
                return True
    return False


def _location_text(categories: object) -> str:
    """Location string from posting categories ('' when absent)."""
    if isinstance(categories, dict):
        location = categories.get("location")
        if isinstance(location, str) and location.strip():
            return location.strip()
    return ""


def _employment_type(categories: object) -> str:
    """Commitment label from categories ('' when absent)."""
    if isinstance(categories, dict):
        commitment = categories.get("commitment")
        if isinstance(commitment, str) and commitment.strip():
            return commitment.strip()
    return ""


def _posted_at(item: dict):
    """Epoch-millis ``createdAt`` -> aware datetime (None when absent/invalid)."""
    created = item.get("createdAt")
    if isinstance(created, bool) or not isinstance(created, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(created) / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _salary_number(value: object):
    """Plain numeric salary bound (None for anything else — never guessed)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _description(item: dict) -> str:
    """Plain-text description: prefer ``descriptionPlain``, else clean HTML."""
    plain = item.get("descriptionPlain")
    if isinstance(plain, str) and plain.strip():
        return _WS.sub(" ", plain).strip()
    return html_to_text(item.get("description"))


def parse_posting(company: str, item: dict) -> DiscoveredJob:
    """Map one Lever posting object to :class:`DiscoveredJob`."""
    item = item if isinstance(item, dict) else {}
    categories = item.get("categories") if isinstance(item.get("categories"), dict) else {}
    location = _location_text(categories)
    title = item.get("text")
    apply_url = item.get("applyUrl")
    return DiscoveredJob(
        external_id=str(item.get("id", "")),
        title=title if isinstance(title, str) else "",
        company_name=humanize_company_handle(company),
        company_domain="",
        location=location,
        locations=[location] if location else [],
        is_remote=detect_remote(location, categories),
        employment_type=_employment_type(categories),
        experience_level="",
        description=_description(item),
        salary_min=_salary_number(item.get("salaryMin")),
        salary_max=_salary_number(item.get("salaryMax")),
        salary_currency=item.get("salaryCurrency") if isinstance(item.get("salaryCurrency"), str) else "INR",
        skills=[],
        source_type="lever",
        source_name=f"lever:{company}",
        source_url=f"https://jobs.lever.co/{company}",
        apply_url=apply_url if isinstance(apply_url, str) else "",
        posted_at=_posted_at(item),
        raw_data=dict(item),
    )


def parse_company_postings(company: str, payload: object) -> list:
    """Map a company's postings array to :class:`DiscoveredJob` objects."""
    if not isinstance(payload, list):
        return []
    return [parse_posting(company, item) for item in payload if isinstance(item, dict)]

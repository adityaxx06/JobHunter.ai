"""Ashby payload -> DiscoveredJob mapping (Phase 4.2C, pure functions).

Field shapes follow Ashby's official Job Postings API docs. Only provided
fields are mapped — nothing is fabricated:
- ``company_name`` is derived from the public board name (humanized) and
  documented as such; ``company_domain`` stays "" (not provided).
- ``experience_level``/``skills`` stay empty (not provided as structured data).
- Postings with ``isListed`` explicitly False are skipped: per Ashby's docs
  they must not be displayed publicly (direct-link only).
- Compensation comes from the job's ``compensation.summaryComponents`` Salary
  entry (present only with ``includeCompensation=true`` and employer consent).
- The complete original posting is preserved in ``raw_data``.
Descriptions prefer ``descriptionPlain``, else the shared stdlib helper cleans
``descriptionHtml``.
"""

import re
from datetime import datetime, timezone

from worker.models.job import DiscoveredJob
from worker.sources.html_text import html_to_text

_WS = re.compile(r"\s+")


def humanize_board_name(board: str) -> str:
    """Derive a display name from a public board name (documented guess)."""
    return _WS.sub(" ", re.sub(r"[-_]+", " ", (board or "").strip().lower())).strip().title()


def detect_remote(is_remote: object, workplace_type: object, location_text: object) -> bool:
    """Remote on explicit signals only: ``isRemote`` True, workplaceType
    "Remote", or 'remote' in location text. Hybrid/onsite/missing are NOT
    remote."""
    if is_remote is True:
        return True
    if isinstance(workplace_type, str) and workplace_type.strip().lower() == "remote":
        return True
    if isinstance(location_text, str) and "remote" in location_text.lower():
        return True
    return False


def _location_text(item: dict) -> str:
    location = item.get("location")
    return location.strip() if isinstance(location, str) and location.strip() else ""


def _all_locations(item: dict) -> list:
    """Primary location plus secondary locations (deduped, order kept)."""
    locations = []
    primary = _location_text(item)
    if primary:
        locations.append(primary)
    secondary = item.get("secondaryLocations")
    if isinstance(secondary, list):
        for entry in secondary:
            if isinstance(entry, dict):
                name = entry.get("location")
            elif isinstance(entry, str):
                name = entry
            else:
                name = None
            if isinstance(name, str) and name.strip() and name.strip() not in locations:
                locations.append(name.strip())
    return locations


def _posted_at(item: dict):
    """ISO-8601 ``publishedAt`` -> aware datetime (None when absent/invalid)."""
    value = item.get("publishedAt")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _compensation(item: dict) -> tuple:
    """(min, max, currency) from the Salary summary component (Nones when absent).

    Only plain numeric values are used; anything else is ignored, never guessed.
    """
    compensation = item.get("compensation")
    components = compensation.get("summaryComponents") if isinstance(compensation, dict) else None
    if not isinstance(components, list):
        return None, None, ""
    for component in components:
        if not isinstance(component, dict):
            continue
        if str(component.get("compensationType", "")).lower() != "salary":
            continue
        low, high = component.get("minValue"), component.get("maxValue")
        low = int(low) if isinstance(low, (int, float)) and not isinstance(low, bool) else None
        high = int(high) if isinstance(high, (int, float)) and not isinstance(high, bool) else None
        if low is None and high is None:
            continue
        currency = component.get("currencyCode")
        return low, high, currency if isinstance(currency, str) and currency.strip() else ""
    return None, None, ""


def _description(item: dict) -> str:
    """Plain-text description: prefer ``descriptionPlain``, else clean HTML."""
    plain = item.get("descriptionPlain")
    if isinstance(plain, str) and plain.strip():
        return _WS.sub(" ", plain).strip()
    return html_to_text(item.get("descriptionHtml"))


def parse_posting(board: str, item: dict):
    """Map one Ashby posting to :class:`DiscoveredJob` (None when unlisted)."""
    item = item if isinstance(item, dict) else {}
    if item.get("isListed") is False:
        return None  # unlisted postings must not be displayed publicly
    location = _location_text(item)
    title = item.get("title")
    apply_url = item.get("applyUrl")
    salary_min, salary_max, currency = _compensation(item)
    job_id = item.get("id")
    return DiscoveredJob(
        external_id=str(job_id) if job_id is not None else "",
        title=title if isinstance(title, str) else "",
        company_name=humanize_board_name(board),
        company_domain="",
        location=location,
        locations=_all_locations(item),
        is_remote=detect_remote(item.get("isRemote"), item.get("workplaceType"), location),
        employment_type=item.get("employmentType") if isinstance(item.get("employmentType"), str) else "",
        experience_level="",
        description=_description(item),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=currency or "INR",
        skills=[],
        source_type="ashby",
        source_name=f"ashby:{board}",
        source_url=f"https://jobs.ashbyhq.com/{board}",
        apply_url=apply_url if isinstance(apply_url, str) else "",
        posted_at=_posted_at(item),
        raw_data=dict(item),
    )


def parse_board_jobs(board: str, payload: object) -> list:
    """Map a board payload (``{"jobs": [...]}``) to postings (unlisted dropped)."""
    jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
    if not isinstance(jobs, list):
        return []
    parsed = []
    for item in jobs:
        if not isinstance(item, dict):
            continue
        job = parse_posting(board, item)
        if job is not None:
            parsed.append(job)
    return parsed

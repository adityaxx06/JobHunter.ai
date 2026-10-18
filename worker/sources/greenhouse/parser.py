"""Greenhouse payload -> DiscoveredJob mapping (Phase 4.2A, pure functions).

Only fields Greenhouse actually provides are mapped — nothing is fabricated:
- ``company_name`` is derived from the public board token (humanized) and
  documented as such; ``company_domain`` stays empty (not provided).
- ``posted_at`` stays None: the public jobs payload carries no posting date.
- ``employment_type`` is taken from job ``metadata`` when present, else "".
- The full original item is preserved in ``raw_data``.
HTML descriptions are converted to plain text with a small stdlib parser
(scripts/styles dropped, entities unescaped, whitespace collapsed).
"""

import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser

from worker.models.job import DiscoveredJob

_WS = re.compile(r"\s+")


class _TextExtractor(HTMLParser):
    """Collect visible text; skip script/style content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs) -> None:
        if tag in ("script", "style"):
            self._skip_depth += 1
        elif tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "ul", "ol"):
            self._parts.append("\n")

    def handle_endtag(self, tag) -> None:
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1
        elif tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4"):
            self._parts.append("\n")

    def handle_data(self, data) -> None:
        if not self._skip_depth:
            self._parts.append(data)

    def text(self) -> str:
        raw = unescape("".join(self._parts))
        lines = [_WS.sub(" ", line).strip() for line in raw.split("\n")]
        return "\n".join(line for line in lines if line)


def html_to_text(html: object) -> str:
    """Convert an HTML description to clean plain text ('' for non-strings)."""
    if not isinstance(html, str) or not html.strip():
        return ""
    if "<" not in html:
        return _WS.sub(" ", html).strip()
    extractor = _TextExtractor()
    try:
        extractor.feed(html)
        extractor.close()
    except Exception:
        return _WS.sub(" ", unescape(html)).strip()
    return extractor.text()


def humanize_board_token(board: str) -> str:
    """Derive a display name from a public board token (documented guess)."""
    return _WS.sub(" ", re.sub(r"[-_]+", " ", (board or "").strip().lower())).strip().title()


def detect_remote(location_name: str) -> bool:
    """Remote when the location text says so (e.g. 'Remote - US')."""
    return "remote" in (location_name or "").lower()


def _parse_datetime(value: object):
    """Parse an ISO-8601 timestamp (None when absent/unparseable)."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _employment_from_metadata(metadata: object) -> str:
    """Find an employment-type-ish metadata value ('' when absent)."""
    if not isinstance(metadata, list):
        return ""
    for entry in metadata:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).lower()
        if "employment" in name or name in ("type", "job type", "work type"):
            value = entry.get("value")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def parse_job(board: str, item: dict) -> DiscoveredJob:
    """Map one Greenhouse job object to :class:`DiscoveredJob`."""
    item = item if isinstance(item, dict) else {}
    location = item.get("location")
    location_name = location.get("name", "") if isinstance(location, dict) else (location if isinstance(location, str) else "")
    posted_at = None
    for key in ("updated_at", "created_at", "first_published"):
        posted_at = _parse_datetime(item.get(key))
        if posted_at is not None:
            break
    job_id = item.get("id")
    return DiscoveredJob(
        external_id=str(job_id) if job_id is not None else "",
        title=item.get("title", "") if isinstance(item.get("title"), str) else "",
        company_name=humanize_board_token(board),
        company_domain="",
        location=location_name if isinstance(location_name, str) else "",
        locations=[location_name] if location_name else [],
        is_remote=detect_remote(location_name if isinstance(location_name, str) else ""),
        employment_type=_employment_from_metadata(item.get("metadata")),
        experience_level="",
        description=html_to_text(item.get("content")),
        skills=[],
        source_type="greenhouse",
        source_name=f"greenhouse:{board}",
        source_url=f"https://job-boards.greenhouse.io/{board}",
        apply_url=item.get("absolute_url", "") if isinstance(item.get("absolute_url"), str) else "",
        posted_at=posted_at,
        raw_data=dict(item),
    )


def parse_board_jobs(board: str, payload: dict) -> list:
    """Map a board's jobs payload (``{"jobs": [...]}``) to postings."""
    jobs = (payload or {}).get("jobs", [])
    if not isinstance(jobs, list):
        return []
    return [parse_job(board, item) for item in jobs if isinstance(item, dict)]

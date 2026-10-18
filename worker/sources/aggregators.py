"""Aggregator URL-first conversion: non-ATS leads -> DiscoveredJob (Phase 9).

Tavily returns LinkedIn/Indeed/Internshala results that no ATS connector can
fetch. Instead of dropping them, job-detail URLs are converted directly into
DiscoveredJobs from the metadata Tavily already returned (title, URL,
snippet) — URL-first, no scraping, no fetching, no fabrication.

Only genuine job-detail pages convert; search/listing/company pages are
skipped with a reason:

- linkedin: /jobs/view/* converts; /jobs/* listings, /company/*, /in/* do not.
- internshala: /internship/detail/* converts; /internships/* categories do not.
- indeed: /viewjob* converts (/pagead/* click-redirects and /q-*.html
  searches do not).

Missing company/location stay empty (never guessed from titles); the
canonical URL becomes the stable apply/canonical identity so re-discovery
deduplicates via the existing apply_url + fingerprint path.
"""

from urllib.parse import urlsplit

from worker.models.job import DiscoveredJob
from worker.sources.resolver import normalize_url

LINKEDIN = "linkedin"
INDEED = "indeed"
INTERNSHALA = "internshala"

#: Aggregator key -> accepted hostname (exact or subdomain).
AGGREGATOR_HOSTS = {
    LINKEDIN: "linkedin.com",
    INDEED: "indeed.com",
    INTERNSHALA: "internshala.com",
}

#: DB job_sources.source_type for converted leads (existing CHECK value).
AGGREGATOR_SOURCE_TYPE = "job_board"

#: Snippet length kept as the description (real returned metadata only).
SNIPPET_MAX_CHARS = 2000


def aggregator_key(url: object) -> str:
    """Aggregator key for a URL ("" when the host is not a known aggregator)."""
    if not isinstance(url, str) or not url.strip():
        return ""
    try:
        host = (urlsplit(url.strip()).hostname or "").lower()
    except Exception:
        return ""
    if not host:
        return ""
    for key, domain in AGGREGATOR_HOSTS.items():
        if host == domain or host.endswith("." + domain):
            return key
    return ""


def _segments(path: str) -> list:
    """Non-empty lowercased path segments."""
    return [s for s in (path or "").lower().split("/") if s]


def is_job_detail_url(key: str, url: object) -> bool:
    """True only for genuine job-detail pages (listings/searches excluded)."""
    if not key or not isinstance(url, str) or not url.strip():
        return False
    try:
        path = (urlsplit(url.strip()).path or "").lower()
    except Exception:
        return False
    segments = _segments(path)
    if key == LINKEDIN:
        return len(segments) >= 3 and segments[0] == "jobs" and segments[1] == "view"
    if key == INTERNSHALA:
        # /internship/detail/* (internships) and /job/detail/* (fresher jobs)
        # both address individual postings; categories (/internships/*),
        # searches, and blogs never qualify.
        return len(segments) >= 3 and segments[0] in ("internship", "job") and segments[1] == "detail"
    if key == INDEED:
        return "viewjob" in segments
    return False


def skip_reason(key: str, url: object) -> str:
    """Human reason why a URL does not convert (for summaries, never secrets)."""
    if not key:
        return "not an aggregator host"
    return f"{key} non-detail page (listing/search/company, not a job posting)"


def discovered_job_from_target(url: object, title: object = "",
                               snippet: object = "") -> DiscoveredJob:
    """Build a DiscoveredJob from Tavily-returned metadata (no fabrication).

    Title/snippet pass through (possibly empty — display layers already
    handle that); company/location stay empty rather than guessed; the
    canonical URL is the stable apply + canonical identity.
    """
    raw_url = url if isinstance(url, str) else ""
    canonical = normalize_url(raw_url)
    key = aggregator_key(raw_url)
    text = snippet if isinstance(snippet, str) else ""
    return DiscoveredJob(
        external_id="",
        title=title.strip() if isinstance(title, str) else "",
        company_name="",
        company_domain="",
        location="",
        locations=[],
        is_remote=False,
        employment_type="",
        experience_level="",
        description=text.strip()[:SNIPPET_MAX_CHARS],
        source_type=AGGREGATOR_SOURCE_TYPE,
        source_name=key,
        source_url=raw_url.strip(),
        apply_url=canonical,
        raw_data={},
    )


def convert_entries(entries: list, max_items: int):
    """Convert (url, title, snippet) entries to DiscoveredJobs.

    Returns (converted, skipped) where skipped entries are (url, reason)
    pairs for honest reporting. Bounded by ``max_items``; never raises.
    """
    converted, skipped = [], []
    cap = max(0, int(max_items))
    for entry in entries or []:
        try:
            url, title, snippet = entry
        except Exception:
            skipped.append(("", "unreadable target"))
            continue
        url = url if isinstance(url, str) else ""
        key = aggregator_key(url)
        if not key:
            skipped.append((url, "not an aggregator host"))
            continue
        if len(converted) >= cap:
            skipped.append((url, f"aggregator cap reached ({cap})"))
            continue
        if not is_job_detail_url(key, url):
            skipped.append((url, skip_reason(key, url)))
            continue
        converted.append(discovered_job_from_target(
            url, title if isinstance(title, str) else "",
            snippet if isinstance(snippet, str) else ""))
    return converted, skipped

"""URL -> source classification (Phase 4.3, conservative hostname rules).

Only the URL's host (and, for career pages, well-known path prefixes) decides
the label. Titles, snippets, and company names are NEVER used — a company
name in a title proves nothing about where a posting lives. Anything
unrecognized, malformed, or empty is "unknown".

Phase 7A.1 adds conservative junk rejection (``is_junk_url``): obvious
non-job pages on the priority aggregators (company profiles, people
profiles, blogs, employer pages) never become discovery targets. Rules are
host-specific and path-prefix based — a legitimate job URL is never junk.
"""

from urllib.parse import urlparse

GREENHOUSE = "greenhouse"
LEVER = "lever"
ASHBY = "ashby"
COMPANY_CAREER = "company_career"
UNKNOWN = "unknown"

_CAREER_PATH_HINTS = ("/careers", "/career", "/jobs", "/join", "/vacancies", "/opportunities")

#: Host -> path prefixes that are definitively NOT job postings. Only exact
#: host or subdomain matches count; everything else is left alone.
_JUNK_PATHS = (
    ("linkedin.com", ("/company/", "/in/", "/posts/", "/feed/", "/learning/",
                      "/school/", "/showcase/", "/groups/", "/events/", "/pulse/")),
    ("internshala.com", ("/blog/",)),
    ("indeed.com", ("/companies/", "/career-advice/", "/hire/", "/employers/")),
)


def _host(url: object) -> str:
    """Lowercased hostname ("" for missing/malformed URLs)."""
    if not isinstance(url, str) or not url.strip():
        return ""
    try:
        return (urlparse(url.strip()).hostname or "").lower()
    except Exception:
        return ""


def classify_url(url: object) -> str:
    """Classify one URL into a source label (conservative, URL-only)."""
    host = _host(url)
    if not host:
        return UNKNOWN
    if host == "boards.greenhouse.io" or host.endswith(".boards.greenhouse.io"):
        return GREENHOUSE
    if host in ("jobs.lever.co", "lever.co") or host.endswith(".lever.co"):
        return LEVER
    if host == "jobs.ashbyhq.com" or host.endswith(".jobs.ashbyhq.com"):
        return ASHBY
    try:
        path = urlparse(url.strip()).path.lower()
    except Exception:
        return UNKNOWN
    if any(path == hint or path.startswith(hint + "/") for hint in _CAREER_PATH_HINTS):
        return COMPANY_CAREER
    return UNKNOWN


def is_junk_url(url: object) -> bool:
    """True for obvious non-job pages on known aggregators (else False).

    Conservative by design: only exact-host (or subdomain) matches with
    well-known non-job path prefixes count. Malformed URLs are NOT junk
    here — they stay "unknown" so legitimate leads are never dropped.
    """
    host = _host(url)
    if not host:
        return False
    try:
        path = urlparse(url.strip()).path.lower() or "/"
    except Exception:
        return False
    for domain, prefixes in _JUNK_PATHS:
        if host != domain and not host.endswith("." + domain):
            continue
        for prefix in prefixes:
            if path == prefix.rstrip("/") or path.startswith(prefix):
                return True
    return False


def classify_results(results: list) -> list:
    """Turn search results into discovery targets (no job claims made).

    Junk URLs (see ``is_junk_url``) are dropped before targeting — they are
    noise, not leads. Everything else keeps its full title/URL/snippet.
    """
    from worker.models.search import DiscoveryTarget

    targets = []
    for result in results:
        url = getattr(result, "url", "")
        if is_junk_url(url):
            continue
        targets.append(
            DiscoveryTarget(
                url=url if isinstance(url, str) else "",
                classified_source=classify_url(url),
                title=getattr(result, "title", "") or "",
                snippet=getattr(result, "snippet", "") or "",
            )
        )
    return targets

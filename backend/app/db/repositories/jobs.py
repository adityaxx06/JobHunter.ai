"""Job repository (Phase 3).

Phase 2 schema has no dedicated fingerprint column (schema frozen), so
``get_job_by_fingerprint`` resolves by scanning recent candidates with the
same normalized title and comparing fingerprints in Python. Phase 5
(normalization/deduplication) may add a stored fingerprint column; the
function contract will not change.
"""

from typing import Optional

from app.db import connection as db
from app.utils.job_fingerprint import build_fingerprint

_JOB_COLS = (
    "j.id, j.company_id, j.title, j.normalized_title, j.description, j.location, "
    "j.is_remote, j.employment_type, j.experience_level, j.salary_min, j.salary_max, "
    "j.salary_currency, j.salary_period, j.skills, j.posted_at, j.first_seen_at, "
    "j.last_seen_at, j.canonical_url, j.apply_url, j.status, j.created_at, j.updated_at"
)

_FINGERPRINT_CANDIDATE_LIMIT = 500


def get_job(job_id: str) -> Optional[dict]:
    """Fetch one job by id with its company names (None when not found)."""
    return db.fetch_one(
        f"""SELECT {_JOB_COLS}, c.name AS company_name, c.normalized_name AS company_normalized_name
            FROM public.jobs j
            LEFT JOIN public.companies c ON c.id = j.company_id
            WHERE j.id = %s""",
        (job_id,),
    )


def get_job_by_fingerprint(fingerprint: str, normalized_title: str) -> Optional[dict]:
    """Find a job by its deterministic fingerprint.

    Args:
        fingerprint: expected ``build_fingerprint(...)`` hex digest.
        normalized_title: narrows candidates (same value used at fingerprint time).

    Compares fingerprints in Python over recent candidates; no schema change.
    """
    candidates = db.fetch_all(
        """SELECT j.id, j.company_id, j.title, j.normalized_title, j.location,
                  j.canonical_url, j.apply_url, c.normalized_name AS company_normalized_name
           FROM public.jobs j
           LEFT JOIN public.companies c ON c.id = j.company_id
           WHERE j.normalized_title = %s
           ORDER BY j.first_seen_at DESC
           LIMIT %s""",
        (normalized_title, _FINGERPRINT_CANDIDATE_LIMIT),
    )
    for row in candidates:
        candidate_fp = build_fingerprint(
            row.get("company_normalized_name") or "",
            row.get("normalized_title") or row.get("title") or "",
            row.get("location") or "",
            row.get("apply_url") or "",
            row.get("canonical_url") or "",
        )
        if candidate_fp == fingerprint:
            return get_job(row["id"])
    return None


def create_job(
    title: str,
    normalized_title: str,
    company_id: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    is_remote: bool = False,
    employment_type: Optional[str] = None,
    experience_level: Optional[str] = None,
    canonical_url: Optional[str] = None,
    apply_url: Optional[str] = None,
    status: str = "active",
    posted_at: Optional[str] = None,
) -> Optional[dict]:
    """Insert a job and return the new row."""
    return db.execute(
        """INSERT INTO public.jobs
           (company_id, title, normalized_title, description, location, is_remote,
            employment_type, experience_level, canonical_url, apply_url, status, posted_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id, company_id, title, normalized_title, location, is_remote,
                     canonical_url, apply_url, status, posted_at, first_seen_at, last_seen_at""",
        (
            company_id,
            title,
            normalized_title,
            description,
            location,
            is_remote,
            employment_type,
            experience_level,
            canonical_url,
            apply_url,
            status,
            posted_at,
        ),
    )


def upsert_job(
    title: str,
    normalized_title: str,
    company_normalized_name: str = "",
    company_id: Optional[str] = None,
    location: Optional[str] = None,
    apply_url: Optional[str] = None,
    canonical_url: Optional[str] = None,
    **extra,
) -> Optional[dict]:
    """Insert a job, or touch ``last_seen_at`` when its fingerprint matches.

    Fingerprint covers normalized company + title + location + apply URL.
    """
    fingerprint = build_fingerprint(
        company_normalized_name, normalized_title, location or "", apply_url or "", canonical_url or ""
    )
    existing = get_job_by_fingerprint(fingerprint, normalized_title)
    if existing:
        return db.execute(
            """UPDATE public.jobs SET last_seen_at = NOW()
               WHERE id = %s
               RETURNING id, company_id, title, normalized_title, location,
                         canonical_url, apply_url, status, last_seen_at""",
            (existing["id"],),
        )
    return create_job(
        title=title,
        normalized_title=normalized_title,
        company_id=company_id,
        location=location,
        apply_url=apply_url,
        canonical_url=canonical_url,
        description=extra.get("description"),
        is_remote=bool(extra.get("is_remote", False)),
        employment_type=extra.get("employment_type"),
        experience_level=extra.get("experience_level"),
        status=extra.get("status", "active"),
        posted_at=extra.get("posted_at"),
    )


def list_recent_jobs(limit: int = 20) -> list:
    """Most recently seen active jobs (basic info for the minimal API)."""
    safe_limit = max(1, min(int(limit), 100))
    return db.fetch_all(
        """SELECT j.id, j.title, j.location, j.is_remote, j.apply_url, j.status,
                  j.posted_at, j.last_seen_at, c.name AS company_name
           FROM public.jobs j
           LEFT JOIN public.companies c ON c.id = j.company_id
           ORDER BY j.last_seen_at DESC
           LIMIT %s""",
        (safe_limit,),
    )


def list_jobs_page(limit: int = 20, offset: int = 0) -> list:
    """Paged jobs with company + timestamps (Phase 5.4 list endpoint)."""
    safe_limit = max(1, min(int(limit), 100))
    safe_offset = max(0, int(offset))
    return db.fetch_all(
        """SELECT j.id, j.title, j.location, j.employment_type, j.is_remote,
                  j.apply_url, j.status, j.posted_at, j.created_at, j.updated_at,
                  c.name AS company_name
           FROM public.jobs j
           LEFT JOIN public.companies c ON c.id = j.company_id
           ORDER BY j.last_seen_at DESC
           LIMIT %s OFFSET %s""",
        (safe_limit, safe_offset),
    )


def count_jobs() -> int:
    """Total persisted jobs (for paged list responses)."""
    row = db.fetch_one("SELECT COUNT(*) AS total FROM public.jobs")
    return int((row or {}).get("total") or 0)


#: Whitelisted sort keys — user input never reaches ORDER BY directly.
_JOB_SORTS = {
    "newest": "j.last_seen_at DESC, j.id ASC",
    "match": ("m.match_score DESC NULLS LAST, m.trust_score DESC NULLS LAST, "
              "j.last_seen_at DESC, j.id ASC"),
    "trust": ("m.trust_score DESC NULLS LAST, m.match_score DESC NULLS LAST, "
              "j.last_seen_at DESC, j.id ASC"),
}

#: Intelligence columns — real NULLs when no profile context is joined in.
_INTEL_COLS = ("m.match_score, m.trust_score, m.recommendation, "
               "m.strengths, m.missing_skills, m.reason")


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so user text matches literally (injection is
    already impossible via params; this preserves search correctness)."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _job_filter_clauses(search=None, role=None, location=None, remote=None,
                         min_match=None, min_trust=None, recommendation=None,
                         employment_type=None):
    """Shared WHERE builder — every value travels as a bound param."""
    clauses, params = [], []
    if search and search.strip():
        like = f"%{_escape_like(search.strip())}%"
        clauses.append("(j.title ILIKE %s ESCAPE '\\' OR c.name ILIKE %s ESCAPE '\\' "
                       "OR j.location ILIKE %s ESCAPE '\\' OR j.description ILIKE %s ESCAPE '\\')")
        params.extend([like, like, like, like])
    if role and role.strip():
        clauses.append("j.title ILIKE %s ESCAPE '\\'")
        params.append(f"%{_escape_like(role.strip())}%")
    if location and location.strip():
        clauses.append("j.location ILIKE %s ESCAPE '\\'")
        params.append(f"%{_escape_like(location.strip())}%")
    if remote is not None:
        clauses.append("j.is_remote = %s")
        params.append(bool(remote))
    if min_match is not None:
        clauses.append("m.match_score >= %s")
        params.append(int(min_match))
    if min_trust is not None:
        clauses.append("m.trust_score >= %s")
        params.append(int(min_trust))
    if recommendation:
        clauses.append("m.recommendation = %s")
        params.append(recommendation)
    if employment_type and employment_type.strip():
        clauses.append("j.employment_type ILIKE %s ESCAPE '\\'")
        params.append(f"%{_escape_like(employment_type.strip())}%")
    return clauses, params


def search_jobs_page(limit=20, offset=0, search=None, role=None, location=None,
                     remote=None, min_match=None, min_trust=None,
                     recommendation=None, employment_type=None, sort="newest",
                     profile_id=None) -> list:
    """Filtered/sorted/paged jobs with company + optional intelligence.

    Intelligence columns/filters/sorts only apply when ``profile_id`` joins
    in that profile's ``job_matches``; otherwise those columns are NULL.
    """
    safe_limit = max(1, min(int(limit), 50))
    safe_offset = max(0, int(offset))
    join, join_params = "", []
    intel = "NULL AS match_score, NULL AS trust_score, NULL AS recommendation, " \
            "NULL AS strengths, NULL AS missing_skills, NULL AS reason"
    if profile_id:
        join = "LEFT JOIN public.job_matches m ON m.job_id = j.id AND m.profile_id = %s"
        join_params = [profile_id]
        intel = _INTEL_COLS
    clauses, filter_params = _job_filter_clauses(
        search=search, role=role, location=location, remote=remote,
        min_match=min_match, min_trust=min_trust, recommendation=recommendation,
        employment_type=employment_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    order = _JOB_SORTS.get(sort, _JOB_SORTS["newest"])
    return db.fetch_all(
        f"""SELECT j.id, j.title, j.location, j.is_remote, j.employment_type,
                  j.apply_url, j.status, j.posted_at, j.created_at, j.updated_at,
                  j.salary_min, j.salary_max, j.salary_currency,
                  c.name AS company_name, {intel}
           FROM public.jobs j
           LEFT JOIN public.companies c ON c.id = j.company_id
           {join}
           {where}
           ORDER BY {order}
           LIMIT %s OFFSET %s""",
        tuple(join_params + filter_params + [safe_limit, safe_offset]),
    )


def count_search_jobs(search=None, role=None, location=None, remote=None,
                      min_match=None, min_trust=None, recommendation=None,
                      employment_type=None, profile_id=None) -> int:
    """Total rows matching the same filters (for paged responses)."""
    join, join_params = "", []
    if profile_id:
        join = "LEFT JOIN public.job_matches m ON m.job_id = j.id AND m.profile_id = %s"
        join_params = [profile_id]
    clauses, filter_params = _job_filter_clauses(
        search=search, role=role, location=location, remote=remote,
        min_match=min_match, min_trust=min_trust, recommendation=recommendation,
        employment_type=employment_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    row = db.fetch_one(
        f"""SELECT COUNT(*) AS total
           FROM public.jobs j
           LEFT JOIN public.companies c ON c.id = j.company_id
           {join}
           {where}""",
        tuple(join_params + filter_params),
    )
    return int((row or {}).get("total") or 0)


def list_job_sources(job_id: str) -> list:
    """Discovery sources for one job, earliest first (Phase 5.4 detail view)."""
    return db.fetch_all(
        """SELECT source_type, source_name, source_url, apply_url,
                  source_job_id, discovered_at
           FROM public.job_sources
           WHERE job_id = %s
           ORDER BY discovered_at ASC""",
        (job_id,),
    )

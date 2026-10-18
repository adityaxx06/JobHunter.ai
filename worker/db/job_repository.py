"""Worker-side job persistence: NormalizedJob -> companies/jobs/job_sources (Phase 5.1).

Mapping (existing schema columns only — nothing invented):
  NormalizedJob.normalized_title      -> jobs.normalized_title
  original.title                      -> jobs.title
  original.description (or NULL)      -> jobs.description
  original.location (or NULL)         -> jobs.location
  normalized.is_remote                -> jobs.is_remote
  normalized employment (fallback original) -> jobs.employment_type
  original.experience_level (or NULL) -> jobs.experience_level
  original.salary_min/max (ints only) -> jobs.salary_min/max
  original.salary_currency (or 'INR') -> jobs.salary_currency
  normalized_skills (JSONB array)      -> jobs.skills
  original.posted_at (or NULL)        -> jobs.posted_at
  apply_url as both links             -> jobs.canonical_url + jobs.apply_url
  'active'                            -> jobs.status (schema default)
  last_seen_at is touched on every re-seen (recency without counting as update)

Lookup strategy (no fingerprint column in the schema — by design):
  1. Exact apply_url match (non-empty) wins immediately.
  2. Otherwise candidates by normalized_title (latest 200, with company names
     joined in); the existing worker fingerprint is recomputed per candidate
     and compared. A fingerprint covers normalized company + title + location
     + apply URL, so equal fingerprints mean all four match — same company
     with a merely similar title, or a different location/URL, never merges.
  3. No match -> insert.

Idempotency: re-persisting only fills empty/missing fields (never overwrites
good values with blanks) and reuses the existing job_sources row, so a second
identical run inserts nothing.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from worker.db import client as db
from worker.models.job import DiscoveryResult, NormalizedJob
from worker.processors.normalizer.job_normalizer import normalize_company_name, normalize_location
from worker.utils.job_fingerprint import build_fingerprint

logger = logging.getLogger("ai-jobhunter.persist")

#: NormalizedJobs from this source are demo fixtures, never production rows.
MOCK_SOURCE_NAME = "mock"

#: Candidate scan cap for fingerprint comparison (mirrors backend repository).
_FINGERPRINT_CANDIDATE_LIMIT = 200


@dataclass
class PersistenceResult:
    """Structured outcome of persisting a discovery run."""

    discovered_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    duplicate_count: int = 0  # re-seen jobs needing no changes
    source_links_created: int = 0
    companies_created: int = 0
    skipped_count: int = 0  # mock rows skipped without explicit opt-in
    errors: list = field(default_factory=list)

    def summary(self) -> dict:
        """Plain-dict summary (handy for logging and tests)."""
        return {
            "discovered": self.discovered_count,
            "inserted": self.inserted_count,
            "updated": self.updated_count,
            "duplicates": self.duplicate_count,
            "source_links": self.source_links_created,
            "companies": self.companies_created,
            "skipped": self.skipped_count,
            "errors": len(self.errors),
        }


def _as_int(value: object) -> Optional[int]:
    """Plain ints only (bools/strings/None rejected — never coerced)."""
    if isinstance(value, bool):
        return None
    return int(value) if isinstance(value, int) else None


def ensure_company(tx, display_name: str, normalized_name: str, domain: str = "") -> tuple:
    """Find a company by normalized_name or insert it. Returns (row, created)."""
    tx.execute(
        "SELECT id, name, normalized_name, domain FROM public.companies WHERE normalized_name = %s",
        (normalized_name,),
    )
    row = tx.fetchone()
    if row is not None:
        return dict(row), False
    tx.execute(
        """INSERT INTO public.companies (name, normalized_name, domain)
           VALUES (%s, %s, %s)
           RETURNING id, name, normalized_name, domain""",
        (display_name or normalized_name, normalized_name, domain or None),
    )
    return dict(tx.fetchone()), True


def find_existing_job(tx, fingerprint: str, normalized_title: str, normalized_company: str,
                      normalized_location: str, apply_url: str = "") -> Optional[dict]:
    """Locate the canonical row for a fingerprinted job (None when new)."""
    if apply_url:
        tx.execute(
            """SELECT j.*, c.normalized_name AS company_normalized_name
               FROM public.jobs j LEFT JOIN public.companies c ON c.id = j.company_id
               WHERE j.apply_url = %s LIMIT 1""",
            (apply_url,),
        )
        row = tx.fetchone()
        if row is not None:
            return dict(row)
    tx.execute(
        """SELECT j.*, c.normalized_name AS company_normalized_name
           FROM public.jobs j LEFT JOIN public.companies c ON c.id = j.company_id
           WHERE j.normalized_title = %s
           ORDER BY j.first_seen_at DESC LIMIT %s""",
        (normalized_title, _FINGERPRINT_CANDIDATE_LIMIT),
    )
    for candidate in tx.fetchall() or []:
        candidate_fp = build_fingerprint(
            candidate.get("company_normalized_name") or "",
            candidate.get("normalized_title") or candidate.get("title") or "",
            normalize_location(candidate.get("location") or ""),
            candidate.get("apply_url") or "",
            candidate.get("canonical_url") or "",
        )
        if candidate_fp == fingerprint:
            return dict(candidate)
    return None


def insert_job(tx, company_id: Optional[str], norm: NormalizedJob) -> dict:
    """Insert a job row from a normalized job. Returns the new row."""
    original = norm.original
    tx.execute(
        """INSERT INTO public.jobs
           (company_id, title, normalized_title, description, location, is_remote,
            employment_type, experience_level, salary_min, salary_max, salary_currency,
            skills, posted_at, canonical_url, apply_url, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, 'active')
           RETURNING id, company_id, title, normalized_title""",
        (
            company_id,
            original.title,
            norm.normalized_title,
            original.description.strip() or None if isinstance(original.description, str) else None,
            original.location.strip() or None if isinstance(original.location, str) else None,
            bool(norm.is_remote),
            norm.normalized_employment_type or (original.employment_type or None),
            original.experience_level.strip() or None if isinstance(original.experience_level, str) else None,
            _as_int(original.salary_min),
            _as_int(original.salary_max),
            original.salary_currency if isinstance(original.salary_currency, str) and original.salary_currency.strip() else "INR",
            json.dumps(list(norm.normalized_skills or [])),
            original.posted_at,
            original.apply_url.strip() or None if isinstance(original.apply_url, str) else None,
            original.apply_url.strip() or None if isinstance(original.apply_url, str) else None,
        ),
    )
    return dict(tx.fetchone())


#: Columns refreshed only when the incoming value is non-blank and different.
_MUTABLE_COLUMNS = (
    "description",
    "location",
    "employment_type",
    "experience_level",
    "salary_min",
    "salary_max",
    "apply_url",
    "canonical_url",
)


def _incoming_values(norm: NormalizedJob) -> dict:
    """Candidate refresh values in jobs-column terms (None = no opinion)."""
    original = norm.original
    text = lambda v: (v.strip() or None) if isinstance(v, str) else None
    return {
        "description": text(original.description),
        "location": text(original.location),
        "employment_type": norm.normalized_employment_type or text(original.employment_type),
        "experience_level": text(original.experience_level),
        "salary_min": _as_int(original.salary_min),
        "salary_max": _as_int(original.salary_max),
        "apply_url": text(original.apply_url),
        "canonical_url": text(original.apply_url),
    }


def refresh_job(tx, existing: dict, norm: NormalizedJob) -> tuple:
    """Fill blank/stale mutable columns (plus last_seen_at). Returns (row, improved)."""
    incoming = _incoming_values(norm)
    changes = {col: incoming[col] for col in _MUTABLE_COLUMNS
               if incoming[col] is not None and incoming[col] != existing.get(col)}
    if changes:
        names = list(changes.keys())
        set_clause = ", ".join(f"{name} = %s" for name in names)
        params = [changes[name] for name in names] + [existing["id"]]
        tx.execute(
            f"""UPDATE public.jobs SET {set_clause}, last_seen_at = NOW()
                WHERE id = %s RETURNING id, company_id, title, normalized_title""",
            tuple(params),
        )
        return dict(tx.fetchone()), True
    tx.execute("UPDATE public.jobs SET last_seen_at = NOW() WHERE id = %s RETURNING id", (existing["id"],))
    return dict(tx.fetchone()), False


def ensure_source_link(tx, job_id: str, norm: NormalizedJob) -> tuple:
    """Reuse or create the job_sources row. Returns (row, created)."""
    original = norm.original
    external_id = original.external_id.strip() if isinstance(original.external_id, str) else ""
    tx.execute(
        """SELECT id FROM public.job_sources
           WHERE job_id = %s AND source_type = %s AND source_name = %s
             AND source_job_id IS NOT DISTINCT FROM %s""",
        (job_id, original.source_type, original.source_name, external_id or None),
    )
    row = tx.fetchone()
    if row is not None:
        return dict(row), False
    tx.execute(
        """INSERT INTO public.job_sources
           (job_id, source_type, source_name, source_url, apply_url, source_job_id, metadata)
           VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
           RETURNING id""",
        (
            job_id,
            original.source_type,
            original.source_name,
            original.source_url.strip() or None if isinstance(original.source_url, str) else None,
            original.apply_url.strip() or None if isinstance(original.apply_url, str) else None,
            external_id or None,
            json.dumps({"fingerprint": norm.fingerprint}),
        ),
    )
    return dict(tx.fetchone()), True


def _is_mock(norm: NormalizedJob) -> bool:
    """Demo fixtures are never production rows without explicit opt-in."""
    return (norm.original.source_name or "") == MOCK_SOURCE_NAME


def persist_job(norm: NormalizedJob, *, allow_mock: bool = False) -> dict:
    """Persist one normalized job transactionally. Returns outcome details."""
    if _is_mock(norm) and not allow_mock:
        return {"action": "skipped", "job_id": None}
    original = norm.original
    normalized_company = norm.normalized_company or normalize_company_name(original.company_name, original.company_domain)
    fingerprint = norm.fingerprint or build_fingerprint(
        normalized_company, norm.normalized_title, norm.normalized_location, original.apply_url or ""
    )
    apply_url = original.apply_url.strip() if isinstance(original.apply_url, str) else ""
    with db.transaction() as tx:
        company_id, company_created = None, False
        if normalized_company:
            display = original.company_name.strip() if isinstance(original.company_name, str) and original.company_name.strip() else normalized_company
            domain = original.company_domain.strip() if isinstance(original.company_domain, str) and original.company_domain.strip() else ""
            company, company_created = ensure_company(tx, display, normalized_company, domain)
            company_id = company["id"]
        existing = find_existing_job(
            tx, fingerprint, norm.normalized_title, normalized_company, norm.normalized_location, apply_url
        )
        if existing is None:
            job = insert_job(tx, company_id, norm)
            action = "inserted"
        else:
            job, improved = refresh_job(tx, existing, norm)
            job = {"id": existing["id"], **job}
            action = "updated" if improved else "duplicate"
        _, link_created = ensure_source_link(tx, job["id"], norm)
        return {"action": action, "job_id": job["id"],
                "company_created": company_created, "source_link_created": link_created}


def persist_discovery_result(discovery: DiscoveryResult, *, allow_mock: bool = False) -> PersistenceResult:
    """Persist every job in a DiscoveryResult. Per-job failures are captured."""
    result = PersistenceResult(discovered_count=len(discovery.jobs or []))
    if not db.is_configured():
        result.errors.append("database not configured (DATABASE_URL is missing) — nothing persisted")
        return result
    for norm in discovery.jobs or []:
        try:
            outcome = persist_job(norm, allow_mock=allow_mock)
        except Exception as exc:
            logger.warning("persist failed: %s", type(exc).__name__)
            result.errors.append(f"persist failed for '{getattr(getattr(norm, 'original', None), 'title', '?')}': {type(exc).__name__}")
            continue
        action = outcome["action"]
        if action == "inserted":
            result.inserted_count += 1
        elif action == "updated":
            result.updated_count += 1
        elif action == "duplicate":
            result.duplicate_count += 1
        elif action == "skipped":
            result.skipped_count += 1
        if outcome.get("company_created"):
            result.companies_created += 1
        if outcome.get("source_link_created"):
            result.source_links_created += 1
    return result

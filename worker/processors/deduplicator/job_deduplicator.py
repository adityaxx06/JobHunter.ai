"""In-memory duplicate detection over normalized jobs (Phase 4.1).

A job is a duplicate when its fingerprint was seen before, or when its
apply URL (falling back to source URL) was seen before — using the same
normalized company/title/location/URL signals as fingerprinting. No AI.
Operates on in-memory lists (e.g. 100 discovered -> ~80 unique); DB-backed
dedup arrives with Phase 5.
"""

from worker.models.job import DedupeResult, NormalizedJob
from worker.utils.job_fingerprint import _norm_url


def _link_key(job: NormalizedJob) -> str:
    """Canonical URL identity: normalized apply URL, else source URL."""
    link = _norm_url(job.original.apply_url)
    if link:
        return link
    return _norm_url(job.original.source_url)


def deduplicate_jobs(jobs: list) -> DedupeResult:
    """Split normalized jobs into unique rows + duplicates (order kept)."""
    seen_fingerprints = set()
    seen_links = set()
    unique = []
    duplicates = []
    for job in jobs:
        link = _link_key(job)
        if job.fingerprint in seen_fingerprints or (link and link in seen_links):
            duplicates.append(job)
            continue
        seen_fingerprints.add(job.fingerprint)
        if link:
            seen_links.add(link)
        unique.append(job)
    return DedupeResult(
        unique_jobs=unique,
        duplicate_count=len(duplicates),
        duplicates=duplicates,
    )

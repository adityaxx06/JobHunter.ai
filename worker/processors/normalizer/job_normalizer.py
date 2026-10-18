"""Job normalization: raw posting -> canonical values (Phase 4.1).

Normalizes title, company, location, employment type, and skills while
keeping the original values on :class:`NormalizedJob`. Deliberately
conservative: case/whitespace/punctuation folding only — meaning is never
rewritten (no title rewriting, no skill aliasing). Remote detection also
honors explicit location text ("remote") alongside the source flag.
"""

import re

from worker.models.job import DiscoveredJob, NormalizedJob
from worker.utils.job_fingerprint import build_fingerprint

_WS = re.compile(r"\s+")
# Keep tech-relevant symbols (+ # .) while folding decorative punctuation.
_TITLE_KEEP = set("+#.")

_COMPANY_SUFFIXES = (
    " pvt. ltd.", " pvt ltd", " private limited",
    " inc.", " inc", " llc", " llp", " ltd.", " ltd",
    " technologies", " technology", " solutions", " systems",
    " labs", " software",
)


def _clean(value: object) -> str:
    """Lowercase, trim, collapse whitespace. Non-strings become ''."""
    if not isinstance(value, str):
        return ""
    return _WS.sub(" ", value.strip().lower())


def normalize_title(title: object) -> str:
    """Fold case/whitespace/punctuation; drop hiring-site noise words."""
    text = _clean(title)
    if not text:
        return ""
    # Strip job-board noise BEFORE punctuation folding (parens matter here).
    for noise in (" - hiring now", " (hiring)", " [hiring]", " urgent hiring"):
        if text.endswith(noise):
            text = text[: -len(noise)].strip()
    text = text.replace("_", " ")
    text = "".join(ch for ch in text if ch.isalnum() or ch.isspace() or ch in _TITLE_KEEP)
    return _WS.sub(" ", text).strip(" -–—:|")


def normalize_company_name(name: object, domain: object = "") -> str:
    """Fold case/whitespace; strip legal-entity suffixes; fall back to domain."""
    text = _clean(name)
    # Strip repeatedly ("... technologies pvt. ltd." -> "..." -> base name).
    changed = True
    while changed:
        changed = False
        for suffix in _COMPANY_SUFFIXES:
            if text.endswith(suffix) and len(text) > len(suffix) + 2:
                text = text[: -len(suffix)].strip()
                changed = True
                break
    if text:
        return text
    host = _clean(domain).replace("www.", "")
    return host.split("/")[0]


def normalize_location(location: object) -> str:
    """Fold case/whitespace; normalize separators to ', '."""
    text = _clean(location)
    if not text:
        return ""
    parts = [p.strip() for p in re.split(r"[;/|]", text) for p in p.split(",")]
    return ", ".join(p for p in parts if p)


def primary_location(normalized_location: str) -> str:
    """First segment of a normalized location ('chennai' from 'chennai, ...')."""
    return normalized_location.split(",")[0].strip() if normalized_location else ""


_EMPLOYMENT_MAP = {
    "full time": "full_time",
    "full-time": "full_time",
    "fulltime": "full_time",
    "part time": "part_time",
    "part-time": "part_time",
    "contract": "contract",
    "intern": "internship",
    "internship": "internship",
    "freelance": "freelance",
    "remote": "remote",
}


def normalize_employment_type(value: object) -> str:
    """Map common variants to a stable token; unknown values pass through cleaned."""
    text = _clean(value).replace("_", " ")
    if not text:
        return ""
    if text in _EMPLOYMENT_MAP:
        return _EMPLOYMENT_MAP[text]
    for variant, token in _EMPLOYMENT_MAP.items():
        if variant in text:
            return token
    return text


def normalize_skills(skills: object) -> list:
    """Lowercase + strip + de-duplicate (order-preserving)."""
    if not isinstance(skills, (list, tuple)):
        return []
    seen = set()
    out = []
    for skill in skills:
        s = _clean(skill)
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def detect_remote(job: DiscoveredJob, normalized_location: str) -> bool:
    """Remote when the source says so or the location text says 'remote'."""
    if job.is_remote:
        return True
    return "remote" in normalized_location.split(",")


def normalize_job(job: DiscoveredJob) -> NormalizedJob:
    """Normalize one posting and attach its fingerprint."""
    normalized_company = normalize_company_name(job.company_name, job.company_domain)
    normalized_title = normalize_title(job.title)
    normalized_location = normalize_location(job.location or ", ".join(job.locations))
    fingerprint = build_fingerprint(
        normalized_company,
        normalized_title,
        normalized_location,
        job.apply_url or "",
    )
    return NormalizedJob(
        original=job,
        normalized_title=normalized_title,
        normalized_company=normalized_company,
        normalized_location=normalized_location,
        primary_location=primary_location(normalized_location),
        normalized_employment_type=normalize_employment_type(job.employment_type),
        normalized_skills=normalize_skills(job.skills),
        is_remote=detect_remote(job, normalized_location),
        fingerprint=fingerprint,
    )


def normalize_jobs(jobs: list) -> list:
    """Normalize a batch (order preserved)."""
    return [normalize_job(job) for job in jobs]

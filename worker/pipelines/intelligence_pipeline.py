"""Intelligence pipeline: persisted jobs -> rules -> Gemini -> job_matches (Phase 5.2).

Free-first and failure-isolated: the rule prefilter runs before any billable
call, cached evaluations are reused without new calls, per-run AI volume is
capped, and every per-job failure (AI, validation, or DB) is recorded while
the run continues. Mock fixtures never consume quota. Nothing secret is
logged — job UUIDs and error kinds only.
"""

import json
import logging
from typing import Optional

from ai.prompts.job_intelligence import build_prompt
from ai.providers.base import AIRequest
from ai.providers.gemini import GeminiProvider
from worker.db import client as db
from worker.db import match_repository as matches
from worker.db import profile_repository as profiles
from worker.models.intelligence import IntelligencePipelineResult
from worker.processors.intelligence import config as ai_config
from worker.processors.intelligence.prefilter import prefilter_job
from worker.processors.intelligence.validator import validate_intelligence

logger = logging.getLogger("ai-jobhunter.intelligence")

_JOB_COLUMNS = (
    "j.id, j.company_id, j.title, j.description, j.location, j.is_remote, "
    "j.employment_type, j.experience_level, j.salary_min, j.salary_max, "
    "j.salary_currency, j.skills, j.posted_at, j.apply_url, j.status"
)


def _salary_text(job: dict) -> str:
    """Human salary summary (or Unknown — never invented)."""
    low, high, currency = job.get("salary_min"), job.get("salary_max"), job.get("salary_currency")
    if low is None and high is None:
        return "Unknown"
    if low is not None and high is not None:
        return f"{low}-{high} {currency or ''}".strip()
    return f"{low if low is not None else high} {currency or ''}".strip() or "Unknown"


def _job_view(row: dict, source_types: list) -> dict:
    """DB row (+ sources) -> prompt/prefilter view (no credentials, no metadata)."""
    skills = row.get("skills")
    return {
        "job_id": row.get("id"),
        "title": row.get("title") or "",
        "company_name": row.get("company_name") or "",
        "description": row.get("description") or "",
        "location": row.get("location") or "",
        "employment_type": row.get("employment_type") or "",
        "experience_level": row.get("experience_level") or "",
        "skills": list(skills) if isinstance(skills, list) else [],
        "salary": _salary_text(row),
        "apply_url": row.get("apply_url") or "",
        "source": ", ".join(source_types) if source_types else "Unknown",
        "source_types": list(source_types),
        "is_remote": bool(row.get("is_remote")),
    }


def _load_jobs(job_limit: int) -> list:
    """Recent active jobs with company names (bounded, read-only)."""
    rows = db.fetch_all(
        f"""SELECT {_JOB_COLUMNS}, c.name AS company_name
            FROM public.jobs j LEFT JOIN public.companies c ON c.id = j.company_id
            WHERE j.status = 'active'
            ORDER BY j.last_seen_at DESC LIMIT %s""",
        (max(1, int(job_limit)),),
    )
    return [dict(r) for r in (rows or [])]


def _load_sources(job_ids: list) -> dict:
    """job_id -> (source_types, source_names) for the given jobs."""
    mapping = {job_id: ([], []) for job_id in job_ids}
    if not job_ids:
        return mapping
    rows = db.fetch_all(
        """SELECT job_id, source_type, source_name FROM public.job_sources
           WHERE job_id = ANY(%s)""",
        (list(job_ids),),
    )
    for row in rows or []:
        if row.get("job_id") in mapping:
            if row.get("source_type"):
                mapping[row["job_id"]][0].append(row["source_type"])
            if row.get("source_name"):
                mapping[row["job_id"]][1].append(row["source_name"])
    return mapping


def _is_mock_job(source_names: list) -> bool:
    """Demo fixtures (source_name 'mock') must never consume AI quota."""
    return "mock" in [str(name) for name in source_names]


def _provider_configured(provider) -> bool:
    """Duck-typed readiness (real provider checks its key; fakes opt out)."""
    check = getattr(provider, "is_configured", None)
    return bool(check()) if callable(check) else True


def run_intelligence(profile_id: Optional[str] = None, job_limit: int = 50,
                     provider=None, refresh: bool = False,
                     max_ai_jobs: Optional[int] = None, dry_run: bool = False) -> IntelligencePipelineResult:
    """Analyze persisted jobs for one candidate. Never raises on job errors.

    With ``dry_run=True`` the full selection runs (gates, job load, prefilter,
    cache checks, cap) but no AI call is made and nothing is written — the
    count of jobs that WOULD be analyzed lands in ``jobs_would_analyze``.
    Default False preserves the exact Phase 5.2 behavior.
    """
    result = IntelligencePipelineResult()
    if not ai_config.is_ai_enabled():
        result.errors.append("AI disabled — set AI_ENABLED=true to enable intelligence")
        return result
    if not db.is_configured():
        result.errors.append("database not configured — intelligence skipped")
        return result
    provider = provider or GeminiProvider(timeout=ai_config.request_timeout())
    if not _provider_configured(provider):
        result.errors.append("Gemini not configured — intelligence skipped")
        return result

    try:
        candidate = profiles.load_candidate(profile_id)
    except Exception as exc:
        result.errors.append(f"candidate load failed: {type(exc).__name__}")
        return result
    if candidate is None:
        result.errors.append("no candidate profile found — intelligence skipped")
        return result

    try:
        rows = _load_jobs(job_limit)
        source_map = _load_sources([r["id"] for r in rows])
    except Exception as exc:
        result.errors.append(f"job load failed: {type(exc).__name__}")
        return result
    result.jobs_received = len(rows)

    cap = max(1, int(max_ai_jobs)) if max_ai_jobs is not None else ai_config.max_jobs_per_run()
    sent = 0
    model_tag = f"gemini:{getattr(provider, 'model', getattr(provider, 'name', 'ai'))}"
    for row in rows:
        job_id = row["id"]
        source_types, source_names = source_map.get(job_id, ([], []))
        if _is_mock_job(source_names):
            result.skipped_mock += 1
            logger.info("mock job skipped (%s)", job_id)
            continue
        view = _job_view(row, source_types)
        try:
            pre = prefilter_job(view, candidate)
        except Exception as exc:
            result.errors.append(f"job {job_id}: prefilter failed ({type(exc).__name__})")
            continue
        if not pre.eligible_for_ai:
            result.jobs_rejected_by_rules += 1
            continue
        result.jobs_prefiltered += 1
        try:
            if not refresh and matches.is_analyzed(candidate["profile_id"], job_id):
                stored = matches.get_match(candidate["profile_id"], job_id)
                result.cached_results += 1
                result.jobs_analyzed += 1
                rec = (stored or {}).get("recommendation") or "UNKNOWN"
                result.recommendations[rec] = result.recommendations.get(rec, 0) + 1
                continue
        except Exception as exc:
            result.errors.append(f"job {job_id}: cache check failed ({type(exc).__name__})")
            continue
        if dry_run:
            # Preview only: count cap-bounded candidates, call nothing, write nothing.
            if result.jobs_would_analyze >= cap:
                break
            result.jobs_would_analyze += 1
            continue
        if sent >= cap:
            break  # quota guard: remaining candidates wait for the next run
        sent += 1
        result.jobs_sent_to_ai += 1
        try:
            response = provider.generate(AIRequest(prompt=build_prompt(candidate, view)))
            intelligence = validate_intelligence(json.loads(response.text))
        except Exception as exc:
            kind = type(exc).__name__
            if "JSON" in kind or "Validation" in kind or isinstance(exc, (ValueError,)):
                result.errors.append(f"job {job_id}: invalid AI output ({kind})")
            else:
                result.errors.append(f"job {job_id}: AI call failed ({kind})")
            continue
        try:
            _, created = matches.save_match(candidate["profile_id"], job_id, intelligence, analyzed_by=model_tag)
        except Exception as exc:
            result.errors.append(f"job {job_id}: match save failed ({type(exc).__name__})")
            continue
        result.jobs_analyzed += 1
        if created:
            result.matches_saved += 1
        else:
            result.matches_updated += 1
        result.recommendations[intelligence.recommendation] = result.recommendations.get(intelligence.recommendation, 0) + 1

    logger.info(
        "AI Job Intelligence | received=%d rejected=%d candidates=%d sent=%d scored=%d cached=%d errors=%d | %s",
        result.jobs_received, result.jobs_rejected_by_rules, result.jobs_prefiltered,
        result.jobs_sent_to_ai, result.jobs_analyzed, result.cached_results,
        len(result.errors), result.recommendations,
    )
    return result

"""Ranking pipeline: analyzed matches -> deterministic ranked list (Phase 5.3).

Zero AI calls by construction — this module never imports the AI providers
and consumes only stored Phase 5.2 intelligence. Flow: load candidate
preferences, load every analyzed match for the profile, validate each row
(invalid rows are counted as excluded, never silently dropped), apply
optional filters, optionally enforce Latest-feed eligibility (freshness +
geography + role fit via the shared eligibility gate), score everything,
sort deterministically, assign ranks, then take top-N. Ranking is recomputed
on demand; nothing is persisted.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from worker.db import client as db
from worker.db import profile_repository as profiles
from worker.db import ranking_repository as ranking_repo
from worker.models.ranking import RankedJob, RankingFilter, RankingPipelineResult
from worker.processors.ranking import eligibility as eligibility_gate
from worker.processors.ranking.scorer import (
    calculate_ranking_score,
    employment_preference,
    location_preference,
    role_preference,
    skill_bonus,
    sort_key,
)

logger = logging.getLogger("ai-jobhunter.ranking")


def _valid_row(row: dict):
    """Return (match, trust, recommendation) or None for invalid rows."""
    match, trust, rec = row.get("match_score"), row.get("trust_score"), row.get("recommendation")
    if isinstance(match, bool) or not isinstance(match, int):
        return None
    if isinstance(trust, bool) or not isinstance(trust, int):
        return None
    if not (0 <= match <= 100 and 0 <= trust <= 100):
        return None
    if rec not in ("APPLY", "CONSIDER", "REVIEW", "AVOID"):
        return None
    if not row.get("job_id"):
        return None
    return match, trust, rec


def _passes_filters(row: dict, match: int, trust: int, filters: Optional[RankingFilter]) -> bool:
    """Optional pre-ranking filters (None filter = everything passes)."""
    if filters is None:
        return True
    if filters.min_match_score is not None and match < filters.min_match_score:
        return False
    if filters.min_trust_score is not None and trust < filters.min_trust_score:
        return False
    if filters.recommendation is not None and row.get("recommendation") != filters.recommendation:
        return False
    if filters.employment_type is not None and (row.get("employment_type") or "") != filters.employment_type:
        return False
    if filters.location is not None and filters.location.lower() not in (row.get("location") or "").lower():
        return False
    if filters.remote is not None and bool(row.get("is_remote")) is not filters.remote:
        return False
    return True


def _score_row(row: dict, match: int, trust: int, rec: str, candidate: dict) -> dict:
    """Score one valid row into a sortable intermediate (+ reasons)."""
    role_score, role_reason = role_preference(
        row.get("title"), candidate.get("target_roles") or [])
    loc_score, loc_reason = location_preference(
        row.get("location"), bool(row.get("is_remote")),
        candidate.get("locations") or [], bool(candidate.get("remote_ok")))
    emp_score, emp_reason = employment_preference(row.get("employment_type"))
    preference = role_score + loc_score + emp_score
    skills_bonus, skills_reason = skill_bonus(row.get("matched_skills"))
    score, reasons, _ = calculate_ranking_score(match, trust, rec, preference, skills_bonus)
    for extra in (role_reason, loc_reason, emp_reason, skills_reason):
        if extra:
            reasons.append(extra)
    return {
        "job_id": row.get("job_id"), "ranking_score": score,
        "match_score": match, "trust_score": trust, "recommendation": rec,
        "role_score": role_score, "location_score": loc_score,
        "reasons": reasons, "row": row,
    }


def rank_jobs_for_profile(profile_id: Optional[str] = None, limit: int = 20,
                           min_match_score: Optional[int] = None,
                           min_trust_score: Optional[int] = None,
                           filters: Optional[RankingFilter] = None,
                           eligible_only: bool = False) -> RankingPipelineResult:
    """Rank every valid analyzed job for a profile; return the top-N.

    Reusable by Phase 5.4 (FastAPI). No AI, no network, no writes.
    With ``eligible_only=True``, rows failing the shared Latest-feed gate
    (stale/unknown date, non-India geography, role misfit) are counted as
    ineligible instead of ranked — the default path is unchanged.
    """
    result = RankingPipelineResult()
    if not db.is_configured():
        result.ranking_errors.append("database not configured — ranking skipped")
        return result
    if filters is None and (min_match_score is not None or min_trust_score is not None):
        filters = RankingFilter(min_match_score=min_match_score, min_trust_score=min_trust_score)
    try:
        candidate = profiles.load_candidate(profile_id)
    except Exception as exc:
        result.ranking_errors.append(f"candidate load failed: {type(exc).__name__}")
        return result
    if candidate is None:
        result.ranking_errors.append("no candidate profile found — ranking skipped")
        return result
    try:
        rows = ranking_repo.load_ranking_inputs(candidate["profile_id"])
    except Exception as exc:
        result.ranking_errors.append(f"match load failed: {type(exc).__name__}")
        return result
    result.jobs_received = len(rows)

    now = datetime.now(timezone.utc)
    max_age_days = eligibility_gate.get_max_age_days()
    country = eligibility_gate.get_target_country()
    seen_jobs = set()
    scored = []
    for row in rows:
        if row.get("job_id") in seen_jobs:
            continue  # one canonical job ranks once even with many sources
        seen_jobs.add(row.get("job_id"))
        valid = _valid_row(row)
        if valid is None:
            result.jobs_excluded += 1
            result.ranking_errors.append(f"job {row.get('job_id') or '?'}: invalid intelligence skipped")
            continue
        match, trust, rec = valid
        if not _passes_filters(row, match, trust, filters):
            continue
        if eligible_only:
            verdict = eligibility_gate.assess_job(
                eligibility_gate.build_job_view(row), candidate,
                now, max_age_days, country)
            if not verdict.eligible:
                result.ineligible_count += 1
                continue
        try:
            scored.append(_score_row(row, match, trust, rec, candidate))
        except Exception as exc:
            result.jobs_excluded += 1
            result.ranking_errors.append(f"job {row.get('job_id') or '?'}: scoring failed ({type(exc).__name__})")

    scored.sort(key=sort_key)
    result.jobs_ranked = len(scored)
    top = scored[: max(0, int(limit))]
    for position, entry in enumerate(top, 1):
        row = entry["row"]
        result.ranked_jobs.append(RankedJob(
            job_id=entry["job_id"], profile_id=candidate["profile_id"], rank=position,
            ranking_score=entry["ranking_score"], match_score=entry["match_score"],
            trust_score=entry["trust_score"], recommendation=entry["recommendation"],
            priority_reasons=entry["reasons"], title=row.get("title") or "",
            company_name=row.get("company_name") or "", location=row.get("location") or "",
            is_remote=bool(row.get("is_remote")), apply_url=row.get("apply_url") or "",
            strengths=list(row.get("strengths") or []) if isinstance(row.get("strengths"), list) else [],
            missing_skills=list(row.get("missing_skills") or []) if isinstance(row.get("missing_skills"), list) else [],
            reason=row.get("reason") or "",
            salary_min=row.get("salary_min") if isinstance(row.get("salary_min"), int) else None,
            salary_max=row.get("salary_max") if isinstance(row.get("salary_max"), int) else None,
            salary_currency=row.get("salary_currency") or None,
            employment_type=row.get("employment_type") or "",
        ))
    logger.info(
        "Job Ranking | profile=%s considered=%d ranked=%d excluded=%d errors=%d",
        candidate["profile_id"], result.jobs_received, result.jobs_ranked,
        result.jobs_excluded, len(result.ranking_errors),
    )
    return result

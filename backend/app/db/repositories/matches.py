"""Match repository: evaluations of a job vs a profile (Phase 3).

Ranked reads sort by match_score DESC, trust_score DESC, posted_at DESC.
No AI calls here — rows are written by the future Phase 6 scorer; Phase 3
only reads/writes the stored evaluations.
"""

from typing import Optional

from app.db import connection as db


def get_match(profile_id: str, job_id: str) -> Optional[dict]:
    """Fetch the single evaluation for a profile+job (None when absent)."""
    return db.fetch_one(
        """SELECT id, profile_id, job_id, match_score, trust_score, recommendation,
                  matched_skills, missing_skills, strengths, risk_signals,
                  reason, analyzed_by, analyzed_at, created_at, updated_at
           FROM public.job_matches
           WHERE profile_id = %s AND job_id = %s""",
        (profile_id, job_id),
    )


def create_or_update_match(
    profile_id: str,
    job_id: str,
    match_score: Optional[int] = None,
    trust_score: Optional[int] = None,
    recommendation: Optional[str] = None,
    matched_skills: Optional[list] = None,
    missing_skills: Optional[list] = None,
    strengths: Optional[list] = None,
    risk_signals: Optional[list] = None,
    reason: Optional[str] = None,
    analyzed_by: Optional[str] = None,
) -> Optional[dict]:
    """Insert or (on profile+job conflict) refresh the stored evaluation."""
    import json

    def _dump(value: Optional[list]) -> str:
        return json.dumps(value or [])

    return db.execute(
        """INSERT INTO public.job_matches
           (profile_id, job_id, match_score, trust_score, recommendation,
            matched_skills, missing_skills, strengths, risk_signals,
            reason, analyzed_by, analyzed_at)
           VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
                   %s, %s, NOW())
           ON CONFLICT (profile_id, job_id) DO UPDATE SET
             match_score = EXCLUDED.match_score,
             trust_score = EXCLUDED.trust_score,
             recommendation = EXCLUDED.recommendation,
             matched_skills = EXCLUDED.matched_skills,
             missing_skills = EXCLUDED.missing_skills,
             strengths = EXCLUDED.strengths,
             risk_signals = EXCLUDED.risk_signals,
             reason = EXCLUDED.reason,
             analyzed_by = EXCLUDED.analyzed_by,
             analyzed_at = NOW()
           RETURNING id, profile_id, job_id, match_score, trust_score, recommendation,
                     matched_skills, missing_skills, strengths, risk_signals,
                     reason, analyzed_by, analyzed_at""",
        (
            profile_id,
            job_id,
            match_score,
            trust_score,
            recommendation,
            _dump(matched_skills),
            _dump(missing_skills),
            _dump(strengths),
            _dump(risk_signals),
            reason,
            analyzed_by,
        ),
    )


def list_top_matches(profile_id: str, limit: int = 20) -> list:
    """Ranked evaluations for a profile (match, trust, recency)."""
    safe_limit = max(1, min(int(limit), 100))
    return db.fetch_all(
        """SELECT m.id, m.profile_id, m.job_id, m.match_score, m.trust_score,
                  m.recommendation, m.reason, m.analyzed_at,
                  j.title, j.location, j.is_remote, j.apply_url, j.posted_at,
                  c.name AS company_name
           FROM public.job_matches m
           JOIN public.jobs j ON j.id = m.job_id
           LEFT JOIN public.companies c ON c.id = j.company_id
           WHERE m.profile_id = %s
           ORDER BY m.match_score DESC NULLS LAST,
                    m.trust_score DESC NULLS LAST,
                    j.posted_at DESC NULLS LAST
           LIMIT %s""",
        (profile_id, safe_limit),
    )


def list_profile_matches(profile_id: str, limit: int = 20, offset: int = 0) -> list:
    """Paged analyzed matches with full intelligence fields (Phase 5.4)."""
    safe_limit = max(1, min(int(limit), 100))
    safe_offset = max(0, int(offset))
    return db.fetch_all(
        """SELECT m.id, m.profile_id, m.job_id, m.match_score, m.trust_score,
                  m.recommendation, m.matched_skills, m.missing_skills,
                  m.strengths, m.reason, m.analyzed_at,
                  j.title, j.location, j.is_remote, j.apply_url,
                  c.name AS company_name
           FROM public.job_matches m
           JOIN public.jobs j ON j.id = m.job_id
           LEFT JOIN public.companies c ON c.id = j.company_id
           WHERE m.profile_id = %s
           ORDER BY m.match_score DESC NULLS LAST,
                    m.trust_score DESC NULLS LAST,
                    j.posted_at DESC NULLS LAST
           LIMIT %s OFFSET %s""",
        (profile_id, safe_limit, safe_offset),
    )


def count_profile_matches(profile_id: str) -> int:
    """Total analyzed matches for a profile (for paged responses)."""
    row = db.fetch_one(
        "SELECT COUNT(*) AS total FROM public.job_matches WHERE profile_id = %s",
        (profile_id,),
    )
    return int((row or {}).get("total") or 0)

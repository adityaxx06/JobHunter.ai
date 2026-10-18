"""Ranking reads: analyzed matches + job/company context (Phase 5.3, read-only).

One joined query per profile — no per-row N+1, no LIMIT that could bias the
ranking (top-N selection happens in Python after scoring everything).
Parameterized SQL only. No Gemini, no network.
"""

from worker.db import client as db

_RANKING_COLS = (
    "m.job_id, m.profile_id, m.match_score, m.trust_score, m.recommendation, "
    "m.matched_skills, m.missing_skills, m.strengths, m.reason, "
    "j.title, j.location, j.is_remote, j.employment_type, j.experience_level, "
    "j.description, j.skills, j.apply_url, j.posted_at, "
    "j.salary_min, j.salary_max, j.salary_currency, "
    "j.normalized_title, c.name AS company_name"
)


def load_ranking_inputs(profile_id: str) -> list:
    """All analyzed (profile, job) rows with display context for ranking."""
    rows = db.fetch_all(
        f"""SELECT {_RANKING_COLS}
            FROM public.job_matches m
            JOIN public.jobs j ON j.id = m.job_id
            LEFT JOIN public.companies c ON c.id = j.company_id
            WHERE m.profile_id = %s""",
        (profile_id,),
    )
    return [dict(r) for r in (rows or [])]

"""Worker-side job_matches persistence (Phase 5.2). Existing table, no migration.

Columns used: profile_id, job_id, match_score, trust_score, recommendation,
matched_skills, missing_skills, strengths, risk_signals (= concerns), reason,
analyzed_by ("gemini:<model>" provenance), analyzed_at. A row counts as
"already analyzed" only when match_score, trust_score, and recommendation are
all present — partial rows are refreshed, never treated as cache hits.

Documented limitation: the schema has no dedicated eligibility column, so
eligibility is evaluated, validated, and returned in JobIntelligence (and
surfaced in logs) but persisted only implicitly via recommendation + reason.
No schema change was made for it.
"""

import json
import logging
from typing import Optional

from worker.db import client as db
from worker.models.intelligence import JobIntelligence

logger = logging.getLogger("ai-jobhunter.matches")

_MATCH_COLS = (
    "id, profile_id, job_id, match_score, trust_score, recommendation, "
    "matched_skills, missing_skills, strengths, risk_signals, reason, "
    "analyzed_by, analyzed_at, created_at, updated_at"
)


def get_match(profile_id: str, job_id: str) -> Optional[dict]:
    """Fetch the stored evaluation for a (profile, job) pair (None when absent)."""
    return db.fetch_one(
        f"SELECT {_MATCH_COLS} FROM public.job_matches WHERE profile_id = %s AND job_id = %s",
        (profile_id, job_id),
    )


def is_analyzed(profile_id: str, job_id: str) -> bool:
    """True only when a complete intelligence result is already stored."""
    row = get_match(profile_id, job_id)
    return bool(
        row is not None
        and row.get("match_score") is not None
        and row.get("trust_score") is not None
        and row.get("recommendation")
    )


def save_match(profile_id: str, job_id: str, intelligence: JobIntelligence,
               analyzed_by: str = "gemini") -> tuple:
    """Insert or refresh the evaluation. Returns (row, created_bool)."""
    with db.transaction() as tx:
        tx.execute(
            f"""SELECT id FROM public.job_matches WHERE profile_id = %s AND job_id = %s""",
            (profile_id, job_id),
        )
        existing = tx.fetchone()
        params = (
            intelligence.match_score, intelligence.trust_score, intelligence.recommendation,
            json.dumps(intelligence.matching_skills), json.dumps(intelligence.missing_skills),
            json.dumps(intelligence.strengths), json.dumps(intelligence.concerns),
            intelligence.reason, analyzed_by,
        )
        if existing is None:
            tx.execute(
                f"""INSERT INTO public.job_matches
                    (profile_id, job_id, match_score, trust_score, recommendation,
                     matched_skills, missing_skills, strengths, risk_signals,
                     reason, analyzed_by, analyzed_at)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
                            %s, %s, NOW())
                    RETURNING {_MATCH_COLS}""",
                (profile_id, job_id) + params,
            )
            return dict(tx.fetchone()), True
        tx.execute(
            f"""UPDATE public.job_matches SET
                    match_score = %s, trust_score = %s, recommendation = %s,
                    matched_skills = %s::jsonb, missing_skills = %s::jsonb,
                    strengths = %s::jsonb, risk_signals = %s::jsonb,
                    reason = %s, analyzed_by = %s, analyzed_at = NOW()
                WHERE profile_id = %s AND job_id = %s
                RETURNING {_MATCH_COLS}""",
            params + (profile_id, job_id),
        )
        return dict(tx.fetchone()), False

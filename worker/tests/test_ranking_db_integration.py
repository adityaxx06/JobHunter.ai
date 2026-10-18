"""OPTIONAL live ranking integration test — never runs by default.

Enable explicitly with BOTH conditions (then it uses the real DATABASE_URL):

    RUN_DB_INTEGRATION_TESTS=true python -m pytest worker/tests/test_ranking_db_integration.py -v

Inserts an isolated profile + company + two analyzed jobs (unique per run),
asserts the deterministic order through the real repository layer, then
deletes everything it created. Never prints the connection string.
"""

import os
import uuid

import pytest

from worker.db import client as db
from worker.pipelines.ranking_pipeline import rank_jobs_for_profile

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION_TESTS", "").strip().lower() != "true" or not os.getenv("DATABASE_URL", "").strip(),
    reason="live DB integration only (RUN_DB_INTEGRATION_TESTS=true + DATABASE_URL required)",
)

MARKER = f"phase53-it-{uuid.uuid4().hex[:8]}"


def _setup(tx):
    tx.execute(
        """INSERT INTO public.profiles (full_name, education, experience_level)
           VALUES (%s, %s, %s) RETURNING id""",
        (f"TEST Rank Profile {MARKER} (safe to delete)", "MCA", "Fresher"),
    )
    profile_id = tx.fetchone()["id"]
    for role in ("Java Developer", "Backend Developer"):
        tx.execute(
            "INSERT INTO public.target_roles (profile_id, role_name) VALUES (%s, %s)",
            (profile_id, role),
        )
    for loc, remote in (("Chennai", False), ("India", False), ("Remote", True)):
        tx.execute(
            "INSERT INTO public.target_locations (profile_id, location_name, is_remote) VALUES (%s, %s, %s)",
            (profile_id, loc, remote),
        )
    tx.execute(
        """INSERT INTO public.companies (name, normalized_name)
           VALUES (%s, %s) RETURNING id""",
        (f"TEST Rank Co {MARKER}", f"test rank co {MARKER}"),
    )
    company_id = tx.fetchone()["id"]
    job_ids = []
    for title, match, trust, rec in (("Java Developer Intern", 96, 98, "APPLY"),
                                     ("Backend Developer Intern", 80, 85, "CONSIDER")):
        tx.execute(
            """INSERT INTO public.jobs (company_id, title, normalized_title, location, status)
               VALUES (%s, %s, %s, %s, 'active') RETURNING id""",
            (company_id, f"{title} {MARKER}", title.lower(), "Chennai, India"),
        )
        job_id = tx.fetchone()["id"]
        job_ids.append(job_id)
        tx.execute(
            """INSERT INTO public.job_matches
               (profile_id, job_id, match_score, trust_score, recommendation,
                reason, analyzed_by, analyzed_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())""",
            (profile_id, job_id, match, trust, rec, "Integration fixture.", "test"),
        )
    return profile_id, company_id, job_ids


def _cleanup(profile_id, company_id, job_ids):
    with db.transaction() as tx:
        tx.execute("DELETE FROM public.job_matches WHERE profile_id = %s", (profile_id,))
        for job_id in job_ids:
            tx.execute("DELETE FROM public.jobs WHERE id = %s", (job_id,))
        tx.execute("DELETE FROM public.companies WHERE id = %s", (company_id,))
        tx.execute("DELETE FROM public.target_roles WHERE profile_id = %s", (profile_id,))
        tx.execute("DELETE FROM public.target_locations WHERE profile_id = %s", (profile_id,))
        tx.execute("DELETE FROM public.profiles WHERE id = %s", (profile_id,))


def test_live_ranking_order():
    with db.transaction() as tx:
        profile_id, company_id, job_ids = _setup(tx)
    try:
        result = rank_jobs_for_profile(profile_id, limit=20)
        assert result.jobs_received == 2 and result.jobs_ranked == 2
        assert [j.job_id for j in result.ranked_jobs] == job_ids  # 96/98 APPLY first
        assert result.ranked_jobs[0].ranking_score > result.ranked_jobs[1].ranking_score
    finally:
        _cleanup(profile_id, company_id, job_ids)
    with db.transaction() as tx:
        tx.execute("SELECT id FROM public.profiles WHERE id = %s", (profile_id,))
        assert tx.fetchone() is None  # cleanup verified

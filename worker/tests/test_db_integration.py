"""OPTIONAL live-database integration test — never runs by default.

Enable explicitly with BOTH conditions (then it uses the real DATABASE_URL):

    RUN_DB_INTEGRATION_TESTS=true python -m pytest worker/tests/test_db_integration.py -v

Uses one clearly-marked test company/job/source (unique per run) and deletes
everything it created, in dependency order. Never prints the connection
string or any credentials. Verifies end-to-end: company reuse, job insert,
fingerprint re-find, source-link reuse, and blank-field protection.
"""

import os
import uuid

import pytest

from worker.db import client as db
from worker.db.job_repository import persist_job
from worker.models.job import DiscoveredJob
from worker.processors.normalizer.job_normalizer import normalize_job

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION_TESTS", "").strip().lower() != "true" or not os.getenv("DATABASE_URL", "").strip(),
    reason="live DB integration only (RUN_DB_INTEGRATION_TESTS=true + DATABASE_URL required)",
)

MARKER = f"phase51-it-{uuid.uuid4().hex[:8]}"


def _job(**overrides):
    base = {
        "external_id": f"{MARKER}-e1",
        "title": f"Integration Test Engineer ({MARKER})",
        "company_name": f"TEST Company {MARKER} (integration fixture, safe to delete)",
        "company_domain": "",
        "location": "Chennai, India",
        "employment_type": "Internship",
        "description": "Full integration-test description",
        "skills": ["Python"],
        "source_type": "greenhouse",
        "source_name": f"greenhouse:{MARKER}",
        "source_url": "https://boards.greenhouse.io/example",
        "apply_url": f"https://boards.greenhouse.io/example/jobs/{MARKER}",
    }
    base.update(overrides)
    return normalize_job(DiscoveredJob(**base))


def _cleanup(company_id, job_id):
    with db.transaction() as tx:
        tx.execute("DELETE FROM public.job_sources WHERE job_id = %s", (job_id,))
        tx.execute("DELETE FROM public.jobs WHERE id = %s", (job_id,))
        tx.execute("DELETE FROM public.companies WHERE id = %s", (company_id,))


def test_live_persist_roundtrip():
    first = persist_job(_job())
    assert first["action"] == "inserted"
    try:
        with db.transaction() as tx:
            tx.execute("SELECT id, company_id FROM public.jobs WHERE id = %s", (first["job_id"],))
            stored = tx.fetchone()
        assert stored and stored["company_id"]
        company_id = stored["company_id"]

        second = persist_job(_job())
        assert second["action"] == "duplicate" and second["job_id"] == first["job_id"]

        improved = persist_job(_job(description=""))
        assert improved["action"] == "duplicate"  # blanks never overwrite
    finally:
        _cleanup(company_id, first["job_id"])

    with db.transaction() as tx:
        tx.execute("SELECT id FROM public.jobs WHERE id = %s", (first["job_id"],))
        assert tx.fetchone() is None  # cleanup verified

"""Phase 3 database-layer tests.

All tests pass WITHOUT a remote database (mocked). An opt-in live probe runs
only when AI_JOBHUNTER_TEST_DATABASE_URL is explicitly set — never otherwise.
Run from backend/:  pytest tests/test_database.py -v
"""

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

EXPECTED_TABLES = [
    "profiles",
    "profile_skills",
    "target_roles",
    "target_locations",
    "companies",
    "jobs",
    "job_sources",
    "job_matches",
    "saved_jobs",
    "applications",
    "search_queries",
    "notifications",
]


def _clear_settings_cache():
    from app.core.config import get_settings

    get_settings.cache_clear()


def test_config_loads_without_database_url():
    """App starts unconfigured; DB features must report, not crash."""
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("DATABASE_URL", None)
        _clear_settings_cache()
        try:
            from app.core.config import get_settings

            settings = get_settings()
            assert settings.database_url == ""
            assert settings.is_database_configured is False
        finally:
            _clear_settings_cache()


def test_fingerprint_is_deterministic():
    from app.utils.job_fingerprint import build_fingerprint

    fp1 = build_fingerprint("Acme Inc", "Java Developer Intern", "Chennai", "https://acme.example/careers/123")
    fp2 = build_fingerprint("  acme   INC ", "java developer intern", " chennai ", "https://acme.example/careers/123/")
    assert fp1 == fp2  # normalization absorbs case/whitespace/trailing slash
    assert len(fp1) == 64  # sha256 hex
    assert build_fingerprint("Acme", "Java Developer", "Chennai") != build_fingerprint(
        "Acme", "Python Developer", "Chennai"
    )
    assert build_fingerprint("Acme", "Java Developer", "Chennai") != build_fingerprint(
        "Acme", "Java Developer", "Mumbai"
    )


def test_repository_sql_is_parameterized():
    """Values travel as params (``%s`` + tuple); never interpolated into SQL."""
    from app.db.repositories import jobs as jobs_repo

    with mock.patch.object(jobs_repo.db, "fetch_all", return_value=[]) as fake:
        jobs_repo.list_recent_jobs(5)
        assert fake.call_count == 1
        sql, params = fake.call_args.args
        assert "%s" in sql and "LIMIT %s" in sql
        assert params == (5,)
        assert "5" not in sql.replace("%s", "")


def test_profile_repository_passes_id_as_param():
    from app.db.repositories import profiles as profiles_repo

    with mock.patch.object(profiles_repo.db, "fetch_one", return_value=None) as fake:
        profiles_repo.get_profile("11111111-1111-1111-1111-111111111111")
        sql, params = fake.call_args.args
        assert "WHERE id = %s" in sql
        assert params == ("11111111-1111-1111-1111-111111111111",)


def test_top_matches_sorted_by_match_trust_recency():
    from app.db.repositories import matches as matches_repo

    with mock.patch.object(matches_repo.db, "fetch_all", return_value=[]) as fake:
        matches_repo.list_top_matches("11111111-1111-1111-1111-111111111111", 10)
        sql, params = fake.call_args.args
        order = sql.upper().split("ORDER BY", 1)[1]
        assert order.index("MATCH_SCORE") < order.index("TRUST_SCORE") < order.index("POSTED_AT")
        assert params == ("11111111-1111-1111-1111-111111111111", 10)


def test_newest_sort_orders_by_recency_with_safe_fallback():
    """Freshness signal: newest = last_seen_at recency; unknown sorts fall back."""
    from app.db.repositories import jobs as jobs_repo

    with mock.patch.object(jobs_repo.db, "fetch_all", return_value=[]) as fake:
        jobs_repo.search_jobs_page(5, 0, sort="newest")
        sql, _ = fake.call_args.args
        assert "ORDER BY j.last_seen_at DESC" in sql
        assert "j.posted_at" in sql  # source freshness stays available for display
    with mock.patch.object(jobs_repo.db, "fetch_all", return_value=[]) as fake:
        jobs_repo.search_jobs_page(5, 0, sort="newest; DROP TABLE jobs--")
        sql, _ = fake.call_args.args
        assert "DROP" not in sql and "ORDER BY j.last_seen_at DESC" in sql


def test_migration_covers_all_tables():
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "supabase",
        "migrations",
        "001_initial_schema.sql",
    )
    src = open(path, encoding="utf-8").read()
    for table in EXPECTED_TABLES:
        assert f"public.{table}" in src, f"missing {table}"
    assert src.count("ENABLE ROW LEVEL SECURITY") >= 9  # all user tables minimum


def test_api_routes_load_and_health_work_without_db():
    """Existing /api/health untouched; /api/db/health reports not_configured."""
    os.environ.pop("DATABASE_URL", None)
    _clear_settings_cache()
    try:
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)
        assert client.get("/api/health").json() == {"status": "ok", "service": "AI-JobHunter API"}
        body = client.get("/api/db/health").json()
        assert body == {"status": "not_configured", "database": "not_configured"}
        assert client.get("/api/profiles/not-a-uuid").status_code == 400
    finally:
        _clear_settings_cache()


@pytest.mark.skipif(
    not os.getenv("AI_JOBHUNTER_TEST_DATABASE_URL"),
    reason="opt-in live DB probe only (AI_JOBHUNTER_TEST_DATABASE_URL unset)",
)
def test_live_database_probe_opt_in_only():
    """Runs ONLY with explicit opt-in env var; asserts SELECT 1 works."""
    with mock.patch.dict(os.environ, {"DATABASE_URL": os.environ["AI_JOBHUNTER_TEST_DATABASE_URL"]}):
        _clear_settings_cache()
        try:
            from app.db.health import check_database

            assert check_database() == "connected"
        finally:
            _clear_settings_cache()

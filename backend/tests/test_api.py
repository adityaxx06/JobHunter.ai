"""Phase 5.4 dashboard-API tests. Fully offline (mocked DB layer).

Run from backend/:  pytest tests/test_api.py -v
Covers jobs, matches, rankings, applications, pagination, validation,
error mapping, and the zero-Gemini architectural guarantee.
"""

import os
import sys
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PID = "11111111-1111-1111-1111-111111111111"
JOB1 = "22222222-2222-2222-2222-222222222222"
JOB2 = "33333333-3333-3333-3333-333333333333"


def _now():
    return datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)


def _job_row(job_id=JOB1, **overrides):
    row = {
        "id": job_id, "company_id": "c1", "title": "Java Developer Intern",
        "normalized_title": "java developer intern",
        "description": "Java internship.", "location": "Chennai, India",
        "is_remote": False, "employment_type": "Internship",
        "experience_level": "Fresher", "salary_min": 5000, "salary_max": 10000,
        "salary_currency": "INR", "salary_period": "month", "skills": ["Java", "SQL"],
        "posted_at": None, "first_seen_at": _now(), "last_seen_at": _now(),
        "canonical_url": "https://example.com/j/1", "apply_url": "https://example.com/apply/1",
        "status": "active", "created_at": _now(), "updated_at": _now(),
        "company_name": "Example Technologies", "company_normalized_name": "example",
    }
    row.update(overrides)
    return row


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


# --- jobs ----------------------------------------------------------------------


def test_list_jobs_shape_and_pagination():
    from app.db.repositories import jobs as repo

    rows = [_job_row(), _job_row(JOB2, title="Backend Developer Intern")]
    with mock.patch.object(repo.db, "fetch_all", return_value=rows) as listed, mock.patch.object(
        repo.db, "fetch_one", return_value={"total": 2}
    ), mock.patch.object(repo, "list_job_sources", return_value=[{"source_type": "greenhouse"}]):
        body = _client().get("/api/jobs?limit=20&offset=0").json()
    assert body["limit"] == 20 and body["offset"] == 0 and body["count"] == 2
    item = body["items"][0]
    assert (item["title"], item["company"], item["source"]) == (
        "Java Developer Intern", "Example Technologies", "greenhouse")
    assert "password" not in str(body).lower() and "api_key" not in str(body).lower()
    sql, params = listed.call_args_list[0].args  # the filtered search select
    assert "LIMIT %s OFFSET %s" in sql and params == (20, 0)


def test_list_jobs_rejects_bad_pagination():
    client = _client()
    assert client.get("/api/jobs?limit=0").status_code == 422
    assert client.get("/api/jobs?limit=101").status_code == 422
    assert client.get("/api/jobs?offset=-1").status_code == 422
    assert client.get("/api/jobs?limit=abc").status_code == 422


def test_get_job_detail_with_and_without_intelligence():
    from app.db.repositories import jobs as repo
    from app.db.repositories import matches as matches_repo

    match = {"match_score": 96, "trust_score": 98, "recommendation": "APPLY",
             "strengths": ["Java"], "missing_skills": ["Spring Boot"], "reason": "Strong match."}
    with mock.patch.object(repo, "get_job", return_value=_job_row()), mock.patch.object(
        repo, "list_job_sources", return_value=[{"source_type": "greenhouse"}]
    ), mock.patch.object(matches_repo, "get_match", return_value=match):
        plain = _client().get(f"/api/jobs/{JOB1}").json()
        assert plain["intelligence"] is None
        assert plain["skills"] == ["Java", "SQL"] and plain["currency"] == "INR"
        full = _client().get(f"/api/jobs/{JOB1}?profile_id={PID}").json()
        assert full["intelligence"]["match_score"] == 96
        assert full["intelligence"]["missing_skills"] == ["Spring Boot"]


def test_get_job_detail_maps_remote_posted_and_source():
    """Detail exposes is_remote/posted_at/source; missing optionals stay null."""
    from app.db.repositories import jobs as repo

    row = _job_row(posted_at=_now(), description=None, skills=None,
                   salary_min=None, salary_max=None)
    with mock.patch.object(repo, "get_job", return_value=row), mock.patch.object(
        repo, "list_job_sources", return_value=[{"source_type": "lever"}]
    ):
        body = _client().get(f"/api/jobs/{JOB1}").json()
    assert body["is_remote"] is False
    assert body["posted_at"] == "2026-09-01T12:00:00Z"
    assert body["employment_type"] == "Internship"
    assert body["source"] == "lever"
    assert body["description"] is None and body["skills"] == []
    assert body["salary_min"] is None and body["intelligence"] is None


def test_get_job_unknown_and_invalid():
    from app.db.repositories import jobs as repo

    with mock.patch.object(repo, "get_job", return_value=None):
        assert _client().get(f"/api/jobs/{JOB1}").status_code == 404
    assert _client().get("/api/jobs/not-a-uuid").status_code == 422


def test_jobs_db_unavailable_is_503_without_leak():
    from app.db.repositories import jobs as repo

    with mock.patch.object(repo, "search_jobs_page",
                           side_effect=RuntimeError("FATAL: password authentication failed for user")):
        response = _client().get("/api/jobs")
    assert response.status_code == 503
    assert "password" not in response.text.lower() and "FATAL" not in response.text


# --- matches ---------------------------------------------------------------------


def test_profile_matches_shape_pagination_and_empty():
    from app.db.repositories import matches as repo

    row = {"job_id": JOB1, "title": "Java Developer Intern", "company_name": "Example",
           "location": "Chennai", "match_score": 96, "trust_score": 98,
           "recommendation": "APPLY", "strengths": ["Java"],
           "missing_skills": ["Spring Boot"], "reason": "Strong match.",
           "apply_url": "https://example.com/apply/1"}
    with mock.patch.object(repo.db, "fetch_all", return_value=[row]) as listed, mock.patch.object(
        repo.db, "fetch_one", return_value={"total": 1}
    ):
        body = _client().get(f"/api/matches/{PID}?limit=10&offset=5").json()
    assert body["profile_id"] == PID and body["count"] == 1
    assert body["items"][0]["missing_skills"] == ["Spring Boot"]
    assert listed.call_args.args[1] == (PID, 10, 5)
    with mock.patch.object(repo.db, "fetch_all", return_value=[]), mock.patch.object(
        repo.db, "fetch_one", return_value={"total": 0}
    ):
        empty = _client().get(f"/api/matches/{PID}").json()
    assert empty == {"profile_id": PID, "items": [], "limit": 20, "offset": 0, "count": 0}


def test_matches_invalid_profile_and_unavailable():
    from app.db.repositories import matches as repo

    assert _client().get("/api/matches/not-a-uuid").status_code == 422
    with mock.patch.object(repo, "list_profile_matches", side_effect=RuntimeError("conn refused")):
        assert _client().get(f"/api/matches/{PID}").status_code == 503


# --- rankings ----------------------------------------------------------------------


def _ranked_result():
    from worker.models.ranking import RankedJob, RankingPipelineResult

    return RankingPipelineResult(
        jobs_received=2, jobs_ranked=2, jobs_excluded=0, ranking_errors=[],
        ranked_jobs=[
            RankedJob(job_id=JOB1, profile_id=PID, rank=1, ranking_score=91.7,
                      match_score=96, trust_score=98, recommendation="APPLY",
                      title="Java Developer Intern", company_name="Example",
                      location="Chennai", apply_url="https://example.com/apply/1",
                      strengths=["Java"], missing_skills=["Spring Boot"], reason="Strong match."),
            RankedJob(job_id=JOB2, profile_id=PID, rank=2, ranking_score=82.4,
                      match_score=88, trust_score=90, recommendation="CONSIDER",
                      title="Backend Developer Intern"),
        ],
    )


def test_rankings_response_order_and_fields():
    from app.services import ranking_service as service

    with mock.patch.object(service, "rank_jobs_for_profile", return_value=_ranked_result()) as ranked:
        body = _client().get(f"/api/rankings/{PID}?limit=20").json()
    assert body["profile_id"] == PID and body["count"] == 2 and body["limit"] == 20
    first, second = body["items"]
    assert (first["rank"], first["ranking_score"], first["recommendation"]) == (1, 91.7, "APPLY")
    assert first["missing_skills"] == ["Spring Boot"] and first["strengths"] == ["Java"]
    assert second["rank"] == 2
    assert ranked.call_args.kwargs["filters"].min_match_score is None


def test_rankings_response_includes_priority_reasons():
    from app.services import ranking_service as service

    result = _ranked_result()
    result.ranked_jobs[0].priority_reasons = ["exact target role: Java Developer", "remote-friendly"]
    with mock.patch.object(service, "rank_jobs_for_profile", return_value=result):
        body = _client().get(f"/api/rankings/{PID}?limit=20").json()
    first, second = body["items"]
    assert first["reasons"] == ["exact target role: Java Developer", "remote-friendly"]
    assert second["reasons"] == []


def test_list_jobs_includes_posted_at_and_null():
    from app.db.repositories import jobs as repo

    posted = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)
    rows = [_job_row(posted_at=posted), _job_row(JOB2, title="Backend Developer Intern", posted_at=None)]
    with mock.patch.object(repo.db, "fetch_all", return_value=rows), mock.patch.object(
        repo.db, "fetch_one", return_value={"total": 2}
    ), mock.patch.object(repo, "list_job_sources", return_value=[]):
        body = _client().get("/api/jobs?limit=20&offset=0").json()
    assert body["items"][0]["posted_at"] == "2026-09-20T10:00:00Z"
    assert body["items"][1]["posted_at"] is None


def test_rankings_filters_and_limit_reach_service():
    from app.services import ranking_service as service

    with mock.patch.object(service, "rank_jobs_for_profile", return_value=_ranked_result()) as ranked:
        response = _client().get(
            f"/api/rankings/{PID}?limit=5&min_match_score=80&min_trust_score=70"
            "&recommendation=APPLY&employment_type=Internship&location=Chennai&remote=false"
        )
    assert response.status_code == 200
    filt = ranked.call_args.kwargs["filters"]
    assert (filt.min_match_score, filt.min_trust_score, filt.recommendation) == (80, 70, "APPLY")
    assert (filt.employment_type, filt.location, filt.remote) == ("Internship", "Chennai", False)


def test_rankings_rejects_bad_params():
    client = _client()
    assert client.get(f"/api/rankings/{PID}?min_match_score=101").status_code == 422
    assert client.get(f"/api/rankings/{PID}?recommendation=MAYBE").status_code == 422
    assert client.get("/api/rankings/not-a-uuid").status_code == 422


def test_rankings_eligible_only_reaches_service():
    from app.services import ranking_service as service

    with mock.patch.object(service, "rank_jobs_for_profile", return_value=_ranked_result()) as ranked:
        response = _client().get(f"/api/rankings/{PID}?eligible_only=true")
    assert response.status_code == 200
    assert ranked.call_args.kwargs["eligible_only"] is True
    with mock.patch.object(service, "rank_jobs_for_profile", return_value=_ranked_result()) as ranked:
        _client().get(f"/api/rankings/{PID}")
    assert ranked.call_args.kwargs["eligible_only"] is False


def test_rankings_empty_db_missing_and_unknown_profile():
    from app.services import ranking_service as service
    from worker.models.ranking import RankingPipelineResult

    with mock.patch.object(service, "rank_jobs_for_profile",
                           return_value=RankingPipelineResult()):
        assert _client().get(f"/api/rankings/{PID}").json()["items"] == []
    with mock.patch.object(service, "rank_jobs_for_profile",
                           return_value=RankingPipelineResult(
                               ranking_errors=["database not configured — ranking skipped"])):
        assert _client().get(f"/api/rankings/{PID}").status_code == 503
    with mock.patch.object(service, "rank_jobs_for_profile",
                           return_value=RankingPipelineResult(
                               ranking_errors=["no candidate profile found — ranking skipped"])):
        assert _client().get(f"/api/rankings/{PID}").status_code == 404


def test_ranking_path_makes_zero_gemini_calls():
    """Architectural guarantee: the served pipeline never touches AI providers."""
    import sys

    for module in ("ai.providers.gemini", "ai.providers"):
        assert module not in sys.modules, f"{module} must not load during API tests"
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    for relative in ("app/services/ranking_service.py", "app/api/routes/rankings.py"):
        text = (root / relative).read_text()
        for token in ("GeminiProvider", "AIRequest", "generate(", "urlopen", "urllib"):
            assert token not in text, f"{relative} must not call AI ({token})"
    from app.services import ranking_service as service

    with mock.patch.object(service, "rank_jobs_for_profile", return_value=_ranked_result()):
        assert _client().get(f"/api/rankings/{PID}").status_code == 200
    for module in ("ai.providers.gemini", "ai.providers"):
        assert module not in sys.modules


# --- applications ---------------------------------------------------------------------


def test_application_list_status_filter_and_pagination():
    from app.db.repositories import applications as repo

    row = {"id": JOB1, "profile_id": PID, "job_id": JOB1, "title": "Java Developer Intern",
           "company_name": "Example", "status": "applied", "applied_at": _now(),
           "notes": "Applied.", "apply_url": "https://example.com/apply/1"}
    with mock.patch.object(repo.db, "fetch_all", return_value=[row]) as listed, mock.patch.object(
        repo.db, "fetch_one", return_value={"total": 1}
    ):
        body = _client().get(f"/api/applications/{PID}?status=applied&limit=10&offset=2").json()
    assert body["items"][0]["status"] == "applied" and body["count"] == 1
    assert listed.call_args.args[1] == (PID, "applied", 10, 2)


def test_applications_invalid_and_empty():
    from app.db.repositories import applications as repo

    client = _client()
    assert client.get(f"/api/applications/{PID}?status=Hired").status_code == 422
    assert client.get("/api/applications/not-a-uuid").status_code == 422
    with mock.patch.object(repo.db, "fetch_all", return_value=[]), mock.patch.object(
        repo.db, "fetch_one", return_value={"total": 0}
    ):
        assert client.get(f"/api/applications/{PID}").json()["items"] == []


# --- security ----------------------------------------------------------------------------


def test_injection_like_input_stays_parameterized():
    from app.db.repositories import matches as repo

    nasty = "x' OR '1'='1'; DROP TABLE job_matches;--"
    with mock.patch.object(repo.db, "fetch_all", return_value=[]) as listed:
        repo.list_profile_matches(PID, 20, 0)
        assert listed.call_args.args[1][0] == PID
    sql = listed.call_args.args[0]
    assert "DROP" not in sql and "%s" in sql  # values ride params, never text


def test_openapi_exposes_new_endpoints():
    paths = _client().get("/openapi.json").json()["paths"]
    for route in ("/api/jobs", "/api/jobs/{job_id}", "/api/matches/{profile_id}",
                  "/api/rankings/{profile_id}", "/api/applications/{profile_id}"):
        assert route in paths, route


# --- config bridge regression (rankings 503 with healthy /api/db/health) ---------


def test_service_bridges_backend_db_config_to_worker():
    """FastAPI-configured DATABASE_URL (e.g. from .env file) must reach the
    worker pipeline even when the process env var was never exported."""
    from app.services import ranking_service as service
    from worker.models.ranking import RankingPipelineResult

    with mock.patch.dict(os.environ, {}, clear=True):
        assert "DATABASE_URL" not in os.environ
        fake_settings = mock.Mock(is_database_configured=True,
                                  database_url="postgresql://u:p@host/db")
        seen = {}

        def fake_pipeline(profile_id=None, limit=20, min_match_score=None,
                          min_trust_score=None, filters=None, eligible_only=False):
            seen["env"] = os.environ.get("DATABASE_URL")
            return RankingPipelineResult()

        with mock.patch.object(service, "get_settings", return_value=fake_settings), mock.patch.object(
            service.pipeline, "rank_jobs_for_profile", side_effect=fake_pipeline
        ):
            service.rank_jobs_for_profile(PID, limit=5)
    assert seen["env"] == "postgresql://u:p@host/db"


def test_service_never_overrides_explicit_env_or_logs_value():
    from app.services import ranking_service as service
    from worker.models.ranking import RankingPipelineResult

    with mock.patch.dict(os.environ, {"DATABASE_URL": "postgresql://env/kept"}):
        fake_settings = mock.Mock(is_database_configured=True,
                                  database_url="postgresql://u:p@host/db")
        with mock.patch.object(service, "get_settings", return_value=fake_settings), mock.patch.object(
            service.pipeline, "rank_jobs_for_profile",
            return_value=RankingPipelineResult(),
        ) as ranked:
            service.rank_jobs_for_profile(PID)
        assert os.environ["DATABASE_URL"] == "postgresql://env/kept"
        assert ranked.call_count == 1


def test_service_sets_nothing_when_backend_unconfigured():
    from app.services import ranking_service as service
    from worker.models.ranking import RankingPipelineResult

    with mock.patch.dict(os.environ, {}, clear=True):
        fake_settings = mock.Mock(is_database_configured=False, database_url="")
        with mock.patch.object(service, "get_settings", return_value=fake_settings), mock.patch.object(
            service.pipeline, "rank_jobs_for_profile",
            return_value=RankingPipelineResult(),
        ):
            service.rank_jobs_for_profile(PID)
        assert "DATABASE_URL" not in os.environ


def test_worker_pool_factory_returns_pool_not_function():
    """Regression: worker `_pool` global must not shadow the `_pool()` factory
    (the shadowing made every worker DB call fail with AttributeError while
    the backend stayed healthy). No live connection is opened by this test."""
    from worker.db import client as worker_client

    with mock.patch.dict(os.environ, {"DATABASE_URL": "postgresql://u:p@localhost:5432/db"}):
        worker_client._POOL = None
        try:
            pool = worker_client._pool()
            assert type(pool).__name__ == "ConnectionPool"
            assert callable(getattr(pool, "connection", None))
            assert worker_client._POOL is pool  # cached, same object
        finally:
            try:
                pool.close()
            except Exception:
                pass
            worker_client._POOL = None


# --- saved jobs (Phase 5.5B, minimal additive endpoints) --------------------------


def test_saved_ids_list_shape():
    from app.db.repositories import saved as repo

    with mock.patch.object(
        repo.db, "fetch_all",
        return_value=[{"job_id": JOB1}, {"job_id": JOB2}],
    ):
        body = _client().get(f"/api/saved-jobs/{PID}").json()
    assert body == {"profile_id": PID, "job_ids": [JOB1, JOB2]}


def test_save_and_unsave_flow():
    from app.db.repositories import saved as repo

    saved_row = {"id": "s1", "profile_id": PID, "job_id": JOB1}
    with mock.patch.object(repo.db, "execute", return_value=saved_row):
        created = _client().post(f"/api/saved-jobs/{PID}/{JOB1}")
    assert created.status_code == 201
    assert created.json() == {"profile_id": PID, "job_id": JOB1, "saved": True}
    with mock.patch.object(repo.db, "execute", return_value=None):
        # Already-saved re-POST stays saved (ON CONFLICT DO NOTHING).
        again = _client().post(f"/api/saved-jobs/{PID}/{JOB1}")
    assert again.status_code == 201 and again.json()["saved"] is True
    with mock.patch.object(repo.db, "execute", return_value={"id": "s1"}):
        removed = _client().delete(f"/api/saved-jobs/{PID}/{JOB1}")
    assert removed.status_code == 200 and removed.json()["saved"] is False
    with mock.patch.object(repo.db, "execute", return_value=None):
        assert _client().delete(f"/api/saved-jobs/{PID}/{JOB1}").status_code == 404


def test_saved_invalid_ids_and_unavailable():
    from app.db.repositories import saved as repo

    client = _client()
    assert client.get("/api/saved-jobs/not-a-uuid").status_code == 422
    assert client.post(f"/api/saved-jobs/{PID}/not-a-uuid").status_code == 422
    with mock.patch.object(repo, "list_saved_job_ids",
                           side_effect=RuntimeError("FATAL: password failure")):
        response = client.get(f"/api/saved-jobs/{PID}")
    assert response.status_code == 503
    assert "password" not in response.text.lower() and "FATAL" not in response.text
    sql_holder = {}

    def _capture(sql, params=()):
        sql_holder["sql"], sql_holder["params"] = sql, params
        return [{"job_id": JOB1}]

    with mock.patch.object(repo.db, "fetch_all", side_effect=_capture):
        client.get(f"/api/saved-jobs/{PID}")
    assert "%s" in sql_holder["sql"] and sql_holder["params"] == (PID,)


def test_ranking_items_carry_salary_and_remote():
    from app.services import ranking_service as service
    from worker.models.ranking import RankedJob, RankingPipelineResult

    ranked = RankedJob(
        job_id=JOB1, profile_id=PID, rank=1, ranking_score=91.7,
        match_score=96, trust_score=98, recommendation="APPLY",
        title="Java Developer Intern", company_name="Example",
        location="Chennai", is_remote=False, apply_url="https://example.com/apply/1",
        salary_min=15000, salary_max=25000, salary_currency="INR",
        employment_type="Internship",
    )
    result = RankingPipelineResult(
        jobs_received=1, jobs_ranked=1, jobs_excluded=0,
        ranking_errors=[], ranked_jobs=[ranked],
    )
    with mock.patch.object(service, "rank_jobs_for_profile", return_value=result):
        item = _client().get(f"/api/rankings/{PID}").json()["items"][0]
    assert (item["salary_min"], item["salary_max"], item["salary_currency"]) == (15000, 25000, "INR")
    assert item["is_remote"] is False and item["employment_type"] == "Internship"


# --- explorer search / filters / sort (Phase 5.5C, server-side) ----------------------


def _explorer_calls(query):
    """Run GET /api/jobs and return (search-select SQL, params, count SQL)."""
    from app.db.repositories import jobs as repo

    calls = []
    real_fetch_all = repo.db.fetch_all
    real_fetch_one = repo.db.fetch_one

    def _all(sql, params=()):
        calls.append(("all", sql, params))
        return []

    def _one(sql, params=()):
        calls.append(("one", sql, params))
        return {"total": 0}

    with mock.patch.object(repo.db, "fetch_all", side_effect=_all), mock.patch.object(
        repo.db, "fetch_one", side_effect=_one
    ):
        response = _client().get(f"/api/jobs{query}")
    assert response.status_code == 200, response.text
    _, search_sql, search_params = next(c for c in calls if c[0] == "all")
    count_sql = next(c for c in calls if c[0] == "one")[1]
    return search_sql, search_params, count_sql


def test_explorer_search_is_parameterized_like():
    sql, params, _ = _explorer_calls("?search=java")
    assert "j.title ILIKE %s" in sql and "%java%" in params
    assert "java" not in sql.replace("%s", "")


def test_explorer_like_wildcards_escaped():
    sql, params, _ = _explorer_calls("?search=100%_x%5C")
    assert "%100\\%\\_x\\\\%" in params  # literal %, _, \ — no wildcard injection


def test_explorer_location_remote_role_employment():
    sql, params, _ = _explorer_calls("?location=chennai&remote=true")
    assert "j.location ILIKE %s" in sql and "j.is_remote = %s" in sql
    assert "%chennai%" in params and True in params
    sql, params, _ = _explorer_calls("?role=Java+Developer&employment_type=Internship")
    assert "j.title ILIKE %s" in sql and "j.employment_type ILIKE %s" in sql
    assert "%Java Developer%" in params and "%Internship%" in params


def test_explorer_match_trust_recommendation_need_profile():
    sql, params, _ = _explorer_calls(
        f"?profile_id={PID}&min_match=70&min_trust=70&recommendation=APPLY")
    assert "m.match_score >= %s" in sql and "m.trust_score >= %s" in sql
    assert "m.recommendation = %s" in sql
    assert 70 in params and "APPLY" in params and PID in params
    client = _client()
    assert client.get("/api/jobs?min_match=70").status_code == 422
    assert client.get("/api/jobs?sort=match").status_code == 422
    assert client.get("/api/jobs?recommendation=MAYBE").status_code == 422
    assert client.get("/api/jobs?profile_id=not-a-uuid").status_code == 422


def test_explorer_sort_whitelist():
    sql, _, _ = _explorer_calls("?sort=match&profile_id=" + PID)
    assert "m.match_score DESC NULLS LAST" in sql
    sql, _, _ = _explorer_calls("?sort=trust&profile_id=" + PID)
    assert "m.trust_score DESC NULLS LAST" in sql
    sql, _, _ = _explorer_calls("?sort=newest")
    assert "j.last_seen_at DESC" in sql
    assert _client().get("/api/jobs?sort=alphabetical").status_code == 422
    assert _client().get("/api/jobs?min_match=101").status_code == 422
    assert _client().get("/api/jobs?limit=51").status_code == 422


def test_explorer_pagination_and_count():
    sql, params, count_sql = _explorer_calls("?limit=20&offset=20")
    assert params[-2:] == (20, 20)
    assert "COUNT(*)" in count_sql and "LIMIT" not in count_sql


def test_explorer_intelligence_columns_present_with_profile():
    sql, params, _ = _explorer_calls(f"?profile_id={PID}")
    assert "m.match_score" in sql and "m.strengths" in sql and PID in params
    sql, _, _ = _explorer_calls("")
    assert "m.match_score" not in sql  # no join, nulls selected instead


# --- application tracker writes (Phase 5.5E; existing table, no migration) ------


def _app_row(**overrides):
    row = {
        "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "profile_id": PID, "job_id": JOB1,
        "status": "applied", "applied_at": _now(), "notes": None,
        "created_at": _now(), "updated_at": _now(),
    }
    row.update(overrides)
    return row


def test_create_application_and_duplicate_returns_existing():
    from app.db.repositories import applications as repo
    from app.db.repositories import jobs as jobs_repo

    with mock.patch.object(jobs_repo, "get_job", return_value=_job_row()), mock.patch.object(
        repo, "get_application", return_value=None
    ), mock.patch.object(repo, "create_application", return_value=_app_row()) as created:
        response = _client().post(f"/api/applications/{PID}", json={"job_id": JOB1})
    assert response.status_code == 201
    assert response.json()["status"] == "applied"
    assert created.call_args.args[:2] == (PID, JOB1)  # positional, parameterized downstream
    with mock.patch.object(jobs_repo, "get_job", return_value=_job_row()), mock.patch.object(
        repo, "get_application", return_value=_app_row()
    ):
        duplicate = _client().post(f"/api/applications/{PID}", json={"job_id": JOB1})
    assert duplicate.status_code == 200 and duplicate.json()["status"] == "applied"


def test_create_application_rejects_bad_input():
    client = _client()
    assert client.post(f"/api/applications/{PID}", json={"job_id": "nope"}).status_code == 422
    assert client.post(f"/api/applications/{PID}", json={"job_id": JOB1, "status": "Hired"}).status_code == 422
    assert client.post(f"/api/applications/{PID}", json={"job_id": JOB1, "notes": "x" * 5001}).status_code == 422
    from app.db.repositories import applications as repo
    from app.db.repositories import jobs as jobs_repo

    with mock.patch.object(jobs_repo, "get_job", return_value=None):
        assert client.post(f"/api/applications/{PID}", json={"job_id": JOB1}).status_code == 404


def test_patch_application_status_notes_and_errors():
    from app.db.repositories import applications as repo
    from app.db.repositories import jobs as jobs_repo

    patched = _app_row(status="interview", notes="Round 2 next week")
    with mock.patch.object(repo, "update_application", return_value=patched) as updated, mock.patch.object(
        jobs_repo, "get_job", return_value=_job_row()
    ):
        body = _client().patch(
            f"/api/applications/{PID}/{JOB1}",
            json={"status": "interview", "notes": "Round 2 next week"},
        ).json()
    assert body["status"] == "interview" and body["notes"] == "Round 2 next week"
    assert updated.call_args.kwargs["status"] == "interview"
    with mock.patch.object(repo, "update_application", return_value=None):
        assert _client().patch(
            f"/api/applications/{PID}/{JOB1}", json={"status": "offer"}).status_code == 404
    client = _client()
    assert client.patch(f"/api/applications/{PID}/{JOB1}", json={"status": "Hired"}).status_code == 422
    assert client.patch(f"/api/applications/{PID}/{JOB1}", json={}).status_code == 422
    assert client.patch("/api/applications/not-a-uuid/x", json={"status": "offer"}).status_code == 422


def test_get_single_application_and_missing():
    from app.db.repositories import applications as repo
    from app.db.repositories import jobs as jobs_repo

    with mock.patch.object(repo, "get_application", return_value=_app_row()), mock.patch.object(
        jobs_repo, "get_job", return_value=_job_row()
    ):
        body = _client().get(f"/api/applications/{PID}/{JOB1}").json()
    assert body["status"] == "applied" and body["title"] == "Java Developer Intern"
    with mock.patch.object(repo, "get_application", return_value=None):
        assert _client().get(f"/api/applications/{PID}/{JOB1}").status_code == 404


def test_cors_allows_app_methods_from_frontend_origin():
    """Preflight must permit every method the dashboard uses (GET/POST/PATCH/DELETE)."""
    client = _client()
    for method in ("GET", "POST", "PATCH", "DELETE"):
        response = client.options(
            f"/api/applications/{PID}/{JOB1}",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": method,
            },
        )
        assert response.status_code == 200, method
        allowed = response.headers.get("access-control-allow-methods", "")
        assert method in allowed, (method, allowed)
    assert client.options(
        "/api/jobs", headers={"Origin": "https://evil.example"}
    ).headers.get("access-control-allow-origin") is None


# --- profiles (Phase 7A writes; repo layer mocked, no live DB) ------------------


def _profile_row(**overrides):
    row = {
        "id": PID, "user_id": None, "full_name": "Dev Candidate",
        "education": "MCA", "experience_level": "Fresher / Student",
        "preferred_work_mode": "Remote + On-site", "relocation_allowed": True,
        "minimum_stipend": None, "created_at": "2026-10-05T00:00:00Z",
        "updated_at": "2026-10-05T00:00:00Z",
    }
    row.update(overrides)
    return row


def _skill_row(skill_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", **overrides):
    row = {"id": skill_id, "profile_id": PID, "skill_name": "Java",
           "skill_level": "intermediate", "is_learning": False,
           "created_at": "2026-10-05T00:00:00Z"}
    row.update(overrides)
    return row


def _role_row(role_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", **overrides):
    row = {"id": role_id, "profile_id": PID, "role_name": "Java Developer",
           "priority": 1, "created_at": "2026-10-05T00:00:00Z"}
    row.update(overrides)
    return row


def _location_row(location_id="cccccccc-cccc-cccc-cccc-cccccccccccc", **overrides):
    row = {"id": location_id, "profile_id": PID, "location_name": "Chennai",
           "is_remote": False, "priority": 1, "created_at": "2026-10-05T00:00:00Z"}
    row.update(overrides)
    return row


def test_get_profile_shape_and_errors():
    from app.db.repositories import profiles as repo

    with mock.patch.object(repo, "get_profile", return_value=_profile_row()), mock.patch.object(
        repo, "list_profile_skills", return_value=[_skill_row()]), mock.patch.object(
        repo, "list_target_roles", return_value=[_role_row()]), mock.patch.object(
        repo, "list_target_locations", return_value=[_location_row()]):
        body = _client().get(f"/api/profiles/{PID}").json()
    assert body["profile"]["education"] == "MCA"
    assert body["skills"][0]["skill_name"] == "Java"
    assert body["target_roles"][0]["role_name"] == "Java Developer"
    assert body["target_locations"][0]["location_name"] == "Chennai"
    with mock.patch.object(repo, "get_profile", return_value=None):
        assert _client().get(f"/api/profiles/{PID}").status_code == 404
    assert _client().get("/api/profiles/not-a-uuid").status_code == 400
    with mock.patch.object(repo, "get_profile", side_effect=RuntimeError("down")):
        assert _client().get(f"/api/profiles/{PID}").status_code == 503


def test_patch_profile_scalars():
    from app.db.repositories import profiles as repo

    updated = _profile_row(education="BCA")
    with mock.patch.object(repo, "update_profile", return_value=updated) as patched:
        body = _client().patch(f"/api/profiles/{PID}", json={"education": "BCA"}).json()
    assert body["education"] == "BCA"
    assert patched.call_args[0][0] == PID
    assert _client().patch(f"/api/profiles/{PID}", json={}).status_code == 422
    assert _client().patch("/api/profiles/not-a-uuid", json={"education": "x"}).status_code == 422
    with mock.patch.object(repo, "update_profile", return_value=None):
        assert _client().patch(f"/api/profiles/{PID}", json={"education": "x"}).status_code == 404
    with mock.patch.object(repo, "update_profile", side_effect=RuntimeError("down")):
        assert _client().patch(f"/api/profiles/{PID}", json={"education": "x"}).status_code == 503


def test_skill_crud_and_duplicates():
    from app.db.repositories import profiles as repo

    client = _client()
    with mock.patch.object(repo, "get_profile", return_value=_profile_row()), mock.patch.object(
        repo, "list_profile_skills", return_value=[]), mock.patch.object(
        repo, "add_profile_skill", return_value=_skill_row()) as added:
        body = client.post(f"/api/profiles/{PID}/skills", json={"skill_name": " Java "}).json()
    assert body == {"skill": _skill_row(), "duplicate": False}
    assert added.call_args[0][1] == "Java"  # trimmed before insert
    with mock.patch.object(repo, "get_profile", return_value=_profile_row()), mock.patch.object(
        repo, "list_profile_skills", return_value=[_skill_row()]), mock.patch.object(
        repo, "add_profile_skill") as added:
        body = client.post(f"/api/profiles/{PID}/skills", json={"skill_name": "java"}).json()
    assert body["duplicate"] is True and added.call_count == 0
    assert client.post(f"/api/profiles/{PID}/skills", json={"skill_name": "   "}).status_code == 422
    with mock.patch.object(repo, "get_profile", return_value=None):
        assert client.post(f"/api/profiles/{PID}/skills", json={"skill_name": "Go"}).status_code == 404
    with mock.patch.object(repo, "update_profile_skill", return_value=_skill_row(skill_level="advanced")):
        body = client.patch(f"/api/profiles/{PID}/skills/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", json={"skill_level": "advanced"}).json()
    assert body["skill_level"] == "advanced"
    assert client.patch(f"/api/profiles/{PID}/skills/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", json={}).status_code == 422
    with mock.patch.object(repo, "update_profile_skill", return_value=None):
        assert client.patch(f"/api/profiles/{PID}/skills/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", json={"skill_level": "x"}).status_code == 404
    with mock.patch.object(repo, "remove_profile_skill", return_value=True):
        assert client.delete(f"/api/profiles/{PID}/skills/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa").json() == {"deleted": True}
    with mock.patch.object(repo, "remove_profile_skill", return_value=False):
        assert client.delete(f"/api/profiles/{PID}/skills/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa").status_code == 404
    assert client.get("/api/profiles/not-a-uuid/skills/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa").status_code in (404, 405)


def test_role_crud_priority_and_conflicts():
    from app.db.repositories import profiles as repo

    client = _client()
    with mock.patch.object(repo, "get_profile", return_value=_profile_row()), mock.patch.object(
        repo, "list_target_roles", return_value=[]), mock.patch.object(
        repo, "add_target_role", return_value=_role_row()):
        body = client.post(f"/api/profiles/{PID}/roles", json={"role_name": "Go Developer", "priority": 2}).json()
    assert body["duplicate"] is False and body["role"]["role_name"] == "Java Developer"
    with mock.patch.object(repo, "get_profile", return_value=_profile_row()), mock.patch.object(
        repo, "list_target_roles", return_value=[_role_row()]):
        assert client.post(f"/api/profiles/{PID}/roles", json={"role_name": "JAVA developer"}).json()["duplicate"] is True
    with mock.patch.object(repo, "list_target_roles", return_value=[_role_row()]), mock.patch.object(
        repo, "update_target_role", return_value=_role_row(priority=3)):
        body = client.patch(f"/api/profiles/{PID}/roles/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", json={"priority": 3}).json()
    assert body["priority"] == 3
    with mock.patch.object(repo, "list_target_roles",
                           return_value=[_role_row(), _role_row("dddddddd-dddd-dddd-dddd-dddddddddddd", role_name="Go Developer")]):
        assert client.patch(f"/api/profiles/{PID}/roles/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", json={"role_name": "go developer"}).status_code == 409
    assert client.patch(f"/api/profiles/{PID}/roles/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", json={}).status_code == 422
    assert client.patch(f"/api/profiles/{PID}/roles/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", json={"priority": 0}).status_code == 422
    with mock.patch.object(repo, "remove_target_role", return_value=True):
        assert client.delete(f"/api/profiles/{PID}/roles/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb").json() == {"deleted": True}
    with mock.patch.object(repo, "remove_target_role", return_value=False):
        assert client.delete(f"/api/profiles/{PID}/roles/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb").status_code == 404


def test_location_crud_remote_and_conflicts():
    from app.db.repositories import profiles as repo

    client = _client()
    with mock.patch.object(repo, "get_profile", return_value=_profile_row()), mock.patch.object(
        repo, "list_target_locations", return_value=[]), mock.patch.object(
        repo, "add_target_location", return_value=_location_row(location_name="Remote", is_remote=True)):
        body = client.post(f"/api/profiles/{PID}/locations",
                           json={"location_name": "Remote", "is_remote": True}).json()
    assert body["duplicate"] is False and body["location"]["is_remote"] is True
    with mock.patch.object(repo, "get_profile", return_value=_profile_row()), mock.patch.object(
        repo, "list_target_locations", return_value=[_location_row()]):
        assert client.post(f"/api/profiles/{PID}/locations", json={"location_name": "chennai"}).json()["duplicate"] is True
    with mock.patch.object(repo, "list_target_locations", return_value=[_location_row()]), mock.patch.object(
        repo, "update_target_location", return_value=_location_row(is_remote=True)):
        body = client.patch(f"/api/profiles/{PID}/locations/cccccccc-cccc-cccc-cccc-cccccccccccc", json={"is_remote": True}).json()
    assert body["is_remote"] is True
    with mock.patch.object(repo, "list_target_locations",
                           return_value=[_location_row(), _location_row("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee", location_name="Remote", is_remote=True)]):
        assert client.patch(f"/api/profiles/{PID}/locations/cccccccc-cccc-cccc-cccc-cccccccccccc", json={"location_name": "REMOTE"}).status_code == 409
    with mock.patch.object(repo, "remove_target_location", return_value=True):
        assert client.delete(f"/api/profiles/{PID}/locations/cccccccc-cccc-cccc-cccc-cccccccccccc").json() == {"deleted": True}
    with mock.patch.object(repo, "remove_target_location", return_value=False):
        assert client.delete(f"/api/profiles/{PID}/locations/cccccccc-cccc-cccc-cccc-cccccccccccc").status_code == 404
    with mock.patch.object(repo, "get_profile", side_effect=RuntimeError("down")):
        assert client.post(f"/api/profiles/{PID}/locations", json={"location_name": "X"}).status_code == 503

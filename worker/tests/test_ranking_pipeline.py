"""Phase 5.3 ranking tests part 2: pipeline, duplicates, filters, top-N, guards."""

import os
from contextlib import contextmanager

from worker.db import profile_repository as profiles
from worker.db import ranking_repository as ranking_repo
from worker.pipelines import ranking_pipeline as ranking
from worker.models.ranking import RankingFilter


def _match_row(job_id="job-1", match=90, trust=90, rec="CONSIDER", **overrides):
    row = {
        "job_id": job_id, "profile_id": "prof-1", "match_score": match,
        "trust_score": trust, "recommendation": rec,
        "matched_skills": ["Java"], "missing_skills": ["Spring Boot"],
        "reason": "Good fit.",
        "title": "Java Developer Intern", "location": "Chennai, India",
        "is_remote": False, "employment_type": "Internship",
        "apply_url": f"https://example.com/jobs/{job_id}",
        "normalized_title": "java developer intern", "company_name": "Example",
    }
    row.update(overrides)
    return row


class FakeDB:
    """Read-only FakeDB: profile tables + one joined ranking query."""

    def __init__(self, configured=True, profile=True, rows=None) -> None:
        self.configured = configured
        self.has_profile = profile
        self.rows = list(rows or [])

    def is_configured(self):
        return self.configured

    def fetch_one(self, sql, params=()):
        rows = self.fetch_all(sql, params)
        return rows[0] if rows else None

    def fetch_all(self, sql, params=()):
        if "FROM public.profiles" in sql:
            return [{"id": "prof-1", "education": "MCA", "experience_level": "Fresher",
                     "relocation_allowed": True}] if self.has_profile else []
        if "FROM public.profile_skills" in sql:
            return [{"skill_name": s, "is_learning": False} for s in ("Java", "Python", "SQL")]
        if "FROM public.target_roles" in sql:
            return [{"role_name": "Java Developer"}, {"role_name": "Backend Developer"}]
        if "FROM public.target_locations" in sql:
            return [{"location_name": "Chennai", "is_remote": False},
                    {"location_name": "Bangalore", "is_remote": False},
                    {"location_name": "India", "is_remote": False},
                    {"location_name": "Remote", "is_remote": True}]
        if "FROM public.job_matches" in sql:
            return [dict(r) for r in self.rows]
        raise AssertionError(f"FakeDB cannot handle SQL: {sql[:60]}")  # pragma: no cover

    @contextmanager
    def transaction(self):
        raise AssertionError("ranking performs no writes")  # pragma: no cover


def _install(monkeypatch, fake):
    for module in (ranking.db, profiles.db, ranking_repo.db):
        monkeypatch.setattr(module, "is_configured", fake.is_configured)
        monkeypatch.setattr(module, "fetch_one", fake.fetch_one)
        monkeypatch.setattr(module, "fetch_all", fake.fetch_all)


def _clear_ai_env(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("AI_ENABLED", raising=False)


# --- pipeline 25, 32, 35 -------------------------------------------------------------


def test_end_to_end_order_and_zero_ai(monkeypatch):
    _clear_ai_env(monkeypatch)
    fake = FakeDB(rows=[
        _match_row("job-1", 96, 98, "APPLY"),
        _match_row("job-2", 92, 95, "APPLY", title="Backend Developer Intern"),
        _match_row("job-3", 84, 97, "CONSIDER", title="Python Developer Intern"),
    ])
    _install(monkeypatch, fake)
    result = ranking.rank_jobs_for_profile(limit=20)
    assert [j.job_id for j in result.ranked_jobs] == ["job-1", "job-2", "job-3"]
    assert [j.rank for j in result.ranked_jobs] == [1, 2, 3]
    assert result.jobs_received == 3 and result.jobs_ranked == 3
    assert result.ranked_jobs[0].ranking_score > result.ranked_jobs[1].ranking_score


def test_ranking_uses_stored_intelligence_offline(monkeypatch):
    _clear_ai_env(monkeypatch)
    fake = FakeDB(rows=[_match_row()])
    _install(monkeypatch, fake)
    result = ranking.rank_jobs_for_profile()
    job = result.ranked_jobs[0]
    assert (job.match_score, job.trust_score, job.recommendation) == (90, 90, "CONSIDER")
    assert job.priority_reasons and job.title == "Java Developer Intern"


def test_ranking_modules_make_no_ai_or_network_calls():
    import pathlib

    for name in ("scorer.py",):
        text = pathlib.Path(f"worker/processors/ranking/{name}").read_text()
        assert "gemini" not in text.lower() and "urllib" not in text.lower()
    for name in ("ranking_pipeline.py", "ranking_repository.py"):
        text = pathlib.Path(f"worker/{'pipelines' if 'pipeline' in name else 'db'}/{name}").read_text()
        assert "AIRequest" not in text and "urlopen" not in text


# --- duplicates 30-31 -------------------------------------------------------------------


def test_canonical_job_ranks_once(monkeypatch):
    _clear_ai_env(monkeypatch)
    fake = FakeDB(rows=[_match_row("job-1"), dict(_match_row("job-1"), recommendation="APPLY")])
    _install(monkeypatch, fake)
    result = ranking.rank_jobs_for_profile()
    assert result.jobs_received == 2 and result.jobs_ranked == 1
    assert len(result.ranked_jobs) == 1


# --- invalid + empty 36-37 -----------------------------------------------------------------


def test_invalid_intelligence_counted_not_silent(monkeypatch):
    _clear_ai_env(monkeypatch)
    fake = FakeDB(rows=[_match_row("job-1"), _match_row("job-2", match=None),
                         _match_row("job-3", rec="STRONG_APPLY"), {"job_id": None}])
    _install(monkeypatch, fake)
    result = ranking.rank_jobs_for_profile()
    assert result.jobs_received == 4  # duplicate-free count still sees rows
    assert result.jobs_ranked == 1 and result.jobs_excluded == 3
    assert len(result.ranking_errors) == 3


def test_empty_result_clean(monkeypatch):
    _clear_ai_env(monkeypatch)
    fake = FakeDB(rows=[])
    _install(monkeypatch, fake)
    result = ranking.rank_jobs_for_profile()
    assert result.summary() == {"received": 0, "ranked": 0, "excluded": 0, "ineligible": 0, "errors": 0}
    assert result.ranked_jobs == []


# --- top-N 38 + full consideration 40 -------------------------------------------------------------


def test_limit_returns_top_of_full_ranking(monkeypatch):
    _clear_ai_env(monkeypatch)
    rows = [_match_row(f"job-{i}", match=60 + i * 5, trust=80) for i in range(5)]
    fake = FakeDB(rows=rows)
    _install(monkeypatch, fake)
    full = ranking.rank_jobs_for_profile(limit=20)
    top2 = ranking.rank_jobs_for_profile(limit=2)
    assert full.jobs_ranked == 5  # everything scored before the cut
    assert [j.job_id for j in top2.ranked_jobs] == [j.job_id for j in full.ranked_jobs[:2]]
    assert [j.rank for j in top2.ranked_jobs] == [1, 2]


# --- filters 39 -------------------------------------------------------------------------------------------------


def test_filters_narrow_before_ranking(monkeypatch):
    _clear_ai_env(monkeypatch)
    fake = FakeDB(rows=[
        _match_row("job-1", 95, 95, "APPLY"),
        _match_row("job-2", 70, 60, "REVIEW", is_remote=True, location="Remote"),
        _match_row("job-3", 50, 90, "CONSIDER"),
    ])
    _install(monkeypatch, fake)
    assert [j.job_id for j in ranking.rank_jobs_for_profile(min_match_score=80).ranked_jobs] == ["job-1"]
    assert [j.job_id for j in ranking.rank_jobs_for_profile(min_trust_score=90).ranked_jobs] == ["job-1", "job-3"]
    assert [j.job_id for j in ranking.rank_jobs_for_profile(
        filters=RankingFilter(recommendation="REVIEW")).ranked_jobs] == ["job-2"]
    assert [j.job_id for j in ranking.rank_jobs_for_profile(
        filters=RankingFilter(remote=True)).ranked_jobs] == ["job-2"]
    assert [j.job_id for j in ranking.rank_jobs_for_profile(
        filters=RankingFilter(location="Chennai")).ranked_jobs] == ["job-1", "job-3"]


# --- guards: no DB / no profile -----------------------------------------------------------------------------------------


def test_no_db_configured_skips_cleanly(monkeypatch):
    _clear_ai_env(monkeypatch)
    fake = FakeDB(configured=False)
    _install(monkeypatch, fake)
    result = ranking.rank_jobs_for_profile()
    assert result.ranked_jobs == []
    assert any("database not configured" in e for e in result.ranking_errors)


def test_no_profile_skips_cleanly(monkeypatch):
    _clear_ai_env(monkeypatch)
    fake = FakeDB(profile=False)
    _install(monkeypatch, fake)
    result = ranking.rank_jobs_for_profile()
    assert any("no candidate profile" in e for e in result.ranking_errors)


# --- recommendation end-to-end 22-24 ---------------------------------------------------------------------------


def test_avoid_ranks_below_review_end_to_end(monkeypatch):
    _clear_ai_env(monkeypatch)
    fake = FakeDB(rows=[
        _match_row("job-1", 80, 80, "AVOID"),
        _match_row("job-2", 60, 60, "REVIEW", title="Python Developer Intern"),
    ])
    _install(monkeypatch, fake)
    ranked = ranking.rank_jobs_for_profile().ranked_jobs
    assert [j.job_id for j in ranked] == ["job-2", "job-1"]

"""Phase 5.2 intelligence tests part 2: pipeline, caching, isolation, guards."""

import json
import os
from contextlib import contextmanager

import pytest

from ai.providers.base import AIRequest, AIResponse, BaseAIProvider
from ai.providers.gemini import GeminiError, GeminiProvider
from worker.db import match_repository as matches
from worker.pipelines import intelligence_pipeline as pipe
from worker.tests.test_intelligence import CANDIDATE, _intel, _job


class FakeGemini(BaseAIProvider):
    """Deterministic stand-in: canned payloads or scripted failures."""

    name = "fake-gemini"

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def configure(self):
        return None

    def is_configured(self):
        return True

    def generate(self, request: AIRequest) -> AIResponse:
        self.calls += 1
        assert isinstance(request.prompt, str) and "match_score" in request.prompt
        action = self.script.pop(0) if self.script else _intel()
        if isinstance(action, Exception):
            raise action
        return AIResponse(text=json.dumps(action) if isinstance(action, dict) else action)


class FakeTx:
    """Cursor stand-in for job_matches reads/writes against the FakeDB."""

    def __init__(self, fake, fail_on_save=False) -> None:
        self.fake = fake
        self.fail_on_save = fail_on_save
        self._result = None

    def execute(self, sql, params=()):
        self._result = None
        matches = self.fake.matches
        if "FROM public.job_matches WHERE" in sql:
            self._result = [m for m in matches.values()
                            if m["profile_id"] == params[0] and m["job_id"] == params[1]]
        elif sql.strip().startswith("INSERT INTO public.job_matches"):
            if self.fail_on_save:
                raise RuntimeError("simulated save failure")
            pid, jid = params[0], params[1]
            matches[(pid, jid)] = {
                "id": f"m-{pid}-{jid}", "profile_id": pid, "job_id": jid,
                "match_score": params[2], "trust_score": params[3], "recommendation": params[4],
                "matched_skills": json.loads(params[5]), "missing_skills": json.loads(params[6]),
                "strengths": json.loads(params[7]), "risk_signals": json.loads(params[8]),
                "reason": params[9], "analyzed_by": params[10],
            }
            self._result = [matches[(pid, jid)]]
        elif sql.strip().startswith("UPDATE public.job_matches"):
            if self.fail_on_save:
                raise RuntimeError("simulated save failure")
            *vals, pid, jid = params
            row = matches[(pid, jid)]
            row.update(dict(zip(
                ("match_score", "trust_score", "recommendation", "matched_skills",
                 "missing_skills", "strengths", "risk_signals", "reason", "analyzed_by"),
                [vals[0], vals[1], vals[2], json.loads(vals[3]), json.loads(vals[4]),
                 json.loads(vals[5]), json.loads(vals[6]), vals[7], vals[8]])))
            self._result = [row]
        else:  # pragma: no cover
            raise AssertionError(f"FakeDB cannot handle SQL: {sql[:80]}")

    def fetchone(self):
        return dict(self._result[0]) if self._result else None

    def fetchall(self):
        return [dict(r) for r in (self._result or [])]


class FakeDB:
    """Module-attribute replacement for worker.db.client in pipeline tests."""

    def __init__(self, configured=True, profile=True, jobs=None, sources=None,
                 matches_seed=None, fail_on_save=False) -> None:
        self.configured = configured
        self.profile = {
            "id": "prof-1", "user_id": None, "full_name": "Dev", "education": "MCA",
            "experience_level": "Fresher", "preferred_work_mode": "Remote + On-site",
            "relocation_allowed": True, "minimum_stipend": None,
        } if profile else None
        self.skills = [
            {"skill_name": s, "skill_level": "intermediate", "is_learning": False}
            for s in CANDIDATE["skills"]
        ] + [{"skill_name": s, "skill_level": "learning", "is_learning": True} for s in CANDIDATE["learning"]]
        self.roles = [{"role_name": r} for r in CANDIDATE["target_roles"]]
        self.locations = [{"location_name": loc, "is_remote": loc == "Remote"} for loc in ["Chennai", "Bangalore", "India", "Remote"]]
        self.jobs = jobs if jobs is not None else []
        self.sources = sources if sources is not None else []
        self.matches = dict(matches_seed or {})
        self.fail_on_save = fail_on_save

    def is_configured(self):
        return self.configured

    def fetch_one(self, sql, params=()):
        rows = self.fetch_all(sql, params)
        return rows[0] if rows else None

    def fetch_all(self, sql, params=()):
        if "FROM public.profiles" in sql:
            return [self.profile] if self.profile else []
        if "FROM public.profile_skills" in sql:
            return list(self.skills)
        if "FROM public.target_roles" in sql:
            return list(self.roles)
        if "FROM public.target_locations" in sql:
            return list(self.locations)
        if "FROM public.jobs" in sql:
            return list(self.jobs)
        if "FROM public.job_sources" in sql:
            return list(self.sources)
        if "FROM public.job_matches WHERE" in sql:
            return [m for m in self.matches.values()
                    if m["profile_id"] == params[0] and m["job_id"] == params[1]]
        raise AssertionError(f"FakeDB cannot handle SQL: {sql[:80]}")  # pragma: no cover

    @contextmanager
    def transaction(self):
        yield FakeTx(self, self.fail_on_save)


def _db_job(job_id="job-1", **overrides):
    row = {
        "id": job_id, "company_id": "c1", "title": "Java Developer Intern",
        "company_name": "Example Technologies",
        "description": "6-month Java internship. REST APIs, Spring Boot, SQL. Freshers welcome. " * 8,
        "location": "Chennai, India", "is_remote": False, "employment_type": "Internship",
        "experience_level": "Fresher", "salary_min": 15000, "salary_max": 25000,
        "salary_currency": "INR", "skills": ["Java", "SQL"], "posted_at": None,
        "apply_url": f"https://example.com/jobs/{job_id}", "status": "active",
    }
    row.update(overrides)
    return row


def _src(job_id, stype="greenhouse", sname="greenhouse:example"):
    return {"job_id": job_id, "source_type": stype, "source_name": sname}


def _complete_match(job_id="job-1", **overrides):
    row = {"id": f"m-{job_id}", "profile_id": "prof-1", "job_id": job_id,
           "match_score": 80, "trust_score": 88, "recommendation": "CONSIDER",
           "matched_skills": ["Java"], "missing_skills": ["Spring Boot"],
           "strengths": ["s"], "risk_signals": [], "reason": "Cached.",
           "analyzed_by": "gemini:test"}
    row.update(overrides)
    return row


@pytest.fixture
def ai_on(monkeypatch):
    monkeypatch.setenv("AI_ENABLED", "true")
    yield
    monkeypatch.delenv("AI_ENABLED", raising=False)


def _install(monkeypatch, fake):
    monkeypatch.setattr(pipe.db, "is_configured", fake.is_configured)
    monkeypatch.setattr(pipe.db, "fetch_one", fake.fetch_one)
    monkeypatch.setattr(pipe.db, "fetch_all", fake.fetch_all)
    monkeypatch.setattr(pipe.db, "transaction", fake.transaction)
    monkeypatch.setattr(matches.db, "fetch_one", fake.fetch_one)
    monkeypatch.setattr(matches.db, "fetch_all", fake.fetch_all)
    monkeypatch.setattr(matches.db, "transaction", fake.transaction)
    from worker.db import profile_repository as profiles

    monkeypatch.setattr(profiles.db, "fetch_one", fake.fetch_one)
    monkeypatch.setattr(profiles.db, "fetch_all", fake.fetch_all)


def test_rejected_jobs_never_reach_gemini(ai_on, monkeypatch):
    fake = FakeDB(jobs=[_db_job(title="Sales Executive", description="Field sales.")],
                  sources=[_src("job-1")])
    _install(monkeypatch, fake)
    gemini = FakeGemini([_intel()])
    result = pipe.run_intelligence(provider=gemini)
    assert gemini.calls == 0
    assert result.jobs_rejected_by_rules == 1 and result.jobs_sent_to_ai == 0


def test_accepted_job_reaches_gemini_and_persists(ai_on, monkeypatch):
    fake = FakeDB(jobs=[_db_job()], sources=[_src("job-1")])
    _install(monkeypatch, fake)
    gemini = FakeGemini([_intel()])
    result = pipe.run_intelligence(provider=gemini)
    assert gemini.calls == 1
    assert (result.matches_saved, result.jobs_analyzed) == (1, 1)
    assert result.recommendations.get("APPLY") == 1
    stored = fake.matches[("prof-1", "job-1")]
    assert stored["missing_skills"] == ["Spring Boot"] and stored["analyzed_by"].startswith("gemini:")


def test_gemini_failure_does_not_stop_remaining_jobs(ai_on, monkeypatch):
    fake = FakeDB(jobs=[_db_job("job-1"), _db_job("job-2")],
                  sources=[_src("job-1"), _src("job-2")])
    _install(monkeypatch, fake)
    gemini = FakeGemini([GeminiError("timeout"), _intel()])
    result = pipe.run_intelligence(provider=gemini)
    assert gemini.calls == 2 and len(result.errors) == 1
    assert result.jobs_analyzed == 1 and result.matches_saved == 1


def test_database_failure_does_not_stop_remaining_jobs(ai_on, monkeypatch):
    fake = FakeDB(jobs=[_db_job("job-1"), _db_job("job-2")],
                  sources=[_src("job-1"), _src("job-2")], fail_on_save=True)
    _install(monkeypatch, fake)
    result = pipe.run_intelligence(provider=FakeGemini([_intel(), _intel()]))
    assert len(result.errors) == 2 and result.matches_saved == 0


def test_cached_result_avoids_duplicate_ai_call(ai_on, monkeypatch):
    fake = FakeDB(jobs=[_db_job()], sources=[_src("job-1")],
                  matches_seed={("prof-1", "job-1"): _complete_match()})
    _install(monkeypatch, fake)
    gemini = FakeGemini([_intel()])
    result = pipe.run_intelligence(provider=gemini)
    assert gemini.calls == 0
    assert result.cached_results == 1 and result.jobs_analyzed == 1


def test_mock_job_does_not_call_gemini(ai_on, monkeypatch):
    fake = FakeDB(jobs=[_db_job()], sources=[_src("job-1", "manual", "mock")])
    _install(monkeypatch, fake)
    gemini = FakeGemini([_intel()])
    result = pipe.run_intelligence(provider=gemini)
    assert gemini.calls == 0 and result.skipped_mock == 1


def test_ai_disabled_means_zero_calls(monkeypatch):
    fake = FakeDB(configured=False, jobs=[_db_job()], sources=[_src("job-1")])
    _install(monkeypatch, fake)
    monkeypatch.delenv("AI_ENABLED", raising=False)
    gemini = FakeGemini([_intel()])
    result = pipe.run_intelligence(provider=gemini)
    assert gemini.calls == 0 and result.jobs_sent_to_ai == 0
    assert any("AI disabled" in e for e in result.errors)


def test_missing_gemini_key_handled_cleanly(ai_on, monkeypatch):
    fake = FakeDB(jobs=[_db_job()], sources=[_src("job-1")])
    _install(monkeypatch, fake)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = pipe.run_intelligence(provider=GeminiProvider(api_key=""))
    assert any("Gemini not configured" in e for e in result.errors)


def test_missing_db_configuration_handled_cleanly(ai_on, monkeypatch):
    fake = FakeDB(configured=False)
    _install(monkeypatch, fake)
    gemini = FakeGemini([_intel()])
    result = pipe.run_intelligence(provider=gemini)
    assert gemini.calls == 0
    assert any("database not configured" in e for e in result.errors)


def test_max_jobs_per_run_respected(ai_on, monkeypatch):
    fake = FakeDB(jobs=[_db_job(f"job-{i}") for i in range(3)],
                  sources=[_src(f"job-{i}") for i in range(3)])
    _install(monkeypatch, fake)
    gemini = FakeGemini([_intel(), _intel(), _intel()])
    result = pipe.run_intelligence(provider=gemini, max_ai_jobs=1)
    assert gemini.calls == 1 and result.jobs_sent_to_ai == 1


def test_malformed_and_empty_ai_output_handled(ai_on, monkeypatch):
    fake = FakeDB(jobs=[_db_job("job-1"), _db_job("job-2")],
                  sources=[_src("job-1"), _src("job-2")])
    _install(monkeypatch, fake)
    result = pipe.run_intelligence(provider=FakeGemini(["{oops", ""]))
    assert len(result.errors) == 2 and result.jobs_analyzed == 0


def test_no_candidate_profile_errors_cleanly(ai_on, monkeypatch):
    fake = FakeDB(profile=False)
    _install(monkeypatch, fake)
    result = pipe.run_intelligence(provider=FakeGemini([_intel()]))
    assert any("no candidate profile" in e for e in result.errors)

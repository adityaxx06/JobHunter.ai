"""Phase 6.2 enrichment tests. Fully offline — every boundary is faked.

Reuses the Phase 5.2 FakeDB/FakeGemini conventions (imported, not rebuilt)
plus a ranking-join extension. No real Gemini, Tavily, ATS, or Supabase.
"""

import pytest

from worker.db import ranking_repository as ranking_repo
from worker.pipelines import enrichment_pipeline as enrich
from worker.pipelines.enrichment_pipeline import run_enrichment
from worker.tests.test_intelligence_pipeline import (
    FakeDB as IntelFakeDB,
    FakeGemini,
    _complete_match,
    _db_job,
    _install,
    _intel,
    _src,
)


class FakeDB(IntelFakeDB):
    """Intel FakeDB + the ranking join (matches x jobs for one profile)."""

    def fetch_all(self, sql, params=()):
        if "JOIN public.jobs" in sql:
            rows = []
            for (pid, jid), match in self.matches.items():
                if pid != params[0]:
                    continue
                job = next((j for j in self.jobs if j["id"] == jid), {})
                rows.append({
                    "job_id": jid, "profile_id": pid,
                    "match_score": match["match_score"], "trust_score": match["trust_score"],
                    "recommendation": match["recommendation"],
                    "matched_skills": match.get("matched_skills", []),
                    "missing_skills": match.get("missing_skills", []),
                    "strengths": match.get("strengths", []),
                    "reason": match.get("reason", ""),
                    "title": job.get("title", ""), "location": job.get("location", ""),
                    "is_remote": job.get("is_remote", False),
                    "employment_type": job.get("employment_type", ""),
                    "apply_url": job.get("apply_url", ""),
                    "salary_min": job.get("salary_min"), "salary_max": job.get("salary_max"),
                    "salary_currency": job.get("salary_currency"),
                    "normalized_title": (job.get("title") or "").lower(),
                    "company_name": job.get("company_name", ""),
                })
            return rows
        return super().fetch_all(sql, params)


@pytest.fixture
def ai_on(monkeypatch):
    monkeypatch.setenv("AI_ENABLED", "true")
    yield
    monkeypatch.delenv("AI_ENABLED", raising=False)


def _install_ranking(monkeypatch, fake):
    _install(monkeypatch, fake)
    monkeypatch.setattr(ranking_repo.db, "fetch_all", fake.fetch_all)
    monkeypatch.setattr(ranking_repo.db, "is_configured", fake.is_configured)


# --- candidate selection -------------------------------------------------------------------


def test_analyzed_job_skipped_but_still_ranks(ai_on, monkeypatch):
    fake = FakeDB(jobs=[_db_job()], sources=[_src("job-1")],
                  matches_seed={("prof-1", "job-1"): _complete_match()})
    _install_ranking(monkeypatch, fake)
    gemini = FakeGemini([_intel()])
    result = run_enrichment(provider=gemini)
    assert gemini.calls == 0 and result.intelligence.cached_results == 1
    assert result.ranking is not None and len(result.ranking.ranked_jobs) == 1


def test_unanalyzed_job_selected_and_ranked(ai_on, monkeypatch):
    fake = FakeDB(jobs=[_db_job()], sources=[_src("job-1")])
    _install_ranking(monkeypatch, fake)
    gemini = FakeGemini([_intel(match_score=90, trust_score=92)])
    result = run_enrichment(provider=gemini)
    assert gemini.calls == 1 and result.intelligence.matches_saved == 1
    assert [j.job_id for j in result.ranking.ranked_jobs] == ["job-1"]
    assert result.gemini_calls == 1 and result.intelligence_writes == 1


def test_cap_takes_first_candidates_in_order(ai_on, monkeypatch):
    fake = FakeDB(jobs=[_db_job(f"job-{i}") for i in range(3)],
                  sources=[_src(f"job-{i}") for i in range(3)])
    _install_ranking(monkeypatch, fake)
    gemini = FakeGemini([_intel(), _intel(), _intel()])
    result = run_enrichment(provider=gemini, max_ai_jobs=2)
    assert gemini.calls == 2
    saved = {key[1] for key in fake.matches}
    assert saved == {"job-0", "job-1"}  # deterministic: first N in load order


def test_profile_isolation(ai_on, monkeypatch):
    fake = FakeDB(jobs=[_db_job()], sources=[_src("job-1")],
                  matches_seed={("prof-9", "job-1"): _complete_match()})
    fake.matches[("prof-9", "job-1")]["profile_id"] = "prof-9"
    _install_ranking(monkeypatch, fake)
    gemini = FakeGemini([_intel()])
    result = run_enrichment(provider=gemini)  # default profile is prof-1
    assert gemini.calls == 1 and result.intelligence.matches_saved == 1


def test_empty_database_is_clean_success(ai_on, monkeypatch):
    fake = FakeDB(jobs=[], sources=[])
    _install_ranking(monkeypatch, fake)
    gemini = FakeGemini([])
    result = run_enrichment(provider=gemini)
    assert result.intelligence.jobs_received == 0 and gemini.calls == 0
    assert result.intelligence_writes == 0 and result.ranking.ranked_jobs == []


# --- prefilter -----------------------------------------------------------------------------------


def test_rejected_job_never_reaches_gemini(ai_on, monkeypatch):
    fake = FakeDB(jobs=[_db_job(title="Sales Executive", description="Field sales.")],
                  sources=[_src("job-1")])
    _install_ranking(monkeypatch, fake)
    gemini = FakeGemini([_intel()])
    result = run_enrichment(provider=gemini)
    assert gemini.calls == 0 and result.intelligence.jobs_rejected_by_rules == 1
    assert result.ranking.ranked_jobs == []


def test_dry_run_counts_without_calls_or_writes(ai_on, monkeypatch):
    fake = FakeDB(jobs=[_db_job("job-1"), _db_job("job-2")],
                  sources=[_src("job-1"), _src("job-2")])
    _install_ranking(monkeypatch, fake)
    gemini = FakeGemini([_intel(), _intel()])
    result = run_enrichment(provider=gemini, dry_run=True)
    assert result.dry_run is True and gemini.calls == 0
    assert result.intelligence.jobs_would_analyze == 2
    assert result.intelligence_writes == 0 and not fake.matches
    assert result.ranking is None and "dry run" in result.ranking_skipped


def test_dry_run_respects_cap(ai_on, monkeypatch):
    fake = FakeDB(jobs=[_db_job(f"job-{i}") for i in range(3)],
                  sources=[_src(f"job-{i}") for i in range(3)])
    _install_ranking(monkeypatch, fake)
    result = run_enrichment(provider=FakeGemini([]), dry_run=True, max_ai_jobs=1)
    assert result.intelligence.jobs_would_analyze == 1


# --- gemini behavior -----------------------------------------------------------------------------------


def test_invalid_response_rejected_without_save(ai_on, monkeypatch):
    fake = FakeDB(jobs=[_db_job()], sources=[_src("job-1")])
    _install_ranking(monkeypatch, fake)
    result = run_enrichment(provider=FakeGemini(["{oops"]))
    assert len(result.intelligence.errors) == 1 and result.intelligence.matches_saved == 0
    assert not fake.matches and result.ranking.ranked_jobs == []


def test_failure_isolated_and_partial_set_ranks(ai_on, monkeypatch):
    from ai.providers.gemini import GeminiError

    fake = FakeDB(jobs=[_db_job("job-1"), _db_job("job-2")],
                  sources=[_src("job-1"), _src("job-2")])
    _install_ranking(monkeypatch, fake)
    gemini = FakeGemini([GeminiError("timeout"), _intel(match_score=88, trust_score=90)])
    result = run_enrichment(provider=gemini)
    assert gemini.calls == 2 and len(result.intelligence.errors) == 1
    assert result.intelligence.matches_saved == 1
    assert [j.job_id for j in result.ranking.ranked_jobs] == ["job-2"]


def test_second_run_is_idempotent(ai_on, monkeypatch):
    fake = FakeDB(jobs=[_db_job()], sources=[_src("job-1")])
    _install_ranking(monkeypatch, fake)
    gemini = FakeGemini([_intel()])
    first = run_enrichment(provider=gemini)
    second = run_enrichment(provider=gemini)
    assert (first.intelligence.matches_saved, gemini.calls) == (1, 1)
    assert second.intelligence.cached_results == 1 and gemini.calls == 1


def test_no_secret_leakage_in_errors(ai_on, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-secret-xyz-123")
    fake = FakeDB(jobs=[_db_job()], sources=[_src("job-1")])
    _install_ranking(monkeypatch, fake)
    result = run_enrichment(provider=FakeGemini([RuntimeError("boom")]))
    assert len(result.intelligence.errors) == 1
    for error in result.intelligence.errors:
        assert "fake-secret-xyz-123" not in error
    assert "fake-secret-xyz-123" not in str(result.summary())


# --- gates -----------------------------------------------------------------------------------


def test_ai_disabled_zero_calls_zero_writes_but_ranking_runs(monkeypatch):
    monkeypatch.delenv("AI_ENABLED", raising=False)
    fake = FakeDB(jobs=[_db_job()], sources=[_src("job-1")],
                  matches_seed={("prof-1", "job-1"): _complete_match()})
    _install_ranking(monkeypatch, fake)
    gemini = FakeGemini([_intel()])
    result = run_enrichment(provider=gemini)
    assert gemini.calls == 0 and result.intelligence_writes == 0
    assert any("AI disabled" in e for e in result.intelligence.errors)
    assert len(result.ranking.ranked_jobs) == 1  # stored intelligence still ranks


def test_ranking_makes_zero_gemini_calls(ai_on, monkeypatch):
    fake = FakeDB(jobs=[_db_job()], sources=[_src("job-1")])
    _install_ranking(monkeypatch, fake)
    gemini = FakeGemini([_intel(match_score=90, trust_score=92)])
    result = run_enrichment(provider=gemini)
    calls_after_intelligence = gemini.calls
    assert calls_after_intelligence == 1
    assert result.ranking is not None  # ranking ran after without touching the provider
    assert gemini.calls == calls_after_intelligence


def test_no_rank_flag_skips_ranking(ai_on, monkeypatch):
    fake = FakeDB(jobs=[_db_job()], sources=[_src("job-1")])
    _install_ranking(monkeypatch, fake)
    result = run_enrichment(provider=FakeGemini([_intel()]), run_ranking=False)
    assert result.ranking is None and "--no-rank" in result.ranking_skipped


# --- module boundaries -----------------------------------------------------------------------------------


def test_enrichment_module_has_no_discovery_imports():
    import pathlib
    import re

    source = pathlib.Path(enrich.__file__).read_text()
    assert not re.search(r"^\s*(from|import)\s+worker\.(search|sources|pipelines\.ingestion)", source, re.MULTILINE)
    assert "tavily" not in source.lower()


def test_parse_enrich_args():
    from worker.main import _parse_enrich_args

    assert _parse_enrich_args(["--enrich"]) == {
        "profile": "", "limit": None, "dry_run": False, "run_ranking": True, "rank_limit": None}
    parsed = _parse_enrich_args(["--enrich", "--profile", "p1", "--limit", "10", "--dry-run", "--no-rank"])
    assert parsed == {"profile": "p1", "limit": 10, "dry_run": True, "run_ranking": False, "rank_limit": None}
    assert _parse_enrich_args(["--enrich", "--rank-limit=bogus"])["rank_limit"] is None

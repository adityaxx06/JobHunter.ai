"""Phase 6.1 ingestion tests. Fully offline — every boundary is faked.

Faked: search provider, ATS sources (via source_factory), persistence
repository, database configuration. No Tavily / ATS / Gemini / Supabase
calls. Gemini is additionally armed to explode if ever touched.
"""

import pytest

from worker.db import client as db_client
from worker.db import job_repository
from worker.db.job_repository import PersistenceResult
from worker.models.job import DiscoveredJob
from worker.models.search import SearchResult
from worker.pipelines import ingestion_pipeline
from worker.pipelines.ingestion_pipeline import run_ingestion
from worker.search.base import SearchProvider
from worker.search.tavily import TavilySearchProvider


def _hit(url, title="Java Developer Intern"):
    return SearchResult(title=title, url=url, snippet="freshers welcome", source_name="fake-search")


def _job(board, job_id, title="Java Developer Intern"):
    return DiscoveredJob(
        external_id=job_id,
        title=title,
        company_name=f"{board.title()} Inc",
        location="Chennai, India",
        source_type="greenhouse",
        source_name="greenhouse",
        source_url=f"https://boards.greenhouse.io/{board}",
        apply_url=f"https://boards.greenhouse.io/{board}/jobs/{job_id}",
    )


class FakeProvider(SearchProvider):
    """Canned discovery: GH x2 (same board), Lever, Ashby, career, unknown."""

    provider_name = "fake-search"

    def __init__(self, hits=None):
        self._hits = hits if hits is not None else [
            _hit("https://boards.greenhouse.io/acme/jobs/1"),
            _hit("https://boards.greenhouse.io/acme/jobs/2"),
            _hit("https://jobs.lever.co/beta/abc"),
            _hit("https://jobs.ashbyhq.com/gamma/def"),
            _hit("https://example.com/careers/backend-dev"),
            _hit("https://example.com/blog/internships"),
        ]
        self.calls = 0

    def is_configured(self):
        return True

    def search(self, query, max_results=5):
        self.calls += 1
        return list(self._hits)

    def health_check(self):
        from worker.models.search import SearchHealth

        return SearchHealth(ok=True, message="fake")


class StubSource:
    """ATS stand-in: canned jobs, optional failure, last_errors protocol."""

    def __init__(self, jobs=None, fail=False, errors=None):
        self._jobs = list(jobs or [])
        self._fail = fail
        self.last_errors = list(errors or [])

    def discover_jobs(self, query="", location="", limit=50):
        if self._fail:
            raise RuntimeError("simulated connector failure")
        return list(self._jobs)


@pytest.fixture
def gates_off(monkeypatch):
    """Default safe world: no persist flags, no database."""
    monkeypatch.delenv("PERSIST_DISCOVERY", raising=False)
    monkeypatch.delenv("ENABLE_LIVE_INGESTION", raising=False)
    monkeypatch.delenv("ALLOW_MOCK_PERSIST", raising=False)
    monkeypatch.setattr(db_client, "is_configured", lambda: False)


@pytest.fixture
def no_persist_calls(monkeypatch):
    """Fail loudly if the repository write path is ever reached."""
    def _boom(discovery, **kwargs):
        raise AssertionError("persist_discovery_result must not be called in dry run")

    monkeypatch.setattr(job_repository, "persist_discovery_result", _boom)


def _factory(boards, calls):
    """source_factory over a {(type, id): StubSource} map, counting fetches."""

    def make(source_type, identifier):
        calls[(source_type, identifier)] = calls.get((source_type, identifier), 0) + 1
        return boards[(source_type, identifier)]

    return make


# --- happy path: discoveries reach their connectors ---------------------------------


def test_greenhouse_lever_ashby_reach_connectors(gates_off, no_persist_calls):
    boards = {
        ("greenhouse", "acme"): StubSource(jobs=[_job("acme", "1"), _job("acme", "2")]),
        ("lever", "beta"): StubSource(jobs=[_job("beta", "9", title="Backend Intern")]),
        ("ashby", "gamma"): StubSource(jobs=[_job("gamma", "7", title="Python Intern")]),
    }
    calls = {}
    result = run_ingestion(provider=FakeProvider(), persist_requested=False,
                           source_factory=_factory(boards, calls), max_queries=2)
    assert result.boards_attempted == 3 and result.boards_succeeded == 3
    assert result.jobs_fetched == 4 and result.jobs_normalized == 4
    assert result.unique_jobs == 4
    assert result.unresolved_company_career == 1 and result.unresolved_unknown == 1
    assert result.writes_performed is False and result.gemini_calls == 0
    assert result.persist_candidates == 4


def test_same_board_fetched_once(gates_off, no_persist_calls):
    boards = {("greenhouse", "acme"): StubSource(jobs=[_job("acme", "1")])}
    calls = {}
    hits = [_hit("https://boards.greenhouse.io/acme/jobs/1"),
            _hit("https://job-boards.greenhouse.io/acme/jobs/2"),
            _hit("https://boards.greenhouse.io/acme")]
    result = run_ingestion(provider=FakeProvider(hits=hits), persist_requested=False,
                           source_factory=_factory(boards, calls), max_queries=1)
    assert calls == {("greenhouse", "acme"): 1}
    assert result.boards_attempted == 1


def test_unknown_and_career_queued_never_fetched(gates_off, no_persist_calls):
    provider = FakeProvider(hits=[_hit("https://example.com/careers/x"), _hit("https://example.com/blog/y")])

    def _boom_factory(source_type, identifier):
        raise AssertionError("no ATS fetch may happen for queued targets")

    result = run_ingestion(provider=provider, persist_requested=False,
                           source_factory=_boom_factory, max_queries=1)
    assert result.boards_attempted == 0
    assert result.unresolved_company_career == 1 and result.unresolved_unknown == 1
    assert result.jobs_fetched == 0 and result.writes_performed is False


# --- isolation -------------------------------------------------------------------------------


def test_connector_failure_does_not_terminate_run(gates_off, no_persist_calls):
    boards = {
        ("greenhouse", "acme"): StubSource(jobs=[_job("acme", "1")]),
        ("lever", "beta"): StubSource(jobs=[_job("beta", "9", title="Backend Intern")]),
        ("ashby", "gamma"): StubSource(fail=True),
    }
    calls = {}
    result = run_ingestion(provider=FakeProvider(), persist_requested=False,
                           source_factory=_factory(boards, calls), max_queries=1)
    assert result.boards_succeeded == 2 and result.boards_failed == 1
    assert result.jobs_fetched == 2
    assert any("gamma" in e for e in result.errors)


def test_duplicate_discovery_deduplicated(gates_off, no_persist_calls):
    same = _job("acme", "1")
    boards = {
        ("greenhouse", "acme"): StubSource(jobs=[same]),
        ("lever", "beta"): StubSource(jobs=[_job("acme", "1")]),  # same fingerprint
    }
    result = run_ingestion(provider=FakeProvider(), persist_requested=False,
                           source_factory=_factory(boards, {}), max_queries=1)
    assert result.jobs_fetched == 2 and result.unique_jobs == 1
    assert result.duplicates_in_run == 1


# --- gates -----------------------------------------------------------------------------------


def test_dry_run_default_zero_writes(gates_off, no_persist_calls):
    boards = {("greenhouse", "acme"): StubSource(jobs=[_job("acme", "1")])}
    result = run_ingestion(provider=FakeProvider(), source_factory=_factory(boards, {}), max_queries=1)
    assert result.persist_requested is False and result.writes_performed is False
    assert "dry run" in result.gate_details


def test_persist_blocked_unless_all_gates_pass(gates_off, no_persist_calls, monkeypatch):
    boards = {("greenhouse", "acme"): StubSource(jobs=[_job("acme", "1")])}
    factory = _factory(boards, {})
    # Gate 1: --persist alone is not enough.
    result = run_ingestion(provider=FakeProvider(), persist_requested=True,
                           source_factory=factory, max_queries=1)
    assert result.writes_performed is False
    # Gate 2: PERSIST_DISCOVERY alone is not enough.
    monkeypatch.setenv("PERSIST_DISCOVERY", "true")
    result = run_ingestion(provider=FakeProvider(), persist_requested=True,
                           source_factory=factory, max_queries=1)
    assert result.writes_performed is False and "ENABLE_LIVE_INGESTION" in result.gate_details
    # Gate 3: both flags but no database -> still no writes.
    monkeypatch.setenv("ENABLE_LIVE_INGESTION", "true")
    result = run_ingestion(provider=FakeProvider(), persist_requested=True,
                           source_factory=factory, max_queries=1)
    assert result.writes_performed is False and "DATABASE_URL" in result.gate_details


def test_persist_writes_only_when_all_gates_pass(monkeypatch):
    recorded = {}

    def _fake_persist(discovery, **kwargs):
        recorded["count"] = len(discovery.jobs)
        out = PersistenceResult(discovered_count=len(discovery.jobs))
        out.inserted_count = len(discovery.jobs)
        out.source_links_created = len(discovery.jobs)
        out.companies_created = 1
        return out

    monkeypatch.setenv("PERSIST_DISCOVERY", "true")
    monkeypatch.setenv("ENABLE_LIVE_INGESTION", "true")
    monkeypatch.setattr(db_client, "is_configured", lambda: True)
    monkeypatch.setattr(job_repository, "persist_discovery_result", _fake_persist)
    boards = {("greenhouse", "acme"): StubSource(jobs=[_job("acme", "1"), _job("acme", "2")])}
    result = run_ingestion(provider=FakeProvider(), persist_requested=True,
                           source_factory=_factory(boards, {}), max_queries=1)
    assert result.writes_performed is True
    assert result.inserted_count == 2 and recorded["count"] == 2
    assert result.source_links_created == 2 and result.companies_created == 1


def test_missing_provider_key_no_crash_no_writes(gates_off, no_persist_calls):
    provider = TavilySearchProvider(api_key="")  # real provider, no key, offline
    result = run_ingestion(provider=provider, persist_requested=False, max_queries=2)
    assert result.queries_executed == 0 and result.boards_attempted == 0
    assert result.writes_performed is False and result.errors


def test_board_cap_bounds_fetches(gates_off, no_persist_calls):
    boards = {
        ("greenhouse", "a1"): StubSource(jobs=[_job("a1", "1")]),
        ("greenhouse", "a2"): StubSource(jobs=[_job("a2", "1")]),
        ("lever", "b1"): StubSource(jobs=[_job("b1", "1")]),
    }
    calls = {}
    result = run_ingestion(provider=FakeProvider(), persist_requested=False,
                           source_factory=_factory(boards, calls), max_queries=1, max_boards=2)
    assert result.boards_attempted == 2 and result.boards_skipped_over_cap == 1
    assert len(calls) == 2


# --- gemini off -----------------------------------------------------------------------------------


def test_gemini_never_called(monkeypatch, gates_off, no_persist_calls):
    from ai.providers.gemini import GeminiProvider

    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("RUN_INTELLIGENCE", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(GeminiProvider, "generate",
                        lambda self, request: (_ for _ in ()).throw(AssertionError("Gemini must not be called")))
    boards = {("greenhouse", "acme"): StubSource(jobs=[_job("acme", "1")])}
    result = run_ingestion(provider=FakeProvider(), persist_requested=False,
                           source_factory=_factory(boards, {}), max_queries=1)
    assert result.gemini_calls == 0 and result.jobs_normalized == 1


def test_pipeline_module_has_no_ai_reference():
    import pathlib
    import re

    source = pathlib.Path(ingestion_pipeline.__file__).read_text()
    assert not re.search(r"^\s*(from|import)\s+ai[\s.]", source, re.MULTILINE)
    assert "GeminiProvider" not in source
    assert "intelligence_pipeline" not in source
    assert "run_intelligence" not in source


# --- CLI parsing -----------------------------------------------------------------------------------


def test_parse_discover_args():
    from worker.main import _parse_discover_args

    assert _parse_discover_args(["--discover"]) == {"provider": "", "persist": False, "max_queries": None}
    assert _parse_discover_args(["--discover", "--provider", "tavily", "--persist"])["persist"] is True
    parsed = _parse_discover_args(["--discover", "--provider=tavily", "--max-queries", "3"])
    assert parsed["provider"] == "tavily" and parsed["max_queries"] == 3
    assert _parse_discover_args(["--discover", "--max-queries=bogus"])["max_queries"] is None


# --- Phase 9: aggregator URL-first path --------------------------------------------------


def _agg_hits():
    return [
        _hit("https://www.linkedin.com/jobs/view/111", "AI Engineer Intern"),
        _hit("https://www.linkedin.com/jobs/search/?keywords=ai", "AI jobs search"),
        _hit("https://in.indeed.com/viewjob?jk=abc", "Backend Intern"),
        _hit("https://internshala.com/internship/detail/x-1", "Python Intern"),
        _hit("https://example.com/blog/internships"),
    ]


def _no_ats_factory():
    def make(source_type, identifier):
        raise AssertionError("no ATS fetch in aggregator-only test")

    return make


def _gates_on(monkeypatch):
    monkeypatch.setenv("PERSIST_DISCOVERY", "true")
    monkeypatch.setenv("ENABLE_LIVE_INGESTION", "true")
    monkeypatch.setattr(db_client, "is_configured", lambda: True)


def test_aggregator_details_normalize_and_persist(monkeypatch):
    recorded = {}

    def _fake_persist(discovery, **kwargs):
        recorded["jobs"] = list(discovery.jobs)
        out = PersistenceResult(discovered_count=len(discovery.jobs))
        out.inserted_count = len(discovery.jobs)
        out.source_links_created = len(discovery.jobs)
        return out

    _gates_on(monkeypatch)
    monkeypatch.setattr(job_repository, "persist_discovery_result", _fake_persist)
    result = run_ingestion(provider=FakeProvider(_agg_hits()), persist_requested=True,
                           source_factory=_no_ats_factory(), max_queries=1, max_boards=5)
    assert result.aggregator_converted == 3
    assert result.aggregator_skipped == 2
    # Converted items leave the unresolved buckets (only the blog remains).
    assert result.unresolved_company_career == 1  # linkedin search page
    assert result.unresolved_unknown == 1  # blog
    assert result.jobs_normalized == 3 and result.unique_jobs == 3
    assert result.writes_performed is True and result.inserted_count == 3
    assert recorded["jobs"] and all(
        j.original.source_type == "job_board" for j in recorded["jobs"])
    assert {j.original.source_name for j in recorded["jobs"]} == {"linkedin", "indeed", "internshala"}


def test_aggregator_dry_run_counts_without_writes(gates_off, no_persist_calls):
    result = run_ingestion(provider=FakeProvider(_agg_hits()), persist_requested=False,
                           source_factory=_no_ats_factory(), max_queries=1, max_boards=5)
    assert result.aggregator_converted == 3 and result.writes_performed is False
    assert result.persist_candidates == 3 and result.gemini_calls == 0


def test_aggregator_tracking_duplicates_dedupe(gates_off, no_persist_calls):
    hits = [
        _hit("https://www.linkedin.com/jobs/view/111", "AI Engineer Intern"),
        _hit("https://www.linkedin.com/jobs/view/111?utm_source=x", "AI Engineer Intern"),
    ]
    result = run_ingestion(provider=FakeProvider(hits), persist_requested=False,
                           source_factory=_no_ats_factory(), max_queries=1, max_boards=5)
    assert result.results_found == 2  # raw hits counted
    assert result.targets_found == 1  # canonical search-layer dedup first
    assert result.aggregator_converted == 1
    assert result.unique_jobs == 1 and result.duplicates_in_run == 0


def test_aggregator_cap_bounds_conversions(gates_off, no_persist_calls):
    hits = [_hit(f"https://www.linkedin.com/jobs/view/{i}", f"Job {i}") for i in range(4)]
    result = run_ingestion(provider=FakeProvider(hits), persist_requested=False,
                           source_factory=_no_ats_factory(), max_queries=1, max_boards=2)
    assert result.aggregator_converted == 2 and result.aggregator_skipped == 2


def test_aggregator_fingerprint_dedupes_rediscovery():
    from worker.processors.deduplicator.job_deduplicator import deduplicate_jobs
    from worker.processors.normalizer.job_normalizer import normalize_job
    from worker.sources.aggregators import discovered_job_from_target

    first = normalize_job(discovered_job_from_target(
        "https://www.linkedin.com/jobs/view/111", "AI Engineer Intern", "Freshers welcome"))
    second = normalize_job(discovered_job_from_target(
        "https://www.linkedin.com/jobs/view/111?utm_source=x#top", "AI Engineer Intern",
        "Freshers welcome (updated snippet)"))
    deduped = deduplicate_jobs([first, second])
    assert len(deduped.unique_jobs) == 1 and deduped.duplicate_count == 1

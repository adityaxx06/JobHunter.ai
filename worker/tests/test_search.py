"""Phase 4.3 search-framework tests. Fully offline (mock provider only)."""

import pytest

from worker.models.search import (
    DiscoveryTarget,
    SearchPipelineResult,
    SearchQuery,
    SearchResult,
)
from worker.pipelines.search_pipeline import run_search_discovery
from worker.search import config as search_config
from worker.search import registry as search_registry
from worker.search.base import SearchProvider
from worker.search.classifier import (
    classify_results,
    classify_url,
)
from worker.search.mock_provider import MockSearchProvider
from worker.search.query_generator import (
    DEFAULT_LOCATIONS,
    DEFAULT_ROLES,
    FRESHER_TERMS,
    JOB_BOARD_HINTS,
    SearchProfile,
    generate_queries,
    generate_site_queries,
    load_search_profile,
    search_profile_from_candidate,
)


@pytest.fixture
def saved_providers():
    """Snapshot + restore the provider registry around mutating tests."""
    snapshot = search_registry.get_all_providers()
    yield
    search_registry.clear_providers()
    for provider in snapshot:
        search_registry.register_provider(provider)


# --- 1. search result model ----------------------------------------------------


def test_search_result_model_defaults():
    result = SearchResult(title="Java Developer Intern", url="https://example.com/j/1")
    assert result.snippet == "" and result.raw_data == {}
    assert result.discovered_at is not None
    assert SearchResult().source_name == ""
    target = DiscoveryTarget(url="https://example.com/j/1")
    assert target.classified_source == "unknown"  # never assume a source
    assert SearchPipelineResult().classification_stats == {}


# --- 2. provider interface ------------------------------------------------------


def test_provider_interface_contract():
    assert issubclass(MockSearchProvider, SearchProvider)
    with pytest.raises(TypeError):
        SearchProvider()  # abstract: cannot instantiate directly
    assert MockSearchProvider().health_check().ok is True


# --- 3. mock provider ------------------------------------------------------------


def test_mock_provider_returns_flagged_results():
    results = MockSearchProvider().search("Java Developer Intern")
    assert len(results) == 5
    for result in results:
        assert result.source_name == "mock"
        assert result.raw_data.get("mock") is True
        assert "MOCK" in result.snippet
        assert result.url.startswith("https://")
    assert len(MockSearchProvider().search("intern", max_results=2)) == 2
    assert len(MockSearchProvider().search("python")) == 1  # filter narrows, then limit applies


# --- 4/5. query generation + limits -------------------------------------------------


def test_query_generation_bounded():
    queries = generate_queries(SearchProfile(), max_queries=30)
    assert 0 < len(queries) <= 30
    assert len({q.query for q in queries}) == len(queries)  # no duplicates
    assert len(generate_queries(SearchProfile(), max_queries=5)) == 5
    assert generate_queries(SearchProfile(), max_queries=0) == []


# --- 6/7/8. role / location / fresher queries ------------------------------------------


def test_role_location_and_fresher_coverage():
    queries = [q.query for q in generate_queries(SearchProfile(), max_queries=30)]
    assert any("Java Developer" in q and "India" in q for q in queries)
    assert any("Chennai" in q or "Bangalore" in q for q in queries)
    assert any(term in " ".join(queries).lower() for term in ("intern", "fresher"))
    assert any("remote" in q.lower() for q in queries)  # remote_ok default True
    no_remote = generate_queries(SearchProfile(remote_ok=False), max_queries=30)
    assert not any(q.location == "remote" for q in no_remote)


# --- 9. source-specific queries -------------------------------------------------------------


def test_site_hint_queries():
    queries = generate_site_queries(["Java Developer"], max_queries=3)
    assert queries[0].query == 'site:boards.greenhouse.io "Java Developer Intern"'
    assert queries[0].site_hint == "site:boards.greenhouse.io"
    assert [q.site_hint for q in queries] == [
        "site:boards.greenhouse.io",
        "site:jobs.lever.co",
        "site:jobs.ashbyhq.com",
    ]


# --- 10/11/12. ATS URL classification -----------------------------------------------------------


def test_ats_url_classification():
    assert classify_url("https://boards.greenhouse.io/acme/jobs/1") == "greenhouse"
    assert classify_url("https://jobs.lever.co/acme/abc") == "lever"
    assert classify_url("https://jobs.ashbyhq.com/acme/def") == "ashby"
    # Company name in title must NOT influence classification (URL-only rule).
    assert classify_url("https://example.com/greenhouse-jobs") != "greenhouse"


# --- 13/14. company-career + unknown ---------------------------------------------------------------


def test_career_and_unknown_classification():
    assert classify_url("https://example.com/careers/backend-dev") == "company_career"
    assert classify_url("https://acme.com/jobs/123") == "company_career"
    assert classify_url("https://example.com/blog/internships") == "unknown"


# --- 15. malformed URLs -------------------------------------------------------------------------------


def test_malformed_urls_are_unknown():
    assert classify_url("") == "unknown"
    assert classify_url(None) == "unknown"
    assert classify_url("not a url at all") == "unknown"
    assert classify_url(12345) == "unknown"


# --- 16. search pipeline ---------------------------------------------------------------------------------


def test_search_pipeline_counts_and_stats():
    result = run_search_discovery(SearchProfile(), provider=MockSearchProvider(), max_queries=10)
    assert result.queries_generated == 10 and result.queries_executed == 10
    assert result.results_found >= result.targets_found > 0
    stats = result.classification_stats
    assert stats.get("greenhouse", 0) >= 1
    assert stats.get("lever", 0) >= 1
    assert stats.get("ashby", 0) >= 1
    assert sum(stats.values()) == result.targets_found
    assert all(isinstance(t, DiscoveryTarget) for t in result.targets)


# --- 17. provider failure isolation ---------------------------------------------------------------------------


class _FlakyProvider(SearchProvider):
    provider_name = "flaky"

    def __init__(self, fail_on):
        self.fail_on = fail_on

    def search(self, query: str, max_results: int = 20):
        if self.fail_on in query:
            raise RuntimeError("simulated outage")
        return MockSearchProvider().search(query, max_results=max_results)


def test_pipeline_isolates_query_failure():
    result = run_search_discovery(
        SearchProfile(roles=["Java Developer", "Python Developer"], locations=["India"]),
        provider=_FlakyProvider("Python"),
        max_queries=10,
    )
    assert result.queries_executed < result.queries_generated
    assert result.targets_found > 0  # surviving queries still produce targets
    assert any("simulated outage" in e for e in result.errors)


# --- 18. empty search results ------------------------------------------------------------------------------------


def test_empty_results_stay_healthy():
    class _Empty(SearchProvider):
        provider_name = "empty"

        def search(self, query: str, max_results: int = 20):
            return []

    result = run_search_discovery(SearchProfile(), provider=_Empty(), max_queries=5)
    assert result.results_found == 0 and result.targets_found == 0
    assert result.errors == []  # empty is valid, not an error


# --- 19. duplicate search results -------------------------------------------------------------------------------------


def test_duplicate_urls_deduped():
    class _Dupes(SearchProvider):
        provider_name = "dupes"

        def search(self, query: str, max_results: int = 20):
            return MockSearchProvider().search("", max_results=5)

    result = run_search_discovery(SearchProfile(), provider=_Dupes(), max_queries=4)
    urls = [t.url for t in result.targets]
    assert len(urls) == len(set(urls)) == 5  # same 5 URLs across queries -> 5 targets


# --- 20. configuration parsing ----------------------------------------------------------------------------------------------


def test_search_config_defaults_and_parsing():
    assert search_config.is_enabled({}) is False
    assert search_config.is_enabled({"SEARCH_ENABLED": "true"}) is True
    assert search_config.get_provider_name({}) == "mock"
    assert search_config.get_timeout({}) == 10.0
    assert search_config.get_max_results({}) == 20
    assert search_config.get_max_results({"SEARCH_MAX_RESULTS": "999"}) == 50  # clamped
    assert search_config.get_max_results({"SEARCH_MAX_RESULTS": "bogus"}) == 20
    assert search_config.get_api_key({}) == "" and search_config.has_api_key({}) is False
    assert search_config.has_api_key({"SEARCH_API_KEY": "x"}) is True


def test_api_key_never_leaks_into_messages():
    provider = MockSearchProvider()
    assert "sk-" not in provider.health_check().message
    result = run_search_discovery(SearchProfile(), provider=provider, max_queries=2)
    assert not any("sk-" in e for e in result.errors)


def test_search_registry():
    assert isinstance(search_registry.get_provider("mock"), MockSearchProvider)
    assert search_registry.get_provider("nope") is None
    assert {p.provider_name for p in search_registry.get_all_providers()} >= {"mock"}


# --- 21. ATS site-query wiring (Phase 6 fix: production includes site: queries) ---


def test_site_queries_wired_into_production_generation():
    """Test A: generate_queries() blends in ATS-targeted queries (all hosts)."""
    queries = generate_queries(SearchProfile(), max_queries=30)
    hints = [q.site_hint for q in queries if q.site_hint]
    assert hints, "production generation must include site-targeted queries"
    assert {"site:boards.greenhouse.io", "site:jobs.lever.co", "site:jobs.ashbyhq.com"} <= set(hints)
    assert all(q.query.startswith(hint) for q, hint in
               [(q, q.site_hint) for q in queries if q.site_hint])


def test_site_queries_within_small_budgets():
    """Test A2/B: even tiny budgets execute ATS discovery; caps always hold."""
    assert len(generate_queries(SearchProfile(), max_queries=3)) == 3
    assert sum(1 for q in generate_queries(SearchProfile(), max_queries=3) if q.site_hint) >= 1
    five = generate_queries(SearchProfile(), max_queries=5)
    assert len(five) == 5 and sum(1 for q in five if q.site_hint) >= 1
    for budget in (1, 2, 3, 5, 10, 30):
        assert len(generate_queries(SearchProfile(), max_queries=budget)) <= budget


def test_blended_queries_no_duplicates():
    """Test C: exact-duplicate strings never reach the provider."""
    for budget in (5, 10, 30):
        queries = generate_queries(SearchProfile(), max_queries=budget)
        assert len({q.query for q in queries}) == len(queries)


def test_generic_queries_still_supported():
    """Test D: blending never drops the legacy generic coverage."""
    queries = [q.query for q in generate_queries(SearchProfile(), max_queries=30)]
    assert any("Java Developer" in q and "India" in q for q in queries)
    assert queries[0] == '"Software Developer intern" India'  # tier-1 head first
    assert sum(1 for q in queries if not q.startswith("site:")) >= 20


def test_production_path_executes_site_queries():
    """Test F: the worker's discovery path sends site: queries to the provider."""

    class _Recorder(SearchProvider):
        provider_name = "recorder"

        def __init__(self):
            self.executed = []

        def search(self, query: str, max_results: int = 20):
            self.executed.append(query)
            return []

    recorder = _Recorder()
    result = run_search_discovery(SearchProfile(), provider=recorder, max_queries=5)
    assert result.queries_executed == 5 and len(recorder.executed) == 5
    assert any(q.startswith("site:") for q in recorder.executed)
    assert len(set(recorder.executed)) == 5  # budget respected, no dupes sent


# --- 22. profile-driven generation (Phase 7A: DB profile steers queries) ---


def test_job_board_site_queries_wired():
    """Job-board hosts (LinkedIn/Internshala/Indeed) join the production blend."""
    assert JOB_BOARD_HINTS == ["site:linkedin.com/jobs", "site:internshala.com", "site:indeed.com"]
    queries = generate_queries(SearchProfile(), max_queries=30)
    hints = [q.site_hint for q in queries if q.site_hint]
    for host in list(JOB_BOARD_HINTS) + [
        "site:boards.greenhouse.io", "site:jobs.lever.co", "site:jobs.ashbyhq.com",
    ]:
        assert host in hints
    five = [q.query for q in generate_queries(SearchProfile(), max_queries=5)]
    assert any("linkedin.com" in q for q in five)  # top priority inside tiny budgets


def test_search_profile_from_custom_candidate():
    """Custom target roles/locations replace hardcoded defaults."""
    candidate = {
        "target_roles": ["Java Backend Intern"],
        "target_locations": ["Chennai"],
        "skills": ["Java"],
        "learning": ["Spring Boot"],
        "status": "Fresher",
        "remote_ok": True,
    }
    profile = search_profile_from_candidate(candidate)
    assert profile.roles == ["Java Backend Intern"]
    assert profile.locations == ["Chennai"]
    assert "Java" in profile.skills and "Spring Boot" in profile.learning_skills
    queries = [q.query for q in generate_queries(profile, max_queries=4)]
    assert any("Java Backend Intern" in q for q in queries)
    assert any("Chennai" in q for q in queries)


def test_search_profile_defaults_on_empty_candidate():
    """Empty candidate facets fall back to module defaults (never zero queries)."""
    profile = search_profile_from_candidate({})
    assert profile.roles == list(DEFAULT_ROLES)
    assert profile.locations == list(DEFAULT_LOCATIONS)
    assert profile.experience_level == "Fresher"


def test_load_search_profile_offline_fallback(monkeypatch):
    """No database -> defaults (discovery stays healthy offline)."""
    from worker.db import client as db_client

    monkeypatch.setattr(db_client, "is_configured", lambda: False)
    assert load_search_profile().roles == list(DEFAULT_ROLES)


def test_load_search_profile_uses_database_candidate(monkeypatch):
    """Configured database -> candidate roles drive the search profile."""
    from worker.db import client as db_client
    from worker.db import profile_repository as profiles

    monkeypatch.setattr(db_client, "is_configured", lambda: True)
    monkeypatch.setattr(
        profiles, "load_candidate",
        lambda profile_id=None: {
            "profile_id": "p1", "target_roles": ["Java Backend Intern"],
            "target_locations": ["Chennai"], "skills": [], "learning": [],
            "status": "Fresher", "remote_ok": True,
        },
    )
    assert load_search_profile().roles == ["Java Backend Intern"]


def test_load_search_profile_never_raises(monkeypatch):
    """Any repository failure -> defaults (no crash in discovery)."""
    from worker.db import client as db_client
    from worker.db import profile_repository as profiles

    monkeypatch.setattr(db_client, "is_configured", lambda: True)

    def _boom(profile_id=None):
        raise RuntimeError("conn refused")

    monkeypatch.setattr(profiles, "load_candidate", _boom)
    assert load_search_profile().roles == list(DEFAULT_ROLES)

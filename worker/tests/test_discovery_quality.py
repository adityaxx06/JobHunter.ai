"""Phase 7A.1 discovery-quality tests. Fully offline — no Tavily/Gemini/ATS/DB.

Covers: profile-differentiated queries (A/B), source priority under tight
budgets, site-query locations, URL-first preservation, canonical dedup,
conservative junk filtering, and prefilter->Gemini discipline for
aggregator-sourced discoveries.
"""

import pytest

from worker.models.search import SearchResult
from worker.pipelines.search_pipeline import run_search_discovery
from worker.search import classifier
from worker.search.base import SearchProvider
from worker.search.classifier import classify_results, classify_url, is_junk_url
from worker.search.query_generator import (
    SearchProfile,
    generate_queries,
    generate_site_queries,
    search_profile_from_candidate,
)


def _candidate(role, location):
    return {
        "target_roles": [role],
        "target_locations": [location],
        "skills": ["Java"],
        "learning": [],
        "status": "Fresher",
        "remote_ok": True,
    }


def _hit(url, title="Java Backend Intern", snippet="freshers welcome"):
    return SearchResult(title=title, url=url, snippet=snippet, source_name="fake-search")


# --- Goal 2/3, Tests 1-2: profile-differentiated queries -------------------------------


def test_two_profiles_produce_materially_different_queries():
    a = [q.query for q in generate_queries(
        search_profile_from_candidate(_candidate("Java Backend Intern", "Chennai")), max_queries=10)]
    b = [q.query for q in generate_queries(
        search_profile_from_candidate(_candidate("Python Developer Intern", "Bangalore")), max_queries=10)]
    assert any("Java Backend Intern" in q for q in a)
    assert any("Chennai" in q for q in a)
    assert any("Python Developer Intern" in q for q in b)
    assert any("Bangalore" in q for q in b)
    assert not any("Python Developer Intern" in q or "Bangalore" in q for q in a)
    assert not any("Java Backend Intern" in q or "Chennai" in q for q in b)
    assert set(a) != set(b)


def test_site_queries_carry_profile_location():
    queries = generate_site_queries(["Java Backend Intern"], max_queries=3, location="Chennai")
    assert queries[0].query == 'site:boards.greenhouse.io "Java Backend Intern" Chennai'
    blended = [q.query for q in generate_queries(
        search_profile_from_candidate(_candidate("Java Backend Intern", "Chennai")), max_queries=10)]
    assert any("Chennai" in q and q.startswith("site:") for q in blended)


def test_site_query_location_optional_preserves_legacy_strings():
    queries = generate_site_queries(["Java Developer"], max_queries=1)
    assert queries[0].query == 'site:boards.greenhouse.io "Java Developer Intern"'


# --- Phase 7A.1.1: qualifier-dedup (no "Intern Intern") ---------------------------------


def _queries_for_role(role: str, max_queries: int = 30) -> list:
    from worker.search.query_generator import search_profile_from_candidate

    profile = search_profile_from_candidate({
        "target_roles": [role], "target_locations": ["Chennai"],
        "skills": [], "learning": [], "status": "Fresher", "remote_ok": True,
    })
    return [q.query for q in generate_queries(profile, max_queries=max_queries)]


def test_intern_role_not_duplicated():
    queries = _queries_for_role("Java Backend Intern")
    assert not any("Intern Intern" in q or "intern intern" in q.lower() for q in queries)
    assert any("Java Backend Intern" in q for q in queries)


def test_internship_role_not_duplicated():
    queries = _queries_for_role("Python Developer Internship")
    assert not any("Internship Internship" in q for q in queries)
    assert any("Python Developer Internship" in q for q in queries)


def test_fresher_role_not_duplicated():
    queries = _queries_for_role("Java Developer Fresher")
    assert not any("Fresher Fresher" in q for q in queries)
    assert any("Java Developer Fresher" in q for q in queries)


def test_plain_role_keeps_existing_intern_behavior():
    queries = _queries_for_role("Python Developer")
    assert any(q == '"Python Developer intern" India' for q in queries)
    default_five = [q.query for q in generate_queries(SearchProfile(), max_queries=5)]
    assert '"Software Engineer intern" India' in default_five  # untouched default role


def test_source_queries_free_of_duplicated_qualifier():
    queries = _queries_for_role("Java Backend Intern", max_queries=10)
    sites = [q for q in queries if q.startswith("site:")]
    assert any("linkedin.com" in q for q in sites)
    assert any("internshala.com" in q for q in sites)
    assert any("indeed.com" in q for q in sites)
    assert not any("Intern Intern" in q for q in sites)


# --- Goal 4, Test 3: source priority under tight budgets ---------------------------------


def test_top_priority_sources_survive_tight_budgets():
    five = [q.query for q in generate_queries(SearchProfile(), max_queries=5)]
    assert any("linkedin.com" in q for q in five)
    assert any("internshala.com" in q for q in five)
    three = [q.query for q in generate_queries(SearchProfile(), max_queries=3)]
    assert any("linkedin.com" in q for q in three)
    ten = [q.query for q in generate_queries(SearchProfile(), max_queries=10)]
    assert any("indeed.com" in q for q in ten)
    # ATS still represented at wider budgets (mixture, not exclusion).
    thirty = [q.query for q in generate_queries(SearchProfile(), max_queries=30)]
    assert any("boards.greenhouse.io" in q for q in thirty)
    assert any("jobs.lever.co" in q for q in thirty)
    assert any("jobs.ashbyhq.com" in q for q in thirty)


# --- Goal 5: URL-first preservation (mocked, no fetching) ----------------------------------


def test_aggregator_results_preserved_as_targets():
    results = [
        _hit("https://www.linkedin.com/jobs/view/123456", "Software Developer Intern"),
        _hit("https://internshala.com/internship/detail/java-dev-999", "Java Intern"),
        _hit("https://www.indeed.com/viewjob?jk=abc123", "Backend Intern"),
    ]
    targets = classify_results(results)
    assert len(targets) == 3
    for target, original in zip(targets, results):
        assert target.url == original.url  # original URL is sacred
        assert target.title == original.title
        assert target.snippet == original.snippet


# --- Goals 6-7, Tests 4-5: canonical dedup + junk filtering ---------------------------------


class _Dupes(SearchProvider):
    """Same job through tracking/fragment/case variants."""

    provider_name = "dupes"

    def search(self, query: str, max_results: int = 20):
        base = "https://www.linkedin.com/jobs/view/123456"
        return [
            _hit(base),
            _hit(base + "?utm_source=x&utm_medium=y"),
            _hit(base + "#apply"),
            _hit("https://www.linkedin.com/jobs/view/123456/"),
            _hit("https://WWW.LINKEDIN.COM/jobs/view/123456"),
        ]


def test_tracking_and_fragment_variants_deduplicate():
    result = run_search_discovery(SearchProfile(), provider=_Dupes(), max_queries=2)
    assert result.results_found == 10  # raw hits counted
    assert result.targets_found == 1  # one canonical target


def test_obvious_junk_urls_rejected():
    junk = [
        "https://www.linkedin.com/company/acme",
        "https://www.linkedin.com/in/john-doe",
        "https://www.linkedin.com/posts/some-post-123",
        "https://www.linkedin.com/feed/",
        "https://www.linkedin.com/learning/courses/python",
        "https://internshala.com/blog/how-to-apply",
        "https://www.indeed.com/companies/acme",
        "https://www.indeed.com/career-advice/finding-a-job",
        "https://www.indeed.com/hire/",
    ]
    for url in junk:
        assert is_junk_url(url) is True, url
    assert classify_results([_hit(url) for url in junk]) == []


def test_legitimate_job_urls_never_junk():
    legit = [
        "https://www.linkedin.com/jobs/view/123456",
        "https://www.linkedin.com/jobs/search/?keywords=java",
        "https://in.linkedin.com/jobs/view/999",
        "https://internshala.com/internship/detail/java-dev-999",
        "https://internshala.com/internships/software-development-internship",
        "https://www.indeed.com/viewjob?jk=abc123",
        "https://boards.greenhouse.io/acme/jobs/1",
        "https://jobs.lever.co/acme/abc",
        "https://jobs.ashbyhq.com/acme/def",
        "https://example.com/careers/backend-dev",
        "https://example.com/blog/internships",
        "not a url",
        "",
        None,
    ]
    for url in legit:
        assert is_junk_url(url) is False, url
    targets = classify_results([_hit(url if isinstance(url, str) else "") for url in legit if url])
    assert len(targets) == len([u for u in legit if u])


def test_junk_removed_counter_tracks_dropped_results():
    class _Mixed(SearchProvider):
        provider_name = "mixed"

        def search(self, query: str, max_results: int = 20):
            return [
                _hit("https://boards.greenhouse.io/acme/jobs/1", "Java Intern"),
                _hit("https://www.linkedin.com/company/acme", "Acme on LinkedIn"),
                _hit("https://www.linkedin.com/in/jane-doe", "Jane Doe"),
                _hit("https://www.indeed.com/career-advice/guides", "Career guide"),
            ]

    result = run_search_discovery(SearchProfile(), provider=_Mixed(), max_queries=1)
    assert result.results_found == 4
    assert result.targets_found == 1
    assert result.junk_removed == 3
    assert result.summary()["junk_removed"] == 3


# --- Goals 8-9, Tests 6-7: prefilter discipline for aggregator discoveries ------------------


def test_irrelevant_aggregator_discovery_never_reaches_gemini(monkeypatch):
    from worker.tests.test_intelligence_pipeline import (
        FakeDB,
        FakeGemini,
        _db_job,
        _install,
        _intel,
        _src,
    )
    from worker.pipelines import intelligence_pipeline as pipe

    sales = _db_job("job-9", title="Sales Executive", description="Field sales.",
                    apply_url="https://www.linkedin.com/jobs/view/999")
    intern = _db_job("job-1", apply_url="https://www.indeed.com/viewjob?jk=abc")
    fake = FakeDB(jobs=[sales, intern], sources=[_src("job-9"), _src("job-1")])
    _install(monkeypatch, fake)
    monkeypatch.setenv("AI_ENABLED", "true")
    gemini = FakeGemini([_intel()])
    result = pipe.run_intelligence(provider=gemini)
    assert gemini.calls == 1  # only the eligible intern, never the sales role
    assert result.jobs_rejected_by_rules == 1 and result.matches_saved == 1


# --- Goal 10, Test 8: ranking source-agnostic -------------------------------------------------


def test_ranking_consumes_aggregator_sourced_match(monkeypatch):
    from worker.pipelines import ranking_pipeline as ranking
    from worker.tests.test_ranking_pipeline import FakeDB as RankingFakeDB, _install, _match_row

    fake = RankingFakeDB(rows=[_match_row("job-1", 90, 92, "APPLY",
                                          apply_url="https://www.linkedin.com/jobs/view/123")])
    _install(monkeypatch, fake)
    result = ranking.rank_jobs_for_profile(limit=5)
    assert [j.job_id for j in result.ranked_jobs] == ["job-1"]
    assert result.ranked_jobs[0].apply_url == "https://www.linkedin.com/jobs/view/123"

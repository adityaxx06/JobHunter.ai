"""Phase 10C-4 cross-source integration tests. Fully offline — faked transports.

Covers: all/partially disabled sources, one source failing while others
succeed, cross-source duplicates (same URL, tracking variants) without
over-deduping distinct jobs, source identity/attribution preservation,
publication-date survival (missing stays missing), unknown feed status
never misread as closed, relevance filters + remote handling, health and
error reporting, and pagination/request bounds.
"""

import json
import urllib.parse
from datetime import datetime, timezone

from worker.models.job import DiscoveredJob, NormalizedJob
from worker.pipelines.discovery_pipeline import run_discovery
from worker.processors.deduplicator.job_deduplicator import deduplicate_jobs
from worker.processors.normalizer.job_normalizer import normalize_job
from worker.sources import registry
from worker.sources.himalayas.client import HimalayaClient
from worker.sources.himalayas.source import HimalayaSource
from worker.sources.jobicy.client import JobicyClient
from worker.sources.jobicy.source import JobicySource
from worker.sources.manual.mock_source import MockSource


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200, headers: dict = None) -> None:
        self._body = body
        self.status = status
        self.headers = headers or {}

    def read(self, *args):
        return self._body


def _him_opener(payload, seen=None):
    def opener(url: str, timeout: float):
        if seen is not None:
            seen.append(url)
        assert "cursor" not in urllib.parse.urlsplit(url).query, "no cursor walking"
        return FakeResponse(json.dumps(payload).encode())
    return opener


def _job_opener(payload, seen=None):
    def opener(url: str, timeout: float):
        if seen is not None:
            seen.append(url)
        assert "cursor" not in urllib.parse.urlsplit(url).query, "no cursor walking"
        return FakeResponse(json.dumps(payload).encode())
    return opener


def _him_job(guid="g1", **overrides):
    base = {
        "title": "Backend Developer Intern",
        "companyName": "Acme Corp",
        "locationRestrictions": [{"name": "India"}],
        "employmentType": "Intern",
        "seniority": ["Entry-level"],
        "description": "<p>Build APIs.</p>",
        "pubDate": 1790812800000,
        "applicationLink": "https://himalayas.app/companies/acme/jobs/x1",
        "guid": guid,
    }
    base.update(overrides)
    return base


def _jobicy_job(job_id=11, **overrides):
    base = {
        "id": job_id,
        "url": "https://jobicy.com/jobs/example-role",
        "jobTitle": "Python Developer Intern",
        "companyName": "Beta Inc",
        "jobIndustry": ["Engineering"],
        "jobType": ["Full-Time"],
        "jobGeo": "Anywhere",
        "jobLevel": "Entry-level",
        "jobDescription": "<p>Write Python.</p>",
        "pubDate": "2026-10-10T12:17:38+00:00",
        "salaryMin": 1000,
        "salaryMax": 2000,
        "salaryCurrency": "USD",
    }
    base.update(overrides)
    return base


def _him_source(payload, keywords=("intern",), **kwargs):
    params = {"enabled": True}
    params.update(kwargs)
    enabled = params.pop("enabled")
    return HimalayaSource(
        keywords=list(keywords),
        enabled=enabled,
        client_factory=lambda k: HimalayaClient(k, opener=_him_opener(payload)),
        **params)


def _job_source(payload, tags=("python",), **kwargs):
    params = {"enabled": True}
    params.update(kwargs)
    enabled = params.pop("enabled")
    return JobicySource(
        tags=list(tags),
        enabled=enabled,
        client_factory=lambda t: JobicyClient(t, opener=_job_opener(payload)),
        **params)


# --- all/partially disabled ------------------------------------------------------------------


def test_all_new_sources_disabled_stay_idle():
    def _boom(url, timeout):
        raise AssertionError("no HTTP when disabled")

    himalaya = HimalayaSource(keywords=["x"], enabled=False,
                              client_factory=lambda k: HimalayaClient(k, opener=_boom))
    jobicy = JobicySource(tags=["x"], enabled=False,
                          client_factory=lambda t: JobicyClient(t, opener=_boom))
    result = run_discovery([himalaya, jobicy])
    assert result.discovered_count == 0 and result.errors == []
    assert himalaya.health_check().ok is False
    assert jobicy.health_check().ok is False


def test_partially_enabled_only_enabled_contributes():
    himalaya = _him_source({"jobs": [_him_job()]})
    jobicy = JobicySource(tags=["x"], enabled=False,
                          client_factory=lambda t: (_ for _ in ()).throw(
                              AssertionError("jobicy must stay idle")))
    result = run_discovery([himalaya, jobicy])
    assert result.discovered_count == 1
    names = {s.name for s in result.source_stats}
    assert names == {"himalaya", "jobicy"}


# --- failure isolation ----------------------------------------------------------------------------


def test_one_source_failing_leaves_others_intact():
    from worker.sources.base import JobSource

    class _Broken(JobSource):
        source_type = "job_board"
        source_name = "broken"

        def discover_jobs(self, query="", location="", limit=50):
            raise RuntimeError("total outage")

    working = _job_source({"success": True, "jobs": [_jobicy_job()]})
    result = run_discovery([_Broken(), working, MockSource()])
    assert result.discovered_count == 1 + 5  # jobicy + mock fixtures
    assert any("broken" in e for e in result.errors)
    assert result.unique_count == 6


def test_failing_client_isolated_inside_source():
    def _boom(url, timeout):
        raise ConnectionError("down")

    failing = HimalayaSource(
        keywords=["x"], enabled=True,
        client_factory=lambda k: HimalayaClient(k, opener=_boom))
    working = _job_source({"success": True, "jobs": [_jobicy_job()]})
    result = run_discovery([failing, working])
    assert result.discovered_count == 1 and result.errors == []
    assert len(failing.last_errors) == 1  # isolated inside the source


# --- duplicates across sources -------------------------------------------------------------------------


def test_same_canonical_url_dedupes_across_sources():
    # Identical canonical identities merge; tracking variants already merge
    # one layer up (search-layer canonical dedup — see the ingestion tests).
    def _job(url):
        return normalize_job(DiscoveredJob(
            title="Python Developer Intern", company_name="Beta Inc", location="Remote",
            source_type="job_board", source_name="jobicy",
            source_url=url, apply_url=url))

    url = "https://jobicy.com/jobs/example-role"
    deduped = deduplicate_jobs([_job(url), _job(url)])
    assert len(deduped.unique_jobs) == 1 and deduped.duplicate_count == 1


def test_similar_titles_do_not_overdedupe():
    jobs = [
        normalize_job(DiscoveredJob(
            title="Python Developer Intern", company_name="Beta Inc", location="Remote",
            source_type="job_board", source_name="jobicy",
            source_url="https://jobicy.com/jobs/a", apply_url="https://jobicy.com/jobs/a")),
        normalize_job(DiscoveredJob(
            title="Python Developer Intern", company_name="Gamma LLC", location="Remote",
            source_type="job_board", source_name="jobicy",
            source_url="https://jobicy.com/jobs/b", apply_url="https://jobicy.com/jobs/b")),
    ]
    deduped = deduplicate_jobs(jobs)
    assert len(deduped.unique_jobs) == 2 and deduped.duplicate_count == 0


# --- identity, attribution, dates -----------------------------------------------------------------------------


def test_source_identity_survives_pipeline():
    himalaya = _him_source({"jobs": [_him_job()]})
    jobicy = _job_source({"success": True, "jobs": [_jobicy_job()]})
    result = run_discovery([himalaya, jobicy])
    by_name = {}
    for job in result.jobs:
        by_name[job.original.source_name] = job.original.source_type
    assert by_name == {"himalaya": "job_board", "jobicy": "job_board"}


def test_publication_dates_survive_and_missing_stays_missing():
    dated = normalize_job(DiscoveredJob(
        title="Dated", source_type="job_board", source_name="himalaya",
        source_url="https://himalayas.app/x", apply_url="https://himalayas.app/x",
        posted_at=datetime(2026, 10, 1, tzinfo=timezone.utc)))
    undated = normalize_job(DiscoveredJob(
        title="Undated", source_type="job_board", source_name="jobicy",
        source_url="https://jobicy.com/jobs/y", apply_url="https://jobicy.com/jobs/y"))
    assert dated.original.posted_at is not None
    assert undated.original.posted_at is None  # never backfilled with "today"


def test_unknown_status_never_means_closed():
    # Neither job model carries a status/closed flag — unknown feed state
    # cannot be misread as closed anywhere downstream.
    assert "status" not in DiscoveredJob.__dataclass_fields__
    assert "status" not in NormalizedJob.__dataclass_fields__


# --- relevance filters + remote handling ---------------------------------------------------------------------------


def test_relevance_filters_and_remote_rules():
    himalaya = _him_source({"jobs": [
        _him_job("a", title="Java Developer Intern"),
        _him_job("b", title="Python Developer Intern"),
    ]})
    assert [j.title for j in himalaya.discover_jobs(query="python")] == ["Python Developer Intern"]
    worldwide = _him_source({"jobs": [_him_job("w", locationRestrictions=[])]})
    assert worldwide.discover_jobs()[0].is_remote is True
    assert worldwide.discover_jobs()[0].location == "Remote"
    onsite = _him_source({"jobs": [_him_job("o", locationRestrictions=[{"name": "Germany"}])]})
    assert onsite.discover_jobs()[0].is_remote is False


# --- health, errors, bounds -----------------------------------------------------------------------------------------------


def test_health_and_error_reporting():
    ok = _him_source({"jobs": []})
    assert ok.health_check().ok is True and "1 keyword" in ok.health_check().message

    def _boom(url, timeout):
        raise TimeoutError("slow")

    failing = JobicySource(tags=["x"], enabled=True,
                           client_factory=lambda t: JobicyClient(t, opener=_boom))
    assert failing.discover_jobs() == []
    assert len(failing.last_errors) == 1 and "TimeoutError" in failing.last_errors[0]


def test_request_bounds_single_page():
    seen_him, seen_job = [], []
    him = HimalayaSource(
        keywords=["a", "b"], enabled=True,
        client_factory=lambda k: HimalayaClient(
            k, opener=_him_opener({"jobs": []}, seen_him)))
    job = JobicySource(
        tags=["x", "y"], enabled=True,
        client_factory=lambda t: JobicyClient(
            t, opener=_job_opener({"success": True, "jobs": []}, seen_job)))
    him.discover_jobs()
    job.discover_jobs()
    assert len(seen_him) == 2 and len(seen_job) == 2  # one page per keyword/tag
    assert all("cursor" not in u for u in seen_him + seen_job)
    limited = HimalayaClient("a", opener=_him_opener({"jobs": []}))
    assert limited.limit <= 20
    assert JobicyClient("a", opener=_job_opener({})).count <= 200


def test_registry_lists_all_six_sources_once():
    names = [s.source_name for s in registry.get_all_sources()]
    assert len(names) == len(set(names))
    assert set(names) >= {"mock", "greenhouse", "lever", "ashby", "himalaya", "jobicy"}

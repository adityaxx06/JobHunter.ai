"""Phase 10C-3 Jobicy tests. Fully offline — HTTP is faked, never live.

Fixtures mirror Jobicy's documented Jobs API shape
(GET /api/v2/remote-jobs — ``{"success": true, "jobs": [...]}``, no auth).
"""

import json
import socket
import urllib.error
import urllib.parse

import pytest

from worker.models.job import DiscoveredJob
from worker.pipelines.discovery_pipeline import run_discovery
from worker.sources import registry
from worker.sources.himalayas.source import HimalayaSource
from worker.sources.jobicy import config as jobicy_config
from worker.sources.jobicy.client import (
    BadRequestError,
    JobicyClient,
    JobicyError,
    NetworkError,
    RateLimitedError,
    ServerError,
)
from worker.sources.jobicy.parser import (
    SOURCE_NAME,
    SOURCE_TYPE,
    parse_job,
    parse_search_jobs,
)
from worker.sources.jobicy.source import JobicySource
from worker.sources.html_text import html_to_text
from worker.sources.manual.mock_source import MockSource


def _item(job_id=123456, **overrides):
    base = {
        "id": job_id,
        "url": "https://jobicy.com/jobs/example-role",
        "jobTitle": "Backend Developer Intern",
        "companyName": "Acme Corp",
        "companyLogo": "https://example.com/logo.png",
        "jobIndustry": ["Engineering"],
        "jobType": ["Full-Time", "Internship"],
        "jobGeo": "Anywhere",
        "jobLevel": "Entry-level",
        "jobExcerpt": "Short summary.",
        "jobDescription": "<p>Build <strong>APIs</strong> with Python.</p>",
        "pubDate": "2026-10-10T12:17:38+00:00",
        "salaryMin": 1000,
        "salaryMax": 2000,
        "salaryCurrency": "USD",
        "salaryPeriod": "yearly",
    }
    base.update(overrides)
    return base


class FakeResponse:
    """Minimal urlopen stand-in: status + headers + body."""

    def __init__(self, body: bytes, status: int = 200, headers: dict = None) -> None:
        self._body = body
        self.status = status
        self.headers = headers or {}

    def read(self, *args):
        return self._body


def _opener_for(mapping):
    """Route by tag param: value | exception | (status, headers, body)."""

    def opener(url: str, timeout: float):
        tag = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get("tag", [""])[0]
        behavior = mapping[tag]
        if isinstance(behavior, BaseException):
            raise behavior
        status, headers, body = behavior
        return FakeResponse(body, status=status, headers=headers)

    return opener


def _json_body(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _source(tags, mapping, **kwargs):
    return JobicySource(
        tags=list(tags),
        enabled=True,
        client_factory=lambda t: JobicyClient(t, opener=_opener_for(mapping)),
        **kwargs,
    )


# --- 1/2. successful response: single + multiple jobs --------------------------


def test_client_fetches_listing_object():
    opener = _opener_for({"python": (200, {}, _json_body({"success": True, "jobs": [_item()]}))})
    payload = JobicyClient("python", opener=opener).fetch_jobs()
    assert len(payload["jobs"]) == 1


def test_client_multiple_jobs_and_query_params():
    seen = {}

    def opener(url: str, timeout: float):
        seen["url"] = url
        return FakeResponse(_json_body({"success": True, "jobs": [_item(1), _item(2)]}))

    client = JobicyClient("python", geo="usa", industry="engineering", opener=opener)
    assert len(client.fetch_jobs()["jobs"]) == 2
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(seen["url"]).query)
    assert query["tag"] == ["python"] and query["geo"] == ["usa"]
    assert query["industry"] == ["engineering"] and int(query["count"][0]) <= 200


# --- 3. empty response -----------------------------------------------------------


def test_empty_search_returns_no_jobs():
    source = _source(["python"], {"python": (200, {}, _json_body({"success": True, "jobs": []}))})
    assert source.discover_jobs() == []
    assert source.last_errors == []


# --- 4/5/6/7/8. error taxonomy -----------------------------------------------------


def test_error_taxonomy():
    cases = [
        ("bad", (400, {}, b"bad filters"), BadRequestError),
        ("limited", (429, {"Retry-After": "7"}, b"slow"), RateLimitedError),
        ("broken", (500, {}, b"oops"), ServerError),
        ("down", urllib.error.URLError("dns"), NetworkError),
        ("slow", socket.timeout("x"), NetworkError),
    ]
    for tag, behavior, kind in cases:
        with pytest.raises(kind):
            JobicyClient(tag, opener=_opener_for({tag: behavior})).fetch_jobs()
    limited = _opener_for({"q": (429, {"Retry-After": "7"}, b"slow")})
    try:
        JobicyClient("q", opener=limited).fetch_jobs()
        raise AssertionError("must raise")
    except RateLimitedError as exc:
        assert exc.retry_after == 7


def test_api_failure_flag_and_malformed_shapes_rejected():
    opener = _opener_for({"q": (200, {}, _json_body({"success": False, "error": "nope"}))})
    with pytest.raises(JobicyError):
        JobicyClient("q", opener=opener).fetch_jobs()
    opener = _opener_for({"q": (200, {}, b"not json")})
    with pytest.raises(JobicyError):
        JobicyClient("q", opener=opener).fetch_jobs()
    opener = _opener_for({"q": (200, {}, _json_body(["a", "list"]))})
    with pytest.raises(JobicyError):
        JobicyClient("q", opener=opener).fetch_jobs()
    opener = _opener_for({"q": (200, {}, _json_body({"jobs": "junk"}))})
    assert parse_search_jobs(JobicyClient("q", opener=opener).fetch_jobs()) == []


def test_unexpected_transport_wrapped_as_network():
    def opener(url: str, timeout: float):
        raise KeyError("boom")

    with pytest.raises(NetworkError):
        JobicyClient("q", opener=opener).fetch_jobs()


# --- 9. multi-tag partial failure ---------------------------------------------------


def test_tag_failure_does_not_stop_remaining():
    mapping = {
        "a": (200, {}, _json_body({"success": True, "jobs": [_item(1)]})),
        "b": urllib.error.URLError("dns"),
        "c": (200, {}, _json_body({"success": True, "jobs": [_item(2), _item(3)]})),
    }
    source = _source(["a", "b", "c"], mapping)
    assert len(source.discover_jobs()) == 3
    assert len(source.last_errors) == 1 and "tag 'b'" in source.last_errors[0]


# --- 10/11. HTML cleaning ------------------------------------------------------------


def test_description_html_cleaned():
    job = parse_job(_item(jobDescription="<p>Hi</p><script>evil()</script><p>Bye</p>"))
    assert job.description == "Hi\nBye"
    assert html_to_text("<p>A &amp; B</p>") == "A & B"


# --- 12. mapping ----------------------------------------------------------------------


def test_job_mapping_uses_documented_fields():
    job = parse_job(_item())
    assert isinstance(job, DiscoveredJob)
    assert (job.title, job.company_name) == ("Backend Developer Intern", "Acme Corp")
    assert job.company_domain == ""
    assert job.location == "Anywhere" and job.is_remote is True
    assert job.source_type == SOURCE_TYPE == "job_board"
    assert job.source_name == SOURCE_NAME == "jobicy"
    assert job.apply_url == job.source_url == "https://jobicy.com/jobs/example-role"
    assert job.external_id == "123456"
    assert (job.salary_min, job.salary_max, job.salary_currency) == (1000, 2000, "USD")
    assert job.employment_type == "Full-Time, Internship"
    assert job.experience_level == "Entry-level"
    assert job.description == "Build APIs with Python."
    assert job.raw_data["id"] == 123456


def test_empty_geo_means_remote():
    job = parse_job(_item(jobGeo=""))
    assert (job.location, job.is_remote) == ("Remote", True)


# --- 13. publication timestamp --------------------------------------------------------------


def test_pubdate_iso_string():
    job = parse_job(_item(pubDate="2026-10-10T12:17:38+00:00"))
    assert job.posted_at is not None
    assert (job.posted_at.year, job.posted_at.month, job.posted_at.day) == (2026, 10, 10)
    assert job.posted_at.tzinfo is not None
    assert parse_job(_item(pubDate="2026-10-10T12:17:38Z")).posted_at == job.posted_at


def test_invalid_timestamps_become_none_not_today():
    for bad in (None, "", "not-a-date", "2026-13-45", 1790812800000, True):
        assert parse_job(_item(pubDate=bad)).posted_at is None, bad


# --- 14. URL validation ---------------------------------------------------------------------------


def test_missing_or_bad_links_skipped():
    with pytest.raises(ValueError):
        parse_job(_item(url=""))
    with pytest.raises(ValueError):
        parse_job(_item(url="ftp://files.example/x"))
    with pytest.raises(ValueError):
        parse_job(_item(jobTitle=""))
    with pytest.raises(ValueError):
        parse_job("junk")
    jobs = parse_search_jobs({"jobs": [_item(1), _item(2, url=""), "junk", None]})
    assert [j.external_id for j in jobs] == ["1"]


# --- 15. salary/employment/experience mapping -----------------------------------------------------------------


def test_salary_employment_experience_mapping():
    job = parse_job(_item())
    assert job.employment_type == "Full-Time, Internship"
    assert parse_job(_item(salaryMin=10.5, salaryMax="x")).salary_min is None
    assert parse_job(_item(salaryMin=10.5, salaryMax="x")).salary_max is None
    assert parse_job(_item(jobType=["Contract"])).employment_type == "Contract"
    assert parse_job(_item(jobType="oops")).employment_type == "oops"


# --- 16. missing optionals -----------------------------------------------------------------------------


def test_missing_optional_fields_default_safely():
    job = parse_job({"jobTitle": "X", "url": "https://jobicy.com/jobs/x"})
    assert job.company_name == "" and job.location == "Remote" and job.is_remote is True
    assert job.description == "" and job.posted_at is None
    assert job.salary_min is None and job.salary_currency == "INR"
    assert job.experience_level == "" and job.external_id == ""
    assert parse_search_jobs({}) == [] and parse_search_jobs({"jobs": "junk"}) == []


# --- 17. client-side filters -------------------------------------------------------------------------------


def test_query_and_limit_filters():
    mapping = {"python": (200, {}, _json_body({"success": True, "jobs": [
        _item(1, jobTitle="Java Developer Intern"),
        _item(2, jobTitle="Python Developer Intern"),
    ]}))}
    source = _source(["python"], mapping)
    assert [j.title for j in source.discover_jobs(query="python")] == ["Python Developer Intern"]
    assert [j.external_id for j in source.discover_jobs(limit=1)] == ["1"]


# --- 18. registry integration -------------------------------------------------------------------------------------


def test_registry_includes_jobicy():
    jobicy = registry.get_source("jobicy")
    assert isinstance(jobicy, JobicySource)
    assert jobicy.source_type == "job_board"
    assert {s.source_name for s in registry.get_all_sources()} >= {
        "mock", "greenhouse", "lever", "ashby", "himalaya", "jobicy"}
    assert isinstance(registry.get_source("himalaya"), HimalayaSource)


# --- 19. pipeline integration ------------------------------------------------------------------------------------------


def test_pipeline_with_mock_and_jobicy():
    jobicy = _source(["python"], {"python": (200, {}, _json_body(
        {"success": True, "jobs": [_item(9, jobTitle="Python Developer Intern")]}))})
    result = run_discovery([MockSource(), jobicy])
    assert result.discovered_count == 6 and result.normalized_count == 6 and result.unique_count == 6
    by_source = {s.name: s for s in result.source_stats}
    assert by_source["mock"].discovered == 5 and by_source["jobicy"].discovered == 1
    jobicy_jobs = [j for j in result.jobs if j.original.source_name == "jobicy"]
    assert len(jobicy_jobs) == 1 and jobicy_jobs[0].normalized_title == "python developer intern"


# --- 20/21. configuration parsing + disabled -------------------------------------------------------------------------------


def test_config_defaults_disabled_and_parsing():
    assert jobicy_config.is_enabled({}) is False
    assert jobicy_config.is_enabled({"JOBICY_ENABLED": "yes"}) is True
    assert jobicy_config.get_tags({}) == []
    assert jobicy_config.get_tags({"JOBICY_TAGS": " Python ;intern,python;; "}) == ["Python", "intern"]
    assert jobicy_config.get_geo({}) == ""
    assert jobicy_config.get_geo({"JOBICY_GEO": " usa "}) == "usa"
    assert jobicy_config.get_industry({"JOBICY_INDUSTRY": "engineering"}) == "engineering"
    assert jobicy_config.get_timeout({}) == 10.0
    assert jobicy_config.get_timeout({"JOBICY_TIMEOUT": "bogus"}) == 10.0


def test_config_tag_capping():
    tags = [f"t{i}" for i in range(8)] + ["t0", "", "  "]
    assert jobicy_config.get_tags({"JOBICY_TAGS": ";".join(tags)}) == [f"t{i}" for i in range(5)]


def test_disabled_or_unconfigured_returns_empty_without_network():
    def _boom(url, timeout):
        raise AssertionError("no HTTP when disabled")

    factory = lambda t: JobicyClient(t, opener=_boom)
    assert JobicySource(tags=[], enabled=False, client_factory=factory).discover_jobs() == []
    assert JobicySource(tags=["x"], enabled=False, client_factory=factory).discover_jobs() == []
    assert JobicySource(enabled=False).health_check().ok is False
    assert JobicySource(tags=[], enabled=True).health_check().ok is False

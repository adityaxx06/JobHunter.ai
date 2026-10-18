"""Phase 10C-2 Himalayas tests. Fully offline — HTTP is faked, never live.

Fixtures mirror Himalayas' documented Jobs API shape
(GET /jobs/api/search — ``{"jobs": [...]}``, no auth).
"""

import json
import socket
import urllib.error
import urllib.parse

import pytest

from worker.models.job import DiscoveredJob
from worker.pipelines.discovery_pipeline import run_discovery
from worker.sources import registry
from worker.sources.greenhouse.source import GreenhouseSource
from worker.sources.himalayas import config as himalaya_config
from worker.sources.himalayas.client import (
    BadRequestError,
    HimalayaClient,
    HimalayaError,
    NetworkError,
    RateLimitedError,
    ServerError,
)
from worker.sources.himalayas.parser import (
    SOURCE_NAME,
    SOURCE_TYPE,
    parse_job,
    parse_search_jobs,
)
from worker.sources.himalayas.source import HimalayaSource
from worker.sources.html_text import html_to_text
from worker.sources.lever.source import LeverSource
from worker.sources.manual.mock_source import MockSource


def _item(job_id="h1", **overrides):
    base = {
        "title": "Backend Developer Intern",
        "excerpt": "Remote backend internship.",
        "companyName": "Acme Corp",
        "companySlug": "acme",
        "companyLogo": "https://cdn.example/logo.png",
        "employmentType": "Intern",
        "minSalary": 1000,
        "maxSalary": 2000,
        "seniority": ["Entry-level"],
        "currency": "USD",
        "locationRestrictions": [{"alpha2": "IN", "name": "India", "slug": "india"}],
        "timezoneRestrictions": [],
        "categories": ["Engineering"],
        "parentCategories": ["Tech"],
        "description": "<p>Build <strong>APIs</strong> with Python.</p>",
        "pubDate": 1790812800000,  # epoch millis
        "expiryDate": 1793491200000,
        "applicationLink": "https://himalayas.app/jobs/backend-developer-intern-h1",
        "guid": job_id,
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
    """Route by q param: value | exception | (status, headers, body)."""

    def opener(url: str, timeout: float):
        keyword = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get("q", [""])[0]
        behavior = mapping[keyword]
        if isinstance(behavior, BaseException):
            raise behavior
        status, headers, body = behavior
        return FakeResponse(body, status=status, headers=headers)

    return opener


def _json_body(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _source(keywords, mapping, **kwargs):
    return HimalayaSource(
        keywords=list(keywords),
        enabled=True,
        client_factory=lambda k: HimalayaClient(k, opener=_opener_for(mapping)),
        **kwargs,
    )


# --- 1/2. successful response: single + multiple jobs --------------------------


def test_client_fetches_search_object():
    opener = _opener_for({"intern": (200, {}, _json_body({"jobs": [_item()]}))})
    payload = HimalayaClient("intern", opener=opener).fetch_jobs()
    assert len(payload["jobs"]) == 1


def test_client_multiple_jobs_and_query_params():
    seen = {}

    def opener(url: str, timeout: float):
        seen["url"] = url
        return FakeResponse(_json_body({"jobs": [_item("a"), _item("b")]}))

    client = HimalayaClient("intern", employment_types=["Intern"], opener=opener)
    assert len(client.fetch_jobs()["jobs"]) == 2
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(seen["url"]).query)
    assert query["q"] == ["intern"] and query["employment_type"] == ["Intern"]
    assert int(query["limit"][0]) <= 20  # documented per-request maximum


# --- 3. empty response -----------------------------------------------------------


def test_empty_search_returns_no_jobs():
    source = _source(["intern"], {"intern": (200, {}, _json_body({"jobs": []}))})
    assert source.discover_jobs() == []
    assert source.last_errors == []


# --- 4/5/6/7/8. error taxonomy -----------------------------------------------------


def test_error_taxonomy():
    cases = [
        ("bad", (400, {}, b"bad params"), BadRequestError),
        ("limited", (429, {"Retry-After": "7"}, b"slow"), RateLimitedError),
        ("broken", (500, {}, b"oops"), ServerError),
        ("down", urllib.error.URLError("dns"), NetworkError),
        ("slow", socket.timeout("x"), NetworkError),
    ]
    for keyword, behavior, kind in cases:
        with pytest.raises(kind):
            HimalayaClient(keyword, opener=_opener_for({keyword: behavior})).fetch_jobs()
    limited = _opener_for({"q": (429, {"Retry-After": "7"}, b"slow")})
    try:
        HimalayaClient("q", opener=limited).fetch_jobs()
        raise AssertionError("must raise")
    except RateLimitedError as exc:
        assert exc.retry_after == 7


def test_malformed_shapes_rejected():
    opener = _opener_for({"q": (200, {}, b"not json")})
    with pytest.raises(HimalayaError):
        HimalayaClient("q", opener=opener).fetch_jobs()
    opener = _opener_for({"q": (200, {}, _json_body(["a", "list"]))})
    with pytest.raises(HimalayaError):
        HimalayaClient("q", opener=opener).fetch_jobs()
    opener = _opener_for({"q": (200, {}, _json_body({"jobs": "junk"}))})
    assert parse_search_jobs(HimalayaClient("q", opener=opener).fetch_jobs()) == []


def test_unexpected_transport_wrapped_as_network():
    def opener(url: str, timeout: float):
        raise KeyError("boom")

    with pytest.raises(NetworkError):
        HimalayaClient("q", opener=opener).fetch_jobs()


# --- 9. multi-keyword partial failure ---------------------------------------------------


def test_keyword_failure_does_not_stop_remaining():
    mapping = {
        "a": (200, {}, _json_body({"jobs": [_item("a1")]})),
        "b": urllib.error.URLError("dns"),
        "c": (200, {}, _json_body({"jobs": [_item("c1"), _item("c2")]})),
    }
    source = _source(["a", "b", "c"], mapping)
    assert len(source.discover_jobs()) == 3
    assert len(source.last_errors) == 1 and "keyword 'b'" in source.last_errors[0]


# --- 10/11. HTML cleaning ------------------------------------------------------------


def test_description_html_cleaned():
    job = parse_job(_item(description="<p>Hi</p><script>evil()</script><p>Bye</p>"))
    assert job.description == "Hi\nBye"
    assert html_to_text("<p>A &amp; B</p>") == "A & B"


# --- 12. mapping ----------------------------------------------------------------------


def test_job_mapping_uses_documented_fields():
    job = parse_job(_item())
    assert isinstance(job, DiscoveredJob)
    assert (job.title, job.company_name) == ("Backend Developer Intern", "Acme Corp")
    assert job.company_domain == ""
    assert job.location == "India" and job.is_remote is False
    assert job.source_type == SOURCE_TYPE == "job_board"
    assert job.source_name == SOURCE_NAME == "himalaya"
    assert job.apply_url == job.source_url == "https://himalayas.app/jobs/backend-developer-intern-h1"
    assert job.external_id == "h1"
    assert (job.salary_min, job.salary_max, job.salary_currency) == (1000, 2000, "USD")
    assert job.description == "Build APIs with Python."
    assert job.raw_data["guid"] == "h1"


def test_worldwide_means_remote_and_lists_join():
    job = parse_job(_item(locationRestrictions=[]))
    assert (job.location, job.is_remote) == ("Remote", True)
    mixed = parse_job(_item(locationRestrictions=["India", {"name": "Germany"}]))
    assert mixed.location == "India, Germany" and mixed.is_remote is False


# --- 13. publication timestamp --------------------------------------------------------------


def test_pubdate_epoch_millis_and_seconds():
    job = parse_job(_item(pubDate=1790812800000))
    assert job.posted_at is not None
    assert (job.posted_at.year, job.posted_at.month, job.posted_at.day) == (2026, 10, 1)
    assert job.posted_at.tzinfo is not None
    assert parse_job(_item(pubDate=1790812800)).posted_at == job.posted_at
    assert "expiry" not in str(job.posted_at)


def test_invalid_timestamps_become_none_not_today():
    for bad in (None, "", "not-a-date", -5, 0, True, 99999999999999999):
        assert parse_job(_item(pubDate=bad)).posted_at is None, bad


# --- 14. URL validation ---------------------------------------------------------------------------


def test_missing_or_bad_links_skipped():
    with pytest.raises(ValueError):
        parse_job(_item(applicationLink=""))
    with pytest.raises(ValueError):
        parse_job(_item(applicationLink="ftp://files.example/x"))
    with pytest.raises(ValueError):
        parse_job(_item(title=""))
    with pytest.raises(ValueError):
        parse_job("junk")
    jobs = parse_search_jobs({"jobs": [_item("ok"), _item("bad", applicationLink=""), "junk", None]})
    assert [j.external_id for j in jobs] == ["ok"]


# --- 15. salary/employment/experience mapping -----------------------------------------------------------------


def test_salary_employment_experience_mapping():
    job = parse_job(_item())
    assert job.employment_type == "Intern"
    assert job.experience_level == "Entry-level"
    assert parse_job(_item(minSalary=10.5, maxSalary="x")).salary_min is None
    assert parse_job(_item(minSalary=10.5, maxSalary="x")).salary_max is None
    assert parse_job(_item(seniority="Mid-level")).experience_level == "Mid-level"
    assert parse_job(_item(seniority=["A", "B"])).experience_level == "A, B"


# --- 16. missing optionals -----------------------------------------------------------------------------


def test_missing_optional_fields_default_safely():
    job = parse_job({"title": "X", "applicationLink": "https://himalayas.app/jobs/x"})
    assert job.company_name == "" and job.location == "Remote" and job.is_remote is True
    assert job.description == "" and job.posted_at is None
    assert job.salary_min is None and job.salary_currency == "INR"
    assert parse_search_jobs({}) == [] and parse_search_jobs({"jobs": "junk"}) == []


# --- 17. client-side filters -------------------------------------------------------------------------------


def test_query_and_location_filters():
    mapping = {"python": (200, {}, _json_body({"jobs": [
        _item("a", title="Java Developer Intern"),
        _item("b", title="Python Developer Intern"),
    ]}))}
    source = _source(["python"], mapping)
    assert [j.title for j in source.discover_jobs(query="python")] == ["Python Developer Intern"]
    assert [j.external_id for j in source.discover_jobs(limit=1)] == ["a"]


# --- 18. registry integration -------------------------------------------------------------------------------------


def test_registry_includes_himalaya():
    himalaya = registry.get_source("himalaya")
    assert isinstance(himalaya, HimalayaSource)
    assert himalaya.source_type == "job_board"
    assert {s.source_name for s in registry.get_all_sources()} >= {
        "mock", "greenhouse", "lever", "ashby", "himalaya"}
    assert isinstance(registry.get_source("greenhouse"), GreenhouseSource)
    assert isinstance(registry.get_source("lever"), LeverSource)


# --- 19. pipeline integration ------------------------------------------------------------------------------------------


def test_pipeline_with_mock_and_himalaya():
    himalaya = _source(["intern"], {"intern": (200, {}, _json_body(
        {"jobs": [_item("h1", title="Python Developer Intern")]}))})
    result = run_discovery([MockSource(), himalaya])
    assert result.discovered_count == 6 and result.normalized_count == 6 and result.unique_count == 6
    by_source = {s.name: s for s in result.source_stats}
    assert by_source["mock"].discovered == 5 and by_source["himalaya"].discovered == 1
    himalaya_jobs = [j for j in result.jobs if j.original.source_name == "himalaya"]
    assert len(himalaya_jobs) == 1 and himalaya_jobs[0].normalized_title == "python developer intern"


# --- 20/21. configuration parsing + disabled -------------------------------------------------------------------------------


def test_config_defaults_disabled_and_parsing():
    assert himalaya_config.is_enabled({}) is False
    assert himalaya_config.is_enabled({"HIMALAYA_ENABLED": "yes"}) is True
    assert himalaya_config.get_keywords({}) == []
    assert himalaya_config.get_keywords({"HIMALAYA_KEYWORDS": " Intern ;python,intern;; "}) == ["Intern", "python"]
    assert himalaya_config.get_employment_types({}) == ["Intern"]
    assert himalaya_config.get_employment_types({"HIMALAYA_EMPLOYMENT_TYPES": ""}) == []
    assert himalaya_config.get_timeout({}) == 10.0
    assert himalaya_config.get_timeout({"HIMALAYA_TIMEOUT": "bogus"}) == 10.0


def test_config_keyword_capping():
    keywords = [f"k{i}" for i in range(8)] + ["k0", "", "  "]
    assert himalaya_config.get_keywords({"HIMALAYA_KEYWORDS": ";".join(keywords)}) == [f"k{i}" for i in range(5)]


def test_disabled_or_unconfigured_returns_empty_without_network():
    def _boom(url, timeout):
        raise AssertionError("no HTTP when disabled")

    factory = lambda k: HimalayaClient(k, opener=_boom)
    assert HimalayaSource(keywords=[], enabled=False, client_factory=factory).discover_jobs() == []
    assert HimalayaSource(keywords=["x"], enabled=False, client_factory=factory).discover_jobs() == []
    assert HimalayaSource(enabled=False).health_check().ok is False
    assert HimalayaSource(keywords=[], enabled=True).health_check().ok is False

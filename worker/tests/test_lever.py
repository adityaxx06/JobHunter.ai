"""Phase 4.2B Lever tests. Fully offline — HTTP is faked, never live."""

import json
import socket
import urllib.error

import pytest

from worker.models.job import DiscoveredJob
from worker.pipelines.discovery_pipeline import run_discovery
from worker.sources import registry
from worker.sources.greenhouse.source import GreenhouseSource
from worker.sources.html_text import html_to_text
from worker.sources.lever import config as lever_config
from worker.sources.lever.client import (
    CompanyNotFoundError,
    LeverClient,
    LeverError,
    NetworkError,
    RateLimitedError,
    ServerError,
)
from worker.sources.lever.parser import (
    detect_remote,
    humanize_company_handle,
    parse_company_postings,
    parse_posting,
)
from worker.sources.lever.source import LeverSource
from worker.sources.manual.mock_source import MockSource


def _posting(post_id="p1", **overrides):
    base = {
        "id": post_id,
        "text": "Backend Developer Intern",
        "hostedUrl": f"https://jobs.lever.co/acme/{post_id}",
        "applyUrl": f"https://jobs.lever.co/acme/{post_id}/apply",
        "categories": {"commitment": "Internship", "location": "Bangalore, India", "team": "Engineering"},
        "description": "<p>Build <strong>APIs</strong> with Python.</p>",
        "createdAt": 1700000000000,
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
    """Route by company handle: value | exception | (status, headers, body)."""

    def opener(url: str, timeout: float):
        company = url.split("/v0/postings/")[1].split("?")[0]
        behavior = mapping[company]
        if isinstance(behavior, BaseException):
            raise behavior
        status, headers, body = behavior
        return FakeResponse(body, status=status, headers=headers)

    return opener


def _json_body(payload) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _source(companies, mapping, **kwargs):
    return LeverSource(
        boards=list(companies),
        enabled=True,
        client_factory=lambda c: LeverClient(c, opener=_opener_for(mapping)),
        **kwargs,
    )


# --- 1/2. successful response: single + multiple postings --------------------


def test_client_fetches_postings_array():
    opener = _opener_for({"acme": (200, {}, _json_body([_posting()]))})
    assert len(LeverClient("acme", opener=opener).fetch_postings()) == 1


def test_client_multiple_postings():
    opener = _opener_for({"acme": (200, {}, _json_body([_posting("p1"), _posting("p2"), _posting("p3")]))})
    assert len(LeverClient("acme", opener=opener).fetch_postings()) == 3


# --- 3. empty response --------------------------------------------------------


def test_empty_company_returns_no_jobs():
    source = _source(["acme"], {"acme": (200, {}, _json_body([]))})
    assert source.discover_jobs() == []
    assert source.last_errors == []


# --- 4/5/6/7/8. error taxonomy -------------------------------------------------


def test_invalid_company_404():
    opener = _opener_for({"nope": (404, {}, b"Not Found")})
    with pytest.raises(CompanyNotFoundError):
        LeverClient("nope", opener=opener).fetch_postings()


def test_rate_limited_429_with_retry_after():
    opener = _opener_for({"acme": (429, {"Retry-After": "15"}, b"slow down")})
    with pytest.raises(RateLimitedError) as caught:
        LeverClient("acme", opener=opener).fetch_postings()
    assert caught.value.retry_after == 15


def test_server_error_5xx():
    opener = _opener_for({"acme": (502, {}, b"bad gateway")})
    with pytest.raises(ServerError):
        LeverClient("acme", opener=opener).fetch_postings()


def test_timeout_and_network_failure():
    with pytest.raises(NetworkError):
        LeverClient("acme", opener=_opener_for({"acme": socket.timeout("timed out")})).fetch_postings()
    with pytest.raises(NetworkError):
        LeverClient("acme", opener=_opener_for({"acme": urllib.error.URLError("dns fail")})).fetch_postings()


def test_unexpected_shape_rejected():
    opener = _opener_for({"acme": (200, {}, _json_body({"jobs": []}))})  # object, not array
    with pytest.raises(LeverError):
        LeverClient("acme", opener=opener).fetch_postings()


# --- 9. multi-company partial failure -------------------------------------------


def test_multiple_companies_partial_failure():
    mapping = {
        "good": (200, {}, _json_body([_posting("g1"), _posting("g2")])),
        "gone": (404, {}, b"nope"),
        "down": socket.timeout("timed out"),
    }
    source = _source(["good", "gone", "down"], mapping)
    jobs = source.discover_jobs()
    assert len(jobs) == 2  # company A retained
    assert len(source.last_errors) == 2  # B + C recorded, no crash
    assert any("gone" in e for e in source.last_errors)


# --- 10/11. HTML cleaning + entities ----------------------------------------------


def test_html_cleaning_and_entities():
    html = (
        "<div><style>.x{color:red}</style><script>alert(1)</script>"
        "<h2>Join&nbsp;us</h2><p>Build&nbsp;APIs &amp; grow.<br/>Apply now.</p></div>"
    )
    text = html_to_text(html)
    assert "alert" not in text and "color" not in text
    assert "Join us" in text and "APIs & grow." in text and "Apply now." in text
    assert html_to_text("") == "" and html_to_text(None) == ""


def test_description_prefers_plain_text():
    job = parse_posting("acme", _posting(description="<p>HTML</p>", descriptionPlain="  Plain   text  "))
    assert job.description == "Plain text"


# --- 12. remote detection ----------------------------------------------------------


def test_remote_detection_conservative():
    assert detect_remote("Remote - US") is True
    assert detect_remote("Remote, India") is True
    assert detect_remote("Hybrid Remote Office") is True
    assert detect_remote("New York, NY") is False
    assert detect_remote("") is False  # missing location is NOT remote
    assert detect_remote(None) is False
    assert detect_remote("Boston", {"workplaceType": "remote"}) is True


# --- 13/14. field mapping + missing optionals ----------------------------------------


def test_posting_mapping_preserves_raw_and_fields():
    raw = _posting("p77", text="AI/ML Intern")
    job = parse_posting("acme-corp", raw)
    assert isinstance(job, DiscoveredJob)
    assert job.external_id == "p77"
    assert job.title == "AI/ML Intern"
    assert job.company_name == "Acme Corp"  # derived from handle (documented)
    assert job.location == "Bangalore, India" and job.locations == ["Bangalore, India"]
    assert job.is_remote is False
    assert job.employment_type == "Internship"
    assert "APIs" in job.description and "<" not in job.description
    assert job.source_type == "lever"
    assert job.source_name == "lever:acme-corp"
    assert job.source_url == "https://jobs.lever.co/acme-corp"
    assert job.apply_url == "https://jobs.lever.co/acme/p77/apply"
    assert job.posted_at is not None and job.posted_at.year == 2023
    assert job.skills == [] and job.salary_min is None and job.company_domain == ""
    assert job.raw_data == raw


def test_missing_optional_fields_default_safely():
    job = parse_posting("acme", {"id": "x1"})
    assert job.title == "" and job.location == "" and job.locations == []
    assert job.is_remote is False and job.description == ""
    assert job.posted_at is None and job.apply_url == ""
    assert job.skills == []
    assert parse_company_postings("acme", "junk") == []
    assert parse_company_postings("acme", [_posting("p1"), "junk", None])[0].external_id == "p1"


def test_humanize_company_handle():
    assert humanize_company_handle("acme-corp") == "Acme Corp"
    assert humanize_company_handle("  FOO_BAR ") == "Foo Bar"


# --- 15. registry integration ---------------------------------------------------------


def test_registry_supports_mock_greenhouse_lever():
    assert isinstance(registry.get_source("mock"), MockSource)
    assert isinstance(registry.get_source("greenhouse"), GreenhouseSource)
    lever = registry.get_source("lever")
    assert lever is not None and lever.source_type == "lever"
    assert {s.source_name for s in registry.get_all_sources()} >= {"mock", "greenhouse", "lever"}


# --- 16. pipeline integration ------------------------------------------------------------


def test_pipeline_with_mock_and_lever():
    lever = _source(["acme"], {"acme": (200, {}, _json_body([_posting("l1", text="Python Developer Intern")]))})
    result = run_discovery([MockSource(), lever])
    assert result.discovered_count == 6 and result.normalized_count == 6 and result.unique_count == 6
    by_source = {s.name: s for s in result.source_stats}
    assert by_source["mock"].discovered == 5 and by_source["lever"].discovered == 1
    lever_jobs = [j for j in result.jobs if j.original.source_type == "lever"]
    assert len(lever_jobs) == 1 and lever_jobs[0].normalized_title == "python developer intern"


# --- 17/18. configuration parsing + dedup/capping ---------------------------------------------


def test_config_defaults_disabled_and_parsing():
    assert lever_config.is_enabled({}) is False
    assert lever_config.is_enabled({"LEVER_ENABLED": "1"}) is True
    assert lever_config.get_boards({}) == []
    assert lever_config.get_boards({"LEVER_BOARDS": " Acme ;globex,acme;; "}) == ["acme", "globex"]
    assert lever_config.get_timeout({}) == 10.0
    assert lever_config.get_timeout({"LEVER_TIMEOUT": "bogus"}) == 10.0


def test_config_duplicate_removal_and_capping():
    boards = [f"c{i}" for i in range(15)] + ["c0", "", "  "]
    capped = lever_config.get_boards({"LEVER_BOARDS": ";".join(boards), "LEVER_MAX_BOARDS": "10"})
    assert capped == [f"c{i}" for i in range(10)]


def test_disabled_source_returns_empty_without_network():
    def _boom(url, timeout):
        raise AssertionError("no HTTP when disabled")

    assert LeverSource(boards=[], enabled=False, client_factory=lambda c: LeverClient(c, opener=_boom)).discover_jobs() == []
    assert LeverSource(enabled=False).health_check().ok is False
    assert LeverSource(boards=[], enabled=True).health_check().ok is False

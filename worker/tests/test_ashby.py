"""Phase 4.2C Ashby tests. Fully offline — HTTP is faked, never live.

Fixtures mirror Ashby's documented Job Postings API shape
(GET /posting-api/job-board/{name}?includeCompensation=true).
"""

import json
import socket
import urllib.error

import pytest

from worker.models.job import DiscoveredJob
from worker.pipelines.discovery_pipeline import run_discovery
from worker.sources import registry
from worker.sources.ashby import config as ashby_config
from worker.sources.ashby.client import (
    AshbyClient,
    AshbyError,
    BoardNotFoundError,
    NetworkError,
    RateLimitedError,
    ServerError,
)
from worker.sources.ashby.parser import (
    detect_remote,
    humanize_board_name,
    parse_board_jobs,
    parse_posting,
)
from worker.sources.ashby.source import AshbySource
from worker.sources.greenhouse.source import GreenhouseSource
from worker.sources.lever.source import LeverSource
from worker.sources.html_text import html_to_text
from worker.sources.lever.source import LeverSource
from worker.sources.manual.mock_source import MockSource


def _posting(job_id="j1", **overrides):
    base = {
        "id": job_id,
        "title": "Backend Developer Intern",
        "location": "Bangalore, India",
        "secondaryLocations": [],
        "department": "Engineering",
        "team": "Platform",
        "isListed": True,
        "isRemote": False,
        "workplaceType": "OnSite",
        "descriptionHtml": "<p>Build <strong>APIs</strong> with Python.</p>",
        "descriptionPlain": "",
        "publishedAt": "2026-09-20T10:00:00.000+00:00",
        "employmentType": "FullTime",
        "jobUrl": f"https://jobs.ashbyhq.com/acme/{job_id}",
        "applyUrl": f"https://jobs.ashbyhq.com/acme/{job_id}/application",
        "compensation": {
            "summaryComponents": [
                {
                    "compensationType": "Salary",
                    "interval": "1 YEAR",
                    "currencyCode": "USD",
                    "minValue": 80000,
                    "maxValue": 100000,
                }
            ]
        },
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
    """Route by board name: value | exception | (status, headers, body)."""

    def opener(url: str, timeout: float):
        board = url.split("/posting-api/job-board/")[1].split("?")[0]
        behavior = mapping[board]
        if isinstance(behavior, BaseException):
            raise behavior
        status, headers, body = behavior
        return FakeResponse(body, status=status, headers=headers)

    return opener


def _json_body(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _source(boards, mapping, **kwargs):
    return AshbySource(
        boards=list(boards),
        enabled=True,
        client_factory=lambda b: AshbyClient(b, opener=_opener_for(mapping)),
        **kwargs,
    )


# --- 1/2. successful response: single + multiple jobs --------------------------


def test_client_fetches_board_object():
    opener = _opener_for({"acme": (200, {}, _json_body({"apiVersion": "1", "jobs": [_posting()]}))})
    payload = AshbyClient("acme", opener=opener).fetch_board()
    assert payload["apiVersion"] == "1" and len(payload["jobs"]) == 1


def test_client_multiple_jobs():
    opener = _opener_for({"acme": (200, {}, _json_body({"jobs": [_posting("j1"), _posting("j2"), _posting("j3")]}))})
    assert len(AshbyClient("acme", opener=opener).fetch_board()["jobs"]) == 3


# --- 3. empty response -----------------------------------------------------------


def test_empty_board_returns_no_jobs():
    source = _source(["acme"], {"acme": (200, {}, _json_body({"jobs": []}))})
    assert source.discover_jobs() == []
    assert source.last_errors == []


# --- 4/5/6/7/8. error taxonomy -----------------------------------------------------


def test_invalid_board_404():
    opener = _opener_for({"nope": (404, {}, b"Not Found")})
    with pytest.raises(BoardNotFoundError):
        AshbyClient("nope", opener=opener).fetch_board()


def test_rate_limited_429_with_retry_after():
    opener = _opener_for({"acme": (429, {"Retry-After": "20"}, b"slow down")})
    with pytest.raises(RateLimitedError) as caught:
        AshbyClient("acme", opener=opener).fetch_board()
    assert caught.value.retry_after == 20


def test_server_error_5xx():
    opener = _opener_for({"acme": (503, {}, b"oops")})
    with pytest.raises(ServerError):
        AshbyClient("acme", opener=opener).fetch_board()


def test_timeout_and_network_failure():
    with pytest.raises(NetworkError):
        AshbyClient("acme", opener=_opener_for({"acme": socket.timeout("timed out")})).fetch_board()
    with pytest.raises(NetworkError):
        AshbyClient("acme", opener=_opener_for({"acme": urllib.error.URLError("dns fail")})).fetch_board()


def test_unexpected_shape_rejected():
    opener = _opener_for({"acme": (200, {}, _json_body([_posting()]))})  # array, not object
    with pytest.raises(AshbyError):
        AshbyClient("acme", opener=opener).fetch_board()


# --- 9. multi-board partial failure ---------------------------------------------------


def test_multiple_boards_partial_failure():
    mapping = {
        "good": (200, {}, _json_body({"jobs": [_posting("g1"), _posting("g2")]})),
        "gone": (404, {}, b"nope"),
        "down": socket.timeout("timed out"),
    }
    source = _source(["good", "gone", "down"], mapping)
    jobs = source.discover_jobs()
    assert len(jobs) == 2  # board A retained
    assert len(source.last_errors) == 2  # B + C recorded, no crash
    assert any("gone" in e for e in source.last_errors)


# --- 10/11. HTML cleaning + entities -----------------------------------------------------


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
    job = parse_posting("acme", _posting(descriptionHtml="<p>HTML</p>", descriptionPlain="  Plain   text  "))
    assert job.description == "Plain text"


# --- 12. remote detection (explicit / text / onsite / hybrid / unknown) ----------------------


def test_remote_detection_cases():
    assert detect_remote(True, "OnSite", "Bangalore") is True  # explicit flag wins
    assert detect_remote(None, "Remote", "Bangalore") is True  # workplace type
    assert detect_remote(False, "OnSite", "Remote - US") is True  # location text
    assert detect_remote(False, "OnSite", "Bangalore, India") is False  # onsite
    assert detect_remote(False, "Hybrid", "Bangalore, India") is False  # hybrid is not remote
    assert detect_remote(None, None, "") is False  # unknown is not remote
    assert detect_remote(None, None, None) is False


# --- 13/14. normal mapping + missing optionals -----------------------------------------------


def test_posting_mapping_preserves_raw_and_fields():
    raw = _posting("p77", title="AI/ML Intern")
    job = parse_posting("acme-corp", raw)
    assert isinstance(job, DiscoveredJob)
    assert job.external_id == "p77"
    assert job.title == "AI/ML Intern"
    assert job.company_name == "Acme Corp"  # derived from board name (documented)
    assert job.location == "Bangalore, India"
    assert job.source_type == "ashby"
    assert job.source_name == "ashby:acme-corp"
    assert job.source_url == "https://jobs.ashbyhq.com/acme-corp"
    assert job.apply_url == "https://jobs.ashbyhq.com/acme/p77/application"
    assert "APIs" in job.description and "<" not in job.description
    assert job.skills == [] and job.company_domain == "" and job.experience_level == ""
    assert job.raw_data == raw


def test_missing_optional_fields_default_safely():
    job = parse_posting("acme", {"id": "x1"})
    assert job.title == "" and job.location == "" and job.locations == []
    assert job.is_remote is False and job.description == ""
    assert job.posted_at is None and job.apply_url == ""
    assert job.salary_min is None and job.salary_max is None
    assert parse_board_jobs("acme", {"jobs": [_posting("p1"), "junk", None]})[0].external_id == "p1"
    assert parse_board_jobs("acme", {"jobs": "junk"}) == []
    assert parse_board_jobs("acme", {}) == []


def test_unlisted_postings_skipped():
    jobs = parse_board_jobs("acme", {"jobs": [_posting("listed"), _posting("hidden", isListed=False)]})
    assert [j.external_id for j in jobs] == ["listed"]


# --- 15. multiple locations --------------------------------------------------------------------


def test_multiple_locations():
    job = parse_posting(
        "acme",
        _posting(
            location="New York, NY",
            secondaryLocations=[{"location": "Remote"}, {"location": "New York, NY"}, "Boston, MA"],
        ),
    )
    assert job.location == "New York, NY"
    assert job.locations == ["New York, NY", "Remote", "Boston, MA"]


# --- 16/17/18. compensation + employment type + posted date ----------------------------------------


def test_compensation_parsing():
    job = parse_posting("acme", _posting())
    assert (job.salary_min, job.salary_max, job.salary_currency) == (80000, 100000, "USD")
    assert parse_posting("acme", _posting(compensation={})).salary_min is None
    assert parse_posting("acme", _posting(compensation=None)).salary_max is None
    equity_only = {"summaryComponents": [{"compensationType": "EquityPercentage", "minValue": 0.5, "maxValue": 1.0}]}
    assert parse_posting("acme", _posting(compensation=equity_only)).salary_min is None


def test_employment_type_and_posted_date():
    job = parse_posting("acme", _posting())
    assert job.employment_type == "FullTime"
    assert job.posted_at is not None and (job.posted_at.year, job.posted_at.month) == (2026, 9)
    assert parse_posting("acme", _posting(publishedAt="not-a-date")).posted_at is None
    assert parse_posting("acme", _posting(publishedAt=None)).posted_at is None


def test_humanize_board_name():
    assert humanize_board_name("acme-corp") == "Acme Corp"
    assert humanize_board_name("  FOO_BAR ") == "Foo Bar"


# --- 19. registry integration ------------------------------------------------------------------------


def test_registry_supports_all_four_sources():
    assert isinstance(registry.get_source("mock"), MockSource)
    assert isinstance(registry.get_source("greenhouse"), GreenhouseSource)
    assert isinstance(registry.get_source("lever"), LeverSource)
    ashby = registry.get_source("ashby")
    assert ashby is not None and ashby.source_type == "ashby"
    assert {s.source_name for s in registry.get_all_sources()} >= {"mock", "greenhouse", "lever", "ashby"}


# --- 20. pipeline integration ----------------------------------------------------------------------------


def test_pipeline_with_mock_and_ashby():
    ashby = _source(["acme"], {"acme": (200, {}, _json_body({"jobs": [_posting("a1", title="Python Developer Intern")]}))})
    result = run_discovery([MockSource(), ashby])
    assert result.discovered_count == 6 and result.normalized_count == 6 and result.unique_count == 6
    by_source = {s.name: s for s in result.source_stats}
    assert by_source["mock"].discovered == 5 and by_source["ashby"].discovered == 1
    ashby_jobs = [j for j in result.jobs if j.original.source_type == "ashby"]
    assert len(ashby_jobs) == 1 and ashby_jobs[0].normalized_title == "python developer intern"


# --- 21/22. configuration parsing + dedup/capping -----------------------------------------------------------------


def test_config_defaults_disabled_and_parsing():
    assert ashby_config.is_enabled({}) is False
    assert ashby_config.is_enabled({"ASHBY_ENABLED": "yes"}) is True
    assert ashby_config.get_boards({}) == []
    assert ashby_config.get_boards({"ASHBY_BOARDS": " Acme ;globex,acme;; "}) == ["acme", "globex"]
    assert ashby_config.get_timeout({}) == 10.0
    assert ashby_config.get_timeout({"ASHBY_TIMEOUT": "bogus"}) == 10.0


def test_config_duplicate_removal_and_capping():
    boards = [f"c{i}" for i in range(15)] + ["c0", "", "  "]
    capped = ashby_config.get_boards({"ASHBY_BOARDS": ";".join(boards), "ASHBY_MAX_BOARDS": "10"})
    assert capped == [f"c{i}" for i in range(10)]


def test_disabled_source_returns_empty_without_network():
    def _boom(url, timeout):
        raise AssertionError("no HTTP when disabled")

    assert AshbySource(boards=[], enabled=False, client_factory=lambda b: AshbyClient(b, opener=_boom)).discover_jobs() == []
    assert AshbySource(enabled=False).health_check().ok is False
    assert AshbySource(boards=[], enabled=True).health_check().ok is False

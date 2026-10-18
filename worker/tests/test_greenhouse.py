"""Phase 4.2A Greenhouse tests. Fully offline — HTTP is faked, never live."""

import json
import socket
import urllib.error

import pytest

from worker.models.job import DiscoveredJob
from worker.pipelines.discovery_pipeline import run_discovery
from worker.sources import registry
from worker.sources.greenhouse import config as gh_config
from worker.sources.greenhouse.client import (
    BoardNotFoundError,
    GreenhouseClient,
    NetworkError,
    RateLimitedError,
    ServerError,
)
from worker.sources.greenhouse.parser import (
    detect_remote,
    html_to_text,
    humanize_board_token,
    parse_board_jobs,
    parse_job,
)
from worker.sources.greenhouse.source import GreenhouseSource
from worker.sources.manual.mock_source import MockSource


def _item(job_id=101, **overrides):
    base = {
        "id": job_id,
        "title": "Backend Developer Intern",
        "absolute_url": f"https://job-boards.greenhouse.io/acme/jobs/{job_id}",
        "location": {"name": "Bangalore, India"},
        "metadata": [{"id": 1, "name": "Employment Type", "value": "Internship"}],
        "content": "<p>Build <strong>APIs</strong> with Python.</p>",
    }
    base.update(overrides)
    return base


def _payload(*items):
    return {"jobs": list(items)}


class FakeResponse:
    """Minimal urlopen stand-in: status + headers + body."""

    def __init__(self, body: bytes, status: int = 200, headers: dict = None) -> None:
        self._body = body
        self.status = status
        self.headers = headers or {}

    def read(self, *args):
        return self._body


def _opener_for(mapping):
    """Build opener routing by board token: value | exception | (status, headers, body)."""

    def opener(url: str, timeout: float):
        board = url.split("/v1/boards/")[1].split("/")[0]
        behavior = mapping[board]
        if isinstance(behavior, BaseException):
            raise behavior
        status, headers, body = behavior
        return FakeResponse(body, status=status, headers=headers)

    return opener


def _json_body(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


# --- 1/2. successful response: single + multiple jobs ------------------------


def test_client_fetches_and_decodes_board():
    opener = _opener_for({"acme": (200, {}, _json_body(_payload(_item())))})
    payload = GreenhouseClient("acme", opener=opener).fetch_jobs()
    assert len(payload["jobs"]) == 1


def test_client_multiple_jobs():
    opener = _opener_for({"acme": (200, {}, _json_body(_payload(_item(1), _item(2), _item(3))))})
    payload = GreenhouseClient("acme", opener=opener).fetch_jobs()
    assert len(payload["jobs"]) == 3


# --- 3. empty board ----------------------------------------------------------


def test_empty_board_returns_no_jobs():
    opener = _opener_for({"acme": (200, {}, _json_body({"jobs": []}))})
    source = GreenhouseSource(boards=["acme"], enabled=True, client_factory=lambda b: GreenhouseClient(b, opener=opener))
    assert source.discover_jobs() == []
    assert source.last_errors == []


# --- 4/5/6/7. error taxonomy -------------------------------------------------


def test_invalid_board_404():
    opener = _opener_for({"nope": (404, {}, b"Not Found")})
    with pytest.raises(BoardNotFoundError):
        GreenhouseClient("nope", opener=opener).fetch_jobs()


def test_rate_limited_429_with_retry_after():
    opener = _opener_for({"acme": (429, {"Retry-After": "30"}, b"slow down")})
    with pytest.raises(RateLimitedError) as caught:
        GreenhouseClient("acme", opener=opener).fetch_jobs()
    assert caught.value.retry_after == 30


def test_server_error_5xx():
    opener = _opener_for({"acme": (503, {}, b"oops")})
    with pytest.raises(ServerError):
        GreenhouseClient("acme", opener=opener).fetch_jobs()


def test_timeout_and_network_failure():
    opener = _opener_for({"acme": socket.timeout("timed out")})
    with pytest.raises(NetworkError):
        GreenhouseClient("acme", opener=opener).fetch_jobs()
    opener = _opener_for({"acme": urllib.error.URLError("dns fail")})
    with pytest.raises(NetworkError):
        GreenhouseClient("acme", opener=opener).fetch_jobs()


# --- 8. multi-board partial failure ------------------------------------------


def test_multiple_boards_partial_failure():
    opener = _opener_for(
        {
            "good": (200, {}, _json_body(_payload(_item(1), _item(2)))),
            "gone": (404, {}, b"nope"),
            "down": (500, {}, b"boom"),
        }
    )
    source = GreenhouseSource(
        boards=["good", "gone", "down"],
        enabled=True,
        client_factory=lambda b: GreenhouseClient(b, opener=opener),
    )
    jobs = source.discover_jobs()
    assert len(jobs) == 2  # board A still contributes
    assert len(source.last_errors) == 2  # B + C recorded, no crash
    assert any("gone" in e for e in source.last_errors)


# --- 9. HTML description parsing ----------------------------------------------


def test_html_description_cleaned():
    html = (
        "<html><head><style>.x{color:red}</style>"
        "<script>alert(1)</script></head>"
        "<body><h1>Join&nbsp;us</h1><p>Build&nbsp;APIs &amp; grow.</p></body></html>"
    )
    text = html_to_text(html)
    assert "alert" not in text and "color" not in text
    assert "Join us" in text and "APIs & grow." in text
    assert html_to_text("") == "" and html_to_text(None) == ""


# --- 10. remote detection -----------------------------------------------------


def test_remote_location_detection():
    assert detect_remote("Remote - US") is True
    assert detect_remote("Remote, India") is True
    assert detect_remote("New York, NY") is False
    assert detect_remote("") is False


# --- 11. Greenhouse -> DiscoveredJob mapping ----------------------------------


def test_job_mapping_preserves_raw_and_fields():
    raw = _item(77, title="AI/ML Intern", location={"name": "Remote, India"})
    job = parse_job("acme-corp", raw)
    assert isinstance(job, DiscoveredJob)
    assert job.external_id == "77"
    assert job.title == "AI/ML Intern"
    assert job.company_name == "Acme Corp"  # derived from board token (documented)
    assert job.location == "Remote, India" and job.locations == ["Remote, India"]
    assert job.is_remote is True
    assert job.employment_type == "Internship"
    assert "APIs" in job.description and "<" not in job.description
    assert job.source_type == "greenhouse"
    assert job.source_name == "greenhouse:acme-corp"
    assert job.apply_url == "https://job-boards.greenhouse.io/acme/jobs/77"
    assert job.raw_data == raw  # full original payload preserved
    assert job.posted_at is None  # list payload carries no posting date


def test_parse_board_jobs_skips_malformed():
    assert parse_board_jobs("acme", {"jobs": [_item(1), "junk", None]})[0].external_id == "1"
    assert parse_board_jobs("acme", {"jobs": "junk"}) == []
    assert parse_board_jobs("acme", {}) == []


def test_humanize_board_token():
    assert humanize_board_token("acme-corp") == "Acme Corp"
    assert humanize_board_token("  FOO_BAR ") == "Foo Bar"


# --- config -------------------------------------------------------------------


def test_config_defaults_disabled_and_parsing():
    assert gh_config.is_enabled({}) is False
    assert gh_config.is_enabled({"GREENHOUSE_ENABLED": "true"}) is True
    assert gh_config.get_boards({}) == []
    assert gh_config.get_boards({"GREENHOUSE_BOARDS": "a-one;b-two, c_three ;a-one"}) == ["a-one", "b-two", "c_three"]
    assert gh_config.get_timeout({}) == 10.0
    assert gh_config.get_timeout({"GREENHOUSE_TIMEOUT": "bogus"}) == 10.0


def test_disabled_source_returns_empty_without_network():
    def _boom(url, timeout):
        raise AssertionError("no HTTP when disabled")

    assert GreenhouseSource(boards=[], enabled=False, client_factory=lambda b: GreenhouseClient(b, opener=_boom)).discover_jobs() == []
    assert GreenhouseSource(enabled=False).health_check().ok is False
    assert GreenhouseSource(boards=[], enabled=True).health_check().ok is False


# --- 12. registry integration --------------------------------------------------


def test_registry_supports_mock_and_greenhouse():
    assert registry.get_source("mock") is not None
    greenhouse = registry.get_source("greenhouse")
    assert greenhouse is not None and greenhouse.source_type == "greenhouse"
    assert isinstance(registry.get_source("mock"), MockSource)
    assert isinstance(greenhouse, GreenhouseSource)


# --- 13. pipeline integration ---------------------------------------------------


def test_pipeline_with_mock_and_greenhouse():
    opener = _opener_for({"acme": (200, {}, _json_body(_payload(_item(901, title="Python Developer Intern"))))})
    greenhouse = GreenhouseSource(boards=["acme"], enabled=True, client_factory=lambda b: GreenhouseClient(b, opener=opener))
    result = run_discovery([MockSource(), greenhouse])
    assert result.discovered_count == 6  # 5 mock + 1 greenhouse
    assert result.normalized_count == 6 and result.unique_count == 6
    by_source = {s.name: s for s in result.source_stats}
    assert by_source["mock"].discovered == 5 and by_source["greenhouse"].discovered == 1
    gh_jobs = [j for j in result.jobs if j.original.source_type == "greenhouse"]
    assert len(gh_jobs) == 1 and gh_jobs[0].normalized_title == "python developer intern"

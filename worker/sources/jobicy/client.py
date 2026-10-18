"""HTTP client for Jobicy's public Remote Jobs API (Phase 10C-3).

Verified endpoint (official docs, ``jobicy.com/jobs-rss-feed``):
``GET https://jobicy.com/api/v2/remote-jobs`` with query params
(``count``, ``tag``, ``geo``, ``industry``) — returns
``{"success": true, "jobs": [...], "nextCursor": ...}``, no auth. Only the
first page is ever fetched (no cursor walking by design). No private
endpoints, stdlib ``urllib`` only. Conservative by design: sequential use,
bounded timeout, capped response size, no retries by default, explicit error
taxonomy (400 / 429 / 5xx / network). Tags are public search terms — safe in
error messages; nothing secret is ever logged.
"""

import json
import logging
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from worker.sources.jobicy import config as jobicy_config

logger = logging.getLogger("ai-jobhunter.jobicy.client")

JOBS_API_HOST = "https://jobicy.com"
JOBS_API_PATH = "/api/v2/remote-jobs"
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_COUNT_PER_REQUEST = 200  # documented API maximum


class JobicyError(Exception):
    """Base error for Jobicy failures (carries the search tag)."""

    def __init__(self, tag: str, message: str) -> None:
        super().__init__(f"tag '{tag}': {message}")
        self.tag = tag


class BadRequestError(JobicyError):
    """HTTP 400 — invalid filters or stale cursor."""


class RateLimitedError(JobicyError):
    """HTTP 429 — backing off; ``retry_after`` mirrors the header (or None)."""

    def __init__(self, tag: str, message: str, retry_after=None) -> None:
        super().__init__(tag, message)
        self.retry_after = retry_after


class ServerError(JobicyError):
    """HTTP 5xx — Jobicy-side failure."""


class NetworkError(JobicyError):
    """Timeout / DNS / connection failure."""


def _default_opener(url: str, timeout: float):
    """Real network call (urllib). Signature matches the injectable opener."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": jobicy_config.USER_AGENT,
            "Accept": "application/json",
        },
    )
    return urllib.request.urlopen(request, timeout=timeout)


class JobicyClient:
    """Thin wrapper over one filtered listing page (single page, bounded).

    ``opener`` is injectable for offline tests:
    ``opener(url, timeout)`` returns an object with ``.status`` (or
    ``.getcode()``), ``.headers`` (mapping), and ``.read()`` — or raises.
    """

    def __init__(self, tag: str = "", geo: str = "", industry: str = "",
                 count: int = 20, timeout: float = None, opener=None,
                 max_retries: int = 0) -> None:
        self.tag = (tag or "").strip()
        self.geo = (geo or "").strip()
        self.industry = (industry or "").strip()
        self.count = max(1, min(int(count), MAX_COUNT_PER_REQUEST))
        self.timeout = timeout if timeout is not None else jobicy_config.get_timeout()
        self.opener = opener or _default_opener
        self.max_retries = max(0, int(max_retries))

    def search_url(self) -> str:
        """Public listing URL (single page — no cursor walking by design)."""
        params = [("count", str(self.count))]
        if self.tag:
            params.append(("tag", self.tag))
        if self.geo:
            params.append(("geo", self.geo))
        if self.industry:
            params.append(("industry", self.industry))
        return JOBS_API_HOST + JOBS_API_PATH + "?" + urllib.parse.urlencode(params)

    def fetch_jobs(self) -> dict:
        """Fetch and JSON-decode one listing page (raises JobicyError)."""
        url = self.search_url()
        attempts = 1 + self.max_retries
        for attempt in range(1, attempts + 1):
            try:
                response = self.opener(url, self.timeout)
                return self._read_json(response, url)
            except RateLimitedError as exc:
                if attempt < attempts and exc.retry_after:
                    logger.warning("jobicy: tag '%s' rate-limited, retrying once", self.tag)
                    time.sleep(min(float(exc.retry_after), 60.0))
                    continue
                raise
            except JobicyError:
                raise
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
                raise NetworkError(self.tag, f"network failure ({type(exc).__name__})")
            except Exception as exc:  # defensive: never leak unexpected failures as success
                raise NetworkError(self.tag, f"unexpected transport failure ({type(exc).__name__})")

    def _read_json(self, response, url: str) -> dict:
        """Validate status, cap body size, decode JSON (raises JobicyError)."""
        status = getattr(response, "status", None)
        if status is None and hasattr(response, "getcode"):
            try:
                status = response.getcode()
            except Exception:
                status = None
        headers = getattr(response, "headers", {}) or {}

        if status == 400:
            raise BadRequestError(self.tag, "HTTP 400 (invalid filters)")
        if status == 429:
            retry_after = self._retry_after(headers)
            raise RateLimitedError(self.tag, "HTTP 429 (rate limited)", retry_after=retry_after)
        if status is not None and 500 <= status <= 599:
            raise ServerError(self.tag, f"HTTP {status}")
        if status is not None and status != 200:
            raise JobicyError(self.tag, f"HTTP {status}")

        try:
            body = response.read(MAX_RESPONSE_BYTES + 1)
        except Exception as exc:
            raise NetworkError(self.tag, f"failed reading response ({type(exc).__name__})")
        if len(body) > MAX_RESPONSE_BYTES:
            raise JobicyError(self.tag, "response exceeded size cap")
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            raise JobicyError(self.tag, "invalid JSON response")
        if not isinstance(payload, dict):
            raise JobicyError(self.tag, "unexpected response shape")
        if payload.get("success") is False:
            raise JobicyError(self.tag, "API reported failure")
        return payload

    @staticmethod
    def _retry_after(headers) -> object:
        """Parse Retry-After seconds (None when absent/invalid)."""
        try:
            get = headers.get if hasattr(headers, "get") else (lambda k: None)
            value = get("Retry-After")
            if value is None:
                return None
            return max(0, int(str(value).strip()))
        except (TypeError, ValueError):
            return None

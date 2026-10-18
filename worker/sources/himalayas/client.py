"""HTTP client for Himalayas' public Remote Jobs API (Phase 10C-2).

Verified endpoint (official docs, ``himalayas.app/docs/remote-jobs-api``):
``GET https://himalayas.app/jobs/api/search`` with query params
(``q``, ``employment_type``, ``limit``) — returns
``{"jobs": [...], "nextCursor": ...}``, no auth. No private endpoints,
stdlib ``urllib`` only. Conservative by design: sequential use, bounded
timeout, capped response size, no retries by default, explicit error taxonomy
(400 / 429 / 5xx / network). Keywords are public search terms — safe in
error messages; nothing secret is ever logged.
"""

import json
import logging
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from worker.sources.himalayas import config as himalaya_config

logger = logging.getLogger("ai-jobhunter.himalayas.client")

SEARCH_API_HOST = "https://himalayas.app"
SEARCH_API_PATH = "/jobs/api/search"
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_LIMIT_PER_REQUEST = 20  # documented API maximum


class HimalayaError(Exception):
    """Base error for Himalayas failures (carries the search keyword)."""

    def __init__(self, keyword: str, message: str) -> None:
        super().__init__(f"keyword '{keyword}': {message}")
        self.keyword = keyword


class BadRequestError(HimalayaError):
    """HTTP 400 — invalid query parameters."""


class RateLimitedError(HimalayaError):
    """HTTP 429 — backing off; ``retry_after`` mirrors the header (or None)."""

    def __init__(self, keyword: str, message: str, retry_after=None) -> None:
        super().__init__(keyword, message)
        self.retry_after = retry_after


class ServerError(HimalayaError):
    """HTTP 5xx — Himalayas-side failure."""


class NetworkError(HimalayaError):
    """Timeout / DNS / connection failure."""


def _default_opener(url: str, timeout: float):
    """Real network call (urllib). Signature matches the injectable opener."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": himalaya_config.USER_AGENT,
            "Accept": "application/json",
        },
    )
    return urllib.request.urlopen(request, timeout=timeout)


class HimalayaClient:
    """Thin wrapper over one filtered search (single page, bounded).

    ``opener`` is injectable for offline tests:
    ``opener(url, timeout)`` returns an object with ``.status`` (or
    ``.getcode()``), ``.headers`` (mapping), and ``.read()`` — or raises.
    """

    def __init__(self, keyword: str = "", employment_types=None, limit: int = 20,
                 timeout: float = None, opener=None, max_retries: int = 0) -> None:
        self.keyword = (keyword or "").strip()
        self.employment_types = [str(t).strip() for t in (employment_types or []) if str(t).strip()]
        self.limit = max(1, min(int(limit), MAX_LIMIT_PER_REQUEST))
        self.timeout = timeout if timeout is not None else himalaya_config.get_timeout()
        self.opener = opener or _default_opener
        self.max_retries = max(0, int(max_retries))

    def search_url(self) -> str:
        """Public search URL (single page — no cursor walking by design)."""
        params = [("q", self.keyword), ("limit", str(self.limit))]
        for employment_type in self.employment_types:
            params.append(("employment_type", employment_type))
        return SEARCH_API_HOST + SEARCH_API_PATH + "?" + urllib.parse.urlencode(params)

    def fetch_jobs(self) -> dict:
        """Fetch and JSON-decode one search page (raises HimalayaError)."""
        url = self.search_url()
        attempts = 1 + self.max_retries
        for attempt in range(1, attempts + 1):
            try:
                response = self.opener(url, self.timeout)
                return self._read_json(response, url)
            except RateLimitedError as exc:
                if attempt < attempts and exc.retry_after:
                    logger.warning("himalaya: keyword '%s' rate-limited, retrying once", self.keyword)
                    time.sleep(min(float(exc.retry_after), 60.0))
                    continue
                raise
            except HimalayaError:
                raise
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
                raise NetworkError(self.keyword, f"network failure ({type(exc).__name__})")
            except Exception as exc:  # defensive: never leak unexpected failures as success
                raise NetworkError(self.keyword, f"unexpected transport failure ({type(exc).__name__})")

    def _read_json(self, response, url: str) -> dict:
        """Validate status, cap body size, decode JSON (raises HimalayaError)."""
        status = getattr(response, "status", None)
        if status is None and hasattr(response, "getcode"):
            try:
                status = response.getcode()
            except Exception:
                status = None
        headers = getattr(response, "headers", {}) or {}

        if status == 400:
            raise BadRequestError(self.keyword, "HTTP 400 (invalid query parameters)")
        if status == 429:
            retry_after = self._retry_after(headers)
            raise RateLimitedError(self.keyword, "HTTP 429 (rate limited)", retry_after=retry_after)
        if status is not None and 500 <= status <= 599:
            raise ServerError(self.keyword, f"HTTP {status}")
        if status is not None and status != 200:
            raise HimalayaError(self.keyword, f"HTTP {status}")

        try:
            body = response.read(MAX_RESPONSE_BYTES + 1)
        except Exception as exc:
            raise NetworkError(self.keyword, f"failed reading response ({type(exc).__name__})")
        if len(body) > MAX_RESPONSE_BYTES:
            raise HimalayaError(self.keyword, "response exceeded size cap")
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            raise HimalayaError(self.keyword, "invalid JSON response")
        if not isinstance(payload, dict):
            raise HimalayaError(self.keyword, "unexpected response shape")
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

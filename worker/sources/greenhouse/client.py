"""HTTP client for public Greenhouse job-board endpoints (Phase 4.2A).

Public endpoint only: ``GET /v1/boards/{board}/jobs?content=true`` on
``boards-api.greenhouse.io``. No auth, no private APIs, stdlib ``urllib``
only. Conservative by design: sequential use, bounded timeout, capped
response size, no retries by default, explicit error taxonomy (404 / 429 /
5xx / network). Board tokens are public identifiers — safe to include in
error messages; nothing secret is ever logged.
"""

import json
import logging
import socket
import time
import urllib.error
import urllib.request

from worker.sources.greenhouse import config as gh_config

logger = logging.getLogger("ai-jobhunter.greenhouse.client")

BOARDS_API_HOST = "https://boards-api.greenhouse.io"
MAX_RESPONSE_BYTES = 5 * 1024 * 1024


class GreenhouseError(Exception):
    """Base error for Greenhouse board failures (carries the board token)."""

    def __init__(self, board: str, message: str) -> None:
        super().__init__(f"board '{board}': {message}")
        self.board = board


class BoardNotFoundError(GreenhouseError):
    """HTTP 404 — unknown/removed board token."""


class RateLimitedError(GreenhouseError):
    """HTTP 429 — backing off; ``retry_after`` mirrors the header (or None)."""

    def __init__(self, board: str, message: str, retry_after=None) -> None:
        super().__init__(board, message)
        self.retry_after = retry_after


class ServerError(GreenhouseError):
    """HTTP 5xx — Greenhouse-side failure."""


class NetworkError(GreenhouseError):
    """Timeout / DNS / connection failure."""


def _default_opener(url: str, timeout: float):
    """Real network call (urllib). Signature matches the injectable opener."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": gh_config.USER_AGENT,
            "Accept": "application/json",
        },
    )
    return urllib.request.urlopen(request, timeout=timeout)


class GreenhouseClient:
    """Thin wrapper over one board's public jobs endpoint.

    ``opener`` is injectable for offline tests:
    ``opener(url, timeout)`` returns an object with ``.status`` (or
    ``.getcode()``), ``.headers`` (mapping), and ``.read()`` — or raises.
    """

    def __init__(self, board: str, timeout: float = None, opener=None, max_retries: int = 0) -> None:
        self.board = (board or "").strip().lower()
        if not self.board:
            raise ValueError("board token must be non-empty")
        self.timeout = timeout if timeout is not None else gh_config.get_timeout()
        self.opener = opener or _default_opener
        self.max_retries = max(0, int(max_retries))

    def jobs_url(self) -> str:
        """Public jobs URL for this board (content included for descriptions)."""
        return f"{BOARDS_API_HOST}/v1/boards/{self.board}/jobs?content=true"

    def fetch_jobs(self) -> dict:
        """Fetch and JSON-decode one board's jobs (raises GreenhouseError)."""
        url = self.jobs_url()
        attempts = 1 + self.max_retries
        for attempt in range(1, attempts + 1):
            try:
                response = self.opener(url, self.timeout)
                return self._read_json(response, url)
            except RateLimitedError as exc:
                if attempt < attempts and exc.retry_after:
                    logger.warning("greenhouse: board '%s' rate-limited, retrying once", self.board)
                    time.sleep(min(float(exc.retry_after), 60.0))
                    continue
                raise
            except GreenhouseError:
                raise
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
                raise NetworkError(self.board, f"network failure ({type(exc).__name__})")
            except Exception as exc:  # defensive: never leak unexpected failures as success
                raise NetworkError(self.board, f"unexpected transport failure ({type(exc).__name__})")

    def _read_json(self, response, url: str) -> dict:
        """Validate status, cap body size, decode JSON (raises GreenhouseError)."""
        status = getattr(response, "status", None)
        if status is None and hasattr(response, "getcode"):
            try:
                status = response.getcode()
            except Exception:
                status = None
        headers = getattr(response, "headers", {}) or {}

        if status == 404:
            raise BoardNotFoundError(self.board, "HTTP 404 (unknown board)")
        if status == 429:
            retry_after = self._retry_after(headers)
            raise RateLimitedError(self.board, "HTTP 429 (rate limited)", retry_after=retry_after)
        if status is not None and 500 <= status <= 599:
            raise ServerError(self.board, f"HTTP {status}")
        if status is not None and status != 200:
            raise GreenhouseError(self.board, f"HTTP {status}")

        try:
            body = response.read(MAX_RESPONSE_BYTES + 1)
        except Exception as exc:
            raise NetworkError(self.board, f"failed reading response ({type(exc).__name__})")
        if len(body) > MAX_RESPONSE_BYTES:
            raise GreenhouseError(self.board, "response exceeded size cap")
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            raise GreenhouseError(self.board, "invalid JSON response")
        if not isinstance(payload, dict):
            raise GreenhouseError(self.board, "unexpected response shape")
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

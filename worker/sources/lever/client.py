"""HTTP client for public Lever postings (Phase 4.2B).

Public endpoint only: ``GET /v0/postings/{company}?mode=json`` on
``api.lever.co`` — returns a JSON **array** of postings. No auth, no private
APIs, stdlib ``urllib`` only. Conservative by design: sequential use, bounded
timeout, capped response size, no retries by default, explicit error taxonomy
(404 / 429 / 5xx / network). Company identifiers are public handles — safe in
error messages; nothing secret is ever logged.
"""

import json
import logging
import socket
import time
import urllib.error
import urllib.request

from worker.sources.lever import config as lever_config

logger = logging.getLogger("ai-jobhunter.lever.client")

POSTINGS_API_HOST = "https://api.lever.co"
MAX_RESPONSE_BYTES = 5 * 1024 * 1024


class LeverError(Exception):
    """Base error for Lever failures (carries the company identifier)."""

    def __init__(self, company: str, message: str) -> None:
        super().__init__(f"company '{company}': {message}")
        self.company = company


class CompanyNotFoundError(LeverError):
    """HTTP 404 — unknown/removed company handle."""


class RateLimitedError(LeverError):
    """HTTP 429 — backing off; ``retry_after`` mirrors the header (or None)."""

    def __init__(self, company: str, message: str, retry_after=None) -> None:
        super().__init__(company, message)
        self.retry_after = retry_after


class ServerError(LeverError):
    """HTTP 5xx — Lever-side failure."""


class NetworkError(LeverError):
    """Timeout / DNS / connection failure."""


def _default_opener(url: str, timeout: float):
    """Real network call (urllib). Signature matches the injectable opener."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": lever_config.USER_AGENT,
            "Accept": "application/json",
        },
    )
    return urllib.request.urlopen(request, timeout=timeout)


class LeverClient:
    """Thin wrapper over one company's public postings endpoint.

    ``opener`` is injectable for offline tests:
    ``opener(url, timeout)`` returns an object with ``.status`` (or
    ``.getcode()``), ``.headers`` (mapping), and ``.read()`` — or raises.
    """

    def __init__(self, company: str, timeout: float = None, opener=None, max_retries: int = 0) -> None:
        self.company = (company or "").strip().lower()
        if not self.company:
            raise ValueError("company identifier must be non-empty")
        self.timeout = timeout if timeout is not None else lever_config.get_timeout()
        self.opener = opener or _default_opener
        self.max_retries = max(0, int(max_retries))

    def postings_url(self) -> str:
        """Public postings URL for this company (JSON mode)."""
        return f"{POSTINGS_API_HOST}/v0/postings/{self.company}?mode=json"

    def fetch_postings(self) -> list:
        """Fetch and decode one company's postings array (raises LeverError)."""
        url = self.postings_url()
        attempts = 1 + self.max_retries
        for attempt in range(1, attempts + 1):
            try:
                response = self.opener(url, self.timeout)
                return self._read_json(response, url)
            except RateLimitedError as exc:
                if attempt < attempts and exc.retry_after:
                    logger.warning("lever: company '%s' rate-limited, retrying once", self.company)
                    time.sleep(min(float(exc.retry_after), 60.0))
                    continue
                raise
            except LeverError:
                raise
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
                raise NetworkError(self.company, f"network failure ({type(exc).__name__})")
            except Exception as exc:  # defensive: never leak unexpected failures as success
                raise NetworkError(self.company, f"unexpected transport failure ({type(exc).__name__})")

    def _read_json(self, response, url: str) -> list:
        """Validate status, cap body size, decode a JSON array (raises LeverError)."""
        status = getattr(response, "status", None)
        if status is None and hasattr(response, "getcode"):
            try:
                status = response.getcode()
            except Exception:
                status = None
        headers = getattr(response, "headers", {}) or {}

        if status == 404:
            raise CompanyNotFoundError(self.company, "HTTP 404 (unknown company)")
        if status == 429:
            retry_after = self._retry_after(headers)
            raise RateLimitedError(self.company, "HTTP 429 (rate limited)", retry_after=retry_after)
        if status is not None and 500 <= status <= 599:
            raise ServerError(self.company, f"HTTP {status}")
        if status is not None and status != 200:
            raise LeverError(self.company, f"HTTP {status}")

        try:
            body = response.read(MAX_RESPONSE_BYTES + 1)
        except Exception as exc:
            raise NetworkError(self.company, f"failed reading response ({type(exc).__name__})")
        if len(body) > MAX_RESPONSE_BYTES:
            raise LeverError(self.company, "response exceeded size cap")
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            raise LeverError(self.company, "invalid JSON response")
        if not isinstance(payload, list):
            raise LeverError(self.company, "unexpected response shape (expected a JSON array)")
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

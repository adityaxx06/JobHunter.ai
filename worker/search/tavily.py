"""Tavily search provider (Phase 6.0) — first real SearchProvider.

Verified against Tavily's public OpenAPI (docs.tavily.com):
``POST https://api.tavily.com/search`` with bearer auth
(``Authorization: Bearer <key>``) and a JSON body of
``{query, search_depth, max_results, include_answer: false,
include_published_date: true}`` plus an optional ``time_range``
(``TAVILY_TIME_RANGE``, unset by default). Response ``results[]`` carry
``{title, url, content, score, published_date}``.

Cost discipline (free tier ≈ 1,000 credits/month): ``basic`` depth costs
1 credit (default), ``advanced`` costs 2; per-query results capped at 10;
one request per ``search()`` call; no retries by default; blank queries
return [] without touching the network.

Stdlib ``urllib`` only (same convention as the ATS connectors), injectable
transport for offline tests. Errors never carry the key, headers, or
secret-bearing URLs — the key travels in the header, never the URL.
"""

import json
import logging
import socket
import time
import urllib.error
import urllib.request

from worker.models.search import SearchHealth, SearchResult
from worker.search import config as search_config
from worker.search.base import SearchProvider

logger = logging.getLogger("ai-jobhunter.search.tavily")

TAVILY_API_HOST = "https://api.tavily.com"
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_RESULTS_CAP = 10
SNIPPET_MAX_CHARS = 1500


class TavilyError(Exception):
    """Base error for Tavily failures (never carries key material)."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(f"tavily {kind}: {message}")
        self.kind = kind  # not_configured | unauthorized | rate_limited | bad_request | server | network | malformed


class NotConfiguredError(TavilyError):
    """No TAVILY_API_KEY present."""

    def __init__(self) -> None:
        super().__init__("not_configured", "TAVILY_API_KEY is missing")


class UnauthorizedError(TavilyError):
    """HTTP 401 — wrong or missing API key (key value never included)."""

    def __init__(self) -> None:
        super().__init__("unauthorized", "HTTP 401 (invalid API key)")


class RateLimitedError(TavilyError):
    """HTTP 429 (or plan-limit 432/433) — ``retry_after`` mirrors the header."""

    def __init__(self, message: str, retry_after=None) -> None:
        super().__init__("rate_limited", message)
        self.retry_after = retry_after


class ServerError(TavilyError):
    """HTTP 5xx — Tavily-side failure."""


class NetworkError(TavilyError):
    """Timeout / DNS / connection failure."""


class MalformedError(TavilyError):
    """Unusable response shape or invalid request rejected by the API."""


def _default_opener(url: str, timeout: float, *, body: bytes, headers: dict):
    """Real network call (urllib). Signature matches the injectable opener."""
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    return urllib.request.urlopen(request, timeout=timeout)


class TavilySearchProvider(SearchProvider):
    """Live web-search leads via Tavily. Free-tier guarded by construction."""

    provider_name = "tavily"

    def __init__(self, api_key: str = "", search_depth: str = "",
                 timeout: float = None, opener=None, max_retries: int = 0,
                 time_range: str = "") -> None:
        self.api_key = api_key or search_config.get_tavily_key()
        self.search_depth = (search_depth or search_config.get_tavily_depth()).strip().lower()
        if self.search_depth not in search_config.TAVILY_DEPTHS:
            self.search_depth = search_config.DEFAULT_TAVILY_DEPTH
        self.time_range = (time_range or search_config.get_tavily_time_range()).strip().lower()
        if self.time_range not in search_config.TAVILY_TIME_RANGES:
            self.time_range = ""
        self.timeout = timeout if timeout is not None else search_config.get_timeout()
        self.opener = opener or _default_opener
        self.max_retries = max(0, int(max_retries))

    def is_configured(self) -> bool:
        """True when an API key is present (no network check)."""
        return bool(self.api_key and self.api_key.strip())

    def health_check(self) -> SearchHealth:
        """Config-only check: never spends credits, never touches network."""
        if not self.is_configured():
            return SearchHealth(ok=False, message="tavily not configured (TAVILY_API_KEY missing)")
        return SearchHealth(ok=True, message="tavily ready (key configured)")

    def _headers(self) -> dict:
        """Auth lives here and ONLY here — callers must never log it."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AI-JobHunter/0.1 (+job-discovery; conservative)",
        }

    def search(self, query: str, max_results: int = 20) -> list:
        """One POST per call; blank queries cost nothing (return [])."""
        if not self.is_configured():
            raise NotConfiguredError()
        if not query or not query.strip():
            return []
        count = max(1, min(int(max_results), MAX_RESULTS_CAP))
        payload = {
            "query": query.strip(),
            "search_depth": self.search_depth,
            "max_results": count,
            "include_answer": False,
            "include_published_date": True,
        }
        if self.time_range:
            # Best-effort recency hint only; strict publication-date filtering
            # stays off so undated results are never silently dropped.
            payload["time_range"] = self.time_range
        body = json.dumps(payload).encode("utf-8")
        attempts = 1 + self.max_retries
        for attempt in range(1, attempts + 1):
            try:
                response = self.opener(
                    f"{TAVILY_API_HOST}/search", self.timeout,
                    body=body, headers=self._headers(),
                )
                return self._read_results(response, query)
            except RateLimitedError as exc:
                if attempt < attempts and exc.retry_after:
                    logger.warning("tavily rate-limited, retrying once")
                    time.sleep(min(float(exc.retry_after), 60.0))
                    continue
                raise
            except TavilyError:
                raise
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
                raise NetworkError("network", f"transport failure ({type(exc).__name__})")
            except Exception as exc:  # defensive: never leak unexpected failures as success
                raise NetworkError("network", f"unexpected transport failure ({type(exc).__name__})")
        raise NetworkError("network", "exhausted retries")  # unreachable; guards the loop

    def _read_results(self, response, query: str) -> list:
        """Validate status, cap body, normalize results[] to SearchResults."""
        status = getattr(response, "status", None)
        if status is None and hasattr(response, "getcode"):
            try:
                status = response.getcode()
            except Exception:
                status = None
        headers = getattr(response, "headers", {}) or {}

        if status == 401:
            raise UnauthorizedError()
        if status == 429:
            raise RateLimitedError("HTTP 429 (rate limited)", retry_after=self._retry_after(headers))
        if status in (432, 433):
            raise RateLimitedError("plan limit exceeded (HTTP %s)" % status, retry_after=self._retry_after(headers))
        if status is not None and 500 <= status <= 599:
            raise ServerError("server", f"HTTP {status}")
        if status is not None and status != 200:
            raise MalformedError("bad_request", f"HTTP {status}")

        try:
            body = response.read(MAX_RESPONSE_BYTES + 1)
        except Exception as exc:
            raise NetworkError("network", f"failed reading response ({type(exc).__name__})")
        if len(body) > MAX_RESPONSE_BYTES:
            raise TavilyError("server", "response exceeded size cap")
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            raise MalformedError("malformed", "invalid JSON response")
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise MalformedError("malformed", "unexpected response shape")
        return [job for job in (self._normalize(item, query) for item in payload["results"]) if job is not None]

    @staticmethod
    def _normalize(item: object, query: str):
        """One result dict -> SearchResult (None for URL-less items)."""
        if not isinstance(item, dict):
            return None
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            return None  # a lead without a URL cannot become a target
        title = item.get("title")
        content = item.get("content")
        snippet = content if isinstance(content, str) else ""
        if len(snippet) > SNIPPET_MAX_CHARS:
            snippet = snippet[:SNIPPET_MAX_CHARS] + "…"
        score = item.get("score")
        published = item.get("published_date")
        return SearchResult(
            title=title if isinstance(title, str) else "",
            url=url.strip(),
            snippet=snippet,
            source_name="tavily",
            raw_data={
                "score": float(score) if isinstance(score, (int, float)) and not isinstance(score, bool) else None,
                "published_date": published if isinstance(published, str) else None,
                "query": query,
            },
        )

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

"""Gemini provider (Phase 5.2 — REST generation behind the Phase 1 abstraction).

Same BaseAIProvider contract (configure/generate); stdlib ``urllib`` against
the public Generative Language endpoint — no new dependencies. The API key
travels only in the request URL, is never logged, and never appears in error
messages (errors carry HTTP status/type only). Empty key = not configured;
generate() then raises instead of calling.
"""

import json
import os
import socket
import urllib.error
import urllib.request

from .base import AIRequest, AIResponse, BaseAIProvider

DEFAULT_MODEL = "gemini-2.5-flash"
GENERATIVE_ENDPOINT = "https://generativelanguage.googleapis.com"
MAX_RESPONSE_BYTES = 1 * 1024 * 1024


class GeminiError(Exception):
    """Typed Gemini failure (kind only — never credentials or key material)."""

    def __init__(self, kind: str, detail: str = "") -> None:
        super().__init__(f"gemini {kind}" + (f": {detail}" if detail else ""))
        self.kind = kind  # not_configured | timeout | rate_limited | bad_request | unauthorized | server | network | empty


class GeminiProvider(BaseAIProvider):
    """Gemini configuration + REST generation (server/worker-side only)."""

    name = "gemini"

    def __init__(self, api_key: str = "", model: str = "", timeout: float = 30.0) -> None:
        # Env-driven, no hardcoded secrets. Empty defaults = not configured.
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model or os.getenv("GEMINI_MODEL", "") or DEFAULT_MODEL
        try:
            self.timeout = max(1.0, min(120.0, float(timeout)))
        except (TypeError, ValueError):
            self.timeout = 30.0

    def is_configured(self) -> bool:
        """True when an API key is present (no network check)."""
        return bool(self.api_key and self.api_key.strip())

    def configure(self) -> None:
        """Validate presence of config only (no client init / no calls)."""
        if not self.is_configured():
            raise GeminiError("not_configured", "GEMINI_API_KEY is missing")

    def generate(self, request: AIRequest) -> AIResponse:
        """POST the prompt and return the model's text (raises GeminiError)."""
        if not self.is_configured():
            raise GeminiError("not_configured", "GEMINI_API_KEY is missing")
        body = json.dumps({
            "contents": [{"parts": [{"text": request.prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        }).encode("utf-8")
        # NOTE: key is in the URL per Google's API-key convention; never logged.
        url = f"{GENERATIVE_ENDPOINT}/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "AI-JobHunter/0.1 (+job-intelligence)",
            },
            method="POST",
        )
        try:
            response = urllib.request.urlopen(req, timeout=self.timeout)
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc.code)
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError):
            raise GeminiError("network", "transport failure")
        if len(raw) > MAX_RESPONSE_BYTES:
            raise GeminiError("server", "oversized response")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            raise GeminiError("server", "invalid JSON response")
        text = self._extract_text(payload)
        if not text.strip():
            raise GeminiError("empty", "model returned no text")
        return AIResponse(text=text)

    @staticmethod
    def _http_error(code: int) -> GeminiError:
        """Map HTTP status to a credential-free error kind."""
        if code == 429:
            return GeminiError("rate_limited", "HTTP 429")
        if code in (401, 403):
            return GeminiError("unauthorized", f"HTTP {code}")
        if code == 400:
            return GeminiError("bad_request", "HTTP 400")
        if 500 <= code <= 599:
            return GeminiError("server", f"HTTP {code}")
        return GeminiError("server", f"HTTP {code}")

    @staticmethod
    def _extract_text(payload: dict) -> str:
        """Join candidate parts text ("" when the shape is unexpected)."""
        try:
            parts = payload["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        except (KeyError, IndexError, TypeError, AttributeError):
            return ""

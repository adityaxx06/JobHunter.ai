"""Himalayas connector configuration (Phase 10C-2, env-driven, no secrets).

The public Himalayas Remote Jobs API needs no API key: free, no signup,
documented at https://himalayas.app/docs/remote-jobs-api. Keywords and
employment types are plain search facets — safe to log; nothing secret here.
"""

import logging
import os

logger = logging.getLogger("ai-jobhunter.himalayas.config")

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_KEYWORDS = 5
USER_AGENT = "AI-JobHunter/0.1 (+job-discovery; conservative; contact via repo)"


def _parse_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _parse_float(value: object, default: float) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def _parse_int(value: object, default: int) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _get(env: object, key: str, default: str = "") -> str:
    if env is None:
        return os.environ.get(key, default)
    get = env.get if hasattr(env, "get") else (lambda k, d="": os.environ.get(k, d))
    return get(key, default)


def is_enabled(env: object = None) -> bool:
    """True only when HIMALAYA_ENABLED is explicitly truthy (default off)."""
    return _parse_bool(_get(env, "HIMALAYA_ENABLED", ""), default=False)


def get_keywords(env: object = None) -> list:
    """Search keywords (``;``/``,`` separated, deduped, capped at 5).

    Example: ``HIMALAYA_KEYWORDS=intern;software engineer intern``.
    Empty by default: an enabled source with no keywords stays idle.
    """
    raw = _get(env, "HIMALAYA_KEYWORDS", "") or ""
    keywords = []
    seen = set()
    for chunk in raw.replace(",", ";").split(";"):
        token = chunk.strip()
        if token and token.lower() not in seen:
            seen.add(token.lower())
            keywords.append(token)
    if len(keywords) > DEFAULT_MAX_KEYWORDS:
        logger.warning("himalaya: %d keywords configured, keeping first %d",
                       len(keywords), DEFAULT_MAX_KEYWORDS)
        keywords = keywords[:DEFAULT_MAX_KEYWORDS]
    return keywords


def get_employment_types(env: object = None) -> list:
    """Employment-type filter values (default ``Intern``; empty disables)."""
    raw = _get(env, "HIMALAYA_EMPLOYMENT_TYPES", "Intern") or ""
    values = []
    for chunk in raw.replace(",", ";").split(";"):
        token = chunk.strip()
        if token and token not in values:
            values.append(token)
    return values


def get_timeout(env: object = None) -> float:
    """Per-request timeout in seconds (default 10, clamped to 1..120)."""
    timeout = _parse_float(_get(env, "HIMALAYA_TIMEOUT", DEFAULT_TIMEOUT_SECONDS), DEFAULT_TIMEOUT_SECONDS)
    return max(1.0, min(120.0, timeout))

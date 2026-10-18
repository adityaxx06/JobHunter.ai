"""Jobicy connector configuration (Phase 10C-3, env-driven, no secrets).

The public Jobicy Remote Jobs API needs no API key: free, no signup,
documented at https://jobicy.com/jobs-rss-feed. Tags/geo/industry are plain
search facets — safe to log; nothing secret here. The paid commercial tier
(direct ATS links, $0.01/job) is deliberately NOT used: the free listing URL
is the canonical, attributable link.
"""

import logging
import os

logger = logging.getLogger("ai-jobhunter.jobicy.config")

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_TAGS = 5
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


def _get(env: object, key: str, default: str = "") -> str:
    if env is None:
        return os.environ.get(key, default)
    get = env.get if hasattr(env, "get") else (lambda k, d="": os.environ.get(k, d))
    return get(key, default)


def is_enabled(env: object = None) -> bool:
    """True only when JOBICY_ENABLED is explicitly truthy (default off)."""
    return _parse_bool(_get(env, "JOBICY_ENABLED", ""), default=False)


def _split_list(raw: object) -> list:
    """Split ``;``/``,`` values, trim, drop empties (case-insensitive dedupe)."""
    values = []
    seen = set()
    for chunk in str(raw or "").replace(",", ";").split(";"):
        token = chunk.strip()
        if token and token.lower() not in seen:
            seen.add(token.lower())
            values.append(token)
    return values


def get_tags(env: object = None) -> list:
    """Keyword tags (``;``/``,`` separated, deduped, capped at 5).

    Example: ``JOBICY_TAGS=python;intern``. Empty by default: an enabled
    source with no tags stays idle.
    """
    tags = _split_list(_get(env, "JOBICY_TAGS", ""))
    if len(tags) > DEFAULT_MAX_TAGS:
        logger.warning("jobicy: %d tags configured, keeping first %d",
                       len(tags), DEFAULT_MAX_TAGS)
        tags = tags[:DEFAULT_MAX_TAGS]
    return tags


def get_geo(env: object = None) -> str:
    """Geography slug filter (default empty = no filter)."""
    return _get(env, "JOBICY_GEO", "").strip()


def get_industry(env: object = None) -> str:
    """Industry slug filter (default empty = no filter)."""
    return _get(env, "JOBICY_INDUSTRY", "").strip()


def get_timeout(env: object = None) -> float:
    """Per-request timeout in seconds (default 10, clamped to 1..120)."""
    timeout = _parse_float(_get(env, "JOBICY_TIMEOUT", DEFAULT_TIMEOUT_SECONDS), DEFAULT_TIMEOUT_SECONDS)
    return max(1.0, min(120.0, timeout))

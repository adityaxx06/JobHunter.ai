"""Search-provider configuration (Phase 4.3, env-driven).

SEARCH_API_KEY is read here and nowhere else. It is never logged, never
returned in messages, and never sent anywhere except a future real provider's
authenticated requests. Empty by default: the app works proof-of-concept-free
with the mock provider and reports "not configured" otherwise.
"""

import logging
import os

logger = logging.getLogger("ai-jobhunter.search.config")

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RESULTS = 20

# Controlled ingestion (Phase 6.1): tiny defaults protect Tavily credits and
# keep ATS traffic conservative. Queries x results bound discovery; boards
# bound downstream ATS fetches (boards deduped before fetching).
DEFAULT_MAX_INGESTION_QUERIES = 3
DEFAULT_MAX_INGESTION_BOARDS = 5
# Per-board job cap for ingestion (Phase 6.3A controlled runs). Default 50
# preserves the exact pre-existing behavior; set lower (e.g. 10) to bound a
# live sample without touching connector or persistence code.
DEFAULT_MAX_INGESTION_JOBS_PER_BOARD = 50

# Tavily depths per the public API (basic/fast/ultra-fast = 1 credit,
# advanced = 2 credits). Default basic keeps the free tier alive.
TAVILY_DEPTHS = ("basic", "advanced", "fast", "ultra-fast")
DEFAULT_TAVILY_DEPTH = "basic"

# Tavily time ranges per the public API (day/week/month/year). Unset by
# default: no date filtering, undated results (e.g. LinkedIn) are kept.
TAVILY_TIME_RANGES = ("day", "week", "month", "year")


def _get(env: object, key: str, default: str = "") -> str:
    if env is None:
        return os.environ.get(key, default)
    get = env.get if hasattr(env, "get") else (lambda k, d="": os.environ.get(k, d))
    return get(key, default)


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


def is_enabled(env: object = None) -> bool:
    """True only when SEARCH_ENABLED is explicitly truthy (default off)."""
    return _parse_bool(_get(env, "SEARCH_ENABLED", ""), default=False)


def get_provider_name(env: object = None) -> str:
    """Configured provider key (default "mock"; never a secret)."""
    return _get(env, "SEARCH_PROVIDER", "mock").strip().lower() or "mock"


def get_api_key(env: object = None) -> str:
    """Configured key for real providers ("" when absent). Handle with care."""
    return _get(env, "SEARCH_API_KEY", "")


def has_api_key(env: object = None) -> bool:
    """Whether any key is configured (no value exposed)."""
    return bool(get_api_key(env).strip())


def get_timeout(env: object = None) -> float:
    """Per-request timeout in seconds (default 10, clamped to 1..120)."""
    timeout = _parse_float(_get(env, "SEARCH_TIMEOUT", DEFAULT_TIMEOUT_SECONDS), DEFAULT_TIMEOUT_SECONDS)
    return max(1.0, min(120.0, timeout))


def get_max_results(env: object = None) -> int:
    """Per-query result cap (default 20, clamped to 1..50)."""
    return max(1, min(50, _parse_int(_get(env, "SEARCH_MAX_RESULTS", DEFAULT_MAX_RESULTS), DEFAULT_MAX_RESULTS)))


def get_tavily_key(env: object = None) -> str:
    """Tavily API key ("" when absent). Server-side only — handle with care."""
    return _get(env, "TAVILY_API_KEY", "")


def has_tavily_key(env: object = None) -> bool:
    """Whether a Tavily key is configured (no value exposed)."""
    return bool(get_tavily_key(env).strip())


def get_tavily_depth(env: object = None) -> str:
    """Tavily search depth (validated; invalid values fall back to basic)."""
    depth = _get(env, "TAVILY_SEARCH_DEPTH", DEFAULT_TAVILY_DEPTH).strip().lower()
    return depth if depth in TAVILY_DEPTHS else DEFAULT_TAVILY_DEPTH


def get_tavily_time_range(env: object = None) -> str:
    """Tavily time range, or "" when unconfigured (validated).

    Unset (or invalid, which safely falls back to unset) means no date
    filtering — existing request behavior is preserved byte-for-byte and
    undated results are kept. Strict publication-date filtering
    (``filter_by_published_date``) is never enabled by this project because
    it would silently drop useful undated LinkedIn results.
    """
    value = _get(env, "TAVILY_TIME_RANGE", "").strip().lower()
    return value if value in TAVILY_TIME_RANGES else ""


def is_live_ingestion_enabled(env: object = None) -> bool:
    """True only when ENABLE_LIVE_INGESTION is explicitly truthy (default off)."""
    return _parse_bool(_get(env, "ENABLE_LIVE_INGESTION", ""), default=False)


def get_max_ingestion_queries(env: object = None) -> int:
    """Search queries per ingestion run (default 3, clamped to 1..10)."""
    return max(1, min(10, _parse_int(_get(env, "MAX_INGESTION_QUERIES", DEFAULT_MAX_INGESTION_QUERIES), DEFAULT_MAX_INGESTION_QUERIES)))


def get_max_ingestion_boards(env: object = None) -> int:
    """Distinct ATS boards fetched per ingestion run (default 5, 1..20)."""
    return max(1, min(20, _parse_int(_get(env, "MAX_INGESTION_BOARDS", DEFAULT_MAX_INGESTION_BOARDS), DEFAULT_MAX_INGESTION_BOARDS)))


def get_max_ingestion_jobs_per_board(env: object = None) -> int:
    """Jobs taken per ATS board per run (default 50, clamped to 1..50)."""
    return max(1, min(50, _parse_int(_get(env, "MAX_INGESTION_JOBS_PER_BOARD", DEFAULT_MAX_INGESTION_JOBS_PER_BOARD), DEFAULT_MAX_INGESTION_JOBS_PER_BOARD)))

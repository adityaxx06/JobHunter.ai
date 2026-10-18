"""Lever connector configuration (Phase 4.2B, env-driven, no secrets).

Public Lever postings need no API key. Company identifiers are the public
handles in a company's Lever board URL — safe to log; nothing secret here.
"""

import logging
import os

logger = logging.getLogger("ai-jobhunter.lever.config")

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_BOARDS = 10
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


def is_enabled(env: object = None) -> bool:
    """True only when LEVER_ENABLED is explicitly truthy (default off)."""
    source = os.environ if env is None else env
    get = source.get if hasattr(source, "get") else (lambda k, d="": os.environ.get(k, d))
    return _parse_bool(get("LEVER_ENABLED", ""), default=False)


def get_boards(env: object = None) -> list:
    """Configured public Lever company identifiers (``;``/``,`` separated).

    Example: ``LEVER_BOARDS=company-one;company-two``. Empty entries are
    ignored, whitespace trimmed, duplicates removed (order preserved), and
    the total is capped at LEVER_MAX_BOARDS (default 10).
    """
    source = os.environ if env is None else env
    get = source.get if hasattr(source, "get") else (lambda k, d="": os.environ.get(k, d))
    raw = get("LEVER_BOARDS", "") or ""
    boards = []
    for chunk in raw.replace(",", ";").split(";"):
        token = chunk.strip().lower()
        if token and token not in boards:
            boards.append(token)
    max_boards = _parse_int(get("LEVER_MAX_BOARDS", DEFAULT_MAX_BOARDS), DEFAULT_MAX_BOARDS)
    if len(boards) > max_boards:
        logger.warning("lever: %d boards configured, keeping first %d", len(boards), max_boards)
        boards = boards[:max_boards]
    return boards


def get_timeout(env: object = None) -> float:
    """Per-request timeout in seconds (default 10, clamped to 1..120)."""
    source = os.environ if env is None else env
    get = source.get if hasattr(source, "get") else (lambda k, d="": os.environ.get(k, d))
    timeout = _parse_float(get("LEVER_TIMEOUT", DEFAULT_TIMEOUT_SECONDS), DEFAULT_TIMEOUT_SECONDS)
    return max(1.0, min(120.0, timeout))

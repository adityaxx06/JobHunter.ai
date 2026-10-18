"""Intelligence feature flags and cost guards (Phase 5.2, env-driven).

AI_ENABLED defaults to false: nothing consumes Gemini quota unless the
operator opts in explicitly. AI_MAX_JOBS_PER_RUN caps billable calls per run.
No secrets live here — GEMINI_API_KEY is read only by the provider itself.
"""

import os


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _parse_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _parse_int(value: object, default: int) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _parse_float(value: object, default: float) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def is_ai_enabled() -> bool:
    """True only when AI_ENABLED is explicitly truthy (default off)."""
    return _parse_bool(_get("AI_ENABLED", ""), default=False)


def max_jobs_per_run() -> int:
    """Billable AI calls allowed per run (default 20, clamped to 1..100)."""
    return max(1, min(100, _parse_int(_get("AI_MAX_JOBS_PER_RUN", "20"), 20)))


def request_timeout() -> float:
    """Per-request seconds for Gemini calls (default 30, clamped 5..120)."""
    return max(5.0, min(120.0, _parse_float(_get("AI_REQUEST_TIMEOUT_SECONDS", "30"), 30.0)))


def run_intelligence_enabled() -> bool:
    """True only when RUN_INTELLIGENCE is explicitly truthy (default off)."""
    return _parse_bool(_get("RUN_INTELLIGENCE", ""), default=False)


def persist_enabled() -> bool:
    """True only when PERSIST_DISCOVERY is explicitly truthy (default off)."""
    return _parse_bool(_get("PERSIST_DISCOVERY", ""), default=False)


def allow_mock_persist() -> bool:
    """True only when ALLOW_MOCK_PERSIST is explicitly truthy (default off)."""
    return _parse_bool(_get("ALLOW_MOCK_PERSIST", ""), default=False)

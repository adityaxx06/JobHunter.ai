"""Database health probing (Phase 3).

Returns a plain status string; never exposes credentials or connection details.
"""

import logging

logger = logging.getLogger("ai-jobhunter.db.health")


def check_database() -> str:
    """Probe PostgreSQL reachability.

    Returns:
        "connected" — SELECT 1 succeeded.
        "not_configured" — DATABASE_URL is missing.
        "unreachable" — configured but the probe failed (details logged
        without credentials).
    """
    from app.db import connection as db

    if not db.is_configured():
        return "not_configured"
    try:
        row = db.fetch_one("SELECT 1 AS ok")
        return "connected" if row and row.get("ok") == 1 else "unreachable"
    except Exception as exc:
        logger.warning("database probe failed: %s", type(exc).__name__)
        return "unreachable"

"""Safe PostgreSQL connection helper (psycopg v3, Phase 3).

Rules enforced here:
- Parameterized queries only: callers pass ``params`` separately; this module
  never formats user values into SQL text.
- Lazy connection pool: created on first use, only when DATABASE_URL is set.
  The app imports and starts fine without any database configured.
- Commit on success for writes, rollback on error.
- Error logging never includes credentials, DATABASE_URL, or API keys.

No Supabase service-role key is required: plain PostgreSQL work uses
DATABASE_URL alone.
"""

import logging
from typing import Any, Optional, Sequence

logger = logging.getLogger("ai-jobhunter.db")

_pool = None


def _load_pool():
    """Create (once) and return the connection pool, or None if unconfigured."""
    global _pool
    if _pool is not None:
        return _pool
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.is_database_configured:
        return None
    try:
        from psycopg_pool import ConnectionPool
    except ImportError:  # pragma: no cover - dependency present via requirements
        logger.error("psycopg pool support is not installed.")
        return None
    # NOTE: the connection string is passed to the driver only; never logged.
    _pool = ConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=5,
        timeout=10,
        kwargs={"connect_timeout": 5},
    )
    return _pool


def is_configured() -> bool:
    """True when DATABASE_URL is present (does not test connectivity)."""
    from app.core.config import get_settings

    return get_settings().is_database_configured


def fetch_one(sql: str, params: Optional[Sequence[Any]] = None) -> Optional[dict]:
    """Run a SELECT expected to return zero or one row (dict or None)."""
    from psycopg.rows import dict_row

    pool = _load_pool()
    if pool is None:
        raise RuntimeError("database not configured (DATABASE_URL is missing)")
    try:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                return cur.fetchone()
    except Exception as exc:
        logger.error("db fetch_one failed: %s", type(exc).__name__)
        raise


def fetch_all(sql: str, params: Optional[Sequence[Any]] = None) -> list:
    """Run a SELECT returning all rows as a list of dicts."""
    from psycopg.rows import dict_row

    pool = _load_pool()
    if pool is None:
        raise RuntimeError("database not configured (DATABASE_URL is missing)")
    try:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())
    except Exception as exc:
        logger.error("db fetch_all failed: %s", type(exc).__name__)
        raise


def execute(sql: str, params: Optional[Sequence[Any]] = None) -> Optional[dict]:
    """Run an INSERT/UPDATE/DELETE; commits on success, rolls back on error.

    Returns the ``RETURNING`` row as a dict when the statement has one,
    otherwise None.
    """
    from psycopg.rows import dict_row

    pool = _load_pool()
    if pool is None:
        raise RuntimeError("database not configured (DATABASE_URL is missing)")
    try:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                row = cur.fetchone() if cur.description is not None else None
            conn.commit()
            return dict(row) if row is not None else None
    except Exception as exc:
        logger.error("db execute failed: %s", type(exc).__name__)
        raise


def close_pool() -> None:
    """Close the pool (tests / shutdown). Safe to call when never opened."""
    global _pool
    if _pool is not None:
        try:
            _pool.close()
        except Exception:
            pass
        _pool = None

"""Worker database client (Phase 3 — connection layer only).

Reusable psycopg access for the future discover -> normalize -> deduplicate ->
save -> match pipeline. No discovery logic here. Reads DATABASE_URL from the
environment (same variable as the backend); never logs credentials.
Requires: pip install "psycopg[binary]"
"""

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator, Optional, Sequence

logger = logging.getLogger("ai-jobhunter-worker.db")

# NOTE: the cache variable MUST NOT be named `_pool` — that name belongs to
# the `_pool()` factory below, and sharing it silently rebinds the global to
# the function itself (all pool users then receive a function, not a pool).
_POOL = None


def is_configured() -> bool:
    """True when DATABASE_URL is present (no connectivity test)."""
    return bool(os.getenv("DATABASE_URL", "").strip())


def _pool():
    """Lazily create the worker pool (None when unconfigured)."""
    global _POOL
    if _POOL is not None:
        return _POOL
    if not is_configured():
        return None
    from psycopg_pool import ConnectionPool

    _POOL = ConnectionPool(
        os.environ["DATABASE_URL"],
        min_size=1,
        max_size=3,
        timeout=10,
        kwargs={"connect_timeout": 5},
    )
    return _POOL


def fetch_one(sql: str, params: Optional[Sequence[Any]] = None) -> Optional[dict]:
    """Parameterized single-row fetch (dict or None)."""
    from psycopg.rows import dict_row

    pool = _pool()
    if pool is None:
        raise RuntimeError("database not configured (DATABASE_URL is missing)")
    try:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                return cur.fetchone()
    except Exception as exc:
        logger.error("worker db fetch_one failed: %s", type(exc).__name__)
        raise


def fetch_all(sql: str, params: Optional[Sequence[Any]] = None) -> list:
    """Parameterized multi-row fetch (list of dicts)."""
    from psycopg.rows import dict_row

    pool = _pool()
    if pool is None:
        raise RuntimeError("database not configured (DATABASE_URL is missing)")
    try:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())
    except Exception as exc:
        logger.error("worker db fetch_all failed: %s", type(exc).__name__)
        raise


def execute(sql: str, params: Optional[Sequence[Any]] = None) -> Optional[dict]:
    """Parameterized write with commit/rollback; returns RETURNING row if any."""
    from psycopg.rows import dict_row

    pool = _pool()
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
        logger.error("worker db execute failed: %s", type(exc).__name__)
        raise


def check_connection() -> str:
    """'connected' | 'not_configured' | 'unreachable' (no details leaked)."""
    if not is_configured():
        return "not_configured"
    try:
        row = fetch_one("SELECT 1 AS ok")
        return "connected" if row and row.get("ok") == 1 else "unreachable"
    except Exception as exc:
        logger.warning("worker db probe failed: %s", type(exc).__name__)
        return "unreachable"


@contextmanager
def transaction() -> Iterator[Any]:
    """Yield a cursor bound to one connection; commit on success, rollback on error.

    All statements for a single job (company + job + source link) run inside
    one ``with`` block so failures never leave orphaned records. Parameterized
    use only — this helper never formats values into SQL.
    """
    from psycopg.rows import dict_row

    pool = _pool()
    if pool is None:
        raise RuntimeError("database not configured (DATABASE_URL is missing)")
    try:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                yield cur
            conn.commit()
    except Exception as exc:
        # pool.connection() rolls back the open transaction on exit.
        logger.error("worker db transaction rolled back: %s", type(exc).__name__)
        raise

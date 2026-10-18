"""Database health endpoint (Phase 3). No credentials exposed."""

from fastapi import APIRouter

from app.db.health import check_database

router = APIRouter()


@router.get("/db/health")
def db_health() -> dict:
    """Report PostgreSQL reachability without leaking connection details."""
    status = check_database()
    if status == "connected":
        return {"status": "ok", "database": "connected"}
    return {"status": status, "database": status}

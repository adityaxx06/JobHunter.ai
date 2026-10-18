"""Ranking service: thin bridge from FastAPI to the worker pipeline (Phase 5.4).

Route -> this service -> existing worker ranking (repository + deterministic
scorer) -> database. No scoring logic lives here, no Gemini is ever called,
and no jobs are modified. The worker package is imported via a repo-root path
bootstrap so the backend reuses the exact Phase 5.3 pipeline (no duplication).
"""

import os
import sys

# Repo root (parent of backend/) so `worker.*` resolves when uvicorn runs
# with backend/ as the working directory. Tests import this module too.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from worker.models.ranking import RankingFilter  # noqa: E402
from worker.pipelines import ranking_pipeline as pipeline  # noqa: E402

from app.core.config import get_settings  # noqa: E402


def ensure_worker_db_config() -> None:
    """Bridge FastAPI's configured DATABASE_URL into the worker layer.

    Root cause of the ranking 503: backend Settings load DATABASE_URL from the
    project's ``.env`` file, while ``worker/db/client.py`` reads only process
    ``os.environ``. When uvicorn is launched without the variable exported,
    the worker pipeline sees "not configured" even though FastAPI is healthy.

    This copies the already-configured backend value into process env with
    setdefault semantics (never overrides an explicit env var, never logs the
    value). The worker itself is untouched and stays independently runnable.
    """
    if os.getenv("DATABASE_URL", "").strip():
        return
    settings = get_settings()
    if settings.is_database_configured:
        os.environ["DATABASE_URL"] = settings.database_url


def rank_jobs_for_profile(profile_id=None, limit=20, min_match_score=None,
                           min_trust_score=None, filters=None, eligible_only=False):
    """Delegate to the existing worker pipeline with config bridged (no AI)."""
    ensure_worker_db_config()
    return pipeline.rank_jobs_for_profile(
        profile_id, limit=limit, min_match_score=min_match_score,
        min_trust_score=min_trust_score, filters=filters,
        eligible_only=bool(eligible_only),
    )


def build_filter(min_match_score=None, min_trust_score=None, recommendation=None,
                 employment_type=None, location=None, remote=None) -> RankingFilter:
    """Assemble the worker filter from validated API query params."""
    return RankingFilter(
        min_match_score=min_match_score,
        min_trust_score=min_trust_score,
        recommendation=recommendation,
        employment_type=employment_type,
        location=location,
        remote=remote,
    )

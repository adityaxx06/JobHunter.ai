"""AI-JobHunter backend entrypoint (FastAPI, Phase 5.4).

Read-only dashboard API over Supabase PostgreSQL: jobs, matches, deterministic
ranking (worker pipeline, zero AI calls), applications. The app starts with
DATABASE_URL unset; DB endpoints then report "not_configured" instead of
failing at import. No discovery, scoring, auth, or AI calls.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import applications, db, jobs, matches, profile, rankings, saved
from app.core.config import get_settings

app = FastAPI(title="AI-JobHunter API", version="0.3.0")

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.frontend_url.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(db.router, prefix="/api", tags=["system"])
app.include_router(profile.router, prefix="/api", tags=["profiles"])
app.include_router(jobs.router, prefix="/api", tags=["jobs"])
app.include_router(matches.router, prefix="/api", tags=["matches"])
app.include_router(rankings.router, prefix="/api", tags=["rankings"])
app.include_router(applications.router, prefix="/api", tags=["applications"])
app.include_router(saved.router, prefix="/api", tags=["saved"])


@app.get("/api/health")
def health() -> dict:
    """Health check (unchanged since Phase 1)."""
    return {"status": "ok", "service": "AI-JobHunter API"}

"""Backend configuration via environment variables.

No secrets hardcoded. All values load from env / .env.
DATABASE_URL drives PostgreSQL access (backend + worker).
SUPABASE_SERVICE_ROLE_KEY is backend-only and only needed for Supabase API
operations — plain PostgreSQL work uses DATABASE_URL alone.
The app starts with DATABASE_URL unset; DB features report "not_configured".
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings (Phase 3 — DB layer, no auth/discovery/AI)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # API
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # CORS: explicit local frontend origin(s), comma-separated. Never "*"
    # together with credentials; production stays configurable via env.
    frontend_url: str = "http://localhost:3000"

    # Database: Supabase-hosted PostgreSQL connection string (server-side only).
    database_url: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # AI (server-side only — never expose to Next.js client)
    gemini_api_key: str = ""
    gemini_model: str = ""

    @property
    def is_database_configured(self) -> bool:
        """True only when a connection string is actually provided."""
        return bool(self.database_url and self.database_url.strip())


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()

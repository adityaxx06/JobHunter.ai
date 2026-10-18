"""Provider credential readiness (Phase 6.0). Presence checks only.

Answers YES/NO for Tavily, Gemini (key + model separately), database, and
the selected search provider — without network calls, AI calls, credits,
or writes. Nothing secret ever appears in the report.
"""

from dataclasses import dataclass

from worker.search import config as search_config


@dataclass
class SearchReadiness:
    """Credential/config presence snapshot (booleans + safe detail strings)."""

    tavily_configured: bool = False
    tavily_detail: str = ""
    gemini_configured: bool = False
    gemini_model_set: bool = False
    database_configured: bool = False
    search_provider: str = "mock"


def get_readiness() -> SearchReadiness:
    """Collect readiness without touching network, credits, or the database."""
    from ai.providers.gemini import GeminiProvider
    from worker.db import client as db_client

    gemini = GeminiProvider()
    provider = search_config.get_provider_name()
    tavily = search_config.has_tavily_key()
    return SearchReadiness(
        tavily_configured=tavily,
        tavily_detail=(
            "TAVILY_API_KEY present" if tavily else "TAVILY_API_KEY missing"
        ),
        gemini_configured=gemini.is_configured(),
        gemini_model_set=bool(gemini.model and gemini.model.strip()),
        database_configured=db_client.is_configured(),
        search_provider=provider,
    )


def format_readiness(readiness: SearchReadiness) -> str:
    """Render the report (YES/NO lines; never secrets)."""
    yes_no = lambda flag: "YES" if flag else "NO"  # noqa: E731 - tiny local helper
    lines = [
        "",
        "## Provider Readiness",
        "",
        f"Tavily configured:   {yes_no(readiness.tavily_configured)} ({readiness.tavily_detail})",
        f"Gemini configured:   {yes_no(readiness.gemini_configured)}",
        f"Gemini model set:    {yes_no(readiness.gemini_model_set)}",
        f"Database configured: {yes_no(readiness.database_configured)}",
        f"Search provider:     {readiness.search_provider}",
        "",
    ]
    if readiness.search_provider == "tavily" and not readiness.tavily_configured:
        lines.append("note: SEARCH_PROVIDER=tavily but TAVILY_API_KEY is missing — "
                     "searches will report a configuration error, not silently fall back")
        lines.append("")
    return "\n".join(lines)

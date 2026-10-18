"""Search-provider registry (Phase 4.3). Separate from the JobSource registry.

Providers register by unique ``provider_name``. The search pipeline reads
only from here, so a future real provider plugs in with one registration —
no pipeline changes. The mock provider is registered on import.
"""

from typing import Optional

from worker.search.base import SearchProvider

_providers: dict = {}


def register_provider(provider: SearchProvider) -> SearchProvider:
    """Register (or replace) a provider by its ``provider_name``."""
    if not getattr(provider, "provider_name", ""):
        raise ValueError("provider must define a non-empty provider_name")
    _providers[provider.provider_name] = provider
    return provider


def get_provider(name: str) -> Optional[SearchProvider]:
    """Return the provider registered as ``name`` (None when unknown)."""
    return _providers.get(name)


def get_all_providers() -> list:
    """All registered providers in registration order."""
    return list(_providers.values())


def clear_providers() -> None:
    """Remove all registrations (tests only)."""
    _providers.clear()


def _register_builtin_providers() -> None:
    """Register mock (always) + Tavily (disabled-safe: no key, no network)."""
    from worker.search.mock_provider import MockSearchProvider
    from worker.search.tavily import TavilySearchProvider

    register_provider(MockSearchProvider())
    register_provider(TavilySearchProvider())


_register_builtin_providers()

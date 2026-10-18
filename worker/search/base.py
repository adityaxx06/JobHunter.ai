"""Search-provider contract (Phase 4.3). Deliberately separate from JobSource.

A SearchProvider returns *leads* (SearchResult), never canonical jobs. Future
providers (official search APIs, authorized providers, curated feeds) plug in
here. No HTML scraping of search engines belongs in any provider.
"""

from abc import ABC, abstractmethod

from worker.models.search import SearchHealth, SearchResult


class SearchProvider(ABC):
    """Abstract search provider. Searches; the pipeline classifies."""

    #: Unique registry key (e.g. "mock").
    provider_name: str = ""

    @abstractmethod
    def search(self, query: str, max_results: int = 20) -> list:
        """Return up to ``max_results`` :class:`SearchResult` for ``query``.

        Must never raise for empty results — return []. May raise on
        transport/config errors; the pipeline isolates per-query failures.
        """
        raise NotImplementedError

    def health_check(self) -> SearchHealth:
        """Self check (default: healthy). Override for live providers."""
        return SearchHealth(ok=True, message=f"{self.provider_name or type(self).__name__} ready")

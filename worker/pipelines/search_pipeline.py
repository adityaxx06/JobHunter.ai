"""Search-discovery pipeline: profile -> queries -> provider -> targets (Phase 4.3).

Flow: load the candidate's SearchProfile from the database (defaults when
offline), generate bounded queries from it, execute each against the
provider, dedupe results by URL, classify into discovery targets. One failed
query never crashes a run — failures are captured per query and execution
continues. The mock provider keeps the default run offline; Tavily
(Phase 6.0) runs only when SEARCH_PROVIDER=tavily with a configured key.
"""

import logging
from typing import Optional

from worker.models.search import SearchPipelineResult
from worker.search import config as search_config
from worker.search import registry as search_registry
from worker.search.classifier import UNKNOWN, classify_results
from worker.search.query_generator import SearchProfile, generate_queries, load_search_profile
from worker.sources.resolver import normalize_url as _canonical_url

logger = logging.getLogger("ai-jobhunter.search")


def _normalize_url(url: object) -> str:
    """URL identity for dedup: the shared canonical form (host-lowercased,
    fragments dropped, tracking params stripped, trailing slash trimmed).

    Reuses the resolver's canonicalizer so pipeline dedup and ATS resolution
    agree on identity — e.g. tracking/fragments variants collapse to one.
    """
    try:
        return _canonical_url(url)
    except Exception:
        return ""


def run_search_discovery(
    profile: Optional[SearchProfile] = None,
    provider=None,
    max_queries: int = 10,
    max_results_per_query: Optional[int] = None,
) -> SearchPipelineResult:
    """Run query generation -> provider search -> classification -> targets.

    A None profile loads the candidate's SearchProfile from the database
    (module defaults when offline) so live discovery follows profile edits.
    """
    profile = profile or load_search_profile()
    if provider is None:
        provider = search_registry.get_provider(search_config.get_provider_name()) or search_registry.get_provider("mock")

    result = SearchPipelineResult()
    queries = generate_queries(profile, max_queries=max_queries)
    result.queries_generated = len(queries)
    per_query = max_results_per_query if max_results_per_query is not None else search_config.get_max_results()

    seen_urls = set()
    unique_results = []
    for item in queries:
        try:
            hits = provider.search(item.query, max_results=per_query) or []
        except Exception as exc:
            message = f"query failed ({item.query!r}): {type(exc).__name__}: {exc}"
            result.errors.append(message)
            logger.warning("search %s", message)
            continue
        result.queries_executed += 1
        result.results_found += len(hits)
        for hit in hits:
            key = _normalize_url(getattr(hit, "url", ""))
            if key and key not in seen_urls:
                seen_urls.add(key)
                unique_results.append(hit)

    targets = classify_results(unique_results)
    result.targets = targets
    result.targets_found = len(targets)
    # Junk URLs are dropped inside classify_results; the difference is the
    # observable junk count (classification behavior itself is unchanged).
    result.junk_removed = len(unique_results) - len(targets)
    stats: dict = {}
    for target in targets:
        stats[target.classified_source] = stats.get(target.classified_source, 0) + 1
    stats.setdefault(UNKNOWN, 0)
    result.classification_stats = stats
    return result

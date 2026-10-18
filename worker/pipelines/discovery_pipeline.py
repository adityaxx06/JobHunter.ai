"""Discovery pipeline: sources -> normalize -> deduplicate (Phase 4.1).

Produces a :class:`DiscoveryResult` (counts, unique jobs, errors, per-source
stats). One broken source never crashes a run: discovery and per-job
normalization failures are captured and the pipeline continues. No network
is required when only the mock source is registered; no AI is used.
"""

import logging
from typing import Optional

from worker.models.job import DiscoveryResult, SourceStats
from worker.processors.deduplicator.job_deduplicator import deduplicate_jobs
from worker.processors.normalizer.job_normalizer import normalize_job

logger = logging.getLogger("ai-jobhunter.discovery")


def run_discovery(
    sources: Optional[list] = None,
    query: str = "",
    location: str = "",
    limit_per_source: int = 50,
) -> DiscoveryResult:
    """Run discovery across sources and return the structured result."""
    if sources is None:
        from worker.sources import registry as registry_module

        sources = registry_module.get_all_sources()

    result = DiscoveryResult()
    normalized = []

    for source in sources:
        stats = SourceStats(name=source.source_name, type=source.source_type)
        try:
            discovered = source.discover_jobs(query=query, location=location, limit=limit_per_source) or []
        except Exception as exc:
            stats.status = "error"
            stats.error = f"{type(exc).__name__}: {exc}"
            result.errors.append(f"source '{source.source_name}' failed: {stats.error}")
            logger.warning("source '%s' failed: %s", source.source_name, stats.error)
            result.source_stats.append(stats)
            continue
        stats.discovered = len(discovered)
        result.discovered_count += len(discovered)

        for job in discovered:
            try:
                normalized.append(normalize_job(job))
            except Exception as exc:
                message = f"normalize failed for '{source.source_name}': {type(exc).__name__}: {exc}"
                result.errors.append(message)
                logger.warning("%s", message)
        result.source_stats.append(stats)

    result.normalized_count = len(normalized)
    deduped = deduplicate_jobs(normalized)
    result.unique_count = len(deduped.unique_jobs)
    result.jobs = deduped.unique_jobs
    if deduped.duplicate_count:
        result.errors.append(f"removed {deduped.duplicate_count} duplicate(s)")
    return result

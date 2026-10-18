"""Controlled ATS ingestion: search -> resolve -> ATS -> persist (Phase 6.1).

Flow: run the existing search discovery (Tavily credits bounded by the query
cap), resolve targets with worker/sources/resolver.py, fetch each distinct
ATS board ONCE through the existing Greenhouse/Lever/Ashby sources, normalize
with the existing normalizer, dedupe with the existing fingerprint logic, and
persist through the existing repository.

What this pipeline NEVER does: AI calls (the ai package is not even
imported), ranking, notifications, auto-apply, generic URL fetching (only the
ATS clients' fixed API hosts are ever contacted, with extracted handles), or
company_career/unknown scraping (those stay queued).

Persistence is doubly gated: ``persist_requested`` (explicit CLI --persist)
AND the existing PERSIST_DISCOVERY flag AND the new ENABLE_LIVE_INGESTION
flag AND a configured database. Anything missing -> honest dry run with zero
writes. Per-board and per-job failures are isolated; the run always finishes
with a full summary.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from worker.db import client as db_client
from worker.db import job_repository
from worker.models.job import DiscoveryResult
from worker.pipelines.search_pipeline import run_search_discovery
from worker.processors.deduplicator.job_deduplicator import deduplicate_jobs
from worker.processors.intelligence import config as persistence_gates
from worker.processors.normalizer.job_normalizer import normalize_job
from worker.search import config as search_config
from worker.search.query_generator import SearchProfile
from worker.sources import aggregators as aggregator_sources
from worker.sources.resolver import ASHBY, GREENHOUSE, LEVER, resolve_targets

logger = logging.getLogger("ai-jobhunter.ingestion")


def _utcnow_iso() -> str:
    """UTC timestamp for discovery metadata (in-memory only, never schema)."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class IngestionResult:
    """Structured outcome of one controlled ingestion run."""

    provider_name: str = ""
    queries_attempted: int = 0
    queries_executed: int = 0
    results_found: int = 0
    targets_found: int = 0
    resolved_counts: dict = field(default_factory=dict)
    boards_attempted: int = 0
    boards_succeeded: int = 0
    boards_failed: int = 0
    boards_skipped_over_cap: int = 0
    jobs_fetched: int = 0
    jobs_normalized: int = 0
    unique_jobs: int = 0
    duplicates_in_run: int = 0
    # Persistence (populated only when writes actually happen).
    persist_requested: bool = False
    persist_allowed: bool = False
    gate_details: str = ""
    writes_performed: bool = False
    inserted_count: int = 0
    updated_count: int = 0
    duplicate_count: int = 0
    source_links_created: int = 0
    companies_created: int = 0
    skipped_count: int = 0
    # Dry run: normalized unique jobs that WOULD be offered to persistence
    # (DB-level dedupe cannot be checked without touching the database).
    persist_candidates: int = 0
    gemini_calls: int = 0  # always 0: this pipeline never calls AI
    unresolved_company_career: int = 0
    unresolved_unknown: int = 0
    aggregator_converted: int = 0  # aggregator detail pages turned into jobs
    aggregator_skipped: int = 0  # aggregator non-detail pages left out
    errors: list = field(default_factory=list)
    per_board: list = field(default_factory=list)

    def summary(self) -> dict:
        """Plain-dict summary (handy for logging, CLI, and tests)."""
        return {
            "provider": self.provider_name,
            "queries_attempted": self.queries_attempted,
            "queries_executed": self.queries_executed,
            "results_found": self.results_found,
            "targets_found": self.targets_found,
            "boards_attempted": self.boards_attempted,
            "boards_succeeded": self.boards_succeeded,
            "jobs_fetched": self.jobs_fetched,
            "jobs_normalized": self.jobs_normalized,
            "unique_jobs": self.unique_jobs,
            "aggregator_converted": self.aggregator_converted,
            "aggregator_skipped": self.aggregator_skipped,
            "writes_performed": self.writes_performed,
            "inserted": self.inserted_count,
            "persist_candidates": self.persist_candidates,
            "gemini_calls": self.gemini_calls,
            "errors": len(self.errors),
        }


def default_source_factory(source_type: str, identifier: str):
    """Build a live single-board ATS source (existing connectors only)."""
    if source_type == GREENHOUSE:
        from worker.sources.greenhouse.source import GreenhouseSource

        return GreenhouseSource(boards=[identifier], enabled=True)
    if source_type == LEVER:
        from worker.sources.lever.source import LeverSource

        return LeverSource(boards=[identifier], enabled=True)
    if source_type == ASHBY:
        from worker.sources.ashby.source import AshbySource

        return AshbySource(boards=[identifier], enabled=True)
    raise ValueError(f"no ATS connector for source type '{source_type}'")


def _gates_allow(persist_requested: bool) -> tuple:
    """Check the persistence gates. Returns (allowed, details)."""
    reasons = []
    if not persist_requested:
        reasons.append("persist not requested (dry run)")
    if not persistence_gates.persist_enabled():
        reasons.append("PERSIST_DISCOVERY is not true")
    if not search_config.is_live_ingestion_enabled():
        reasons.append("ENABLE_LIVE_INGESTION is not true")
    if not db_client.is_configured():
        reasons.append("DATABASE_URL is missing")
    if reasons:
        return False, "; ".join(reasons)
    return True, "all gates passed (explicit --persist + PERSIST_DISCOVERY + ENABLE_LIVE_INGESTION + DATABASE_URL)"


def run_ingestion(
    profile: Optional[SearchProfile] = None,
    provider=None,
    max_queries: Optional[int] = None,
    max_results_per_query: Optional[int] = None,
    persist_requested: bool = False,
    source_factory=None,
    max_boards: Optional[int] = None,
    board_job_limit: Optional[int] = None,
) -> IngestionResult:
    """Run search -> resolve -> ATS fetch -> normalize -> dedupe -> persist?.

    With any persistence gate closed this is a dry run: discovery, resolving,
    ATS fetching, and normalization still execute, but zero DB writes occur.
    """
    outcome = IngestionResult(persist_requested=bool(persist_requested))
    factory = source_factory or default_source_factory
    query_cap = max_queries if max_queries is not None else search_config.get_max_ingestion_queries()
    board_cap = max_boards if max_boards is not None else search_config.get_max_ingestion_boards()
    per_board = board_job_limit if board_job_limit is not None else search_config.get_max_ingestion_jobs_per_board()

    # -- 1. search discovery (existing pipeline: bounded queries, per-query isolation)
    search = run_search_discovery(
        profile=profile,
        provider=provider,
        max_queries=query_cap,
        max_results_per_query=max_results_per_query,
    )
    if provider is not None:
        outcome.provider_name = getattr(provider, "provider_name", "") or ""
    if not outcome.provider_name:
        outcome.provider_name = search_config.get_provider_name()
    outcome.queries_attempted = search.queries_generated
    outcome.queries_executed = search.queries_executed
    outcome.results_found = search.results_found
    outcome.targets_found = search.targets_found
    outcome.resolved_counts = dict(search.classification_stats or {})
    outcome.errors.extend(search.errors)

    # -- 2. resolve (parse-only; ATS boards group, the rest queue below)
    resolved = resolve_targets(search.targets)
    ats_boards: dict = {}  # (source_type, identifier) -> first ResolvedSource
    non_ats_entries: list = []  # (DiscoveryTarget, ResolvedSource) in order
    for target, item in zip(search.targets or [], resolved or []):
        if item.is_ats:
            ats_boards.setdefault((item.source_type, item.identifier), item)
        else:
            non_ats_entries.append((target, item))

    ordered = sorted(ats_boards.values(), key=lambda r: (r.source_type, r.identifier))
    if len(ordered) > board_cap:
        outcome.boards_skipped_over_cap = len(ordered) - board_cap
        outcome.errors.append(
            f"board cap reached ({board_cap}): {outcome.boards_skipped_over_cap} board(s) skipped"
        )
        ordered = ordered[:board_cap]
    outcome.boards_attempted = len(ordered)

    # -- 2b. aggregator URL-first conversion (no fetching, no scraping).
    # Qualifying LinkedIn/Indeed/Internshala job-detail pages become
    # DiscoveredJobs from Tavily metadata; listing/search/company pages are
    # skipped with reasons. Converted items leave the unresolved buckets.
    agg_entries = [
        (getattr(target, "url", ""), getattr(target, "title", ""),
         getattr(target, "snippet", ""))
        for target, _item in non_ats_entries
    ]
    agg_jobs, agg_skipped = aggregator_sources.convert_entries(agg_entries, board_cap)
    outcome.aggregator_converted = len(agg_jobs)
    outcome.aggregator_skipped = len(agg_skipped)
    converted_raw_urls = {
        job.source_url for job in agg_jobs if getattr(job, "source_url", "")
    }
    for target, item in non_ats_entries:
        raw = getattr(target, "url", "")
        raw = raw.strip() if isinstance(raw, str) else ""
        if raw and raw in converted_raw_urls:
            continue  # converted above; not unresolved
        if item.source_type == "company_career":
            outcome.unresolved_company_career += 1
        else:
            outcome.unresolved_unknown += 1
    if agg_skipped:
        outcome.errors.append(
            f"aggregator skipped {len(agg_skipped)} non-detail URL(s) (first: {agg_skipped[0][1]})"
        )

    # -- 3. fetch + normalize (per-board isolation; one board fetch each)
    normalized: list = []
    for item in ordered:
        board_stat = {"source_type": item.source_type, "identifier": item.identifier,
                      "fetched": 0, "normalized": 0, "status": "ok", "error": ""}
        try:
            source = factory(item.source_type, item.identifier)
            fetched = source.discover_jobs(limit=max(1, int(per_board))) or []
            board_notes = list(getattr(source, "last_errors", []) or [])
        except Exception as exc:
            board_stat.update(status="error", error=f"{type(exc).__name__}: {exc}")
            outcome.boards_failed += 1
            outcome.errors.append(f"board '{item.identifier}' ({item.source_type}) failed: {type(exc).__name__}: {exc}")
            logger.warning("ingestion board '%s' failed: %s", item.identifier, exc)
            outcome.per_board.append(board_stat)
            continue
        if not fetched and board_notes:
            # Connectors isolate per-board failures into last_errors and return [];
            # an empty board with recorded errors is a failed board, not success.
            board_stat.update(status="error", error="; ".join(board_notes[:3]))
            outcome.boards_failed += 1
            outcome.errors.append(f"board '{item.identifier}' ({item.source_type}) failed: {board_notes[0]}")
            outcome.per_board.append(board_stat)
            continue
        if board_notes:
            board_stat["error"] = "; ".join(board_notes[:3])
            outcome.errors.append(f"board '{item.identifier}' ({item.source_type}) partial: {board_notes[0]}")
        outcome.boards_succeeded += 1
        board_stat["fetched"] = len(fetched)
        outcome.jobs_fetched += len(fetched)
        for job in fetched:
            try:
                norm = normalize_job(job)
                if isinstance(job.raw_data, dict):
                    job.raw_data["discovery"] = {
                        "provider": outcome.provider_name,
                        "discovered_url": item.original_url,
                        "classified_source": item.source_type,
                        "resolved_identifier": item.identifier,
                        "resolved_at": _utcnow_iso(),
                    }
                normalized.append(norm)
                board_stat["normalized"] += 1
            except Exception as exc:
                message = f"normalize failed for board '{item.identifier}': {type(exc).__name__}"
                outcome.errors.append(message)
                logger.warning("%s", message)
        outcome.per_board.append(board_stat)

    # -- 3b. normalize converted aggregator jobs (same normalizer, same gates).
    for job in agg_jobs:
        try:
            norm = normalize_job(job)
            if isinstance(job.raw_data, dict):
                job.raw_data["discovery"] = {
                    "provider": outcome.provider_name,
                    "discovered_url": job.source_url,
                    "classified_source": job.source_type,
                    "resolved_identifier": job.source_name,
                    "resolved_at": _utcnow_iso(),
                }
            normalized.append(norm)
        except Exception as exc:
            message = f"normalize failed for aggregator job: {type(exc).__name__}"
            outcome.errors.append(message)
            logger.warning("%s", message)
    outcome.jobs_normalized = len(normalized)

    # -- 4. in-run dedupe (existing fingerprint logic stays authoritative)
    deduped = deduplicate_jobs(normalized)
    unique = deduped.unique_jobs
    outcome.unique_jobs = len(unique)
    outcome.duplicates_in_run = deduped.duplicate_count
    if deduped.duplicate_count:
        outcome.errors.append(f"removed {deduped.duplicate_count} in-run duplicate(s)")

    # -- 5. persist or dry run (gates re-checked at the point of writing)
    allowed, details = _gates_allow(outcome.persist_requested)
    outcome.persist_allowed = allowed
    outcome.gate_details = details
    if not allowed:
        outcome.persist_candidates = len(unique)
        return outcome
    discovery = DiscoveryResult(
        discovered_count=len(unique),
        normalized_count=len(unique),
        unique_count=len(unique),
        jobs=list(unique),
    )
    try:
        persisted = job_repository.persist_discovery_result(
            discovery, allow_mock=persistence_gates.allow_mock_persist()
        )
    except Exception as exc:
        outcome.persist_allowed = False
        outcome.writes_performed = False
        outcome.errors.append(f"persistence failed: {type(exc).__name__}: {exc}")
        logger.warning("ingestion persistence failed: %s", exc)
        return outcome
    outcome.writes_performed = True
    outcome.inserted_count = persisted.inserted_count
    outcome.updated_count = persisted.updated_count
    outcome.duplicate_count = persisted.duplicate_count
    outcome.source_links_created = persisted.source_links_created
    outcome.companies_created = persisted.companies_created
    outcome.skipped_count = persisted.skipped_count
    outcome.errors.extend(persisted.errors)
    return outcome

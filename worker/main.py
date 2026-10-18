"""Worker entrypoint (Phase 6.1: discovery + search demos, optional ingestion).

Running ``python -m worker.main`` from the repo root runs the registered job
sources through normalize -> deduplicate, then the mock search provider
through query generation -> classification. Fully offline by default: no
network, no secrets, no AI calls, and no database writes.

Persistence is strictly opt-in: ``PERSIST_DISCOVERY=true python -m worker.main``
persists the discovery result (mock rows additionally require
``ALLOW_MOCK_PERSIST=true``). Without DATABASE_URL it reports
"database not configured" and writes nothing.

Live ATS ingestion is a separate explicit command and defaults to dry run::

    python -m worker.main --discover --provider tavily --dry-run
    python -m worker.main --discover --provider tavily --persist --max-queries 3

``--persist`` additionally requires PERSIST_DISCOVERY=true,
ENABLE_LIVE_INGESTION=true, and DATABASE_URL — otherwise the run stays a
dry run with zero writes. Gemini is never called by ingestion.

Post-ingestion enrichment is a separate explicit command (dry run by default
unless AI is explicitly enabled)::

    python -m worker.main --enrich --dry-run
    AI_ENABLED=true GEMINI_API_KEY=<key> python -m worker.main --enrich --limit 20
"""

import logging
import os
import sys

# Allow `python worker/main.py` as well as `python -m worker.main`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-jobhunter-worker")


def _print_summary(result) -> None:
    """Print the discovery outcome (counts + job list, never secrets)."""
    print("")
    print("## AI-JobHunter Discovery Engine")
    print("")
    print(f"Sources: {len(result.source_stats)}")
    print(f"Discovered: {result.discovered_count}")
    print(f"Normalized: {result.normalized_count}")
    print(f"Unique: {result.unique_count}")
    print("")
    print("Jobs:")
    print("")
    if not result.jobs:
        print("(none)")
    for i, job in enumerate(result.jobs, 1):
        original = job.original
        where = "Remote" if job.is_remote else (job.primary_location.title() or "—")
        print(f"{i}. {original.title} - {original.company_name} - {where}")
    if result.errors:
        print("")
        for error in result.errors:
            print(f"note: {error}")


def _print_search_summary(result, queries) -> None:
    """Print the mock search outcome (queries, stats, targets — never secrets)."""
    print("")
    print("## Search Discovery (mock provider)")
    print("")
    print(f"Queries generated: {result.queries_generated}")
    print(f"Queries executed: {result.queries_executed}")
    print(f"Results found: {result.results_found}")
    print(f"Targets found: {result.targets_found}")
    print(f"Junk removed: {result.junk_removed}")
    print("")
    print("Sample queries:")
    print("")
    for item in queries[:5]:
        print(f"- {item.query}")
    print("")
    print("Classification:")
    print("")
    for label in ("greenhouse", "lever", "ashby", "company_career", "unknown"):
        print(f"- {label}: {result.classification_stats.get(label, 0)}")
    print("")
    print("Targets:")
    print("")
    if not result.targets:
        print("(none)")
    for target in result.targets:
        print(f"- [{target.classified_source}] {target.title} ({target.url})")
    if result.errors:
        print("")
        for error in result.errors:
            print(f"note: {error}")


def _parse_bool(value: object) -> bool:
    """True for explicit opt-ins (1/true/yes/on); everything else is off."""
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _parse_discover_args(argv: list) -> dict:
    """Parse --discover options (pure function, safe to unit test).

    Returns provider override ("" = env default), persist flag, and an
    optional max-queries override (None = configured default).
    """
    args = list(argv or [])
    options = {"provider": "", "persist": "--persist" in args, "max_queries": None}
    for index, token in enumerate(args):
        if token == "--provider" and index + 1 < len(args):
            options["provider"] = args[index + 1].strip().lower()
        elif token.startswith("--provider="):
            options["provider"] = token.split("=", 1)[1].strip().lower()
        elif token == "--max-queries" and index + 1 < len(args):
            try:
                options["max_queries"] = max(1, int(args[index + 1]))
            except (TypeError, ValueError):
                options["max_queries"] = None
        elif token.startswith("--max-queries="):
            try:
                options["max_queries"] = max(1, int(token.split("=", 1)[1]))
            except (TypeError, ValueError):
                options["max_queries"] = None
    return options


def _print_intelligence_summary(result) -> None:
    """Print the intelligence outcome (counts only — never prompts or keys)."""
    print("")
    print("AI Job Intelligence")
    print("-------------------")
    summary = result.summary()
    print(f"Jobs received:       {summary['received']}")
    print(f"Rule-rejected:       {summary['rejected']}")
    print(f"AI candidates:       {summary['prefiltered']}")
    print(f"Already analyzed:    {summary['cached']}")
    print(f"Sent to Gemini:      {summary['sent_to_ai']}")
    print(f"Successfully scored: {summary['analyzed']}")
    print(f"Failed:              {summary['errors']}")
    print("")
    print("Recommendations:")
    for label in ("APPLY", "CONSIDER", "REVIEW", "AVOID"):
        print(f"{label + ':':<20} {result.recommendations.get(label, 0)}")
    for error in result.errors:
        print(f"note: {error}")


def _print_persistence_summary(result) -> None:
    """Print persistence counts (never connection details or secrets)."""
    print("")
    print("## Persistence")
    print("")
    summary = result.summary()
    for key in ("discovered", "inserted", "updated", "duplicates", "source_links", "companies", "skipped", "errors"):
        print(f"{key}: {summary[key]}")
    for error in result.errors:
        print(f"note: {error}")


def _parse_enrich_args(argv: list) -> dict:
    """Parse --enrich options (pure function, safe to unit test)."""
    args = list(argv or [])
    options = {"profile": "", "limit": None, "dry_run": "--dry-run" in args,
               "run_ranking": "--no-rank" not in args, "rank_limit": None}
    for index, token in enumerate(args):
        if token == "--profile" and index + 1 < len(args):
            options["profile"] = args[index + 1].strip()
        elif token.startswith("--profile="):
            options["profile"] = token.split("=", 1)[1].strip()
        elif token == "--limit" and index + 1 < len(args):
            try:
                options["limit"] = max(1, int(args[index + 1]))
            except (TypeError, ValueError):
                options["limit"] = None
        elif token.startswith("--limit="):
            try:
                options["limit"] = max(1, int(token.split("=", 1)[1]))
            except (TypeError, ValueError):
                options["limit"] = None
        elif token == "--rank-limit" and index + 1 < len(args):
            try:
                options["rank_limit"] = max(1, int(args[index + 1]))
            except (TypeError, ValueError):
                options["rank_limit"] = None
        elif token.startswith("--rank-limit="):
            try:
                options["rank_limit"] = max(1, int(token.split("=", 1)[1]))
            except (TypeError, ValueError):
                options["rank_limit"] = None
    return options


def _print_enrichment_summary(result) -> None:
    """Print the enrichment outcome (counts only — never prompts or keys)."""
    intel = result.intelligence.summary()
    print("")
    print("## Post-Ingestion Enrichment (Phase 6.2)")
    print("")
    print(f"Profile: {result.profile_id or '—'}")
    print(f"Candidates: {intel['received']}")
    print(f"Prefilter rejected: {intel['rejected']}")
    print(f"Gemini eligible: {intel['prefiltered']}")
    print(f"Cached (no AI call): {intel['cached']}")
    if result.dry_run:
        print(f"Would analyze: {intel['would_analyze']}")
        print("DRY RUN — Gemini calls: 0, writes: 0 (ranking skipped)")
    else:
        print(f"Sent to Gemini: {intel['sent_to_ai']}")
        print(f"Analyzed: {intel['analyzed']}")
        print(f"Intelligence writes: {result.intelligence_writes}")
        print(f"Gemini calls: {result.gemini_calls}")
    if result.ranking is not None:
        print("")
        print(f"Ranked: {len(result.ranking.ranked_jobs)} "
              f"(considered {result.ranking.jobs_received}, excluded {result.ranking.jobs_excluded})")
        for ranked in result.ranking.ranked_jobs[:10]:
            print(f"{ranked.rank}. {ranked.title} — {ranked.ranking_score:.1f} "
                  f"(match {ranked.match_score}, trust {ranked.trust_score}, {ranked.recommendation})")
        for error in result.ranking.ranking_errors:
            print(f"note: {error}")
    elif result.ranking_skipped:
        print(f"Ranking: skipped ({result.ranking_skipped})")
    for error in result.intelligence.errors:
        print(f"note: {error}")


def _run_enrich(argv: list) -> None:
    """Explicit enrichment command (intelligence -> ranking, gates respected)."""
    from worker.pipelines.enrichment_pipeline import run_enrichment

    options = _parse_enrich_args(argv)
    result = run_enrichment(
        profile_id=options["profile"] or None,
        job_limit=options["limit"] or 50,
        dry_run=options["dry_run"],
        run_ranking=options["run_ranking"],
        ranking_limit=options["rank_limit"] or 20,
    )
    _print_enrichment_summary(result)


def _print_ingestion_summary(result) -> None:
    """Print the ingestion outcome (counts only — never keys or URLs with creds)."""
    """Print the ingestion outcome (counts only — never keys or URLs with creds)."""
    print("")
    print("## Controlled ATS Ingestion (Phase 6.1)")
    print("")
    print(f"Provider: {result.provider_name}")
    print(f"Queries attempted: {result.queries_attempted}")
    print(f"Queries executed: {result.queries_executed}")
    print(f"Search results: {result.results_found}")
    print(f"Targets: {result.targets_found}")
    print("")
    print("Resolved:")
    print("")
    for label in ("greenhouse", "lever", "ashby"):
        print(f"- {label}: {result.resolved_counts.get(label, 0)}")
    print("")
    print("Unresolved (queued, never fetched):")
    print("")
    print(f"- company career: {result.unresolved_company_career}")
    print(f"- unknown: {result.unresolved_unknown}")
    print("")
    print(f"ATS boards attempted: {result.boards_attempted}")
    print(f"ATS boards succeeded: {result.boards_succeeded}")
    print(f"ATS boards failed: {result.boards_failed}")
    if result.boards_skipped_over_cap:
        print(f"ATS boards skipped (cap): {result.boards_skipped_over_cap}")
    print(f"ATS jobs fetched: {result.jobs_fetched}")
    print(f"Aggregator jobs converted: {result.aggregator_converted}")
    print(f"Aggregator skipped: {result.aggregator_skipped}")
    print(f"Jobs normalized: {result.jobs_normalized}")
    print(f"Unique jobs: {result.unique_jobs}")
    print("")
    if result.writes_performed:
        print("PERSIST MODE — production writes performed:")
        print(f"- inserted: {result.inserted_count}")
        print(f"- updated: {result.updated_count}")
        print(f"- duplicates: {result.duplicate_count}")
        print(f"- companies created: {result.companies_created}")
        print(f"- source links created: {result.source_links_created}")
        print(f"- skipped: {result.skipped_count}")
    else:
        print("DRY RUN — production writes: 0")
        print(f"Would persist (candidates): {result.persist_candidates}")
        print(f"Gate state: {result.gate_details}")
    print("Gemini calls: 0")
    if result.per_board:
        print("")
        print("Boards:")
        for board in result.per_board:
            print(f"- [{board['source_type']}] {board['identifier']}: "
                  f"{board['status']} (fetched {board['fetched']}, normalized {board['normalized']})")
    if result.errors:
        print("")
        for error in result.errors:
            print(f"note: {error}")


def _run_discover(argv: list) -> None:
    """Explicit ingestion command (dry run unless every persist gate passes)."""
    from worker.pipelines.ingestion_pipeline import run_ingestion
    from worker.search import config as search_config
    from worker.search import registry as search_registry
    from worker.search.query_generator import load_search_profile

    options = _parse_discover_args(argv)
    provider_name = options["provider"] or search_config.get_provider_name()
    provider = search_registry.get_provider(provider_name)
    if provider is None:
        print(f"unknown search provider '{provider_name}' — nothing ran (no writes, no credits spent)")
        return
    result = run_ingestion(
        profile=load_search_profile(),
        provider=provider,
        max_queries=options["max_queries"],
        persist_requested=options["persist"],
    )
    _print_ingestion_summary(result)


def main() -> None:
    """Log readiness, then run the safe mock discovery + search demos."""
    if "--readiness" in sys.argv or "--check-search-provider" in sys.argv:
        from worker.search.readiness import format_readiness, get_readiness

        print(format_readiness(get_readiness()))
        return
    if "--discover" in sys.argv:
        _run_discover(sys.argv[1:])
        return
    if "--enrich" in sys.argv:
        _run_enrich(sys.argv[1:])
        return
    from worker.db import client as db_client
    from worker.db.job_repository import persist_discovery_result
    from worker.pipelines.discovery_pipeline import run_discovery
    from worker.pipelines.search_pipeline import run_search_discovery
    from worker.search import registry as search_registry
    from worker.search.query_generator import generate_queries, load_search_profile
    from worker.sources import registry

    logger.info("AI-JobHunter worker is ready (no pipelines wired yet).")
    sources = registry.get_all_sources()
    logger.info("Loaded %d source(s): %s", len(sources), [s.source_name for s in sources])
    result = run_discovery(sources)
    _print_summary(result)

    providers = search_registry.get_all_providers()
    logger.info("Loaded %d search provider(s): %s", len(providers), [p.provider_name for p in providers])
    search_profile = load_search_profile()
    search_result = run_search_discovery(search_profile, max_queries=10)
    _print_search_summary(search_result, generate_queries(search_profile, max_queries=10))

    if not _parse_bool(os.getenv("PERSIST_DISCOVERY", "")):
        print("")
        print("persistence: disabled (set PERSIST_DISCOVERY=true to enable)")
    elif not db_client.is_configured():
        print("")
        print("persistence: database not configured (set DATABASE_URL) — nothing persisted")
    else:
        persisted = persist_discovery_result(
            result, allow_mock=_parse_bool(os.getenv("ALLOW_MOCK_PERSIST", ""))
        )
        _print_persistence_summary(persisted)

    if not _parse_bool(os.getenv("RUN_INTELLIGENCE", "")):
        print("")
        print("intelligence: disabled — AI disabled (set RUN_INTELLIGENCE=true to enable)")
    elif not db_client.is_configured():
        print("")
        print("database not configured — intelligence skipped")
    else:
        from worker.pipelines.intelligence_pipeline import run_intelligence

        _print_intelligence_summary(run_intelligence())

    if not _parse_bool(os.getenv("RUN_RANKING", "")):
        print("")
        print("ranking: disabled (set RUN_RANKING=true to enable)")
        return
    if not db_client.is_configured():
        print("")
        print("database not configured — ranking skipped")
        return
    from worker.pipelines.ranking_pipeline import rank_jobs_for_profile

    try:
        limit = max(1, int(os.getenv("RANKING_DEFAULT_LIMIT", "20")))
    except (TypeError, ValueError):
        limit = 20
    ranked = rank_jobs_for_profile(limit=limit)
    if not ranked.ranked_jobs and not ranked.ranking_errors:
        print("")
        print("no analyzed jobs available — ranking skipped")
        return
    _print_ranking_summary(ranked, limit)


def _print_ranking_summary(result, limit: int) -> None:
    """Print the ranking outcome (titles + scores only — never secrets)."""
    print("")
    print("Job Ranking")
    print("-----------")
    summary = result.summary()
    profile = result.ranked_jobs[0].profile_id if result.ranked_jobs else "—"
    print(f"Profile:             {profile}")
    print(f"Jobs considered:     {summary['received']}")
    print(f"Jobs ranked:         {summary['ranked']}")
    print(f"Invalid/skipped:     {summary['excluded']}")
    print("")
    print(f"Top opportunities (top {limit}):")
    if not result.ranked_jobs:
        print("(none)")
    for ranked in result.ranked_jobs:
        print(f"{ranked.rank}. {ranked.title} — {ranked.ranking_score:.1f} "
              f"(match {ranked.match_score}, trust {ranked.trust_score}, {ranked.recommendation})")
    for error in result.ranking_errors:
        print(f"note: {error}")


if __name__ == "__main__":
    main()

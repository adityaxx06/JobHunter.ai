# Worker — Job discovery + processing

Phase 5.2: Gemini job intelligence added (discovery + persistence unchanged).

- `models/job.py` — canonical `DiscoveredJob` / `NormalizedJob`, pipeline result types.
- `sources/base.py` — `JobSource` interface (`discover_jobs`, `health_check`).
- `sources/manual/mock_source.py` — 5 mock fixtures (offline-safe).
- `sources/greenhouse/` — `client.py` (stdlib HTTP), `parser.py` (mapping +
  HTML-to-text), `source.py` (multi-board `JobSource`), `config.py` (env).
- `sources/lever/` — same split for public Lever postings (`client.py`,
  `parser.py`, `source.py`, `config.py`).
- `sources/ashby/` — same split for Ashby's public Job Postings API
  (`GET /posting-api/job-board/{name}`, verified in Ashby's official docs).
- `sources/html_text.py` — shared stdlib HTML-to-text helper.
- `models/search.py` — `SearchResult` / `DiscoveryTarget` / `SearchQuery` / pipeline result (leads, not jobs).
- `search/base.py` — `SearchProvider` interface (separate from `JobSource`).
- `search/mock_provider.py` — 5 deterministic mock leads (offline-safe).
- `search/query_generator.py` — tiered, capped role/location/fresher + `site:` queries from profile facets.
- `search/classifier.py` — conservative URL-hostname → source classification.
- `search/registry.py` + `search/config.py` — provider registry, env config
  (`SEARCH_*`, key never logged). `search/tavily.py` — first real provider
  (Phase 6.0, opt-in via `SEARCH_PROVIDER=tavily` + `TAVILY_API_KEY`).
  `search/readiness.py` — credential presence report (no network, no credits).
- `sources/registry.py` — `register_source` / `get_source` / `get_all_sources`.
- `processors/normalizer/job_normalizer.py` — title/company/location/employment/skills normalization (originals kept).
- `processors/deduplicator/job_deduplicator.py` — in-memory fingerprint + URL dedup.
- `utils/job_fingerprint.py` — SHA-256 fingerprint (parity-tested with backend copy).
- `pipelines/discovery_pipeline.py` — sources → normalize → dedupe (`run_discovery`).
- `db/client.py` — reusable Postgres client (+ `transaction()` context manager).
- `db/job_repository.py` — `persist_job` / `persist_discovery_result` + `PersistenceResult`
  (company reuse, fingerprint lookup, blank-safe updates, source-link reuse, mock guard).

Legacy `processors/*/service.py` and `sources/*/adapter.py` placeholders remain
for future stages (filter/scorer/ranker, real adapters).

## Run the discovery pipeline

From the repo root (no secrets, no AI calls):

```bash
python -m worker.main
# or: python worker/main.py
```

Runs job-source discovery (mock jobs; ATS connectors idle unless configured)
plus the mock search demo: generated queries → classified targets. Fully
offline by default — no external requests, no secrets, no AI calls.

Without connector config: 4 sources registered, mock yields 5 jobs,
`greenhouse`/`lever`/`ashby` report disabled/not-configured and stay idle —
output is the 5 mock jobs, application healthy.

With connectors (public boards only, conservative single request per board):

```bash
GREENHOUSE_ENABLED=true GREENHOUSE_BOARDS=company-one;company-two python -m worker.main
LEVER_ENABLED=true LEVER_BOARDS=acme;globex python -m worker.main
ASHBY_ENABLED=true ASHBY_BOARDS=acme;globex python -m worker.main
```

## Persistence mode (opt-in, Phase 5.1)

Discovery alone never writes. To persist:

```bash
PERSIST_DISCOVERY=true python -m worker.main
```

- Requires `DATABASE_URL` (Supabase Postgres) — otherwise prints
  `database not configured` and writes nothing.
- Mock fixtures persist only with `ALLOW_MOCK_PERSIST=true` (never by accident).
- Safe workflow: run discovery-only first, verify the summary, then re-run
  with `PERSIST_DISCOVERY=true` against a dev database.
- Gated live integration test (isolated, self-cleaning records):
  `RUN_DB_INTEGRATION_TESTS=true python -m pytest worker/tests/test_db_integration.py -v`

## Intelligence mode (opt-in, Phase 5.2 — free-first, see docs/intelligence.md)

```bash
PERSIST_DISCOVERY=true RUN_INTELLIGENCE=true AI_ENABLED=true python -m worker.main
```

- Rule prefilter (`processors/intelligence/prefilter.py`) runs before any AI call.
- Gemini via `ai/providers` (`GEMINI_API_KEY` server-side only, never logged).
- Strict validation: malformed output never reaches `job_matches`.
- Guards: `AI_MAX_JOBS_PER_RUN=20` quota cap, cached results reused, mock jobs
  skipped, per-job failures isolated. Disabled/missing DB/key prints a clean
  skip message — default run makes zero Gemini calls.
- Gated live test (one fixture, never in the suite):
  `RUN_GEMINI_LIVE_TESTS=true GEMINI_API_KEY=<key> python -m pytest worker/tests/test_gemini_live.py -v`

## Post-ingestion enrichment (explicit, Phase 6.2 — see docs/intelligence.md)

```bash
python -m worker.main --enrich --dry-run
AI_ENABLED=true GEMINI_API_KEY=<key> python -m worker.main --enrich --limit 20
```

- `pipelines/enrichment_pipeline.py` — `run_enrichment`: existing
  `run_intelligence` (prefilter → Gemini → `job_matches`) then existing
  `rank_jobs_for_profile` (stored intelligence → ranked list, zero AI).
  Never imports search/sources/ingestion — DB jobs in, ranked list out.
- `--dry-run` previews selection (`would_analyze`) with zero AI calls and
  zero writes, even when AI is enabled; `--no-rank` skips ranking;
  `--profile` / `--limit` / `--rank-limit` scope the run.
- Ingestion stays AI-free; ranking after partial failure still ranks the
  successes; re-runs reuse the `job_matches` cache (no re-analysis).

## Ranking mode (opt-in, Phase 5.3 — deterministic, zero AI, see docs/ranking.md)

```bash
RUN_RANKING=true python -m worker.main
```

- Consumes stored Phase 5.2 intelligence: `match*0.60 + trust*0.25`,
  recommendation bonus (APPLY +10 … AVOID −25), profile preference (0–5),
  skill bonus (capped +2), trust-band penalties (severe below 25).
- Deterministic tie-breaks down to job ID; duplicates rank once; optional
  filters + top-N (`RANKING_DEFAULT_LIMIT=20`, scored-before-cut).
- Guards: needs DB (`database not configured — ranking skipped` otherwise)
  and analyzed jobs (`no analyzed jobs available — ranking skipped`).
- Reusable service: `rank_jobs_for_profile(profile_id, limit=20, ...)` for
  Phase 5.4. Gated DB test (isolated, self-cleaning):
  `RUN_DB_INTEGRATION_TESTS=true python -m pytest worker/tests/test_ranking_db_integration.py -v`

## Run worker tests (offline)

```bash
python -m pytest worker/tests/ -v
```

Optional live smoke test (exactly one real request, never in normal runs):

```bash
GREENHOUSE_LIVE_TEST=true GREENHOUSE_BOARDS=<public-board-token> python -m pytest worker/tests/test_greenhouse_live.py -v
LEVER_LIVE_TEST=true LEVER_BOARDS=<public-company-handle> python -m pytest worker/tests/test_lever_live.py -v
ASHBY_LIVE_TEST=true ASHBY_BOARDS=<public-board-name> python -m pytest worker/tests/test_ashby_live.py -v
TAVILY_LIVE_TEST=true TAVILY_API_KEY=<key> python -m pytest worker/tests/test_tavily_live.py -v
```

## Provider readiness (Phase 6.0 — no network, no credits, no writes)

```bash
python -m worker.main --readiness
# or: python -m worker.main --check-search-provider
```

Reports Tavily / Gemini / database configuration and the selected search
provider. To use Tavily (free tier, key at https://app.tavily.com):

```bash
SEARCH_PROVIDER=tavily TAVILY_API_KEY=<key> python -m worker.main --readiness
```

Without a key the provider reports "not configured" and searches fail
cleanly per query — the mock provider keeps every default run offline.

## Controlled ATS ingestion (Phase 6.1 — dry run unless every gate passes)

```bash
python -m worker.main --discover --provider tavily --dry-run --max-queries 2
```

- `sources/resolver.py` — `DiscoveryTarget` → `ResolvedSource`
  (greenhouse/lever/ashby + handle, else queued company_career/unknown).
  Parse-only; exact-host rules; arbitrary URLs are never fetched.
- `pipelines/ingestion_pipeline.py` — search → resolve → one fetch per
  distinct board via the existing ATS sources → existing normalizer/dedupe
  → existing persistence → STOP (no AI, no ranking, no auto-apply).
- Writes happen ONLY with `--persist` AND `PERSIST_DISCOVERY=true` AND
  `ENABLE_LIVE_INGESTION=true` AND `DATABASE_URL` — otherwise an honest dry
  run with zero writes:
  `PERSIST_DISCOVERY=true ENABLE_LIVE_INGESTION=true DATABASE_URL=<db>
  python -m worker.main --discover --provider tavily --persist`.
- Credit safety: `MAX_INGESTION_QUERIES=3` (1..10), `MAX_INGESTION_BOARDS=5`
  (1..20); boards deduped before fetching.
- Gated live test (tiny dry run, persists nothing, never in the suite):
  `TAVILY_LIVE_TEST=true TAVILY_API_KEY=<key> python -m pytest worker/tests/test_ingestion_live.py -v`

# Job Sources (Phase 4.1 — discovery framework)

## Supported source architecture

Every source implements `worker/sources/base.py::JobSource`:

- `source_type` — machine key matching DB `job_sources.source_type`
  (`company_careers | greenhouse | lever | ashby | search_engine | manual`).
- `source_name` — unique registry key (several sources may share a type).
- `discover_jobs(query, location, limit)` — returns `DiscoveredJob` list (stdlib only).
- `health_check()` — self check, no network required for local sources.

Sources register in `worker/sources/registry.py` (`register_source`,
`get_source`, `get_all_sources`, `get_sources_by_type`). The pipeline
(`worker/pipelines/discovery_pipeline.py`) reads only the registry:

```
Source discovery (per source, failures isolated)
  -> Normalize (worker/processors/normalizer/job_normalizer.py)
  -> Deduplicate in-memory (worker/processors/deduplicator/job_deduplicator.py)
  -> DiscoveryResult (discovered/normalized/unique counts, jobs, errors, per-source stats)
```

## Current sources

- `mock` (type `manual`, `worker/sources/manual/mock_source.py`) — 5 fictional
  fixtures (Java/Backend/Software-Engineer/Python/AI-ML Intern) with
  `example.com` links and `raw_data.mock=True`. Clearly mock data for safe
  offline testing of the whole ingestion flow. No network, no secrets.
- `greenhouse` (type `greenhouse`, `worker/sources/greenhouse/`) — first real
  connector over public Greenhouse job-board endpoints
  (`GET /v1/boards/{board}/jobs?content=true`, no API key). Split files:
  `client.py` (stdlib-urllib HTTP only), `parser.py` (payload → `DiscoveredJob`
  + HTML-to-text), `source.py` (`JobSource`, multi-board orchestration),
  `config.py` (env parsing). Registered as `greenhouse`; idle unless enabled.

## Greenhouse connector (Phase 4.2A)

- Configuration (see `.env.example`): `GREENHOUSE_ENABLED=true` to run,
  `GREENHOUSE_BOARDS=company-one;company-two` with public board tokens
  (the public identifier in a company's board URL — not a credential),
  `GREENHOUSE_TIMEOUT` (default 10s), `GREENHOUSE_MAX_BOARDS` (default 25).
  Disabled/empty/invalid config returns `[]` + a `health_check()` note —
  never a crash.
- Safety/rate limits: sequential board requests, one request per board,
  bounded timeout, 5MB response cap, no retries by default (single
  `Retry-After`-honoring retry only when explicitly configured). 404 → board
  skipped; 429 → `RateLimitedError` with `retry_after`; 5xx/network →
  typed errors; per-board failures recorded in `source.last_errors` while
  healthy boards still contribute jobs.
- Mapping: `external_id/title/location/apply_url/posted_at-if-present` from
  the payload; `company_name` humanized from the board token (documented
  derivation); `company_domain` left empty (not provided); `posted_at` stays
  `None` (list payload carries no date); full item preserved in `raw_data`.
  Descriptions are HTML-stripped with a small stdlib parser (scripts/styles
  dropped, entities unescaped).
- Add a board: append its token to `GREENHOUSE_BOARDS` — no code changes.

## Lever connector (Phase 4.2B)

- Public postings only (`GET /v0/postings/{company}?mode=json` on
  `api.lever.co`, returns a JSON array — no key, no auth). Split files mirroring
  Greenhouse: `client.py`, `parser.py`, `source.py`, `config.py`; registered as
  `lever`; idle unless enabled. HTML cleaning reuses the shared stdlib helper
  `worker/sources/html_text.py`.
- Configuration: `LEVER_ENABLED=true`, `LEVER_BOARDS=acme;globex` (public
  company handles — not credentials), `LEVER_TIMEOUT` (default 10s),
  `LEVER_MAX_BOARDS` (default 10). Disabled/empty/invalid config returns `[]`
  + a `health_check()` note — never a crash.
- Safety/rate limits: sequential requests, one call per company, bounded
  timeout, 5MB cap, no default retries (optional `Retry-After`-honoring
  retry). 404/429/5xx/network map to typed errors; per-company failures land
  in `source.last_errors` while healthy companies still contribute.
- Mapping: `external_id/text/location/commitment/applyUrl/createdAt` from the
  payload; `company_name` humanized from the handle (documented derivation);
  `description` prefers `descriptionPlain`, else HTML-stripped; `skills` stays
  `[]` and salary stays `None` (not provided — never fabricated); remote only
  on explicit location/category signals (missing location is NOT remote);
  full posting preserved in `raw_data`.
- Add another Lever source: append its handle to `LEVER_BOARDS` — no code changes.
- Optional live test: `LEVER_LIVE_TEST=true LEVER_BOARDS=<handle> pytest
  worker/tests/test_lever_live.py -v` (one read-only request, never in the suite).

## Ashby connector (Phase 4.2C)

- Verified public endpoint (Ashby official docs,
  `developers.ashbyhq.com/docs/public-job-posting-api`):
  `GET https://api.ashbyhq.com/posting-api/job-board/{NAME}?includeCompensation=true`
  returning `{"apiVersion": "1", "jobs": [...]}` — no key, no auth. Split files
  mirroring the other connectors: `client.py`, `parser.py`, `source.py`,
  `config.py`; registered as `ashby`; idle unless enabled. Nothing guessed.
- Configuration: `ASHBY_ENABLED=true`, `ASHBY_BOARDS=acme;globex` (public board
  names — not credentials), `ASHBY_TIMEOUT` (default 10s), `ASHBY_MAX_BOARDS`
  (default 10). Disabled/empty/invalid config returns `[]` + a `health_check()`
  note — never a crash.
- Safety/rate limits: sequential requests, one call per board, bounded timeout,
  5MB cap, no default retries (optional `Retry-After`-honoring retry). 404/429/
  5xx/network map to typed errors; per-board failures land in
  `source.last_errors` while healthy boards still contribute.
- Mapping: documented fields (`title/location/secondaryLocations/department/
  team/isRemote/workplaceType/descriptionHtml/descriptionPlain/publishedAt/
  employmentType/jobUrl/applyUrl/isListed/compensation`) → `DiscoveredJob`;
  unlisted postings (`isListed: false`) are skipped per Ashby's docs (direct-link
  only, must not be displayed publicly); remote only on explicit `isRemote`,
  `workplaceType: Remote`, or location text (hybrid/onsite/missing are NOT
  remote); salary from the Salary `summaryComponents` entry (numeric only);
  `descriptionPlain` preferred, else shared-helper HTML cleaning; full posting
  preserved in `raw_data`.
- Add another Ashby board: append its name to `ASHBY_BOARDS` — no code changes.
- Optional live test: `ASHBY_LIVE_TEST=true ASHBY_BOARDS=<name> pytest
  worker/tests/test_ashby_live.py -v` (one read-only request, never in the suite).

## Himalayas connector (Phase 10C-2)

- Verified public endpoint (official docs, `himalayas.app/docs/remote-jobs-api`):
  `GET https://himalayas.app/jobs/api/search` with `q`, `employment_type`,
  `limit` (max 20/request) returning `{"jobs": [...], "nextCursor": ...}` —
  no key, no signup, free. Same four-file split (`client.py`, `parser.py`,
  `source.py`, `config.py`); registered as `himalaya` (`source_type`
  `job_board`, reusing the existing DB CHECK value); idle unless enabled.
  One bounded page per keyword — no cursor walking, no polling (data refreshes
  ~daily, so re-polling within a day gains nothing).
- Configuration: `HIMALAYA_ENABLED=true`, `HIMALAYA_KEYWORDS=intern;software
  engineer` (max 5), `HIMALAYA_EMPLOYMENT_TYPES=Intern` (empty disables the
  filter), `HIMALAYA_TIMEOUT` (default 10s). Disabled/empty config returns
  `[]` + a `health_check()` note — never a crash.
- Safety/rate limits: sequential requests, one page per keyword, bounded
  timeout, 5MB cap, no default retries (optional `Retry-After`-honoring
  retry). 400/429/5xx/network map to typed errors; per-keyword failures land
  in `source.last_errors` while healthy keywords still contribute.
- Mapping: documented fields only — `title` (required), `companyName`,
  `locationRestrictions[].name` (empty means worldwide → "Remote"),
  `employmentType`, `seniority` (list or string), sanitized-HTML
  `description` via the shared helper, numeric salaries, `currency`.
  `pubDate` (Unix epoch, seconds or millis) → `posted_at`; `expiryDate` and
  discovery time are never substituted. `applicationLink` becomes
  `apply_url`/`source_url` only when it parses as http(s); URL-less items are
  skipped. `guid` → `external_id`. Full item preserved in `raw_data`.
- Attribution (per the API terms): displayed jobs link back to their
  Himalayas `applicationLink` (kept verbatim as `apply_url`), and
  `source_name` stays `himalaya` so attribution survives into `job_sources`.
- Optional live test: `HIMALAYA_LIVE_TEST=true pytest
  worker/tests/test_himalaya_live.py -v` (two read-only requests — search +
  field probe, never in the suite).

## Jobicy connector (Phase 10C-3)

- Verified public endpoint (official docs, `jobicy.com/jobs-rss-feed`):
  `GET https://jobicy.com/api/v2/remote-jobs` with `count` (1–200),
  `tag`, `geo`, `industry` returning
  `{"success": true, "jobs": [...], "nextCursor": ...}` — no key, no signup,
  free under fair use. Same four-file split (`client.py`, `parser.py`,
  `source.py`, `config.py`); registered as `jobicy` (`source_type`
  `job_board`, reusing the existing DB CHECK value); idle unless enabled.
  One bounded page per tag — no cursor walking. The feed covers publication
  dates within the last 7 days (3-hour delay); syncing a few times per day
  is plenty, never more than once per hour.
- Configuration: `JOBICY_ENABLED=true`, `JOBICY_TAGS=python;intern`
  (max 5), `JOBICY_GEO=` / `JOBICY_INDUSTRY=` (optional slugs; empty
  disables the filter), `JOBICY_TIMEOUT` (default 10s). Disabled/empty
  config returns `[]` + a `health_check()` note — never a crash.
- Safety/rate limits: sequential requests, one page per tag, bounded
  timeout, 5MB cap, no default retries (optional `Retry-After`-honoring
  retry). 400/429/5xx/`success:false`/network map to typed errors;
  per-tag failures land in `source.last_errors` while healthy tags still
  contribute. The paid direct-ATS-link tier is deliberately unused.
- Mapping: documented fields only — `jobTitle` (required), `companyName`,
  `jobGeo` (empty means worldwide → "Remote"; remote-only board, so
  `is_remote` is always true), `jobType` array joined, `jobLevel`,
  full HTML `jobDescription` via the shared helper (`jobExcerpt` ignored),
  numeric salaries, `salaryCurrency`. `pubDate` (ISO-8601 string) →
  `posted_at`; expiry/retrieval/discovery times are never substituted.
  `url` (canonical Jobicy listing URL for keyless requests) becomes
  `apply_url`/`source_url` only when it parses as http(s); URL-less items
  are skipped. Integer `id` → `external_id`. Full item preserved in
  `raw_data`.
- Attribution (per fair use): displayed jobs keep the canonical Jobicy
  listing URL and must not be presented as original postings;
  `source_name` stays `jobicy` so attribution survives into `job_sources`.
  Remote-only coverage (including internships) — India on-site roles are
  out of scope for this source by design.
- Optional live test: `JOBICY_LIVE_TEST=true pytest
  worker/tests/test_jobicy_live.py -v` (two read-only requests — search +
  field probe, never in the suite).

## Search discovery (Phase 4.3 abstraction; mock default, Tavily opt-in 6.0)

- Separate abstraction from `JobSource`: `worker/search/base.py::SearchProvider`
  (`search(query, max_results)`, `health_check()`) returns *leads*
  (`SearchResult`: title/url/snippet/provider/raw), never canonical jobs.
  Registry at `worker/search/registry.py` (mock registered; future providers
  plug in with one registration). Config (`worker/search/config.py`):
  `SEARCH_ENABLED=false`, `SEARCH_PROVIDER=mock`, `SEARCH_API_KEY=` (empty
  placeholder, never logged), `SEARCH_TIMEOUT=10`, `SEARCH_MAX_RESULTS=20`.
- Query generation (`worker/search/query_generator.py`): profile roles/skills/
  locations/remote/experience → bounded tiered queries
  (`"Java Developer Intern" India`, `"Backend Developer Fresher" Chennai`,
  `"AI ML Intern" remote`) plus site hints
  (`site:jobs.lever.co "Python Developer Intern"`). Tier-ordered and capped
  (`max_queries`) — no combinatorial explosion. Tier 2 prefers owned/learning
  skill terms for the first roles (skipped when already in the role);
  intern/fresher terms apply to fresher profiles only (explicit seniority
  switches them off). Tier 4 rotates six site slots across the top three
  roles and top two locations (job boards first, then ATS). Queries go to
  the provider; nothing here touches a search engine.
- Freshness limits (measured, not assumed): no query requests a date and the
  provider sends no date filter — `include_published_date` only preserves a
  date when Tavily supplies one. LinkedIn detail pages arrive undated;
  Internshala category pages carry page-update dates (not posting dates) and
  its detail pages arrive undated; Indeed returns undated search pages.
  Keyword wording (`latest`, `posted today`) is not a date filter and must
  never be treated as one. An optional best-effort hint exists:
  `TAVILY_TIME_RANGE=day|week|month|year` is passed through to Tavily when
  set (empty default = unchanged behavior, invalid values fall back to
  unset). It does NOT guarantee results are newly posted or correctly dated,
  costs nothing extra, and never enables strict publication-date filtering
  (which would silently drop undated LinkedIn results). Newest-first
  ordering cannot be guaranteed from this data;
  `posted_at`/`first_seen_at` remain display/recency signals only.
- Classification (`worker/search/classifier.py`): URL-hostname rules only —
  `boards.greenhouse.io` → greenhouse, `jobs.lever.co` → lever,
  `jobs.ashbyhq.com` → ashby, `/careers|/jobs|/join`-style paths →
  company_career, everything else/malformed → unknown. Titles never decide.
- Targets, not jobs: `DiscoveryTarget(url, classified_source, title, snippet)`
  records *where to look with which parser later* — search results are never
  presented as postings.
- Pipeline (`worker/pipelines/search_pipeline.py`): profile → queries →
  provider → URL-deduped results → targets, returning queries
  generated/executed, results/targets counts, classification stats, errors.
  One failed query never crashes a run.
- Why no direct search-engine HTML scraping: Google/Bing ToS, CAPTCHAs, and
  rate limits prohibit automated result scraping; browser automation and
  logins are out of scope. Coverage comes from official/authorized search APIs
  (future provider) plus ATS and career-page sources.
- Adding a real provider: subclass `SearchProvider` (key via `SEARCH_API_KEY`
  only inside that provider), register it, add offline tests with faked
  transport — no pipeline changes.

## Tavily provider (Phase 6.0 — first real provider, opt-in)

- Verified endpoint (Tavily public OpenAPI, `docs.tavily.com`):
  `POST https://api.tavily.com/search` with bearer auth
  (`Authorization: Bearer <key>`) and body
  `{query, search_depth, max_results, include_answer: false,
  include_published_date: true}`. Response `results[]` carry
  `{title, url, content, score, published_date}`. Nothing guessed.
- Implementation (`worker/search/tavily.py`, stdlib urllib only): one request
  per `search()` call, bounded timeout, 5MB cap, no retries by default,
  blank queries return [] without network. Normalizes to `SearchResult`
  (title/url/snippet capped at 1500 chars; score + published date preserved
  in `raw_data`; URL-less items skipped — a lead without a URL cannot target).
- Configuration (see `.env.example`): `TAVILY_API_KEY=` (empty placeholder;
  free tier ≈ 1,000 credits/month, no card — key at https://app.tavily.com,
  server-side ONLY, never `NEXT_PUBLIC_*`, never frontend, never logged).
  `SEARCH_PROVIDER=tavily` selects it (default stays `mock`).
  `TAVILY_SEARCH_DEPTH=basic` (1 credit; `advanced` costs 2).
  Result cap 10/query, `SEARCH_TIMEOUT` reused. Missing key + tavily selected
  is an explicit per-query configuration error — never silent fallback.
- Errors: missing key, 401 (invalid key), 429/plan-limit (with `retry_after`),
  5xx, network, malformed — all typed, none carrying key material.

## Source / ATS resolver (Phase 6.1 — discovery becomes authoritative jobs)

Tavily results are leads, never jobs. `worker/sources/resolver.py` maps each
`DiscoveryTarget` URL to a `ResolvedSource` (parse-only, zero network):

- `greenhouse` + board handle from `boards.greenhouse.io/{board}` or
  `job-boards.greenhouse.io/{board}` (the connector's canonical host);
- `lever` + company handle from `jobs.lever.co/{company}`;
- `ashby` + board handle from `jobs.ashbyhq.com/{board}`;
- `company_career` / `unknown` stay queued — never fetched, never scraped.

Hostname-exact rules only: a path that merely mentions an ATS
(`example.com/careers/greenhouse`) or a lookalike host
(`boards.greenhouse.io.evil.com`) never resolves. URL normalization
(lowercased host, no fragments, tracking params stripped, credentials
dropped) happens before matching. SSRF posture: arbitrary discovered URLs
are never fetched — only recognized ATS handles reach the existing
connectors' fixed API hosts.

## Controlled ingestion (Phase 6.1)

`worker/pipelines/ingestion_pipeline.py` runs the smallest real path:

```
Tavily (<= MAX_INGESTION_QUERIES queries, default 3)
-> classifier -> DiscoveryTarget
-> resolver -> ResolvedSource
-> existing Greenhouse/Lever/Ashby source, one fetch per distinct board
   (<= MAX_INGESTION_BOARDS boards, default 5)
-> existing normalizer (+ discovery metadata in raw_data only — no schema change)
-> existing fingerprint dedupe -> existing persistence
-> STOP (no Gemini, no ranking, no notifications, no auto-apply)
```

Dry run is the default: without `--persist` + `PERSIST_DISCOVERY=true` +
`ENABLE_LIVE_INGESTION=true` + `DATABASE_URL`, zero writes occur and the
summary reports what WOULD persist. Per-board/per-job failures are isolated;
company, fingerprint, and source-link reuse are the existing behaviors.
Discovery provenance (query/provider/URL/timestamp) lives in `raw_data`
in-memory only — the SQL schema has no column for it, so no migration was
made (documented limitation).

```bash
python -m worker.main --discover --provider tavily --dry-run --max-queries 2
PERSIST_DISCOVERY=true ENABLE_LIVE_INGESTION=true DATABASE_URL=<db> \
  python -m worker.main --discover --provider tavily --persist --max-queries 3
```

## Search -> ATS resolution design (Phase 6.x, not implemented yet)

A classified target resolves by its label: `greenhouse` targets feed the
Greenhouse connector (board token derived from the URL), `lever` -> Lever
connector, `ashby` -> Ashby connector, `company_career` -> a future
company-page parser, `unknown` -> held for review, never force-parsed.
Connectors themselves are untouched by this design.

## Trust stance (unchanged)

A provider hit is DISCOVERED, never VERIFIED: Tavily results enter the
pipeline with no trust of their own. Trust is earned later — known ATS
sources, company identity, description quality, scam screening — by the
existing prefilter and trust engine. Nothing here assigns scores.

## Planned sources (not implemented yet)
- `lever/` — public Lever postings API.
- `ashby/` — public Ashby API.
- `company_careers/` — generic career-page fetching (respect robots/ToS).
- `search_engine/` — legitimate discovery entry points (respect ToS/robots).
- `manual/` — curated human-provided URLs (real version of the mock).

## Why restricted platforms are not automated directly

LinkedIn, Indeed, Internshala, etc. require login sessions, aggressively
rate-limit, and prohibit automation in their ToS; techniques like login
automation, CAPTCHA bypass, or browser-fingerprint spoofing are out of scope
and will not be implemented. Coverage for those platforms comes from
company career pages, official ATS APIs, and manual curation instead.

## How to add a new source

1. Create `worker/sources/<type>/<name>.py` with a `JobSource` subclass
   returning `DiscoveredJob` objects (stdlib only; never hardcode secrets).
2. Register it (import + `register_source(...)` near the builtin
   registration in `worker/sources/registry.py`).
3. Add an offline test in `worker/tests/test_discovery.py` (fixtures, no live calls).
4. Run `python -m worker.main` and `pytest worker/tests/` — no pipeline changes needed.

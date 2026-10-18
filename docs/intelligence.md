# Job Intelligence (Phase 5.2 — Gemini + rules, free-first)

## Architecture

```
persisted jobs (Supabase)
  -> load candidate (profiles / profile_skills / target_roles / target_locations)
  -> rule prefilter (worker/processors/intelligence/prefilter.py, no AI)
  -> Gemini via ai/providers (BaseAIProvider contract, key server-side only)
  -> strict validation (validator.py — malformed output never reaches the DB)
  -> job_matches (existing table, parameterized upserts)
```

Key files: `worker/models/intelligence.py` (JobIntelligence, strict
APPLY/CONSIDER/REVIEW/AVOID + ELIGIBLE/... vocabularies, 0–100 int scores),
`ai/prompts/job_intelligence.py` (prompt lives here, never inline),
`ai/providers/gemini.py` (stdlib-urllib REST, typed credential-free errors),
`worker/db/profile_repository.py` (profile bundle reads),
`worker/db/match_repository.py` (cache check + save),
`worker/pipelines/intelligence_pipeline.py` (orchestration + stats),
`worker/pipelines/enrichment_pipeline.py` (Phase 6.2 explicit stage).

## Phase 6.2 — explicit enrichment stage

Ingestion stays AI-free; enrichment composes the existing pipelines:

```
persisted jobs (Supabase)
  -> run_intelligence (prefilter -> Gemini -> job_matches)
  -> rank_jobs_for_profile (stored intelligence -> ranked list, zero AI)
```

```bash
python -m worker.main --enrich --dry-run          # preview: selection only, 0 calls, 0 writes
AI_ENABLED=true GEMINI_API_KEY=<key> python -m worker.main --enrich --limit 20
python -m worker.main --enrich --profile <id> --no-rank --rank-limit 10
```

`--dry-run` forces the read-only path even with AI enabled (counts land in
`jobs_would_analyze`). Ranking always consumes stored intelligence, so it
still ranks previously analyzed jobs when AI is disabled or the run
partially fails. Selection is the existing behavior: recent active jobs
(`last_seen_at DESC`, bounded by `--limit`), analyzed pairs skipped via the
`job_matches` cache, AI volume capped by `AI_MAX_JOBS_PER_RUN`.

## Rule-based prefilter

Title context decides roles (description words like sales/marketing/client
never reject a software role alone). Hard title exclusions (sales, telecaller,
recruiters, marketing, support...), senior titles and 3+ year requirements
rejected; 1–2 years passes with a concern flag. Payment-fee patterns and
DM/Telegram/WhatsApp-only application paths flag trust (a bare WhatsApp
mention is not flagged). Preliminary match/trust scores guide, never decide.

## Gemini configuration

Env only (see `.env.example`): `AI_ENABLED=false` (master switch, default
off), `AI_MAX_JOBS_PER_RUN=20` (quota cap), `AI_REQUEST_TIMEOUT_SECONDS=30`,
`GEMINI_API_KEY=` (empty placeholder, never logged/committed/exposed),
`GEMINI_MODEL=` (defaults to a flash model when unset). Worker flag
`RUN_INTELLIGENCE=true` enables the stage; without DB it prints
`database not configured — intelligence skipped`, without a key
`Gemini not configured — intelligence skipped`. Mock fixtures
(`source_name "mock"`) are always skipped with a `mock job skipped` log.

## Scoring, trust, recommendations

Prompt weights: Skills 40%, Experience 20%, Education 10%, Role 15%,
Location 10%, Compensation 5%. Trust weighs source legitimacy, company
identity, process, description quality, salary realism, scam/contact signals —
independent of match. Trust overrides: high match + very low trust → AVOID.
`job_matches` stores scores, recommendation, skill sets, strengths,
risk_signals (= concerns), reason, and `gemini:<model>` provenance.
Limitation: the schema has no eligibility column, so eligibility is evaluated,
validated, and returned — but persisted only implicitly via recommendation +
reason. No migration was made for it.

## Test commands

```bash
python -m pytest worker/tests -q        # offline (FakeGemini + FakeDB)
python -m pytest backend/tests -q
```

Gated live test (exactly one fixture, never in the normal suite):

```bash
RUN_GEMINI_LIVE_TESTS=true GEMINI_API_KEY=<key> python -m pytest worker/tests/test_gemini_live.py -v
```

## Free-tier / cost protection

Rules run before any billable call; cached evaluations are reused;
per-run AI volume is capped; sequential calls, no retries storms, no
re-analysis; mock jobs and disabled/missing-key states spend zero quota.
Logs carry counts only — never keys, prompts, or descriptions.

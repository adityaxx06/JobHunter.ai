# AI-JobHunter Daily Operations Runbook (Phase 8)

How to start, verify, and run the system day to day. Commands are the real
ones from each component README; flags match the current CLIs. No secrets
live in this file — copy `.env.example` to `.env` and fill it in locally
(never commit `.env`).

## 1. Prerequisites

- Python 3.11 (root README tech stack), Node.js + npm (see `frontend/package.json`).
- Supabase Postgres reachable; `DATABASE_URL` set (backend + worker share it).
- Optional live providers: `TAVILY_API_KEY` (Tavily search, free tier) and
  `GEMINI_API_KEY` (+ `GEMINI_MODEL`, e.g. `gemini-flash-lite-latest`) for AI
  enrichment. Absent keys = clean "not configured" states, never crashes.
- Pinned dependencies: `backend/requirements.txt`, `worker/requirements.txt`,
  `frontend/package-lock.json`. Install with `pip install -r requirements.txt`
  (backend or worker dir) and `npm ci` (frontend dir).

## 2. Starting the system

Backend (from `backend/`):
```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8001
# GET http://127.0.0.1:8001/api/health
```

Frontend (from `frontend/`):
```bash
npm ci
npm run dev     # http://localhost:3000 (needs backend for live data)
```

Worker (from repo root, offline by default — no network, no writes):
```bash
pip install -r worker/requirements.txt
python -m worker.main            # discovery + search demos
python -m worker.main --readiness
```

## 3. Health verification

- Backend: `GET /api/health` → 200 `{"status":"ok"}`.
- Database: `GET /api/db/health` → `connected` / `not_configured` /
  `unreachable` (never leaks credentials; a transient `unreachable` can
  self-clear on retry while reads still work).
- Worker: `python -m worker.main --readiness` reports Tavily / Gemini /
  database presence and the selected search provider (no network, no credits).
- Frontend: header API-status pill + `NEXT_PUBLIC_API_URL` (default
  `http://127.0.0.1:8001`, see `frontend/.env.example`).

## 4. Daily discovery workflow

All worker runs are explicit commands (no scheduler, no auto-run):

1. **Profile** (already seeded): `11111111-1111-1111-1111-111111111111`.
   Edit any time at `/profile`; discovery loads it from the DB
   (`load_search_profile`, offline fallback to defaults).
2. **Discovery (dry run first, always):**
   ```bash
   python -m worker.main --discover --provider tavily --dry-run --max-queries 5
   ```
   Expect: queries attempted/executed, search hits, targets, per-source
   resolved counts (greenhouse/lever/ashby), queued company-career/unknown,
   boards attempted/succeeded/failed, jobs fetched/normalized/unique,
   `DRY RUN — production writes: 0`, `Gemini calls: 0`.
3. **Persistence (only when the dry run looks right):** add `--persist`
   with ALL gates set, else the run stays a dry run with zero writes:
   ```bash
   PERSIST_DISCOVERY=true ENABLE_LIVE_INGESTION=true DATABASE_URL=<db> \
     python -m worker.main --discover --provider tavily --persist --max-queries 5
   ```
   Caps: `MAX_INGESTION_QUERIES` (default 3, 1–10),
   `MAX_INGESTION_BOARDS` (default 5, 1–20),
   `MAX_INGESTION_JOBS_PER_BOARD` (default 50, 1–50). Oversized ATS
   boards are rejected by the 5 MB response guard — an expected safe outcome.
4. **Prefilter + AI enrichment** (existing pipeline, needs `AI_ENABLED=true`
   plus key; at most `AI_MAX_JOBS_PER_RUN` jobs, default 20):
   ```bash
   AI_ENABLED=true GEMINI_API_KEY=<key> python -m worker.main --enrich --limit 20
   ```
   Expect: candidates, rule-rejected, eligible, sent-to-Gemini, analyzed,
   writes; per-job failures isolated. `--dry-run` previews selection with
   zero calls and zero writes.
5. **Ranking:** runs inside `--enrich` over stored intelligence (zero AI
   calls), or on demand via `GET /api/rankings/{profile_id}`.
6. **Frontend verification:** `/dashboard` (stats + top opportunities),
   `/jobs` explorer, `/jobs/[jobId]` detail, `/applications` tracker.

## 5. Configuration gates (all default safe/off)

`AI_ENABLED`, `RUN_INTELLIGENCE`, `RUN_RANKING`, `PERSIST_DISCOVERY`,
`ALLOW_MOCK_PERSIST` (mock rows need this too), `ENABLE_LIVE_INGESTION`,
`SEARCH_PROVIDER` (`mock` default; `tavily` needs key),
`AI_MAX_JOBS_PER_RUN`, `MAX_INGESTION_*`, `GEMINI_MODEL`. Missing key +
live provider selected = explicit per-query error, never silent fallback.

## 6. Troubleshooting (expected safe behavior)

- **Tavily unavailable / no key:** per-query `not_configured`/network
  errors, run completes with 0 results, 0 writes. Check `--readiness`.
- **Gemini unavailable (e.g. HTTP 503) or bad key:** per-job errors,
  successes still persist; ranking still covers stored matches. Verify the
  model name is current (retired names 404 — see runbook history).
- **Database unavailable:** CLI reports gates/skip messages, 0 writes;
  API returns 503 `database not configured/unreachable`; UI shows retry states.
- **Backend unavailable:** frontend API pill shows Down; pages show error +
  retry, never fake numbers.
- **No jobs discovered:** check query count executed vs attempted, provider
  errors in output, and whether site queries fit the `--max-queries` budget
  (generic queries fill small budgets first).
- **Jobs but no enrichment:** check prefilter-rejected count (senior/
  non-software roles are rejected by design) and `AI_ENABLED`/key/cap.
- **Resume parse failure:** 422 = bad/unreadable file; 200 +
  `parse_error.ai_unavailable` = text extracted, AI down; profile untouched
  until Apply.

## 7. Safety boundaries (non-negotiable)

No auto-apply (no such code path exists); no CAPTCHA/login bypass; no
anti-bot evasion; no protected-page scraping (LinkedIn/Internshala/Indeed
results are URL-first leads — the user applies manually on the original
site); no browser automation; resume bytes are processed in memory and
discarded, never stored or logged.

## 8. Data safety

Automated tests use mocks/fakes and never touch production data. Live runs
only write through explicit gates. Current verification baseline:

```text
jobs = 20
job_matches = 1
applications = 0
```

# AI-JobHunter

> Automatically discover relevant internships and entry-level jobs from legitimate sources, normalize and deduplicate them, evaluate match and trust scores, rank opportunities, and present the best opportunities with direct application links.

**Status:** Phase 6.2 — Post-ingestion enrichment. Discovery (Greenhouse/Lever/Ashby/search), persistence, Gemini intelligence, ranking, FastAPI API, and the Next.js dashboard (dashboard, job explorer, job details, application tracker) are implemented. Tavily search → ATS resolver → connector ingestion runs via explicit `--discover` (dry run by default); enrichment runs via explicit `--enrich` (prefilter → Gemini → ranking). No auth; no auto-apply; no scheduling.

## 1. Project overview

Entry-level job search is noisy and scam-prone. AI-JobHunter will discover postings from legitimate sources (company career pages, Greenhouse/Lever/Ashby ATS APIs, legitimate search entry points, manual curation), normalize + deduplicate them, score match + trust with Gemini, rank, and show direct application links.

Target profile (roles, locations, skills) stays configurable, never hardcoded. Initial roles: Software Developer, Software Engineer, Java Developer, Backend Developer, Backend Engineer, Full Stack Developer, Web Developer, Python Developer, AI/ML Intern, AI Engineer Intern, Machine Learning Intern — extensible without restructuring.

## 2. Architecture

```
sources/* (adapters -> worker/sources/base.py)
  -> worker/processors: normalizer -> deduplicator -> filter
  -> worker/processors/scorer (ai/match_engine + ai/trust_engine via ai/providers/base.py)
  -> worker/processors/ranker
  -> database (Supabase/Postgres, planned)
  -> backend (FastAPI) -> frontend (Next.js)
  -> automation (schedules + notifications)
```

- `frontend/` — Next.js 14 dashboard (App Router): `/dashboard`, `/jobs`
  explorer with server-side search/filters/sort/pagination, `/jobs/[jobId]`
  details, `/applications` tracker. Dark-first Tailwind UI, typed API client.
- `backend/` — FastAPI API: health, jobs (search/filter/sort/page), job
  detail + stored intelligence, matches, deterministic rankings (zero AI
  calls), applications CRUD, saved-jobs. Parameterized psycopg access.
- `worker/` — discovery (mock + Greenhouse/Lever/Ashby + search), normalize →
  deduplicate → persist (opt-in), Gemini intelligence (opt-in), ranking.
- `ai/` — provider-independent Gemini layer (server/worker-side only).
- `database/` — legacy reference copies (Phase 2 canonical schema is `supabase/`).
- `supabase/` — PostgreSQL migrations (`migrations/001_initial_schema.sql`), `seed.sql`, `config.toml`. See Database section below.
- `automation/` — schedules/notifications (future).
- `docs/` — architecture, job-schema, scoring, sources, ranking, intelligence, roadmap.

## 3. Tech stack

- Frontend: Next.js 14, TypeScript, Tailwind CSS 3, App Router.
- Backend: Python 3.11, FastAPI, Pydantic / pydantic-settings, Uvicorn.
- Worker: Python (discovery connectors, persistence, Gemini intelligence, ranking).
- Database: PostgreSQL via Supabase (migrations versioned in `supabase/`).
- AI: Gemini API (primary), provider-independent (`ai/providers/base.py`); worker-only calls, never from the browser.

## 4. Development setup

Frontend (independent):

```bash
cd frontend
npm install
npm run dev    # http://localhost:3000
npm run build  # production check
```

Backend (independent):

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
# GET http://127.0.0.1:8001/api/health
```

Worker (independent):

```bash
python worker/main.py
```

Notes: run from repo root `python worker/main.py` or `cd worker`. No scraping, no Gemini calls in Phase 1.

## 5. Environment variables

Copy `.env.example` to `.env` (never commit `.env`):

```
GEMINI_API_KEY=            # server-side only — NEVER expose to Next.js client
GEMINI_MODEL=
DATABASE_URL=
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
API_HOST= / API_PORT=
NOTIFICATION_WEBHOOK_URL= / CRON_SCHEDULE=
```

Frontend uses only `NEXT_PUBLIC_API_URL` (see `frontend/.env.example`). Security: `.gitignore` covers `.env`, `.env.*` (except `!.env.example`), `__pycache__/`, `node_modules/`, `.next/`, `.venv/`, `*.pyc` / `*.py[cod]`.

## Configuration (Supabase + backend)

1. Create/configure a Supabase project (dashboard) — nothing in this repo connects automatically.
2. Obtain database connection details: `DATABASE_URL` (Postgres connection string), `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY` (backend-only).
3. Put credentials into a local `.env` (copy from `.env.example`). The backend reads `.env` via `backend/app/core/config.py`; the worker reads `DATABASE_URL` from the environment.
4. Never commit `.env` (gitignored; only `.env.example` with empty placeholders is tracked).
5. Start the backend: `cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload`.
6. Test `GET /api/health` → `{"status":"ok","service":"AI-JobHunter API"}` (works with or without a database).
7. Test `GET /api/db/health` → `{"status":"ok","database":"connected"}` when reachable, or `{"status":"not_configured","database":"not_configured"}` when `DATABASE_URL` is absent. No credentials are ever returned.

Apply schema/seed explicitly on a dev database only: `supabase db reset` (migrations + `supabase/seed.sql`). Never auto-run against remote.

## Database (Supabase PostgreSQL)

Supabase PostgreSQL is the database. No Prisma — schema changes live as version-controlled SQL in `supabase/migrations/` (safe to run from a clean DB), never dashboard-only edits.

- `supabase/migrations/001_initial_schema.sql` — 12 tables (`profiles, profile_skills, target_roles, target_locations, companies, jobs, job_sources, job_matches, saved_jobs, applications, search_queries, notifications`) with constraints, indexes, RLS, and `updated_at` triggers. Details in `docs/job-schema.md`.
- `supabase/seed.sql` — generic MCA fresher dev profile (skills, learning skills, 11 target roles, locations incl. Remote). No personal data. Apply via `supabase db reset` once the CLI is available.
- `supabase/config.toml` — minimal CLI config (CLI not installed locally; `supabase init/link` will expand it when you authorize a project).
- Security: RLS on all user tables (owner-or-unclaimed MVP policies, tightened when Auth ships); `companies/jobs/job_sources` public-read, backend-write. Service-role key backend-only, never in frontend or source.

Local workflow (requires Supabase CLI + Docker, neither installed here — nothing done automatically):

```bash
npm i -g supabase
supabase start     # local stack
supabase db reset  # migrations + seed
# supabase link + supabase db push — only when YOU authorize a remote project
```

## 6. Current status

Completed through Phase 5.5F (final polish):

- [x] Foundation, Supabase schema (12 tables + RLS), FastAPI + psycopg layer
- [x] Discovery framework + Greenhouse/Lever/Ashby connectors + search (all conservative, offline-safe)
- [x] Persistence (opt-in), Gemini intelligence (opt-in, validated), deterministic ranking (zero-AI API)
- [x] FastAPI dashboard API: jobs, detail + intelligence, matches, rankings, applications CRUD, saved-jobs
- [x] Next.js dashboard: overview, job explorer (`/jobs`), job details (`/jobs/[jobId]`), application tracker (`/applications`), shared save state

Explicitly NOT active: automated real-world ingestion (opt-in worker modes only), auth, notifications.

## 7. Phases

- Phase 1 — Foundation (done)
- Phase 2 — Database (done)
- Phase 3 — User/job profile data layer (done)
- Phase 4.1–4.3 — Discovery framework, Greenhouse/Lever/Ashby, search (done)
- Phase 5.1 — Persistence (done)
- Phase 5.2 — Gemini intelligence (done)
- Phase 5.3 — Ranking (done)
- Phase 5.4 — FastAPI intelligence API (done)
- Phase 5.5A–5.5F — Dashboard, cards, explorer, details, tracker, polish (done)

Next: real job ingestion/discovery activation (separate stage).

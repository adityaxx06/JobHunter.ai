# Architecture

Goal: discover internships/entry-level jobs from legitimate sources, normalize,
deduplicate, score (match + trust), rank, present with direct application links.

## Flow (Phase 3 — backend + worker own all database access)

```
Next.js frontend
  ↓  (HTTP only, NEXT_PUBLIC_API_URL; no secrets in the browser)
FastAPI backend
  ↓  (psycopg, parameterized SQL, DATABASE_URL — server-side only)
Supabase PostgreSQL (PostgreSQL is the source of truth, Supabase hosts it)
  ↑  (psycopg, DATABASE_URL — server-side only)
Python worker (scheduled discovery/processing; connection layer only in Phase 3)
```

## Data path (planned, stages land in later phases)

```
sources/* (adapters)
  -> processors/normalizer -> deduplicator -> filter
  -> processors/scorer (ai/match_engine + ai/trust_engine)
  -> processors/ranker
  -> database -> backend API -> frontend
```

## Decisions

- No Prisma. Direct PostgreSQL via `psycopg[binary]` with a small hand-written
  layer (`backend/app/db/`: connection pool, repositories per aggregate). A
  large ORM would add indirection without benefit at MVP scale; repositories
  keep every query parameterized and auditable in one place.
- PostgreSQL is the source of truth. Supabase hosts it (auth/storage available
  later); the app talks plain SQL over `DATABASE_URL`, so the data layer stays
  portable even if hosting changes.
- Migrations remain version-controlled (`supabase/migrations/*.sql`), applied
  with the Supabase CLI workflow. Never dashboard-only edits. Seed
  (`supabase/seed.sql`) is applied explicitly with `supabase db reset` on a
  dev database — never auto-run against remote.
- Secrets remain server-side. `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`,
  and `GEMINI_API_KEY` never reach the browser: the frontend only ever sees
  `NEXT_PUBLIC_*` public config. `SUPABASE_SERVICE_ROLE_KEY` is not even
  required for normal backend work (PostgreSQL uses `DATABASE_URL`); it is
  reserved for Supabase API operations that specifically need it.
- App boots without a database. `GET /api/health` always works;
  `GET /api/db/health` reports `not_configured` until `DATABASE_URL` is set.

## Principles

- Profile (roles, locations, skills) is configurable, never hardcoded.
- New sources/filters/roles plug in without restructuring.
- Direct application links preferred; no apply-spam automation.
- Respect source ToS / robots.

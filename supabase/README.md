# Supabase — version-controlled Postgres (Phase 2)

Canonical schema lives in `supabase/` (NOT only in the dashboard):

- `supabase/migrations/001_initial_schema.sql` — 12 tables, constraints, indexes, RLS + `updated_at` triggers.
- `supabase/seed.sql` — generic dev profile (MCA, fresher, skills/roles/locations). No personal data.
- `supabase/config.toml` — minimal CLI config (CLI not installed locally yet).

Legacy `database/` folder is kept for reference; `supabase/` is canonical for migrations.

Workflow (once CLI is available):

```bash
npm i -g supabase   # or scoop/choco on Windows
supabase init       # expands config (already scaffolded here)
supabase start      # local stack (requires Docker)
supabase db reset   # apply migrations + seed locally
supabase link       # only when YOU authorize a remote project
supabase db push    # push migrations to linked project
```

Security: RLS enabled on all user tables; `companies`/`jobs`/`job_sources` are public-read, backend-write (service_role bypasses RLS, stays backend-only, never in frontend).

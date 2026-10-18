# Job Schema (Phase 2 — Supabase PostgreSQL)

Canonical migration: `supabase/migrations/001_initial_schema.sql`. Dev seed: `supabase/seed.sql`.
No Prisma. Schema changes only via versioned SQL migrations, never dashboard-only edits.

## Tables

### profiles — user job-search profile
- `id UUID PK`, `user_id UUID NULL` (nullable for single-user MVP; set to `auth.uid()` when Supabase Auth ships).
- `full_name, education, experience_level, preferred_work_mode TEXT`, `relocation_allowed BOOL DEFAULT true`, `minimum_stipend INT NULL`.
- `created_at / updated_at TIMESTAMPTZ DEFAULT NOW()` (auto-bumped by `handle_updated_at()` trigger).
- Relationships: parent of `profile_skills, target_roles, target_locations, job_matches, saved_jobs, applications, search_queries, notifications`.

### profile_skills — skills per profile
- `id PK`, `profile_id FK CASCADE`, `skill_name NOT NULL`, `skill_level`, `is_learning DEFAULT false`, `created_at`.
- `UNIQUE(profile_id, skill_name)` prevents duplicate skills. Index on `profile_id`.

### target_roles — wanted roles as editable data (never hardcoded)
- `id PK`, `profile_id FK CASCADE`, `role_name NOT NULL`, `priority DEFAULT 1`, `created_at`.
- `UNIQUE(profile_id, role_name)`. Seed: Software Developer, Software Engineer, Java Developer, Backend Developer, Backend Engineer, Full Stack Developer, Web Developer, Python Developer, AI/ML Intern, AI Engineer Intern, Machine Learning Intern.

### target_locations — wanted locations; remote via flag
- `id PK`, `profile_id FK CASCADE`, `location_name NOT NULL`, `is_remote DEFAULT false`, `priority DEFAULT 1`, `created_at`.
- `UNIQUE(profile_id, location_name)`. Seed: India, Chennai, Bangalore, Hyderabad, Pune, Mumbai, Delhi NCR, Gurgaon, Noida, Kolkata + `Remote/is_remote=true`.

### companies — canonical company
- `id PK`, `name NOT NULL`, `normalized_name NOT NULL UNIQUE` (dedup key), `website_url, careers_url, logo_url, description, domain`, `created_at/updated_at`.
- Index on `domain`. One company -> many `jobs` (`company_id ON DELETE SET NULL`).

### jobs — canonical normalized opportunity
- `id PK`, `company_id FK SET NULL`, `title NOT NULL`, `normalized_title NOT NULL`, `description`, `location`, `is_remote DEFAULT false`, `employment_type, experience_level`, `salary_min/max NULL`, `salary_currency DEFAULT 'INR'`, `salary_period NULL`, `skills JSONB DEFAULT '[]'`, `posted_at NULL`, `first_seen_at/last_seen_at DEFAULT NOW()`, `canonical_url, apply_url`, `status DEFAULT 'active'`, `created_at/updated_at`.
- Indexes: `company_id, normalized_title, location, posted_at, status, is_remote`.
- Deliberately NO unique on title/company/location — similar postings can be legitimately distinct; dedup happens via `job_sources` + fingerprint logic later.

### job_sources — where a job was found (one job -> many sources)
- `id PK`, `job_id FK CASCADE`, `source_type NOT NULL CHECK IN (company_careers, greenhouse, lever, ashby, search_engine, job_board, manual)`, `source_name NOT NULL`, `source_url, apply_url`, `discovered_at DEFAULT NOW()`, `source_job_id NULL`, `metadata JSONB DEFAULT '{}'`.
- Indexes on `job_id, source_type, source_job_id`; unique `(job_id, source_type, source_name, source_job_id)`.
- Example: "Java Developer Intern — ABC" has rows for Company Careers + Greenhouse + Search Engine.

### job_matches — evaluation of a job vs a profile (conceptual)
- `id PK`, `profile_id FK CASCADE`, `job_id FK CASCADE`, `match_score INT NULL CHECK 0–100`, `trust_score INT NULL CHECK 0–100`, `recommendation TEXT` (free text for now; APPLY/MAYBE/SKIP in Phase 6+), `matched_skills/missing_skills/strengths/risk_signals JSONB DEFAULT '[]'`, `reason, analyzed_by, analyzed_at`, `created_at/updated_at`.
- `UNIQUE(profile_id, job_id)` — one evaluation per profile+job. Indexes on `profile_id, job_id, match_score`.
- Concept: worker `scorer` calls `ai/match_engine` (fit) + `ai/trust_engine` (legitimacy), writes one row here; `ranker` sorts by it. No scoring in Phase 2.

### saved_jobs — manual saves
- `id PK`, `profile_id FK CASCADE`, `job_id FK CASCADE`, `created_at`. `UNIQUE(profile_id, job_id)`.

### applications — application tracker
- `id PK`, `profile_id FK CASCADE`, `job_id FK CASCADE`, `status DEFAULT 'saved' CHECK IN (saved, applied, assessment, interview, offer, rejected, withdrawn)`, `applied_at NULL`, `notes NULL`, `created_at/updated_at`.
- `UNIQUE(profile_id, job_id)` — one tracker row per profile+job; status transitions instead of duplicate rows.

### search_queries — discovery-worker search definitions
- `id PK`, `profile_id FK CASCADE`, `query NOT NULL`, `source_type`, `location NULL`, `role NULL`, `last_run_at NULL`, `created_at`. Index on `profile_id`.

### notifications — notification history
- `id PK`, `profile_id FK CASCADE`, `type NOT NULL`, `channel NOT NULL`, `title, message`, `job_id FK SET NULL`, `sent_at NULL`, `status DEFAULT 'pending'`, `created_at`. Indexes on `profile_id, status`.

## RLS / security

- RLS enabled on all 12 tables.
- User tables (`profiles, profile_skills, target_roles, target_locations, job_matches, saved_jobs, applications, search_queries, notifications`): owner-or-unclaimed policies — rows with `user_id IS NULL` (MVP) or `user_id = auth.uid()` (post-Auth); child tables check via parent `profiles` row. Tighten to strict ownership when Auth ships.
- Shared tables (`companies, jobs, job_sources`): `SELECT` for `anon, authenticated`; no write policies (backend `service_role` bypasses RLS). Service-role key stays backend-only, never in frontend or source.

## Persistence mapping (Phase 5.1 — worker/db/job_repository.py, schema unchanged)

DiscoveredJob (normalized) maps onto existing columns only:
- normalized_title -> normalized_title; original.title -> title
- original.description (blank becomes NULL) -> description
- original.location (blank becomes NULL) -> location; normalized is_remote -> is_remote
- normalized employment (fallback: original) -> employment_type
- original.experience_level (blank becomes NULL) -> experience_level
- integer salary_min/max (else NULL); salary_currency (else schema default)
- normalized_skills as JSONB array -> skills; posted_at -> posted_at
- apply_url fills BOTH canonical_url and apply_url (the stable posting link)
- status keeps the schema default (active); last_seen_at is touched on re-seen

jobs -> job_sources: one row per (job, source_type, source_name, external_id),
looked up with IS NOT DISTINCT FROM so re-discovery reuses the row. The
fingerprint is stored in metadata for audit. Source types satisfy the CHECK.

Company dedup: normalize via the normalizer, SELECT by UNIQUE(normalized_name),
insert only when absent (domain stored only when actually provided, never
invented). Jobs with no company info keep company_id NULL, which the schema
allows.

Fingerprint strategy: existing SHA-256 over normalized company + title +
location + apply URL (worker/utils/job_fingerprint.py — no second algorithm,
no schema column). Lookup: exact apply_url match first, else scan the latest
200 normalized_title candidates and compare fingerprints in Python. Equal
fingerprints mean all four signals match, so same-company/similar-title rows
with different locations or URLs never merge.

Idempotency: re-persisting fills only blank/stale mutable columns (good values
are never overwritten with blanks), touches last_seen_at, and reuses the
job_sources row. A second identical run inserts nothing. Each job persists in
one transaction (company + job + source link); failures roll back and are
reported per job without aborting the run. Mock fixtures persist only with
explicit ALLOW_MOCK_PERSIST=true.

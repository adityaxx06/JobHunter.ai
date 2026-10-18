-- AI-JobHunter initial schema (Phase 2 — Supabase PostgreSQL).
-- Safe to run on a clean database. Re-runnable (IF NOT EXISTS + DROP IF EXISTS for policies/triggers).
-- No Prisma. Schema versioned here; do NOT create tables manually via dashboard.
-- Remote/dev notes: run with `supabase db push` (CLI) once a linked project exists.
-- No production/remote writes from this scaffold phase.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- updated_at helper: reused by every table carrying an updated_at column.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- 1. profiles — user job-search profile (single-user MVP: user_id nullable;
--    wire Supabase Auth later by setting user_id = auth.uid()).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NULL,
  full_name TEXT,
  education TEXT,
  experience_level TEXT,
  preferred_work_mode TEXT,
  relocation_allowed BOOLEAN NOT NULL DEFAULT true,
  minimum_stipend INTEGER NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 2. profile_skills — skills per profile; no duplicate skill per profile.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.profile_skills (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id UUID NOT NULL REFERENCES public.profiles (id) ON DELETE CASCADE,
  skill_name TEXT NOT NULL,
  skill_level TEXT,
  is_learning BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT profile_skills_profile_skill_unique UNIQUE (profile_id, skill_name)
);
CREATE INDEX IF NOT EXISTS idx_profile_skills_profile_id ON public.profile_skills (profile_id);

-- ---------------------------------------------------------------------------
-- 3. target_roles — wanted roles as editable data (never hardcoded in app).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.target_roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id UUID NOT NULL REFERENCES public.profiles (id) ON DELETE CASCADE,
  role_name TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT target_roles_profile_role_unique UNIQUE (profile_id, role_name)
);
CREATE INDEX IF NOT EXISTS idx_target_roles_profile_id ON public.target_roles (profile_id);

-- ---------------------------------------------------------------------------
-- 4. target_locations — wanted locations; remote via is_remote flag.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.target_locations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id UUID NOT NULL REFERENCES public.profiles (id) ON DELETE CASCADE,
  location_name TEXT NOT NULL,
  is_remote BOOLEAN NOT NULL DEFAULT false,
  priority INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT target_locations_profile_location_unique UNIQUE (profile_id, location_name)
);
CREATE INDEX IF NOT EXISTS idx_target_locations_profile_id ON public.target_locations (profile_id);

-- ---------------------------------------------------------------------------
-- 5. companies — canonical company; normalized_name prevents duplicates.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.companies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  website_url TEXT,
  careers_url TEXT,
  logo_url TEXT,
  description TEXT,
  domain TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT companies_normalized_name_unique UNIQUE (normalized_name)
);
CREATE INDEX IF NOT EXISTS idx_companies_domain ON public.companies (domain);

-- ---------------------------------------------------------------------------
-- 6. jobs — canonical normalized opportunity. No aggressive unique on
--    title/company/location: similar postings can be legitimately distinct.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NULL REFERENCES public.companies (id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  normalized_title TEXT NOT NULL,
  description TEXT,
  location TEXT,
  is_remote BOOLEAN NOT NULL DEFAULT false,
  employment_type TEXT,
  experience_level TEXT,
  salary_min INTEGER NULL,
  salary_max INTEGER NULL,
  salary_currency TEXT NOT NULL DEFAULT 'INR',
  salary_period TEXT NULL,
  skills JSONB NOT NULL DEFAULT '[]'::jsonb,
  posted_at TIMESTAMPTZ NULL,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  canonical_url TEXT,
  apply_url TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_jobs_company_id ON public.jobs (company_id);
CREATE INDEX IF NOT EXISTS idx_jobs_normalized_title ON public.jobs (normalized_title);
CREATE INDEX IF NOT EXISTS idx_jobs_location ON public.jobs (location);
CREATE INDEX IF NOT EXISTS idx_jobs_posted_at ON public.jobs (posted_at);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON public.jobs (status);
CREATE INDEX IF NOT EXISTS idx_jobs_is_remote ON public.jobs (is_remote);

-- ---------------------------------------------------------------------------
-- 7. job_sources — where a job was found. One canonical job -> many sources.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.job_sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES public.jobs (id) ON DELETE CASCADE,
  source_type TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_url TEXT,
  apply_url TEXT,
  discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  source_job_id TEXT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT job_sources_type_check CHECK (
    source_type IN (
      'company_careers', 'greenhouse', 'lever', 'ashby',
      'search_engine', 'job_board', 'manual'
    )
  )
);
CREATE INDEX IF NOT EXISTS idx_job_sources_job_id ON public.job_sources (job_id);
CREATE INDEX IF NOT EXISTS idx_job_sources_source_type ON public.job_sources (source_type);
CREATE INDEX IF NOT EXISTS idx_job_sources_source_job_id ON public.job_sources (source_job_id);
-- Prevent exact duplicate ingestion rows (NULL source_job_id rows stay distinct in PG, which is acceptable).
CREATE UNIQUE INDEX IF NOT EXISTS uq_job_sources_job_source_extid
  ON public.job_sources (job_id, source_type, source_name, source_job_id);

-- ---------------------------------------------------------------------------
-- 8. job_matches — AI/rule evaluation of a job vs a profile (scores 0-100).
--    recommendation intentionally free TEXT (APPLY/MAYBE/SKIP later, flexible).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.job_matches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id UUID NOT NULL REFERENCES public.profiles (id) ON DELETE CASCADE,
  job_id UUID NOT NULL REFERENCES public.jobs (id) ON DELETE CASCADE,
  match_score INTEGER NULL,
  trust_score INTEGER NULL,
  recommendation TEXT,
  matched_skills JSONB NOT NULL DEFAULT '[]'::jsonb,
  missing_skills JSONB NOT NULL DEFAULT '[]'::jsonb,
  strengths JSONB NOT NULL DEFAULT '[]'::jsonb,
  risk_signals JSONB NOT NULL DEFAULT '[]'::jsonb,
  reason TEXT,
  analyzed_by TEXT,
  analyzed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT job_matches_profile_job_unique UNIQUE (profile_id, job_id),
  CONSTRAINT job_matches_match_score_range CHECK (match_score IS NULL OR (match_score BETWEEN 0 AND 100)),
  CONSTRAINT job_matches_trust_score_range CHECK (trust_score IS NULL OR (trust_score BETWEEN 0 AND 100))
);
CREATE INDEX IF NOT EXISTS idx_job_matches_profile_id ON public.job_matches (profile_id);
CREATE INDEX IF NOT EXISTS idx_job_matches_job_id ON public.job_matches (job_id);
CREATE INDEX IF NOT EXISTS idx_job_matches_match_score ON public.job_matches (match_score);

-- ---------------------------------------------------------------------------
-- 9. saved_jobs — manual saves; one row per profile+job.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.saved_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id UUID NOT NULL REFERENCES public.profiles (id) ON DELETE CASCADE,
  job_id UUID NOT NULL REFERENCES public.jobs (id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT saved_jobs_profile_job_unique UNIQUE (profile_id, job_id)
);
CREATE INDEX IF NOT EXISTS idx_saved_jobs_profile_id ON public.saved_jobs (profile_id);

-- ---------------------------------------------------------------------------
-- 10. applications — tracker; one row per profile+job, status transitions.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.applications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id UUID NOT NULL REFERENCES public.profiles (id) ON DELETE CASCADE,
  job_id UUID NOT NULL REFERENCES public.jobs (id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'saved',
  applied_at TIMESTAMPTZ NULL,
  notes TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT applications_profile_job_unique UNIQUE (profile_id, job_id),
  CONSTRAINT applications_status_check CHECK (
    status IN ('saved', 'applied', 'assessment', 'interview', 'offer', 'rejected', 'withdrawn')
  )
);
CREATE INDEX IF NOT EXISTS idx_applications_profile_id ON public.applications (profile_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON public.applications (status);

-- ---------------------------------------------------------------------------
-- 11. search_queries — discovery-worker search definitions.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.search_queries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id UUID NOT NULL REFERENCES public.profiles (id) ON DELETE CASCADE,
  query TEXT NOT NULL,
  source_type TEXT,
  location TEXT NULL,
  role TEXT NULL,
  last_run_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_search_queries_profile_id ON public.search_queries (profile_id);

-- ---------------------------------------------------------------------------
-- 12. notifications — notification history.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id UUID NOT NULL REFERENCES public.profiles (id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  channel TEXT NOT NULL,
  title TEXT,
  message TEXT,
  job_id UUID NULL REFERENCES public.jobs (id) ON DELETE SET NULL,
  sent_at TIMESTAMPTZ NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notifications_profile_id ON public.notifications (profile_id);
CREATE INDEX IF NOT EXISTS idx_notifications_status ON public.notifications (status);

-- ---------------------------------------------------------------------------
-- updated_at triggers (only tables carrying updated_at).
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_profiles_updated_at ON public.profiles;
CREATE TRIGGER trg_profiles_updated_at
  BEFORE UPDATE ON public.profiles
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS trg_companies_updated_at ON public.companies;
CREATE TRIGGER trg_companies_updated_at
  BEFORE UPDATE ON public.companies
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS trg_jobs_updated_at ON public.jobs;
CREATE TRIGGER trg_jobs_updated_at
  BEFORE UPDATE ON public.jobs
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS trg_job_matches_updated_at ON public.job_matches;
CREATE TRIGGER trg_job_matches_updated_at
  BEFORE UPDATE ON public.job_matches
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS trg_applications_updated_at ON public.applications;
CREATE TRIGGER trg_applications_updated_at
  BEFORE UPDATE ON public.applications
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

-- ---------------------------------------------------------------------------
-- ROW LEVEL SECURITY
-- User tables: owner-or-unclaimed-profile access (MVP: user_id NULL rows are
-- readable/writable; tighten to strict auth.uid() ownership when Auth ships).
-- Shared discovery tables (companies/jobs/job_sources): public read, backend
-- (service_role bypasses RLS) writes. Service-role key stays backend-only.
-- ---------------------------------------------------------------------------
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profile_skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.target_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.target_locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.job_matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.saved_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.search_queries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.job_sources ENABLE ROW LEVEL SECURITY;

-- profiles: own-or-unclaimed
DROP POLICY IF EXISTS profiles_owner_access ON public.profiles;
CREATE POLICY profiles_owner_access ON public.profiles
  FOR ALL TO authenticated, anon
  USING (user_id IS NULL OR user_id = auth.uid())
  WITH CHECK (user_id IS NULL OR user_id = auth.uid());

-- profile_skills: via parent profile
DROP POLICY IF EXISTS profile_skills_owner_access ON public.profile_skills;
CREATE POLICY profile_skills_owner_access ON public.profile_skills
  FOR ALL TO authenticated, anon
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = profile_skills.profile_id
        AND (p.user_id IS NULL OR p.user_id = auth.uid())
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = profile_skills.profile_id
        AND (p.user_id IS NULL OR p.user_id = auth.uid())
    )
  );

-- target_roles: via parent profile
DROP POLICY IF EXISTS target_roles_owner_access ON public.target_roles;
CREATE POLICY target_roles_owner_access ON public.target_roles
  FOR ALL TO authenticated, anon
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = target_roles.profile_id
        AND (p.user_id IS NULL OR p.user_id = auth.uid())
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = target_roles.profile_id
        AND (p.user_id IS NULL OR p.user_id = auth.uid())
    )
  );

-- target_locations: via parent profile
DROP POLICY IF EXISTS target_locations_owner_access ON public.target_locations;
CREATE POLICY target_locations_owner_access ON public.target_locations
  FOR ALL TO authenticated, anon
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = target_locations.profile_id
        AND (p.user_id IS NULL OR p.user_id = auth.uid())
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = target_locations.profile_id
        AND (p.user_id IS NULL OR p.user_id = auth.uid())
    )
  );

-- job_matches: via parent profile
DROP POLICY IF EXISTS job_matches_owner_access ON public.job_matches;
CREATE POLICY job_matches_owner_access ON public.job_matches
  FOR ALL TO authenticated, anon
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = job_matches.profile_id
        AND (p.user_id IS NULL OR p.user_id = auth.uid())
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = job_matches.profile_id
        AND (p.user_id IS NULL OR p.user_id = auth.uid())
    )
  );

-- saved_jobs: via parent profile
DROP POLICY IF EXISTS saved_jobs_owner_access ON public.saved_jobs;
CREATE POLICY saved_jobs_owner_access ON public.saved_jobs
  FOR ALL TO authenticated, anon
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = saved_jobs.profile_id
        AND (p.user_id IS NULL OR p.user_id = auth.uid())
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = saved_jobs.profile_id
        AND (p.user_id IS NULL OR p.user_id = auth.uid())
    )
  );

-- applications: via parent profile
DROP POLICY IF EXISTS applications_owner_access ON public.applications;
CREATE POLICY applications_owner_access ON public.applications
  FOR ALL TO authenticated, anon
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = applications.profile_id
        AND (p.user_id IS NULL OR p.user_id = auth.uid())
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = applications.profile_id
        AND (p.user_id IS NULL OR p.user_id = auth.uid())
    )
  );

-- search_queries: via parent profile
DROP POLICY IF EXISTS search_queries_owner_access ON public.search_queries;
CREATE POLICY search_queries_owner_access ON public.search_queries
  FOR ALL TO authenticated, anon
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = search_queries.profile_id
        AND (p.user_id IS NULL OR p.user_id = auth.uid())
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = search_queries.profile_id
        AND (p.user_id IS NULL OR p.user_id = auth.uid())
    )
  );

-- notifications: via parent profile
DROP POLICY IF EXISTS notifications_owner_access ON public.notifications;
CREATE POLICY notifications_owner_access ON public.notifications
  FOR ALL TO authenticated, anon
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = notifications.profile_id
        AND (p.user_id IS NULL OR p.user_id = auth.uid())
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = notifications.profile_id
        AND (p.user_id IS NULL OR p.user_id = auth.uid())
    )
  );

-- Shared discovery data: public read; writes only via service_role/backend (no write policy for anon/authenticated).
DROP POLICY IF EXISTS companies_public_read ON public.companies;
CREATE POLICY companies_public_read ON public.companies
  FOR SELECT TO authenticated, anon USING (true);

DROP POLICY IF EXISTS jobs_public_read ON public.jobs;
CREATE POLICY jobs_public_read ON public.jobs
  FOR SELECT TO authenticated, anon USING (true);

DROP POLICY IF EXISTS job_sources_public_read ON public.job_sources;
CREATE POLICY job_sources_public_read ON public.job_sources
  FOR SELECT TO authenticated, anon USING (true);

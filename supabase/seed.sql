-- AI-JobHunter dev seed (Phase 2). Idempotent via ON CONFLICT DO NOTHING.
-- Generic development profile only — NO sensitive personal information.
-- Run: `supabase db reset` (applies seed) or psql < supabase/seed.sql on a dev DB.
-- Never run against production.

-- Fixed dev profile id keeps child inserts deterministic across re-seeds.
INSERT INTO public.profiles (id, user_id, full_name, education, experience_level, preferred_work_mode, relocation_allowed, minimum_stipend)
VALUES (
  '11111111-1111-1111-1111-111111111111',
  NULL,
  'Dev Candidate',
  'MCA',
  'Fresher / Student',
  'Remote + On-site',
  true,
  NULL
)
ON CONFLICT (id) DO NOTHING;

-- Owned skills (is_learning = false)
INSERT INTO public.profile_skills (profile_id, skill_name, skill_level, is_learning)
VALUES
  ('11111111-1111-1111-1111-111111111111', 'Java', 'intermediate', false),
  ('11111111-1111-1111-1111-111111111111', 'Python', 'intermediate', false),
  ('11111111-1111-1111-1111-111111111111', 'JavaScript', 'intermediate', false),
  ('11111111-1111-1111-1111-111111111111', 'HTML', 'intermediate', false),
  ('11111111-1111-1111-1111-111111111111', 'CSS', 'intermediate', false),
  ('11111111-1111-1111-1111-111111111111', 'SQL', 'beginner', false),
  ('11111111-1111-1111-1111-111111111111', 'Git', 'intermediate', false),
  ('11111111-1111-1111-1111-111111111111', 'GitHub', 'intermediate', false),
  ('11111111-1111-1111-1111-111111111111', 'OOP', 'intermediate', false),
  ('11111111-1111-1111-1111-111111111111', 'DSA', 'beginner', false)
ON CONFLICT (profile_id, skill_name) DO NOTHING;

-- Learning skills (is_learning = true)
INSERT INTO public.profile_skills (profile_id, skill_name, skill_level, is_learning)
VALUES
  ('11111111-1111-1111-1111-111111111111', 'React', 'learning', true),
  ('11111111-1111-1111-1111-111111111111', 'Spring Boot', 'learning', true),
  ('11111111-1111-1111-1111-111111111111', 'REST APIs', 'learning', true),
  ('11111111-1111-1111-1111-111111111111', 'AI/ML', 'learning', true)
ON CONFLICT (profile_id, skill_name) DO NOTHING;

-- Target roles (editable data, not app logic)
INSERT INTO public.target_roles (profile_id, role_name, priority)
VALUES
  ('11111111-1111-1111-1111-111111111111', 'Software Developer', 1),
  ('11111111-1111-1111-1111-111111111111', 'Software Engineer', 1),
  ('11111111-1111-1111-1111-111111111111', 'Java Developer', 1),
  ('11111111-1111-1111-1111-111111111111', 'Backend Developer', 1),
  ('11111111-1111-1111-1111-111111111111', 'Backend Engineer', 2),
  ('11111111-1111-1111-1111-111111111111', 'Full Stack Developer', 2),
  ('11111111-1111-1111-1111-111111111111', 'Web Developer', 2),
  ('11111111-1111-1111-1111-111111111111', 'Python Developer', 2),
  ('11111111-1111-1111-1111-111111111111', 'AI/ML Intern', 1),
  ('11111111-1111-1111-1111-111111111111', 'AI Engineer Intern', 1),
  ('11111111-1111-1111-1111-111111111111', 'Machine Learning Intern', 1)
ON CONFLICT (profile_id, role_name) DO NOTHING;

-- Preferred locations (remote tracked separately via is_remote)
INSERT INTO public.target_locations (profile_id, location_name, is_remote, priority)
VALUES
  ('11111111-1111-1111-1111-111111111111', 'India', false, 1),
  ('11111111-1111-1111-1111-111111111111', 'Chennai', false, 1),
  ('11111111-1111-1111-1111-111111111111', 'Bangalore', false, 1),
  ('11111111-1111-1111-1111-111111111111', 'Hyderabad', false, 2),
  ('11111111-1111-1111-1111-111111111111', 'Pune', false, 2),
  ('11111111-1111-1111-1111-111111111111', 'Mumbai', false, 2),
  ('11111111-1111-1111-1111-111111111111', 'Delhi NCR', false, 2),
  ('11111111-1111-1111-1111-111111111111', 'Gurgaon', false, 3),
  ('11111111-1111-1111-1111-111111111111', 'Noida', false, 3),
  ('11111111-1111-1111-1111-111111111111', 'Kolkata', false, 3),
  ('11111111-1111-1111-1111-111111111111', 'Remote', true, 1)
ON CONFLICT (profile_id, location_name) DO NOTHING;

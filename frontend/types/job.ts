// Canonical frontend models mirroring backend/app/schemas/jobs.py (Phase 5.4).
// No `any` — every API shape is typed. Unknown recommendation strings from
// the API are tolerated at runtime but never invented here.

export type Recommendation = "APPLY" | "CONSIDER" | "REVIEW" | "AVOID";

export interface JobListItem {
  id: string;
  title: string;
  company: string | null;
  location: string | null;
  is_remote: boolean | null;
  employment_type: string | null;
  apply_url: string | null;
  source: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  match_score: number | null;
  trust_score: number | null;
  recommendation: Recommendation | null;
  strengths: string[];
  missing_skills: string[];
  reason: string | null;
  posted_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface JobListResponse {
  items: JobListItem[];
  limit: number;
  offset: number;
  count: number;
}

export interface JobIntelligence {
  match_score: number;
  trust_score: number;
  recommendation: Recommendation;
  strengths: string[];
  missing_skills: string[];
  reason: string | null;
}

export interface JobDetail extends Omit<JobListItem, "created_at" | "updated_at"> {
  description: string | null;
  skills: string[];
  salary_min: number | null;
  salary_max: number | null;
  currency: string | null;
  posted_at: string | null;
  intelligence: JobIntelligence | null;
}

export interface MatchItem {
  job_id: string;
  title: string | null;
  company: string | null;
  location: string | null;
  match_score: number | null;
  trust_score: number | null;
  recommendation: Recommendation | null;
  strengths: string[];
  missing_skills: string[];
  reason: string | null;
  apply_url: string | null;
}

export interface MatchListResponse {
  profile_id: string;
  items: MatchItem[];
  limit: number;
  offset: number;
  count: number;
}

export interface RankedJob {
  rank: number;
  job_id: string;
  title: string | null;
  company: string | null;
  location: string | null;
  match_score: number;
  trust_score: number;
  recommendation: Recommendation;
  ranking_score: number;
  strengths: string[];
  missing_skills: string[];
  reason: string | null;
  reasons: string[];
  apply_url: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  is_remote: boolean | null;
  employment_type: string | null;
}

export interface RankingResponse {
  profile_id: string;
  items: RankedJob[];
  limit: number;
  count: number;
}

export interface ApplicationItem {
  id: string;
  job_id: string;
  title: string | null;
  company: string | null;
  location: string | null;
  is_remote: boolean | null;
  employment_type: string | null;
  status: string;
  applied_at: string | null;
  notes: string | null;
  apply_url: string | null;
  updated_at: string | null;
}

export interface ApplicationListResponse {
  profile_id: string;
  items: ApplicationItem[];
  limit: number;
  offset: number;
  count: number;
}

export interface ApplicationCreatePayload {
  job_id: string;
  status?: string;
  notes?: string | null;
}

export interface ApplicationUpdatePayload {
  status?: string;
  notes?: string | null;
}

export interface HealthResponse {
  status: string;
  service?: string;
  database?: string;
}

export type JobSort = "match" | "trust" | "newest";

export interface JobSearchParams {
  limit?: number;
  offset?: number;
  profileId?: string;
  search?: string;
  role?: string;
  location?: string;
  remote?: boolean;
  minMatch?: number;
  minTrust?: number;
  recommendation?: string;
  employmentType?: string;
  sort?: JobSort;
}

export interface ProfileRole {
  id?: string;
  profile_id?: string;
  role_name: string;
  priority?: number;
}

export interface ProfileLocation {
  id?: string;
  profile_id?: string;
  location_name: string;
  is_remote: boolean;
  priority?: number;
}

export interface ProfileScalar {
  id: string;
  user_id: string | null;
  full_name: string | null;
  education: string | null;
  experience_level: string | null;
  preferred_work_mode: string | null;
  relocation_allowed: boolean;
  minimum_stipend: number | null;
}

export interface ProfileSkill {
  id: string;
  profile_id: string;
  skill_name: string;
  skill_level: string | null;
  is_learning: boolean;
}

export interface ProfileResponse {
  profile: ProfileScalar;
  skills: ProfileSkill[];
  target_roles: ProfileRole[];
  target_locations: ProfileLocation[];
}

export interface SavedJobIdsResponse {
  profile_id: string;
  job_ids: string[];
}

export interface SavedJobResponse {
  profile_id: string;
  job_id: string;
  saved: boolean;
}

export interface ResumeSkillItem {
  name: string;
}

export interface ResumeExperienceItem {
  title: string;
  organization?: string | null;
  duration?: string | null;
}

export interface ResumeExtraction {
  full_name?: string | null;
  email?: string | null;
  phone?: string | null;
  education: string[];
  experience: ResumeExperienceItem[];
  skills: ResumeSkillItem[];
  projects: string[];
  certifications: string[];
  target_roles: string[];
  experience_level?: string | null;
  summary?: string | null;
}

export interface ResumeParseError {
  code: "ai_unavailable" | "invalid_output" | "extraction_failed";
  message: string;
}

export interface ResumeParseMeta {
  file_type: string;
  file_size: number;
  text_chars: number;
  truncated: boolean;
}

export interface ResumeParseResponse {
  extraction: ResumeExtraction | null;
  parse_error: ResumeParseError | null;
  meta: ResumeParseMeta;
}

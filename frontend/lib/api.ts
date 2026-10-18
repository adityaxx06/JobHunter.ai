// Typed FastAPI client (Phase 5.4 endpoints). All requests flow through
// `request()` — no raw fetch() calls scattered across components.
import { API_BASE_URL, DEFAULT_PROFILE_ID } from "@/lib/config";
import type {
  ApplicationCreatePayload,
  ApplicationItem,
  ApplicationListResponse,
  ApplicationUpdatePayload,
  HealthResponse,
  JobDetail,
  JobListResponse,
  JobSearchParams,
  MatchListResponse,
  ProfileLocation,
  ProfileResponse,
  ProfileRole,
  ProfileScalar,
  ProfileSkill,
  RankingResponse,
  ResumeParseResponse,
  SavedJobIdsResponse,
  SavedJobResponse,
} from "@/types/job";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

interface QueryParams {
  [key: string]: string | number | boolean | undefined | null;
}

function buildUrl(path: string, params: QueryParams = {}): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return `${API_BASE_URL}${path}${query ? `?${query}` : ""}`;
}

async function request<T>(
  path: string,
  params: QueryParams = {},
  init: RequestInit = {},
): Promise<T> {
  const { headers: initHeaders, ...rest } = init;
  let response: Response;
  try {
    response = await fetch(buildUrl(path, params), {
      headers: { Accept: "application/json", ...(initHeaders ?? {}) },
      ...rest,
    });
  } catch {
    // Network failure / backend down — generic message, no internals leaked.
    throw new ApiError(0, "Unable to reach the AI-JobHunter API.");
  }
  if (!response.ok) {
    if (response.status === 404) throw new ApiError(404, "Not found.");
    if (response.status === 422) throw new ApiError(422, "Invalid request.");
    if (response.status === 503)
      throw new ApiError(503, "The AI-JobHunter API is temporarily unavailable.");
    throw new ApiError(response.status, "Something went wrong loading data.");
  }
  return (await response.json()) as T;
}

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health", {}, { signal });
}

export function getJobs(params: JobSearchParams = {}): Promise<JobListResponse> {
  const {
    limit = 20,
    offset = 0,
    profileId,
    search,
    role,
    location,
    remote,
    minMatch,
    minTrust,
    recommendation,
    employmentType,
    sort,
  } = params;
  return request<JobListResponse>("/api/jobs", {
    limit,
    offset,
    profile_id: profileId,
    search,
    role,
    location,
    remote,
    min_match: minMatch,
    min_trust: minTrust,
    recommendation,
    employment_type: employmentType,
    sort,
  });
}

export function getProfile(profileId: string = DEFAULT_PROFILE_ID): Promise<ProfileResponse> {
  return request<ProfileResponse>(`/api/profiles/${profileId}`);
}

export interface ProfilePatch {
  full_name?: string | null;
  education?: string | null;
  experience_level?: string | null;
  preferred_work_mode?: string | null;
  relocation_allowed?: boolean;
  minimum_stipend?: number | null;
}

export function patchProfile(
  profileId: string = DEFAULT_PROFILE_ID,
  body: ProfilePatch,
): Promise<ProfileScalar> {
  return request<ProfileScalar>(`/api/profiles/${profileId}`, {}, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export interface SkillCreate {
  skill_name: string;
  skill_level?: string | null;
  is_learning?: boolean;
}

export interface SkillUpdate {
  skill_level?: string | null;
  is_learning?: boolean;
}

export interface SkillResult {
  skill: ProfileSkill;
  duplicate: boolean;
}

export function addSkill(
  profileId: string = DEFAULT_PROFILE_ID,
  body: SkillCreate,
): Promise<SkillResult> {
  return request<SkillResult>(`/api/profiles/${profileId}/skills`, {}, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function patchSkill(
  profileId: string = DEFAULT_PROFILE_ID,
  skillId: string,
  body: SkillUpdate,
): Promise<ProfileSkill> {
  return request<ProfileSkill>(`/api/profiles/${profileId}/skills/${skillId}`, {}, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function deleteSkill(
  profileId: string = DEFAULT_PROFILE_ID,
  skillId: string,
): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/api/profiles/${profileId}/skills/${skillId}`, {}, {
    method: "DELETE",
  });
}

export interface RoleCreate {
  role_name: string;
  priority?: number;
}

export interface RoleUpdate {
  role_name?: string;
  priority?: number;
}

export interface RoleResult {
  role: ProfileRole;
  duplicate: boolean;
}

export function addRole(
  profileId: string = DEFAULT_PROFILE_ID,
  body: RoleCreate,
): Promise<RoleResult> {
  return request<RoleResult>(`/api/profiles/${profileId}/roles`, {}, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function patchRole(
  profileId: string = DEFAULT_PROFILE_ID,
  roleId: string,
  body: RoleUpdate,
): Promise<ProfileRole> {
  return request<ProfileRole>(`/api/profiles/${profileId}/roles/${roleId}`, {}, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function deleteRole(
  profileId: string = DEFAULT_PROFILE_ID,
  roleId: string,
): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/api/profiles/${profileId}/roles/${roleId}`, {}, {
    method: "DELETE",
  });
}

export interface LocationCreate {
  location_name: string;
  is_remote?: boolean;
  priority?: number;
}

export interface LocationUpdate {
  location_name?: string;
  is_remote?: boolean;
  priority?: number;
}

export interface LocationResult {
  location: ProfileLocation;
  duplicate: boolean;
}

export function addLocation(
  profileId: string = DEFAULT_PROFILE_ID,
  body: LocationCreate,
): Promise<LocationResult> {
  return request<LocationResult>(`/api/profiles/${profileId}/locations`, {}, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function patchLocation(
  profileId: string = DEFAULT_PROFILE_ID,
  locationId: string,
  body: LocationUpdate,
): Promise<ProfileLocation> {
  return request<ProfileLocation>(`/api/profiles/${profileId}/locations/${locationId}`, {}, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function deleteLocation(
  profileId: string = DEFAULT_PROFILE_ID,
  locationId: string,
): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/api/profiles/${profileId}/locations/${locationId}`, {}, {
    method: "DELETE",
  });
}

export async function parseResume(
  file: File,
  profileId: string = DEFAULT_PROFILE_ID,
  signal?: AbortSignal,
): Promise<ResumeParseResponse> {
  const form = new FormData();
  form.append("file", file, file.name);
  const response = await fetch(
    `${API_BASE_URL}/api/profiles/${profileId}/resume/parse`,
    { method: "POST", headers: { Accept: "application/json" }, body: form, signal },
  ).catch(() => {
    throw new ApiError(0, "Unable to reach the AI-JobHunter API.");
  });
  if (!response.ok) {
    if (response.status === 404) throw new ApiError(404, "Not found.");
    if (response.status === 422) {
      const detail = await response.json().catch(() => null);
      const message =
        typeof detail?.detail === "string" ? detail.detail : "This resume file cannot be used.";
      throw new ApiError(422, message);
    }
    if (response.status === 413) throw new ApiError(413, "File too large. Resumes must be 5 MB or smaller.");
    if (response.status === 409) throw new ApiError(409, "This name is already used.");
    if (response.status === 503)
      throw new ApiError(503, "The AI-JobHunter API is temporarily unavailable.");
    throw new ApiError(response.status, "Something went wrong loading data.");
  }
  return (await response.json()) as ResumeParseResponse;
}

export function getJob(jobId: string, profileId: string = DEFAULT_PROFILE_ID): Promise<JobDetail> {
  return request<JobDetail>(`/api/jobs/${jobId}`, { profile_id: profileId });
}

export function getMatches(
  profileId: string = DEFAULT_PROFILE_ID,
  options: { limit?: number; offset?: number } = {},
): Promise<MatchListResponse> {
  const { limit = 20, offset = 0 } = options;
  return request<MatchListResponse>(`/api/matches/${profileId}`, { limit, offset });
}

export function getRankings(
  profileId: string = DEFAULT_PROFILE_ID,
  options: { limit?: number; eligibleOnly?: boolean } = {},
): Promise<RankingResponse> {
  const { limit = 20, eligibleOnly = false } = options;
  return request<RankingResponse>(`/api/rankings/${profileId}`, {
    limit,
    ...(eligibleOnly ? { eligible_only: true } : {}),
  });
}

export function getApplications(
  profileId: string = DEFAULT_PROFILE_ID,
  options: { limit?: number; offset?: number; status?: string } = {},
): Promise<ApplicationListResponse> {
  const { limit = 20, offset = 0, status } = options;
  return request<ApplicationListResponse>(`/api/applications/${profileId}`, {
    limit,
    offset,
    status,
  });
}

export function getSavedJobIds(
  profileId: string = DEFAULT_PROFILE_ID,
): Promise<SavedJobIdsResponse> {
  return request<SavedJobIdsResponse>(`/api/saved-jobs/${profileId}`);
}

export function saveJob(
  jobId: string,
  profileId: string = DEFAULT_PROFILE_ID,
): Promise<SavedJobResponse> {
  return request<SavedJobResponse>(
    `/api/saved-jobs/${profileId}/${jobId}`,
    {},
    { method: "POST" },
  );
}

export function unsaveJob(
  jobId: string,
  profileId: string = DEFAULT_PROFILE_ID,
): Promise<SavedJobResponse> {
  return request<SavedJobResponse>(
    `/api/saved-jobs/${profileId}/${jobId}`,
    {},
    { method: "DELETE" },
  );
}

function jsonInit(method: string, payload: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  };
}

export function getApplication(
  jobId: string,
  profileId: string = DEFAULT_PROFILE_ID,
): Promise<ApplicationItem> {
  return request<ApplicationItem>(`/api/applications/${profileId}/${jobId}`);
}

export function createApplication(
  payload: ApplicationCreatePayload,
  profileId: string = DEFAULT_PROFILE_ID,
): Promise<ApplicationItem> {
  return request<ApplicationItem>(
    `/api/applications/${profileId}`,
    {},
    jsonInit("POST", payload),
  );
}

export function updateApplication(
  jobId: string,
  payload: ApplicationUpdatePayload,
  profileId: string = DEFAULT_PROFILE_ID,
): Promise<ApplicationItem> {
  return request<ApplicationItem>(
    `/api/applications/${profileId}/${jobId}`,
    {},
    jsonInit("PATCH", payload),
  );
}

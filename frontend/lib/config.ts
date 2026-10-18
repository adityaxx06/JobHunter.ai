// Frontend-only configuration. Only NEXT_PUBLIC_* values are ever read here,
// which means only the API base URL can reach the browser. Secrets
// (DATABASE_URL, SUPABASE_SERVICE_ROLE_KEY, GEMINI_API_KEY) must never appear
// in this file or any NEXT_PUBLIC_* variable.

export const API_BASE_URL: string =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8001";

// Single MVP profile constant. Deliberately one place only — authentication
// will replace this later. No sensitive personal data is stored here.
export const DEFAULT_PROFILE_ID = "11111111-1111-1111-1111-111111111111";

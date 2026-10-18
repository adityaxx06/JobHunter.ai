# Backend (FastAPI)

Read-only dashboard API over Supabase PostgreSQL (Phase 5.4). No discovery,
no scoring, no AI calls, no auth yet.

## Endpoints

| Method | Path | Purpose |
| ------ | ---- | ------- |
| GET | `/api/health` | Service health (always works) |
| GET | `/api/db/health` | `connected` / `not_configured` (never leaks credentials) |
| GET | `/api/jobs?limit=&offset=&profile_id=` | Paged persisted jobs → `{items, limit, offset, count}` |
| GET | `/api/jobs` + explorer filters | Server-side `search/role/location/remote/min_match/min_trust/recommendation/employment_type` + whitelisted `sort=match\|trust\|newest` (default `newest`, limit ≤ 50). Intelligence params/sorts need `profile_id` (else 422); intelligence columns are null without it. `sort=newest` orders by `last_seen_at DESC` (recency including re-seen jobs); unknown sort values fall back to `newest`. `posted_at` (employer date, often null for ATS boards) is returned when present for display. |
| GET | `/api/jobs/{job_id}?profile_id=` | Full detail: description, skills, salary, `is_remote`, `posted_at`, source + stored `intelligence` block (`null` when unanalyzed); 404 when unknown |
| GET | `/api/matches/{profile_id}?limit=&offset=` | Stored `job_matches` rows with job context |
| GET | `/api/rankings/{profile_id}?limit=&min_match_score=&min_trust_score=&recommendation=&employment_type=&location=&remote=` | Deterministic ranking via the worker Phase 5.3 pipeline — **zero Gemini calls** |
| GET | `/api/applications/{profile_id}?limit=&offset=&status=` | Tracker rows; `status` must be a schema status (`saved`, `applied`, `assessment`, `interview`, `offer`, `rejected`, `withdrawn`) |
| GET | `/api/applications/{profile_id}/{job_id}` | One tracker row with job context; 404 when not tracked |
| POST | `/api/applications/{profile_id}` `{job_id, status?, notes?}` | Track a job (duplicate returns existing row); 404 for unknown job; `applied_at` set once |
| PATCH | `/api/applications/{profile_id}/{job_id}` `{status?, notes?}` | Change status and/or notes only (notes ≤ 5000 chars); 404 when not tracked |
| GET | `/api/saved-jobs/{profile_id}` | Saved job IDs (Save-button initial state) |
| POST | `/api/saved-jobs/{profile_id}/{job_id}` | Save a job (idempotent, 201) |
| DELETE | `/api/saved-jobs/{profile_id}/{job_id}` | Remove a save (404 when never saved) |
| GET | `/api/profiles/{profile_id}` | Profile + skills/roles/locations (Phase 3 shape) |
| GET | `/docs`, `/openapi.json` | Auto-generated OpenAPI (all routes above appear there) |

## Parameters & errors

- Pagination: `limit` 1–100 (default 20), `offset` ≥ 0 (default 0); violations → `422`.
- UUID path params (`job_id`, `profile_id`) → malformed values return `422`
  (legacy `/api/profiles/*` keeps its Phase 3 `400` behavior unchanged).
- Unknown job → `404`; unknown profile on rankings → `404`.
- Database missing/unreachable → `503` with a generic message. Raw PostgreSQL
  errors, stack traces, and credentials never appear in responses.

## Ranking behavior

`GET /api/rankings/*` calls `app/services/ranking_service.py`, which reuses
`worker/pipelines/ranking_pipeline.py` (repository + deterministic scorer) via
a repo-root path bootstrap — no duplicated formula, no second scorer. Ranking
is recomputed per request from stored intelligence; nothing is persisted and
no AI inference runs. Filters map 1:1 onto the worker `RankingFilter`.

## CORS

Development-safe, env-driven (`FRONTEND_URL`, default `http://localhost:3000`,
comma-separated for more origins). Explicit origins only — never `"*"` with
credentials. `GET`-only methods exposed.

## Run & test

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8001
pytest tests/ -v   # offline (mocked DB); live probe is opt-in only
```

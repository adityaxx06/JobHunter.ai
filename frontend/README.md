# Frontend — AI-JobHunter Dashboard (Next.js + TypeScript + Tailwind)

Premium dark-first dashboard (Phase 5.5A foundation + 5.5B job cards).
App Router, client-side data fetching (build never needs the API), no extra
data-fetching or UI-kit dependencies.

## Structure

- `app/` — routes (`/` → `/dashboard`; `dashboard/page.tsx`; `jobs/page.tsx`
  explorer with server-side search, filters, sort, pagination, URL state;
  `jobs/[jobId]/page.tsx` detail with header, scores, reasoning, skills,
  full description, info table, Apply + shared Save + Mark as Applied;
  `applications/page.tsx` tracker with stats, status filters/sort, detail
  modal with status transitions and explicit notes saving)
- `components/jobs/` — `JobExplorer`, `JobFilters` (toolbar + mobile drawer),
  `ActiveFilters`, `JobPagination`, `JobDetailView` (detail sections),
  `JobActions` (shared Apply/Save buttons used by cards + detail)
- `components/applications/` — `ApplicationCard`, `ApplicationModal`
  (status + explicit notes saving), `StatusBadge` (DB status vocabulary)
- `components/saved/` — `SavedJobsContext` (shared save state)
- `components/layout/` — `AppShell` (responsive sidebar + drawer), `Sidebar`,
  `Header` (title, reserved search, API status, avatar)
- `components/dashboard/` — `StatsGrid`, `TopOpportunities`, `JobCard`
  (in `components/JobCard.tsx`), `EmptyJobsState`, `DashboardError` (working retry)
- `components/ui/` — `Score` (Match/Trust/Recommendation), `Skeleton`
  loaders, inline SVG `icons` (no emoji, no icon package)
- `lib/applicationStatus.ts` — single status vocabulary (values = DB CHECK,
  labels display-only), `lib/format.ts` incl. relative dates
- `lib/api.ts` — typed FastAPI client (jobs, detail, matches, rankings,
  applications incl. create/patch, saved-jobs)
- `lib/config.ts` — `API_BASE_URL` (`NEXT_PUBLIC_API_URL` only) + single
  `DEFAULT_PROFILE_ID` (auth will replace this; never put secrets in `NEXT_PUBLIC_*`)
- `types/job.ts` — API response models, no `any`
- `components/JobCard.tsx` — ranking-driven card (score panels with band
  labels, skills/missing, honest salary row, Apply + working Save button)
- `hooks/useDashboard.ts` — parallel fetches with per-endpoint fallbacks
  (`components/saved/SavedJobsContext.tsx` owns shared save state)
- `lib/format.ts` — salary/band formatting (display-only, never recalculated)

## Run

```bash
npm install
npm run dev     # http://localhost:3000 (needs backend for live data)
npm run build   # production check — works with the API offline
```

Copy `.env.example` to `.env.local` to point at the backend
(`NEXT_PUBLIC_API_URL`, default `http://127.0.0.1:8001` matching local dev).

## Later phases (not yet)

Saved-jobs page, Profile/Settings pages. Their sidebar entries are
intentionally disabled placeholders — never broken links. (Save/unsave
itself already works via `/api/saved-jobs`.)

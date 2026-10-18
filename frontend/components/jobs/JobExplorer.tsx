"use client";

// Job Explorer: server-side search, filters, sorting, and pagination over
// GET /api/jobs. The browser only ever holds one page — filtering and
// sorting happen in PostgreSQL. URL holds the full state (shareable,
// refresh-safe, back/forward friendly).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ActiveFilters, type ActiveFilter } from "@/components/jobs/ActiveFilters";
import { JobFilters, type FilterValues } from "@/components/jobs/JobFilters";
import { JobPagination } from "@/components/jobs/JobPagination";
import { JobCard, toJobCardData } from "@/components/JobCard";
import { DashboardError } from "@/components/dashboard/DashboardError";
import { JobCardSkeleton } from "@/components/ui/Skeleton";
import { useSavedJobs } from "@/components/saved/SavedJobsContext";
import { useApplicationStatus } from "@/components/applications/ApplicationStatusContext";
import { getJobs, getProfile } from "@/lib/api";
import { DEFAULT_PROFILE_ID } from "@/lib/config";
import {
  EXPLORER_PAGE_SIZE,
  LOCATION_OPTIONS,
  ROLE_OPTIONS,
  SORT_OPTIONS,
} from "@/lib/filters";
import type { JobListItem, JobSort } from "@/types/job";

const DEFAULTS: FilterValues & { sort: JobSort; page: number } = {
  q: "",
  role: "",
  location: "",
  remote: "all",
  match: "",
  trust: "",
  rec: "",
  employment: "",
  sort: "match",
  page: 1,
};

function readState(params: URLSearchParams): typeof DEFAULTS {
  const sort = params.get("sort");
  const page = Math.max(1, parseInt(params.get("page") ?? "1", 10) || 1);
  return {
    q: params.get("q") ?? "",
    role: params.get("role") ?? "",
    location: params.get("location") ?? "",
    remote: params.get("remote") ?? "all",
    match: params.get("match") ?? "",
    trust: params.get("trust") ?? "",
    rec: params.get("rec") ?? "",
    employment: params.get("employment") ?? "",
    sort: sort === "trust" || sort === "newest" ? sort : "match",
    page,
  };
}

function writeParams(state: typeof DEFAULTS): string {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  if (state.role) params.set("role", state.role);
  if (state.location) params.set("location", state.location);
  if (state.remote !== "all") params.set("remote", state.remote);
  if (state.match) params.set("match", state.match);
  if (state.trust) params.set("trust", state.trust);
  if (state.rec) params.set("rec", state.rec);
  if (state.employment) params.set("employment", state.employment);
  if (state.sort !== "match") params.set("sort", state.sort);
  if (state.page > 1) params.set("page", String(state.page));
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function JobExplorer() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [state, setState] = useState<typeof DEFAULTS>(() => readState(searchParams));
  const [items, setItems] = useState<JobListItem[]>([]);
  const [count, setCount] = useState(0);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [refreshing, setRefreshing] = useState(false);
  const [roleOptions, setRoleOptions] = useState<string[]>(ROLE_OPTIONS);
  const [locationOptions, setLocationOptions] = useState<string[]>(LOCATION_OPTIONS);
  const { savedIds, pendingId, error: saveError, toggleSave } = useSavedJobs();
  const { statusByJobId } = useApplicationStatus();
  const requestId = useRef(0);
  const resultsRef = useRef<HTMLDivElement>(null);

  // Profile-driven filter options (falls back to presentation lists).
  useEffect(() => {
    getProfile(DEFAULT_PROFILE_ID)
      .then((profile) => {
        const roles = profile.target_roles
          .map((entry) => entry.role_name.trim())
          .filter(Boolean);
        const locations = profile.target_locations
          .map((entry) => entry.location_name.trim())
          .filter(Boolean);
        if (roles.length > 0) setRoleOptions(roles);
        if (locations.length > 0) setLocationOptions(locations);
      })
      .catch(() => {
        // Fallbacks already in place — filters stay usable offline-ish.
      });
  }, []);

  // Fetch exactly one page per committed state (no client-side filtering).
  useEffect(() => {
    const current = ++requestId.current;
    const controller = new AbortController();
    setRefreshing(true);
    const { q, role, location, remote, match, trust, rec, employment, sort, page } = state;
    getJobs({
      limit: EXPLORER_PAGE_SIZE,
      offset: (page - 1) * EXPLORER_PAGE_SIZE,
      profileId: DEFAULT_PROFILE_ID,
      search: q || undefined,
      role: role || undefined,
      location: location === "Remote" ? undefined : location || undefined,
      remote: location === "Remote" ? true : remote === "all" ? undefined : remote === "remote",
      minMatch: match ? Number(match) : undefined,
      minTrust: trust ? Number(trust) : undefined,
      recommendation: rec || undefined,
      employmentType: employment || undefined,
      sort,
    })
      .then((response) => {
        if (current !== requestId.current || controller.signal.aborted) return;
        setItems(response.items);
        setCount(response.count);
        setStatus("ready");
        setRefreshing(false);
      })
      .catch(() => {
        if (current !== requestId.current || controller.signal.aborted) return;
        setStatus("error");
        setRefreshing(false);
      });
    return () => controller.abort();
  }, [state]);

  const commit = useCallback(
    (patch: Partial<typeof DEFAULTS>, resetPage: boolean) => {
      setState((previous) => {
        const next = {
          ...previous,
          ...patch,
          page: resetPage ? 1 : (patch.page ?? previous.page),
        };
        router.replace(`${pathname}${writeParams(next)}`, { scroll: false });
        return next;
      });
    },
    [pathname, router],
  );

  // URL holds the full state; the state initializes from the URL, so no
  // initial push is needed (deep links stay intact).

  const goPage = useCallback(
    (page: number) => {
      commit({ page }, false);
      resultsRef.current?.scrollIntoView({ block: "start" });
    },
    [commit],
  );

  const activeFilters: ActiveFilter[] = useMemo(() => {
    const list: ActiveFilter[] = [];
    const remove = (patch: Partial<typeof DEFAULTS>) => () => commit(patch, true);
    if (state.q) list.push({ key: "q", label: `“${state.q}”`, onRemove: remove({ q: "" }) });
    if (state.role) list.push({ key: "role", label: state.role, onRemove: remove({ role: "" }) });
    if (state.location)
      list.push({ key: "location", label: state.location, onRemove: remove({ location: "" }) });
    if (state.remote !== "all")
      list.push({
        key: "remote",
        label: state.remote === "remote" ? "Remote" : "Not remote",
        onRemove: remove({ remote: "all" }),
      });
    if (state.match) list.push({ key: "match", label: `Match ${state.match}+`, onRemove: remove({ match: "" }) });
    if (state.trust) list.push({ key: "trust", label: `Trust ${state.trust}+`, onRemove: remove({ trust: "" }) });
    if (state.rec) list.push({ key: "rec", label: state.rec, onRemove: remove({ rec: "" }) });
    if (state.employment)
      list.push({ key: "employment", label: state.employment, onRemove: remove({ employment: "" }) });
    if (state.sort !== "match")
      list.push({
        key: "sort",
        label: state.sort === "trust" ? "Highest Trust" : "Newest",
        onRemove: remove({ sort: "match" }),
      });
    return list;
  }, [state, commit]);

  const clearAll = useCallback(() => {
    commit(
      { q: "", role: "", location: "", remote: "all", match: "", trust: "", rec: "", employment: "", sort: "match" },
      true,
    );
  }, [commit]);

  const totalPages = Math.max(1, Math.ceil(count / EXPLORER_PAGE_SIZE));
  const hasActiveFilters = activeFilters.length > 0;

  return (
    <div>
      <div className="animate-rise">
        <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">Jobs</h2>
        <p className="mt-1 text-sm text-fog sm:text-[15px]">
          Explore and find your best opportunities
        </p>
      </div>

      <JobFilters
        values={state}
        onChange={(patch) => commit(patch, true)}
        roleOptions={roleOptions}
        locationOptions={locationOptions}
        activeCount={activeFilters.length}
      />

      {hasActiveFilters ? (
        <div className="mt-3">
          <ActiveFilters filters={activeFilters} onClearAll={clearAll} />
        </div>
      ) : null}

      <div ref={resultsRef} className="mt-5 scroll-mt-20">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-fog" aria-live="polite">
            {status === "loading" && items.length === 0 ? (
              "Loading opportunities…"
            ) : (
              <>
                <span className="font-semibold tabular-nums text-zinc-100">{count}</span>{" "}
                {count === 1 ? "opportunity" : "opportunities"}
                {refreshing ? <span className="text-fog-dim"> · updating…</span> : null}
              </>
            )}
          </p>
          <label className="inline-flex items-center gap-2 text-sm text-fog">
            Sort
            <select
              value={state.sort}
              onChange={(event) =>
                commit({ sort: event.target.value as "match" | "trust" | "newest" }, true)
              }
              aria-label="Sort jobs"
              className="rounded-lg border border-line bg-ink-900 px-2.5 py-1.5 text-sm text-zinc-200 focus:outline-none"
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {status === "loading" && items.length === 0 ? (
          <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2" aria-label="Loading jobs">
            {[0, 1, 2, 3].map((key) => (
              <div key={key} className="rounded-xl2 border border-line bg-ink-900 p-5">
                <div className="skeleton animate-shimmer h-5 w-2/3 rounded-md" aria-hidden="true" />
                <div className="skeleton animate-shimmer mt-2 h-4 w-1/2 rounded-md" aria-hidden="true" />
                <div className="skeleton animate-shimmer mt-4 h-16 w-full rounded-md" aria-hidden="true" />
              </div>
            ))}
          </div>
        ) : status === "error" ? (
          <div className="mt-4" role="alert">
            <div className="flex flex-col items-center rounded-xl2 border border-line bg-ink-900 px-6 py-12 text-center">
              <h3 className="text-base font-semibold tracking-tight">Unable to load jobs</h3>
              <p className="mt-1.5 max-w-sm text-sm text-fog">
                The AI-JobHunter API isn&apos;t responding right now.
              </p>
              <button
                type="button"
                onClick={() => commit({}, false)}
                className="mt-4 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
              >
                Try Again
              </button>
            </div>
          </div>
        ) : items.length === 0 && hasActiveFilters ? (
          <div className="mt-4 flex flex-col items-center rounded-xl2 border border-dashed border-line bg-ink-900/60 px-6 py-14 text-center">
            <h3 className="text-base font-semibold tracking-tight">No opportunities found</h3>
            <p className="mt-1.5 max-w-sm text-sm text-fog">
              Try adjusting your search or filters.
            </p>
            <button
              type="button"
              onClick={clearAll}
              className="mt-5 rounded-lg border border-line bg-ink-850 px-4 py-2 text-sm font-medium text-zinc-200 transition-colors hover:bg-ink-800"
            >
              Clear filters
            </button>
          </div>
        ) : items.length === 0 ? (
          <div className="mt-4 flex flex-col items-center rounded-xl2 border border-dashed border-line bg-ink-900/60 px-6 py-14 text-center">
            <h3 className="text-base font-semibold tracking-tight">No opportunities yet</h3>
            <p className="mt-1.5 max-w-sm text-sm text-fog">
              AI-JobHunter hasn&apos;t discovered any opportunities yet. Once the
              discovery pipeline runs, your jobs will appear here.
            </p>
          </div>
        ) : (
          <>
            <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
              {items.map((item) => (
                <JobCard
                  key={item.id}
                  job={toJobCardData(item)}
                  saved={savedIds.has(item.id)}
                  savePending={pendingId === item.id}
                  saveError={pendingId === item.id ? saveError : null}
                  onToggleSave={() => toggleSave(item.id)}
                  applicationStatus={statusByJobId.get(item.id) ?? null}
                />
              ))}
            </div>
            <div className="mt-6">
              <JobPagination page={state.page} totalPages={totalPages} onPage={goPage} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

"use client";

// /applications — personal tracker workspace. One list fetch (limit 100);
// filtering and sorting are client-side over the loaded records, which keeps
// this page to a single request for MVP data volumes. Status changes and
// notes go through PATCH; failures restore the previous record.
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApplicationCard } from "@/components/applications/ApplicationCard";
import { ApplicationModal } from "@/components/applications/ApplicationModal";
import { DashboardError } from "@/components/dashboard/DashboardError";
import { StatsGrid } from "@/components/dashboard/StatsGrid";
import { AppShell } from "@/components/layout/AppShell";
import { JobCardSkeleton, StatCardSkeleton } from "@/components/ui/Skeleton";
import { getApplications, updateApplication } from "@/lib/api";
import { APPLICATION_STATUSES, statusLabel } from "@/lib/applicationStatus";
import { DEFAULT_PROFILE_ID } from "@/lib/config";
import { cn } from "@/lib/utils";
import type { ApplicationItem } from "@/types/job";

type SortKey = "updated" | "applied" | "oldest";
type PageStatus = "loading" | "ready" | "error";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "updated", label: "Recently updated" },
  { value: "applied", label: "Recently applied" },
  { value: "oldest", label: "Oldest first" },
];

function timeValue(iso: string | null): number {
  if (!iso) return Number.NEGATIVE_INFINITY;
  const time = new Date(iso).getTime();
  return Number.isNaN(time) ? Number.NEGATIVE_INFINITY : time;
}

function sortItems(items: ApplicationItem[], sort: SortKey): ApplicationItem[] {
  const ranked = [...items];
  if (sort === "applied") {
    ranked.sort((a, b) => timeValue(b.applied_at) - timeValue(a.applied_at));
  } else if (sort === "oldest") {
    ranked.sort((a, b) => timeValue(a.applied_at) - timeValue(b.applied_at));
  } else {
    ranked.sort((a, b) => timeValue(b.updated_at) - timeValue(a.updated_at));
  }
  return ranked;
}

export default function ApplicationsPage() {
  const [status, setStatus] = useState<PageStatus>("loading");
  const [items, setItems] = useState<ApplicationItem[]>([]);
  const [filter, setFilter] = useState<string>("all");
  const [sort, setSort] = useState<SortKey>("updated");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);
  const requestId = useRef(0);

  const load = useCallback(() => {
    const current = ++requestId.current;
    setStatus("loading");
    getApplications(DEFAULT_PROFILE_ID, { limit: 100, offset: 0 })
      .then((response) => {
        if (current !== requestId.current) return;
        setItems(response.items);
        setStatus("ready");
      })
      .catch(() => {
        if (current !== requestId.current) return;
        setStatus("error");
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const counts = useMemo(() => {
    const tally: Record<string, number> = { total: items.length };
    for (const item of items) {
      tally[item.status] = (tally[item.status] ?? 0) + 1;
    }
    return tally;
  }, [items]);

  const visible = useMemo(() => {
    const filtered =
      filter === "all" ? items : items.filter((item) => item.status === filter);
    return sortItems(filtered, sort);
  }, [items, filter, sort]);

  const selected = selectedId
    ? (items.find((item) => item.id === selectedId) ?? null)
    : null;

  const handleSave = useCallback(
    (input: { status: string; notes: string | null }) => {
      if (!selected || saving) return;
      setSaving(true);
      setJustSaved(false);
      setModalError(null);
      updateApplication(selected.job_id, input, DEFAULT_PROFILE_ID)
        .then((updated) => {
          setItems((previous) =>
            previous.map((item) => (item.id === updated.id ? updated : item)),
          );
          setJustSaved(true);
        })
        .catch(() => {
          setModalError("Couldn't save your changes. Try again.");
        })
        .finally(() => {
          setSaving(false);
        });
    },
    [selected, saving],
  );

  return (
    <AppShell title="Applications">
      <div className="animate-rise">
        <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">
          Applications
        </h2>
        <p className="mt-1 text-sm text-fog sm:text-[15px]">
          Track your job search progress.
        </p>
      </div>

      {status === "loading" ? (
        <>
          <div className="mt-6 grid grid-cols-1 gap-3 min-[480px]:grid-cols-2 lg:grid-cols-4">
            {[0, 1, 2, 3].map((key) => (
              <StatCardSkeleton key={key} />
            ))}
          </div>
          <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
            {[0, 1].map((key) => (
              <JobCardSkeleton key={key} />
            ))}
          </div>
        </>
      ) : status === "error" ? (
        <div className="mt-6">
          <DashboardError onRetry={load} />
        </div>
      ) : (
        <>
          <div className="mt-6">
            <StatsGrid
              stats={[
                { label: "Total", value: String(counts.total ?? 0), hint: "Tracked applications" },
                { label: "Applied", value: String(counts.applied ?? 0), hint: "Submitted" },
                { label: "Interviews", value: String(counts.interview ?? 0), hint: "In interview" },
                { label: "Offers", value: String(counts.offer ?? 0), hint: "Received" },
                { label: "Rejected", value: String(counts.rejected ?? 0), hint: "Not moving forward" },
              ]}
            />
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter by status">
            {["all", ...APPLICATION_STATUSES].map((value) => {
              const active = filter === value;
              const count = value === "all" ? counts.total ?? 0 : (counts[value] ?? 0);
              return (
                <button
                  key={value}
                  type="button"
                  onClick={() => setFilter(value)}
                  aria-pressed={active}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                    active
                      ? "border-accent/50 bg-accent-dim text-zinc-50"
                      : "border-line bg-ink-900 text-fog hover:bg-ink-800 hover:text-zinc-100",
                  )}
                >
                  {value === "all" ? "All" : statusLabel(value)}
                  <span className="ml-1.5 tabular-nums text-fog-dim">{count}</span>
                </button>
              );
            })}
          </div>

          {visible.length === 0 && filter === "all" ? (
            <div className="mt-4 flex flex-col items-center rounded-xl2 border border-dashed border-line bg-ink-900/60 px-6 py-14 text-center">
              <h3 className="text-base font-semibold tracking-tight">No applications yet</h3>
              <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-fog">
                When you apply to a job, track it here so you never lose sight
                of your job search.
              </p>
              <Link
                href="/jobs"
                className="mt-5 inline-flex items-center rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
              >
                Explore Jobs
              </Link>
            </div>
          ) : visible.length === 0 ? (
            <div className="mt-4 flex flex-col items-center rounded-xl2 border border-dashed border-line bg-ink-900/60 px-6 py-14 text-center">
              <h3 className="text-base font-semibold tracking-tight">Nothing with this status</h3>
              <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-fog">
                No applications are currently marked as “{statusLabel(filter)}”.
              </p>
              <button
                type="button"
                onClick={() => setFilter("all")}
                className="mt-5 rounded-lg border border-line bg-ink-850 px-4 py-2 text-sm font-medium text-zinc-200 transition-colors hover:bg-ink-800"
              >
                Show all
              </button>
            </div>
          ) : (
            <>
              <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm text-fog" aria-live="polite">
                  <span className="font-semibold tabular-nums text-zinc-100">{visible.length}</span>{" "}
                  {visible.length === 1 ? "application" : "applications"}
                </p>
                <label className="inline-flex items-center gap-2 text-sm text-fog">
                  Sort
                  <select
                    value={sort}
                    onChange={(event) => setSort(event.target.value as SortKey)}
                    aria-label="Sort applications"
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
              <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
                {visible.map((item) => (
                  <ApplicationCard
                    key={item.id}
                    application={item}
                    onOpen={() => {
                      setModalError(null);
                      setSelectedId(item.id);
                    }}
                  />
                ))}
              </div>
            </>
          )}
        </>
      )}

      {selected ? (
        <ApplicationModal
          key={selected.id}
          application={selected}
          saving={saving}
          saveState={justSaved && !saving ? "saved" : "idle"}
          error={modalError}
          onClose={() => {
            if (!saving) {
              setSelectedId(null);
              setModalError(null);
              setJustSaved(false);
            }
          }}
          onSave={handleSave}
        />
      ) : null}
    </AppShell>
  );
}

import Link from "next/link";
import type { RankedJob } from "@/types/job";

// Needs Attention: strong recommendations the user hasn't acted on yet.
// Derived entirely from data the dashboard already loads (ranked jobs +
// saved IDs + tracker statuses) — no new endpoint, no extra fetch, nothing
// invented. Renders nothing when there is nothing to surface.
const TRACKED_THROUGH = new Set([
  "applied",
  "assessment",
  "interview",
  "offer",
  "rejected",
  "withdrawn",
]);

export function selectNeedsAttention(
  jobs: RankedJob[],
  savedIds: Set<string>,
  statusByJobId: Map<string, string>,
  limit = 3,
): RankedJob[] {
  return jobs
    .filter(
      (job) =>
        job.recommendation === "APPLY" &&
        !savedIds.has(job.job_id) &&
        !TRACKED_THROUGH.has(statusByJobId.get(job.job_id) ?? ""),
    )
    .slice(0, Math.max(0, limit));
}

export function NeedsAttention({
  jobs,
  savedIds,
  statusByJobId,
}: {
  jobs: RankedJob[];
  savedIds: Set<string>;
  statusByJobId: Map<string, string>;
}) {
  const items = selectNeedsAttention(jobs, savedIds, statusByJobId, 3);
  if (items.length === 0) return null;
  return (
    <section aria-labelledby="needs-attention" className="mt-8">
      <h2 id="needs-attention" className="text-lg font-semibold tracking-tight">
        Needs Attention
      </h2>
      <p className="mt-0.5 text-sm text-fog">Strong matches you haven&apos;t saved or tracked yet</p>
      <ul className="mt-4 space-y-2">
        {items.map((job) => (
          <li
            key={job.job_id}
            className="flex items-center justify-between gap-3 rounded-xl2 border border-line bg-ink-900 px-4 py-3"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-zinc-100">{job.title ?? "Untitled role"}</p>
              <p className="truncate text-xs text-fog">
                {[job.company, job.location].filter(Boolean).join(" · ") || "—"}
              </p>
            </div>
            <Link
              href={`/jobs/${job.job_id}`}
              className="shrink-0 rounded-lg border border-line bg-ink-850 px-3 py-1.5 text-xs font-medium text-zinc-200 transition-colors hover:bg-ink-800"
            >
              Review
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

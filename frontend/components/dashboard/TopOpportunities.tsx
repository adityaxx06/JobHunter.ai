import { JobCard, toJobCardData } from "@/components/JobCard";
import { ArrowRightIcon, RefreshIcon, SparkIcon } from "@/components/ui/icons";
import type { RankedJob } from "@/types/job";

export function EmptyJobsState() {
  return (
    <div className="flex flex-col items-center rounded-xl2 border border-dashed border-line bg-ink-900/60 px-6 py-14 text-center">
      <span
        aria-hidden="true"
        className="flex h-12 w-12 items-center justify-center rounded-full bg-accent-dim text-accent-soft"
      >
        <SparkIcon size={22} />
      </span>
      <h3 className="mt-4 text-base font-semibold tracking-tight">No opportunities yet</h3>
      <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-fog">
        AI-JobHunter hasn&apos;t found any ranked opportunities for your profile
        yet. Once job discovery and intelligence processing run, your best
        matches will appear here.
      </p>
      <button
        type="button"
        disabled
        title="Discovery runs from the worker, not the dashboard, in this phase"
        className="mt-5 cursor-not-allowed rounded-lg border border-line bg-ink-850 px-4 py-2 text-sm font-medium text-fog-dim"
      >
        Discovery coming soon
      </button>
    </div>
  );
}

function SectionError({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center rounded-xl2 border border-line bg-ink-900 px-6 py-10 text-center"
    >
      <h3 className="text-base font-semibold tracking-tight">Unable to load job intelligence</h3>
      <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-fog">
        The AI-JobHunter API isn&apos;t responding right now. Your other
        dashboard sections above are unaffected.
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-4 inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
      >
        <RefreshIcon size={15} />
        Try Again
      </button>
    </div>
  );
}

export interface TopOpportunitiesProps {
  jobs: RankedJob[];
  savedIds: Set<string>;
  savePendingId: string | null;
  saveError: string | null;
  onToggleSave: (jobId: string) => void;
  rankingsFailed: boolean;
  onRetryRankings: () => void;
  applicationStatusByJob?: Map<string, string>;
}

export function TopOpportunities({
  jobs,
  savedIds,
  savePendingId,
  saveError,
  onToggleSave,
  rankingsFailed,
  onRetryRankings,
  applicationStatusByJob,
}: TopOpportunitiesProps) {
  return (
    <section aria-labelledby="top-opportunities">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h2 id="top-opportunities" className="text-lg font-semibold tracking-tight">
            Top Opportunities
          </h2>
          <p className="mt-0.5 text-sm text-fog">Your strongest current job matches</p>
        </div>
        <button
          type="button"
          disabled
          title="The full Jobs explorer arrives in a later phase"
          className="inline-flex shrink-0 cursor-not-allowed items-center gap-1 rounded-lg px-2 py-1 text-sm font-medium text-fog-dim"
        >
          View all
          <ArrowRightIcon size={15} />
        </button>
      </div>
      {rankingsFailed ? (
        <div className="mt-4">
          <SectionError onRetry={onRetryRankings} />
        </div>
      ) : jobs.length === 0 ? (
        <div className="mt-4">
          <EmptyJobsState />
        </div>
      ) : (
        <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
          {jobs.map((job) => (
            <JobCard
              key={job.job_id}
              job={toJobCardData(job)}
              saved={savedIds.has(job.job_id)}
              savePending={savePendingId === job.job_id}
              saveError={savePendingId === job.job_id ? saveError : null}
              onToggleSave={() => onToggleSave(job.job_id)}
              applicationStatus={applicationStatusByJob?.get(job.job_id) ?? null}
            />
          ))}
        </div>
      )}
    </section>
  );
}

// Reusable job card (single canonical implementation).
// Takes a JobCardData view model so dashboard (RankedJob) and explorer
// (JobListItem) render identically. Displays backend values only — scores are
// labeled, never recalculated. Null scores render an honest unavailable state.
import { RecommendationBadge, TrustScore } from "@/components/ui/Score";
import { ApplyButton, SaveButton } from "@/components/jobs/JobActions";
import { PinIcon } from "@/components/ui/icons";
import { statusLabel } from "@/lib/applicationStatus";
import { formatRelativeDate, formatSalary, formatWorkMode, matchBand } from "@/lib/format";
import type { JobListItem, RankedJob } from "@/types/job";
import Link from "next/link";

export interface JobCardData {
  job_id: string;
  title: string | null;
  company: string | null;
  location: string | null;
  is_remote: boolean | null;
  employment_type: string | null;
  match_score: number | null;
  trust_score: number | null;
  recommendation: string | null;
  strengths: string[];
  missing_skills: string[];
  reason: string | null;
  reasons: string[];
  postedAt: string | null;
  apply_url: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
}

/** Adapt either API shape into the card view model (no data invented). */
export function toJobCardData(item: RankedJob | JobListItem): JobCardData {
  return {
    job_id: "job_id" in item ? item.job_id : item.id,
    title: item.title,
    company: item.company,
    location: item.location,
    is_remote: item.is_remote,
    employment_type: item.employment_type,
    match_score: item.match_score,
    trust_score: item.trust_score,
    recommendation: item.recommendation,
    strengths: item.strengths ?? [],
    missing_skills: item.missing_skills ?? [],
    reason: item.reason,
    reasons: "reasons" in item && Array.isArray(item.reasons) ? item.reasons : [],
    postedAt: "posted_at" in item ? (item.posted_at ?? null) : null,
    apply_url: item.apply_url,
    salary_min: "salary_min" in item ? item.salary_min : null,
    salary_max: "salary_max" in item ? item.salary_max : null,
    salary_currency: "salary_currency" in item ? item.salary_currency : null,
  };
}

export interface JobCardProps {
  job: JobCardData;
  saved: boolean;
  savePending: boolean;
  saveError: string | null;
  onToggleSave: () => void;
  applicationStatus?: string | null;
}

export function JobCard({ job, saved, savePending, saveError, onToggleSave, applicationStatus }: JobCardProps) {
  const skills = (job.strengths ?? []).slice(0, 6);
  const missing = (job.missing_skills ?? []).slice(0, 3);
  const workMode = formatWorkMode(job.location, job.is_remote);
  const employment = (job.employment_type ?? "").trim() || null;
  const meta = [employment, workMode].filter(Boolean).join(" · ");
  const salary = formatSalary(job.salary_min, job.salary_max, job.salary_currency);
  const band = job.match_score === null ? null : matchBand(job.match_score);
  const postedLabel = formatRelativeDate(job.postedAt, "Posted");
  const reasons = (job.reasons ?? []).map((reason) => reason.trim()).filter(Boolean).slice(0, 6);

  return (
    <article className="animate-rise rounded-xl2 border border-line bg-ink-900 p-5 shadow-card transition-[border-color,box-shadow,transform] duration-200 hover:-translate-y-px hover:border-accent/40 hover:shadow-pop">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="text-[15px] font-semibold tracking-tight">
            <Link
              href={`/jobs/${job.job_id}`}
              className="rounded transition-colors hover:text-accent-soft"
            >
              {job.title ?? "Untitled role"}
            </Link>
          </h3>
          {job.company ? (
            <p className="mt-0.5 truncate text-sm text-fog">{job.company}</p>
          ) : null}
        </div>
        {job.recommendation ? (
          <RecommendationBadge value={job.recommendation} />
        ) : (
          <span className="inline-flex items-center rounded-full border border-line px-2.5 py-0.5 text-xs font-medium uppercase tracking-wide text-fog-dim">
            Not analyzed
          </span>
        )}
      </div>
      {applicationStatus ? (
        <p className="mt-1.5 text-xs font-medium uppercase tracking-wide text-accent-soft">
          {statusLabel(applicationStatus)}
        </p>
      ) : null}

      {meta ? (
        <p className="mt-2 flex min-w-0 items-center gap-1.5 text-sm text-fog">
          <PinIcon size={15} className="shrink-0 text-fog-dim" />
          <span className="truncate">{meta}</span>
        </p>
      ) : null}
      {postedLabel ? (
        <p className="mt-1 text-xs text-fog-dim">{postedLabel}</p>
      ) : null}

      <div className="mt-3 grid grid-cols-2 gap-2" aria-label="AI evaluation scores">
        <div className="rounded-lg border border-line-soft bg-ink-850 px-3 py-2.5">
          <p className="text-2xl font-semibold tabular-nums tracking-tight text-positive">
            {job.match_score === null ? (
              "—"
            ) : (
              <>
                {job.match_score}
                <span className="text-sm font-medium">%</span>
              </>
            )}
          </p>
          <p className="mt-0.5 text-[11px] font-medium uppercase tracking-wide text-fog">
            {band === null ? "Match · not scored" : `Match · ${band}`}
          </p>
        </div>
        <div className="rounded-lg border border-line-soft bg-ink-850 px-3 py-2.5">
          {job.trust_score === null ? (
            <p className="text-2xl font-semibold tabular-nums tracking-tight text-fog">
              —
            </p>
          ) : (
            <div className="text-xl font-semibold tabular-nums tracking-tight">
              <TrustScore value={job.trust_score} />
            </div>
          )}
          <p className="mt-1 text-[11px] font-medium uppercase tracking-wide text-fog">
            Independent of match
          </p>
        </div>
      </div>

      {job.reason ? (
        <p className="mt-2.5 line-clamp-3 text-sm leading-relaxed text-fog">{job.reason}</p>
      ) : null}

      {skills.length > 0 ? (
        <div className="mt-3">
          <p className="text-[11px] font-medium uppercase tracking-wide text-fog-dim">
            Skills
          </p>
          <ul aria-label="Matching skills" className="mt-1.5 flex flex-wrap gap-1.5">
            {skills.map((skill) => (
              <li
                key={skill}
                className="rounded-md border border-line-soft bg-ink-850 px-2 py-0.5 text-xs text-zinc-300"
              >
                {skill}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {missing.length > 0 ? (
        <div className="mt-3">
          <p className="text-[11px] font-medium uppercase tracking-wide text-fog-dim">
            Missing skills
          </p>
          <p className="mt-1 text-xs text-zinc-300">{missing.join(", ")}</p>
        </div>
      ) : null}

      {reasons.length > 0 ? (
        <details className="mt-3 rounded-lg border border-line-soft bg-ink-850 px-3 py-2">
          <summary className="cursor-pointer text-xs font-medium uppercase tracking-wide text-fog">
            Why this job?
          </summary>
          <ul className="mt-1.5 space-y-1">
            {reasons.map((reason) => (
              <li key={reason} className="text-xs leading-relaxed text-zinc-300">
                · {reason}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {salary ? (
        <p className="mt-3 text-sm font-medium tabular-nums text-zinc-200" aria-label={`Salary ${salary}`}>
          {salary}
        </p>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <ApplyButton applyUrl={job.apply_url} title={job.title} className="flex-1 sm:flex-none" />
        <SaveButton
          saved={saved}
          pending={savePending}
          onToggle={onToggleSave}
          title={job.title}
        />
      </div>
      {saveError ? (
        <p role="alert" className="mt-2 text-xs text-danger">
          {saveError}
        </p>
      ) : null}
    </article>
  );
}

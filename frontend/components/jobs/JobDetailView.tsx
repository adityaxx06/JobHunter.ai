"use client";

// Presentational job-detail sections. Receives a real JobDetail plus save
// wiring from the page — displays backend values only, never invents data.
// Every optional section hides itself when its data is absent.
"use client";

import Link from "next/link";
import { useState } from "react";
import { ApplyButton, SaveButton } from "@/components/jobs/JobActions";
import { StatusBadge } from "@/components/applications/StatusBadge";
import { MatchScore, RecommendationBadge, TrustScore } from "@/components/ui/Score";
import { PinIcon } from "@/components/ui/icons";
import {
  formatPostedDate,
  formatRelativeDate,
  formatSalary,
  formatSource,
  formatWorkMode,
  matchBand,
  trustBand,
} from "@/lib/format";
import { statusLabel } from "@/lib/applicationStatus";
import type { ApplicationItem, JobDetail } from "@/types/job";

function Section({
  title,
  children,
  labelledBy,
}: {
  title: string;
  children: React.ReactNode;
  labelledBy: string;
}) {
  return (
    <section aria-labelledby={labelledBy} className="rounded-xl2 border border-line bg-ink-900 p-5 shadow-card sm:p-6">
      <h2 id={labelledBy} className="text-base font-semibold tracking-tight">
        {title}
      </h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5 py-2.5 sm:flex-row sm:items-baseline sm:gap-4">
      <dt className="w-36 shrink-0 text-xs font-medium uppercase tracking-wide text-fog-dim">
        {label}
      </dt>
      <dd className="min-w-0 text-sm text-zinc-200">{value}</dd>
    </div>
  );
}

export function JobDetailView({
  job,
  saved,
  savePending,
  saveError,
  onToggleSave,
  application,
  appPending,
  appError,
  onMarkApplied,
}: {
  job: JobDetail;
  saved: boolean;
  savePending: boolean;
  saveError: string | null;
  onToggleSave: () => void;
  application: ApplicationItem | null;
  appPending: boolean;
  appError: string | null;
  onMarkApplied: () => void;
}) {
  const intelligence = job.intelligence;
  const workMode = formatWorkMode(job.location, job.is_remote);
  const employment = (job.employment_type ?? "").trim() || null;
  const meta = [employment, workMode].filter(Boolean).join(" · ");
  const salary = formatSalary(job.salary_min, job.salary_max, job.currency);
  const source = formatSource(job.source);
  const posted = formatPostedDate(job.posted_at);
  const skills = (job.skills ?? []).filter((skill) => skill.trim().length > 0);
  const strengths = (intelligence?.strengths ?? []).slice(0, 12);
  const missing = (intelligence?.missing_skills ?? []).slice(0, 8);
  const [confirming, setConfirming] = useState(false);
  const appliedLabel = application
    ? (formatRelativeDate(application.applied_at, "Applied") ?? "Tracked")
    : null;

  return (
    <div className="animate-rise space-y-4">
      {/* Header card */}
      <section
        aria-labelledby="job-title"
        className="rounded-xl2 border border-line bg-ink-900 p-5 shadow-card sm:p-6"
      >
        {job.company ? (
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-accent-soft">
            {job.company}
          </p>
        ) : null}
        <h1 id="job-title" className="mt-1.5 text-xl font-semibold tracking-tight sm:text-2xl">
          {job.title ?? "Untitled role"}
        </h1>
        {meta ? (
          <p className="mt-2 flex min-w-0 items-center gap-1.5 text-sm text-fog">
            <PinIcon size={15} className="shrink-0 text-fog-dim" />
            <span className="truncate">{meta}</span>
          </p>
        ) : null}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          {intelligence ? (
            <>
              <MatchScore value={intelligence.match_score} />
              <TrustScore value={intelligence.trust_score} />
              <RecommendationBadge value={intelligence.recommendation} />
            </>
          ) : (
            <span className="inline-flex items-center rounded-full border border-line px-2.5 py-0.5 text-xs font-medium uppercase tracking-wide text-fog-dim">
              Not analyzed
            </span>
          )}
        </div>

        {intelligence ? (
          <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2" aria-label="AI evaluation scores">
            <div className="rounded-lg border border-line-soft bg-ink-850 px-4 py-4">
              <p className="text-xs font-medium uppercase tracking-wide text-fog">Match Score</p>
              <p className="mt-1 text-4xl font-semibold tabular-nums tracking-tight text-positive">
                {intelligence.match_score}
              </p>
              <p className="mt-1 text-sm text-fog">{matchBand(intelligence.match_score)}</p>
            </div>
            <div className="rounded-lg border border-line-soft bg-ink-850 px-4 py-4">
              <p className="text-xs font-medium uppercase tracking-wide text-fog">Trust Score</p>
              <p className="mt-1 text-4xl font-semibold tabular-nums tracking-tight">
                {intelligence.trust_score}
              </p>
              <p className="mt-1 text-sm text-fog">{trustBand(intelligence.trust_score)}</p>
            </div>
          </div>
        ) : (
          <p className="mt-4 rounded-lg border border-line-soft bg-ink-850 px-4 py-3 text-sm text-fog">
            Match details are not available for this job yet.
          </p>
        )}

        <div className="mt-5 flex flex-col gap-2 sm:flex-row">
          <ApplyButton applyUrl={job.apply_url} title={job.title} className="flex-1 sm:flex-none sm:px-8" />
          <SaveButton
            saved={saved}
            pending={savePending}
            onToggle={onToggleSave}
            title={job.title}
            className="flex-1 sm:flex-none"
          />
        </div>
        {saveError ? (
          <p role="alert" className="mt-2 text-xs text-danger">
            {saveError}
          </p>
        ) : null}

        {/* Application tracking — explicit opt-in only, never automatic. */}
        {application ? (
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-positive/25 bg-positive/10 px-4 py-3">
            <StatusBadge status={application.status} />
            <span className="text-sm text-zinc-200">
              {statusLabel(application.status)} · {appliedLabel}
            </span>
            <Link
              href="/applications"
              className="ml-auto text-sm font-medium text-accent-soft transition-opacity hover:opacity-80"
            >
              View Applications →
            </Link>
          </div>
        ) : confirming ? (
          <div
            className="mt-3 rounded-lg border border-line bg-ink-850 px-4 py-3"
            role="group"
            aria-label="Confirm tracking this application"
          >
            <p className="text-sm font-medium">Mark as Applied?</p>
            <p className="mt-0.5 text-xs text-fog">
              This will add this job to your application tracker. Applied date: Today
            </p>
            {appError ? (
              <p role="alert" className="mt-1.5 text-xs text-danger">
                {appError}
              </p>
            ) : null}
            <div className="mt-2.5 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setConfirming(false)}
                disabled={appPending}
                className="rounded-lg border border-line bg-ink-900 px-3.5 py-1.5 text-sm font-medium text-zinc-200 transition-colors hover:bg-ink-800 disabled:opacity-60"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  onMarkApplied();
                }}
                disabled={appPending}
                className="rounded-lg bg-accent px-3.5 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60"
              >
                {appPending ? "Marking…" : "Mark as Applied"}
              </button>
            </div>
          </div>
        ) : (
          <div className="mt-3">
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="inline-flex items-center rounded-lg border border-line bg-ink-850 px-3.5 py-2 text-sm font-medium text-zinc-200 transition-colors hover:bg-ink-800"
            >
              Mark as Applied
            </button>
            {appError ? (
              <p role="alert" className="mt-1.5 text-xs text-danger">
                {appError}
              </p>
            ) : null}
          </div>
        )}
      </section>

      {/* Intelligence */}
      <Section title="Why this job matches" labelledBy="why-matches">
        {intelligence?.reason ? (
          <p className="text-sm leading-relaxed text-zinc-200">{intelligence.reason}</p>
        ) : (
          <p className="text-sm leading-relaxed text-fog">
            Match details are not available for this job yet.
          </p>
        )}
        {strengths.length > 0 ? (
          <div className="mt-4">
            <h3 className="text-[11px] font-medium uppercase tracking-wide text-fog-dim">
              Your strengths
            </h3>
            <ul aria-label="Your strengths" className="mt-1.5 flex flex-wrap gap-1.5">
              {strengths.map((skill) => (
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
          <div className="mt-4">
            <h3 className="text-[11px] font-medium uppercase tracking-wide text-fog-dim">
              Skills to strengthen
            </h3>
            <ul aria-label="Skills to strengthen" className="mt-1.5 flex flex-wrap gap-1.5">
              {missing.map((skill) => (
                <li
                  key={skill}
                  className="rounded-md border border-caution/25 bg-caution/10 px-2 py-0.5 text-xs text-caution"
                >
                  {skill}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </Section>

      {/* Description */}
      {job.description && job.description.trim() ? (
        <Section title="Job Description" labelledBy="job-description">
          <div className="space-y-3">
            {job.description
              .split(/\n\s*\n/)
              .map((paragraph) => paragraph.trim())
              .filter(Boolean)
              .map((paragraph, index) => (
                <p key={index} className="whitespace-pre-line text-sm leading-relaxed text-zinc-300">
                  {paragraph}
                </p>
              ))}
          </div>
        </Section>
      ) : null}

      {/* Metadata */}
      <Section title="Job Information" labelledBy="job-information">
        <dl className="divide-y divide-line-soft">
          {employment ? <InfoRow label="Employment Type" value={employment} /> : null}
          {job.location?.trim() ? <InfoRow label="Location" value={job.location.trim()} /> : null}
          {job.is_remote !== null ? (
            <InfoRow label="Remote" value={job.is_remote ? "Yes" : "No"} />
          ) : null}
          {salary ? <InfoRow label="Salary" value={salary} /> : null}
          {source ? <InfoRow label="Source" value={source} /> : null}
          {posted ? <InfoRow label="Posted" value={posted} /> : null}
          {!employment &&
          !job.location?.trim() &&
          job.is_remote === null &&
          !salary &&
          !source &&
          !posted ? (
            <p className="py-2.5 text-sm text-fog">No additional details available.</p>
          ) : null}
        </dl>
      </Section>
    </div>
  );
}

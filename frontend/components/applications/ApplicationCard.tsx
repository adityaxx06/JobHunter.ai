"use client";

// One tracker row: job context, status, applied date, actions.
// Missing job data degrades gracefully (never fabricated).
import Link from "next/link";
import { StatusBadge } from "@/components/applications/StatusBadge";
import { ExternalIcon, PinIcon } from "@/components/ui/icons";
import { formatRelativeDate, formatWorkMode } from "@/lib/format";
import type { ApplicationItem } from "@/types/job";

export function ApplicationCard({
  application,
  onOpen,
}: {
  application: ApplicationItem;
  onOpen: () => void;
}) {
  const meta = [application.company, formatWorkMode(application.location, application.is_remote)]
    .filter(Boolean)
    .join(" · ");
  const applied = formatRelativeDate(application.applied_at, "Applied");

  return (
    <article className="animate-rise rounded-xl2 border border-line bg-ink-900 p-5 shadow-card transition-[border-color,box-shadow,transform] duration-200 hover:-translate-y-px hover:border-accent/40 hover:shadow-pop">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-[15px] font-semibold tracking-tight">
            {application.title ?? "Company information unavailable"}
          </h3>
          {meta ? (
            <p className="mt-0.5 flex min-w-0 items-center gap-1.5 truncate text-sm text-fog">
              <PinIcon size={14} className="shrink-0 text-fog-dim" />
              <span className="truncate">{meta}</span>
            </p>
          ) : null}
        </div>
        <StatusBadge status={application.status} />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-fog-dim">
        {applied ? <span>{applied}</span> : null}
        {application.employment_type ? <span>{application.employment_type}</span> : null}
      </div>

      {application.notes && application.notes.trim() ? (
        <p className="mt-2.5 line-clamp-2 text-sm leading-relaxed text-fog">
          {application.notes.trim()}
        </p>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Link
          href={`/jobs/${application.job_id}`}
          className="inline-flex items-center rounded-lg border border-line bg-ink-850 px-3.5 py-2 text-sm font-medium text-zinc-200 transition-colors hover:bg-ink-800"
        >
          View Job
        </Link>
        {application.apply_url ? (
          <a
            href={application.apply_url}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`Open application page for ${application.title ?? "this role"} (opens in a new tab)`}
            className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium text-fog transition-colors hover:text-zinc-100"
          >
            Apply page
            <ExternalIcon size={14} />
          </a>
        ) : null}
        <button
          type="button"
          onClick={onOpen}
          aria-label={`Update application for ${application.title ?? "this role"}`}
          className="inline-flex items-center rounded-lg bg-accent px-3.5 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
        >
          Update Status
        </button>
      </div>
    </article>
  );
}

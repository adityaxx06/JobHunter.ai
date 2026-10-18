"use client";

// Application detail modal: status transitions, explicit notes saving,
// applied date, and links. No autosave — Save Notes is deliberate.
// Failures restore the previous state and show an honest message.
import Link from "next/link";
import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/applications/StatusBadge";
import { CloseIcon } from "@/components/ui/icons";
import { APPLICATION_STATUSES, statusLabel } from "@/lib/applicationStatus";
import { formatRelativeDate } from "@/lib/format";
import type { ApplicationItem } from "@/types/job";

const NOTES_MAX_LENGTH = 5000;

export function ApplicationModal({
  application,
  saving,
  saveState,
  error,
  onClose,
  onSave,
}: {
  application: ApplicationItem;
  saving: boolean;
  saveState: "idle" | "saving" | "saved";
  error: string | null;
  onClose: () => void;
  onSave: (input: { status: string; notes: string | null }) => void;
}) {
  const [status, setStatus] = useState(application.status);
  const [notes, setNotes] = useState(application.notes ?? "");
  const [notesTouched, setNotesTouched] = useState(false);
  const applied = formatRelativeDate(application.applied_at, "Applied");

  useEffect(() => {
    setStatus(application.status);
    setNotes(application.notes ?? "");
    setNotesTouched(false);
  }, [application]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const statusDirty = status !== application.status;
  const notesDirty = notesTouched && notes !== (application.notes ?? "");
  const canSave = (statusDirty || notesDirty) && !saving;
  const notesTooLong = notes.length > NOTES_MAX_LENGTH;

  function handleSave() {
    if (!canSave || notesTooLong) return;
    onSave({
      status,
      notes: notesDirty ? notes : null,
    });
  }

  return (
    <div
      className="fixed inset-0 z-40 flex items-end justify-center sm:items-center sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`Application for ${application.title ?? "a role"}`}
    >
      <div className="absolute inset-0 bg-black/60" onClick={onClose} aria-hidden="true" />
      <div className="relative max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-t-2xl border border-line bg-ink-900 p-5 sm:rounded-2xl sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold tracking-tight">
              {application.title ?? "Company information unavailable"}
            </h2>
            {application.company ? (
              <p className="mt-0.5 truncate text-sm text-fog">{application.company}</p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close application details"
            className="rounded-lg p-2 text-fog transition-colors hover:bg-ink-800 hover:text-zinc-100"
          >
            <CloseIcon size={18} />
          </button>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <StatusBadge status={status} />
          {applied ? <span className="text-xs text-fog-dim">{applied}</span> : null}
        </div>

        <div className="mt-4">
          <label
            htmlFor="application-status"
            className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-fog-dim"
          >
            Status
          </label>
          <select
            id="application-status"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            disabled={saving}
            className="w-full rounded-lg border border-line bg-ink-850 px-2.5 py-2 text-sm text-zinc-200 focus:outline-none disabled:opacity-60"
          >
            {APPLICATION_STATUSES.map((value) => (
              <option key={value} value={value}>
                {statusLabel(value)}
              </option>
            ))}
          </select>
        </div>

        <div className="mt-4">
          <label
            htmlFor="application-notes"
            className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-fog-dim"
          >
            Notes
          </label>
          <textarea
            id="application-notes"
            value={notes}
            onChange={(event) => {
              setNotes(event.target.value);
              setNotesTouched(true);
            }}
            disabled={saving}
            rows={4}
            maxLength={NOTES_MAX_LENGTH + 100}
            placeholder="Recruiter contact, interview rounds, follow-ups…"
            className="w-full resize-y rounded-lg border border-line bg-ink-850 px-3 py-2 text-sm text-zinc-200 placeholder:text-fog-faint focus:outline-none disabled:opacity-60"
          />
          <div className="mt-1 flex items-center justify-between text-xs">
            <span className={notesTooLong ? "text-danger" : "text-fog-dim"}>
              {notes.length} / {NOTES_MAX_LENGTH}
            </span>
            {saveState === "saved" && !notesDirty && !statusDirty ? (
              <span className="text-positive">Saved</span>
            ) : null}
          </div>
        </div>
        {notesTooLong ? (
          <p role="alert" className="mt-1 text-xs text-danger">
            Notes must be {NOTES_MAX_LENGTH} characters or fewer.
          </p>
        ) : null}

        {error ? (
          <p role="alert" className="mt-3 text-xs text-danger">
            {error}
          </p>
        ) : null}

        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <button
            type="button"
            onClick={handleSave}
            disabled={!canSave}
            className="inline-flex flex-1 items-center justify-center rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save Notes"}
          </button>
          <Link
            href={`/jobs/${application.job_id}`}
            className="inline-flex flex-1 items-center justify-center rounded-lg border border-line bg-ink-850 px-4 py-2 text-sm font-medium text-zinc-200 transition-colors hover:bg-ink-800"
          >
            View Job
          </Link>
        </div>
      </div>
    </div>
  );
}

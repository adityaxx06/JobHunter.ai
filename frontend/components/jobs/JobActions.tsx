"use client";

// Shared Apply/Save actions (single implementation for cards + detail page).
// Apply opens the real backend URL in a new tab and never touches internal
// state. Save toggles through SavedJobsContext via the parent's handler.
import {
  BookmarkFilledIcon,
  BookmarkIcon,
  CheckIcon,
  ExternalIcon,
} from "@/components/ui/icons";
import { cn } from "@/lib/utils";

export function ApplyButton({
  applyUrl,
  title,
  className,
}: {
  applyUrl: string | null;
  title: string | null;
  className?: string;
}) {
  const label = `Apply for ${title ?? "this role"}`;
  if (!applyUrl) {
    return (
      <button
        type="button"
        disabled
        title="No application link provided for this role"
        className={cn(
          "inline-flex cursor-not-allowed items-center justify-center gap-1.5 rounded-lg border border-line bg-ink-850 px-3.5 py-2 text-sm font-medium text-fog-dim",
          className,
        )}
      >
        Apply Now
        <ExternalIcon size={15} />
      </button>
    );
  }
  return (
    <a
      href={applyUrl}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`${label} (opens in a new tab)`}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-lg bg-accent px-3.5 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90",
        className,
      )}
    >
      Apply Now
      <ExternalIcon size={15} />
    </a>
  );
}

export function SaveButton({
  saved,
  pending,
  onToggle,
  title,
  className,
}: {
  saved: boolean;
  pending: boolean;
  onToggle: () => void;
  title: string | null;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={pending}
      aria-pressed={saved}
      aria-label={`${saved ? "Unsave" : "Save"} ${title ?? "this role"}`}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-lg border px-3.5 py-2 text-sm font-medium transition-colors disabled:opacity-60",
        saved
          ? "border-accent/40 bg-accent-dim text-accent-soft hover:bg-accent-dim"
          : "border-line bg-ink-850 text-zinc-200 hover:border-line hover:bg-ink-800",
        className,
      )}
    >
      {saved ? <BookmarkFilledIcon size={15} /> : <BookmarkIcon size={15} />}
      {pending ? "Saving…" : saved ? (
        <span className="inline-flex items-center gap-1">
          Saved <CheckIcon size={14} />
        </span>
      ) : (
        "Save"
      )}
    </button>
  );
}

// Shared card/field styling for the Profile workspace (matches dashboard tokens).
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export const CARD = "rounded-xl2 border border-line bg-ink-900 p-5 shadow-card";
export const TITLE = "text-base font-semibold tracking-tight text-zinc-50";
export const SUBTITLE = "mt-1 text-sm text-fog";
export const LABEL = "mb-1 block text-xs font-medium uppercase tracking-wide text-fog";
export const INPUT =
  "w-full rounded-lg border border-line bg-ink-850 px-3 py-2 text-sm text-zinc-200 placeholder:text-fog-faint focus:outline-none disabled:opacity-60";
export const BTN_PRIMARY =
  "rounded-lg bg-accent px-4 py-2 text-sm font-medium text-ink-950 transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50";
export const BTN_GHOST =
  "rounded-lg border border-line bg-ink-850 px-3.5 py-2 text-sm font-medium text-zinc-200 transition-colors hover:bg-ink-800 disabled:opacity-60";
export const BTN_DANGER =
  "rounded-lg border border-line px-2.5 py-1 text-xs font-medium text-fog transition-colors hover:border-danger/50 hover:text-danger disabled:opacity-60";

export function Section({
  title,
  blurb,
  action,
  children,
}: {
  title: string;
  blurb: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className={cn(CARD, "animate-rise")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className={TITLE}>{title}</h2>
          <p className={SUBTITLE}>{blurb}</p>
        </div>
        {action}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

export function FieldError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="mt-2 text-sm text-danger">
      {message}
    </p>
  );
}

// Application status badge. Text label always present (never color-only);
// unknown backend values degrade to a neutral chip instead of crashing.
import { cn } from "@/lib/utils";
import { statusLabel } from "@/lib/applicationStatus";

const STATUS_STYLES: Record<string, string> = {
  saved: "bg-fog/10 text-fog border-line",
  applied: "bg-sky-400/10 text-sky-300 border-sky-400/25",
  assessment: "bg-caution/10 text-caution border-caution/25",
  interview: "bg-accent/10 text-accent-soft border-accent/25",
  offer: "bg-positive/10 text-positive border-positive/25",
  rejected: "bg-danger/10 text-danger border-danger/25",
  withdrawn: "bg-fog/10 text-fog-dim border-line",
};

export function StatusBadge({ status }: { status: string }) {
  const className = STATUS_STYLES[status] ?? "bg-fog/10 text-fog border-line";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide",
        className,
      )}
    >
      {statusLabel(status)}
    </span>
  );
}

// Score + recommendation visuals. Text labels always accompany color so
// status stays understandable without color vision.
import { cn } from "@/lib/utils";
import type { Recommendation } from "@/types/job";

export function MatchScore({ value }: { value: number }) {
  return (
    <span
      className="inline-flex items-baseline gap-1 rounded-md bg-positive/10 px-2 py-1 text-sm font-semibold text-positive"
      aria-label={`Match score ${value} percent`}
    >
      <span className="tabular-nums">{value}%</span>
      <span className="text-[11px] font-medium uppercase tracking-wide">Match</span>
    </span>
  );
}

export function TrustScore({ value }: { value: number }) {
  const tone =
    value >= 70
      ? "bg-sky-400/10 text-sky-300"
      : value >= 50
        ? "bg-caution/10 text-caution"
        : "bg-danger/10 text-danger";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-sm font-semibold",
        tone,
      )}
      aria-label={`Trust score ${value} out of 100`}
    >
      <ShieldDot />
      <span className="tabular-nums">{value}</span>
      <span className="text-[11px] font-medium uppercase tracking-wide">Trust</span>
    </span>
  );
}

function ShieldDot() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 3 5 5.8v5.4c0 4.3 2.9 7.4 7 9.3 4.1-1.9 7-5 7-9.3V5.8z" />
    </svg>
  );
}

const RECOMMENDATION_STYLES: Record<Recommendation, { label: string; className: string }> = {
  APPLY: { label: "Apply", className: "bg-positive/10 text-positive border-positive/25" },
  CONSIDER: { label: "Consider", className: "bg-accent/10 text-accent-soft border-accent/25" },
  REVIEW: { label: "Review", className: "bg-caution/10 text-caution border-caution/25" },
  AVOID: { label: "Avoid", className: "bg-danger/10 text-danger border-danger/25" },
};

export function RecommendationBadge({ value }: { value: Recommendation | string }) {
  const style =
    RECOMMENDATION_STYLES[value as Recommendation] ?? ({
      label: String(value),
      className: "bg-fog/10 text-fog border-line",
    } as const);
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide",
        style.className,
      )}
    >
      {style.label}
    </span>
  );
}

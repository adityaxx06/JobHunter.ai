// Display formatting for job data. Everything here is presentational —
// scores and rankings are never recalculated, only labeled/formatted.

export type MatchBand = "Excellent" | "Strong" | "Good" | "Maybe" | "Low";

/** Backend-authoritative score mapped to a visual label only. */
export function matchBand(score: number): MatchBand {
  if (score >= 90) return "Excellent";
  if (score >= 80) return "Strong";
  if (score >= 70) return "Good";
  if (score >= 60) return "Maybe";
  return "Low";
}

export type TrustBand = "Highly Trusted" | "Trusted" | "Moderate" | "Low Trust";

/** Backend-authoritative trust mapped to a visual label only. */
export function trustBand(score: number): TrustBand {
  if (score >= 90) return "Highly Trusted";
  if (score >= 70) return "Trusted";
  if (score >= 50) return "Moderate";
  return "Low Trust";
}

const CURRENCY_SYMBOLS: Record<string, string> = {
  INR: "₹",
  USD: "$",
  EUR: "€",
  GBP: "£",
};

function compactAmount(value: number, currency: string): string {
  const symbol = CURRENCY_SYMBOLS[currency] ?? `${currency} `;
  if (currency === "INR" && value >= 100000 && value % 100000 === 0) {
    return `${symbol}${value / 100000}L`;
  }
  if (value >= 1000 && value % 1000 === 0) {
    return `${symbol}${value / 1000}k`;
  }
  return `${symbol}${value.toLocaleString("en-US")}`;
}

/**
 * Honest salary line from real fields only. Returns null when no usable
 * bound exists — never "₹0", never an estimate. No pay period is shown
 * because the API does not provide one.
 */
export function formatSalary(
  min: number | null,
  max: number | null,
  currency: string | null,
): string | null {
  const code = (currency ?? "").trim() || "INR";
  const hasMin = typeof min === "number" && min > 0;
  const hasMax = typeof max === "number" && max > 0;
  if (!hasMin && !hasMax) return null;
  if (hasMin && hasMax) {
    if (min === max) return compactAmount(min as number, code);
    return `${compactAmount(min as number, code)}–${compactAmount(max as number, code)}`;
  }
  if (hasMin) return `${compactAmount(min as number, code)}+`;
  return `Up to ${compactAmount(max as number, code)}`;
}

/** "Chennai · Remote" style location line from real fields only. */
export function formatWorkMode(location: string | null, isRemote: boolean | null): string | null {
  const place = (location ?? "").trim() || null;
  if (isRemote && place) {
    return place.toLowerCase().includes("remote") ? place : `${place} · Remote`;
  }
  if (isRemote) return "Remote";
  return place;
}

const SOURCE_LABELS: Record<string, string> = {
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  company_careers: "Company Career Page",
  job_board: "Job Board",
  search_engine: "Search Discovery",
  manual: "Manual",
};

/** Human source label from the backend vocabulary (unknown values pass through). */
export function formatSource(source: string | null): string | null {
  const key = (source ?? "").trim();
  if (!key) return null;
  return SOURCE_LABELS[key.toLowerCase()] ?? key;
}

/** Localized posted date, or null when missing/invalid (never invented). */
export function formatPostedDate(iso: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/**
 * Human relative date ("Applied today", "Applied 3 days ago",
 * "Applied Sep 28, 2026"). Null/invalid input yields null — never invented.
 */
export function formatRelativeDate(iso: string | null, prefix = ""): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  const now = new Date();
  const startOf = (value: Date) =>
    new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
  const days = Math.round((startOf(now) - startOf(date)) / 86400000);
  const label =
    days <= 0
      ? "today"
      : days === 1
        ? "yesterday"
        : days < 30
          ? `${days} days ago`
          : (formatPostedDate(iso) ?? "an earlier date");
  const lead = prefix ? `${prefix} ` : "";
  return days < 30 ? `${lead}${label}` : `${lead}${label}`;
}

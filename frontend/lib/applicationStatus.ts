// Centralized application-status vocabulary (Phase 5.5E). Single place only.
// Values match the database CHECK constraint exactly; labels are display-only.
// Unknown values from the API fall back to neutral styling, never crash.
export const APPLICATION_STATUSES = [
  "saved",
  "applied",
  "assessment",
  "interview",
  "offer",
  "rejected",
  "withdrawn",
] as const;

export type ApplicationStatus = (typeof APPLICATION_STATUSES)[number];

const STATUS_LABELS: Record<string, string> = {
  saved: "Saved",
  applied: "Applied",
  assessment: "Assessment",
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

export function isApplicationStatus(value: string): value is ApplicationStatus {
  return (APPLICATION_STATUSES as readonly string[]).includes(value);
}

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

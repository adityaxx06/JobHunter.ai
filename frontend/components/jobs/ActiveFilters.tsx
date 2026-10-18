"use client";

// Active-filter chips + Clear all. Each chip removes exactly one filter;
// Clear all resets search, filters, sort, and page to defaults.
export interface ActiveFilter {
  key: string;
  label: string;
  onRemove: () => void;
}

export function ActiveFilters({
  filters,
  onClearAll,
}: {
  filters: ActiveFilter[];
  onClearAll: () => void;
}) {
  if (filters.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5" aria-label="Active filters">
      <span className="text-xs font-medium text-fog-dim">Active filters:</span>
      {filters.map((filter) => (
        <button
          key={filter.key}
          type="button"
          onClick={filter.onRemove}
          aria-label={`Remove ${filter.label} filter`}
          title={`Remove ${filter.label}`}
          className="inline-flex items-center gap-1 rounded-full border border-accent/30 bg-accent-dim px-2.5 py-1 text-xs font-medium text-accent-soft transition-colors hover:border-accent/60"
        >
          {filter.label}
          <span aria-hidden="true" className="text-sm leading-none">
            ×
          </span>
        </button>
      ))}
      <button
        type="button"
        onClick={onClearAll}
        className="rounded-full px-2 py-1 text-xs font-medium text-fog transition-colors hover:text-zinc-100"
      >
        Clear all
      </button>
    </div>
  );
}

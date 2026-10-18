"use client";

// Compact page-number pagination with prev/next, ellipsis for large sets,
// and meaningful aria labels. No page-size control (fixed server limit).
export function JobPagination({
  page,
  totalPages,
  onPage,
}: {
  page: number;
  totalPages: number;
  onPage: (page: number) => void;
}) {
  if (totalPages <= 1) return null;

  const numbers: (number | "gap")[] = [];
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) numbers.push(i);
  } else {
    numbers.push(1);
    const start = Math.max(2, page - 1);
    const end = Math.min(totalPages - 1, page + 1);
    if (start > 2) numbers.push("gap");
    for (let i = start; i <= end; i++) numbers.push(i);
    if (end < totalPages - 1) numbers.push("gap");
    numbers.push(totalPages);
  }

  const buttonClass = (active: boolean) =>
    `min-w-9 rounded-lg border px-2.5 py-1.5 text-sm tabular-nums transition-colors ${
      active
        ? "border-accent/50 bg-accent-dim font-semibold text-zinc-50"
        : "border-line bg-ink-900 text-fog hover:bg-ink-800 hover:text-zinc-100"
    }`;

  return (
    <nav aria-label="Job results pages" className="flex flex-wrap items-center justify-center gap-1.5">
      <button
        type="button"
        onClick={() => onPage(page - 1)}
        disabled={page <= 1}
        aria-label="Previous page"
        className="rounded-lg border border-line bg-ink-900 px-3 py-1.5 text-sm text-fog transition-colors hover:bg-ink-800 hover:text-zinc-100 disabled:cursor-not-allowed disabled:opacity-40"
      >
        ← Prev
      </button>
      {numbers.map((number, index) =>
        number === "gap" ? (
          <span key={`gap-${index}`} aria-hidden="true" className="px-1 text-fog-faint">
            …
          </span>
        ) : (
          <button
            key={number}
            type="button"
            onClick={() => onPage(number)}
            disabled={number === page}
            aria-label={`Page ${number}`}
            aria-current={number === page ? "page" : undefined}
            className={buttonClass(number === page)}
          >
            {number}
          </button>
        ),
      )}
      <button
        type="button"
        onClick={() => onPage(page + 1)}
        disabled={page >= totalPages}
        aria-label="Next page"
        className="rounded-lg border border-line bg-ink-900 px-3 py-1.5 text-sm text-fog transition-colors hover:bg-ink-800 hover:text-zinc-100 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Next →
      </button>
    </nav>
  );
}

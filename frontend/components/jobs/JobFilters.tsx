"use client";

// Filter toolbar: debounced search + labeled selects. Desktop shows the
// toolbar inline; mobile collapses it behind a Filters button with a count
// badge. All controls are native labeled elements (keyboard accessible).
import { useEffect, useState } from "react";
import { CloseIcon, SearchIcon } from "@/components/ui/icons";
import {
  EMPLOYMENT_OPTIONS,
  MATCH_OPTIONS,
  RECOMMENDATION_OPTIONS,
  REMOTE_OPTIONS,
  TRUST_OPTIONS,
} from "@/lib/filters";
import { cn } from "@/lib/utils";

export interface FilterValues {
  q: string;
  role: string;
  location: string;
  remote: string;
  match: string;
  trust: string;
  rec: string;
  employment: string;
}

const selectClass =
  "w-full rounded-lg border border-line bg-ink-900 px-2.5 py-2 text-sm text-zinc-200 focus:outline-none";
  "w-full rounded-lg border border-line bg-ink-900 px-2.5 py-2 text-sm text-zinc-200 focus:outline-none";

function Field({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-w-0">
      <label htmlFor={id} className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-fog-dim">
        {label}
      </label>
      {children}
    </div>
  );
}

function SearchInput({ value, onCommit }: { value: string; onCommit: (v: string) => void }) {
  const [text, setText] = useState(value);
  useEffect(() => {
    setText(value);
  }, [value]);
  useEffect(() => {
    if (text === value) return;
    const timer = setTimeout(() => onCommit(text.trim()), 350);
    return () => clearTimeout(timer);
  }, [text, value, onCommit]);

  return (
    <form
      role="search"
      aria-label="Job search"
      onSubmit={(event) => {
        event.preventDefault();
        onCommit(text.trim());
      }}
    >
      <div className="relative">
        <SearchIcon
          size={16}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fog-faint"
        />
        <input
          type="search"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Search jobs, skills, companies…"
          aria-label="Search jobs, skills, companies"
          className="w-full rounded-xl border border-line bg-ink-900 py-2.5 pl-9 pr-3 text-sm text-zinc-100 placeholder:text-fog-faint focus:outline-none"
        />
      </div>
    </form>
  );
}

function Select({
  id,
  value,
  onChange,
  options,
  ariaLabel,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[] | string[];
  ariaLabel: string;
}) {
  return (
    <select
      id={id}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      aria-label={ariaLabel}
      className={selectClass}
    >
      {options.map((option) =>
        typeof option === "string" ? (
          <option key={option || "all"} value={option}>
            {option || "All roles"}
          </option>
        ) : (
          <option key={option.value || "all"} value={option.value}>
            {option.label}
          </option>
        ),
      )}
    </select>
  );
}

export function JobFilters({
  values,
  onChange,
  roleOptions,
  locationOptions,
  activeCount,
}: {
  values: FilterValues;
  onChange: (patch: Partial<FilterValues>) => void;
  roleOptions: string[];
  locationOptions: string[];
  activeCount: number;
}) {
  const [drawerOpen, setDrawerOpen] = useState(false);

  const fields = (
    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4">
      <Field id="filter-role" label="Role">
        <Select
          id="filter-role"
          ariaLabel="Filter by role"
          value={values.role}
          onChange={(role) => onChange({ role })}
          options={[{ value: "", label: "All roles" }, ...roleOptions.map((r) => ({ value: r, label: r }))]}
        />
      </Field>
      <Field id="filter-location" label="Location">
        <Select
          id="filter-location"
          ariaLabel="Filter by location"
          value={values.location}
          onChange={(location) => onChange({ location })}
          options={[{ value: "", label: "All locations" }, ...locationOptions.map((l) => ({ value: l, label: l }))]}
        />
      </Field>
      <Field id="filter-remote" label="Work mode">
        <Select
          id="filter-remote"
          ariaLabel="Filter by remote"
          value={values.remote}
          onChange={(remote) => onChange({ remote })}
          options={REMOTE_OPTIONS}
        />
      </Field>
      <Field id="filter-match" label="Match">
        <Select
          id="filter-match"
          ariaLabel="Filter by minimum match score"
          value={values.match}
          onChange={(match) => onChange({ match })}
          options={MATCH_OPTIONS}
        />
      </Field>
      <Field id="filter-trust" label="Trust">
        <Select
          id="filter-trust"
          ariaLabel="Filter by minimum trust score"
          value={values.trust}
          onChange={(trust) => onChange({ trust })}
          options={TRUST_OPTIONS}
        />
      </Field>
      <Field id="filter-rec" label="Recommendation">
        <Select
          id="filter-rec"
          ariaLabel="Filter by recommendation"
          value={values.rec}
          onChange={(rec) => onChange({ rec })}
          options={RECOMMENDATION_OPTIONS}
        />
      </Field>
      <Field id="filter-employment" label="Employment">
        <Select
          id="filter-employment"
          ariaLabel="Filter by employment type"
          value={values.employment}
          onChange={(employment) => onChange({ employment })}
          options={EMPLOYMENT_OPTIONS}
        />
      </Field>
    </div>
  );

  return (
    <div className="mt-4">
      <SearchInput value={values.q} onCommit={(q) => onChange({ q })} />
      {/* Desktop toolbar */}
      <div className="mt-3 hidden lg:block">{fields}</div>
      {/* Mobile drawer */}
      <div className="mt-3 lg:hidden">
        <button
          type="button"
          onClick={() => setDrawerOpen(true)}
          aria-haspopup="dialog"
          className="inline-flex items-center gap-2 rounded-lg border border-line bg-ink-900 px-3.5 py-2 text-sm font-medium text-zinc-200"
        >
          Filters
          {activeCount > 0 ? (
            <span
              aria-label={`${activeCount} active filters`}
              className="rounded-full bg-accent-dim px-2 py-px text-xs font-semibold text-accent-soft"
            >
              {activeCount}
            </span>
          ) : null}
        </button>
      </div>
      {drawerOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Job filters">
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setDrawerOpen(false)}
            aria-hidden="true"
          />
          <div className="absolute inset-x-0 bottom-0 max-h-[85vh] overflow-y-auto rounded-t-2xl border-t border-line bg-ink-900 p-5">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-base font-semibold">Filters</h3>
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                aria-label="Close filters"
                className="rounded-lg p-2 text-fog hover:bg-ink-800"
              >
                <CloseIcon size={18} />
              </button>
            </div>
            {fields}
            <button
              type="button"
              onClick={() => setDrawerOpen(false)}
              className={cn(
                "mt-5 w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white",
              )}
            >
              Show results
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

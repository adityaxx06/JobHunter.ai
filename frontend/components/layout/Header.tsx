"use client";

// Top header: page title, jobs shortcut, API status, avatar.
import Link from "next/link";
import { useEffect, useState } from "react";
import { getHealth } from "@/lib/api";
import { MenuIcon, SearchIcon } from "@/components/ui/icons";
import { cn } from "@/lib/utils";

type ApiState = "checking" | "online" | "offline";

function useApiStatus(): ApiState {
  const [state, setState] = useState<ApiState>("checking");
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    getHealth(controller.signal)
      .then(() => {
        if (!controller.signal.aborted) setState("online");
      })
      .catch(() => {
        if (!controller.signal.aborted) setState("offline");
      })
      .finally(() => clearTimeout(timer));
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, []);
  return state;
}

function ApiStatus() {
  const state = useApiStatus();
  const label =
    state === "online"
      ? "Intelligence engine online"
      : state === "offline"
        ? "API unavailable"
        : "Checking API status";
  return (
    <span
      role="status"
      aria-label={label}
      title={label}
      className="inline-flex items-center gap-1.5 rounded-full border border-line bg-ink-900 px-2.5 py-1 text-xs text-fog"
    >
      <span
        aria-hidden="true"
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          state === "online" && "bg-positive",
          state === "offline" && "bg-danger",
          state === "checking" && "bg-caution",
        )}
      />
      <span className="hidden sm:inline">{state === "online" ? "System Ready" : label}</span>
      <span className="sm:hidden">{state === "online" ? "Ready" : state === "offline" ? "Down" : "…"}</span>
    </span>
  );
}

export function Header({ title, onMenu }: { title: string; onMenu: () => void }) {
  return (
    <header className="sticky top-0 z-20 border-b border-line-soft bg-ink-950/85 backdrop-blur">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-3 px-4 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={onMenu}
          aria-label="Open navigation menu"
          className="rounded-lg p-2 text-fog transition-colors hover:bg-ink-800 hover:text-zinc-100 lg:hidden"
        >
          <MenuIcon size={20} />
        </button>

        <h1 className="min-w-0 flex-1 truncate text-base font-semibold tracking-tight sm:text-lg">
          {title}
        </h1>

        <Link
          href="/jobs"
          aria-label="Search jobs in the Job Explorer"
          title="Search jobs in the Job Explorer"
          className="relative hidden md:block"
        >
          <SearchIcon
            size={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fog-faint"
          />
          <span className="block w-52 cursor-pointer truncate rounded-lg border border-line bg-ink-900 py-2 pl-9 pr-3 text-sm text-fog-faint lg:w-64">
            Search jobs…
          </span>
        </Link>

        <ApiStatus />

        <span
          aria-label="Signed in as Aditya, MCA Student"
          title="Aditya · MCA Student"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink-800 text-xs font-semibold text-accent-soft"
        >
          A
        </span>
      </div>
    </header>
  );
}

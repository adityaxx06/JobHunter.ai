"use client";

// Dashboard error state with a working retry (router.refresh re-runs the
// server fetch below it). Never surfaces backend internals.
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AlertIcon, RefreshIcon } from "@/components/ui/icons";

export function DashboardError({ onRetry }: { onRetry?: () => void }) {
  const router = useRouter();
  const [retrying, setRetrying] = useState(false);

  async function handleRetry() {
    if (onRetry) {
      setRetrying(true);
      try {
        await onRetry();
      } finally {
        setRetrying(false);
      }
      return;
    }
    setRetrying(true);
    router.refresh();
    setTimeout(() => setRetrying(false), 1500);
  }

  return (
    <div
      role="alert"
      className="flex flex-col items-center rounded-xl2 border border-line bg-ink-900 px-6 py-14 text-center"
    >
      <span
        aria-hidden="true"
        className="flex h-12 w-12 items-center justify-center rounded-full bg-danger/10 text-danger"
      >
        <AlertIcon size={22} />
      </span>
      <h3 className="mt-4 text-base font-semibold tracking-tight">
        Unable to load job intelligence
      </h3>
      <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-fog">
        The AI-JobHunter API isn&apos;t responding right now. Check that the
        backend is running, then try again.
      </p>
      <button
        type="button"
        onClick={handleRetry}
        disabled={retrying}
        className="mt-5 inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60"
      >
        <RefreshIcon size={15} />
        {retrying ? "Retrying…" : "Retry"}
      </button>
    </div>
  );
}

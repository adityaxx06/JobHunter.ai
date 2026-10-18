"use client";

// /jobs route: server-driven explorer (search, filters, sort, pagination).
// Wrapped in Suspense because the explorer reads the URL query state.
import { Suspense } from "react";
import { JobExplorer } from "@/components/jobs/JobExplorer";
import { AppShell } from "@/components/layout/AppShell";
import { JobCardSkeleton } from "@/components/ui/Skeleton";

function ExplorerFallback() {
  return (
    <div className="grid grid-cols-1 gap-3 xl:grid-cols-2" aria-label="Loading jobs">
      {[0, 1, 2, 3].map((key) => (
        <JobCardSkeleton key={key} />
      ))}
    </div>
  );
}

export default function JobsPage() {
  return (
    <AppShell title="Jobs">
      <Suspense fallback={<ExplorerFallback />}>
        <JobExplorer />
      </Suspense>
    </AppShell>
  );
}

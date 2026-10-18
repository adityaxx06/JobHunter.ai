// Skeleton loaders that resemble the final UI (subtle shimmer, no spinners).
import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn("skeleton animate-shimmer rounded-md", className)}
    />
  );
}

export function StatCardSkeleton() {
  return (
    <div className="rounded-xl2 border border-line bg-ink-900 p-5">
      <Skeleton className="h-3.5 w-24" />
      <Skeleton className="mt-3 h-8 w-14" />
      <Skeleton className="mt-2 h-3.5 w-32" />
    </div>
  );
}

export function JobCardSkeleton() {
  return (
    <div
      className="rounded-xl2 border border-line bg-ink-900 p-5"
      aria-label="Loading job opportunity"
    >
      <div className="flex items-start justify-between gap-3">
        <Skeleton className="h-5 w-2/3" />
        <Skeleton className="h-7 w-24 shrink-0" />
      </div>
      <Skeleton className="mt-2 h-4 w-1/2" />
      <div className="mt-4 flex gap-2">
        <Skeleton className="h-6 w-16" />
        <Skeleton className="h-6 w-14" />
        <Skeleton className="h-6 w-12" />
      </div>
      <Skeleton className="mt-4 h-4 w-full" />
      <div className="mt-4 flex items-center justify-between">
        <Skeleton className="h-7 w-20" />
        <Skeleton className="h-9 w-28" />
      </div>
    </div>
  );
}

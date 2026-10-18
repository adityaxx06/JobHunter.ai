"use client";

// Main dashboard screen: greeting, stat cards, top opportunities.
// Handles loading (skeletons), error (retry), empty (polished empty state),
// and populated states. Client-rendered so `next build` never needs the API.
import { AppShell } from "@/components/layout/AppShell";
import { DashboardError } from "@/components/dashboard/DashboardError";
import { NeedsAttention } from "@/components/dashboard/NeedsAttention";
import { StatsGrid } from "@/components/dashboard/StatsGrid";
import { TopOpportunities } from "@/components/dashboard/TopOpportunities";
import { JobCardSkeleton, StatCardSkeleton } from "@/components/ui/Skeleton";
import { useDashboard } from "@/hooks/useDashboard";
import { useApplicationStatus } from "@/components/applications/ApplicationStatusContext";
import { useSavedJobs } from "@/components/saved/SavedJobsContext";

function greetingFor(date: Date): string {
  const hour = date.getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function formatStat(value: number | null): string {
  return value === null ? "—" : String(value);
}

export default function DashboardPage() {
  const { status, stats, topJobs, rankingsFailed, reload } = useDashboard();
  const {
    savedIds,
    pendingId: savePendingId,
    error: saveError,
    toggleSave,
  } = useSavedJobs();
  const { statusByJobId } = useApplicationStatus();

  return (
    <AppShell title="Dashboard">
      <div className="animate-rise">
        <p className="text-[15px] text-fog sm:text-base">
          {greetingFor(new Date())}, Aditya
        </p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight sm:text-2xl">
          Your job intelligence overview
        </h2>
      </div>

      <div className="mt-6" aria-label="Summary statistics">
        {status === "loading" ? (
          <div className="grid grid-cols-1 gap-3 min-[480px]:grid-cols-2 lg:grid-cols-4">
            {[0, 1, 2, 3].map((key) => (
              <StatCardSkeleton key={key} />
            ))}
          </div>
        ) : status === "error" ? (
          <DashboardError onRetry={reload} />
        ) : (
          <StatsGrid
            stats={[
              { label: "Opportunities", value: formatStat(stats.opportunities), hint: "Discovered jobs" },
              { label: "Analyzed", value: formatStat(stats.analyzed), hint: "AI-evaluated" },
              { label: "Top Matches", value: formatStat(stats.topMatches), hint: "Recommended to apply" },
              { label: "Applications", value: formatStat(stats.applications), hint: "Tracked" },
            ]}
          />
        )}
      </div>

      {status !== "error" && (
        <div className="mt-8">
          {status === "loading" ? (
            <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
              {[0, 1].map((key) => (
                <JobCardSkeleton key={key} />
              ))}
            </div>
          ) : (
            <>
              <TopOpportunities
                jobs={topJobs}
                savedIds={savedIds}
                savePendingId={savePendingId}
                saveError={saveError}
                onToggleSave={toggleSave}
                rankingsFailed={rankingsFailed}
                onRetryRankings={reload}
                applicationStatusByJob={statusByJobId}
              />
              <NeedsAttention jobs={topJobs} savedIds={savedIds} statusByJobId={statusByJobId} />
            </>
          )}
        </div>
      )}
    </AppShell>
  );
}

"use client";

// Dashboard data hook: parallel, abortable fetches with per-endpoint
// fallbacks. A stat the API cannot provide renders as "—", never a fake
// number. Only when every data source fails does the dashboard error.
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getApplications,
  getJobs,
  getMatches,
  getRankings,
} from "@/lib/api";
import { DEFAULT_PROFILE_ID } from "@/lib/config";
import type { RankedJob } from "@/types/job";

export interface DashboardStats {
  opportunities: number | null;
  analyzed: number | null;
  topMatches: number | null;
  applications: number | null;
}

export type DashboardStatus = "loading" | "ready" | "error";

export interface DashboardState {
  status: DashboardStatus;
  stats: DashboardStats;
  topJobs: RankedJob[];
  rankingsFailed: boolean;
  reload: () => void;
}

function countOrNull(
  result: PromiseSettledResult<{ count: number }>,
): number | null {
  return result.status === "fulfilled" ? result.value.count : null;
}

export function useDashboard(): DashboardState {
  const [status, setStatus] = useState<DashboardStatus>("loading");
  const [stats, setStats] = useState<DashboardStats>({
    opportunities: null,
    analyzed: null,
    topMatches: null,
    applications: null,
  });
  const [topJobs, setTopJobs] = useState<RankedJob[]>([]);
  const [rankingsFailed, setRankingsFailed] = useState(false);
  const requestId = useRef(0);

  const load = useCallback(() => {
    const current = ++requestId.current;
    const controller = new AbortController();
    setStatus("loading");

    (async () => {
      const [jobs, matches, rankings, applications] = await Promise.allSettled([
        getJobs({ limit: 1, offset: 0 }),
        getMatches(DEFAULT_PROFILE_ID, { limit: 1, offset: 0 }),
        // Latest-feed eligibility: the dashboard surfaces only fresh,
        // geography-fit, role-fit matches (ineligible rows never render
        // as verified-new opportunities).
        getRankings(DEFAULT_PROFILE_ID, { limit: 100, eligibleOnly: true }),
        getApplications(DEFAULT_PROFILE_ID, { limit: 1, offset: 0 }),
      ]);
      if (current !== requestId.current || controller.signal.aborted) return;

      const allFailed =
        jobs.status === "rejected" &&
        matches.status === "rejected" &&
        rankings.status === "rejected" &&
        applications.status === "rejected";
      if (allFailed) {
        setStatus("error");
        return;
      }

      const ranked =
        rankings.status === "fulfilled" ? rankings.value.items : [];
      setRankingsFailed(rankings.status === "rejected");
      setStats({
        opportunities: countOrNull(jobs),
        analyzed: countOrNull(matches),
        topMatches:
          rankings.status === "fulfilled"
            ? ranked.filter((job) => job.recommendation === "APPLY").length
            : null,
        applications: countOrNull(applications),
      });
      setTopJobs(ranked.slice(0, 5));
      setStatus("ready");
    })().catch(() => {
      if (current === requestId.current) setStatus("error");
    });

    return () => controller.abort();
  }, []);

  useEffect(() => {
    const cleanup = load();
    return cleanup;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reload = useCallback(() => {
    load();
  }, [load]);

  return { status, stats, topJobs, rankingsFailed, reload };
}

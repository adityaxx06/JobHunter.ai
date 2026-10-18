"use client";

// Shared application-status state, mounted once in the root layout next to
// SavedJobsContext. Loads the profile's tracker rows once (single request)
// into a jobId -> status map so cards can show status without N+1 fetches.
// Read-only: status changes happen on detail/tracker screens, never here.
import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { getApplications } from "@/lib/api";
import { DEFAULT_PROFILE_ID } from "@/lib/config";

export interface ApplicationStatusState {
  statusByJobId: Map<string, string>;
}

const ApplicationStatusContext = createContext<ApplicationStatusState | null>(null);

export function ApplicationStatusProvider({ children }: { children: React.ReactNode }) {
  const [statusByJobId, setStatusByJobId] = useState<Map<string, string>>(new Map());
  const requestId = useRef(0);
  const profileId = DEFAULT_PROFILE_ID;

  useEffect(() => {
    const current = ++requestId.current;
    getApplications(profileId, { limit: 100, offset: 0 })
      .then((response) => {
        if (current !== requestId.current) return;
        const next = new Map<string, string>();
        for (const item of response.items) {
          if (item.job_id && item.status) next.set(item.job_id, item.status);
        }
        setStatusByJobId(next);
      })
      .catch(() => {
        // Status badges simply stay hidden — cards render without them.
      });
    return () => {
      requestId.current += 1;
    };
  }, [profileId]);

  const value = useMemo(() => ({ statusByJobId }), [statusByJobId]);
  return <ApplicationStatusContext.Provider value={value}>{children}</ApplicationStatusContext.Provider>;
}

export function useApplicationStatus(): ApplicationStatusState {
  const state = useContext(ApplicationStatusContext);
  if (state === null) {
    throw new Error("useApplicationStatus must be used inside ApplicationStatusProvider");
  }
  return state;
}

"use client";

// Shared saved-jobs state, mounted once in the root layout so Dashboard and
// Job Explorer stay consistent. Loads the profile's saved IDs once; toggling
// is guarded against rapid double-submits and reverts with an honest message
// on failure (raw API errors never surface).
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { getSavedJobIds, saveJob, unsaveJob } from "@/lib/api";
import { DEFAULT_PROFILE_ID } from "@/lib/config";

export interface SavedJobsState {
  savedIds: Set<string>;
  pendingId: string | null;
  error: string | null;
  toggleSave: (jobId: string) => void;
}

const SavedJobsContext = createContext<SavedJobsState | null>(null);

export function SavedJobsProvider({ children }: { children: React.ReactNode }) {
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set());
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);
  const profileId = DEFAULT_PROFILE_ID;

  useEffect(() => {
    const current = ++requestId.current;
    getSavedJobIds(profileId)
      .then((response) => {
        if (current !== requestId.current) return;
        setSavedIds(new Set(response.job_ids));
      })
      .catch(() => {
        // Saving stays usable — failures surface per-action, not page-wide.
      });
    return () => {
      requestId.current += 1;
    };
  }, [profileId]);

  const toggleSave = useCallback(
    (jobId: string) => {
      if (pendingId !== null) return; // prevent duplicate rapid submissions
      setError(null);
      setPendingId(jobId);
      setSavedIds((previous) => {
        const optimistic = new Set(previous);
        if (optimistic.has(jobId)) {
          optimistic.delete(jobId);
        } else {
          optimistic.add(jobId);
        }
        return optimistic;
      });
      const wasSaved = savedIds.has(jobId);
      const action = wasSaved ? unsaveJob(jobId, profileId) : saveJob(jobId, profileId);
      action
        .then((response) => {
          setSavedIds((previous) => {
            const next = new Set(previous);
            if (response.saved) {
              next.add(jobId);
            } else {
              next.delete(jobId);
            }
            return next;
          });
        })
        .catch(() => {
          // Revert the optimistic update so state matches the server.
          setSavedIds((previous) => {
            const next = new Set(previous);
            if (wasSaved) {
              next.add(jobId);
            } else {
              next.delete(jobId);
            }
            return next;
          });
          setError("Unable to save this job. Try again.");
        })
        .finally(() => {
          setPendingId(null);
        });
    },
    [pendingId, savedIds, profileId],
  );

  const value = useMemo(
    () => ({ savedIds, pendingId, error, toggleSave }),
    [savedIds, pendingId, error, toggleSave],
  );
  return <SavedJobsContext.Provider value={value}>{children}</SavedJobsContext.Provider>;
}

export function useSavedJobs(): SavedJobsState {
  const state = useContext(SavedJobsContext);
  if (state === null) {
    throw new Error("useSavedJobs must be used inside SavedJobsProvider");
  }
  return state;
}

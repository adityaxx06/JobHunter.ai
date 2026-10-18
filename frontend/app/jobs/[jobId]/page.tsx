"use client";

// /jobs/[jobId] — full job detail from GET /api/jobs/{id} (+ stored
// intelligence for the default profile). Real data only: every optional
// section hides when its field is absent. Client-rendered so the build never
// needs the API or a job ID up front.
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { JobDetailView } from "@/components/jobs/JobDetailView";
import { AppShell } from "@/components/layout/AppShell";
import { BackIcon, RefreshIcon } from "@/components/ui/icons";
import { Skeleton } from "@/components/ui/Skeleton";
import { useSavedJobs } from "@/components/saved/SavedJobsContext";
import { createApplication, getApplication, getJob } from "@/lib/api";
import { DEFAULT_PROFILE_ID } from "@/lib/config";
import type { ApplicationItem, JobDetail } from "@/types/job";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type DetailStatus = "loading" | "ready" | "not-found" | "invalid" | "error";

function DetailSkeleton() {
  return (
    <div className="animate-rise space-y-4" aria-label="Loading job details">
      <div className="rounded-xl2 border border-line bg-ink-900 p-5 sm:p-6">
        <Skeleton className="h-3.5 w-32" />
        <Skeleton className="mt-2 h-7 w-3/4" />
        <Skeleton className="mt-2 h-4 w-1/2" />
        <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
        <div className="mt-5 flex flex-col gap-2 sm:flex-row">
          <Skeleton className="h-10 flex-1 sm:flex-none sm:w-40" />
          <Skeleton className="h-10 flex-1 sm:flex-none sm:w-32" />
        </div>
      </div>
      <div className="rounded-xl2 border border-line bg-ink-900 p-5 sm:p-6">
        <Skeleton className="h-5 w-48" />
        <Skeleton className="mt-3 h-4 w-full" />
        <Skeleton className="mt-2 h-4 w-5/6" />
      </div>
      <div className="rounded-xl2 border border-line bg-ink-900 p-5 sm:p-6">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="mt-3 h-32 w-full" />
      </div>
    </div>
  );
}

function BackButton({ onBack }: { onBack: () => void }) {
  return (
    <button
      type="button"
      onClick={onBack}
      className="inline-flex items-center gap-1.5 rounded-lg px-1 py-1 text-sm font-medium text-fog transition-colors hover:text-zinc-100"
    >
      <BackIcon size={16} />
      Back to Jobs
    </button>
  );
}

export default function JobDetailPage() {
  const params = useParams<{ jobId: string }>();
  const router = useRouter();
  const jobId = params.jobId;
  const [status, setStatus] = useState<DetailStatus>("loading");
  const [job, setJob] = useState<JobDetail | null>(null);
  const [application, setApplication] = useState<ApplicationItem | null>(null);
  const [appPending, setAppPending] = useState(false);
  const [appError, setAppError] = useState<string | null>(null);
  const { savedIds, pendingId, error: saveError, toggleSave } = useSavedJobs();
  const requestId = useRef(0);

  const load = useCallback(() => {
    if (!UUID_RE.test(jobId)) {
      setStatus("invalid");
      return;
    }
    const current = ++requestId.current;
    setStatus("loading");
    Promise.allSettled([
      getJob(jobId, DEFAULT_PROFILE_ID),
      getApplication(jobId, DEFAULT_PROFILE_ID),
    ]).then(([jobResult, appResult]) => {
      if (current !== requestId.current) return;
      if (jobResult.status === "rejected") {
        const apiStatus =
          typeof jobResult.reason === "object" &&
          jobResult.reason !== null &&
          "status" in jobResult.reason
            ? (jobResult.reason as { status: number }).status
            : 0;
        setStatus(apiStatus === 404 ? "not-found" : "error");
        return;
      }
      setJob(jobResult.value);
      // A missing tracker row is normal (not an error) — it means untracked.
      setApplication(appResult.status === "fulfilled" ? appResult.value : null);
      setAppError(null);
      setStatus("ready");
    });
  }, [jobId]);

  useEffect(() => {
    load();
  }, [load]);

  const goBack = useCallback(() => {
    if (typeof window !== "undefined" && window.history.length > 1) {
      router.back();
    } else {
      router.push("/jobs");
    }
  }, [router]);

  const handleMarkApplied = useCallback(() => {
    if (appPending) return;
    setAppPending(true);
    setAppError(null);
    createApplication({ job_id: jobId, status: "applied" }, DEFAULT_PROFILE_ID)
      .then((created) => {
        setApplication(created);
      })
      .catch(() => {
        setAppError("Couldn't track this application. Try again.");
      })
      .finally(() => {
        setAppPending(false);
      });
  }, [appPending, jobId]);

  return (
    <AppShell title="Job Details">
      <div className="mb-4">
        <BackButton onBack={goBack} />
      </div>

      {status === "loading" ? (
        <DetailSkeleton />
      ) : status === "ready" && job ? (
        <JobDetailView
          job={job}
          saved={savedIds.has(job.id)}
          savePending={pendingId === job.id}
          saveError={pendingId === job.id ? saveError : null}
          onToggleSave={() => toggleSave(job.id)}
          application={application}
          appPending={appPending}
          appError={appError}
          onMarkApplied={handleMarkApplied}
        />
      ) : status === "not-found" ? (
        <div className="flex flex-col items-center rounded-xl2 border border-line bg-ink-900 px-6 py-14 text-center">
          <h2 className="text-base font-semibold tracking-tight">Job not found</h2>
          <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-fog">
            This job may have been removed or is no longer available.
          </p>
          <Link
            href="/jobs"
            className="mt-5 inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
          >
            <BackIcon size={15} />
            Back to Jobs
          </Link>
        </div>
      ) : status === "invalid" ? (
        <div className="flex flex-col items-center rounded-xl2 border border-line bg-ink-900 px-6 py-14 text-center">
          <h2 className="text-base font-semibold tracking-tight">Invalid job link</h2>
          <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-fog">
            This link doesn&apos;t point to a valid job posting.
          </p>
          <Link
            href="/jobs"
            className="mt-5 inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
          >
            <BackIcon size={15} />
            Back to Jobs
          </Link>
        </div>
      ) : (
        <div
          role="alert"
          className="flex flex-col items-center rounded-xl2 border border-line bg-ink-900 px-6 py-14 text-center"
        >
          <h2 className="text-base font-semibold tracking-tight">Unable to load this job</h2>
          <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-fog">
            The AI-JobHunter API isn&apos;t responding right now.
          </p>
          <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
            <button
              type="button"
              onClick={load}
              className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
            >
              <RefreshIcon size={15} />
              Try Again
            </button>
            <Link
              href="/jobs"
              className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-ink-850 px-4 py-2 text-sm font-medium text-zinc-200 transition-colors hover:bg-ink-800"
            >
              <BackIcon size={15} />
              Back to Jobs
            </Link>
          </div>
        </div>
      )}
    </AppShell>
  );
}

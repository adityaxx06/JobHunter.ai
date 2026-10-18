// ApplicationStatusContext tests: single batched load, graceful degradation.
// fetch is stubbed per test — no backend, no network.
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApplicationStatusProvider,
  useApplicationStatus,
} from "./ApplicationStatusContext";

function wrapper({ children }: { children: React.ReactNode }) {
  return <ApplicationStatusProvider>{children}</ApplicationStatusProvider>;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ApplicationStatusProvider", () => {
  it("loads statuses once into a lookup map", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          profile_id: "p",
          items: [
            { job_id: "job-1", status: "applied" },
            { job_id: "job-2", status: "saved" },
          ],
          limit: 100,
          offset: 0,
          count: 2,
        }),
      })),
    );
    const { result } = renderHook(() => useApplicationStatus(), { wrapper });
    await waitFor(() => expect(result.current.statusByJobId.get("job-1")).toBe("applied"));
    expect(result.current.statusByJobId.get("job-2")).toBe("saved");
    expect(result.current.statusByJobId.get("missing")).toBeUndefined();
  });

  it("degrades to an empty map when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("down");
      }),
    );
    const { result } = renderHook(() => useApplicationStatus(), { wrapper });
    await waitFor(() =>
      expect(result.current.statusByJobId).toBeInstanceOf(Map),
    );
    expect(result.current.statusByJobId.size).toBe(0);
  });
});

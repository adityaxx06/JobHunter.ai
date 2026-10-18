// NeedsAttention derivation tests (pure function, no rendering).
import { describe, expect, it } from "vitest";
import { selectNeedsAttention } from "./NeedsAttention";
import type { RankedJob } from "@/types/job";

function job(jobId: string, recommendation: "APPLY" | "CONSIDER"): RankedJob {
  return {
    rank: 1,
    job_id: jobId,
    title: `Role ${jobId}`,
    company: "Acme",
    location: "Chennai",
    match_score: 90,
    trust_score: 90,
    recommendation,
    ranking_score: 91,
    strengths: [],
    missing_skills: [],
    reason: null,
    reasons: [],
    apply_url: null,
    salary_min: null,
    salary_max: null,
    salary_currency: null,
    is_remote: false,
    employment_type: null,
  };
}

describe("selectNeedsAttention", () => {
  it("surfaces APPLY jobs that are neither saved nor tracked", () => {
    const jobs = [job("a", "APPLY"), job("b", "CONSIDER"), job("c", "APPLY")];
    const result = selectNeedsAttention(jobs, new Set(["c"]), new Map());
    expect(result.map((entry) => entry.job_id)).toEqual(["a"]);
  });

  it("excludes terminal tracker statuses only", () => {
    const jobs = [job("a", "APPLY"), job("b", "APPLY"), job("c", "APPLY")];
    const statuses = new Map([
      ["a", "applied"],
      ["b", "saved"],
      ["c", "rejected"],
    ]);
    const result = selectNeedsAttention(jobs, new Set(), statuses);
    expect(result.map((entry) => entry.job_id)).toEqual(["b"]);
  });

  it("caps at the limit and renders empty cleanly", () => {
    const jobs = [job("a", "APPLY"), job("b", "APPLY"), job("c", "APPLY"), job("d", "APPLY")];
    expect(selectNeedsAttention(jobs, new Set(), new Map())).toHaveLength(3);
    expect(selectNeedsAttention([], new Set(), new Map())).toEqual([]);
    expect(selectNeedsAttention([job("a", "CONSIDER")], new Set(), new Map())).toEqual([]);
  });
});

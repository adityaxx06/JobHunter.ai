// Pure date-utility tests (no DOM, no network, deterministic).
import { describe, expect, it } from "vitest";
import { formatPostedDate, formatRelativeDate } from "./format";

function isoDaysAgo(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString();
}

describe("formatPostedDate", () => {
  it("formats valid dates and rejects null/invalid", () => {
    expect(formatPostedDate("2026-09-20T10:00:00Z")).toContain("2026");
    expect(formatPostedDate(null)).toBeNull();
    expect(formatPostedDate("")).toBeNull();
    expect(formatPostedDate("not-a-date")).toBeNull();
  });
});

describe("formatRelativeDate", () => {
  it("labels today/yesterday/recent days", () => {
    expect(formatRelativeDate(new Date().toISOString(), "Posted")).toBe("Posted today");
    expect(formatRelativeDate(isoDaysAgo(1), "Posted")).toBe("Posted yesterday");
    expect(formatRelativeDate(isoDaysAgo(3), "Posted")).toBe("Posted 3 days ago");
  });

  it("falls back to the calendar date for old postings", () => {
    const label = formatRelativeDate(isoDaysAgo(90), "Posted");
    expect(label).toContain("Posted");
    expect(label).not.toContain("days ago");
  });

  it("is null-safe for freshness display", () => {
    expect(formatRelativeDate(null, "Posted")).toBeNull();
    expect(formatRelativeDate("garbage", "Posted")).toBeNull();
  });
});

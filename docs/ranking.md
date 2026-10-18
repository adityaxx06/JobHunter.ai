# Job Ranking (Phase 5.3 — deterministic, zero AI)

## 1. Ranking architecture

Phase 5.2 intelligence is consumed, never recomputed:
`job_matches` (+ job/company context) → validate → optional filters → score →
deterministic sort → rank → top-N. Files: `worker/models/ranking.py`
(`RankedJob`, `RankingPipelineResult`), `worker/processors/ranking/scorer.py`
(formula + constants), `worker/db/ranking_repository.py` (one joined read),
`worker/pipelines/ranking_pipeline.py` (orchestration, reusable as
`rank_jobs_for_profile(...)` by Phase 5.4). Ranking is recomputed on demand;
nothing is persisted (the schema has no ranking column by design).

## 2. Scoring formula

```
base = match_score * 0.60 + trust_score * 0.25
final = base + recommendation_bonus + profile_preference (0-5)
        + skill_bonus (0-2) - trust_penalty
clamped to 0-100, rounded to 2 decimals
```

Example: Match 94, Trust 97, APPLY (+10), Role preference +4 (say exact role
2.5 + city 1.5 + internship 1.0 capped within the 5.0 budget) → high ranking:
`94*0.6 + 97*0.25 + 10 + 5 + skill bonus = ~95.65`.

## 3. Trust penalties

Trust bands (constants in `scorer.py`, not scattered): below 25 → severe −30;
25–49 → moderate −12; 50–69 → mild −4; 70+ → none. A 98-match/20-trust job
scores far below a 90-match/95-trust job by construction.

## 4. Recommendation priorities

APPLY +10 (highest), CONSIDER +5 (high), REVIEW +0 (medium/low),
AVOID −25 (lowest). AVOID stacks with the trust penalty, so avoided or
suspicious jobs sink without being deleted — the tracker may still show them.

## 5. Profile preference bonuses (budget 0–5, read from the DB profile)

- Role: exact target-role substring +2.5 (e.g. "java developer" in the title),
  related word overlap +1.0, else 0.
- Location: priority city or accepted-remote +1.5; India-wide/other known
  location +0.5 (relocation-compatible, never harshly penalized); empty 0.
- Employment: internship/full-time tokens +1.0 (fresher fit), else +0.5.
- Skills: +0.25 per matching skill, capped at +2.0 — alignment nudges but can
  never overpower a substantially better Match/Trust pair. Missing skills
  never subtract.

## 6. Tie-breaking (deterministic, no randomness, no insertion-order dependence)

Higher ranking score → higher match → higher trust → APPLY before CONSIDER
before REVIEW before AVOID → stronger role preference → stronger location
preference → lexicographic job ID. Re-running on the same inputs always
returns the same order.

## 7. Filtering (all optional, default = every valid analyzed job)

`min_match_score`, `min_trust_score`, `recommendation`, `employment_type`,
`location` (substring), `remote` (bool). Invalid rows (missing/bad scores,
unknown recommendation, missing job identity) are counted as excluded with an
error entry — never silently dropped.

## 8. Top-N behavior

`rank_jobs_for_profile(profile_id, limit=20)`: every valid candidate is
scored and sorted first; only then is the top-N slice taken. The database
query carries no LIMIT, so selection can never bias the ranking. Duplicate
canonical jobs (one row, many sources) rank exactly once.

## 9. Deterministic behavior

Pure functions, fixed constants, stable sort keys, string job IDs as the
final tie-break. Same inputs → same output, with zero network and zero
Gemini calls (architecturally enforced: ranking modules never import the AI
providers — covered by a test).

## 10. Example ranking

```
1. Java Developer Intern — 97.35 (match 96, trust 98, APPLY)
2. Backend Developer Intern — 94.20 (match 92, trust 95, APPLY)
3. Python Developer Intern — 83.40 (match 84, trust 97, CONSIDER)
```

## 11. Latest-feed eligibility (opt-in gate, scoring untouched)

`rank_jobs_for_profile(..., eligible_only=True)` (API: `GET
/api/rankings/{profile}?eligible_only=true`; dashboard uses it) counts — but
never ranks — rows failing the shared gate in
`worker/processors/ranking/eligibility.py`: publication age over
`LATEST_MAX_AGE_DAYS` (default 7, measured ONLY from `posted_at`; unknown or
future dates fail), non-India geography without a verifiable India/remote
opening (ambiguous locations stay unverified, never guessed), or deterministic
prefilter rejection. Formula, weights, and tie-breaks are identical; default
`eligible_only=False` behavior is byte-for-byte unchanged. Rediscovery is
safe by construction: `posted_at` is not a mutable persistence column, so a
re-seen job keeps its original publication date forever.

"""Phase 5.3 ranking tests part 1: scorer math, trust, preferences, skills."""

import pytest

from worker.models.ranking import RankedJob, RankingFilter
from worker.processors.ranking.scorer import (
    calculate_ranking_score,
    employment_preference,
    location_preference,
    role_preference,
    skill_bonus,
    sort_key,
    trust_penalty,
)

ROLES = ["Java Developer", "Backend Developer", "Software Engineer"]
LOCS = ["Chennai", "Bangalore", "India", "Remote"]


# --- basic scoring 1-7 ----------------------------------------------------------


def test_high_match_high_trust_ranks_high():
    score, _, _ = calculate_ranking_score(96, 98, "APPLY")
    assert score == round(96 * 0.60 + 98 * 0.25 + 10, 2) == 92.1


def test_high_match_low_trust_penalized():
    high_trust, _, _ = calculate_ranking_score(90, 95, "CONSIDER")
    low_trust, _, _ = calculate_ranking_score(95, 60, "CONSIDER")
    assert low_trust < high_trust  # 95-match cannot ride skill fit past trust


def test_moderate_match_high_trust_sensible():
    score, _, _ = calculate_ranking_score(75, 95, "CONSIDER")
    assert score == round(75 * 0.60 + 95 * 0.25 + 5, 2) == 73.75


def test_low_match_does_not_rank_highly():
    score, _, _ = calculate_ranking_score(40, 90, "CONSIDER")
    assert score < 60


def test_apply_outranks_consider():
    apply, _, _ = calculate_ranking_score(80, 80, "APPLY")
    consider, _, _ = calculate_ranking_score(80, 80, "CONSIDER")
    assert (apply, consider) == (78.0, 73.0)


def test_consider_outranks_review():
    consider, _, _ = calculate_ranking_score(70, 70, "CONSIDER")
    review, _, _ = calculate_ranking_score(70, 70, "REVIEW")
    assert consider > review


def test_review_outranks_avoid():
    review, _, _ = calculate_ranking_score(70, 70, "REVIEW")
    avoid, _, _ = calculate_ranking_score(70, 70, "AVOID")
    assert review > avoid and avoid == round(70 * 0.60 + 70 * 0.25 - 25, 2)


# --- trust bands 8-12 --------------------------------------------------------------


def test_trust_below_25_severe():
    penalty, reason = trust_penalty(20)
    assert penalty == 30.0 and reason is not None
    score, reasons, _ = calculate_ranking_score(90, 20, "REVIEW")
    assert score == round(90 * 0.60 + 20 * 0.25 - 30, 2) == 29.0
    assert any("severe" in r for r in reasons)


def test_trust_25_to_49_moderate():
    assert trust_penalty(25)[0] == 12.0
    assert trust_penalty(49)[0] == 12.0


def test_trust_50_to_69_mild():
    assert trust_penalty(50)[0] == 4.0
    assert trust_penalty(69)[0] == 4.0


def test_trust_70_plus_normal():
    assert trust_penalty(70) == (0.0, None)
    assert trust_penalty(100) == (0.0, None)


def test_high_match_trust_10_never_top():
    suspect, _, _ = calculate_ranking_score(95, 10, "APPLY", preference=5.0, skills_bonus=2.0)
    honest, _, _ = calculate_ranking_score(90, 95, "CONSIDER")
    assert suspect < honest  # 39.5 + extras still lose to 82.75


# --- preferences 13-18 -----------------------------------------------------------------


def test_exact_target_role_preferred():
    bonus, reason = role_preference("Senior Java Developer", ROLES)
    assert bonus == 2.5 and "java developer" in reason.lower()


def test_related_role_smaller_preference():
    bonus, _ = role_preference("Java Programmer", ROLES)
    assert bonus == 1.0
    assert role_preference("Accountant", ROLES)[0] == 0.0


def test_priority_city_preferred():
    bonus, reason = location_preference("Chennai, India", False, LOCS, True)
    assert bonus == 1.5 and reason == "priority location"


def test_remote_positive_when_accepted():
    assert location_preference("Remote", True, LOCS, True) == (1.5, "remote-friendly")
    assert location_preference("", True, LOCS, True) == (1.5, "remote-friendly")
    assert location_preference("Remote", True, LOCS, False)[0] == 0.5  # not punished hard


def test_india_wide_eligible_and_relocation_compatible():
    assert location_preference("India", False, LOCS, True) == (1.5 - 1.0, "india-wide eligible")
    bonus, reason = location_preference("Kochi, Kerala", False, LOCS, True)
    assert bonus == 0.5 and reason == "relocation-compatible"
    assert location_preference("", False, LOCS, True) == (0.0, None)


def test_employment_preference():
    assert employment_preference("Internship")[0] == 1.0
    assert employment_preference("Full-Time")[0] == 1.0
    assert employment_preference("Contract")[0] == 0.5


# --- skills 19-21 -----------------------------------------------------------------------------


def test_matching_skills_small_bonus():
    assert skill_bonus(["Java", "SQL"]) == (0.5, "2 matching skill(s)")
    assert skill_bonus([]) == (0.0, None)
    assert skill_bonus([f"s{i}" for i in range(20)])[0] == 2.0  # capped


def test_missing_skills_do_not_eliminate():
    score, _, _ = calculate_ranking_score(85, 90, "CONSIDER", preference=3.0, skills_bonus=0.0)
    assert score == round(85 * 0.60 + 90 * 0.25 + 5 + 3.0, 2) == 81.5


def test_skill_count_cannot_overpower_match_trust():
    strong, _, _ = calculate_ranking_score(95, 97, "APPLY", skills_bonus=skill_bonus(["a", "b", "c", "d"])[0])
    weak, _, _ = calculate_ranking_score(90, 96, "APPLY", skills_bonus=skill_bonus([f"s{i}" for i in range(9)])[0])
    assert strong > weak  # 92.25 vs 90.0


# --- recommendation 22-24 ------------------------------------------------------------------------------


def test_avoid_strong_penalty():
    score, reasons, _ = calculate_ranking_score(80, 80, "AVOID")
    assert score == round(80 * 0.60 + 80 * 0.25 - 25, 2) == 43.0
    assert any("AVOID" in r for r in reasons)


def test_avoid_plus_low_trust_near_bottom():
    score, _, _ = calculate_ranking_score(80, 10, "AVOID")
    assert score == 0.0  # 48 + 2.5 - 25 - 30 clamps to the bottom


def test_apply_high_trust_near_top():
    score, _, _ = calculate_ranking_score(94, 97, "APPLY", preference=4.0)
    assert score == round(94 * 0.60 + 97 * 0.25 + 10 + 4.0, 2) == 94.65


# --- invalid inputs rejected, never defaulted ---------------------------------------------------------------


def test_invalid_scores_and_recommendations_rejected():
    with pytest.raises(ValueError):
        calculate_ranking_score(101, 90, "APPLY")
    with pytest.raises(ValueError):
        calculate_ranking_score(90, -1, "APPLY")
    with pytest.raises(ValueError):
        calculate_ranking_score(True, 90, "APPLY")
    with pytest.raises(ValueError):
        calculate_ranking_score(90, 90, "STRONG_APPLY")


# --- sorting 25-29 (sort_key unit level) ----------------------------------------------------------------------------


def _entry(score, match, trust, rec, role=0.0, loc=0.0, job_id="j1"):
    return {"ranking_score": score, "match_score": match, "trust_score": trust,
            "recommendation": rec, "role_score": role, "location_score": loc, "job_id": job_id}


def test_higher_score_first_and_match_tiebreak():
    ordered = sorted([_entry(80.0, 70, 90, "CONSIDER", job_id="b"),
                      _entry(90.0, 90, 90, "CONSIDER", job_id="a"),
                      _entry(80.0, 85, 70, "CONSIDER", job_id="c")], key=sort_key)
    assert [e["job_id"] for e in ordered] == ["a", "c", "b"]


def test_trust_then_recommendation_tiebreak():
    ordered = sorted([_entry(80.0, 80, 70, "APPLY", job_id="b"),
                      _entry(80.0, 80, 90, "CONSIDER", job_id="a"),
                      _entry(80.0, 80, 90, "APPLY", job_id="c")], key=sort_key)
    assert [e["job_id"] for e in ordered] == ["c", "a", "b"]


def test_role_location_then_job_id_tiebreak():
    ordered = sorted([_entry(80.0, 80, 80, "APPLY", role=1.0, loc=0.0, job_id="b"),
                      _entry(80.0, 80, 80, "APPLY", role=2.5, loc=1.5, job_id="a"),
                      _entry(80.0, 80, 80, "APPLY", role=2.5, loc=1.5, job_id="c")], key=sort_key)
    assert [e["job_id"] for e in ordered] == ["a", "c", "b"]


def test_ranked_job_model_defaults():
    ranked = RankedJob(job_id="j1")
    assert ranked.rank == 0 and ranked.priority_reasons == []
    assert isinstance(RankingFilter().min_match_score, type(None))

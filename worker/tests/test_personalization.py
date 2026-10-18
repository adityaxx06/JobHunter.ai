"""Phase 7C personalization tests. Fully offline — no Tavily/Gemini/ATS/DB.

Covers: skill synonym normalization (unit + prefilter overlap), owned vs
learning skill terms in tier-2 (bounded, skip-if-in-role), experience-aware
query terms (fresher vs senior), and freshness sort wiring.
"""

from worker.processors.intelligence.prefilter import _skill_overlap
from worker.search.query_generator import (
    SearchProfile,
    generate_queries,
    is_fresher_profile,
)
from worker.utils.skill_synonyms import canonical_skill, skills_match


def _profile(**overrides):
    base = {
        "roles": ["Software Engineer"],
        "skills": [],
        "learning_skills": [],
        "locations": ["India"],
        "remote_ok": True,
        "experience_level": "Fresher",
    }
    base.update(overrides)
    return SearchProfile(**base)


# --- skill normalization -----------------------------------------------------------------


def test_canonical_skill_aliases():
    assert canonical_skill("JS") == "javascript"
    assert canonical_skill("TypeScript") == "typescript"
    assert canonical_skill("  Postgres  ") == "postgresql"
    assert canonical_skill("ReactJS") == "react"
    assert canonical_skill("") == "" and canonical_skill(None) == ""
    assert skills_match("JS", "JavaScript") is True
    assert skills_match("java", "JAVA") is True


def test_synonyms_never_overmerge():
    assert skills_match("Java", "JavaScript") is False
    assert skills_match("JavaScript", "Java") is False
    assert skills_match("React", "React Native") is False
    assert skills_match("C", "react") is False
    assert skills_match("", "Java") is False


def test_prefilter_overlap_uses_aliases():
    job = {"title": "Frontend Developer", "description": "JavaScript and advocacy.", "skills": []}
    assert _skill_overlap(["JS"], job) == ["JS"]
    assert _skill_overlap(["C"], {"title": "React dev", "description": "", "skills": []}) == []
    job_lists = {"title": "Dev", "description": "", "skills": ["TypeScript"]}
    assert _skill_overlap(["TS"], job_lists) == ["TS"]


# --- skill-aware tier-2 ----------------------------------------------------------------------


def test_owned_skill_term_used_when_absent_from_role():
    queries = [q.query for q in generate_queries(
        _profile(roles=["Software Engineer"], skills=["Python"]), max_queries=10)]
    assert any(q == '"Software Engineer Python" India' for q in queries)


def test_skill_skipped_when_already_in_role():
    queries = [q.query for q in generate_queries(
        _profile(roles=["Java Backend Intern"], skills=["Java"]), max_queries=10)]
    assert any("Java Backend Intern" in q and "Chennai" not in q for q in queries)
    assert not any("Java Backend Intern Java" in q for q in queries)


def test_learning_skill_is_secondary_signal():
    queries = [q.query for q in generate_queries(
        _profile(roles=["Software Engineer", "Backend Developer"],
                 skills=["Python"], learning_skills=["Go"]), max_queries=30)]
    assert any('"Software Engineer Python"' in q for q in queries)
    assert any('"Backend Developer Go"' in q for q in queries)


def test_skill_terms_bounded_to_first_roles():
    roles = ["Role A", "Role B", "Role C"]
    queries = [q.query for q in generate_queries(
        _profile(roles=roles, skills=["Python", "Go", "Rust"]), max_queries=30)]
    assert any('"Role A Python"' in q for q in queries)
    assert any('"Role B Go"' in q for q in queries)
    assert not any("Rust" in q for q in queries)  # cap: first two roles only


def test_empty_skills_keep_fresher_terms():
    queries = [q.query for q in generate_queries(_profile(), max_queries=10)]
    assert any("intern" in q for q in queries)


# --- experience-aware terms ---------------------------------------------------------------------


def test_is_fresher_profile_cases():
    assert is_fresher_profile("Fresher") is True
    assert is_fresher_profile("Fresher / Student") is True
    assert is_fresher_profile("") is True
    assert is_fresher_profile(None) is True
    assert is_fresher_profile("Unknown") is True
    assert is_fresher_profile("Senior Engineer") is False
    assert is_fresher_profile("5+ years experience") is False
    assert is_fresher_profile("Engineering Manager") is False


def test_senior_profile_has_no_intern_terms():
    queries = [q.query for q in generate_queries(
        _profile(roles=["Backend Developer"], experience_level="Senior Engineer"), max_queries=30)]
    assert queries  # still generates
    without_hosts = [q.lower().replace("internshala", "") for q in queries]
    assert not any("intern" in q for q in without_hosts)
    assert any(q == '"Backend Developer" India' for q in queries)
    assert any(q == '"Backend Developer" remote' for q in queries)


def test_fresher_profile_unchanged():
    queries = [q.query for q in generate_queries(_profile(), max_queries=5)]
    assert queries[0] == '"Software Engineer intern" India'
    assert any("intern" in q for q in queries)


# --- Phase 10A: widened Tier-4 coverage (3 roles x 2 locations, same budget) ---


def _three_by_two_profile():
    return SearchProfile(
        roles=["Alpha Developer", "Beta Engineer", "Gamma Coder"],
        skills=[],
        learning_skills=[],
        locations=["Chennai", "Bangalore", "India"],
        remote_ok=True,
        experience_level="Fresher",
    )


def test_site_queries_cover_three_roles_two_locations():
    from worker.search.query_generator import JOB_BOARD_HINTS, SITE_HINTS

    queries = [q for q in generate_queries(_three_by_two_profile(), max_queries=30) if q.site_hint]
    assert len(queries) == 6
    assert [q.site_hint for q in queries] == list(JOB_BOARD_HINTS) + list(SITE_HINTS)
    assert {q.role for q in queries} == {"Alpha Developer", "Beta Engineer", "Gamma Coder"}
    text = " ".join(q.query for q in queries)
    assert "Chennai" in text and "Bangalore" in text
    assert len({q.query for q in queries}) == 6  # no duplicates


def test_site_budget_unchanged_at_default_profile():
    queries = generate_queries(SearchProfile(), max_queries=30)
    site = [q for q in queries if q.site_hint]
    assert len(site) == 6
    assert len(queries) <= 30
    assert any("remote" in q.location for q in queries)  # remote tier survives


def test_single_role_profile_still_covers_all_hosts():
    from worker.search.query_generator import JOB_BOARD_HINTS, SITE_HINTS

    profile = SearchProfile(roles=["Solo Developer"], locations=["Chennai"])
    hints = [q.site_hint for q in generate_queries(profile, max_queries=30) if q.site_hint]
    assert set(hints) == set(JOB_BOARD_HINTS) | set(SITE_HINTS)


def test_tight_budgets_keep_source_priority():
    five = [q.query for q in generate_queries(SearchProfile(), max_queries=5)]
    assert any("linkedin.com" in q for q in five)
    assert any("internshala.com" in q for q in five)

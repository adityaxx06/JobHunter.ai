"""Latest-feed eligibility tests (fixed clock — deterministic, fully offline)."""

from datetime import datetime, timedelta, timezone

from worker.processors.ranking import eligibility as gate
from worker.processors.ranking.eligibility import (
    assess_job,
    build_job_view,
    check_freshness,
    check_geography,
    check_role,
)

NOW = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)

CANDIDATE = {
    "profile_id": "prof-1",
    "education": "MCA",
    "status": "Fresher",
    "skills": ["Java", "Python", "SQL"],
    "learning": [],
    "target_roles": ["Java Developer", "Backend Developer"],
    "target_locations": ["Chennai", "Bangalore", "India", "Remote"],
    "locations": ["Chennai", "Bangalore", "India", "Remote"],
    "remote_ok": True,
    "relocation_ok": True,
}


def _view(**overrides):
    base = {
        "job_id": "job-1",
        "title": "Java Developer Intern",
        "company_name": "Example",
        "description": "6-month Java internship in Chennai. Freshers welcome.",
        "location": "Chennai, India",
        "employment_type": "Internship",
        "experience_level": "Fresher",
        "skills": ["Java", "SQL"],
        "apply_url": "https://example.com/jobs/1",
        "source_types": [],
        "is_remote": False,
        "posted_at": NOW - timedelta(days=1),
    }
    base.update(overrides)
    return base


# --- config -----------------------------------------------------------------------------------


def test_eligibility_config_defaults_and_clamps():
    assert gate.get_max_age_days({}) == 7
    assert gate.get_max_age_days({"LATEST_MAX_AGE_DAYS": "3"}) == 3
    assert gate.get_max_age_days({"LATEST_MAX_AGE_DAYS": "999"}) == 90
    assert gate.get_max_age_days({"LATEST_MAX_AGE_DAYS": "bogus"}) == 7
    assert gate.get_target_country({}) == "India"
    assert gate.get_target_country({"LATEST_COUNTRY": "  "}) == "India"


# --- freshness -------------------------------------------------------------------------------------


def test_freshness_boundaries_with_fixed_clock():
    assert check_freshness(NOW - timedelta(days=1), NOW, 7)[0] is True
    assert check_freshness(NOW - timedelta(days=7), NOW, 7)[0] is True
    for days in (8, 30, 90, 150):
        ok, reason = check_freshness(NOW - timedelta(days=days), NOW, 7)
        assert ok is False and "older than 7" in reason, days


def test_freshness_missing_invalid_and_future():
    assert check_freshness(None, NOW, 7) == (False, "unknown publication date")
    assert check_freshness("not-a-date", NOW, 7)[0] is False
    assert check_freshness(12345, NOW, 7)[0] is False
    ok, reason = check_freshness(NOW + timedelta(days=5), NOW, 7)
    assert ok is False and "future" in reason
    # Tolerated clock skew stays fresh; naive datetimes assume UTC.
    assert check_freshness(NOW + timedelta(hours=12), NOW, 7)[0] is True
    assert check_freshness(NOW.replace(tzinfo=None), NOW, 7)[0] is True
    assert check_freshness("2026-10-09T10:00:00Z", NOW, 7)[0] is True


# --- geography --------------------------------------------------------------------------------------


def test_geography_india_and_remote_india_eligible():
    assert check_geography("Chennai, India", False) == ("eligible", "India-based opportunity")
    assert check_geography("Remote India", True) == ("eligible", "India-based opportunity")
    assert check_geography("Bangalore", False)[0] == "eligible"


def test_geography_foreign_excluded():
    for location, remote in [("Chicago", False), ("London", False),
                             ("Remote US", True), ("Montreal", False),
                             ("Remote US (Maryland)", True)]:
        verdict, _ = check_geography(location, remote)
        assert verdict == "excluded", (location, remote)


def test_geography_ambiguous_stays_unverified():
    for location, remote in [("", False), ("Springfield", False),
                             ("Remote", True), (None, False)]:
        verdict, _ = check_geography(location, remote)
        assert verdict == "unverified", (location, remote)
    assert check_geography("Anywhere", True) == ("eligible", "worldwide remote")


# --- role (shared prefilter) ------------------------------------------------------------------------------


def test_role_gate_uses_prefilter():
    ok, _ = check_role(_view(), CANDIDATE)
    assert ok is True
    ok, _ = check_role(_view(title="Senior Software Engineer"), CANDIDATE)
    assert ok is False
    ok, _ = check_role(_view(title="Accountant"), CANDIDATE)
    assert ok is False


# --- combined assessment ---------------------------------------------------------------------------------------


def test_assess_eligible_and_unverified_flags():
    good = assess_job(_view(), CANDIDATE, NOW)
    assert good.eligible is True and good.unverified is False
    stale = assess_job(_view(posted_at=NOW - timedelta(days=30)), CANDIDATE, NOW)
    assert stale.eligible is False and stale.unverified is False
    undated = assess_job(_view(posted_at=None), CANDIDATE, NOW)
    assert undated.eligible is False and undated.unverified is True
    foreign = assess_job(_view(location="Chicago", posted_at=NOW - timedelta(days=1)),
                         CANDIDATE, NOW)
    assert foreign.eligible is False
    assert assess_job({}, {}, NOW).eligible is False  # never raises, never eligible


def test_rediscovered_stale_job_never_looks_new():
    # A stale original date stays stale no matter when it is re-seen.
    old = NOW - timedelta(days=90)
    assert assess_job(_view(posted_at=old), CANDIDATE, NOW).eligible is False
    assert assess_job(_view(posted_at=old), CANDIDATE,
                      NOW + timedelta(days=365)).eligible is False


def test_refresh_never_touches_posted_at():
    from worker.db.job_repository import _incoming_values
    from worker.models.job import DiscoveredJob, NormalizedJob

    norm = NormalizedJob(original=DiscoveredJob(title="T"))
    assert "posted_at" not in _incoming_values(norm)
    assert "first_seen_at" not in _incoming_values(norm)
    assert "last_seen_at" not in _incoming_values(norm)


# --- ranking pipeline eligible_only -----------------------------------------------------------------


def test_eligible_only_filters_pipeline(monkeypatch):
    from datetime import datetime as _dt

    from worker.pipelines import ranking_pipeline as ranking
    from worker.tests.test_ranking_pipeline import FakeDB as RankingFakeDB
    from worker.tests.test_ranking_pipeline import _install, _match_row

    now = _dt.now(timezone.utc)
    fresh = _match_row("job-1", posted_at=now - timedelta(days=1),
                       description="Java internship in Chennai. Freshers welcome.")
    stale = _match_row("job-2", posted_at=now - timedelta(days=30),
                       description="Java internship.")
    foreign = _match_row("job-3", posted_at=now - timedelta(days=1),
                         location="Chicago", description="Java internship.")
    undated = _match_row("job-4", description="Java internship.")
    fake = RankingFakeDB(rows=[fresh, stale, foreign, undated])
    _install(monkeypatch, fake)
    result = ranking.rank_jobs_for_profile(limit=20, eligible_only=True)
    assert [j.job_id for j in result.ranked_jobs] == ["job-1"]
    assert result.ineligible_count == 3
    assert result.ranking_errors == []


def test_default_ranking_path_ignores_eligibility(monkeypatch):
    from worker.pipelines import ranking_pipeline as ranking
    from worker.tests.test_ranking_pipeline import FakeDB as RankingFakeDB
    from worker.tests.test_ranking_pipeline import _install, _match_row

    fake = RankingFakeDB(rows=[_match_row("job-1"), _match_row("job-2")])
    _install(monkeypatch, fake)
    result = ranking.rank_jobs_for_profile(limit=20)
    assert result.jobs_ranked == 2 and result.ineligible_count == 0

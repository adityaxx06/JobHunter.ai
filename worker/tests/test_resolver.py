"""Phase 6.1 resolver tests. Fully offline — parse-only, never any network."""

import pytest

from worker.models.search import DiscoveryTarget
from worker.sources import resolver
from worker.sources.resolver import (
    ResolvedSource,
    normalize_url,
    resolve_target,
    resolve_targets,
    resolve_url,
)


# --- greenhouse -----------------------------------------------------------------


def test_greenhouse_boards_job_url():
    verdict = resolve_url("https://boards.greenhouse.io/acme/jobs/12345")
    assert verdict.source_type == "greenhouse"
    assert verdict.identifier == "acme"
    assert verdict.is_ats is True and verdict.confidence == "high"


def test_greenhouse_job_boards_host():
    # The project's own Greenhouse parser treats job-boards.greenhouse.io
    # as canonical — the resolver must recognize it too.
    verdict = resolve_url("https://job-boards.greenhouse.io/acme/jobs/77?gh_src=abc")
    assert (verdict.source_type, verdict.identifier) == ("greenhouse", "acme")
    assert verdict.is_ats is True


def test_greenhouse_bare_board_url():
    assert resolve_url("https://boards.greenhouse.io/acme").identifier == "acme"


# --- lever / ashby -------------------------------------------------------------------


def test_lever_company_url():
    verdict = resolve_url("https://jobs.lever.co/exampletech/abc-123")
    assert (verdict.source_type, verdict.identifier, verdict.confidence) == ("lever", "exampletech", "high")
    assert verdict.is_ats is True


def test_ashby_board_url():
    verdict = resolve_url("https://jobs.ashbyhq.com/acme/def-456#about")
    assert (verdict.source_type, verdict.identifier) == ("ashby", "acme")
    assert verdict.is_ats is True


# --- unresolved ---------------------------------------------------------------------------


def test_unknown_and_career_stay_unresolved():
    career = resolve_url("https://example.com/careers/backend-dev")
    assert career.source_type == "company_career" and career.is_ats is False
    assert career.identifier == "" and career.confidence == ""
    unknown = resolve_url("https://example.com/blog/internships")
    assert unknown.source_type == "unknown" and unknown.is_ats is False


def test_malformed_urls_unresolved():
    for bad in ("", None, 12345, "not a url", "ftp://boards.greenhouse.io/acme", "https://", "http:///"):
        verdict = resolve_url(bad)
        assert verdict.source_type == "unknown" and verdict.is_ats is False


def test_ats_host_without_handle_unresolved():
    for bad in ("https://boards.greenhouse.io/", "https://jobs.lever.co", "https://jobs.ashbyhq.com///"):
        verdict = resolve_url(bad)
        assert verdict.is_ats is False and verdict.identifier == ""


# --- false positives -----------------------------------------------------------------------------


def test_false_positives_rejected():
    # A path that mentions an ATS is NOT ATS infrastructure.
    assert resolve_url("https://example.com/careers/greenhouse").is_ats is False
    assert resolve_url("https://example.com/greenhouse-jobs").is_ats is False
    assert resolve_url("https://example.com/jobs/lever-board").is_ats is False
    # Lookalike hosts are NOT the ATS.
    assert resolve_url("https://greenhouse.example.com/acme").is_ats is False
    assert resolve_url("https://boards.greenhouse.io.evil.com/acme").is_ats is False
    assert resolve_url("https://evil-boards.greenhouse.io/acme").is_ats is False
    assert resolve_url("https://jobs.lever.co.evil.com/acme").is_ats is False


# --- normalization --------------------------------------------------------------------------------------


def test_normalization_case_fragment_tracking():
    verdict = resolve_url("HTTPS://Boards.Greenhouse.IO/Acme/Jobs/1?utm_source=x&gh_jid=9#top")
    assert verdict.source_type == "greenhouse" and verdict.identifier == "acme"
    assert "utm_source" not in verdict.original_url and "#top" not in verdict.original_url
    assert "gh_jid=9" in verdict.original_url  # meaningful params preserved
    assert normalize_url("https://boards.greenhouse.io/acme/") == "https://boards.greenhouse.io/acme"
    assert normalize_url("") == "" and normalize_url(None) == ""


def test_credentials_never_survive_normalization():
    cleaned = normalize_url("https://user:secret@boards.greenhouse.io/acme")
    assert "secret" not in cleaned and "user" not in cleaned
    assert resolve_url("https://user:secret@boards.greenhouse.io/acme").identifier == "acme"


# --- target interface --------------------------------------------------------------------------------------


def test_resolve_target_and_batch():
    target = DiscoveryTarget(
        url="https://jobs.lever.co/acme/1", classified_source="lever", title="t", snippet="s"
    )
    verdict = resolve_target(target)
    assert isinstance(verdict, ResolvedSource)
    assert (verdict.source_type, verdict.identifier) == ("lever", "acme")
    batch = resolve_targets([target, DiscoveryTarget(url="junk"), None, "https://jobs.ashbyhq.com/z/1"])
    assert [b.source_type for b in batch] == ["lever", "unknown", "unknown", "ashby"]

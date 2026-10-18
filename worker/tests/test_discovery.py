"""Phase 4.1 discovery-framework tests. Fully offline (mock source only)."""

import os
import sys

import pytest

from worker.models.job import DiscoveredJob, NormalizedJob
from worker.pipelines.discovery_pipeline import run_discovery
from worker.processors.deduplicator.job_deduplicator import deduplicate_jobs
from worker.processors.normalizer import job_normalizer as norm
from worker.processors.normalizer.job_normalizer import normalize_job
from worker.sources import registry
from worker.sources.base import JobSource
from worker.sources.manual.mock_source import MockSource
from worker.utils import job_fingerprint as worker_fp


@pytest.fixture
def saved_registry():
    """Snapshot + restore the global registry around mutating tests."""
    snapshot = registry.get_all_sources()
    yield
    registry.clear_sources()
    for source in snapshot:
        registry.register_source(source)


def _job(**overrides):
    base = {
        "external_id": "t-1",
        "title": "Java Developer Intern",
        "company_name": "Example Technologies",
        "company_domain": "example.com",
        "location": "Chennai, Tamil Nadu, India",
        "employment_type": "Internship",
        "skills": ["Java", "SQL"],
        "source_type": "manual",
        "source_name": "mock",
        "source_url": "mock://manual/test-feed",
        "apply_url": "https://example.com/jobs/t-1",
    }
    base.update(overrides)
    return DiscoveredJob(**base)


# --- canonical model --------------------------------------------------------


def test_job_model_defaults():
    job = DiscoveredJob(title="AI/ML Intern")
    assert job.title == "AI/ML Intern"
    assert job.skills == [] and job.locations == [] and job.raw_data == {}
    assert job.discovered_at is not None  # auto timestamp
    other = DiscoveredJob()
    assert other.skills is not job.skills  # no shared mutable defaults
    assert job.salary_currency == "INR"


# --- normalization ----------------------------------------------------------


def test_normalize_title_variants():
    assert norm.normalize_title("Software Engineer Intern") == "software engineer intern"
    assert norm.normalize_title("Java Developer - Internship") == "java developer internship"
    assert norm.normalize_title("  Backend_Developer (Hiring)  ") == "backend developer"
    # Meaning preserved: tech tokens survive.
    assert "c++" in norm.normalize_title("C++ Developer Intern")
    assert norm.normalize_title("") == ""


def test_normalize_company_and_location():
    assert norm.normalize_company_name("Example Technologies Pvt. Ltd.") == "example"
    assert norm.normalize_company_name("", domain="AcmeCorp.io") == "acmecorp.io"
    assert norm.normalize_location("Chennai, Tamil Nadu, India") == "chennai, tamil nadu, india"
    assert norm.primary_location("chennai, tamil nadu, india") == "chennai"


def test_normalize_employment_and_skills():
    assert norm.normalize_employment_type("Full-Time") == "full_time"
    assert norm.normalize_employment_type("INTERNSHIP") == "internship"
    assert norm.normalize_skills(["Java", " java ", "SQL", "", "SQL"]) == ["java", "sql"]
    assert norm.normalize_skills("not-a-list") == []


def test_normalize_job_keeps_original_and_remote():
    job = _job(location="Remote, India")
    out = normalize_job(job)
    assert isinstance(out, NormalizedJob)
    assert out.original is job  # original preserved
    assert out.normalized_title == "java developer intern"
    assert out.is_remote is True
    assert len(out.fingerprint) == 64


# --- fingerprinting ---------------------------------------------------------


def test_worker_fingerprint_deterministic():
    fp1 = worker_fp.build_fingerprint("Example", "Java Developer Intern", "Chennai", "https://example.com/j/1")
    fp2 = worker_fp.build_fingerprint("  EXAMPLE ", "java  developer intern", " chennai ", "https://example.com/j/1/")
    assert fp1 == fp2
    assert worker_fp.build_fingerprint("A", "X", "L") != worker_fp.build_fingerprint("A", "Y", "L")


def test_fingerprint_parity_with_backend():
    """Worker and backend implementations must never conflict (same digests)."""
    backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend")
    sys.path.insert(0, os.path.normpath(backend_dir))
    try:
        from app.utils import job_fingerprint as backend_fp
    finally:
        sys.path.remove(os.path.normpath(backend_dir))
    fixtures = [
        ("Example", "Java Developer Intern", "Chennai", "https://example.com/j/1", ""),
        ("", "", "", "", ""),
        ("Acme", "C++ Engineer", "Remote, India", "", "https://acme.example/careers/9/"),
    ]
    for company, title, location, apply_url, canonical_url in fixtures:
        assert worker_fp.build_fingerprint(company, title, location, apply_url, canonical_url) == backend_fp.build_fingerprint(
            company, title, location, apply_url, canonical_url
        )


# --- deduplication ----------------------------------------------------------


def test_dedupe_exact_and_variant_duplicates():
    jobs = [normalize_job(_job()), normalize_job(_job())]  # exact dup
    variant = _job(title="  JAVA developer - Intern ", apply_url="https://example.com/jobs/T-1/")
    jobs.append(normalize_job(variant))  # same fingerprint modulo normalization
    jobs.append(normalize_job(_job(external_id="t-2", title="Python Developer Intern", apply_url="https://example.com/jobs/t-2")))
    result = deduplicate_jobs(jobs)
    assert len(result.unique_jobs) == 2
    assert result.duplicate_count == 2
    assert len(result.duplicates) == 2


def test_dedupe_same_apply_url_counts_as_duplicate():
    jobs = [
        normalize_job(_job(title="Java Developer Intern", location="Chennai")),
        normalize_job(_job(title="Java Developer", location="Chennai, India")),  # different fp, same URL
    ]
    result = deduplicate_jobs(jobs)
    assert len(result.unique_jobs) == 1 and result.duplicate_count == 1


# --- registry ---------------------------------------------------------------


def test_registry_register_get_and_list(saved_registry):
    registry.clear_sources()
    mock = MockSource()
    registry.register_source(mock)
    assert registry.get_source("mock") is mock
    assert registry.get_source("nope") is None
    assert registry.get_all_sources() == [mock]
    assert registry.get_sources_by_type("manual") == [mock]
    assert registry.get_sources_by_type("greenhouse") == []


# --- mock source ------------------------------------------------------------


def test_mock_source_returns_five_flagged_jobs():
    jobs = MockSource().discover_jobs()
    assert len(jobs) == 5
    titles = {j.title for j in jobs}
    assert {"Java Developer Intern", "Backend Developer Intern", "Software Engineer Intern", "Python Developer Intern", "AI/ML Intern"} <= titles
    for job in jobs:
        assert job.source_type == "manual" and job.source_name == "mock"
        assert job.raw_data.get("mock") is True
        assert "MOCK" in job.description
        assert job.apply_url.startswith("https://example.com/")
    assert MockSource().health_check().ok is True


def test_mock_source_filters_and_limit():
    assert len(MockSource().discover_jobs(query="python")) == 1
    assert len(MockSource().discover_jobs(location="remote")) == 2
    assert len(MockSource().discover_jobs(limit=2)) == 2


# --- pipeline ---------------------------------------------------------------


def test_pipeline_counts_with_mock():
    result = run_discovery([MockSource()])
    assert result.discovered_count == 5
    assert result.normalized_count == 5
    assert result.unique_count == 5
    assert len(result.jobs) == 5
    assert result.source_stats[0].status == "ok"
    assert result.summary() == {"sources": 1, "discovered": 5, "normalized": 5, "unique": 5, "errors": 0}


class _BrokenSource(JobSource):
    source_type = "greenhouse"
    source_name = "broken-board"

    def discover_jobs(self, query="", location="", limit=50):
        raise RuntimeError("simulated outage")


def test_pipeline_isolates_source_failure():
    result = run_discovery([_BrokenSource(), MockSource()])
    assert result.discovered_count == 5  # mock still processed
    assert result.unique_count == 5
    assert any(s.name == "broken-board" and s.status == "error" for s in result.source_stats)
    assert any("broken-board" in e for e in result.errors)

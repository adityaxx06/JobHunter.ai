"""Phase 9 aggregator tests. Fully offline — parse-only, never any network."""

from worker.models.job import DiscoveredJob
from worker.sources import aggregators as agg


# --- host detection ------------------------------------------------------------------


def test_aggregator_key_hosts_and_subdomains():
    assert agg.aggregator_key("https://www.linkedin.com/jobs/view/1") == "linkedin"
    assert agg.aggregator_key("https://in.linkedin.com/jobs/view/1") == "linkedin"
    assert agg.aggregator_key("https://jobs.lever.co/x") == ""
    assert agg.aggregator_key("https://boards.greenhouse.io/x/y") == ""
    assert agg.aggregator_key("https://example.com/careers/x") == ""
    assert agg.aggregator_key("https://linkedin.evil.com/jobs/view/1") == ""
    for bad in ("", None, 42, "not a url", "ftp://x"):
        assert agg.aggregator_key(bad) == ""


# --- detail vs listing --------------------------------------------------------------------


def test_linkedin_detail_urls():
    assert agg.is_job_detail_url("linkedin", "https://www.linkedin.com/jobs/view/123456") is True
    assert agg.is_job_detail_url("linkedin", "https://in.linkedin.com/jobs/view/x-at-y-99/") is True
    for listing in (
        "https://www.linkedin.com/jobs/search/?keywords=java",
        "https://www.linkedin.com/jobs/collections/recommended/",
        "https://www.linkedin.com/company/acme",
        "https://www.linkedin.com/in/jane-doe",
    ):
        assert agg.is_job_detail_url("linkedin", listing) is False, listing


def test_internshala_detail_urls():
    assert agg.is_job_detail_url(
        "internshala", "https://internshala.com/internship/detail/java-dev-999") is True
    assert agg.is_job_detail_url(
        "internshala",
        "https://internshala.com/job/detail/fresher-remote-ml-intern-job-at-x17") is True
    for listing in (
        "https://internshala.com/internships/remote-java-internships-in-bangalore",
        "https://internshala.com/internships",
        "https://internshala.com/blog/how-to-apply",
        "https://internshala.com/jobs/python-jobs",
        "https://internshala.com/fresher-jobs/java-jobs",
    ):
        assert agg.is_job_detail_url("internshala", listing) is False, listing
    # Misleading detail-like path on another host stays host-gated.
    assert agg.is_job_detail_url(
        "linkedin", "https://www.linkedin.com/job/detail/x") is False


def test_indeed_detail_urls():
    assert agg.is_job_detail_url("indeed", "https://www.indeed.com/viewjob?jk=abc123") is True
    assert agg.is_job_detail_url("indeed", "https://in.indeed.com/m/viewjob?jk=abc") is True
    for listing in (
        "https://in.indeed.com/q-java-jobs.html",
        "https://www.indeed.com/pagead/clk?mo=r&ad=-6NYl",
        "https://www.indeed.com/companies/acme",
        "https://www.indeed.com/career-advice/finding-a-job",
    ):
        assert agg.is_job_detail_url("indeed", listing) is False, listing


def test_detail_requires_key_and_url():
    assert agg.is_job_detail_url("", "https://www.linkedin.com/jobs/view/1") is False
    assert agg.is_job_detail_url("linkedin", "") is False
    assert agg.is_job_detail_url("unknown", "https://example.com/x") is False


# --- conversion -------------------------------------------------------------------------------


def test_discovered_job_fields_no_fabrication():
    job = agg.discovered_job_from_target(
        "https://www.linkedin.com/jobs/view/123456?utm_source=x",
        "AI Engineer Intern at Valura.Ai",
        "Freshers welcome. " * 500,
    )
    assert isinstance(job, DiscoveredJob)
    assert job.title == "AI Engineer Intern at Valura.Ai"
    assert job.company_name == "" and job.location == ""  # never guessed
    assert job.source_type == "job_board" and job.source_name == "linkedin"
    assert job.apply_url == "https://www.linkedin.com/jobs/view/123456"
    assert job.source_url.startswith("https://www.linkedin.com/jobs/view/123456")
    assert "utm_source" not in job.apply_url
    assert len(job.description) <= agg.SNIPPET_MAX_CHARS


def test_discovered_job_empty_safe():
    job = agg.discovered_job_from_target("https://www.indeed.com/viewjob?jk=a", "", "")
    assert job.title == "" and job.apply_url == "https://www.indeed.com/viewjob?jk=a"
    job = agg.discovered_job_from_target(None, None, None)
    assert job.title == "" and job.apply_url == ""


def test_convert_entries_mixed_batch_and_cap():
    entries = [
        ("https://www.linkedin.com/jobs/view/1", "Java Intern", "Freshers welcome"),
        ("https://www.linkedin.com/jobs/search/?keywords=java", "Search", ""),
        ("https://www.indeed.com/viewjob?jk=a", "Backend Intern", ""),
        ("https://example.com/blog/x", "Blog", ""),
        ("https://internshala.com/internship/detail/x-1", "Python Intern", ""),
        ("https://www.linkedin.com/jobs/view/2", "Second", ""),
    ]
    converted, skipped = agg.convert_entries(entries, max_items=2)
    assert [j.source_name for j in converted] == ["linkedin", "indeed"]
    assert len(skipped) == 4
    assert any("cap reached" in reason for _, reason in skipped)
    assert any("non-detail" in reason for _, reason in skipped)
    assert any("not an aggregator" in reason for _, reason in skipped)


def test_convert_entries_never_raises():
    converted, skipped = agg.convert_entries([None, 42, ("x",)], max_items=5)
    assert converted == [] and len(skipped) == 3

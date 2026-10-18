"""Mock/manual source for safe end-to-end ingestion tests (Phase 4.1).

Returns ~5 realistic test jobs aligned with the dev profile. These are
CLEARLY mock data (fictional "Example" companies, example.com links,
``raw_data["mock"] is True``) — never presented as real jobs.
"""

from datetime import datetime, timedelta, timezone

from worker.models.job import DiscoveredJob, SourceHealth
from worker.sources.base import JobSource

MOCK_NOTICE = "[MOCK DATA — pipeline testing only, not a real posting]"


def _days_ago(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


_MOCK_JOBS = [
    {
        "external_id": "mock-001",
        "title": "Java Developer Intern",
        "company_name": "Example Technologies",
        "company_domain": "example.com",
        "location": "Chennai, Tamil Nadu, India",
        "is_remote": False,
        "employment_type": "Internship",
        "experience_level": "Fresher",
        "description": (
            f"{MOCK_NOTICE} 6-month Java developer internship: REST APIs with "
            "Spring Boot, SQL, Git, code reviews with senior mentors."
        ),
        "salary_min": 15000,
        "salary_max": 25000,
        "skills": ["Java", "Spring Boot", "SQL", "Git", "REST APIs"],
        "apply_url": "https://example.com/jobs/mock-001-java-developer-intern",
        "posted_days_ago": 2,
    },
    {
        "external_id": "mock-002",
        "title": "Backend Developer Intern",
        "company_name": "Sample Systems",
        "company_domain": "example.com",
        "location": "Bangalore, Karnataka, India",
        "is_remote": False,
        "employment_type": "Internship",
        "experience_level": "Fresher",
        "description": (
            f"{MOCK_NOTICE} Backend internship: Python services, PostgreSQL, "
            "REST APIs, Docker basics, on-call shadowing."
        ),
        "salary_min": 20000,
        "salary_max": 30000,
        "skills": ["Python", "SQL", "REST APIs", "Git", "DSA"],
        "apply_url": "https://example.com/jobs/mock-002-backend-developer-intern",
        "posted_days_ago": 5,
    },
    {
        "external_id": "mock-003",
        "title": "Software Engineer Intern",
        "company_name": "Demo Labs",
        "company_domain": "example.com",
        "location": "Remote, India",
        "is_remote": True,
        "employment_type": "Internship",
        "experience_level": "Student",
        "description": (
            f"{MOCK_NOTICE} Remote software engineer internship: JavaScript, "
            "HTML/CSS, React fundamentals, GitHub workflow."
        ),
        "salary_min": 10000,
        "salary_max": 20000,
        "skills": ["JavaScript", "HTML", "CSS", "React", "GitHub"],
        "apply_url": "https://example.com/jobs/mock-003-software-engineer-intern",
        "posted_days_ago": 1,
    },
    {
        "external_id": "mock-004",
        "title": "Python Developer Intern",
        "company_name": "MockWorks",
        "company_domain": "example.com",
        "location": "Hyderabad, Telangana, India",
        "is_remote": False,
        "employment_type": "Internship",
        "experience_level": "Fresher",
        "description": (
            f"{MOCK_NOTICE} Python internship: automation scripts, data "
            "pipelines, OOP, DSA practice, Linux basics."
        ),
        "salary_min": 12000,
        "salary_max": 22000,
        "skills": ["Python", "OOP", "DSA", "SQL", "Git"],
        "apply_url": "https://example.com/jobs/mock-004-python-developer-intern",
        "posted_days_ago": 7,
    },
    {
        "external_id": "mock-005",
        "title": "AI/ML Intern",
        "company_name": "Fictional AI",
        "company_domain": "example.com",
        "location": "Remote, India",
        "is_remote": True,
        "employment_type": "Internship",
        "experience_level": "Student",
        "description": (
            f"{MOCK_NOTICE} Remote AI/ML internship: Python, ML basics, "
            "data cleaning, model evaluation notebooks."
        ),
        "salary_min": 15000,
        "salary_max": 25000,
        "skills": ["Python", "AI/ML", "SQL", "DSA", "Git"],
        "apply_url": "https://example.com/jobs/mock-005-ai-ml-intern",
        "posted_days_ago": 3,
    },
]


class MockSource(JobSource):
    """In-memory test source. No network, no scraping, no secrets."""

    source_type = "manual"
    source_name = "mock"

    def discover_jobs(self, query: str = "", location: str = "", limit: int = 50) -> list:
        """Return mock jobs (naive title/location filter, honors limit)."""
        items = list(_MOCK_JOBS)
        if query.strip():
            q = query.strip().lower()
            items = [j for j in items if q in j["title"].lower()]
        if location.strip():
            loc = location.strip().lower()
            items = [j for j in items if loc in j["location"].lower()]
        jobs = []
        for item in items[: max(0, limit)]:
            jobs.append(
                DiscoveredJob(
                    external_id=item["external_id"],
                    title=item["title"],
                    company_name=item["company_name"],
                    company_domain=item["company_domain"],
                    location=item["location"],
                    is_remote=item["is_remote"],
                    employment_type=item["employment_type"],
                    experience_level=item["experience_level"],
                    description=item["description"],
                    salary_min=item["salary_min"],
                    salary_max=item["salary_max"],
                    salary_currency="INR",
                    skills=list(item["skills"]),
                    source_type=self.source_type,
                    source_name=self.source_name,
                    source_url="mock://manual/test-feed",
                    apply_url=item["apply_url"],
                    posted_at=_days_ago(item["posted_days_ago"]),
                    raw_data={"mock": True, "note": "Phase 4.1 test fixture"},
                )
            )
        return jobs

    def health_check(self) -> SourceHealth:
        """Always healthy — no external dependency."""
        return SourceHealth(ok=True, message="mock source ready (5 fixtures)")

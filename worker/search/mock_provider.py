"""Deterministic mock search provider for testing (Phase 4.3).

Returns 5 fictional leads aligned with the dev profile. URLs use a mix of
ATS-style hosts (with clearly fake company slugs) and example.com pages so
the classifier can be exercised end to end. Every fixture carries
``raw_data["mock"] is True`` — never presented as real results. No network.
"""

from worker.models.search import SearchHealth, SearchResult
from worker.search.base import SearchProvider

MOCK_NOTICE = "[MOCK DATA — search testing only, not a real result]"


_MOCK_RESULTS = [
    {
        "title": "Java Developer Intern — Example Technologies",
        "url": "https://boards.greenhouse.io/exampletechnologies/jobs/1001",
        "snippet": f"{MOCK_NOTICE} Java internship posting on a public board.",
    },
    {
        "title": "Backend Developer Intern — Sample Systems",
        "url": "https://jobs.lever.co/samplesystems/b2b2b2b2",
        "snippet": f"{MOCK_NOTICE} Backend internship posting on a public board.",
    },
    {
        "title": "Software Engineer Intern — Demo Labs",
        "url": "https://jobs.ashbyhq.com/demolabs/c3c3c3c3",
        "snippet": f"{MOCK_NOTICE} Software engineer internship on a public board.",
    },
    {
        "title": "Python Developer Intern — MockWorks Careers",
        "url": "https://example.com/careers/python-developer-intern",
        "snippet": f"{MOCK_NOTICE} Company career-page posting.",
    },
    {
        "title": "AI/ML Intern — Fictional AI Blog",
        "url": "https://example.com/blog/ai-ml-internships",
        "snippet": f"{MOCK_NOTICE} Blog post mentioning internships.",
    },
]


class MockSearchProvider(SearchProvider):
    """In-memory test provider. No network, no secrets, no scraping."""

    provider_name = "mock"

    def search(self, query: str, max_results: int = 20) -> list:
        """Return fixtures (naive title match, honors limit)."""
        items = list(_MOCK_RESULTS)
        if query.strip():
            q = query.strip().lower().strip('"')
            # Match on significant words so generic queries still return leads.
            words = [w.strip('"') for w in q.split() if len(w.strip('"')) > 2]
            items = [r for r in items if any(w in r["title"].lower() for w in words)]
        results = []
        for item in items[: max(0, int(max_results))]:
            results.append(
                SearchResult(
                    title=item["title"],
                    url=item["url"],
                    snippet=item["snippet"],
                    source_name=self.provider_name,
                    raw_data={"mock": True, "note": "Phase 4.3 test fixture"},
                )
            )
        return results

    def health_check(self) -> SearchHealth:
        """Always healthy — no external dependency."""
        return SearchHealth(ok=True, message="mock search provider ready (5 fixtures)")

"""OPTIONAL live Gemini test — never runs in the normal suite.

Enable explicitly with BOTH conditions:

    RUN_GEMINI_LIVE_TESTS=true GEMINI_API_KEY=<key> \
        python -m pytest worker/tests/test_gemini_live.py -v

Analyzes exactly ONE controlled fixture through the real Gemini provider +
strict validator. Skips cleanly otherwise. Never prints the API key, the full
prompt, or response internals — assertions only.
"""

import os

import pytest

from ai.prompts.job_intelligence import build_prompt
from ai.providers.base import AIRequest
from ai.providers.gemini import GeminiProvider
from worker.processors.intelligence.validator import validate_intelligence

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_GEMINI_LIVE_TESTS", "").strip().lower() != "true" or not os.getenv("GEMINI_API_KEY", "").strip(),
    reason="live Gemini only (RUN_GEMINI_LIVE_TESTS=true + GEMINI_API_KEY required)",
)


def test_live_single_fixture_analysis():
    import json

    provider = GeminiProvider()
    assert provider.is_configured()
    candidate = {
        "education": "MCA", "status": "Fresher",
        "skills": ["Java", "Python", "SQL", "Git"],
        "learning": ["Spring Boot"], "target_roles": ["Java Developer"],
        "target_locations": ["Chennai", "India"],
        "remote_ok": True, "relocation_ok": True,
    }
    job = {
        "title": "Java Developer Intern", "company_name": "Example Technologies",
        "description": "6-month Java internship in Chennai. REST APIs, SQL. Freshers welcome.",
        "location": "Chennai, India", "employment_type": "Internship",
        "experience_level": "Fresher", "skills": ["Java", "SQL"],
        "salary": "Unknown", "apply_url": "https://example.com/jobs/live-1",
        "source": "manual",
    }
    response = provider.generate(AIRequest(prompt=build_prompt(candidate, job)))
    intelligence = validate_intelligence(json.loads(response.text))
    assert 0 <= intelligence.match_score <= 100
    assert 0 <= intelligence.trust_score <= 100
    assert intelligence.recommendation in ("APPLY", "CONSIDER", "REVIEW", "AVOID")
    assert intelligence.reason.strip()

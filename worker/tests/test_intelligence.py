"""Phase 5.2 intelligence tests part 1: prefilter, candidate fit, validation."""

import json
import os
from contextlib import contextmanager

import pytest

from ai.prompts.job_intelligence import build_prompt
from ai.providers.base import AIRequest, AIResponse, BaseAIProvider
from ai.providers.gemini import GeminiError, GeminiProvider
from worker.db import match_repository as matches
from worker.models.intelligence import JobIntelligence
from worker.pipelines import intelligence_pipeline as pipe
from worker.processors.intelligence.prefilter import prefilter_job
from worker.processors.intelligence.validator import ValidationError, validate_intelligence

CANDIDATE = {
    "profile_id": "prof-1",
    "education": "MCA",
    "status": "Fresher",
    "skills": ["Java", "Python", "JavaScript", "HTML", "CSS", "SQL", "Git", "GitHub", "OOP", "DSA"],
    "learning": ["React", "Spring Boot", "REST APIs", "AI/ML"],
    "target_roles": ["Java Developer", "Backend Developer"],
    "target_locations": ["Chennai", "Bangalore", "India"],
    "locations": ["Chennai", "Bangalore", "India"],
    "remote_ok": True,
    "relocation_ok": True,
}


def _job(**overrides):
    base = {
        "title": "Java Developer Intern",
        "company_name": "Example Technologies",
        "description": "6-month Java internship. Build REST APIs with Spring Boot and SQL. Git required. Freshers welcome.",
        "location": "Chennai, India",
        "employment_type": "Internship",
        "experience_level": "Fresher",
        "skills": ["Java", "SQL", "Git"],
        "apply_url": "https://example.com/jobs/1",
        "source_types": ["greenhouse"],
        "is_remote": False,
    }
    base.update(overrides)
    return base


def _intel(**overrides):
    base = {
        "match_score": 82,
        "trust_score": 90,
        "recommendation": "APPLY",
        "matching_skills": ["Java", "SQL", "Git"],
        "missing_skills": ["Spring Boot"],
        "strengths": ["Strong Java backend fit"],
        "concerns": [],
        "eligibility": "ELIGIBLE",
        "reason": "Strong fresher Java backend match.",
    }
    base.update(overrides)
    return base


def test_prefilter_accepts_java_internship():
    out = prefilter_job(_job(), CANDIDATE)
    assert out.eligible_for_ai is True
    assert out.preliminary_match is not None and out.preliminary_trust is not None
    assert any("java developer" in r for r in out.reasons)


def test_prefilter_accepts_python_internship():
    out = prefilter_job(_job(title="Python Developer Intern", skills=["Python"]), CANDIDATE)
    assert out.eligible_for_ai is True


def test_prefilter_accepts_software_engineer_fresher():
    out = prefilter_job(_job(title="Software Engineer (Fresher)", skills=[]), CANDIDATE)
    assert out.eligible_for_ai is True


def test_prefilter_rejects_sales_executive():
    out = prefilter_job(_job(title="Sales Executive", description="Field sales role."), CANDIDATE)
    assert out.eligible_for_ai is False
    assert any("sales executive" in r for r in out.reasons)


def test_prefilter_rejects_telecalling():
    out = prefilter_job(_job(title="Telecaller", description="Outbound calls."), CANDIDATE)
    assert out.eligible_for_ai is False


def test_prefilter_rejects_hr_recruiter():
    out = prefilter_job(_job(title="HR Recruiter", description="Hiring for clients."), CANDIDATE)
    assert out.eligible_for_ai is False


def test_prefilter_rejects_senior_engineer():
    out = prefilter_job(_job(title="Senior Software Engineer", description="Lead the team."), CANDIDATE)
    assert out.eligible_for_ai is False


def test_prefilter_rejects_five_years_role():
    out = prefilter_job(_job(title="Software Engineer", description="Required: 5 years of Java."), CANDIDATE)
    assert out.eligible_for_ai is False


def test_prefilter_flags_payment_scam():
    job = _job(description=("Join us! " * 30) + " One-time registration fee of Rs 999 to apply.")
    out = prefilter_job(job, CANDIDATE)
    assert "payment-required" in out.flags
    assert out.preliminary_trust is not None and out.preliminary_trust < 50


def test_prefilter_flags_whatsapp_only_but_ignores_mention():
    only = _job(description="DM to apply on WhatsApp only. No portal.", apply_url="")
    assert "suspicious-contact" in prefilter_job(only, CANDIDATE).flags
    mention = _job(description="Questions? Ping us on WhatsApp. Apply at the link above.")
    assert "suspicious-contact" not in prefilter_job(mention, CANDIDATE).flags


def test_prefilter_rejects_irrelevant_role():
    out = prefilter_job(_job(title="Accountant"), CANDIDATE)
    assert out.eligible_for_ai is False


def test_prefilter_accepts_ai_automation_intern():
    out = prefilter_job(_job(title="AI Automation Engineer Intern"), CANDIDATE)
    assert out.eligible_for_ai is True
    assert any("ai automation" in r.lower() for r in out.reasons)


def test_prefilter_accepts_generative_ai_intern():
    out = prefilter_job(_job(title="Generative AI Intern"), CANDIDATE)
    assert out.eligible_for_ai is True
    gen = prefilter_job(_job(title="Gen AI Internship"), CANDIDATE)
    assert gen.eligible_for_ai is True


def test_prefilter_accepts_bare_ai_intern():
    out = prefilter_job(_job(title="AI Intern"), CANDIDATE)
    assert out.eligible_for_ai is True


def test_prefilter_still_rejects_senior_ai_roles():
    out = prefilter_job(_job(title="Senior AI Automation Engineer"), CANDIDATE)
    assert out.eligible_for_ai is False and "senior-role" in out.flags
    lead = prefilter_job(
        _job(title="Gen AI Engineer", description="8+ years building LLM systems."), CANDIDATE)
    assert lead.eligible_for_ai is False


def test_prefilter_still_rejects_unrelated_roles():
    for title in ("Accountant", "Nurse Practitioner", "Truck Driver"):
        out = prefilter_job(_job(title=title), CANDIDATE)
        assert out.eligible_for_ai is False, title


def test_prefilter_generic_developer_is_conservative():
    generic = prefilter_job(_job(title="Developer"), CANDIDATE)
    specific = prefilter_job(_job(), CANDIDATE)
    assert generic.eligible_for_ai is True
    assert "generic-title" in generic.flags
    assert generic.preliminary_match < specific.preliminary_match


def test_candidate_java_skill_overlap():
    out = prefilter_job(_job(), CANDIDATE)
    assert any("java" in r.lower() for r in out.reasons)


def test_candidate_location_and_remote():
    assert any("ocation" in r for r in prefilter_job(_job(), CANDIDATE).reasons)
    remote = prefilter_job(_job(title="Python Developer Intern", location="Remote, India", is_remote=True), CANDIDATE)
    assert any("emote" in r for r in remote.reasons)


def test_candidate_relocation_supported():
    out = prefilter_job(_job(location="Kochi, India"), CANDIDATE)
    assert out.eligible_for_ai is True  # relocation_ok: non-target city is not a rejection


def test_validator_accepts_valid_response():
    intel = validate_intelligence(_intel())
    assert isinstance(intel, JobIntelligence)
    assert (intel.match_score, intel.trust_score) == (82, 90)


def test_validator_rejects_scores_out_of_range():
    with pytest.raises(ValidationError):
        validate_intelligence(_intel(match_score=-5))
    with pytest.raises(ValidationError):
        validate_intelligence(_intel(trust_score=101))
    with pytest.raises(ValidationError):
        validate_intelligence(_intel(match_score="94%"))
    with pytest.raises(ValidationError):
        validate_intelligence(_intel(match_score=True))
    with pytest.raises(ValidationError):
        validate_intelligence(_intel(match_score=None))


def test_validator_rejects_bad_enums_and_shapes():
    with pytest.raises(ValidationError):
        validate_intelligence(_intel(recommendation="STRONG_APPLY"))
    with pytest.raises(ValidationError):
        validate_intelligence(_intel(eligibility="MAYBE"))
    with pytest.raises(ValidationError):
        validate_intelligence(_intel(reason="  "))
    with pytest.raises(ValidationError):
        validate_intelligence(_intel(matching_skills=["Java", 42]))
    dropped = dict(_intel())
    del dropped["reason"]
    with pytest.raises(ValidationError):
        validate_intelligence(dropped)
    with pytest.raises(ValidationError):
        validate_intelligence(["not", "a", "dict"])


def test_validator_ignores_extra_fields():
    intel = validate_intelligence(dict(_intel(), salary_guess="$999K", _debug={}))
    assert intel.match_score == 82


def test_prompt_states_weights_and_trust_override():
    prompt = build_prompt(CANDIDATE, {
        "title": "Java Developer Intern", "company_name": "Example",
        "description": "Java work.", "location": "Chennai",
        "employment_type": "Internship", "experience_level": "Fresher",
        "skills": ["Java"], "salary": "Unknown",
        "apply_url": "https://example.com/j/1", "source": "greenhouse",
    })
    assert "Skills 40%" in prompt and "AVOID (even with a high match score)" in prompt
    assert "Never invent candidate skills" in prompt
    assert "GEMINI_API_KEY" not in prompt and "postgres" not in prompt.lower()


def test_trust_official_source_vs_payment_scam():
    good = prefilter_job(_job(), CANDIDATE)
    assert good.preliminary_trust >= 80
    scam = prefilter_job(_job(description=("Legit text. " * 30) + " Pay a processing fee to apply."), CANDIDATE)
    assert scam.preliminary_trust < 50


def test_trust_override_shapes_survive_validation():
    avoid = validate_intelligence(_intel(match_score=95, trust_score=15, recommendation="AVOID"))
    assert (avoid.match_score, avoid.trust_score, avoid.recommendation) == (95, 15, "AVOID")
    apply = validate_intelligence(_intel(match_score=94, trust_score=96, recommendation="APPLY"))
    assert apply.recommendation == "APPLY"

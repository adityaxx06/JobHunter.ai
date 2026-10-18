"""Job-intelligence prompt builder (Phase 5.2). Prompt lives here — never inline.

build_prompt(candidate, job) renders the full instruction + data payload and
requests strict JSON only. Anti-hallucination rules are part of the prompt:
unknown information must be reported as unknown, never invented.
"""

import json

SYSTEM_INSTRUCTION = """You are a job opportunity intelligence engine. Evaluate ONE job against ONE candidate profile.

You must:
1. determine role relevance
2. determine eligibility (fresher/student constraints respected)
3. compare the candidate's skills with the job's stated requirements
4. identify missing skills
5. estimate match quality with these relative weights: Skills 40%, Experience 20%, Education 10%, Role relevance 15%, Location 10%, Compensation 5%
6. evaluate trust/risk signals (source legitimacy, company identity, application process, description quality, salary realism, scam indicators, contact method)
7. recommend exactly one of: APPLY, CONSIDER, REVIEW, AVOID
8. explain the decision concisely

Recommendation guidance (trust can override match):
- 90-100 match + high trust -> APPLY
- 80-89 match + high trust -> APPLY or CONSIDER
- 70-79 -> CONSIDER
- 60-69 -> REVIEW
- below 60 -> REVIEW or AVOID
- very low trust or obvious scam -> AVOID (even with a high match score)

Match score and trust score are independent (0-100 integers each).

Anti-hallucination rules (critical):
- Never invent candidate skills. Never invent job requirements, salary, experience, company information, benefits, location, or application instructions.
- If information is unavailable, use "Unknown" or "Uncertain" — prefer uncertainty over fabricated information.
- Do not treat a missing requirement as definitely required unless the job states it. Distinguish "required" from "preferred".
- A missing skill must not automatically cause rejection.
- Do not recommend applying to suspicious jobs merely because skill match is high.

Return ONLY the requested JSON object. No markdown fences, no commentary."""

OUTPUT_SCHEMA_HINT = """Return exactly this JSON shape (all fields required):
{
  "match_score": <integer 0-100>,
  "trust_score": <integer 0-100>,
  "recommendation": "APPLY" | "CONSIDER" | "REVIEW" | "AVOID",
  "matching_skills": [<strings actually shared by candidate and job>],
  "missing_skills": [<strings the job states that the candidate lacks>],
  "strengths": [<short strings>],
  "concerns": [<short strings>],
  "eligibility": "ELIGIBLE" | "LIKELY_ELIGIBLE" | "UNCERTAIN" | "NOT_ELIGIBLE",
  "reason": "<one concise paragraph>"
}"""


def _truncate(text: object, limit: int = 4000) -> str:
    """Cap long text (descriptions) so prompts stay small and cheap."""
    if not isinstance(text, str):
        return ""
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + " …[truncated]"


def build_prompt(candidate: dict, job: dict) -> str:
    """Render the full prompt for one (candidate, job) pair (no secrets)."""
    candidate = candidate or {}
    job = job or {}
    candidate_payload = {
        "education": candidate.get("education", "Unknown"),
        "status": candidate.get("status", "Unknown"),
        "skills": candidate.get("skills") or [],
        "learning": candidate.get("learning") or [],
        "target_roles": candidate.get("target_roles") or [],
        "target_locations": candidate.get("target_locations") or [],
        "remote": bool(candidate.get("remote_ok")),
        "relocation": bool(candidate.get("relocation_ok")),
    }
    job_payload = {
        "title": job.get("title", "Unknown"),
        "company": job.get("company_name") or "Unknown",
        "description": _truncate(job.get("description"), 4000),
        "location": job.get("location") or "Unknown",
        "employment_type": job.get("employment_type") or "Unknown",
        "experience": job.get("experience_level") or "Unknown",
        "skills": job.get("skills") or [],
        "salary": job.get("salary") or "Unknown",
        "apply_url": job.get("apply_url") or "Unknown",
        "source": job.get("source") or "Unknown",
    }
    return (
        f"{SYSTEM_INSTRUCTION}\n\n"
        f"Candidate:\n{json.dumps(candidate_payload, ensure_ascii=False)}\n\n"
        f"Job:\n{json.dumps(job_payload, ensure_ascii=False)}\n\n"
        f"{OUTPUT_SCHEMA_HINT}"
    )

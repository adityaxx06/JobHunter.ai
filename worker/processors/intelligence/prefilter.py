"""Deterministic rule-based prefilter (Phase 5.2). No AI, no network.

Decides whether a persisted job deserves Gemini quota. Title context drives
role decisions (description words like "sales"/"marketing"/"client" never
reject a software role on their own). Experience bands, payment-scam signals,
and suspicious contact channels are flagged deterministically; trust math
stays conservative so Gemini makes the final call.
"""

import re

from worker.models.intelligence import PrefilterResult
from worker.utils.skill_synonyms import canonical_skill

#: Title phrases for clearly non-software roles (matched against the title only).
HARD_EXCLUSIONS = (
    "sales executive", "sales intern", "sales manager", "sales representative",
    "sales rep", "telecaller", "tele caller", "telecalling", "call center",
    "business development", "insurance agent", "field sales",
    "door-to-door sales", "door to door sales", "commission-only sales",
    "commission only", "real estate sales", "recruitment consultant",
    "hr recruiter", "recruiter", "content writer", "social media manager",
    "digital marketing", "marketing executive", "marketing intern",
    "marketing manager", "customer support", "customer service representative",
    "data entry",
)

#: Role signals, most-specific first (order matters for the generic fallback).
ROLE_TERMS = (
    "software engineer", "software developer", "backend developer",
    "backend engineer", "java developer", "python developer",
    "full stack developer", "full-stack developer", "web developer",
    "ai engineer", "ai automation", "generative ai", "gen ai", "genai",
    "ai intern", "machine learning", "ai/ml", "ai engineer intern",
    "software intern", "developer intern", "engineering intern",
    "sde intern", "sde-", "developer",
)

FRESHER_TERMS = (
    "intern", "internship", "fresher", "freshers", "entry level",
    "entry-level", "graduate", "student", "trainee", "junior",
)

SENIOR_TITLE_TOKENS = (
    "senior", " sr ", "sr.", "lead", "principal", "architect",
    "engineering manager", "head of", "director", "staff engineer",
    "staff software", "vp engineering", "cto",
)

#: "3+ years", "5 years", "0-1 years" style requirements.
_YEARS_RE = re.compile(r"(\d+)\s*(?:[-–+]\s*(\d+))?\s*(?:\+)?\s*(?:yrs?|years?)", re.IGNORECASE)

PAYMENT_SCAM_RE = re.compile(
    r"(registration|application|training|security|processing)\s*(fee|fees|deposit)|"
    r"pay\s+to\s+(apply|get\s+(the\s+)?job)|buy\s+course|guaranteed\s+(job|placement)|"
    r"pay\s+money|security\s+deposit",
    re.IGNORECASE,
)

_TRUSTED_SOURCES = {"greenhouse", "lever", "ashby", "company_careers"}


def _lower(value: object) -> str:
    return value.lower() if isinstance(value, str) else ""


def _word_hit(text: str, phrase: str) -> bool:
    """Substring hit with padding for very short tokens (avoids 'lead' in 'leader' noise)."""
    if len(phrase.strip()) <= 4:
        return f" {phrase.strip()} " in f" {text} "
    return phrase in text


def _matched_role(title: str):
    """Most specific role term in the title (None when irrelevant)."""
    for term in ROLE_TERMS:
        if _word_hit(title, term):
            return term
    return None


def _experience_years(text: str) -> list:
    """All year-numbers appearing in a years-requirement context."""
    return [int(m.group(1)) for m in _YEARS_RE.finditer(text or "")]


def _skill_overlap(candidate_skills: list, job: dict) -> list:
    """Candidate skills appearing as whole words in skills/title/description.

    Both sides go through skill canonicalization first, so alias spellings
    ("JS" vs "JavaScript") still overlap. Original display forms are kept.
    """
    haystacks = {canonical_skill(s) for s in (job.get("skills") or []) if s}
    haystacks.discard("")
    text = f"{_lower(job.get('title'))} {_lower(job.get('description'))}"
    overlap = []
    for skill in candidate_skills or []:
        token = str(skill).strip().lower()
        if not token:
            continue
        canonical = canonical_skill(token)
        variants = {token} if canonical == token else {token, canonical}
        if canonical in haystacks or any(
            re.search(rf"(?<![\w+#]){re.escape(variant)}(?![\w+#])", text)
            for variant in variants
        ):
            overlap.append(str(skill).strip())
    return overlap


def prefilter_job(job: dict, candidate: dict) -> PrefilterResult:
    """Apply deterministic rules. Never raises on missing keys."""
    job = job or {}
    candidate = candidate or {}
    title = _lower(job.get("title"))
    description = _lower(job.get("description"))
    experience_text = f"{title} {description} {_lower(job.get('experience_level'))}"

    # --- hard exclusions: title context only ---------------------------------
    for phrase in HARD_EXCLUSIONS:
        if _word_hit(title, phrase):
            return PrefilterResult(
                eligible_for_ai=False,
                reasons=[f"Excluded non-software role: {phrase}"],
                flags=["excluded-role"],
            )

    # --- role relevance --------------------------------------------------------
    role = _matched_role(title)
    if role is None:
        return PrefilterResult(
            eligible_for_ai=False,
            reasons=["Role outside target software set"],
            flags=["irrelevant-role"],
        )
    generic_only = (role == "developer")
    reasons = [f"Target software role: {role}"]
    flags = []
    match = 30 if generic_only else 40
    if generic_only:
        flags.append("generic-title")

    # --- experience band ---------------------------------------------------------
    senior = any(_word_hit(title, token.strip()) for token in SENIOR_TITLE_TOKENS)
    years = _experience_years(experience_text)
    if senior or any(y >= 3 for y in years):
        detail = "senior title" if senior else f"{max(years)}+ years required"
        return PrefilterResult(
            eligible_for_ai=False,
            reasons=[f"Experienced role, not fresher-fit ({detail})"],
            flags=["senior-role"],
        )
    if any(1 <= y <= 2 for y in years):
        flags.append("experience-note:1-2-years")
        reasons.append("Some experience mentioned (1-2 years) — needs AI judgement")
        match += 5
    if any(term in experience_text for term in FRESHER_TERMS):
        reasons.append("Fresher-friendly")
        match += 20
    else:
        match += 5

    # --- skills -------------------------------------------------------------------
    overlap = _skill_overlap(candidate.get("skills") or [], job)
    if overlap:
        reasons.append(f"{len(overlap)} profile skill(s) overlap ({', '.join(sorted(set(overlap))[:5])})")
        match += min(15, 3 * len(set(overlap)))

    # --- location -------------------------------------------------------------------
    wanted = [str(loc).strip().lower() for loc in (candidate.get("locations") or []) if str(loc).strip()]
    job_location = _lower(job.get("location"))
    if wanted and any(loc and loc in job_location for loc in wanted):
        reasons.append("Location match")
        match += 5
    if job.get("is_remote") and candidate.get("remote_ok"):
        reasons.append("Remote-friendly")
        match += 5

    # --- trust signals -----------------------------------------------------------------
    trust = 70
    sources = [str(s).lower() for s in (job.get("source_types") or []) if s]
    if any(s in _TRUSTED_SOURCES for s in sources):
        trust += 10
        reasons.append("Known legitimate source")
    if isinstance(job.get("description"), str) and len(job["description"]) > 200:
        trust += 5
    if job.get("apply_url"):
        trust += 5
    else:
        trust -= 10
        flags.append("no-apply-url")
    if not job.get("company_name"):
        trust -= 15
        flags.append("no-company-identity")
    if PAYMENT_SCAM_RE.search(f"{title} {description}"):
        flags.append("payment-required")
        trust -= 45
    contact_text = f"{title} {description}"
    has_telegram = "telegram" in contact_text
    has_whatsapp = "whatsapp" in contact_text
    dm_apply = bool(re.search(r"(dm|message|ping)\s+(to\s+)?apply|apply\s+(via|through|on)\s+(telegram|whatsapp)", contact_text))
    if (has_telegram or has_whatsapp) and (dm_apply or not job.get("apply_url")):
        flags.append("suspicious-contact")
        trust -= 20
    # A bare WhatsApp/Telegram mention with a normal apply path is NOT flagged.

    return PrefilterResult(
        eligible_for_ai=True,
        reasons=reasons,
        flags=flags,
        preliminary_match=max(0, min(100, match)),
        preliminary_trust=max(0, min(100, trust)),
    )

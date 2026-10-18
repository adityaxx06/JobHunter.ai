"""Deterministic ranking scorer (Phase 5.3). Pure Python, no AI, no network.

Formula (transparent, tested constants — tune here, nowhere else):

    base      = match_score * 0.60 + trust_score * 0.25
    final     = base + recommendation_bonus + profile_preference (0-5)
                     + skill_bonus (0-2) - trust_penalty
    clamped to 0-100, rounded to 2 decimals.

Match dominates, but trust bites: trust < 25 takes a severe penalty and any
AVOID takes -25, so high-match/low-trust jobs cannot top honest ones.
Profile preference rewards exact target roles, priority cities / remote, and
fresher-friendly employment without ever inventing data.
"""

from worker.models.intelligence import MAX_SCORE, MIN_SCORE, RECOMMENDATIONS

MATCH_WEIGHT = 0.60
TRUST_WEIGHT = 0.25

RECOMMENDATION_BONUS = {
    "APPLY": 10.0,
    "CONSIDER": 5.0,
    "REVIEW": 0.0,
    "AVOID": -25.0,
}
RECOMMENDATION_ORDER = {"APPLY": 0, "CONSIDER": 1, "REVIEW": 2, "AVOID": 3}

# Trust bands (severe < 25, moderate 25-49, mild 50-69, normal 70+).
TRUST_SEVERE_BELOW = 25
TRUST_MODERATE_BELOW = 50
TRUST_MILD_BELOW = 70
TRUST_PENALTY_SEVERE = 30.0
TRUST_PENALTY_MODERATE = 12.0
TRUST_PENALTY_MILD = 4.0

# Profile-preference budget (0-5 total).
ROLE_EXACT_BONUS = 2.5
ROLE_PARTIAL_BONUS = 1.0
LOCATION_BONUS = 1.5
LOCATION_GENERAL_BONUS = 0.5
EMPLOYMENT_BONUS = 1.0
EMPLOYMENT_OTHER_BONUS = 0.5

SKILL_BONUS_PER_SKILL = 0.25
SKILL_BONUS_CAP = 2.0

_FRESHER_EMPLOYMENT_TOKENS = ("intern", "trainee", "apprentice", "full-time", "full time", "full_time")


def _lower(value: object) -> str:
    return value.lower() if isinstance(value, str) else ""


def trust_penalty(trust_score: int) -> tuple:
    """(penalty, reason-or-None) for the trust bands."""
    if trust_score < TRUST_SEVERE_BELOW:
        return TRUST_PENALTY_SEVERE, f"severe trust penalty (trust {trust_score} < {TRUST_SEVERE_BELOW})"
    if trust_score < TRUST_MODERATE_BELOW:
        return TRUST_PENALTY_MODERATE, f"moderate trust penalty (trust {trust_score} < {TRUST_MODERATE_BELOW})"
    if trust_score < TRUST_MILD_BELOW:
        return TRUST_PENALTY_MILD, f"mild trust penalty (trust {trust_score} < {TRUST_MILD_BELOW})"
    return 0.0, None


def role_preference(job_title: str, target_roles: list) -> tuple:
    """(bonus, reason-or-None): exact target-role hit beats a word overlap."""
    title = _lower(job_title)
    if not title:
        return 0.0, None
    for role in target_roles or []:
        name = _lower(role).strip()
        if name and name in title:
            return ROLE_EXACT_BONUS, f"exact target role: {str(role).strip()}"
    title_words = {w for w in title.replace("/", " ").split() if len(w) > 3}
    for role in target_roles or []:
        words = [w for w in _lower(role).replace("/", " ").split() if len(w) > 3]
        if any(w in title_words for w in words):
            return ROLE_PARTIAL_BONUS, "related role overlap"
    return 0.0, None


def location_preference(job_location: str, is_remote: bool, locations: list, remote_ok: bool) -> tuple:
    """(bonus, reason-or-None): priority city / remote / India-wide / other."""
    text = _lower(job_location)
    city_names = [str(loc).strip().lower() for loc in (locations or []) if str(loc).strip()]
    priority_cities = [c for c in city_names if c not in ("india", "remote")]
    if text and any(city and city in text for city in priority_cities):
        return LOCATION_BONUS, "priority location"
    if (is_remote or "remote" in text) and remote_ok:
        return LOCATION_BONUS, "remote-friendly"
    if text and ("india" in text or any(city and city in text for city in city_names)):
        return LOCATION_GENERAL_BONUS, "india-wide eligible"
    if text:
        return LOCATION_GENERAL_BONUS, "relocation-compatible"
    return 0.0, None


def employment_preference(employment_type: str) -> tuple:
    """(bonus, reason-or-None): internships and full-time fit a fresher profile."""
    text = _lower(employment_type)
    if not text:
        return EMPLOYMENT_OTHER_BONUS, None
    if any(token in text for token in _FRESHER_EMPLOYMENT_TOKENS):
        return EMPLOYMENT_BONUS, "fresher-friendly employment"
    return EMPLOYMENT_OTHER_BONUS, None


def skill_bonus(matching_skills: list) -> tuple:
    """Small capped bonus for skill alignment (never overpowers match/trust)."""
    count = len([s for s in (matching_skills or []) if isinstance(s, str) and s.strip()])
    bonus = min(SKILL_BONUS_CAP, SKILL_BONUS_PER_SKILL * count)
    if bonus > 0:
        return bonus, f"{count} matching skill(s)"
    return 0.0, None


def calculate_ranking_score(match_score: int, trust_score: int, recommendation: str,
                            preference: float = 0.0, skills_bonus: float = 0.0) -> tuple:
    """Combine validated signals into (score, reasons, trust_penalty).

    Raises ValueError on out-of-range scores or unknown recommendations —
    callers treat that as an excluded row, never a silent default.
    """
    if isinstance(match_score, bool) or not isinstance(match_score, int):
        raise ValueError("match_score must be an integer 0-100")
    if isinstance(trust_score, bool) or not isinstance(trust_score, int):
        raise ValueError("trust_score must be an integer 0-100")
    if not (MIN_SCORE <= match_score <= MAX_SCORE):
        raise ValueError("match_score must be an integer 0-100")
    if not (MIN_SCORE <= trust_score <= MAX_SCORE):
        raise ValueError("trust_score must be an integer 0-100")
    if recommendation not in RECOMMENDATIONS:
        raise ValueError(f"recommendation must be one of {', '.join(RECOMMENDATIONS)}")
    base = match_score * MATCH_WEIGHT + trust_score * TRUST_WEIGHT
    rec_bonus = RECOMMENDATION_BONUS[recommendation]
    penalty, penalty_reason = trust_penalty(trust_score)
    score = max(0.0, min(100.0, base + rec_bonus + float(preference) + float(skills_bonus) - penalty))
    reasons = [
        f"match {match_score} x {MATCH_WEIGHT}",
        f"trust {trust_score} x {TRUST_WEIGHT}",
        f"recommendation {recommendation} {rec_bonus:+g}",
    ]
    if penalty_reason:
        reasons.append(f"{penalty_reason} (-{penalty:g})")
    return round(score, 2), reasons, penalty


def sort_key(ranked: dict) -> tuple:
    """Deterministic ordering: score, match, trust, rec priority, prefs, job id.

    ``ranked`` carries ranking_score, match_score, trust_score,
    recommendation, role_score, location_score, job_id. No randomness, no
    dependence on database insertion order.
    """
    return (
        -ranked["ranking_score"],
        -ranked["match_score"],
        -ranked["trust_score"],
        RECOMMENDATION_ORDER.get(ranked.get("recommendation"), 4),
        -ranked.get("role_score", 0.0),
        -ranked.get("location_score", 0.0),
        str(ranked.get("job_id", "")),
    )

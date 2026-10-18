"""Latest-feed eligibility: fresh + geography-fit + role-fit (Phase 7D fix).

Single shared gate so discovery summaries, ranking, and the dashboard agree
on what counts as a qualified recent match. Pure functions, no AI, no
network, no database. Callers pass ``now`` explicitly so tests use a fixed
clock; production passes ``datetime.now(timezone.utc)``.

Freshness uses the genuine employer/source publication timestamp
(``posted_at``) ONLY — never ``first_seen_at``/``last_seen_at``, retrieval
time, expiry dates, or category-page update times. Unknown or invalid dates
are reported, never silently treated as new.

Geography defaults to India (``LATEST_COUNTRY``): India-based roles and
remote roles verifiably open to India pass; foreign-restricted roles fail;
ambiguous locations are ``unverified``, never guessed.

Role fit reuses the existing deterministic prefilter — no second rule set.
"""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

DEFAULT_MAX_AGE_DAYS = 7
DEFAULT_COUNTRY = "India"
#: Clock-skew tolerance for future timestamps (beyond this = invalid).
FUTURE_TOLERANCE_DAYS = 1

#: India location tokens (city/state/country names, lowercase).
INDIA_TOKENS = frozenset({
    "india", "chennai", "madras", "bengaluru", "bangalore", "hyderabad",
    "pune", "mumbai", "bombay", "delhi", "new delhi", "ncr", "gurgaon",
    "gurugram", "noida", "kolkata", "calcutta", "ahmedabad", "kochi",
    "cochin", "coimbatore", "indore", "jaipur", "lucknow", "nagpur",
    "surat", "patna", "bhopal", "visakhapatnam", "thiruvananthapuram",
    "mysuru", "mysore", "vijayawada", "guwahati", "chandigarh", "bhubaneswar",
    "pan india",
})

#: Explicit foreign-restriction markers (lowercase; matched as whole tokens).
#: Small and conservative on purpose — unknown places stay "unverified".
FOREIGN_TOKENS = frozenset({
    "united states", "usa", "u.s.a", "us", "america", "united kingdom", "uk",
    "uae", "london", "germany", "berlin", "france", "paris", "spain", "barcelona",
    "netherlands", "amsterdam", "canada", "australia", "chicago",
    "new york", "nyc", "texas", "california", "montreal", "europe",
})

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def _tokens(text: object) -> set:
    """Lowercase word tokens from free text (empty set for junk input)."""
    if not isinstance(text, str):
        return set()
    return {token for token in _TOKEN_SPLIT.split(text.lower()) if token}


def _lexicon_hit(lowered_text: str, tokens: set, lexicon: frozenset) -> bool:
    """True when any lexicon entry matches (phrases by substring, words by token).

    Single words match whole tokens only ("us" never fires inside "campus");
    multi-word phrases ("new york", "pan india") match as substrings.
    """
    return any(
        (entry in lowered_text) if " " in entry else (entry in tokens)
        for entry in lexicon
    )


def get_max_age_days(env: object = None) -> int:
    """Maximum posting age in days (default 7, clamped to 1..90)."""
    source = os.environ if env is None else env
    get = source.get if hasattr(source, "get") else (lambda k, d="": os.environ.get(k, d))
    try:
        return max(1, min(90, int(str(get("LATEST_MAX_AGE_DAYS", DEFAULT_MAX_AGE_DAYS)))))
    except (TypeError, ValueError):
        return DEFAULT_MAX_AGE_DAYS


def get_target_country(env: object = None) -> str:
    """Target country for geography eligibility (default India)."""
    source = os.environ if env is None else env
    get = source.get if hasattr(source, "get") else (lambda k, d="": os.environ.get(k, d))
    value = str(get("LATEST_COUNTRY", DEFAULT_COUNTRY) or "").strip()
    return value or DEFAULT_COUNTRY


def parse_posted_at(value: object):
    """Genuine publication timestamp -> aware datetime (None when unusable).

    Accepts datetimes (naive assumed UTC) and ISO-8601 strings. Never
    invents a date: missing/invalid values yield None.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except (ValueError, OverflowError):
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def check_freshness(posted_at: object, now: datetime, max_age_days: int) -> tuple:
    """(is_fresh, reason) using the publication timestamp only."""
    parsed = parse_posted_at(posted_at)
    if parsed is None:
        return False, "unknown publication date"
    try:
        now_aware = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    except Exception:
        return False, "invalid reference time"
    age_days = (now_aware - parsed).total_seconds() / 86400.0
    if age_days < -FUTURE_TOLERANCE_DAYS:
        return False, "future publication date"
    if age_days <= max_age_days:
        return True, f"posted {max(0, int(age_days))} day(s) ago"
    return False, f"posted {int(age_days)} day(s) ago (older than {max_age_days})"


def check_geography(location: object, is_remote: object, country: str = DEFAULT_COUNTRY) -> tuple:
    """(verdict, reason) where verdict is eligible/unverified/excluded.

    Only the default country (India) has token knowledge; other countries
    behave conservatively (known-foreign exclusion still applies).
    """
    text = location if isinstance(location, str) else ""
    lowered = text.lower()
    tokens = _tokens(text)
    remote = bool(is_remote) or "remote" in lowered
    is_india = country.strip().lower() == "india"
    india_hit = is_india and ("india" in lowered or _lexicon_hit(lowered, tokens, INDIA_TOKENS))
    if india_hit:
        return "eligible", "India-based opportunity"
    foreign_hit = _lexicon_hit(lowered, tokens, FOREIGN_TOKENS)
    if foreign_hit:
        return "excluded", "restricted outside India"
    if remote:
        if any(word in lowered for word in ("anywhere", "worldwide", "global")):
            return "eligible", "worldwide remote"
        return "unverified", "remote scope unclear"
    if not text.strip():
        return "unverified", "unknown location"
    if country.strip().lower() != "india":
        return "unverified", "unknown geography fit"
    return "unverified", "location not verifiable as India"


def check_role(job_view: dict, candidate: dict) -> tuple:
    """(role_ok, reasons) via the existing deterministic prefilter."""
    from worker.processors.intelligence.prefilter import prefilter_job

    try:
        pre = prefilter_job(job_view or {}, candidate or {})
    except Exception as exc:
        return False, [f"prefilter failed ({type(exc).__name__})"]
    return bool(pre.eligible_for_ai), list(pre.reasons)


@dataclass
class EligibilityResult:
    """Per-job Latest-feed verdict (all three gates must pass)."""

    fresh_ok: bool = False
    fresh_reason: str = ""
    geo_verdict: str = "unverified"  # eligible | unverified | excluded
    geo_reason: str = ""
    role_ok: bool = False
    role_reasons: list = field(default_factory=list)

    @property
    def eligible(self) -> bool:
        """Qualified recent match: fresh + geography-eligible + role-fit."""
        return self.fresh_ok and self.geo_verdict == "eligible" and self.role_ok

    @property
    def unverified(self) -> bool:
        """Needs the Date-Unverified treatment: bad date or unclear geography."""
        return (not self.fresh_ok and "unknown publication date" in self.fresh_reason) \
            or self.geo_verdict == "unverified"


def assess_job(job_view: dict, candidate: dict, now: datetime,
               max_age_days: int = DEFAULT_MAX_AGE_DAYS,
               country: str = DEFAULT_COUNTRY) -> EligibilityResult:
    """Assess one job view for Latest-feed eligibility (never raises)."""
    try:
        fresh_ok, fresh_reason = check_freshness(
            (job_view or {}).get("posted_at"), now, max_age_days)
    except Exception:
        fresh_ok, fresh_reason = False, "freshness check failed"
    try:
        geo_verdict, geo_reason = check_geography(
            (job_view or {}).get("location"), (job_view or {}).get("is_remote"), country)
    except Exception:
        geo_verdict, geo_reason = "unverified", "geography check failed"
    role_ok, role_reasons = check_role(job_view, candidate)
    return EligibilityResult(
        fresh_ok=fresh_ok, fresh_reason=fresh_reason,
        geo_verdict=geo_verdict, geo_reason=geo_reason,
        role_ok=role_ok, role_reasons=role_reasons,
    )


def build_job_view(row: dict) -> dict:
    """Ranking row -> prefilter-compatible job view (no fetching)."""
    skills = row.get("skills")
    return {
        "job_id": row.get("job_id"),
        "title": row.get("title") or "",
        "company_name": row.get("company_name") or "",
        "description": row.get("description") or "",
        "location": row.get("location") or "",
        "employment_type": row.get("employment_type") or "",
        "experience_level": row.get("experience_level") or "",
        "skills": list(skills) if isinstance(skills, list) else [],
        "apply_url": row.get("apply_url") or "",
        "source_types": [],
        "is_remote": bool(row.get("is_remote")),
        "posted_at": row.get("posted_at"),
    }

"""Search-query generation from profile facets (Phase 4.3).

Builds a bounded, prioritized query list — never a combinatorial explosion:
tier 1 (role + intern + country), tier 2 (role + skill-or-fresher-term + top
cities, round-robin — first roles prefer an owned/learning skill term when
absent from the role), tier 3 (remote variants), tier 4 (six site: slots
rotating every host across the top three roles and top two locations —
job boards first, then ATS hosts — blended in so
small budgets still reach them). Intern/fresher terms apply only to
fresher profiles (explicit seniority evidence switches them off); the
tier-1 head always survives capping.
Truncated to ``max_queries`` with the tier-1 head first, so the most valuable
queries always survive capping. Queries are handed to the provider; nothing here
touches a search engine.
"""

from dataclasses import dataclass, field

from worker.models.search import SearchQuery

DEFAULT_ROLES = [
    "Software Developer",
    "Software Engineer",
    "Java Developer",
    "Backend Developer",
    "Backend Engineer",
    "Full Stack Developer",
    "Web Developer",
    "Python Developer",
    "AI/ML Intern",
    "AI Engineer Intern",
    "Machine Learning Intern",
]

DEFAULT_LOCATIONS = [
    "India",
    "Chennai",
    "Bangalore",
    "Hyderabad",
    "Pune",
    "Mumbai",
    "Delhi NCR",
    "Gurgaon",
    "Noida",
    "Kolkata",
    "Remote",
]

FRESHER_TERMS = [
    "intern",
    "internship",
    "fresher",
    "entry level",
    "graduate",
    "trainee",
    "junior",
]

SITE_HINTS = [
    "site:boards.greenhouse.io",
    "site:jobs.lever.co",
    "site:jobs.ashbyhq.com",
]

#: Job-board discovery hosts, highest priority first (Phase 7A source-first
#: discovery: LinkedIn, Internshala, Indeed — original URLs are enough since
#: the user applies manually). Same query-string mechanism as SITE_HINTS.
JOB_BOARD_HINTS = [
    "site:linkedin.com/jobs",
    "site:internshala.com",
    "site:indeed.com",
]

#: Tier-4 site-query budget (Phase 10A). Six slots cover every host once
#: across the top three roles and top two locations (3 roles x 2 locations,
#: hosts in priority order); with the default 24 generic queries the combined
#: 30 fits the default budget with zero cuts (remote variants included),
#: while small budgets still execute source-targeted discovery.
SITE_QUERY_BUDGET = 6

DEFAULT_COUNTRY = "India"


@dataclass
class SearchProfile:
    """Profile facets driving query generation (plain data, no secrets)."""

    roles: list = field(default_factory=lambda: list(DEFAULT_ROLES))
    skills: list = field(default_factory=list)
    learning_skills: list = field(default_factory=list)
    locations: list = field(default_factory=lambda: list(DEFAULT_LOCATIONS))
    remote_ok: bool = True
    experience_level: str = "Fresher"


#: Roles indices that may use a skill term instead of a fresher term
#: (Phase 7C: bounded personalization, never a combinatorial explosion).
SKILL_TERM_ROLES = 2

#: Profile hints marking non-fresher candidates (substring, own profile text).
_SENIOR_PROFILE_HINTS = (
    "senior", "lead", "principal", "staff", "manager", "director",
    "architect", "cto", "experienced", "expert", "3+", "4+", "5+",
)


def is_fresher_profile(experience_level: object) -> bool:
    """True unless the experience text shows seniority (unknown stays fresher).

    Unknown/empty keeps the current broad fresher behavior; only explicit
    seniority evidence switches query terms off.
    """
    text = str(experience_level or "").strip().lower()
    if not text:
        return True
    return not any(hint in text for hint in _SENIOR_PROFILE_HINTS)


def _skill_term(role: str, owned: list, learning: list, used: set = None):
    """First unused skill absent from the role words (owned before learning).

    Returns None when every skill already appears in the role (or there are
    no skills), so the caller falls back to fresher terms. ``used`` tracks
    skills spent on earlier roles so one skill never fills every slot.
    Display casing of the skill is preserved; matching is case-insensitive
    whole-word.
    """
    words = {word for word in str(role or "").lower().split() if word}
    used = used if used is not None else set()
    for pool in (owned, learning):
        for skill in pool or []:
            token = str(skill).strip()
            lowered = token.lower()
            if len(token) > 1 and lowered not in words and lowered not in used:
                used.add(lowered)
                return token
    return None


def _role_query(role: str, term: str, location: str) -> str:
    """`"Role Term" Location` — quoted role keeps multi-word roles together."""
    return f'"{_with_term(role, term)}" {location}'.strip()


#: Trailing-word families treated as one qualifier (case-insensitive), so a
#: role already carrying one never receives it (or its sibling) again.
_INTERN_FAMILY = {"intern", "interns", "internship", "internships"}
_FRESHER_FAMILY = {"fresher", "freshers"}


def _with_term(role: str, term: str) -> str:
    """Append a fresher/intern term unless the role already ends with it.

    Case-insensitive, whole-word(s) only: "Java Backend Intern" + "intern"
    stays unchanged, while "Printer" + "intern" still appends (no substring
    games). Original casing is preserved.
    """
    role = (role or "").strip()
    term = (term or "").strip()
    if not role or not term:
        return role or term
    lowered_role, lowered_term = role.lower(), term.lower()
    if lowered_role == lowered_term or lowered_role.endswith(" " + lowered_term):
        return role
    last = lowered_role.split()[-1]
    if last in _INTERN_FAMILY and lowered_term in _INTERN_FAMILY:
        return role
    if last in _FRESHER_FAMILY and lowered_term in _FRESHER_FAMILY:
        return role
    return f"{role} {term}"


def generate_queries(profile: SearchProfile = None, max_queries: int = 30) -> list:
    """Generate bounded role/location/fresher queries in priority-tier order.

    Generic tiers first (tier 1 broad, tier 2 fresher x city, tier 3 remote),
    then the existing ATS-targeted ``generate_site_queries()`` blended in
    right after the tier-1 head (1 site per 2 generic). Blending — not
    appending — is what lets small budgets (even 3) still execute ATS
    discovery while the combined list honors the single ``max_queries`` cap.
    Exact-duplicate strings are dropped; ordering stays deterministic.
    """
    profile = profile or SearchProfile()
    roles = [r for r in (profile.roles or []) if r.strip()] or list(DEFAULT_ROLES)
    locations = [loc for loc in (profile.locations or []) if loc.strip()]
    cities = [loc for loc in locations if loc.strip().lower() != "remote"] or [DEFAULT_COUNTRY]
    owned = [str(s).strip() for s in (getattr(profile, "skills", None) or []) if str(s).strip()]
    learning = [str(s).strip() for s in (getattr(profile, "learning_skills", None) or []) if str(s).strip()]
    fresher = is_fresher_profile(getattr(profile, "experience_level", "Fresher"))

    queries: list = []
    seen = set()

    def _add(query: str, role: str, location: str, site_hint: str = "") -> None:
        if query and query not in seen:
            seen.add(query)
            queries.append(SearchQuery(query=query, role=role, location=location, site_hint=site_hint))

    # Tier 1: every role (+ intern for fresher profiles) + country (broad first).
    tier1_term = "intern" if fresher else ""
    for role in roles:
        _add(_role_query(role, tier1_term, DEFAULT_COUNTRY), role, DEFAULT_COUNTRY)
    # Tier 2: roles x terms x top cities, round-robin (no explosion). The
    # first roles prefer a skill term (owned before learning, skipped when
    # already in the role); the rest keep fresher terms for fresher profiles.
    top_cities = cities[:4]
    used_skill_terms: set = set()
    for index, role in enumerate(roles):
        if index < SKILL_TERM_ROLES:
            skill_term = _skill_term(role, owned, learning, used_skill_terms)
            if skill_term is not None:
                city = top_cities[index % len(top_cities)]
                _add(_role_query(role, skill_term, city), role, city)
                continue
        term = FRESHER_TERMS[index % len(FRESHER_TERMS)] if fresher else ""
        city = top_cities[index % len(top_cities)]
        _add(_role_query(role, term, city), role, city)
    # Tier 3: remote variant when the profile allows it.
    if profile.remote_ok:
        for role in roles[:3]:
            _add(_role_query(role, "intern" if fresher else "", "remote"), role, "remote")
    generic = list(queries)
    # Tier 4: source-targeted site queries (existing helper, shared budget).
    # Six slots rotate job boards first, then ATS, across the top three
    # roles and top two non-remote locations — every host covered once per
    # run without any Cartesian explosion.
    site_roles = roles[:3]
    site_locs = cities[:2]
    site_hosts = list(JOB_BOARD_HINTS) + list(SITE_HINTS)
    site_term = "Intern" if fresher else ""
    ordered_site = []
    for index, host in enumerate(site_hosts[:SITE_QUERY_BUDGET]):
        role = site_roles[index % len(site_roles)]
        place = site_locs[(index // len(site_roles)) % len(site_locs)] if site_locs else ""
        ordered_site.extend(generate_site_queries(
            [role], sites=[host], max_queries=1, location=place, role_term=site_term))
    site_queries = [item for item in ordered_site if item.query and item.query not in seen]
    for item in site_queries:
        seen.add(item.query)
    blended: list = []
    if generic:
        blended.append(generic[0])
    pending_generic, pending_site = generic[1:], list(site_queries)
    while pending_generic or pending_site:
        if pending_site:
            blended.append(pending_site.pop(0))
        for _ in range(2):
            if pending_generic:
                blended.append(pending_generic.pop(0))
    return blended[: max(0, int(max_queries))]


def generate_site_queries(roles: list = None, sites: list = None, max_queries: int = 9,
                        location: str = "", role_term: str = "Intern") -> list:
    """Source-scoped hints, e.g. ``site:jobs.lever.co "Java Developer Intern"``.

    These are query *strings* for a provider to execute — never fetched here.
    ``location`` (a city/country facet, "" for none) is appended so
    source-targeted queries stay profile-relevant; empty preserves the
    legacy exact strings. ``role_term`` qualifies the role ("Intern" for
    fresher profiles, "" for experienced ones so senior queries stay clean).
    """
    roles = [r for r in (roles or DEFAULT_ROLES[:3]) if r.strip()]
    sites = list(sites or SITE_HINTS)
    place = f" {location.strip()}" if location and location.strip() else ""
    queries: list = []
    seen = set()
    for role in roles:
        for site in sites:
            query = f'{site} "{_with_term(role, role_term)}"{place}'.strip()
            if query not in seen:
                seen.add(query)
                queries.append(SearchQuery(query=query, role=role, location="", site_hint=site))
            if len(queries) >= max(0, int(max_queries)):
                return queries
    return queries


def search_profile_from_candidate(candidate: dict) -> SearchProfile:
    """Map a DB candidate bundle (load_candidate shape) onto SearchProfile.

    Pure function: target roles/locations drive queries, skills and
    experience ride along for present/future consumers. Empty facets fall
    back to the module defaults so discovery never runs with zero queries.
    """
    candidate = candidate or {}
    roles = [str(r).strip() for r in (candidate.get("target_roles") or []) if str(r).strip()]
    locations = [str(loc).strip() for loc in (candidate.get("target_locations") or []) if str(loc).strip()]
    owned = [str(s).strip() for s in (candidate.get("skills") or []) if str(s).strip()]
    learning = [str(s).strip() for s in (candidate.get("learning") or []) if str(s).strip()]
    experience = str(candidate.get("status") or "").strip()
    return SearchProfile(
        roles=roles or list(DEFAULT_ROLES),
        skills=owned,
        learning_skills=learning,
        locations=locations or list(DEFAULT_LOCATIONS),
        remote_ok=bool(candidate.get("remote_ok", True)),
        experience_level=experience or "Fresher",
    )


def load_search_profile(profile_id=None) -> SearchProfile:
    """DB-backed SearchProfile for live discovery (defaults when unavailable).

    Returns module defaults when the database is unconfigured, the profile
    is missing, or anything fails — discovery stays healthy offline. Never
    raises, never touches the network beyond the local database driver.
    """
    try:
        from worker.db import client as db_client
        from worker.db import profile_repository as profiles

        if not db_client.is_configured():
            return SearchProfile()
        candidate = profiles.load_candidate(profile_id)
    except Exception:
        return SearchProfile()
    if not candidate:
        return SearchProfile()
    return search_profile_from_candidate(candidate)

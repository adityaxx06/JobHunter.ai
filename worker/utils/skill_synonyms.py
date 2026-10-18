"""Deterministic skill normalization (Phase 7C). Pure Python, no AI.

Maps common skill aliases to one canonical token so matching never misses
on spelling alone ("JS" vs "JavaScript"). Deliberately tiny and explicit:
whole-token matches only — never substring guessing, so "C" cannot match
arbitrary words and "Java" never collapses into "JavaScript" (nor the
reverse). Fingerprints and stored skills are untouched; this layer only
informs matching decisions.
"""

import re

#: Alias -> canonical token. Whole tokens only; keep this list short and
#: unambiguous. Never add bare single letters or broad families here.
SKILL_SYNONYMS = {
    "js": "javascript",
    "ts": "typescript",
    "postgres": "postgresql",
    "reactjs": "react",
    "vuejs": "vue",
}

_WS = re.compile(r"\s+")


def canonical_skill(name: object) -> str:
    """Lowercased, whitespace-collapsed skill with aliases resolved ("" for junk)."""
    if not isinstance(name, str):
        return ""
    token = _WS.sub(" ", name.strip().lower())
    if not token:
        return ""
    return SKILL_SYNONYMS.get(token, token)


def skills_match(first: object, second: object) -> bool:
    """True when two skill names denote the same skill (case/alias-insensitive)."""
    left, right = canonical_skill(first), canonical_skill(second)
    return bool(left) and left == right

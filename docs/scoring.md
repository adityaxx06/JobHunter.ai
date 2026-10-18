# Scoring (draft, not implemented yet)

- Match score: role/skill fit vs configurable profile (`ai/match_engine/`).
- Trust score: source + posting legitimacy (`ai/trust_engine/`).
- Rank: combine match x trust; direct-link postings first.
- Prompts versioned in `ai/prompts/`, outputs in `ai/schemas/`.

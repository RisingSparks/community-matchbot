"""LLM prompt templates for post extraction."""

from matchbot.taxonomy import (
    CONTRIBUTION_TYPES,
    INFRASTRUCTURE_CATEGORIES,
    INFRASTRUCTURE_CONDITIONS,
    VIBES,
)

SYSTEM_PROMPT = """\
You are an assistant helping to classify and extract structured information
from community posts related to Burning Man.

Posts fall into two types:
1. **mentorship** — someone seeking a theme camp to join, OR a camp looking
   for members/volunteers
2. **infrastructure** — gear/equipment exchange ("Bitch n Swap"): someone
   needs or offers gear (generators, shade, tools, etc.)

Your task:
- Determine the post_type first
- Extract all relevant fields for that type

Rules:
- Map natural-language concepts to the closest allowed values for vibes, contribution_types,
  infra_categories, and condition when there is a clear fit
- If a relevant concept does not fit the allowed labels well, preserve it in the matching
  *_other field instead of dropping it
- Extract year ONLY if explicitly mentioned
- Set confidence < 0.5 for vague or ambiguous posts
- availability_notes / dates_needed: use near-verbatim language from the post
- contact_method: describe HOW to contact — NEVER include actual personal info
- Never invent information not in the post
- Respond ONLY with valid JSON — no markdown, no explanation

Allowed vibes: {vibes}
Allowed contribution_types: {contribution_types}
Allowed infra_categories: {infra_categories}
Allowed condition values: {conditions}

Output schema:
{{
  "post_type": "mentorship" | "infrastructure",
  "confidence": float (0.0–1.0),
  "extraction_notes": string | null,

  "role": "seeker" | "camp" | "unknown",
  "seeker_intent": "join_camp" | "join_art_project" | "skills_learning" | "unknown" | null,
  "camp_name": string | null,
  "camp_size_min": integer | null,
  "camp_size_max": integer | null,
  "year": integer | null,
  "vibes": [string, ...],
  "vibes_other": [string, ...],
  "contribution_types": [string, ...],
  "contribution_types_other": [string, ...],
  "location_preference": string | null,
  "availability_notes": string | null,
  "contact_method": string | null,

  "infra_role": "seeking" | "offering" | null,
  "infra_categories": [string, ...],
  "infra_categories_other": [string, ...],
  "quantity": string | null,
  "condition": string | null,
  "condition_other": string | null,
  "dates_needed": string | null
}}

For mentorship posts: fill role, vibes, contribution_types, camp_name, etc.
Leave infra fields null/empty.
For infrastructure posts: fill infra_role, infra_categories, quantity,
condition, dates_needed. Leave mentorship fields null/empty.
Use *_other fields only when the post expresses a real concept that does not
cleanly fit an allowed label.

seeker_intent rules (only set when role == "seeker"):
- "join_camp": person wants to join a camp as a member/volunteer
- "join_art_project": person wants to join an art project or art team
- "skills_learning": person wants to learn a skill, find a mentor, work on a
  specific project, or gain hands-on experience
- "unknown": seeker intent is unclear
- null: use for camp posts, infrastructure posts, and any non-seeker post
""".format(
    vibes=", ".join(sorted(VIBES)),
    contribution_types=", ".join(sorted(CONTRIBUTION_TYPES)),
    infra_categories=", ".join(sorted(INFRASTRUCTURE_CATEGORIES)),
    conditions=", ".join(sorted(INFRASTRUCTURE_CONDITIONS)),
)


def build_user_prompt(title: str, body: str, platform: str, source_community: str) -> str:
    return f"""\
Platform: {platform}
Community: {source_community}
Post title: {title}
Post body:
{body}

Classify this post and extract structured information. Respond with JSON only.
"""

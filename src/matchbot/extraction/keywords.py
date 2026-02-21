"""Deterministic keyword pre-filter — no LLM calls."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from matchbot.db.models import InfraRole, PostRole, PostType

# ---------------------------------------------------------------------------
# Mentorship patterns (camp-finding)
# ---------------------------------------------------------------------------

_SEEKER_PATTERNS = [
    r"\bseeking\s+(?:a\s+)?camp\b",
    r"\blooking\s+for\s+(?:a\s+)?camp\b",
    r"\bneed(?:ing)?\s+(?:a\s+)?camp\b",
    r"\bwant(?:ing)?\s+(?:to\s+)?(?:join|find)\s+(?:a\s+)?camp\b",
    r"\bbirgin\b",
    r"\bfirst[\s.\-]?time[r]?\b",
    r"\bfirst\s+burn\b",
    r"\bnewbie\b",
    r"\bnoob\b",
    r"\bnewcomer\b",
    r"\bwilling\s+to\s+(?:build|cook|contribute|help|work)\b",
    r"\bcan\s+(?:help\s+with|contribute|build|cook)\b",
    r"\boffering\s+(?:my\s+)?(?:skills?|help|time|labor)\b",
    r"\bopen\s+to\s+(?:joining|any)\s+camp\b",
    r"\bhave\s+skills?\b",
    r"\bcamp\s+(?:mate|member|spot)\s+(?:wanted|needed|available)\b",
    r"\biso\s+(?:a\s+)?camp\b",
    r"\bin\s+search\s+of\s+(?:a\s+)?camp\b",
]

_CAMP_PATTERNS = [
    r"\bcamp\s+(?:has\s+)?openings?\b",
    r"\bcamp\s+(?:is\s+)?(?:recruiting|accepting)\b",
    r"\bcamp\s+spots?\s+(?:available|open|left)\b",
    r"\brecruiting\s+(?:new\s+)?(?:members?|builders?|volunteers?|campers?)\b",
    r"\blooking\s+for\s+(?:a\s+)?(?:builder|volunteer|member|camper|cook|medic|artist)\b",
    r"\bopen\s+(?:to\s+)?applicat",
    r"\bapplications?\s+(?:open|now\s+open|being\s+accepted)\b",
    r"\bjoin\s+(?:our|my)\s+camp\b",
    r"\bwe\s+(?:are\s+)?(?:looking|seeking|recruiting)\b.*\b(?:member|volunteer|builder|camper)\b",
    r"\btheme\s+camp\s+(?:has|with|seeking)\b",
    r"\bcamp\s+members?\s+wanted\b",
    r"\bcamp\s+(?:is\s+)?(?:full|not\s+accepting)\b",
    r"\bwe\s+have\s+space\b",
    r"\bwe\s+have\s+(?:open\s+)?spots?\b",
    r"\bspace\s+(?:for|available\s+for)\s+(?:one|two|a\s+few|more|new)?\s*(?:person|people|member|builder|volunteer)\b",
]

# ---------------------------------------------------------------------------
# Infrastructure / "Bitch n Swap" patterns
# ---------------------------------------------------------------------------

_INFRA_SEEKING_PATTERNS = [
    r"\bneed(?:ing)?\s+(?:a\s+|an\s+)?(?:generator|solar|power|shade|tarp|canopy|trailer|truck|tool|kitchen|stove|radio|speaker)\b",
    r"\blooking\s+(?:to\s+)?(?:borrow|rent)\b",
    r"\biso\b.{0,40}\b(?:generator|shade|tarp|power|tool|trailer|truck|kitchen)\b",
    r"\bwho\s+has\s+(?:a\s+|an\s+)?(?:generator|solar|shade|tarp|trailer|truck|tool)\b",
    r"\banyone\s+(?:have|has|lending|renting)\b",
    r"\bcan\s+someone\s+(?:lend|loan|spare|share)\b",
    r"\bneeded?\s*:\s*(?:generator|shade|tarp|power|tool|trailer|truck|kitchen|speaker|radio)\b",
    r"\blooking\s+for\s+(?:to\s+)?(?:borrow|rent|acquire)\b",
    r"\bwanted\b.{0,30}\b(?:generator|shade|tarp|power|tool|trailer|truck|kitchen)\b",
    r"\bseeking\s+(?:gear|equipment|tools?|shade|power|generator)\b",
]

_INFRA_OFFERING_PATTERNS = [
    r"\bhave\s+(?:a\s+|an\s+|extra\s+|spare\s+)?(?:generator|solar|shade|tarp|canopy|trailer|truck|tool|kitchen|stove|radio|speaker)\b",
    r"\boffering\s+(?:to\s+)?(?:lend|loan|share|rent|give|sell)\b",
    r"\bcan\s+(?:lend|loan|share|spare)\b",
    r"\b(?:lending|loaning|sharing|renting|giving\s+away)\b.{0,40}\b(?:generator|shade|tarp|power|tool|trailer|truck|kitchen)\b",
    r"\bfree\s+(?:to\s+)?(?:a\s+good\s+)?home\b",
    r"\bswap\b.{0,30}\b(?:for|to|or)\b",
    r"\bbitch\s+n\s+swap\b",
    r"\bsurplus\b.{0,30}\b(?:generator|shade|tarp|power|tool|trailer|truck|kitchen|gear|equipment)\b",
    r"\b(?:for|available)\s+(?:borrow|loan|rent|free)\b",
    r"\bgiving\s+away\b",
    r"\bavailable\s+to\s+(?:lend|loan|share|borrow)\b",
    r"\b(?:generator|shade|tarp|canopy|trailer|truck|tool|kitchen|stove)\b.{0,40}\b(?:available|for\s+loan|to\s+borrow|to\s+rent|free)\b",
]


@dataclass
class KeywordResult:
    matched: bool
    candidate_role: str          # PostRole value (mentorship path)
    post_type: str = PostType.MENTORSHIP  # mentorship | infrastructure
    infra_role: str | None = None         # seeking | offering (infra path only)


def keyword_filter(title: str, body: str) -> KeywordResult:
    """
    Run regex patterns against title+body text.

    Returns KeywordResult with:
    - matched=False if no patterns match (post should be SKIPPED)
    - post_type: mentorship | infrastructure
    - For mentorship: candidate_role seeker | camp | unknown
    - For infrastructure: infra_role seeking | offering
    """
    text = f"{title}\n{body}".lower()

    # Check infrastructure patterns first (more specific)
    infra_seeking = _any_match(text, _INFRA_SEEKING_PATTERNS)
    infra_offering = _any_match(text, _INFRA_OFFERING_PATTERNS)

    if infra_seeking or infra_offering:
        # Determine infra role
        if infra_seeking and infra_offering:
            infra_role = InfraRole.SEEKING  # default to seeking if ambiguous
        elif infra_seeking:
            infra_role = InfraRole.SEEKING
        else:
            infra_role = InfraRole.OFFERING
        return KeywordResult(
            matched=True,
            candidate_role=PostRole.UNKNOWN,
            post_type=PostType.INFRASTRUCTURE,
            infra_role=infra_role,
        )

    # Check mentorship patterns
    seeker_match = _any_match(text, _SEEKER_PATTERNS)
    camp_match = _any_match(text, _CAMP_PATTERNS)

    if not seeker_match and not camp_match:
        return KeywordResult(matched=False, candidate_role=PostRole.UNKNOWN)

    if seeker_match and camp_match:
        return KeywordResult(matched=True, candidate_role=PostRole.UNKNOWN)

    if seeker_match:
        return KeywordResult(matched=True, candidate_role=PostRole.SEEKER)

    return KeywordResult(matched=True, candidate_role=PostRole.CAMP)


def _any_match(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)

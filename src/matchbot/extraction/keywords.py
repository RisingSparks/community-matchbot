"""Deterministic keyword pre-filter — no LLM calls."""

from __future__ import annotations

import re
from dataclasses import dataclass

from matchbot.db.models import PostRole

# ---------------------------------------------------------------------------
# Pattern sets
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
    r"\bcamp\s+(?:is\s+)?(?:full|not\s+accepting)\b",  # negative signal — still relevant
    r"\bwe\s+have\s+space\b",
    r"\bwe\s+have\s+(?:open\s+)?spots?\b",
    r"\bspace\s+(?:for|available\s+for)\s+(?:one|two|a\s+few|more|new)?\s*(?:person|people|member|builder|volunteer)\b",
]


@dataclass
class KeywordResult:
    matched: bool
    candidate_role: str  # PostRole value


def keyword_filter(title: str, body: str) -> KeywordResult:
    """
    Run regex patterns against title+body text.

    Returns KeywordResult with:
    - matched=False if no patterns match (post should be SKIPPED)
    - candidate_role: seeker | camp | unknown (both matched)
    """
    text = f"{title}\n{body}".lower()

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

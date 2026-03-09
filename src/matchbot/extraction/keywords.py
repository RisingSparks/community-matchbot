"""Deterministic keyword pre-filter — no LLM calls."""

from __future__ import annotations

import re
from dataclasses import dataclass

from matchbot.db.models import InfraRole, PostRole, PostType

# ---------------------------------------------------------------------------
# Mentorship patterns (camp-finding)
# ---------------------------------------------------------------------------

_SEEKER_PATTERNS = [
    r"\bseeking\s+(?:a\s+)?camp\b",
    r"\blooking\s+for\s+(?:a\s+)?camp\b",
    r"\bneed(?:ing)?\s+(?:a\s+)?camp\b",
    r"\bwant(?:ing)?\s+(?:to\s+)?(?:join|find)\s+(?:\w+\s+)?camp\b",
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
    tier: str = "no_match"                # hard_match | soft_match | no_match
    score: int = 0
    reasons: tuple[str, ...] = ()


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
            tier="hard_match",
            score=100,
            reasons=("infra_regex",),
        )

    # Check mentorship patterns
    seeker_match = _any_match(text, _SEEKER_PATTERNS)
    camp_match = _any_match(text, _CAMP_PATTERNS)

    if seeker_match and camp_match:
        return KeywordResult(
            matched=True,
            candidate_role=PostRole.UNKNOWN,
            tier="hard_match",
            score=100,
            reasons=("seeker_regex", "camp_regex"),
        )

    if seeker_match:
        return KeywordResult(
            matched=True,
            candidate_role=PostRole.SEEKER,
            tier="hard_match",
            score=100,
            reasons=("seeker_regex",),
        )

    if camp_match:
        return KeywordResult(
            matched=True,
            candidate_role=PostRole.CAMP,
            tier="hard_match",
            score=100,
            reasons=("camp_regex",),
        )

    score, role, reasons = _score_mentorship_signals(text)
    if score >= 5:
        return KeywordResult(
            matched=True,
            candidate_role=role,
            tier="hard_match",
            score=score,
            reasons=tuple(reasons),
        )
    if score >= 3:
        return KeywordResult(
            matched=False,
            candidate_role=role,
            tier="soft_match",
            score=score,
            reasons=tuple(reasons),
        )

    return KeywordResult(
        matched=False,
        candidate_role=PostRole.UNKNOWN,
        tier="no_match",
        score=score,
        reasons=tuple(reasons),
    )


def _any_match(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


_TARGET_OBJECT_PATTERNS: dict[str, list[str]] = {
    "camp_object": [
        r"\bcamp\b",
        r"\btheme\s+camp\b",
        r"\bart\s+project\b",
        r"\bart\s+team\b",
        r"\bbuild\s+crew\b",
        r"\bcrew\b",
        r"\bteam\b",
        r"\bvillage\b",
    ],
    "join_verb": [
        r"\bjoin(?:ing)?\b",
        r"\bfind\b",
        r"\blooking\b",
        r"\bseeking\b",
        r"\binterested\b",
        r"\bwant\b",
        r"\blove\b",
        r"\bhoping\b",
        r"\bopen\s+to\b",
    ],
    "contribution": [
        r"\bbuild(?:ing|er)?\b",
        r"\bhelp\b",
        r"\bvolunteer(?:ing)?\b",
        r"\bbartend(?:ing)?\b",
        r"\bkitchen\b",
        r"\bstrike\b",
        r"\bsetup\b",
        r"\bdecorate(?:ing)?\b",
        r"\bcook(?:ing)?\b",
        r"\bmentor(?:ing)?\b",
        r"\bfire\s+spinning\b",
    ],
    "experience": [
        r"\bfirst[\s.\-]?time[r]?\b",
        r"\bfirst\s+burn\b",
        r"\bnew(?:bie|comer)?\b",
        r"\bI\s+have\s+experience\b",
        r"\bI[' ]?ve\s+done\b",
        r"\bI\s+can\b",
        r"\bskills?\b",
    ],
    "preference": [
        r"\bideally\b",
        r"\bwould\s+love\b",
        r"\binterested\s+in\b",
        r"\blooking\s+for\s+a\s+camp\s+that\b",
        r"\bjoin(?:ing)?\s+a\s+camp\s+that\b",
    ],
    "camp_supply": [
        r"\bopenings?\b",
        r"\bspots?\b",
        r"\bspace\b",
        r"\brecruiting\b",
        r"\baccepting\b",
        r"\bmembers?\b",
        r"\bbuilders?\b",
        r"\bvolunteers?\b",
        r"\bneed\s+help\b",
    ],
    "negative": [
        r"\btraffic\b",
        r"\bweather\b",
        r"\bwhat\s+to\s+wear\b",
        r"\bpacking\s+list\b",
        r"\bwho\s+is\s+going\b",
        r"\btheme\s+\"?[^\n]+\"?\b",
        r"\btickets?\b",
    ],
}


def _score_mentorship_signals(text: str) -> tuple[int, str, list[str]]:
    score = 0
    reasons: list[str] = []

    if _has_proximity(
        text,
        _TARGET_OBJECT_PATTERNS["camp_object"],
        _TARGET_OBJECT_PATTERNS["join_verb"],
        8,
    ):
        score += 5
        reasons.append("object_join_proximity")

    if _has_proximity(
        text,
        _TARGET_OBJECT_PATTERNS["camp_object"],
        _TARGET_OBJECT_PATTERNS["contribution"],
        12,
    ):
        score += 4
        reasons.append("object_contribution_proximity")

    if (
        _any_match(text, _TARGET_OBJECT_PATTERNS["camp_object"])
        and _any_match(text, _TARGET_OBJECT_PATTERNS["experience"])
    ):
        score += 2
        reasons.append("object_experience")

    if (
        _any_match(text, _TARGET_OBJECT_PATTERNS["camp_object"])
        and _any_match(text, _TARGET_OBJECT_PATTERNS["preference"])
    ):
        score += 2
        reasons.append("object_preference")

    if (
        _any_match(text, _TARGET_OBJECT_PATTERNS["experience"])
        and _any_match(text, _TARGET_OBJECT_PATTERNS["contribution"])
    ):
        score += 2
        reasons.append("experience_contribution")

    if _has_proximity(
        text,
        _TARGET_OBJECT_PATTERNS["camp_object"],
        _TARGET_OBJECT_PATTERNS["camp_supply"],
        10,
    ):
        score += 5
        reasons.append("object_supply_proximity")

    if _any_match(text, _TARGET_OBJECT_PATTERNS["negative"]) and score < 5:
        score -= 2
        reasons.append("negative_context")

    role = PostRole.UNKNOWN
    if "object_supply_proximity" in reasons:
        role = PostRole.CAMP
    elif any(reason in reasons for reason in (
        "object_join_proximity",
        "object_contribution_proximity",
        "object_experience",
        "object_preference",
        "experience_contribution",
    )):
        role = PostRole.SEEKER

    return max(score, 0), role, reasons


def _has_proximity(
    text: str,
    left_patterns: list[str],
    right_patterns: list[str],
    max_words: int,
) -> bool:
    tokens = re.findall(r"\b\w+\b", text)
    if not tokens:
        return False

    left_ranges = _match_token_ranges(tokens, left_patterns)
    right_ranges = _match_token_ranges(tokens, right_patterns)

    for left_start, left_end in left_ranges:
        for right_start, right_end in right_ranges:
            gap = min(abs(right_start - left_end), abs(left_start - right_end))
            if gap <= max_words:
                return True
    return False


def _match_token_ranges(tokens: list[str], patterns: list[str]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    joined = " ".join(tokens)
    offsets: list[tuple[int, int]] = []
    cursor = 0
    for token in tokens:
        start = cursor
        end = start + len(token)
        offsets.append((start, end))
        cursor = end + 1

    for pattern in patterns:
        for match in re.finditer(pattern, joined):
            token_start = _char_to_token_index(offsets, match.start())
            token_end = _char_to_token_index(offsets, match.end() - 1)
            if token_start is not None and token_end is not None:
                ranges.append((token_start, token_end))
    return ranges


def _char_to_token_index(offsets: list[tuple[int, int]], pos: int) -> int | None:
    for idx, (start, end) in enumerate(offsets):
        if start <= pos < end:
            return idx
    return None

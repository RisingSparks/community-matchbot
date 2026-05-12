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
    r"\bfirst[\s.\-]?time(?:r)?\s+(?:burner|going|at\s+burning\s+man|to\s+the\s+burn)\b",
    r"\bfirst\s+burn\b",
    r"\bnewbie\b",
    r"\bnoob\b",
    r"\bnewcomer\b",
    r"\bwilling\s+to\s+(?:build|cook|contribute|help|work)\b",
    r"\bcan\s+(?:help\s+with|build|cook)\b",
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
    (
        r"\bneed(?:ing)?\s+(?:a\s+|an\s+)?(?:generator|solar|power|shade|tarp|canopy|"
        r"trailer|truck|tool|kitchen|stove|radio|speaker|scaffold(?:ing)?|shower(?:\s+stall(?:s)?)?|"
        r"gazebo(?:s)?|temporary\s+structure(?:s)?|shade\s+structure(?:s)?|parts?)\b"
    ),
    r"\blooking\s+(?:to\s+)?(?:borrow|rent)\b",
    r"\biso\b.{0,40}\b(?:generator|shade|tarp|power|tool|trailer|truck|kitchen)\b",
    (
        r"\bwho\s+has\s+(?:a\s+|an\s+)?(?:generator|solar|shade|tarp|trailer|truck|tool|"
        r"scaffold(?:ing)?|shower(?:\s+stall(?:s)?)?|gazebo(?:s)?|canopy(?:ies)?|parts?)\b"
    ),
    r"\banyone\s+(?:have|has|lending|renting)\b",
    r"\bcan\s+someone\s+(?:lend|loan|spare|share)\b",
    (
        r"\bneeded?\s*:\s*(?:generator|shade|tarp|power|tool|trailer|truck|kitchen|speaker|"
        r"radio|scaffold(?:ing)?|shower(?:\s+stall(?:s)?)?|gazebo(?:s)?|canopy(?:ies)?|parts?)\b"
    ),
    r"\blooking\s+for\s+(?:to\s+)?(?:borrow|rent|acquire)\b",
    r"\bwanted\b.{0,30}\b(?:generator|shade|tarp|power|tool|trailer|truck|kitchen)\b",
    (
        r"\bseeking\s+(?:gear|equipment|tools?|shade|power|generator|scaffold(?:ing)?|"
        r"shower(?:\s+stall(?:s)?)?|gazebo(?:s)?|canopy(?:ies)?|parts?)\b"
    ),
]

_INFRA_OFFERING_PATTERNS = [
    (
        r"\bhave\s+(?:a\s+|an\s+|extra\s+|spare\s+)?(?:generator|solar|shade|tarp|canopy|"
        r"trailer|truck|tool|kitchen|stove|radio|speaker|scaffold(?:ing)?|shower(?:\s+stall(?:s)?)?|"
        r"gazebo(?:s)?|temporary\s+structure(?:s)?|shade\s+structure(?:s)?|parts?)\b"
    ),
    r"\boffering\s+(?:to\s+)?(?:lend|loan|share|rent|give|sell)\b",
    r"\bcan\s+(?:lend|loan|share|spare)\b",
    (
        r"\b(?:lending|loaning|sharing|renting|giving\s+away|selling(?:\s+my|\s+off)?)\b.{0,40}\b"
        r"(?:generator|shade|tarp|power|tool|trailer|truck|kitchen|scaffold(?:ing)?|"
        r"shower(?:\s+stall(?:s)?)?|gazebo(?:s)?|canopy(?:ies)?|parts?)\b"
    ),
    r"\bfree\s+(?:to\s+)?(?:a\s+good\s+)?home\b",
    r"\bswap\b.{0,30}\b(?:for|to|or)\b",
    r"\bbitch\s+n\s+swap\b",
    (
        r"\bsurplus\b.{0,30}\b(?:generator|shade|tarp|power|tool|trailer|truck|kitchen|gear|"
        r"equipment|scaffold(?:ing)?|shower(?:\s+stall(?:s)?)?|gazebo(?:s)?|canopy(?:ies)?|parts?)\b"
    ),
    r"\b(?:for|available)\s+(?:borrow|loan|rent|free)\b",
    (
        r"\b(?:for\s+sale|sale)\b.{0,60}\b(?:generator|solar|shade|tarp|canopy|trailer|truck|"
        r"tool|kitchen|stove|radio|speaker|scaffold(?:ing)?|shower(?:\s+stall(?:s)?)?|gazebo(?:s)?|"
        r"parts?|rv|motorhome|camper|travel\s+trailer|fifth\s+wheel|toy\s+hauler)\b"
    ),
    (
        r"\b(?:generator|solar|shade|tarp|canopy|trailer|truck|tool|kitchen|stove|radio|speaker|"
        r"scaffold(?:ing)?(?:\s+tower(?:s)?)?|shower(?:\s+stall(?:s)?)?|gazebo(?:s)?|parts?)\b"
        r".{0,60}\b(?:for\s+sale|sale)\b"
    ),
    (
        r"\b(?:selling|selling\s+off|selling\s+my)\b.{0,60}\b(?:generator|solar|shade|tarp|canopy|"
        r"trailer|truck|tool|kitchen|stove|radio|speaker|scaffold(?:ing)?|shower(?:\s+stall(?:s)?)?|"
        r"gazebo(?:s)?|parts?|rv|motorhome|camper|travel\s+trailer|fifth\s+wheel|toy\s+hauler)\b"
    ),
    r"\bgiving\s+away\b",
    r"\bavailable\s+to\s+(?:lend|loan|share|borrow)\b",
    (
        r"\b(?:generator|shade|tarp|canopy|trailer|truck|tool|kitchen|stove|scaffold(?:ing)?|"
        r"shower(?:\s+stall(?:s)?)?|gazebo(?:s)?|parts?)\b.{0,40}\b(?:available|for\s+loan|to\s+borrow|"
        r"to\s+rent|free)\b"
    ),
]

_RV_RENTAL_SUPPRESSOR_PATTERNS = [
    r"\brenting\s+out\s+my\s+(?:rv|motorhome|camper|travel\s+trailer|fifth\s+wheel|toy\s+hauler)\b",
    r"\b(?:rv|motorhome|camper|travel\s+trailer|fifth\s+wheel|toy\s+hauler|recreational\s+vehicle)s?\b.{0,80}\b(?:rent|rental|for\s+rent|for\s+sale|available)\b",
    r"\b(?:rent|rental|available)\b.{0,40}\b(?:rv|motorhome|camper|travel\s+trailer|fifth\s+wheel|toy\s+hauler)\b",
    r"\b(?:rv|motorhome|camper|travel\s+trailer|fifth\s+wheel|toy\s+hauler|recreational\s+vehicle)s?\b.{0,80}\b(?:pickup|delivery|deposit|sleeps)\b",
    r"\b(?:playa[- ]ready|camp[- ]ready)\b.{0,80}\b(?:rv|motorhome|camper)\b",
]

_RV_RENTAL_LISTING_PATTERNS = [
    r"\brv\s+rentals?\b",
    r"\bmotorhomes?\s+for\s+rent\b",
    r"\bfor\s+sale\s+or\s+rent\b",
    r"\bsale\s+or\s+rent\b",
    r"\brv\s+for\s+rent\b",
    r"\brv\s+to\s+rent\b",
    r"\bmotorhomes?\s+available\s+for\s+rent\b",
    r"\brvs?\s+available\b",
    r"\bavailable\s+for\s+rent\b",
    r"\bavailable\s+to\s+rent\b",
    r"\b(?:rv|motorhome|camper|travel\s+trailer|fifth\s+wheel|toy\s+hauler|recreational\s+vehicle)s?\s+rental(?:s)?\b",
    r"\bclass\s+[ac]\s+motorhomes?\b",
    r"\bclass\s+[ac]\s+gas\s+motorhomes?\b",
]

_INFRA_STRONG_OFFERING_PATTERNS = [
    r"\b(?:for\s+sale|sale)\b",
    r"\b(?:selling|selling\s+off|selling\s+my)\b",
    r"\bfree\s+(?:to\s+)?(?:a\s+good\s+)?home\b",
    r"\bgiving\s+away\b",
    r"\bbitch\s+n\s+swap\b",
    r"\brenting\s+out\b",
    r"\boffering\s+(?:to\s+)?(?:lend|loan|share|rent|give|sell)\b",
    r"\bswap\b.{0,30}\b(?:for|to|or)\b",
    r"\bstill\s+available\b",
    r"\bmessage\s+me\s+for\s+details\b",
    r"\bdelivery\s+included\b",
    r"\blet'?s\s+make\s+a\s+deal\b",
    r"\bi\s+got\s+these\b",
    r"\bi\s+have\s+these\b",
    r"\bavailable\s+for\s+pickup\b",
    r"\bpickup\s+from\b",
    r"\bwhich\s+camp\s+needs\b",
    r"\banyone\s+need\b",
]

# ---------------------------------------------------------------------------
# Noise / Suppression patterns
# ---------------------------------------------------------------------------

_NOISE_PATTERNS = [
    r"\blet'?s\s+welcome\s+our\s+new\s+members\b",
    r"\bwelcome\s+our\s+new(?:est)?\s+members\b",
    r"\bplease\s+welcome\s+our\s+new\s+members\b",
    r"\bwelcome\s+to\s+the\s+group\b",
]


def is_noise_post(title: str, body: str) -> bool:
    """Return True if the post looks like an automated 'Welcome new members' or similar noise."""
    text = f"{title}\n{body}".lower()
    normalized = " ".join(text.split())
    return _any_match(normalized, _NOISE_PATTERNS)


@dataclass
class KeywordResult:
    matched: bool
    candidate_role: str  # PostRole value (kept for compatibility; mentorship defaults unknown)
    post_type: str = PostType.MENTORSHIP  # mentorship | infrastructure
    infra_role: str | None = None  # seeking | offering (infra path only)
    tier: str = "no_match"  # hard_match | soft_match | no_match
    score: int = 0
    reasons: tuple[str, ...] = ()


def keyword_filter(title: str, body: str) -> KeywordResult:
    """
    Run regex patterns against title+body text.

    Returns KeywordResult with:
    - matched=False if no patterns match (post should be SKIPPED)
    - post_type: mentorship | infrastructure
    - For mentorship: candidate_role is always unknown; the LLM owns seeker/camp classification
    - For infrastructure: infra_role seeking | offering
    """
    if is_noise_post(title, body):
        return KeywordResult(
            matched=False,
            candidate_role=PostRole.UNKNOWN,
            tier="no_match",
            score=0,
            reasons=("noise_suppression",),
        )

    text = f"{title}\n{body}".lower()

    # Check infrastructure patterns first (more specific)
    if _looks_like_rv_rental_listing(text):
        return KeywordResult(
            matched=False,
            candidate_role=PostRole.UNKNOWN,
            tier="no_match",
            score=0,
            reasons=("rv_rental_suppression",),
        )

    infra_seeking = _any_match(text, _INFRA_SEEKING_PATTERNS)
    infra_offering = _any_match(text, _INFRA_OFFERING_PATTERNS)

    if infra_seeking or infra_offering:
        # Determine infra role
        if infra_seeking and infra_offering:
            infra_role = (
                InfraRole.OFFERING
                if _any_match(text, _INFRA_STRONG_OFFERING_PATTERNS)
                else InfraRole.SEEKING
            )
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
            candidate_role=PostRole.UNKNOWN,
            tier="hard_match",
            score=100,
            reasons=("seeker_regex",),
        )

    if camp_match:
        return KeywordResult(
            matched=True,
            candidate_role=PostRole.UNKNOWN,
            tier="hard_match",
            score=100,
            reasons=("camp_regex",),
        )

    if _any_match(text, _MENTORSHIP_DISCUSSION_SUPPRESSOR_PATTERNS):
        return KeywordResult(
            matched=False,
            candidate_role=PostRole.UNKNOWN,
            tier="no_match",
            score=0,
            reasons=("discussion_suppressor",),
        )

    score, reasons = _score_mentorship_signals(text)
    if score >= 3:
        return KeywordResult(
            matched=False,
            candidate_role=PostRole.UNKNOWN,
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


def _looks_like_rv_rental_listing(text: str) -> bool:
    if _any_match(text, _RV_RENTAL_LISTING_PATTERNS):
        return True
    return _any_match(text, _RV_RENTAL_SUPPRESSOR_PATTERNS)


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
        r"\bnew(?:bie|comer)\b",
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


_MENTORSHIP_DISCUSSION_SUPPRESSOR_PATTERNS = [
    r"\bticket\s+aid\b",
    r"\btickets?\b",
    r"\bstewards?\s+sale\b",
    r"\bvehicle\s+passes?\b",
    r"\bvp'?s\b",
    r"\bresales?\b",
    r"\baftermarket\b",
    r"\ballocation\b",
    r"\broster\b",
    r"\bfill(?:ing)?\s+our\s+roster\b",
    r"\bcamp\s+lead\b",
    r"\bcamp\s+logistics?\b",
    r"\bcamp\s+admins?\b",
    r"\bcamp\s+operations?\b",
    r"\battendance\s+trends?\b",
    r"\bwhat\s+people'?s\s+thoughts?\s+are\b",
    r"\bcurious\s+what\s+people\s+think\b",
    r"\bcurious\s+the\s+dynamic\b",
    r"\bramblings?\b",
    r"\bharbinger\s+of\s+doom\b",
    r"\bshit\s+economy\b",
    r"\binternational\s+travel\b",
]


def _score_mentorship_signals(text: str) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    if _has_proximity(
        text,
        _TARGET_OBJECT_PATTERNS["camp_object"],
        _TARGET_OBJECT_PATTERNS["join_verb"],
        12,
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

    return max(score, 0), reasons


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

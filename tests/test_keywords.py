"""Tests for keyword pre-filter (no LLM calls)."""


from matchbot.db.models import PostRole
from matchbot.extraction.keywords import keyword_filter


class TestSeekerPatterns:
    def test_seeking_camp(self):
        result = keyword_filter("Seeking camp for Burning Man", "")
        assert result.matched is True
        assert result.candidate_role == PostRole.UNKNOWN

    def test_looking_for_camp(self):
        result = keyword_filter("Looking for a camp", "Need somewhere to stay at BM")
        assert result.matched is True
        assert result.candidate_role == PostRole.UNKNOWN

    def test_birgin(self):
        result = keyword_filter("Birgin here!", "First time going, looking for camp")
        assert result.matched is True
        assert result.candidate_role == PostRole.UNKNOWN

    def test_first_time(self):
        result = keyword_filter("First time burner", "")
        assert result.matched is True
        assert result.candidate_role == PostRole.UNKNOWN

    def test_first_time_phrase_not_burner_context(self):
        result = keyword_filter(
            "Poor ticket sales this year and other ramblings",
            "We didn't use our Stewards sale allocation this year, the first time in forever.",
        )
        assert result.matched is False
        assert result.tier == "no_match"

    def test_first_burn(self):
        result = keyword_filter("My first burn!", "Super excited. Looking to find my people.")
        assert result.matched is True
        assert result.candidate_role == PostRole.UNKNOWN

    def test_willing_to_build(self):
        result = keyword_filter("", "I'm willing to build and help with setup")
        assert result.matched is True
        assert result.candidate_role == PostRole.UNKNOWN

    def test_iso_camp(self):
        result = keyword_filter("ISO a camp for 2025", "")
        assert result.matched is True
        assert result.candidate_role == PostRole.UNKNOWN

    def test_in_search_of_camp(self):
        result = keyword_filter("In search of a camp", "")
        assert result.matched is True
        assert result.candidate_role == PostRole.UNKNOWN


class TestCampPatterns:
    def test_camp_has_openings(self):
        result = keyword_filter("Camp has openings for 2025", "")
        assert result.matched is True
        assert result.candidate_role == PostRole.UNKNOWN

    def test_camp_recruiting(self):
        result = keyword_filter("Camp is recruiting new members", "")
        assert result.matched is True
        assert result.candidate_role == PostRole.UNKNOWN

    def test_looking_for_builder(self):
        result = keyword_filter("", "We are looking for a builder to join our camp")
        assert result.matched is True
        assert result.candidate_role == PostRole.UNKNOWN

    def test_open_applications(self):
        result = keyword_filter("Applications open now!", "")
        assert result.matched is True
        assert result.candidate_role == PostRole.UNKNOWN

    def test_join_our_camp(self):
        result = keyword_filter("Join our camp at BM 2025", "")
        assert result.matched is True
        assert result.candidate_role == PostRole.UNKNOWN

    def test_camp_spots_available(self):
        result = keyword_filter("", "We have camp spots available for the right people")
        assert result.matched is True
        assert result.candidate_role == PostRole.UNKNOWN

    def test_space_for_volunteers(self):
        result = keyword_filter("", "We have space for a few volunteers")
        assert result.matched is True
        assert result.candidate_role == PostRole.UNKNOWN

    def test_recruiting_post_does_not_get_role_from_regex(self):
        result = keyword_filter(
            "Looking for people to wear lab coats and make strangers fill out fake paperwork in the desert",
            (
                "The Cognitive Research Institute is a new interactive camp coming to Black Rock City "
                "in 2026, and we're looking for a few more people who want to build it with us."
            ),
        )
        assert result.matched is False
        assert result.tier == "soft_match"
        assert result.candidate_role == PostRole.UNKNOWN


class TestNoMatch:
    def test_generic_post(self):
        result = keyword_filter("What to bring to Burning Man", "packing list advice needed")
        assert result.matched is False

    def test_random_question(self):
        result = keyword_filter("Weather forecast?", "Is it always so hot in August?")
        assert result.matched is False

    def test_empty_text(self):
        result = keyword_filter("", "")
        assert result.matched is False

    def test_tangential_camp_word(self):
        result = keyword_filter("Camping gear review", "I reviewed my tent and sleeping bag")
        assert result.matched is False


class TestAmbiguousRole:
    def test_both_patterns_returns_unknown(self):
        result = keyword_filter(
            "Seeking camp AND we have openings",
            "Looking for camp members — also our camp is recruiting",
        )
        assert result.matched is True
        assert result.candidate_role == PostRole.UNKNOWN

    def test_case_insensitive(self):
        result = keyword_filter("SEEKING CAMP FOR BURNING MAN", "WILLING TO BUILD")
        assert result.matched is True
        assert result.candidate_role == PostRole.UNKNOWN


class TestMentorshipFalsePositives:
    """Regression tests for posts wrongly classified as mentorship seekers."""

    def test_can_contribute_to_community_not_seeker(self):
        """'Can contribute' in general discussion must not hard-match as seeker."""
        result = keyword_filter(
            "Poor ticket sales this year and other ramblings",
            (
                "We should find ways to help people get tickets so they "
                "can contribute to the community."
            ),
        )
        # Should not be a hard-match seeker (may still soft-match via scoring)
        assert not (result.matched and result.tier == "hard_match"), (
            f"Unexpectedly hard-matched as mentorship seeker: reasons={result.reasons}"
        )

    def test_session_contributor_post_only_soft_matches(self):
        result = keyword_filter(
            "Seeking: Integrative therapy professionals for CFT",
            (
                "The Campfire Talks team is hoping to produce a session on Integrating your "
                "Burning Man Experience. We're interested in connecting with Burners who have "
                "professional experience with integrative therapy. If you might be interested "
                "in contributing to our session, please reach out!"
            ),
        )
        assert result.matched is False
        assert result.tier == "soft_match"

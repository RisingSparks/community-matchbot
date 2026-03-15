"""Tests for keyword pre-filter (no LLM calls)."""


from matchbot.db.models import PostRole, PostType
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


class TestInfraFalsePositives:
    """Regression tests for posts that were wrongly classified as infrastructure.

    Generic borrow/lend/swap patterns must not fire unless an infrastructure
    item (generator, tarp, stove, …) is also present in the text.
    """

    def test_ticket_aid_not_infra(self):
        """'Can someone spare a ticket' must not trigger infra seeking."""
        result = keyword_filter(
            "Ticket Aid",
            (
                "Hey everyone, I am looking for ticket aid this year. "
                "Can someone spare any advice on the best way to get a ticket? "
                "Anyone have extra tickets at face value?"
            ),
        )
        assert result.post_type != PostType.INFRASTRUCTURE

    def test_ticket_sales_ramblings_not_infra(self):
        """General community discussion with 'anyone have' must not trigger infra."""
        result = keyword_filter(
            "Poor ticket sales this year and other ramblings",
            (
                "Long post about ticket sales being poor. Anyone have thoughts on why? "
                "Camps are struggling to fill spots because members can't afford tickets."
            ),
        )
        assert result.post_type != PostType.INFRASTRUCTURE

    def test_effigy_art_question_not_infra(self):
        """'Can someone lend their expertise' must not trigger infra seeking."""
        result = keyword_filter(
            "Question for experienced effigy-burning art",
            (
                "We are looking to build an effigy this year. "
                "Can someone lend their expertise on fire safety and permits?"
            ),
        )
        assert result.post_type != PostType.INFRASTRUCTURE

    def test_patch_swap_without_infra_item_not_infra(self):
        """Patch/badge swaps ('swap for') must not trigger infra offering."""
        result = keyword_filter(
            "Patch postage advice",
            (
                "I collect Burning Man patches and want to swap some. "
                "I have extras from past years, looking to swap for patches from other camps."
            ),
        )
        assert result.post_type != PostType.INFRASTRUCTURE

    def test_looking_to_borrow_with_generator_is_infra(self):
        """'Looking to borrow' WITH an infra item should still classify as infra."""
        result = keyword_filter(
            "Looking to borrow a generator",
            "Need a generator for our camp power setup this year.",
        )
        assert result.post_type == PostType.INFRASTRUCTURE
        assert result.matched is True

    def test_anyone_have_with_tarp_is_infra(self):
        """'Anyone have' WITH an infra item should still classify as infra."""
        result = keyword_filter(
            "Anyone have a spare tarp?",
            "We need an extra tarp for shade at our camp.",
        )
        assert result.post_type == PostType.INFRASTRUCTURE
        assert result.matched is True

    def test_swap_for_with_gear_is_infra(self):
        """'Swap for' WITH an infra item should still classify as infra offering."""
        result = keyword_filter(
            "Bitch n swap - have extra solar panels",
            "Will swap for generator time or kitchen equipment.",
        )
        assert result.post_type == PostType.INFRASTRUCTURE
        assert result.matched is True


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

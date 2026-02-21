"""Tests for keyword pre-filter (no LLM calls)."""

import pytest

from matchbot.db.models import PostRole
from matchbot.extraction.keywords import keyword_filter


class TestSeekerPatterns:
    def test_seeking_camp(self):
        result = keyword_filter("Seeking camp for Burning Man", "")
        assert result.matched is True
        assert result.candidate_role == PostRole.SEEKER

    def test_looking_for_camp(self):
        result = keyword_filter("Looking for a camp", "Need somewhere to stay at BM")
        assert result.matched is True
        assert result.candidate_role == PostRole.SEEKER

    def test_birgin(self):
        result = keyword_filter("Birgin here!", "First time going, looking for camp")
        assert result.matched is True
        assert result.candidate_role == PostRole.SEEKER

    def test_first_time(self):
        result = keyword_filter("First time burner", "")
        assert result.matched is True
        assert result.candidate_role == PostRole.SEEKER

    def test_first_burn(self):
        result = keyword_filter("My first burn!", "Super excited. Looking to find my people.")
        assert result.matched is True
        assert result.candidate_role == PostRole.SEEKER

    def test_willing_to_build(self):
        result = keyword_filter("", "I'm willing to build and help with setup")
        assert result.matched is True
        assert result.candidate_role == PostRole.SEEKER

    def test_iso_camp(self):
        result = keyword_filter("ISO a camp for 2025", "")
        assert result.matched is True
        assert result.candidate_role == PostRole.SEEKER

    def test_in_search_of_camp(self):
        result = keyword_filter("In search of a camp", "")
        assert result.matched is True
        assert result.candidate_role == PostRole.SEEKER


class TestCampPatterns:
    def test_camp_has_openings(self):
        result = keyword_filter("Camp has openings for 2025", "")
        assert result.matched is True
        assert result.candidate_role == PostRole.CAMP

    def test_camp_recruiting(self):
        result = keyword_filter("Camp is recruiting new members", "")
        assert result.matched is True
        assert result.candidate_role == PostRole.CAMP

    def test_looking_for_builder(self):
        result = keyword_filter("", "We are looking for a builder to join our camp")
        assert result.matched is True
        assert result.candidate_role == PostRole.CAMP

    def test_open_applications(self):
        result = keyword_filter("Applications open now!", "")
        assert result.matched is True
        assert result.candidate_role == PostRole.CAMP

    def test_join_our_camp(self):
        result = keyword_filter("Join our camp at BM 2025", "")
        assert result.matched is True
        assert result.candidate_role == PostRole.CAMP

    def test_camp_spots_available(self):
        result = keyword_filter("", "We have camp spots available for the right people")
        assert result.matched is True
        assert result.candidate_role == PostRole.CAMP

    def test_space_for_volunteers(self):
        result = keyword_filter("", "We have space for a few volunteers")
        assert result.matched is True
        assert result.candidate_role == PostRole.CAMP


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
        assert result.candidate_role == PostRole.SEEKER

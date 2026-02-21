"""Tests for the deterministic Jaccard scorer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from matchbot.db.models import Platform, Post, PostRole, PostStatus
from matchbot.matching.scorer import _jaccard, _recency_score, _year_score, score_match


class TestJaccard:
    def test_identical_sets(self):
        assert _jaccard({"a", "b"}, {"a", "b"}) == pytest.approx(1.0)

    def test_no_overlap(self):
        assert _jaccard({"a"}, {"b"}) == pytest.approx(0.0)

    def test_partial_overlap(self):
        # |intersection| / |union| = 1/3
        assert _jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)

    def test_both_empty(self):
        # Both unknown → mild positive signal
        assert _jaccard(set(), set()) == pytest.approx(0.5)

    def test_one_empty(self):
        assert _jaccard({"a"}, set()) == pytest.approx(0.0)


class TestRecencyScore:
    def test_fresh_post(self):
        score = _recency_score(datetime.now(UTC))
        assert score == pytest.approx(1.0, abs=0.01)

    def test_30_day_half_life(self):
        ts = datetime.now(UTC) - timedelta(days=30)
        score = _recency_score(ts)
        assert score == pytest.approx(0.5, abs=0.02)

    def test_after_60_days_is_zero(self):
        ts = datetime.now(UTC) - timedelta(days=61)
        assert _recency_score(ts) == 0.0

    def test_none_returns_zero(self):
        assert _recency_score(None) == 0.0


class TestYearScore:
    def test_same_year(self):
        assert _year_score(2025, 2025) == pytest.approx(1.0)

    def test_different_years(self):
        assert _year_score(2025, 2026) == pytest.approx(0.0)

    def test_both_none(self):
        assert _year_score(None, None) == pytest.approx(0.7)

    def test_one_none(self):
        assert _year_score(2025, None) == pytest.approx(0.5)
        assert _year_score(None, 2025) == pytest.approx(0.5)


def _make_indexed_post(
    role: str,
    vibes: list[str],
    contribs: list[str],
    year: int | None = 2025,
    age_days: int = 0,
) -> Post:
    detected = datetime.now(UTC) - timedelta(days=age_days)
    return Post(
        platform=Platform.REDDIT,
        platform_post_id=f"test_{id(object())}",
        status=PostStatus.INDEXED,
        role=role,
        vibes="|".join(vibes),
        contribution_types="|".join(contribs),
        year=year,
        detected_at=detected,
    )


class TestScoreMatch:
    def test_perfect_match(self):
        seeker = _make_indexed_post(PostRole.SEEKER, ["art", "build_focused"], ["build", "art"])
        camp = _make_indexed_post(PostRole.CAMP, ["art", "build_focused"], ["build", "art"])
        score, breakdown = score_match(seeker, camp)
        # vibe_overlap=1.0 * 0.35 + contribution_overlap=1.0 * 0.40 + recency≈1.0 * 0.15 + year=1.0 * 0.10
        assert score >= 0.95

    def test_no_vibe_overlap(self):
        seeker = _make_indexed_post(PostRole.SEEKER, ["sober"], ["build"])
        camp = _make_indexed_post(PostRole.CAMP, ["party"], ["build"])
        score, breakdown = score_match(seeker, camp)
        assert breakdown["vibe_overlap"] == pytest.approx(0.0)
        # contribution overlap is still 1.0, so overall score is > 0
        assert score > 0.3

    def test_score_below_threshold_for_bad_match(self):
        seeker = _make_indexed_post(PostRole.SEEKER, ["sober"], ["medical"])
        camp = _make_indexed_post(PostRole.CAMP, ["party"], ["sound"])
        score, breakdown = score_match(seeker, camp)
        assert breakdown["vibe_overlap"] == pytest.approx(0.0)
        assert breakdown["contribution_overlap"] == pytest.approx(0.0)
        # Only recency (max ~0.15) and year (0.10) contribute
        assert score < 0.3

    def test_stale_posts_have_lower_score(self):
        seeker_fresh = _make_indexed_post(PostRole.SEEKER, ["art"], ["build"], age_days=0)
        seeker_stale = _make_indexed_post(PostRole.SEEKER, ["art"], ["build"], age_days=45)
        camp = _make_indexed_post(PostRole.CAMP, ["art"], ["build"], age_days=0)

        score_fresh, _ = score_match(seeker_fresh, camp)
        score_stale, _ = score_match(seeker_stale, camp)
        assert score_fresh > score_stale

    def test_year_mismatch_penalised(self):
        seeker = _make_indexed_post(PostRole.SEEKER, ["art"], ["build"], year=2025)
        camp_same_year = _make_indexed_post(PostRole.CAMP, ["art"], ["build"], year=2025)
        camp_diff_year = _make_indexed_post(PostRole.CAMP, ["art"], ["build"], year=2026)

        score_same, _ = score_match(seeker, camp_same_year)
        score_diff, _ = score_match(seeker, camp_diff_year)
        assert score_same > score_diff

    def test_breakdown_keys_present(self):
        seeker = _make_indexed_post(PostRole.SEEKER, ["art"], ["build"])
        camp = _make_indexed_post(PostRole.CAMP, ["art"], ["build"])
        _, breakdown = score_match(seeker, camp)
        assert set(breakdown.keys()) == {"vibe_overlap", "contribution_overlap", "recency", "year_match"}

    def test_empty_vibes_both_gets_partial_credit(self):
        seeker = _make_indexed_post(PostRole.SEEKER, [], ["build"])
        camp = _make_indexed_post(PostRole.CAMP, [], ["build"])
        score, breakdown = score_match(seeker, camp)
        assert breakdown["vibe_overlap"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_propose_matches_creates_match(db_session, seeker_post_factory, camp_post_factory):
    from matchbot.matching.queue import propose_matches

    seeker = seeker_post_factory(vibes=["art", "build_focused"], contribution_types=["build"])
    camp = camp_post_factory(vibes=["art", "build_focused"], contribution_types=["build", "kitchen"])

    db_session.add(seeker)
    db_session.add(camp)
    await db_session.commit()
    await db_session.refresh(seeker)
    await db_session.refresh(camp)

    matches = await propose_matches(db_session, seeker)
    assert len(matches) >= 1
    assert matches[0].seeker_post_id == seeker.id
    assert matches[0].camp_post_id == camp.id


@pytest.mark.asyncio
async def test_propose_matches_deduplicates(db_session, seeker_post_factory, camp_post_factory):
    from matchbot.matching.queue import propose_matches

    seeker = seeker_post_factory(vibes=["art"], contribution_types=["build"])
    camp = camp_post_factory(vibes=["art"], contribution_types=["build"])

    db_session.add(seeker)
    db_session.add(camp)
    await db_session.commit()
    await db_session.refresh(seeker)
    await db_session.refresh(camp)

    await propose_matches(db_session, seeker)
    matches2 = await propose_matches(db_session, seeker)
    assert len(matches2) == 0  # already exists


@pytest.mark.asyncio
async def test_propose_matches_skips_low_score(db_session, seeker_post_factory, camp_post_factory):
    # Totally different vibes/skills, and stale
    from datetime import timedelta

    from matchbot.matching.queue import propose_matches

    seeker = seeker_post_factory(vibes=["sober"], contribution_types=["medical"])
    seeker.detected_at = datetime.now(UTC) - timedelta(days=61)  # stale
    camp = camp_post_factory(vibes=["party"], contribution_types=["sound"])
    camp.detected_at = datetime.now(UTC) - timedelta(days=61)  # stale

    db_session.add(seeker)
    db_session.add(camp)
    await db_session.commit()
    await db_session.refresh(seeker)
    await db_session.refresh(camp)

    matches = await propose_matches(db_session, seeker)
    assert len(matches) == 0

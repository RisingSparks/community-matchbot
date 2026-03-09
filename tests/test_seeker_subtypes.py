"""Tests for seeker sub-type (A vs A.2) feature."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from matchbot.db.models import Platform, Post, PostRole, PostStatus
from matchbot.extraction.schemas import ExtractedPost

# ---------------------------------------------------------------------------
# ExtractedPost validator tests
# ---------------------------------------------------------------------------


class TestExtractedPostSeekerIntent:
    def test_accepts_join_camp(self):
        ep = ExtractedPost(role="seeker", seeker_intent="join_camp")
        assert ep.seeker_intent == "join_camp"

    def test_accepts_join_art_project(self):
        ep = ExtractedPost(role="seeker", seeker_intent="join_art_project")
        assert ep.seeker_intent == "join_art_project"

    def test_accepts_skills_learning(self):
        ep = ExtractedPost(role="seeker", seeker_intent="skills_learning")
        assert ep.seeker_intent == "skills_learning"

    def test_accepts_unknown(self):
        ep = ExtractedPost(role="seeker", seeker_intent="unknown")
        assert ep.seeker_intent == "unknown"

    def test_rejects_invalid_value(self):
        ep = ExtractedPost(role="seeker", seeker_intent="join_as_friend")
        assert ep.seeker_intent is None

    def test_passes_none_through(self):
        ep = ExtractedPost(role="camp")
        assert ep.seeker_intent is None

    def test_explicit_none_passes_through(self):
        ep = ExtractedPost(role="seeker", seeker_intent=None)
        assert ep.seeker_intent is None


# ---------------------------------------------------------------------------
# Scorer dispatch tests
# ---------------------------------------------------------------------------


def _make_post_with_intent(
    role: str,
    vibes: list[str],
    contribs: list[str],
    seeker_intent: str | None = None,
) -> Post:
    from datetime import UTC, datetime

    return Post(
        platform=Platform.REDDIT,
        platform_post_id=f"test_{id(object())}",
        status=PostStatus.INDEXED,
        role=role,
        vibes="|".join(vibes),
        contribution_types="|".join(contribs),
        year=2025,
        detected_at=datetime.now(UTC),
        seeker_intent=seeker_intent,
    )


class TestSeekerIntentScoring:
    def test_skills_learning_uses_skills_weights(self):
        from matchbot.matching.scorer import WEIGHTS_SKILLS, score_match

        seeker = _make_post_with_intent(
            PostRole.SEEKER, ["sober"], ["build", "art"], seeker_intent="skills_learning"
        )
        camp = _make_post_with_intent(PostRole.CAMP, ["party"], ["build", "art"])

        score, breakdown = score_match(seeker, camp, seeker_intent=seeker.seeker_intent)
        # contribution_overlap=1.0, vibe_overlap=0.0
        # expected composite ≈ contribution overlap weight + recency weight
        # + year match weight
        expected_floor = WEIGHTS_SKILLS["contribution_overlap"] * 1.0
        assert score >= expected_floor - 0.01

    def test_join_camp_uses_default_weights(self):
        from matchbot.matching.scorer import WEIGHTS, score_match

        seeker = _make_post_with_intent(
            PostRole.SEEKER, ["sober"], ["build"], seeker_intent="join_camp"
        )
        camp = _make_post_with_intent(PostRole.CAMP, ["party"], ["build"])

        score, _ = score_match(seeker, camp, seeker_intent=seeker.seeker_intent)
        # contribution_overlap=1.0, vibe_overlap=0.0
        expected_floor = WEIGHTS["contribution_overlap"] * 1.0
        assert score >= expected_floor - 0.01


# ---------------------------------------------------------------------------
# Queue — skills seeker passes seeker_intent to scorer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_propose_matches_passes_seeker_intent_to_scorer(
    db_session, seeker_post_factory, camp_post_factory
):
    from matchbot.matching import queue as queue_mod

    seeker = seeker_post_factory(
        vibes=["art"],
        contribution_types=["build"],
        seeker_intent="skills_learning",
    )
    camp = camp_post_factory(vibes=["art"], contribution_types=["build", "teaching"])

    db_session.add(seeker)
    db_session.add(camp)
    await db_session.commit()
    await db_session.refresh(seeker)
    await db_session.refresh(camp)

    call_kwargs: list[dict] = []

    original_score_match = queue_mod.score_match

    def capturing_score_match(s, c, seeker_intent=None):
        call_kwargs.append({"seeker_intent": seeker_intent})
        return original_score_match(s, c, seeker_intent=seeker_intent)

    with patch.object(queue_mod, "score_match", side_effect=capturing_score_match):
        await queue_mod.propose_matches(db_session, seeker)

    assert len(call_kwargs) >= 1
    assert call_kwargs[0]["seeker_intent"] == "skills_learning"


# ---------------------------------------------------------------------------
# Renderer — skills seeker dispatches to skills template
# ---------------------------------------------------------------------------


class TestRenderIntroDispatch:
    def _make_rendered_post(
        self,
        role: str,
        seeker_intent: str | None = None,
        camp_name: str | None = "Test Camp",
    ) -> Post:
        return Post(
            platform=Platform.REDDIT,
            platform_post_id=f"test_{id(object())}",
            status=PostStatus.INDEXED,
            role=role,
            vibes="art|build_focused",
            contribution_types="build|art",
            author_display_name="TestUser",
            source_url="https://reddit.com/test",
            camp_name=camp_name,
            seeker_intent=seeker_intent,
        )

    def test_skills_learning_seeker_uses_skills_template(self):
        from matchbot.messaging import renderer as renderer_mod

        seeker = self._make_rendered_post(PostRole.SEEKER, seeker_intent="skills_learning")
        camp = self._make_rendered_post(PostRole.CAMP, camp_name="Dusty Makers")

        rendered_templates: list[str] = []
        original_get_template = renderer_mod._jinja_env.get_template

        def capturing_get_template(name: str):
            rendered_templates.append(name)
            return original_get_template(name)

        with patch.object(
            renderer_mod._jinja_env,
            "get_template",
            side_effect=capturing_get_template,
        ):
            renderer_mod.render_intro(seeker, camp, "reddit")

        assert rendered_templates[0] == "intro_skills_reddit.md.j2"

    def test_skills_learning_camp_facing_uses_skills_camp_template(self):
        from matchbot.messaging import renderer as renderer_mod

        seeker = self._make_rendered_post(PostRole.SEEKER, seeker_intent="skills_learning")
        camp = self._make_rendered_post(PostRole.CAMP, camp_name="Dusty Makers")

        rendered_templates: list[str] = []
        original_get_template = renderer_mod._jinja_env.get_template

        def capturing_get_template(name: str):
            rendered_templates.append(name)
            return original_get_template(name)

        with patch.object(
            renderer_mod._jinja_env,
            "get_template",
            side_effect=capturing_get_template,
        ):
            renderer_mod.render_intro(seeker, camp, "reddit", for_camp=True)

        assert rendered_templates[0] == "intro_skills_camp_reddit.md.j2"

    def test_join_camp_seeker_uses_standard_template(self):
        from matchbot.messaging import renderer as renderer_mod

        seeker = self._make_rendered_post(PostRole.SEEKER, seeker_intent="join_camp")
        camp = self._make_rendered_post(PostRole.CAMP, camp_name="Dusty Makers")

        rendered_templates: list[str] = []
        original_get_template = renderer_mod._jinja_env.get_template

        def capturing_get_template(name: str):
            rendered_templates.append(name)
            return original_get_template(name)

        with patch.object(
            renderer_mod._jinja_env,
            "get_template",
            side_effect=capturing_get_template,
        ):
            renderer_mod.render_intro(seeker, camp, "reddit")

        assert rendered_templates[0] == "intro_reddit.md.j2"

    def test_skills_intro_contains_skills_copy(self):
        from matchbot.messaging.renderer import render_intro

        seeker = self._make_rendered_post(PostRole.SEEKER, seeker_intent="skills_learning")
        camp = self._make_rendered_post(PostRole.CAMP, camp_name="Dusty Makers")

        output = render_intro(seeker, camp, "reddit")
        # Skills template should mention learning/hands-on, not generic join-camp copy
        assert (
            "learn" in output.lower()
            or "skill" in output.lower()
            or "hands-on" in output.lower()
        )

    def test_skills_camp_intro_contains_skills_copy(self):
        from matchbot.messaging.renderer import render_intro

        seeker = self._make_rendered_post(PostRole.SEEKER, seeker_intent="skills_learning")
        camp = self._make_rendered_post(PostRole.CAMP, camp_name="Dusty Makers")

        output = render_intro(seeker, camp, "reddit", for_camp=True)
        # Camp-facing skills template should mention learning/skills intent
        assert "learn" in output.lower() or "skill" in output.lower()

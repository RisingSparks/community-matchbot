"""Jinja2 intro message renderer."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from matchbot.db.models import Post, PostType, SeekerIntent

_TEMPLATE_DIR = Path(__file__).parent.parent / "config" / "templates"

_MENTORSHIP_TEMPLATES = {
    "reddit": "intro_reddit.md.j2",
    "discord": "intro_discord.md.j2",
    "facebook": "intro_facebook.md.j2",
}

_MENTORSHIP_CAMP_TEMPLATES = {
    "reddit": "intro_camp_reddit.md.j2",
    "discord": "intro_camp_discord.md.j2",
    "facebook": "intro_camp_facebook.md.j2",
}

_INFRA_TEMPLATES = {
    "reddit": "intro_infra_reddit.md.j2",
    "discord": "intro_infra_discord.md.j2",
    "facebook": "intro_infra_facebook.md.j2",
}

_SKILLS_TEMPLATES = {
    "reddit": "intro_skills_reddit.md.j2",
    "discord": "intro_skills_discord.md.j2",
    "facebook": "intro_skills_facebook.md.j2",
}

_SKILLS_CAMP_TEMPLATES = {
    "reddit": "intro_skills_camp_reddit.md.j2",
    "discord": "intro_skills_camp_discord.md.j2",
    "facebook": "intro_skills_camp_facebook.md.j2",
}

_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_intro(seeker: Post, camp: Post, platform: str, for_camp: bool = False) -> str:
    """Render an intro message for the given platform, dispatching on post_type.

    Args:
        seeker: The seeker/seeking post.
        camp: The camp/offering post.
        platform: Target platform (reddit, discord, facebook).
        for_camp: If True, render the camp-facing version of the intro.
    """
    # For infra matches, seeker=seeking post, camp=offering post (canonical naming in Match)
    if seeker.post_type == PostType.INFRASTRUCTURE or camp.post_type == PostType.INFRASTRUCTURE:
        return _render_infra_intro(seeker, camp, platform)
    if seeker.seeker_intent == SeekerIntent.SKILLS_LEARNING:
        if for_camp:
            return _render_skills_intro_camp(seeker, camp, platform)
        return _render_skills_intro(seeker, camp, platform)
    if for_camp:
        return _render_mentorship_intro_camp(seeker, camp, platform)
    return _render_mentorship_intro(seeker, camp, platform)


def _render_mentorship_intro(seeker: Post, camp: Post, platform: str) -> str:
    template_name = _MENTORSHIP_TEMPLATES.get(platform, "intro_reddit.md.j2")
    template = _jinja_env.get_template(template_name)

    shared_vibes = sorted(set(seeker.vibes_list()) & set(camp.vibes_list()))
    shared_contrib = sorted(set(seeker.contribution_types_list()) & set(camp.contribution_types_list()))

    from matchbot.settings import get_settings
    settings = get_settings()

    context = {
        "seeker_username": seeker.author_display_name or seeker.platform_author_id or "burner",
        "camp_name": camp.camp_name or "",
        "camp_contact": camp.author_display_name or camp.platform_author_id or "camp",
        "shared_vibes": shared_vibes,
        "shared_contrib": shared_contrib,
        "seeker_url": seeker.source_url or "",
        "camp_url": camp.source_url or "",
        "moderator_name": settings.moderator_name,
    }

    return template.render(**context)


def _render_mentorship_intro_camp(seeker: Post, camp: Post, platform: str) -> str:
    template_name = _MENTORSHIP_CAMP_TEMPLATES.get(platform, "intro_camp_reddit.md.j2")
    template = _jinja_env.get_template(template_name)

    shared_vibes = sorted(set(seeker.vibes_list()) & set(camp.vibes_list()))
    shared_contrib = sorted(set(seeker.contribution_types_list()) & set(camp.contribution_types_list()))

    from matchbot.settings import get_settings
    settings = get_settings()

    context = {
        "seeker_username": seeker.author_display_name or seeker.platform_author_id or "burner",
        "camp_name": camp.camp_name or "",
        "camp_contact": camp.author_display_name or camp.platform_author_id or "camp",
        "shared_vibes": shared_vibes,
        "shared_contrib": shared_contrib,
        "seeker_url": seeker.source_url or "",
        "camp_url": camp.source_url or "",
        "moderator_name": settings.moderator_name,
    }

    return template.render(**context)


def _render_skills_intro(seeker: Post, camp: Post, platform: str) -> str:
    template_name = _SKILLS_TEMPLATES.get(platform, "intro_skills_reddit.md.j2")
    template = _jinja_env.get_template(template_name)

    shared_vibes = sorted(set(seeker.vibes_list()) & set(camp.vibes_list()))
    shared_contrib = sorted(set(seeker.contribution_types_list()) & set(camp.contribution_types_list()))

    from matchbot.settings import get_settings
    settings = get_settings()

    context = {
        "seeker_username": seeker.author_display_name or seeker.platform_author_id or "burner",
        "camp_name": camp.camp_name or "",
        "camp_contact": camp.author_display_name or camp.platform_author_id or "camp",
        "shared_vibes": shared_vibes,
        "shared_contrib": shared_contrib,
        "seeker_url": seeker.source_url or "",
        "camp_url": camp.source_url or "",
        "moderator_name": settings.moderator_name,
    }

    return template.render(**context)


def _render_skills_intro_camp(seeker: Post, camp: Post, platform: str) -> str:
    template_name = _SKILLS_CAMP_TEMPLATES.get(platform, "intro_skills_camp_reddit.md.j2")
    template = _jinja_env.get_template(template_name)

    shared_vibes = sorted(set(seeker.vibes_list()) & set(camp.vibes_list()))
    shared_contrib = sorted(set(seeker.contribution_types_list()) & set(camp.contribution_types_list()))

    from matchbot.settings import get_settings
    settings = get_settings()

    context = {
        "seeker_username": seeker.author_display_name or seeker.platform_author_id or "burner",
        "camp_name": camp.camp_name or "",
        "camp_contact": camp.author_display_name or camp.platform_author_id or "camp",
        "shared_vibes": shared_vibes,
        "shared_contrib": shared_contrib,
        "seeker_url": seeker.source_url or "",
        "camp_url": camp.source_url or "",
        "moderator_name": settings.moderator_name,
    }

    return template.render(**context)


def _render_infra_intro(seeking: Post, offering: Post, platform: str) -> str:
    template_name = _INFRA_TEMPLATES.get(platform, "intro_infra_reddit.md.j2")
    template = _jinja_env.get_template(template_name)

    shared_categories = sorted(
        set(seeking.infra_categories_list()) & set(offering.infra_categories_list())
    )

    # Build a short human-readable summary of what the offerer has
    offerer_parts = []
    if offering.infra_categories_list():
        offerer_parts.append(", ".join(offering.infra_categories_list()))
    if offering.quantity:
        offerer_parts.append(f"({offering.quantity})")
    if offering.condition:
        offerer_parts.append(f"— condition: {offering.condition}")
    offerer_summary = " ".join(offerer_parts) if offerer_parts else "gear"

    # Combine dates context from both posts
    dates_parts = [d for d in [seeking.dates_needed, offering.dates_needed] if d]
    dates_context = " / ".join(dates_parts) if dates_parts else ""

    from matchbot.settings import get_settings
    settings = get_settings()

    context = {
        "seeker_username": seeking.author_display_name or seeking.platform_author_id or "burner",
        "offerer_contact": offering.author_display_name or offering.platform_author_id or "them",
        "shared_categories": shared_categories,
        "offerer_summary": offerer_summary,
        "seeker_url": seeking.source_url or "",
        "offerer_url": offering.source_url or "",
        "dates_context": dates_context,
        "moderator_name": settings.moderator_name,
    }

    return template.render(**context)

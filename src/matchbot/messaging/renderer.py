"""Jinja2 intro message renderer."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from matchbot.db.models import Post

_TEMPLATE_DIR = Path(__file__).parent.parent.parent.parent / "config" / "templates"

_PLATFORM_TEMPLATE = {
    "reddit": "intro_reddit.md.j2",
    "discord": "intro_discord.md.j2",
    "facebook": "intro_facebook.md.j2",
}

_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_intro(seeker: Post, camp: Post, platform: str) -> str:
    """Render an intro message for the given platform."""
    template_name = _PLATFORM_TEMPLATE.get(platform, "intro_reddit.md.j2")
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

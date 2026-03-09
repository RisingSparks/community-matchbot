from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.db.models import Post, PostRole, PostStatus, PostType, Profile


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _supports_profile(post: Post) -> bool:
    return (
        post.status == PostStatus.INDEXED
        and post.post_type != PostType.INFRASTRUCTURE
        and post.role in {PostRole.CAMP, PostRole.SEEKER}
    )


async def sync_profile_from_post(session: AsyncSession, post: Post) -> Profile | None:
    """
    Upsert the canonical profile row for an indexed mentorship post and attach it.

    Profiles are keyed logically by platform + platform_author_id + role.
    """
    if not _supports_profile(post):
        post.profile_id = None
        session.add(post)
        return None

    profile = None
    if post.profile_id:
        profile = await session.get(Profile, post.profile_id)
        if profile and (
            profile.platform != post.platform
            or profile.platform_author_id != post.platform_author_id
            or profile.role != post.role
        ):
            profile = None

    if profile is None:
        profile = (
            await session.exec(
                select(Profile)
                .where(
                    Profile.platform == post.platform,
                    Profile.platform_author_id == post.platform_author_id,
                    Profile.role == post.role,
                )
                .order_by(Profile.updated_at.desc())  # type: ignore[attr-defined]
            )
        ).first()

    if profile is None:
        profile = Profile(
            role=post.role or PostRole.UNKNOWN,
            platform=post.platform,
            platform_author_id=post.platform_author_id,
        )

    profile.role = post.role or profile.role
    profile.seeker_intent = post.seeker_intent
    profile.display_name = post.author_display_name
    profile.platform = post.platform
    profile.platform_author_id = post.platform_author_id
    profile.camp_name = post.camp_name
    profile.vibes = post.vibes
    profile.contribution_types = post.contribution_types
    profile.year = post.year
    profile.availability_notes = post.availability_notes
    profile.contact_method = post.contact_method
    profile.is_active = True
    profile.updated_at = _now()

    session.add(profile)
    await session.flush()

    post.profile_id = profile.id
    session.add(post)
    return profile

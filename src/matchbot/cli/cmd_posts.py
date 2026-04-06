"""matchbot posts — browse and manage indexed posts."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.cli._db import with_session
from matchbot.db.models import Event, Post, PostStatus, PostType

app = typer.Typer(help="Browse and manage community signals")
console = Console(width=160)


def _build_extractor():
    from matchbot.extraction.anthropic_extractor import AnthropicExtractor
    from matchbot.extraction.openai_extractor import OpenAIExtractor
    from matchbot.settings import get_settings

    settings = get_settings()
    return AnthropicExtractor() if settings.llm_provider == "anthropic" else OpenAIExtractor()


@app.command("list")
def posts_list(
    role: Annotated[str | None, typer.Option("--role", help="seeker|camp")] = None,
    platform: Annotated[str | None, typer.Option("--platform")] = None,
    status: Annotated[str | None, typer.Option("--status")] = None,
    post_type: Annotated[str | None, typer.Option("--type", help="mentorship|infrastructure")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 100,
) -> None:
    """List community signals (seekers and groups)."""

    async def _run(session):
        q = select(Post)
        if role:
            q = q.where(Post.role == role)
        if platform:
            q = q.where(Post.platform == platform)
        if status:
            q = q.where(Post.status == status)
        if post_type:
            q = q.where(Post.post_type == post_type)
        q = q.order_by(Post.detected_at.desc())
        if limit:
            q = q.limit(limit)

        posts = (await session.exec(q)).all()
        if not posts:
            rprint("[yellow]No signals found.[/yellow]")
            return

        table = Table(title="Community Signals")
        table.add_column("ID", style="dim", width=10)
        table.add_column("Platform", width=10)
        table.add_column("Type", width=14)
        table.add_column("Role", width=8)
        table.add_column("Status", width=14)
        table.add_column("Title", no_wrap=False, max_width=50)
        table.add_column("URL", no_wrap=False, overflow="fold", max_width=60)
        table.add_column("Detected")

        for p in posts:
            table.add_row(
                p.id[:8],
                p.platform,
                p.post_type,
                p.role or "",
                p.status,
                p.title[:50],
                p.source_url or "",
                p.detected_at.strftime("%Y-%m-%d"),
            )
        console.print(table)

    with_session(_run)


@app.command("show")
def posts_show(post_id: str) -> None:
    """Examine a community signal."""

    async def _run(session):
        post = await _resolve_post(session, post_id)
        if not post:
            rprint(f"[red]Signal {post_id!r} not found.[/red]")
            raise typer.Exit(1)

        if post.post_type == PostType.INFRASTRUCTURE:
            type_detail = (
                f"[bold]Infra Role:[/bold] {post.infra_role or ''}  |  "
                f"[bold]Categories:[/bold] {post.infra_categories or '—'}\n"
                f"[bold]Quantity:[/bold] {post.quantity or '—'}  |  "
                f"[bold]Condition:[/bold] {post.condition or '—'}  |  "
                f"[bold]Dates:[/bold] {post.dates_needed or '—'}\n"
            )
        else:
            type_detail = (
                f"[bold]Role:[/bold] {post.role}  |  "
                f"[bold]Vibes:[/bold] {post.vibes}\n"
                f"[bold]Contributions:[/bold] {post.contribution_types}\n"
                f"[bold]Year:[/bold] {post.year}  |  "
                f"[bold]Camp/Project:[/bold] {post.camp_name}  |  "
                f"[bold]Availability:[/bold] {post.availability_notes}\n"
            )

        content = (
            f"[bold]Platform:[/bold] {post.platform} / {post.source_community}\n"
            f"[bold]Type:[/bold] {post.post_type}  |  [bold]Status:[/bold] {post.status}\n"
            f"[bold]Extraction Confidence:[/bold] {post.extraction_confidence}  |  "
            f"[bold]Method:[/bold] {post.extraction_method}\n"
            f"{type_detail}\n"
            f"[bold yellow]Title:[/bold yellow] {post.title}\n\n"
            f"[bold]Original Signal:[/bold]\n{post.raw_text}"
        )
        console.print(Panel(content, title=f"Signal {post.id[:8]}", expand=False))

    with_session(_run)


@app.command("re-extract")
def posts_re_extract(post_id: str) -> None:
    """Re-analyze a signal for better alignment."""

    async def _run(session):
        post = await _resolve_post(session, post_id)
        if not post:
            rprint(f"[red]Signal {post_id!r} not found.[/red]")
            raise typer.Exit(1)

        from matchbot.extraction import process_post

        extractor = _build_extractor()

        post.status = PostStatus.RAW  # reset to re-process
        session.add(post)
        await session.commit()

        try:
            updated = await process_post(session, post, extractor)
        finally:
            await extractor.aclose()
        rprint(f"[green]Re-analyzed signal {post_id[:8]}: status={updated.status}[/green]")

    with_session(_run)


@app.command("re-extract-many")
def posts_re_extract_many(
    role: Annotated[str | None, typer.Option("--role", help="Filter by current role")] = None,
    platform: Annotated[str | None, typer.Option("--platform")] = None,
    status: Annotated[str, typer.Option("--status")] = PostStatus.INDEXED,
    post_type: Annotated[str | None, typer.Option("--type", help="mentorship|infrastructure")] = None,
    author: Annotated[str | None, typer.Option("--author", help="Filter by author_display_name")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 50,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show matching posts without re-extracting")] = False,
) -> None:
    """Re-analyze a filtered batch of signals."""

    async def _run(session):
        q = (
            select(Post)
            .where(Post.status == status)
            .order_by(Post.detected_at.desc())
            .limit(limit)
        )
        if role:
            q = q.where(Post.role == role)
        if platform:
            q = q.where(Post.platform == platform)
        if post_type:
            q = q.where(Post.post_type == post_type)
        if author:
            q = q.where(Post.author_display_name == author)

        posts = (await session.exec(q)).all()
        if not posts:
            rprint("[yellow]No signals matched the re-extract filter.[/yellow]")
            return

        if dry_run:
            rprint(f"[cyan]Would re-extract {len(posts)} signal(s):[/cyan]")
            for post in posts:
                rprint(f"  {post.id[:8]}  {post.platform}  {post.role or ''}  {post.title[:80]}")
            return

        from matchbot.extraction import process_post

        extractor = _build_extractor()
        updated = 0
        try:
            total = len(posts)
            rprint(f"[cyan]Re-analyzing {total} signal(s)...[/cyan]")
            for idx, post in enumerate(posts, start=1):
                rprint(
                    f"[dim][{idx}/{total}] {post.id[:8]} {post.platform} {post.title[:80]}[/dim]"
                )
                post.status = PostStatus.RAW
                session.add(post)
                await session.commit()
                await session.refresh(post)
                await process_post(session, post, extractor)
                updated += 1
        finally:
            await extractor.aclose()

        rprint(f"[green]Re-analyzed {updated} signal(s).[/green]")

    with_session(_run)


@app.command("flag")
def posts_flag(
    post_id: str,
    note: Annotated[str | None, typer.Option("--note")] = None,
) -> None:
    """Flag a signal for moderator attention."""

    async def _run(session):
        post = await _resolve_post(session, post_id)
        if not post:
            rprint(f"[red]Signal {post_id!r} not found.[/red]")
            raise typer.Exit(1)
        post.status = PostStatus.NEEDS_REVIEW
        session.add(post)
        await session.commit()
        rprint(f"[yellow]Signal {post_id[:8]} flagged for human review.[/yellow]")
        if note:
            rprint(f"  Note: {note}")

    with_session(_run)



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _apply_field_overrides(post: Post, overrides: dict) -> list[str]:
    """
    Apply moderator field overrides to a post.

    Returns a list of human-readable change descriptions for display.
    Normalizes vibes, contribution_types, and infra_categories against the taxonomy.
    """
    from matchbot.taxonomy import (
        normalize_contribution_types,
        normalize_infra_categories,
        normalize_vibes,
    )

    changes = []

    if overrides.get("role") is not None:
        post.role = overrides["role"]
        changes.append(f"role={overrides['role']}")

    if overrides.get("vibes") is not None:
        raw = [v.strip() for v in overrides["vibes"].split("|") if v.strip()]
        normalized = normalize_vibes(raw)
        unknown = set(raw) - set(normalized)
        if unknown:
            rprint(f"[yellow]  Ignored unknown vibes: {sorted(unknown)}[/yellow]")
        post.vibes = "|".join(normalized)
        changes.append(f"vibes={post.vibes!r}")

    if overrides.get("contribution_types") is not None:
        raw = [v.strip() for v in overrides["contribution_types"].split("|") if v.strip()]
        normalized = normalize_contribution_types(raw)
        unknown = set(raw) - set(normalized)
        if unknown:
            rprint(f"[yellow]  Ignored unknown contribution_types: {sorted(unknown)}[/yellow]")
        post.contribution_types = "|".join(normalized)
        changes.append(f"contribution_types={post.contribution_types!r}")

    if overrides.get("camp_name") is not None:
        post.camp_name = overrides["camp_name"]
        changes.append(f"camp_name={overrides['camp_name']!r}")

    if overrides.get("year") is not None:
        post.year = overrides["year"]
        changes.append(f"year={overrides['year']}")

    if overrides.get("infra_role") is not None:
        post.infra_role = overrides["infra_role"]
        changes.append(f"infra_role={overrides['infra_role']}")

    if overrides.get("infra_categories") is not None:
        raw = [v.strip() for v in overrides["infra_categories"].split("|") if v.strip()]
        normalized = normalize_infra_categories(raw)
        unknown = set(raw) - set(normalized)
        if unknown:
            rprint(f"[yellow]  Ignored unknown infra_categories: {sorted(unknown)}[/yellow]")
        post.infra_categories = "|".join(normalized)
        changes.append(f"infra_categories={post.infra_categories!r}")

    if overrides.get("quantity") is not None:
        post.quantity = overrides["quantity"]
        changes.append(f"quantity={overrides['quantity']!r}")

    if overrides.get("condition") is not None:
        post.condition = overrides["condition"]
        changes.append(f"condition={overrides['condition']!r}")

    return changes


async def _resolve_post(session: AsyncSession, post_id: str) -> Post | None:
    """
    Resolve a post by full UUID or unique short prefix.

    Returns None if no post matches, and exits with an explanatory error when
    the prefix is ambiguous.
    """
    if len(post_id) >= 36:
        return await session.get(Post, post_id)

    rows = (
        await session.exec(
            select(Post).where(Post.id.startswith(post_id)).order_by(Post.detected_at.desc()).limit(2)
        )
    ).all()
    if not rows:
        return None
    if len(rows) > 1:
        rprint(f"[red]Post ID prefix {post_id!r} is ambiguous. Use more characters.[/red]")
        for p in rows:
            rprint(f"  - {p.id}")
        raise typer.Exit(1)
    return rows[0]


async def _write_event(
    session,
    post: Post,
    event_type: str,
    payload: dict,
    note: str | None = None,
) -> None:
    event = Event(
        event_type=event_type,
        post_id=post.id,
        actor="moderator",
        payload=json.dumps(payload),
        note=note,
    )
    session.add(event)


# ---------------------------------------------------------------------------
# Moderator review commands
# ---------------------------------------------------------------------------


@app.command("edit")
def posts_edit(
    post_id: str,
    role: Annotated[str | None, typer.Option("--role", help="seeker|camp|unknown")] = None,
    vibes: Annotated[str | None, typer.Option("--vibes", help="Pipe-delimited, e.g. 'art|music'")] = None,
    contribution_types: Annotated[str | None, typer.Option("--contribution-types", help="Pipe-delimited")] = None,
    camp_name: Annotated[str | None, typer.Option("--camp-name")] = None,
    year: Annotated[int | None, typer.Option("--year")] = None,
    infra_role: Annotated[str | None, typer.Option("--infra-role", help="seeking|offering")] = None,
    infra_categories: Annotated[str | None, typer.Option("--infra-categories", help="Pipe-delimited")] = None,
    quantity: Annotated[str | None, typer.Option("--quantity")] = None,
    condition: Annotated[str | None, typer.Option("--condition")] = None,
    note: Annotated[str | None, typer.Option("--note")] = None,
) -> None:
    """Refine signal details."""

    async def _run(session):
        post = await _resolve_post(session, post_id)
        if not post:
            rprint(f"[red]Signal {post_id!r} not found.[/red]")
            raise typer.Exit(1)
        if post.status != PostStatus.NEEDS_REVIEW:
            rprint(f"[red]Signal {post_id[:8]} has status {post.status!r}. Only NEEDS_REVIEW signals can be refined.[/red]")
            raise typer.Exit(1)

        overrides = {
            "role": role,
            "vibes": vibes,
            "contribution_types": contribution_types,
            "camp_name": camp_name,
            "year": year,
            "infra_role": infra_role,
            "infra_categories": infra_categories,
            "quantity": quantity,
            "condition": condition,
        }
        changes = _apply_field_overrides(post, overrides)

        if not changes:
            rprint("[yellow]No fields specified — nothing changed.[/yellow]")
            return

        session.add(post)
        await _write_event(session, post, "post_edited", {"changes": changes}, note=note)
        await session.commit()

        rprint(f"[green]Signal {post_id[:8]} refined:[/green]")
        for c in changes:
            rprint(f"  {c}")
        if note:
            rprint(f"  Note: {note}")

    with_session(_run)


@app.command("approve")
def posts_approve(
    post_id: str,
    note: Annotated[str | None, typer.Option("--note")] = None,
    role: Annotated[str | None, typer.Option("--role", help="seeker|camp|unknown")] = None,
    vibes: Annotated[str | None, typer.Option("--vibes", help="Pipe-delimited, e.g. 'art|music'")] = None,
    contribution_types: Annotated[str | None, typer.Option("--contribution-types", help="Pipe-delimited")] = None,
    camp_name: Annotated[str | None, typer.Option("--camp-name")] = None,
    year: Annotated[int | None, typer.Option("--year")] = None,
    infra_role: Annotated[str | None, typer.Option("--infra-role", help="seeking|offering")] = None,
    infra_categories: Annotated[str | None, typer.Option("--infra-categories", help="Pipe-delimited")] = None,
    quantity: Annotated[str | None, typer.Option("--quantity")] = None,
    condition: Annotated[str | None, typer.Option("--condition")] = None,
) -> None:
    """Verify and index a community signal."""

    async def _run(session):
        post = await _resolve_post(session, post_id)
        if not post:
            rprint(f"[red]Signal {post_id!r} not found.[/red]")
            raise typer.Exit(1)
        if post.status != PostStatus.NEEDS_REVIEW:
            rprint(f"[red]Signal {post_id[:8]} has status {post.status!r}. Only NEEDS_REVIEW signals can be approved.[/red]")
            raise typer.Exit(1)

        overrides = {
            "role": role,
            "vibes": vibes,
            "contribution_types": contribution_types,
            "camp_name": camp_name,
            "year": year,
            "infra_role": infra_role,
            "infra_categories": infra_categories,
            "quantity": quantity,
            "condition": condition,
        }
        changes = _apply_field_overrides(post, overrides)

        post.status = PostStatus.INDEXED
        session.add(post)
        await _write_event(
            session,
            post,
            "post_approved",
            {"changes": changes, "prev_status": PostStatus.NEEDS_REVIEW},
            note=note,
        )
        await session.commit()
        await session.refresh(post)

        rprint(f"[green]Signal {post_id[:8]} verified → INDEXED.[/green]")
        for c in changes:
            rprint(f"  {c}")
        if note:
            rprint(f"  Note: {note}")

        # Trigger matching now that the post is indexed
        from matchbot.matching.queue import propose_matches

        await propose_matches(session, post)
        await session.refresh(post)
        rprint(f"[dim]Connections explored for {post_id[:8]}.[/dim]")

    with_session(_run)


@app.command("dismiss")
def posts_dismiss(
    post_id: str,
    reason: Annotated[str | None, typer.Option("--reason", help="spam|off-topic|duplicate|other")] = None,
) -> None:
    """Dismiss a signal (off-topic or noise)."""

    async def _run(session):
        post = await _resolve_post(session, post_id)
        if not post:
            rprint(f"[red]Signal {post_id!r} not found.[/red]")
            raise typer.Exit(1)
        if post.status not in {PostStatus.NEEDS_REVIEW, PostStatus.ERROR}:
            rprint(
                f"[red]Signal {post_id[:8]} has status {post.status!r}. "
                "Only NEEDS_REVIEW or ERROR signals can be dismissed.[/red]"
            )
            raise typer.Exit(1)

        prev_status = post.status
        post.status = PostStatus.SKIPPED
        post.post_type = None
        session.add(post)
        await _write_event(
            session,
            post,
            "post_dismissed",
            {"prev_status": prev_status, "reason": reason},
            note=reason,
        )
        await session.commit()

        rprint(f"[yellow]Signal {post_id[:8]} dismissed → SKIPPED.[/yellow]")
        if reason:
            rprint(f"  Reason: {reason}")

    with_session(_run)


@app.command("opt-out")
def posts_opt_out(post_id: str) -> None:
    """Mark a post as opted out — excluded from matching."""

    async def _run(session):
        post = await _resolve_post(session, post_id)
        if not post:
            rprint(f"[red]Signal {post_id!r} not found.[/red]")
            raise typer.Exit(1)
        if post.opted_out:
            rprint(f"[dim]Signal {post_id[:8]} is already opted out.[/dim]")
            return

        post.opted_out = True
        session.add(post)
        await _write_event(session, post, "post_opted_out", note="User requested removal")
        await session.commit()

        rprint(f"[yellow]Signal {post_id[:8]} opted out → excluded from matching.[/yellow]")

    with_session(_run)


@app.command("un-opt-out")
def posts_un_opt_out(post_id: str) -> None:
    """Restore a post that was previously opted out."""

    async def _run(session):
        post = await _resolve_post(session, post_id)
        if not post:
            rprint(f"[red]Signal {post_id!r} not found.[/red]")
            raise typer.Exit(1)
        if not post.opted_out:
            rprint(f"[dim]Signal {post_id[:8]} is not opted out.[/dim]")
            return

        post.opted_out = False
        session.add(post)
        await _write_event(session, post, "post_un_opted_out", note="Opt-out reversed")
        await session.commit()

        rprint(f"[green]Signal {post_id[:8]} opt-out removed → back in matching pool.[/green]")

    with_session(_run)

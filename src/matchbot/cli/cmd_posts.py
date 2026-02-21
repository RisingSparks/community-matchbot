"""matchbot posts — browse and manage indexed posts."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from matchbot.cli._db import with_session
from matchbot.db.models import Event, Post, PostStatus, PostType

app = typer.Typer(help="Browse and manage indexed posts")
console = Console()


@app.command("list")
def posts_list(
    role: Annotated[str | None, typer.Option("--role", help="seeker|camp")] = None,
    platform: Annotated[str | None, typer.Option("--platform")] = None,
    status: Annotated[str | None, typer.Option("--status")] = None,
    post_type: Annotated[str | None, typer.Option("--type", help="mentorship|infrastructure")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 20,
) -> None:
    """List posts."""

    async def _run(session):
        from sqlmodel import select

        q = select(Post)
        if role:
            q = q.where(Post.role == role)
        if platform:
            q = q.where(Post.platform == platform)
        if status:
            q = q.where(Post.status == status)
        if post_type:
            q = q.where(Post.post_type == post_type)
        q = q.order_by(Post.detected_at.desc()).limit(limit)  # type: ignore[arg-type]

        posts = (await session.exec(q)).all()
        if not posts:
            rprint("[yellow]No posts found.[/yellow]")
            return

        table = Table(title="Posts")
        table.add_column("ID", style="dim", width=10)
        table.add_column("Platform", width=10)
        table.add_column("Type", width=14)
        table.add_column("Role", width=8)
        table.add_column("Status", width=14)
        table.add_column("Title", no_wrap=False, max_width=50)
        table.add_column("Detected")

        for p in posts:
            table.add_row(
                p.id[:8],
                p.platform,
                p.post_type,
                p.role or "?",
                p.status,
                p.title[:50],
                p.detected_at.strftime("%Y-%m-%d"),
            )
        console.print(table)

    with_session(_run)


@app.command("show")
def posts_show(post_id: str) -> None:
    """Show full details of a post."""

    async def _run(session):
        post = await session.get(Post, post_id)
        if not post:
            rprint(f"[red]Post {post_id!r} not found.[/red]")
            raise typer.Exit(1)

        if post.post_type == PostType.INFRASTRUCTURE:
            type_detail = (
                f"[bold]Infra Role:[/bold] {post.infra_role or '?'}  |  "
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
                f"[bold]Camp:[/bold] {post.camp_name}  |  "
                f"[bold]Availability:[/bold] {post.availability_notes}\n"
            )

        content = (
            f"[bold]Platform:[/bold] {post.platform} / {post.source_community}\n"
            f"[bold]Type:[/bold] {post.post_type}  |  [bold]Status:[/bold] {post.status}\n"
            f"[bold]Confidence:[/bold] {post.extraction_confidence}  |  "
            f"[bold]Method:[/bold] {post.extraction_method}\n"
            f"{type_detail}\n"
            f"[bold yellow]Title:[/bold yellow] {post.title}\n\n"
            f"[bold]Body:[/bold]\n{post.raw_text}"
        )
        console.print(Panel(content, title=f"Post {post.id[:8]}", expand=False))

    with_session(_run)


@app.command("re-extract")
def posts_re_extract(post_id: str) -> None:
    """Re-run LLM extraction on a post."""

    async def _run(session):
        post = await session.get(Post, post_id)
        if not post:
            rprint(f"[red]Post {post_id!r} not found.[/red]")
            raise typer.Exit(1)

        from matchbot.extraction import process_post
        from matchbot.extraction.anthropic_extractor import AnthropicExtractor
        from matchbot.extraction.openai_extractor import OpenAIExtractor
        from matchbot.settings import get_settings

        settings = get_settings()
        extractor = (
            AnthropicExtractor()
            if settings.llm_provider == "anthropic"
            else OpenAIExtractor()
        )

        post.status = PostStatus.RAW  # reset to re-process
        session.add(post)
        await session.commit()

        try:
            updated = await process_post(session, post, extractor)
        finally:
            await extractor.aclose()
        rprint(f"[green]Re-extracted post {post_id[:8]}: status={updated.status}[/green]")

    with_session(_run)


@app.command("flag")
def posts_flag(
    post_id: str,
    note: Annotated[str | None, typer.Option("--note")] = None,
) -> None:
    """Flag a post for human review."""

    async def _run(session):
        post = await session.get(Post, post_id)
        if not post:
            rprint(f"[red]Post {post_id!r} not found.[/red]")
            raise typer.Exit(1)
        post.status = PostStatus.NEEDS_REVIEW
        session.add(post)
        await session.commit()
        rprint(f"[yellow]Post {post_id[:8]} flagged for review.[/yellow]")
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
    """Correct extraction fields on a NEEDS_REVIEW post."""

    async def _run(session):
        post = await session.get(Post, post_id)
        if not post:
            rprint(f"[red]Post {post_id!r} not found.[/red]")
            raise typer.Exit(1)
        if post.status != PostStatus.NEEDS_REVIEW:
            rprint(f"[red]Post {post_id[:8]} has status {post.status!r}. Only NEEDS_REVIEW posts can be edited.[/red]")
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

        rprint(f"[green]Post {post_id[:8]} updated:[/green]")
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
    """Promote a NEEDS_REVIEW post to INDEXED, optionally correcting fields first."""

    async def _run(session):
        post = await session.get(Post, post_id)
        if not post:
            rprint(f"[red]Post {post_id!r} not found.[/red]")
            raise typer.Exit(1)
        if post.status != PostStatus.NEEDS_REVIEW:
            rprint(f"[red]Post {post_id[:8]} has status {post.status!r}. Only NEEDS_REVIEW posts can be approved.[/red]")
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

        rprint(f"[green]Post {post_id[:8]} approved → INDEXED.[/green]")
        for c in changes:
            rprint(f"  {c}")
        if note:
            rprint(f"  Note: {note}")

        # Trigger matching now that the post is indexed
        from matchbot.matching.queue import propose_matches

        await propose_matches(session, post)
        await session.refresh(post)
        rprint(f"[dim]Matches proposed for {post_id[:8]}.[/dim]")

    with_session(_run)


@app.command("dismiss")
def posts_dismiss(
    post_id: str,
    reason: Annotated[str | None, typer.Option("--reason", help="spam|off-topic|duplicate|other")] = None,
) -> None:
    """Permanently skip a NEEDS_REVIEW post (spam, off-topic, duplicate)."""

    async def _run(session):
        post = await session.get(Post, post_id)
        if not post:
            rprint(f"[red]Post {post_id!r} not found.[/red]")
            raise typer.Exit(1)
        if post.status not in {PostStatus.NEEDS_REVIEW, PostStatus.ERROR}:
            rprint(
                f"[red]Post {post_id[:8]} has status {post.status!r}. "
                "Only NEEDS_REVIEW or ERROR posts can be dismissed.[/red]"
            )
            raise typer.Exit(1)

        prev_status = post.status
        post.status = PostStatus.SKIPPED
        session.add(post)
        await _write_event(
            session,
            post,
            "post_dismissed",
            {"prev_status": prev_status, "reason": reason},
            note=reason,
        )
        await session.commit()

        rprint(f"[yellow]Post {post_id[:8]} dismissed → SKIPPED.[/yellow]")
        if reason:
            rprint(f"  Reason: {reason}")

    with_session(_run)

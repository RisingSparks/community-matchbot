"""matchbot queue — review and manage the match queue."""

from __future__ import annotations

import asyncio
from typing import Annotated, Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from matchbot.cli._db import with_session
from matchbot.db.models import Match, MatchStatus, Post
from matchbot.lifecycle.status import transition
from matchbot.matching.queue import get_match, get_queue
from matchbot.settings import get_settings

app = typer.Typer(help="Review and manage the match queue")
console = Console()


def _short_text(text: str, max_len: int = 60) -> str:
    return text[:max_len] + "…" if len(text) > max_len else text


@app.command("list")
def queue_list(
    status: Annotated[str, typer.Option("--status")] = MatchStatus.PROPOSED,
    min_score: Annotated[float, typer.Option("--min-score")] = 0.0,
    limit: Annotated[int, typer.Option("--limit")] = 25,
) -> None:
    """List matches in the queue."""

    async def _run(session):
        from sqlmodel import select

        matches = await get_queue(session, status=status, min_score=min_score, limit=limit)
        if not matches:
            rprint(f"[yellow]No matches with status={status!r} and score≥{min_score}[/yellow]")
            return

        table = Table(title=f"Match Queue  [{status}]  ≥{min_score:.2f}")
        table.add_column("ID", style="dim", width=12)
        table.add_column("Score", justify="right")
        table.add_column("Method", width=14)
        table.add_column("Seeker snippet", no_wrap=False, max_width=35)
        table.add_column("Camp snippet", no_wrap=False, max_width=35)
        table.add_column("Created")

        for m in matches:
            seeker = await session.get(Post, m.seeker_post_id)
            camp = await session.get(Post, m.camp_post_id)
            seeker_text = _short_text(seeker.title if seeker else "?")
            camp_text = _short_text(camp.title if camp else "?")
            table.add_row(
                m.id[:8],
                f"{m.score:.3f}",
                m.match_method,
                seeker_text,
                camp_text,
                m.created_at.strftime("%Y-%m-%d"),
            )

        console.print(table)

    with_session(_run)


@app.command("view")
def queue_view(match_id: str) -> None:
    """View full details of a match."""

    async def _run(session):
        match = await get_match(session, match_id)
        if not match:
            rprint(f"[red]Match {match_id!r} not found.[/red]")
            raise typer.Exit(1)

        seeker = await session.get(Post, match.seeker_post_id)
        camp = await session.get(Post, match.camp_post_id)

        breakdown = match.score_breakdown_dict()
        breakdown_str = "\n".join(f"  {k}: {v:.4f}" for k, v in breakdown.items())

        panel_content = (
            f"[bold]Status:[/bold] {match.status}\n"
            f"[bold]Score:[/bold] {match.score:.4f}  (method: {match.match_method})\n"
            f"[bold]Confidence:[/bold] {match.confidence}\n\n"
            f"[bold cyan]Score breakdown:[/bold cyan]\n{breakdown_str}\n\n"
            f"[bold]Moderator notes:[/bold] {match.moderator_notes or '—'}\n\n"
            f"[bold yellow]SEEKER:[/bold yellow] {seeker.title if seeker else '?'}\n"
            f"{seeker.raw_text[:500] if seeker else ''}\n\n"
            f"[bold green]CAMP:[/bold green] {camp.title if camp else '?'}\n"
            f"{camp.raw_text[:500] if camp else ''}"
        )

        console.print(Panel(panel_content, title=f"Match {match.id[:8]}", expand=False))

    with_session(_run)


@app.command("approve")
def queue_approve(
    match_id: str,
    note: Annotated[Optional[str], typer.Option("--note")] = None,
) -> None:
    """Approve a proposed match."""

    async def _run(session):
        match = await get_match(session, match_id)
        if not match:
            rprint(f"[red]Match {match_id!r} not found.[/red]")
            raise typer.Exit(1)
        updated = await transition(session, match, MatchStatus.APPROVED, actor="moderator", note=note)
        rprint(f"[green]Match {match_id[:8]} approved.[/green]")
        if note:
            rprint(f"  Note: {note}")

    with_session(_run)


@app.command("reject")
def queue_reject(
    match_id: str,
    reason: Annotated[str, typer.Option("--reason")] = "",
) -> None:
    """Decline a proposed match."""

    async def _run(session):
        match = await get_match(session, match_id)
        if not match:
            rprint(f"[red]Match {match_id!r} not found.[/red]")
            raise typer.Exit(1)
        match.mismatch_reason = reason or None
        session.add(match)
        await session.commit()
        updated = await transition(session, match, MatchStatus.DECLINED, actor="moderator", note=reason)
        rprint(f"[yellow]Match {match_id[:8]} declined.[/yellow]")
        if reason:
            rprint(f"  Reason: {reason}")

    with_session(_run)


@app.command("send-intro")
def queue_send_intro(
    match_id: str,
    platform: Annotated[Optional[str], typer.Option("--platform", help="reddit|discord|facebook")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Send intro message for an approved match."""

    async def _run(session):
        match = await get_match(session, match_id)
        if not match:
            rprint(f"[red]Match {match_id!r} not found.[/red]")
            raise typer.Exit(1)
        if match.status != MatchStatus.APPROVED:
            rprint(f"[red]Match must be APPROVED before sending intro (current: {match.status}).[/red]")
            raise typer.Exit(1)

        seeker = await session.get(Post, match.seeker_post_id)
        camp = await session.get(Post, match.camp_post_id)

        target_platform = platform or (seeker.platform if seeker else "reddit")

        from matchbot.messaging.renderer import render_intro

        intro_text = render_intro(seeker, camp, target_platform)

        console.print(Panel(intro_text, title="[cyan]Intro Message Preview[/cyan]", expand=False))

        if dry_run:
            rprint("[dim]--dry-run: not sending.[/dim]")
            return

        confirmed = typer.confirm("Send this intro?", default=False)
        if not confirmed:
            rprint("[yellow]Aborted.[/yellow]")
            return

        from datetime import datetime, timezone
        from matchbot.messaging import send_intro_message

        await send_intro_message(session, match, seeker, camp, target_platform)
        match.intro_sent_at = datetime.now(timezone.utc)
        match.intro_platform = target_platform
        session.add(match)
        await transition(session, match, MatchStatus.INTRO_SENT, actor="moderator")
        rprint(f"[green]Intro sent via {target_platform}.[/green]")

    with_session(_run)


@app.command("status")
def queue_status(
    match_id: str,
    new_status: str,
    note: Annotated[Optional[str], typer.Option("--note")] = None,
) -> None:
    """Manually override match status."""

    async def _run(session):
        match = await get_match(session, match_id)
        if not match:
            rprint(f"[red]Match {match_id!r} not found.[/red]")
            raise typer.Exit(1)
        updated = await transition(session, match, new_status, actor="moderator", note=note)
        rprint(f"[green]Match {match_id[:8]} → {new_status}.[/green]")

    with_session(_run)

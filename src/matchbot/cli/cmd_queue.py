"""matchbot queue — review and manage the match queue."""

from __future__ import annotations

from datetime import UTC
from typing import Annotated

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from matchbot.cli._db import with_session
from matchbot.db.models import Match, MatchStatus, Post
from matchbot.lifecycle.status import transition
from matchbot.matching.queue import get_match, get_queue

app = typer.Typer(help="Review and facilitate potential connections")
console = Console()


def _short_text(text: str, max_len: int = 60) -> str:
    return text[:max_len] + "…" if len(text) > max_len else text


@app.command("list")
def queue_list(
    status: Annotated[str, typer.Option("--status")] = MatchStatus.PROPOSED,
    min_score: Annotated[float, typer.Option("--min-score")] = 0.0,
    limit: Annotated[int, typer.Option("--limit")] = 25,
    post_type: Annotated[str | None, typer.Option("--type", help="mentorship|infrastructure")] = None,
) -> None:
    """List pending connection opportunities."""

    async def _run(session):

        matches = await get_queue(session, status=status, min_score=min_score, limit=limit)

        # Filter by post_type if requested (check either post in the pair)
        if post_type:
            filtered = []
            for m in matches:
                seeker = await session.get(Post, m.seeker_post_id)
                if seeker and seeker.post_type == post_type:
                    filtered.append(m)
            matches = filtered

        if not matches:
            rprint(f"[yellow]No potential connections with status={status!r} and score≥{min_score}[/yellow]")
            return

        title = f"Potential Connections  [{status}]  ≥{min_score:.2f}"
        if post_type:
            title += f"  [{post_type}]"

        table = Table(title=title)
        table.add_column("ID", style="dim", width=12)
        table.add_column("Score", justify="right")
        table.add_column("Method", width=18)
        table.add_column("Seeker snippet", no_wrap=False, max_width=35)
        table.add_column("Camp snippet", no_wrap=False, max_width=35)
        table.add_column("Detected")

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
    """Examine a potential connection."""

    async def _run(session):
        match = await get_match(session, match_id)
        if not match:
            rprint(f"[red]Connection {match_id!r} not found.[/red]")
            raise typer.Exit(1)

        seeker = await session.get(Post, match.seeker_post_id)
        camp = await session.get(Post, match.camp_post_id)

        breakdown = match.score_breakdown_dict()
        breakdown_str = "\n".join(f"  {k}: {v:.4f}" for k, v in breakdown.items())

        panel_content = (
            f"[bold]Status:[/bold] {match.status}\n"
            f"[bold]Score:[/bold] {match.score:.4f}  (method: {match.match_method})\n"
            f"[bold]Confidence:[/bold] {match.confidence}\n\n"
            f"[bold cyan]Alignment breakdown:[/bold cyan]\n{breakdown_str}\n\n"
            f"[bold]Moderator notes:[/bold] {match.moderator_notes or '—'}\n\n"
            f"[bold magenta]Intro draft:[/bold magenta]\n{match.intro_draft or '(not yet rendered)'}\n\n"
            f"[bold yellow]SEEKER:[/bold yellow] {seeker.title if seeker else '?'}\n"
            f"{seeker.raw_text[:500] if seeker else ''}\n\n"
            f"[bold green]CAMP/PROJECT:[/bold green] {camp.title if camp else '?'}\n"
            f"{camp.raw_text[:500] if camp else ''}"
        )

        console.print(Panel(panel_content, title=f"Connection {match.id[:8]}", expand=False))

    with_session(_run)


@app.command("approve")
def queue_approve(
    match_id: str,
    note: Annotated[str | None, typer.Option("--note")] = None,
) -> None:
    """Verify this connection for introduction."""

    async def _run(session):
        match = await get_match(session, match_id)
        if not match:
            rprint(f"[red]Connection {match_id!r} not found.[/red]")
            raise typer.Exit(1)
        await transition(session, match, MatchStatus.APPROVED, actor="moderator", note=note)
        rprint(f"[green]Connection {match_id[:8]} verified for intro.[/green]")
        if note:
            rprint(f"  Note: {note}")

    with_session(_run)


@app.command("reject")
def queue_reject(
    match_id: str,
    reason: Annotated[str, typer.Option("--reason")] = "",
) -> None:
    """Dismiss this connection as a mismatch."""

    async def _run(session):
        match = await get_match(session, match_id)
        if not match:
            rprint(f"[red]Connection {match_id!r} not found.[/red]")
            raise typer.Exit(1)
        match.mismatch_reason = reason or None
        session.add(match)
        await session.commit()
        await transition(session, match, MatchStatus.DECLINED, actor="moderator", note=reason)
        rprint(f"[yellow]Connection {match_id[:8]} dismissed.[/yellow]")
        if reason:
            rprint(f"  Reason: {reason}")

    with_session(_run)


@app.command("send-intro")
def queue_send_intro(
    match_id: str,
    platform: Annotated[str | None, typer.Option("--platform", help="reddit|discord|facebook")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Facilitate a handshake between parties."""

    async def _run(session):
        match = await get_match(session, match_id)
        if not match:
            rprint(f"[red]Connection {match_id!r} not found.[/red]")
            raise typer.Exit(1)
        if match.status != MatchStatus.APPROVED:
            rprint(f"[red]Connection must be VERIFIED before sending intro (current: {match.status}).[/red]")
            raise typer.Exit(1)

        seeker = await session.get(Post, match.seeker_post_id)
        camp = await session.get(Post, match.camp_post_id)

        target_platform = platform or (seeker.platform if seeker else "reddit")

        from matchbot.messaging.renderer import render_intro

        intro_text = match.intro_draft or render_intro(seeker, camp, target_platform)

        console.print(Panel(intro_text, title="[cyan]Intro Handshake Preview[/cyan]", expand=False))

        if dry_run:
            rprint("[dim]--dry-run: not sending.[/dim]")
            return

        confirmed = typer.confirm("Send this handshake?", default=False)
        if not confirmed:
            rprint("[yellow]Aborted.[/yellow]")
            return

        from datetime import datetime

        from matchbot.messaging import send_intro_message

        await send_intro_message(session, match, seeker, camp, target_platform)
        match.intro_sent_at = datetime.now(UTC)
        match.intro_platform = target_platform
        session.add(match)
        await transition(session, match, MatchStatus.INTRO_SENT, actor="moderator")
        rprint(f"[green]Handshake sent via {target_platform}.[/green]")

    with_session(_run)


@app.command("triage")
def queue_triage(
    match_id: str,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Analyze alignment for an ambiguous connection."""

    async def _run(session):
        match = await get_match(session, match_id)
        if not match:
            rprint(f"[red]Connection {match_id!r} not found.[/red]")
            raise typer.Exit(1)

        seeker = await session.get(Post, match.seeker_post_id)
        camp = await session.get(Post, match.camp_post_id)
        if not seeker or not camp:
            rprint("[red]Could not load seeker or camp signal.[/red]")
            raise typer.Exit(1)

        from matchbot.extraction.anthropic_extractor import AnthropicExtractor
        from matchbot.extraction.openai_extractor import OpenAIExtractor
        from matchbot.matching.triage import llm_triage
        from matchbot.settings import get_settings

        settings = get_settings()
        extractor = OpenAIExtractor() if settings.llm_provider == "openai" else AnthropicExtractor()

        rprint(f"[cyan]Analyzing alignment for connection {match_id[:8]}…[/cyan]")
        try:
            confidence, rationale = await llm_triage(seeker, camp, extractor)
        finally:
            await extractor.aclose()

        rprint(f"  Confidence: {confidence:.3f}")
        rprint(f"  Rationale: {rationale}")

        if dry_run:
            rprint("[dim]--dry-run: not updating.[/dim]")
            return

        # Update match record: store triage result and clear the "needs triage" note
        notes = match.moderator_notes or ""
        notes = notes.replace("[needs LLM triage]", "").strip()
        notes = (notes + f" [triage: {confidence:.2f} — {rationale}]").strip()
        match.moderator_notes = notes
        match.match_method = "llm_triage"
        match.confidence = confidence
        session.add(match)
        await session.commit()
        rprint(f"[green]Analysis complete. Connection {match_id[:8]} updated.[/green]")

    with_session(_run)


@app.command("feedback-list")
def queue_feedback_list(
    limit: Annotated[int, typer.Option("--limit")] = 25,
) -> None:
    """List connections awaiting feedback."""

    async def _run(session):
        from sqlmodel import select

        matches = (
            await session.exec(
                select(Match)
                .where(
                    Match.status == MatchStatus.INTRO_SENT,
                    Match.moderator_notes.contains("[feedback pending]"),  # type: ignore[union-attr]
                )
                .order_by(Match.intro_sent_at)  # type: ignore[attr-defined]
                .limit(limit)
            )
        ).all()

        if not matches:
            rprint("[yellow]No connections with [feedback pending].[/yellow]")
            return

        table = Table(title="Feedback Pending")
        table.add_column("ID", style="dim", width=12)
        table.add_column("Score", justify="right")
        table.add_column("Platform", width=10)
        table.add_column("Seeker snippet", no_wrap=False, max_width=35)
        table.add_column("Camp snippet", no_wrap=False, max_width=35)
        table.add_column("Handshake sent")

        for m in matches:
            seeker = await session.get(Post, m.seeker_post_id)
            camp = await session.get(Post, m.camp_post_id)
            seeker_text = _short_text(seeker.title if seeker else "?")
            camp_text = _short_text(camp.title if camp else "?")
            sent_at = m.intro_sent_at.strftime("%Y-%m-%d") if m.intro_sent_at else "—"
            table.add_row(
                m.id[:8],
                f"{m.score:.3f}",
                m.intro_platform or "—",
                seeker_text,
                camp_text,
                sent_at,
            )

        console.print(table)

    with_session(_run)


@app.command("send-feedback")
def queue_send_feedback(
    match_id: str,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Check in on a facilitated connection."""

    async def _run(session):
        match = await get_match(session, match_id)
        if not match:
            rprint(f"[red]Connection {match_id!r} not found.[/red]")
            raise typer.Exit(1)

        if not match.moderator_notes or "[feedback pending]" not in match.moderator_notes:
            rprint(f"[red]Connection {match_id[:8]} does not have [feedback pending] in notes.[/red]")
            raise typer.Exit(1)

        seeker = await session.get(Post, match.seeker_post_id)
        camp = await session.get(Post, match.camp_post_id)
        if not seeker or not camp:
            rprint("[red]Could not load seeker or camp signal.[/red]")
            raise typer.Exit(1)

        platform = match.intro_platform or (seeker.platform if seeker else "reddit")

        from matchbot.messaging.renderer import render_feedback

        seeker_text = render_feedback(seeker, camp, platform)
        camp_text = render_feedback(camp, seeker, platform)

        console.print(Panel(seeker_text, title=f"[cyan]Check-in → {seeker.author_display_name or seeker.platform_author_id}[/cyan]", expand=False))
        console.print(Panel(camp_text, title=f"[cyan]Check-in → {camp.author_display_name or camp.platform_author_id}[/cyan]", expand=False))

        if dry_run:
            rprint("[dim]--dry-run: not sending.[/dim]")
            return

        confirmed = typer.confirm("Send these check-in messages?", default=False)
        if not confirmed:
            rprint("[yellow]Aborted.[/yellow]")
            return

        from matchbot.messaging import send_feedback_message

        await send_feedback_message(session, match, seeker, camp)

        # Strip [feedback pending] from notes
        notes = (match.moderator_notes or "").replace("[feedback pending]", "").strip()
        match.moderator_notes = notes or None
        session.add(match)
        await session.commit()

        rprint(f"[green]Check-in sent for connection {match_id[:8]}.[/green]")

    with_session(_run)


@app.command("status")
def queue_status(
    match_id: str,
    new_status: str,
    note: Annotated[str | None, typer.Option("--note")] = None,
) -> None:
    """Manually override connection status."""

    async def _run(session):
        match = await get_match(session, match_id)
        if not match:
            rprint(f"[red]Connection {match_id!r} not found.[/red]")
            raise typer.Exit(1)
        await transition(session, match, new_status, actor="moderator", note=note)
        rprint(f"[green]Connection {match_id[:8]} → {new_status}.[/green]")

    with_session(_run)

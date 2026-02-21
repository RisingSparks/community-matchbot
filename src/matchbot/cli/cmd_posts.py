"""matchbot posts — browse and manage indexed posts."""

from __future__ import annotations

from typing import Annotated, Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from matchbot.cli._db import with_session
from matchbot.db.models import Post, PostStatus

app = typer.Typer(help="Browse and manage indexed posts")
console = Console()


@app.command("list")
def posts_list(
    role: Annotated[Optional[str], typer.Option("--role", help="seeker|camp")] = None,
    platform: Annotated[Optional[str], typer.Option("--platform")] = None,
    status: Annotated[Optional[str], typer.Option("--status")] = None,
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
        q = q.order_by(Post.detected_at.desc()).limit(limit)  # type: ignore[arg-type]

        posts = (await session.exec(q)).all()
        if not posts:
            rprint("[yellow]No posts found.[/yellow]")
            return

        table = Table(title="Posts")
        table.add_column("ID", style="dim", width=10)
        table.add_column("Platform", width=10)
        table.add_column("Role", width=8)
        table.add_column("Status", width=14)
        table.add_column("Title", no_wrap=False, max_width=50)
        table.add_column("Detected")

        for p in posts:
            table.add_row(
                p.id[:8],
                p.platform,
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

        content = (
            f"[bold]Platform:[/bold] {post.platform} / {post.source_community}\n"
            f"[bold]Role:[/bold] {post.role}  |  [bold]Status:[/bold] {post.status}\n"
            f"[bold]Confidence:[/bold] {post.extraction_confidence}  |  "
            f"[bold]Method:[/bold] {post.extraction_method}\n"
            f"[bold]Vibes:[/bold] {post.vibes}\n"
            f"[bold]Contributions:[/bold] {post.contribution_types}\n"
            f"[bold]Year:[/bold] {post.year}\n"
            f"[bold]Camp:[/bold] {post.camp_name}  |  "
            f"[bold]Availability:[/bold] {post.availability_notes}\n\n"
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

        updated = await process_post(session, post, extractor)
        rprint(f"[green]Re-extracted post {post_id[:8]}: status={updated.status}[/green]")

    with_session(_run)


@app.command("flag")
def posts_flag(
    post_id: str,
    note: Annotated[Optional[str], typer.Option("--note")] = None,
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

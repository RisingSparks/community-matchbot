"""matchbot submit — manually ingest posts."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Annotated

import typer
from rich import print as rprint

from matchbot.cli._db import with_session
from matchbot.db.models import Platform, Post, PostStatus

app = typer.Typer(help="Manually ingest posts")


@app.command("text")
def submit_text(
    text: str,
    platform: Annotated[str, typer.Option("--platform", help="reddit|discord|facebook|manual")] = Platform.MANUAL,
    community: Annotated[str, typer.Option("--community")] = "",
    title: Annotated[str, typer.Option("--title")] = "",
    extract: Annotated[bool, typer.Option("--extract/--no-extract")] = True,
) -> None:
    """Ingest a post from text input."""

    async def _run(session):
        import uuid

        post = Post(
            platform=platform,
            platform_post_id=f"manual_{uuid.uuid4().hex[:12]}",
            platform_author_id="manual",
            source_community=community,
            title=title or text[:80],
            raw_text=text[:2000],
            status=PostStatus.RAW,
        )
        session.add(post)
        await session.commit()
        await session.refresh(post)

        if extract:
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
            try:
                post = await process_post(session, post, extractor)
            finally:
                await extractor.aclose()

        rprint(f"[green]Post ingested: {post.id[:8]}  status={post.status}[/green]")

    with_session(_run)


@app.command("file")
def submit_file(
    file_path: str,
    platform: Annotated[str, typer.Option("--platform")] = Platform.MANUAL,
    extract: Annotated[bool, typer.Option("--extract/--no-extract")] = True,
) -> None:
    """Ingest posts from a CSV file (columns: title, body, community)."""

    async def _run(session):
        import uuid

        path = Path(file_path)
        if not path.exists():
            rprint(f"[red]File not found: {file_path}[/red]")
            raise typer.Exit(1)

        from matchbot.extraction import process_post
        from matchbot.extraction.anthropic_extractor import AnthropicExtractor
        from matchbot.extraction.openai_extractor import OpenAIExtractor
        from matchbot.settings import get_settings

        settings = get_settings()
        extractor = None
        if extract:
            extractor = (
                AnthropicExtractor()
                if settings.llm_provider == "anthropic"
                else OpenAIExtractor()
            )

        count = 0
        try:
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    post = Post(
                        platform=platform,
                        platform_post_id=f"manual_{uuid.uuid4().hex[:12]}",
                        platform_author_id="manual",
                        source_community=row.get("community", ""),
                        title=row.get("title", "")[:80],
                        raw_text=row.get("body", "")[:2000],
                        status=PostStatus.RAW,
                    )
                    session.add(post)
                    await session.commit()
                    await session.refresh(post)

                    if extract and extractor:
                        post = await process_post(session, post, extractor)
                    count += 1
        finally:
            if extractor:
                await extractor.aclose()

        rprint(f"[green]Ingested {count} posts from {file_path}.[/green]")

    with_session(_run)

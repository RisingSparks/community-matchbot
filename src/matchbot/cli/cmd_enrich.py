"""matchbot enrich — enrich camp posts from the Burning Man WWW Guide."""

from __future__ import annotations

import logging
from typing import Annotated

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from matchbot.cli._db import with_session
from matchbot.log_config import log_exception

app = typer.Typer(help="Enrich camp posts from external data sources")
console = Console()
logger = logging.getLogger(__name__)


@app.command("www-guide")
def enrich_www_guide(
    url: Annotated[str | None, typer.Option("--url", help="Guide API URL (overrides settings)")] = None,
    year: Annotated[int | None, typer.Option("--year", help="Burn year to tag records")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview matches without writing")] = False,
) -> None:
    """Fetch WWW Guide camp data and enrich matched camp posts."""

    async def _run(session):
        from matchbot.enrichment.www_guide import enrich_camp_posts, fetch_guide_camps
        from matchbot.settings import get_settings

        settings = get_settings()
        guide_url = url or settings.www_guide_url
        guide_year = year or settings.www_guide_year

        if not guide_url:
            rprint("[red]No WWW Guide URL configured. Set WWW_GUIDE_URL in .env or pass --url.[/red]")
            raise typer.Exit(1)

        rprint(f"[cyan]Fetching guide data from {guide_url} ...[/cyan]")

        try:
            camps = await fetch_guide_camps(guide_url, year=guide_year)
        except Exception as exc:
            log_exception(logger, "Failed to fetch WWW Guide data from %s: %s", guide_url, exc)
            rprint(f"[red]Failed to fetch guide: {exc}[/red]")
            raise typer.Exit(1)

        rprint(f"[green]Fetched {len(camps)} camps from guide.[/green]")

        enriched = await enrich_camp_posts(session, camps, dry_run=dry_run)

        if not enriched:
            rprint("[yellow]No matching camp posts found to enrich.[/yellow]")
            return

        table = Table(title=f"{'[DRY RUN] ' if dry_run else ''}Enriched Posts")
        table.add_column("Post ID", style="dim", width=10)
        table.add_column("Camp Name", max_width=30)
        table.add_column("Guide Match", max_width=30)
        table.add_column("Location")
        table.add_column("Size", justify="right")

        for post, guide_camp in enriched:
            table.add_row(
                post.id[:8],
                post.camp_name or "?",
                guide_camp.name[:30],
                guide_camp.location_string[:20] or "—",
                str(guide_camp.camp_size) if guide_camp.camp_size else "—",
            )

        console.print(table)

        if dry_run:
            rprint(f"[dim]--dry-run: {len(enriched)} posts would be updated, nothing written.[/dim]")
        else:
            rprint(f"[green]Enriched {len(enriched)} camp posts.[/green]")

    with_session(_run)

"""matchbot report — generate pilot reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich import print as rprint
from rich.console import Console

from matchbot.cli._db import with_session
from matchbot.settings import get_settings

app = typer.Typer(help="Generate pilot reports")
console = Console()


@app.command("metrics")
def report_metrics(
    format: Annotated[str, typer.Option("--format", help="json|csv")] = "json",
    output: Annotated[str | None, typer.Option("--output")] = None,
) -> None:
    """Compute and output pilot metrics."""

    async def _run(session):
        from matchbot.reporting.metrics import compute_metrics

        metrics = await compute_metrics(session)

        if format == "csv":
            rprint("[yellow]CSV not supported for metrics (use json or --format csv for matches).[/yellow]")
            return

        if output:
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            with open(output, "w") as f:
                json.dump(metrics, f, indent=2)
            rprint(f"[green]Metrics written to {output}[/green]")
        else:
            rprint(json.dumps(metrics, indent=2))

    with_session(_run)


@app.command("matches")
def report_matches(
    format: Annotated[str, typer.Option("--format")] = "csv",
    output: Annotated[str | None, typer.Option("--output")] = None,
) -> None:
    """Export match data."""

    async def _run(session):
        settings = get_settings()
        from matchbot.reporting.metrics import export_matches_csv

        out_path = output or str(Path(settings.report_output_dir) / "matches.csv")
        await export_matches_csv(session, out_path)
        rprint(f"[green]Matches exported to {out_path}[/green]")

    with_session(_run)


@app.command("weekly")
def report_weekly(
    week: Annotated[str | None, typer.Option("--week", help="ISO week e.g. 2025-W34")] = None,
) -> None:
    """Generate weekly summary."""

    async def _run(session):
        from matchbot.reporting.metrics import compute_metrics

        metrics = await compute_metrics(session)
        week_label = week or "current"
        rprint(f"\n[bold cyan]Weekly Report — {week_label}[/bold cyan]")
        rprint(f"  Active camp profiles:    {metrics['active_camp_profiles']}")
        rprint(f"  Active seeker profiles:  {metrics['active_seeker_profiles']}")
        rprint(f"  Total posts indexed:     {metrics['total_posts_indexed']}")
        rprint(f"  Match attempts:          {metrics['match_attempts_total']}")
        rprint(f"  Connections made:             {metrics['intro_sent_total']}")
        rprint(f"  Conversations started:   {metrics['conversation_started_total']}")
        rprint(f"  Onboarded:               {metrics['onboarded_total']}")
        rprint(f"  Intro→Conversation rate: {metrics['intro_to_conversation_rate']:.1%}")
        rprint(f"  Conv→Onboarding rate:    {metrics['conversation_to_onboarding_rate']:.1%}")

    with_session(_run)

"""Root Typer app — registers all sub-command groups."""

import os
from typing import Annotated

import typer

from matchbot.cli.cmd_data import app as data_app
from matchbot.cli.cmd_enrich import app as enrich_app
from matchbot.cli.cmd_posts import app as posts_app
from matchbot.cli.cmd_queue import app as queue_app
from matchbot.cli.cmd_report import app as report_app
from matchbot.cli.cmd_submit import app as submit_app
from matchbot.log_config import configure_logging
from matchbot.settings import get_settings

app = typer.Typer(
    name="matchbot",
    help="Rising Sparks Matchmaking: Connecting Seekers & Builders",
    no_args_is_help=True,
)

app.add_typer(queue_app, name="queue", help="Review and facilitate potential connections")
app.add_typer(posts_app, name="posts", help="Browse and manage community signals")
app.add_typer(report_app, name="report", help="Generate impact and pilot findings")
app.add_typer(submit_app, name="submit", help="Manually add community signals")
app.add_typer(enrich_app, name="enrich", help="Enrich signals from the WWW Guide")
app.add_typer(data_app, name="data", help="Raw data caching and replay")


@app.callback()
def _root_options(
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose logs and full exception tracebacks"),
    ] = False,
) -> None:
    if verbose:
        os.environ["VERBOSE"] = "true"
        get_settings.cache_clear()
    configure_logging(verbose=verbose or get_settings().verbose)


if __name__ == "__main__":
    app()

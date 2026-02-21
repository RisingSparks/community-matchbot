"""Root Typer app — registers all sub-command groups."""

import typer

from matchbot.cli.cmd_enrich import app as enrich_app
from matchbot.cli.cmd_posts import app as posts_app
from matchbot.cli.cmd_queue import app as queue_app
from matchbot.cli.cmd_report import app as report_app
from matchbot.cli.cmd_submit import app as submit_app

app = typer.Typer(
    name="matchbot",
    help="Burning Man Theme Camp Connection Bot — moderator CLI",
    no_args_is_help=True,
)

app.add_typer(queue_app, name="queue", help="Review and manage the match queue")
app.add_typer(posts_app, name="posts", help="Browse and manage indexed posts")
app.add_typer(report_app, name="report", help="Generate pilot reports")
app.add_typer(submit_app, name="submit", help="Manually ingest posts")
app.add_typer(enrich_app, name="enrich", help="Enrich posts from external data sources")

if __name__ == "__main__":
    app()

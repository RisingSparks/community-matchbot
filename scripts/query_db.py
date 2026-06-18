#!/usr/bin/env python
# ruff: noqa: E402
"""
Database query utility for running arbitrary SQL queries.
Automatically routes queries to the configured backend (SQLite or Neon/Postgres)
defined in .env and formats output beautifully using Rich.

Usage:
    # Query database and view as table
    uv run python scripts/query_db.py "SELECT id, platform, status, title FROM post LIMIT 5;"

    # View full record details vertically
    uv run python scripts/query_db.py "SELECT * FROM post LIMIT 1;" --format vertical

    # Run query and output JSON (great for piping to other tools or agents)
    uv run python scripts/query_db.py \
        "SELECT count(*), status FROM post GROUP BY status;" --format json

    # Execute an update or modification query (will be committed automatically)
    uv run python scripts/query_db.py "UPDATE post SET status = 'extracted' WHERE id = 'xyz';"

    # Pipe query from stdin
    cat query.sql | uv run python scripts/query_db.py
"""

import asyncio
import csv
import io
import json
import sys
import time
import warnings
from argparse import ArgumentParser
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

# Add src to python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Suppress the SQLModel session.execute deprecation/user warnings when running raw SQL queries
warnings.filterwarnings("ignore")

from matchbot.db.engine import dispose_engine, get_session
from matchbot.settings import get_settings


async def run_query(sql: str, format_type: str, show_metadata: bool) -> None:
    settings = get_settings()
    db_backend = settings.database_backend

    # Determine if it is likely a write query
    is_write = any(
        sql.strip().upper().startswith(kw)
        for kw in ["INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "REPLACE", "TRUNCATE"]
    )

    start_time = time.perf_counter()

    try:
        async with get_session() as session:
            result = await session.execute(text(sql))

            if is_write:
                await session.commit()
                duration = time.perf_counter() - start_time
                rowcount = result.rowcount
                if show_metadata:
                    print(
                        f"Database: {db_backend.upper()} (Write Query)\n"
                        f"Query: {sql.strip()[:100]}...\n"
                        f"Rows Affected: {rowcount}\n"
                        f"Time: {duration:.3f}s\n"
                        f"Status: Committed successfully."
                    )
                else:
                    print(f"Affected rows: {rowcount}")
                return

            # For SELECT/Read queries
            keys = list(result.keys())
            rows = result.fetchall()
            duration = time.perf_counter() - start_time

            if not rows:
                if format_type in ("json", "csv"):
                    print("[]" if format_type == "json" else "")
                else:
                    print(f"Query returned 0 rows. (Took {duration:.3f}s)")
                return

            if format_type == "json":
                # Print raw JSON array of objects
                data = [dict(zip(keys, row, strict=False)) for row in rows]

                # Custom JSON encoder to handle datetime objects
                def json_serializer(obj):
                    if hasattr(obj, "isoformat"):
                        return obj.isoformat()
                    return str(obj)

                print(json.dumps(data, indent=2, default=json_serializer))

            elif format_type == "csv":
                # Print CSV
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(keys)
                for row in rows:
                    writer.writerow([str(val) if val is not None else "" for val in row])
                print(output.getvalue().strip())

            elif format_type == "vertical":
                # Vertical layout: useful for single rows with many columns
                from rich.console import Console

                console = Console()
                for idx, row in enumerate(rows, 1):
                    console.print(f"[bold cyan]--- Record {idx} ---[/bold cyan]")
                    for key, val in zip(keys, row, strict=False):
                        console.print(f"[bold green]{key}:[/bold green] {val}")
                    console.print()
                if show_metadata:
                    console.print(
                        f"[dim]Returned {len(rows)} rows in {duration:.3f}s "
                        f"({db_backend} backend)[/dim]"
                    )

            else:  # Table layout (default)
                from rich.console import Console
                from rich.table import Table

                console = Console()
                table = Table(show_header=True, header_style="bold magenta", box=None)

                for key in keys:
                    table.add_column(key)

                for row in rows:
                    table.add_row(*(str(val) if val is not None else "" for val in row))

                console.print(table)
                if show_metadata:
                    console.print(
                        f"[dim]Returned {len(rows)} rows in {duration:.3f}s "
                        f"({db_backend} backend)[/dim]"
                    )

    except DBAPIError as exc:
        print(f"Database Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error executing query: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        await dispose_engine()


def main():
    parser = ArgumentParser(description="Query the production SQL database.")
    parser.add_argument(
        "query", nargs="?", help="SQL query to execute. Use '-' to read from standard input."
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["table", "json", "csv", "vertical"],
        default="table",
        help="Output format: table (default), json, csv, vertical (record detail)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress metadata info (execution time, database backend, etc.)",
    )

    args = parser.parse_args()

    # Read from stdin if query argument is omitted or is '-'
    if not args.query or args.query == "-":
        if sys.stdin.isatty():
            parser.print_help()
            sys.exit(0)
        query = sys.stdin.read()
    else:
        query = args.query

    if not query.strip():
        print("Error: Empty query.", file=sys.stderr)
        sys.exit(1)

    asyncio.run(run_query(query, args.format, not args.quiet))


if __name__ == "__main__":
    main()

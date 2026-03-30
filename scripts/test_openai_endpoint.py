#!/usr/bin/env python
"""Minimal OpenAI Responses API smoke test using matchbot settings."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import openai
import typer

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from matchbot.log_config import configure_logging
from matchbot.settings import get_settings

app = typer.Typer()


@app.command()
def main(
    prompt: str = typer.Option("Reply with exactly: ok", help="Prompt to send."),
    max_output_tokens: int = typer.Option(
        512, "--max-output-tokens", help="Max output tokens for the test request."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging."),
) -> None:
    """Send one minimal request to OpenAI using the configured model/tier."""
    settings = get_settings()
    configure_logging(verbose=verbose or settings.verbose)

    if settings.llm_provider != "openai":
        typer.echo(f"Warning: LLM_PROVIDER={settings.llm_provider!r}; testing OpenAI anyway.")
    if not settings.openai_api_key:
        raise typer.BadParameter("OPENAI_API_KEY is not set.")

    asyncio.run(_main_async(prompt=prompt, max_output_tokens=max_output_tokens))


async def _main_async(*, prompt: str, max_output_tokens: int) -> None:
    settings = get_settings()
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    extra: dict[str, str] = {}
    if settings.openai_service_tier is not None:
        extra["service_tier"] = settings.openai_service_tier

    started_at = time.monotonic()
    try:
        response = await client.responses.create(
            model=settings.openai_model,
            input=prompt,
            max_output_tokens=max_output_tokens,
            **extra,
        )
    finally:
        await client.close()

    elapsed = time.monotonic() - started_at

    typer.echo(f"model={settings.openai_model}")
    typer.echo(f"service_tier={settings.openai_service_tier or 'default'}")
    typer.echo(f"response_id={getattr(response, 'id', '<none>')}")
    typer.echo(f"status={getattr(response, 'status', '<none>')}")
    typer.echo(f"incomplete_details={getattr(response, 'incomplete_details', None)!r}")
    typer.echo(f"usage={getattr(response, 'usage', None)!r}")
    typer.echo(f"elapsed_seconds={elapsed:.2f}")
    typer.echo("output_text:")
    typer.echo(getattr(response, "output_text", ""))


if __name__ == "__main__":
    app()

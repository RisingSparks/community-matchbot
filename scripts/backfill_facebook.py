#!/usr/bin/env python
"""Backfill historical Facebook posts from HAR or Extension JSON files."""

import asyncio
import json
import logging
import re
import shutil
import sys
from collections import defaultdict
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any

import typer

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from matchbot.backfill import accumulate_counts, new_backfill_counts
from matchbot.db.engine import create_db_and_tables, dispose_engine
from matchbot.importers.facebook_har import (
    backfill_facebook_posts,
    parse_extension_json,
    parse_har_file,
)
from matchbot.log_config import configure_logging
from matchbot.settings import get_settings

logger = logging.getLogger("matchbot.backfill_facebook")
app = typer.Typer()
_FORMAT_SNIFF_BYTES = 64 * 1024
_GROUPS_PATH_RE = re.compile(r"facebook\.com/groups/([^/?#]+)", re.IGNORECASE)
_EXTENSION_FILENAME_RE = re.compile(
    r"^(?P<slug>.+)_fb_posts_\d{4}-\d{2}-\d{2}T.*$",
    re.IGNORECASE,
)
_TITLE_MEMBER_COUNT_RE = re.compile(r"^\(\d+\+\)\s*")
_REPO_ROOT = Path(__file__).resolve().parent.parent
_FACEBOOK_RAW_DIR = _REPO_ROOT / "data" / "raw" / "facebook"


def _detect_format(path: Path) -> str:
    """Detect if the file is a HAR or extension-style JSON."""
    try:
        with open(path, "rb") as f:
            header = f.read(_FORMAT_SNIFF_BYTES).lstrip()
            if header.startswith(b"["):
                return "extension"
            if header.startswith(b"{") and b'"log"' in header and b'"entries"' in header:
                return "har"
    except OSError:
        pass
    return "unknown"


def _extract_group_token_from_url(url: str) -> str | None:
    match = _GROUPS_PATH_RE.search(url)
    if not match:
        return None
    token = match.group(1).strip()
    return token or None


def _titleize_group_slug(slug: str) -> str:
    words = re.split(r"[-_.]+", slug.strip())
    return " ".join(word.capitalize() for word in words if word)


def _clean_group_title(title: str) -> str:
    cleaned = re.sub(r"\s*[-|]\s*Facebook\s*$", "", title, flags=re.IGNORECASE).strip()
    cleaned = _TITLE_MEMBER_COUNT_RE.sub("", cleaned).strip()
    return cleaned


def _infer_group_name_from_filename(path: Path) -> str | None:
    match = _EXTENSION_FILENAME_RE.match(path.stem)
    if not match:
        return None
    slug = match.group("slug").strip("-_ ")
    if not slug:
        return None
    return _titleize_group_slug(slug)


def _extract_group_name_from_payload_obj(
    obj: object, *, group_id: str | None = None, depth: int = 0
) -> str | None:
    if depth > 20:
        return None

    if isinstance(obj, dict):
        name = obj.get("name")
        obj_group_id = str(obj.get("id") or "").strip() or None
        url = str(obj.get("url") or "").strip()
        typename = str(obj.get("__typename") or "").strip()
        is_groupish = typename == "Group" or obj.get("__isEntity") == "Group" or "/groups/" in url

        if isinstance(name, str):
            cleaned_name = name.strip()
            if cleaned_name and is_groupish:
                if group_id is None or obj_group_id == group_id or f"/groups/{group_id}" in url:
                    return cleaned_name

        for value in obj.values():
            found = _extract_group_name_from_payload_obj(value, group_id=group_id, depth=depth + 1)
            if found:
                return found

    elif isinstance(obj, list):
        for item in obj:
            found = _extract_group_name_from_payload_obj(item, group_id=group_id, depth=depth + 1)
            if found:
                return found

    return None


def _extract_group_candidates_from_payload_obj(
    obj: object, *, depth: int = 0
) -> list[tuple[str | None, str | None]]:
    if depth > 20:
        return []

    candidates: list[tuple[str | None, str | None]] = []
    if isinstance(obj, dict):
        obj_group_id = str(obj.get("id") or "").strip() or None
        name = obj.get("name")
        cleaned_name = name.strip() if isinstance(name, str) and name.strip() else None
        url = str(obj.get("url") or "").strip()
        typename = str(obj.get("__typename") or "").strip()
        is_groupish = typename == "Group" or obj.get("__isEntity") == "Group" or "/groups/" in url

        if is_groupish and (obj_group_id or cleaned_name):
            candidates.append((cleaned_name, obj_group_id))

        for value in obj.values():
            candidates.extend(_extract_group_candidates_from_payload_obj(value, depth=depth + 1))
    elif isinstance(obj, list):
        for item in obj:
            candidates.extend(_extract_group_candidates_from_payload_obj(item, depth=depth + 1))

    return candidates


def _select_group_candidate(
    candidates: list[tuple[str | None, str | None]],
    *,
    preferred_name: str | None = None,
) -> tuple[str | None, str | None]:
    if not candidates:
        return None, None

    if preferred_name:
        preferred_key = preferred_name.casefold()
        for candidate_name, candidate_id in candidates:
            if candidate_name and candidate_name.casefold() == preferred_key:
                return candidate_name, candidate_id

    unique_candidates = {
        (candidate_name, candidate_id) for candidate_name, candidate_id in candidates
    }
    if len(unique_candidates) == 1:
        return next(iter(unique_candidates))

    unique_ids = {candidate_id for _, candidate_id in candidates if candidate_id}
    if len(unique_ids) == 1:
        matched_id = next(iter(unique_ids))
        for candidate_name, candidate_id in candidates:
            if candidate_id == matched_id:
                return candidate_name, candidate_id

    return None, None


def _infer_group_name_from_extension_json(path: Path, *, group_id: str | None = None) -> str | None:
    try:
        with open(path, "rb") as f:
            responses = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(responses, list):
        return None

    for item in responses:
        if not isinstance(item, dict):
            continue
        page_title = str(item.get("pageTitle") or "").strip()
        if not page_title:
            text = item.get("text")
            if not isinstance(text, str):
                continue
            for line in text.splitlines():
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                found = _extract_group_name_from_payload_obj(payload, group_id=group_id)
                if found:
                    return found
            continue
        cleaned = _clean_group_title(page_title)
        if cleaned:
            return cleaned

    return None


def _infer_group_candidate_from_extension_json(
    path: Path, *, preferred_name: str | None = None
) -> tuple[str | None, str | None]:
    try:
        with open(path, "rb") as f:
            responses = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None, None

    if not isinstance(responses, list):
        return None, None

    candidates: list[tuple[str | None, str | None]] = []
    for item in responses:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str):
            continue
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            candidates.extend(_extract_group_candidates_from_payload_obj(payload))

    return _select_group_candidate(candidates, preferred_name=preferred_name)


def _infer_group_name_from_har(path: Path, *, group_id: str | None = None) -> str | None:
    try:
        with open(path, "rb") as f:
            har_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    pages = har_data.get("log", {}).get("pages", [])
    for page in pages:
        title = str(page.get("title") or "").strip()
        if not title:
            continue
        cleaned = _clean_group_title(title)
        if cleaned:
            return cleaned

    entries = har_data.get("log", {}).get("entries", [])
    for entry in entries:
        text = entry.get("response", {}).get("content", {}).get("text")
        if not isinstance(text, str):
            continue
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            found = _extract_group_name_from_payload_obj(payload, group_id=group_id)
            if found:
                return found
    return None


def _infer_group_candidate_from_har(
    path: Path, *, preferred_name: str | None = None
) -> tuple[str | None, str | None]:
    try:
        with open(path, "rb") as f:
            har_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None, None

    candidates: list[tuple[str | None, str | None]] = []
    entries = har_data.get("log", {}).get("entries", [])
    for entry in entries:
        text = entry.get("response", {}).get("content", {}).get("text")
        if not isinstance(text, str):
            continue
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            candidates.extend(_extract_group_candidates_from_payload_obj(payload))

    return _select_group_candidate(candidates, preferred_name=preferred_name)


def _stage_input_file(path: Path, staging_dir: Path = _FACEBOOK_RAW_DIR) -> Path:
    """Copy external capture files into the repo-local Facebook raw data directory."""
    resolved_path = path.expanduser().resolve()
    resolved_staging_dir = staging_dir.resolve()

    if resolved_path.parent == resolved_staging_dir:
        return resolved_path

    resolved_staging_dir.mkdir(parents=True, exist_ok=True)

    destination = resolved_staging_dir / resolved_path.name
    if destination.exists() and destination.resolve() != resolved_path:
        suffix = 2
        while True:
            candidate = destination.with_name(
                f"{destination.stem}-{suffix}{destination.suffix}"
            )
            if not candidate.exists():
                destination = candidate
                break
            suffix += 1

    shutil.copy2(resolved_path, destination)
    logger.info("Copied %s to repo data dir: %s", resolved_path, destination)
    return destination


def _infer_group_metadata(
    files: list[Path],
    file_formats: dict[Path, str],
    posts: list[dict],
) -> tuple[str | None, str | None]:
    inferred_name: str | None = None
    group_tokens = {
        token
        for post in posts
        if (token := _extract_group_token_from_url(str(post.get("source_url") or "")))
    }

    if len(group_tokens) == 1:
        token = next(iter(group_tokens))
        if token.isdigit():
            inferred_group_id = token
        else:
            inferred_group_id = None
            inferred_name = _titleize_group_slug(token)
    else:
        inferred_group_id = None

    for path in files:
        if file_formats.get(path) == "extension":
            if not inferred_name:
                inferred_name = _infer_group_name_from_extension_json(
                    path, group_id=inferred_group_id
                )
            candidate_name, candidate_id = _infer_group_candidate_from_extension_json(
                path, preferred_name=inferred_name
            )
            if not inferred_name:
                inferred_name = candidate_name or _infer_group_name_from_filename(path)
            if not inferred_group_id:
                inferred_group_id = candidate_id
        elif file_formats.get(path) == "har":
            if not inferred_name:
                inferred_name = _infer_group_name_from_har(path, group_id=inferred_group_id)
            candidate_name, candidate_id = _infer_group_candidate_from_har(
                path, preferred_name=inferred_name
            )
            if not inferred_name:
                inferred_name = candidate_name
            if not inferred_group_id:
                inferred_group_id = candidate_id

    if not inferred_name and inferred_group_id:
        inferred_name = f"Facebook Group {inferred_group_id}"

    return inferred_name, inferred_group_id

def _build_group_batches(
    parsed_files: list[dict[str, Any]],
    *,
    group_name_override: str | None,
    group_id_override: str | None,
) -> list[dict[str, Any]]:
    grouped_posts: dict[tuple[str, str], dict[str, Any]] = {}
    seen_post_ids: set[str] = set()

    for parsed_file in parsed_files:
        path = parsed_file["path"]
        fmt = parsed_file["format"]
        posts = parsed_file["posts"]
        file_group_name, file_group_id = _infer_group_metadata([path], {path: fmt}, posts)

        token_groups: dict[str | None, list[dict]] = defaultdict(list)
        for post in posts:
            token = _extract_group_token_from_url(str(post.get("source_url") or ""))
            token_groups[token].append(post)

        for token, token_posts in token_groups.items():
            if token and token.isdigit():
                inferred_group_id = token
                inferred_group_name = (
                    file_group_name if file_group_id == token and file_group_name else None
                )
                if not inferred_group_name:
                    inferred_group_name = f"Facebook Group {token}"
            elif token:
                inferred_group_id = file_group_id
                inferred_group_name = file_group_name or _titleize_group_slug(token)
            else:
                inferred_group_id = file_group_id
                inferred_group_name = file_group_name

            resolved_group_id = group_id_override or inferred_group_id
            resolved_group_name = group_name_override or inferred_group_name
            if not resolved_group_name:
                raise typer.BadParameter(
                    "Could not infer Facebook group name for "
                    f"{path}. Pass --group-name to override."
                )

            batch_key = (
                resolved_group_id or f"name:{resolved_group_name.casefold()}",
                resolved_group_name,
            )
            batch = grouped_posts.setdefault(
                batch_key,
                {
                    "group_name": resolved_group_name,
                    "group_id": resolved_group_id,
                    "posts": [],
                },
            )

            for post in token_posts:
                post_id = str(post["platform_post_id"])
                if post_id in seen_post_ids:
                    continue
                seen_post_ids.add(post_id)
                batch["posts"].append(post)

    return [batch for batch in grouped_posts.values() if batch["posts"]]


@app.command()
def main(
    files: list[Path] = typer.Argument(..., help="Path to HAR or Extension JSON file(s)"),
    group_name: str | None = typer.Option(
        None,
        "--group-name",
        help="Name of the Facebook group (optional override; inferred when possible)",
    ),
    group_id: str | None = typer.Option(
        None, "--group-id", help="Numeric Facebook Group ID (optional override)"
    ),
    since_date: str | None = typer.Option(
        None, "--since-date", help="UTC date cutoff (YYYY-MM-DD)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Parse and dedup only, without DB writes."
    ),
    no_extract: bool = typer.Option(
        False, "--no-extract", help="Skip LLM extraction, save as RAW."
    ),
    sleep_seconds: float = typer.Option(0.5, "--sleep-seconds", help="Pause between LLM calls."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging."),
) -> None:
    """Backfill Facebook posts from intercepted network traffic files."""
    settings = get_settings()
    configure_logging(verbose=verbose or settings.verbose)

    asyncio.run(
        _main_async(
            files=files,
            group_name=group_name,
            group_id=group_id,
            since_date=since_date,
            dry_run=dry_run,
            no_extract=no_extract,
            sleep_seconds=sleep_seconds,
        )
    )


async def _main_async(
    *,
    files: list[Path],
    group_name: str | None,
    group_id: str | None,
    since_date: str | None,
    dry_run: bool,
    no_extract: bool,
    sleep_seconds: float,
) -> None:
    since_datetime = None
    if since_date:
        try:
            parsed_since_date = datetime.strptime(since_date, "%Y-%m-%d").date()
            since_datetime = datetime.combine(
                parsed_since_date, time.min, tzinfo=UTC
            ).replace(tzinfo=None)
        except ValueError as exc:
            raise typer.BadParameter("--since-date must be in YYYY-MM-DD format") from exc

    await create_db_and_tables()

    parsed_files: list[dict[str, Any]] = []
    for original_path in files:
        path = original_path.expanduser()
        if not path.exists():
            logger.error("File not found: %s", path)
            continue

        path = _stage_input_file(path)

        fmt = _detect_format(path)
        logger.info("Processing %s (detected format: %s)", path, fmt)

        if fmt == "har":
            posts = parse_har_file(path)
        elif fmt == "extension":
            posts = parse_extension_json(path)
        else:
            logger.error("Could not detect format for %s", path)
            continue

        logger.info("Found %d post-like nodes in %s", len(posts), path)
        parsed_files.append({"path": path, "format": fmt, "posts": posts})

    group_batches = _build_group_batches(
        parsed_files,
        group_name_override=group_name,
        group_id_override=group_id,
    )
    total_unique_posts = sum(len(batch["posts"]) for batch in group_batches)
    logger.info("Total unique posts found across all files: %d", total_unique_posts)

    if total_unique_posts == 0:
        logger.info("No posts to process.")
        await dispose_engine()
        return

    counts = new_backfill_counts()
    counts["parsed"] = 0
    try:
        for batch in group_batches:
            logger.info(
                "Processing batch: group_name=%s group_id=%s posts=%d",
                batch["group_name"],
                batch["group_id"] or "<unknown>",
                len(batch["posts"]),
            )
            batch_counts = await backfill_facebook_posts(
                batch["posts"],
                group_name=batch["group_name"],
                group_id=batch["group_id"],
                since_datetime=since_datetime,
                dry_run=dry_run,
                sleep_seconds=sleep_seconds,
                no_extract=no_extract,
            )
            accumulate_counts(counts, batch_counts)
    finally:
        await dispose_engine()

    logger.info(
        (
            "Facebook backfill complete: parsed=%d new_candidates=%d matched=%d "
            "skipped=%d deduped=%d before_cutoff=%d extracted=%d raw_after_error=%d dry_run=%s"
        ),
        counts["parsed"],
        counts["new_candidates"],
        counts["matched"],
        counts["skipped"],
        counts["deduped"],
        counts["before_cutoff"],
        counts["extracted"],
        counts["raw_after_error"],
        dry_run,
    )


if __name__ == "__main__":
    app()

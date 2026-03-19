# tests/test_cli_data.py
import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from matchbot.cli.app import app

runner = CliRunner()


@pytest.fixture
def raw_dir(tmp_path):
    """Populate a temp data/raw dir with one Reddit post."""
    post = {
        "id": "abc123",
        "title": "Looking for camp",
        "selftext": "I want to join a theme camp for BM 2026.",
        "author": "testuser",
        "author_fullname": "t2_xyz",
        "permalink": "/r/BurningMan/comments/abc123/",
        "created_utc": 1700000000,
    }
    post_dir = tmp_path / "reddit" / "2026-03-15"
    post_dir.mkdir(parents=True)
    (post_dir / "abc123.json").write_text(json.dumps(post))
    return tmp_path


def test_data_replay_help():
    result = runner.invoke(app, ["data", "replay", "--help"])
    assert result.exit_code == 0
    assert "--platform" in result.output


def test_data_replay_dry_run(raw_dir, monkeypatch):
    """Dry-run should list posts that would be processed without touching the DB."""
    monkeypatch.setenv("RAW_DATA_DIR", str(raw_dir))

    with patch("matchbot.cli.cmd_data._post_exists_batch", return_value={"abc123": False}):
        result = runner.invoke(app, ["data", "replay", "--platform", "reddit", "--dry-run"])

    assert result.exit_code == 0
    assert "abc123" in result.output
    assert "would process" in result.output.lower() or "dry" in result.output.lower()


def test_data_replay_skips_existing_db_post(raw_dir, monkeypatch):
    """Posts already in DB should be skipped, not re-processed."""
    monkeypatch.setenv("RAW_DATA_DIR", str(raw_dir))

    with patch("matchbot.cli.cmd_data._post_exists_batch", return_value={"abc123": True}):
        result = runner.invoke(app, ["data", "replay", "--platform", "reddit"])

    assert result.exit_code == 0
    assert "skipped" in result.output.lower()


def test_data_replay_unknown_platform(raw_dir, monkeypatch):
    monkeypatch.setenv("RAW_DATA_DIR", str(raw_dir))
    result = runner.invoke(app, ["data", "replay", "--platform", "twitter"])
    assert result.exit_code != 0

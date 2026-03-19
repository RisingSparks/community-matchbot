# tests/test_raw_store.py
import json
import pytest
from pathlib import Path
from matchbot.storage.raw_store import RawStore


@pytest.fixture
def store(tmp_path):
    return RawStore(base_dir=tmp_path)


def test_save_creates_file(store, tmp_path):
    store.save("reddit", "2026-03-15", "abc123", {"title": "Test post", "selftext": "Hello world"})
    expected = tmp_path / "reddit" / "2026-03-15" / "abc123.json"
    assert expected.exists()
    data = json.loads(expected.read_text())
    assert data["title"] == "Test post"


def test_save_is_idempotent(store, tmp_path):
    store.save("reddit", "2026-03-15", "abc123", {"title": "First"})
    store.save("reddit", "2026-03-15", "abc123", {"title": "Second"})
    # Second save should NOT overwrite
    data = json.loads((tmp_path / "reddit" / "2026-03-15" / "abc123.json").read_text())
    assert data["title"] == "First"


def test_exists_true(store):
    store.save("reddit", "2026-03-15", "abc123", {})
    assert store.exists("reddit", "abc123") is True


def test_exists_false(store):
    assert store.exists("reddit", "missing_id") is False


def test_load_returns_payload(store):
    store.save("reddit", "2026-03-15", "abc123", {"key": "value"})
    result = store.load("reddit", "abc123")
    assert result == {"key": "value"}


def test_load_returns_none_when_missing(store):
    assert store.load("reddit", "missing_id") is None


def test_list_ids_empty(store):
    assert store.list_ids("reddit") == []


def test_list_ids_returns_saved_ids(store):
    store.save("reddit", "2026-03-15", "aaa", {})
    store.save("reddit", "2026-03-15", "bbb", {})
    store.save("discord", "2026-03-15", "ccc", {})
    ids = store.list_ids("reddit")
    assert set(ids) == {"aaa", "bbb"}


def test_list_ids_filtered_by_date(store):
    store.save("reddit", "2026-03-14", "old", {})
    store.save("reddit", "2026-03-15", "new", {})
    ids = store.list_ids("reddit", date="2026-03-15")
    assert ids == ["new"]


def test_list_ids_sorted(store):
    store.save("reddit", "2026-03-15", "zzz", {})
    store.save("reddit", "2026-03-15", "aaa", {})
    ids = store.list_ids("reddit")
    assert ids == ["aaa", "zzz"]

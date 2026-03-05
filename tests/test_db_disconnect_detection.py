from __future__ import annotations

from sqlalchemy.exc import DBAPIError

from matchbot.db.engine import is_disconnect_error


def test_is_disconnect_error_detects_connection_invalidated_dbapi_error() -> None:
    err = DBAPIError(
        statement="SELECT 1",
        params={},
        orig=Exception("boom"),
        connection_invalidated=True,
    )
    assert is_disconnect_error(err) is True


def test_is_disconnect_error_detects_asyncpg_connection_closed_message() -> None:
    msg = "ConnectionDoesNotExistError: connection was closed in the middle of operation"
    err = DBAPIError(
        statement="SELECT 1",
        params={},
        orig=Exception(msg),
    )
    assert is_disconnect_error(err) is True


def test_is_disconnect_error_ignores_non_disconnect_errors() -> None:
    err = DBAPIError(
        statement="SELECT 1",
        params={},
        orig=Exception("unique constraint violated"),
    )
    assert is_disconnect_error(err) is False

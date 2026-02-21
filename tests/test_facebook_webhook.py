"""Tests for Facebook webhook endpoints."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from matchbot.server import create_app


@pytest.fixture
def client():
    """FastAPI TestClient with a fresh app instance."""
    return TestClient(create_app())


@pytest.fixture
def verify_token() -> str:
    return "test_verify_token_123"


@pytest.fixture
def app_secret() -> str:
    return "test_app_secret_abc"


def _make_signature(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


# ---------------------------------------------------------------------------
# GET /webhook/facebook — verification handshake
# ---------------------------------------------------------------------------


def test_facebook_verify_success(client, verify_token):
    with patch("matchbot.listeners.facebook.get_settings") as mock_settings:
        mock_settings.return_value.facebook_verify_token = verify_token
        mock_settings.return_value.facebook_app_secret = ""

        resp = client.get(
            "/webhook/facebook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": verify_token,
                "hub.challenge": "challenge_string_abc",
            },
        )

    assert resp.status_code == 200
    assert resp.text == "challenge_string_abc"


def test_facebook_verify_wrong_token(client):
    with patch("matchbot.listeners.facebook.get_settings") as mock_settings:
        mock_settings.return_value.facebook_verify_token = "correct_token"
        mock_settings.return_value.facebook_app_secret = ""

        resp = client.get(
            "/webhook/facebook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong_token",
                "hub.challenge": "challenge_abc",
            },
        )

    assert resp.status_code == 403


def test_facebook_verify_wrong_mode(client, verify_token):
    with patch("matchbot.listeners.facebook.get_settings") as mock_settings:
        mock_settings.return_value.facebook_verify_token = verify_token
        mock_settings.return_value.facebook_app_secret = ""

        resp = client.get(
            "/webhook/facebook",
            params={
                "hub.mode": "unsubscribe",
                "hub.verify_token": verify_token,
                "hub.challenge": "challenge_abc",
            },
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /webhook/facebook — event handling
# ---------------------------------------------------------------------------


def _feed_payload(message: str = "Seeking camp for Burning Man") -> dict:
    return {
        "object": "group",
        "entry": [
            {
                "changes": [
                    {
                        "field": "feed",
                        "value": {
                            "message": message,
                            "from": {"id": "user_fb_123", "name": "Test User"},
                            "post_id": "123456789_987654321",
                            "permalink_url": "https://facebook.com/groups/test/posts/1",
                            "group_id": "FB_GROUP_ID_1",
                        },
                    }
                ]
            }
        ],
    }


def test_facebook_post_valid_signature(client, app_secret):
    payload = _feed_payload()
    body = json.dumps(payload).encode()
    signature = _make_signature(body, app_secret)

    with (
        patch("matchbot.listeners.facebook.get_settings") as mock_settings,
        patch("matchbot.listeners.facebook._handle_feed_change", new_callable=AsyncMock) as mock_handle,
    ):
        mock_settings.return_value.facebook_verify_token = "token"
        mock_settings.return_value.facebook_app_secret = app_secret

        resp = client.post(
            "/webhook/facebook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature,
            },
        )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    mock_handle.assert_called_once()


def test_facebook_post_invalid_signature(client, app_secret):
    payload = _feed_payload()
    body = json.dumps(payload).encode()

    with patch("matchbot.listeners.facebook.get_settings") as mock_settings:
        mock_settings.return_value.facebook_verify_token = "token"
        mock_settings.return_value.facebook_app_secret = app_secret

        resp = client.post(
            "/webhook/facebook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=invalidsignature",
            },
        )

    assert resp.status_code == 403


def test_facebook_post_no_secret_skips_verification(client):
    """If no app_secret configured, HMAC check is skipped (dev mode)."""
    payload = _feed_payload()
    body = json.dumps(payload).encode()

    with (
        patch("matchbot.listeners.facebook.get_settings") as mock_settings,
        patch("matchbot.listeners.facebook._handle_feed_change", new_callable=AsyncMock),
    ):
        mock_settings.return_value.facebook_verify_token = "token"
        mock_settings.return_value.facebook_app_secret = ""  # no secret

        resp = client.post(
            "/webhook/facebook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=anything",
            },
        )

    assert resp.status_code == 200


def test_facebook_post_non_feed_change_ignored(client, app_secret):
    payload = {
        "object": "group",
        "entry": [{"changes": [{"field": "reactions", "value": {}}]}],
    }
    body = json.dumps(payload).encode()
    signature = _make_signature(body, app_secret)

    with (
        patch("matchbot.listeners.facebook.get_settings") as mock_settings,
        patch("matchbot.listeners.facebook._handle_feed_change", new_callable=AsyncMock) as mock_handle,
    ):
        mock_settings.return_value.facebook_verify_token = "token"
        mock_settings.return_value.facebook_app_secret = app_secret

        resp = client.post(
            "/webhook/facebook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature,
            },
        )

    assert resp.status_code == 200
    mock_handle.assert_not_called()


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

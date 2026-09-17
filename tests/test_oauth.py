"""Tests for the OAuth engine (PKCE + AWS SSO OIDC device flow)."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services import oauth
from app.services.oauth import (
    ANTIGRAVITY_SPEC,
    KIRO_SPEC,
    SPECS,
    PendingError,
    complete_device_flow,
    complete_pkce_flow,
    get_valid_access_token,
    start_device_flow,
    start_pkce_flow,
)
from app.services.oauth_store import oauth_store


class TestSpecs:
    def test_both_providers_registered(self):
        assert set(SPECS) == {"kiro", "antigravity"}

    def test_antigravity_is_pkce(self):
        assert ANTIGRAVITY_SPEC.flow == "pkce"
        assert ANTIGRAVITY_SPEC.authorize_url.startswith("https://accounts.google.com")

    def test_kiro_is_device_code(self):
        assert KIRO_SPEC.flow == "device_code"
        assert "oidc.us-east-1.amazonaws.com" in KIRO_SPEC.authorize_url


class TestPkceFlow:
    @pytest.mark.asyncio
    async def test_start_returns_auth_url_with_challenge(self):
        result = await start_pkce_flow(ANTIGRAVITY_SPEC)
        assert result["flow"] == "pkce"
        assert result["state"]
        assert "code_challenge_method=S256" in result["authUrl"]
        assert "access_type=offline" in result["authUrl"]
        assert ANTIGRAVITY_SPEC.client_id in result["authUrl"]

    @pytest.mark.asyncio
    async def test_complete_exchanges_and_stores(self, monkeypatch):
        oauth._pending.clear()
        start = await start_pkce_flow(ANTIGRAVITY_SPEC)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "ya29.test",
            "refresh_token": "refresh-123",
            "expires_in": 3600,
            "scope": "openid email",
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.services.oauth.httpx.AsyncClient", return_value=mock_http),
            patch.object(oauth_store, "save", new=AsyncMock()) as save_mock,
            patch.object(oauth, "_bootstrap_antigravity_project", new=AsyncMock()),
        ):
            out = await complete_pkce_flow(start["state"], "test-code")

        assert out["connected"] is True
        saved = save_mock.await_args.args[1]
        assert saved["access_token"] == "ya29.test"
        assert saved["refresh_token"] == "refresh-123"

    @pytest.mark.asyncio
    async def test_complete_rejects_unknown_state(self):
        oauth._pending.clear()
        with pytest.raises(ValueError, match="state"):
            await complete_pkce_flow("nonexistent", "code")


class TestDeviceFlow:
    @pytest.mark.asyncio
    async def test_start_returns_verification_uri(self):
        reg = MagicMock()
        reg.status_code = 200
        reg.json.return_value = {"clientId": "cid", "clientSecret": "csec"}

        dev = MagicMock()
        dev.status_code = 200
        dev.json.return_value = {
            "deviceCode": "dc-123",
            "userCode": "ABCD-EFGH",
            "verificationUri": "https://device.sso.us-east-1.amazonaws.com/",
            "verificationUriComplete": "https://device.sso.us-east-1.amazonaws.com/?user_code=ABCD-EFGH",
            "expiresIn": 600,
            "interval": 5,
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=[reg, dev])
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        oauth._pending.clear()
        with patch("app.services.oauth.httpx.AsyncClient", return_value=mock_http):
            out = await start_device_flow(KIRO_SPEC)

        assert out["flow"] == "device_code"
        assert out["userCode"] == "ABCD-EFGH"
        assert out["verificationUri"].startswith("https://")
        assert out["state"] in oauth._pending

    @pytest.mark.asyncio
    async def test_poll_pending_raises_PendingError(self):
        oauth._pending.clear()
        from app.services.oauth import PendingFlow
        sf = PendingFlow(
            provider="kiro",
            state="poll-test",
            verifier="cid:csec",
            device_code="dc",
        )
        oauth._pending["poll-test"] = sf

        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"error": "authorization_pending"}

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.oauth.httpx.AsyncClient", return_value=mock_http), \
             pytest.raises(PendingError) as exc_info:
            await complete_device_flow("poll-test")
        assert exc_info.value.code == "authorization_pending"

    @pytest.mark.asyncio
    async def test_poll_granted_persists_tokens(self):
        oauth._pending.clear()
        from app.services.oauth import PendingFlow
        sf = PendingFlow(
            provider="kiro",
            state="grant-test",
            verifier="cid:csec",
            device_code="dc",
        )
        oauth._pending["grant-test"] = sf

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "accessToken": "abcd",
            "refreshToken": "rt",
            "expiresIn": 3600,
        }
        mock_resp.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        captured = {}

        async def fake_persist(provider, data):
            captured["provider"] = provider
            captured["data"] = data
            return data

        with (
            patch("app.services.oauth.httpx.AsyncClient", return_value=mock_http),
            patch.object(oauth, "_persist_tokens", new=fake_persist),
        ):
            await complete_device_flow("grant-test")

        # AWS OIDC returns camelCase — must be normalized before persisting
        assert captured["provider"] == "kiro"
        assert captured["data"]["access_token"] == "abcd"
        assert captured["data"]["refresh_token"] == "rt"
        assert "grant-test" not in oauth._pending


class TestTokenRefresh:
    @pytest.mark.asyncio
    async def test_get_valid_access_token_refreshes_when_expired(self):
        expired = {
            "access_token": "old",
            "refresh_token": "rt",
            "expires_at": time.time() - 100,
        }
        with (
            patch.object(oauth_store, "get", new=AsyncMock(return_value=expired)),
            patch.object(oauth_store, "is_expired", new=AsyncMock(return_value=True)),
            patch.object(oauth, "refresh_token_flow", new=AsyncMock(return_value={"access_token": "new", "refresh_token": "rt", "expires_at": time.time() + 3600})),
        ):
            token = await get_valid_access_token("kiro")
            assert token == "new"

    @pytest.mark.asyncio
    async def test_get_valid_access_token_needs_connection(self):
        with (
            patch.object(oauth_store, "get", new=AsyncMock(return_value=None)),
            pytest.raises(ValueError, match="not connected"),
        ):
            await get_valid_access_token("kiro")

"""
Security tests: auth middleware, body size limit, and path traversal protection.
"""

import pytest
from app.config import get_settings
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def authed_client(monkeypatch):
    """Client with a valid gateway key configured."""
    monkeypatch.setenv("GATEWAY_API_KEY", "test-gateway-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestAuthMiddleware:
    """Auth middleware must reject invalid keys and never accept provider keys."""

    @pytest.mark.asyncio
    async def test_no_auth_header_rejected(self, authed_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/keys/status")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_key_rejected(self, authed_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/keys/status",
                headers={"Authorization": "Bearer wrong-key"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_provider_key_not_accepted(self, authed_client):
        """Provider (nvidia/openai) keys must NOT authenticate against the gateway."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/keys/status",
                headers={"Authorization": "Bearer test-nvidia-key"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_gateway_key_accepted(self, authed_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/keys/status",
                headers={"Authorization": "Bearer test-gateway-key"},
            )
        assert resp.status_code in (200, 500)  # may fail w/o redis, but not 401

    @pytest.mark.asyncio
    async def test_public_paths_open(self, authed_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code != 401


class TestBodySizeLimit:
    @pytest.mark.asyncio
    async def test_oversized_body_rejected(self, authed_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/chat",
                headers={
                    "Authorization": "Bearer test-gateway-key",
                    "Content-Length": str(20 * 1024 * 1024),  # 20 MB > 10 MB default
                },
                content=b"{}",
            )
        assert resp.status_code == 413

    @pytest.mark.asyncio
    async def test_normal_body_allowed(self, authed_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/chat",
                headers={
                    "Authorization": "Bearer test-gateway-key",
                    "Content-Type": "application/json",
                },
                json={"message": "hello"},
            )
        # may fail downstream w/o providers but must pass the size gate
        assert resp.status_code != 413


class TestPathTraversal:
    """The /api/projects/index endpoint must reject paths outside allowed roots."""

    @pytest.mark.asyncio
    async def test_indexing_disabled_without_roots(self, authed_client, monkeypatch):
        monkeypatch.setenv("ALLOWED_INDEX_ROOTS", "[]")
        get_settings.cache_clear()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/projects/index",
                headers={"Authorization": "Bearer test-gateway-key"},
                json={"path": "C:\\"},
            )
        assert resp.status_code == 403
        get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_path_outside_roots_rejected(self, authed_client, monkeypatch, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        forbidden = tmp_path / "forbidden"
        forbidden.mkdir()
        monkeypatch.setenv("ALLOWED_INDEX_ROOTS", str(allowed))
        get_settings.cache_clear()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/projects/index",
                headers={"Authorization": "Bearer test-gateway-key"},
                json={"path": str(forbidden)},
            )
        assert resp.status_code == 403
        get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_path_inside_roots_accepted(self, authed_client, monkeypatch, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        inner = allowed / "project"
        inner.mkdir()
        monkeypatch.setenv("ALLOWED_INDEX_ROOTS", str(allowed))
        get_settings.cache_clear()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/projects/index",
                headers={"Authorization": "Bearer test-gateway-key"},
                json={"path": str(inner)},
            )
        assert resp.status_code == 200
        get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_traversal_sequence_rejected(self, authed_client, monkeypatch, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        monkeypatch.setenv("ALLOWED_INDEX_ROOTS", str(allowed))
        get_settings.cache_clear()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/projects/index",
                headers={"Authorization": "Bearer test-gateway-key"},
                json={"path": str(allowed / ".." / ".." / "etc")},
            )
        assert resp.status_code == 403
        get_settings.cache_clear()

"""Tests for API endpoints."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
class TestHealthEndpoint:
    """Test the health check endpoint."""

    async def test_health_check(self, client):
        """Should return health status."""
        with (
            patch("app.main.redis_health_check", new_callable=AsyncMock, return_value={"status": "healthy", "latency_ms": 1.0}),
            patch("app.main.qdrant_health_check", return_value={"status": "healthy", "latency_ms": 2.0}),
        ):
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] in ("healthy", "degraded")
            assert "services" in data


@pytest.mark.asyncio
class TestChatEndpoints:
    """Test chat API endpoints."""

    async def test_gateway_chat(self, client, sample_llm_response):
        """Test POST /api/chat endpoint."""
        with (
            patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
            patch("app.api.chat.build_context", new_callable=AsyncMock, return_value=[{"role": "user", "content": "test"}]),
            patch("app.api.chat.rate_limiter") as mock_limiter,
            patch("app.api.chat.get_provider") as mock_get_provider,
            patch("app.api.chat.set_cached_response", new_callable=AsyncMock),
        ):
            mock_limiter.wait_if_needed = AsyncMock(return_value={"allowed": True, "waited_seconds": 0})
            mock_provider = AsyncMock()
            mock_provider.name = "nvidia"
            mock_provider.default_model = "test-model"
            mock_provider.chat = AsyncMock(return_value=sample_llm_response)
            mock_get_provider.return_value = mock_provider

            response = await client.post(
                "/api/chat",
                json={"message": "Hello", "project": "test"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "response" in data
            assert data["provider"] == "nvidia"

    async def test_openai_chat_completions(self, client, sample_llm_response):
        """Test POST /v1/chat/completions endpoint."""
        with (
            patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
            patch("app.api.chat.build_context", new_callable=AsyncMock, return_value=[{"role": "user", "content": "test"}]),
            patch("app.api.chat.rate_limiter") as mock_limiter,
            patch("app.api.chat.get_provider") as mock_get_provider,
            patch("app.api.chat.set_cached_response", new_callable=AsyncMock),
        ):
            mock_limiter.wait_if_needed = AsyncMock(return_value={"allowed": True, "waited_seconds": 0})
            mock_provider = AsyncMock()
            mock_provider.name = "nvidia"
            mock_provider.default_model = "test-model"
            mock_provider.chat = AsyncMock(return_value=sample_llm_response)
            mock_get_provider.return_value = mock_provider

            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["object"] == "chat.completion"
            assert len(data["choices"]) > 0
            assert data["choices"][0]["message"]["role"] == "assistant"

    async def test_cached_response(self, client):
        """Test that cached responses are returned correctly."""
        cached = {
            "content": "cached answer",
            "model": "test-model",
            "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
        }

        with (
            patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=cached),
            patch("app.api.chat.get_provider") as mock_get_provider,
        ):
            mock_provider = MagicMock()
            mock_provider.name = "nvidia"
            mock_provider.default_model = "test-model"
            mock_get_provider.return_value = mock_provider

            response = await client.post(
                "/api/chat",
                json={"message": "Hello", "project": "test"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["cached"] is True
            assert data["response"] == "cached answer"

    async def test_list_models(self, client):
        """Test GET /v1/models endpoint."""
        with patch("app.api.chat.list_providers", return_value=["nvidia"]):
            mock_provider = MagicMock()
            mock_provider.default_model = "test-model"
            with patch("app.api.chat.get_provider", return_value=mock_provider):
                response = await client.get("/v1/models")
                assert response.status_code == 200
                data = response.json()
                assert data["object"] == "list"
                assert len(data["data"]) > 0


@pytest.mark.asyncio
class TestAuthMiddleware:
    """Test API key authentication."""

    async def test_public_health_no_auth(self):
        """Health endpoint should not require auth."""
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with (
                patch("app.main.redis_health_check", new_callable=AsyncMock, return_value={"status": "healthy"}),
                patch("app.main.qdrant_health_check", return_value={"status": "healthy"}),
            ):
                response = await client.get("/health")
                assert response.status_code == 200

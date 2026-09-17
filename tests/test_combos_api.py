"""End-to-end tests for combo CRUD + combo routing via /api/chat."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.combos import Combo, ComboTarget, combo_store


@pytest.fixture(autouse=True)
async def reset_combos(_clean=combo_store._local.clear):
    combo_store._local.clear()
    yield
    combo_store._local.clear()


@pytest.mark.asyncio
class TestComboAPI:
    async def test_crud_cycle(self, client):
        # Create
        resp = await client.post("/api/combos", json={
            "name": "fast",
            "targets": [{"provider": "nvidia"}, {"provider": "deepseek"}],
            "strategy": "race",
            "race_size": 2,
        })
        assert resp.status_code == 201

        # List
        resp = await client.get("/api/combos")
        assert resp.status_code == 200
        names = [c["name"] for c in resp.json()["combos"]]
        assert "fast" in names

        # Get
        resp = await client.get("/api/combos/fast")
        assert resp.status_code == 200

        # Delete
        resp = await client.delete("/api/combos/fast")
        assert resp.status_code == 200
        resp = await client.get("/api/combos/fast")
        assert resp.status_code == 404

    async def test_chat_via_combo(self, client, sample_llm_response):
        """model=combo:fast should route through the race path."""
        await combo_store.save(Combo(
            name="fast",
            targets=[ComboTarget(provider="nvidia", model=None)],
            strategy="race",
            race_size=2,
        ))

        key = MagicMock(key="k", key_id="fid", display="d", index=0, requests_used=1, requests_limit=35)

        with (
            patch("app.api.chat.get_cached_response", new=AsyncMock(return_value=None)),
            patch("app.api.chat.build_context", new=AsyncMock(return_value=[{"role": "user", "content": "hi"}])),
            patch("app.api.chat.key_manager") as mock_km,
            patch("app.api.chat.get_provider") as mock_get_provider,
            patch("app.api.chat.set_cached_response", new=AsyncMock()),
            patch("app.services.circuit_breaker.circuit_breaker.is_available", new=AsyncMock(return_value=True)),
        ):
            mock_km.acquire_key = AsyncMock(return_value=key)
            mock_km.report_error = AsyncMock()
            provider = AsyncMock()
            provider.name = "nvidia"
            provider.default_model = "test-model"
            provider.chat = AsyncMock(return_value=sample_llm_response)
            mock_get_provider.return_value = provider

            resp = await client.post(
                "/api/chat",
                json={"message": "hello", "project": "test", "model": "combo:fast"},
            )
            assert resp.status_code == 200
            assert resp.json()["provider"] == "nvidia"

    async def test_metrics_endpoint(self, client):
        resp = await client.get("/api/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_requests" in data
        assert "circuit_states" in data

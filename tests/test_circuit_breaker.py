"""Tests for the circuit breaker service."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from app.services.circuit_breaker import CircuitBreakerRegistry


@pytest.fixture
def breaker():
    """Fresh breaker with fast thresholds for the tests."""
    return CircuitBreakerRegistry(failure_threshold=3, unhealthy_duration=0.05)


@pytest.mark.asyncio
class TestCircuitBreaker:
    async def test_closed_allows_traffic(self, breaker):
        with patch("app.services.circuit_breaker.get_redis", new=AsyncMock(side_effect=Exception("no redis"))):
            assert await breaker.is_available("nvidia") is True

    async def test_open_after_threshold_failures(self, breaker):
        with patch("app.services.circuit_breaker.get_redis", new=AsyncMock(side_effect=Exception("no redis"))):
            for _ in range(3):
                state = await breaker.record_failure("nvidia")
            assert state.state == "open"
            assert state.consecutive_failures == 3
            assert await breaker.is_available("nvidia") is False

    async def test_half_open_after_window(self, breaker):
        with patch("app.services.circuit_breaker.get_redis", new=AsyncMock(side_effect=Exception("no redis"))):
            for _ in range(3):
                await breaker.record_failure("nvidia")
            assert await breaker.is_available("nvidia") is False
            await asyncio.sleep(0.06)
            # After the window the probe is allowed through
            assert await breaker.is_available("nvidia") is True

    async def test_success_resets(self, breaker):
        with patch("app.services.circuit_breaker.get_redis", new=AsyncMock(side_effect=Exception("no redis"))):
            await breaker.record_failure("nvidia")
            await breaker.record_failure("nvidia")
            await breaker.record_success("nvidia")
            state = await breaker.get_state("nvidia")
            assert state.consecutive_failures == 0
            assert await breaker.is_available("nvidia") is True

    async def test_scoped_by_model(self, breaker):
        with patch("app.services.circuit_breaker.get_redis", new=AsyncMock(side_effect=Exception("no redis"))):
            for _ in range(3):
                await breaker.record_failure("nvidia", "model-a")
            assert await breaker.is_available("nvidia", "model-a") is False
            assert await breaker.is_available("nvidia", "model-b") is True

    async def test_get_all_states_snapshot(self, breaker):
        with patch("app.services.circuit_breaker.get_redis", new=AsyncMock(side_effect=Exception("no redis"))):
            await breaker.record_failure("nvidia")
            await breaker.record_failure("groq", "m1")
            states = await breaker.get_all_states()
            assert "nvidia" in states
            assert "groq:m1" in states

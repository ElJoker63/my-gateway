"""Tests for combos, race execution, and metrics."""


import pytest
from app.services.combos import Combo, ComboTarget
from app.services.metrics import MetricsStore
from app.services.racing import race_or_failover, race_targets


class TestComboModel:
    def test_combo_serialization_roundtrip(self):
        combo = Combo(
            name="fast",
            targets=[
                ComboTarget(provider="nvidia", model="llama-3.3-70b"),
                ComboTarget(provider="deepseek", model=None),
            ],
            strategy="race",
            race_size=2,
        )
        data = combo.to_dict()
        assert Combo.from_dict(data) == combo

    def test_default_strategy_is_strict(self):
        combo = Combo(name="x", targets=[ComboTarget(provider="nvidia")])
        assert combo.strategy == "strict"
        assert combo.race_size == 2


@pytest.mark.asyncio
class TestRacing:
    async def test_strict_first_success_wins(self):
        order = []
        targets = ["a", "b", "c"]

        async def call(t):
            order.append(t)
            if t == "a":
                raise RuntimeError("fail")
            return f"ok-{t}"

        outcome = await race_or_failover(targets, call, strategy="strict")
        assert outcome.ok is True
        assert outcome.result == "ok-b"
        assert outcome.attempts == 2
        assert order == ["a", "b"]  # c never ran

    async def test_strict_all_fail(self):
        async def call(t):
            raise RuntimeError("boom")

        outcome = await race_or_failover(["a", "b"], call, strategy="strict")
        assert outcome.ok is False
        assert outcome.attempts == 2
        assert "boom" in outcome.error

    async def test_race_first_valid_response_wins(self):
        import asyncio

        async def call(t):
            if t == "slow":
                await asyncio.sleep(0.05)
                return "slow"
            return f"fast-{t}"

        outcome = await race_or_failover(["slow", "fast1", "fast2"], call, strategy="race", race_size=2)
        assert outcome.ok is True
        assert outcome.result in ("fast-fast1", "fast-fast2")

    async def test_race_all_fail_returns_last_error(self):
        async def call(t):
            raise RuntimeError(f"err-{t}")

        outcome = await race_targets(["a", "b"], call, race_size=2)
        assert outcome.ok is False
        assert outcome.attempts == 2

    async def test_race_size_caps_parallelism(self):
        import asyncio

        started = []

        async def call(t):
            started.append(t)
            await asyncio.sleep(0.01)
            return t

        outcome = await race_targets(["a", "b", "c", "d"], call, race_size=2)
        assert outcome.ok is True
        assert len(started) == 2  # only race_size targets launched


class TestMetrics:
    def test_counters_and_percentiles(self):
        m = MetricsStore()
        m.record("nvidia", "llama", latency_ms=100, ok=True, tokens=50)
        m.record("nvidia", "llama", latency_ms=200, ok=True, tokens=80)
        m.record("nvidia", "llama", latency_ms=50, ok=False)
        m.record("groq", "mixtral", latency_ms=300, ok=True, raced=True, won_race=True)

        s = m.summary()
        assert s["total_requests"] == 4
        assert s["total_errors"] == 1
        assert s["total_races"] == 1
        assert s["race_wins"] == 1
        assert s["providers"]["nvidia"]["requests"] == 3
        assert s["providers"]["nvidia"]["error_rate"] == pytest.approx(round(1 / 3, 4))
        assert "nvidia:llama" in s["latency"]

    def test_latency_percentiles(self):
        m = MetricsStore()
        for ms in range(1, 101):
            m.record("p", "m", latency_ms=ms, ok=True)
        lat = m.summary()["latency"]["p:m"]
        assert lat["p50_ms"] == pytest.approx(50, abs=2)
        assert lat["p95_ms"] == pytest.approx(95, abs=2)
        assert lat["count"] == 100

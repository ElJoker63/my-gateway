"""Config must scale to all providers via env vars, not just the typed 4."""

import os
from app.config import Settings


class TestProviderEnvFallback:
    def test_provider_keys_from_env_for_untyped_provider(self, monkeypatch):
        """Provider without typed Settings fields reads from env."""
        monkeypatch.setenv("QIANFAN_API_KEY", "qf-key-123")
        s = Settings()
        assert s.get_provider_keys("qianfan") == ["qf-key-123"]

    def test_provider_keys_json_from_env(self, monkeypatch):
        monkeypatch.setenv("DASHSCOPE_API_KEYS", '["k1","k2"]')
        s = Settings()
        assert s.get_provider_keys("dashscope") == ["k1", "k2"]

    def test_provider_keys_comma_separated_from_env(self, monkeypatch):
        monkeypatch.setenv("MOONSHOT_API_KEYS", "k1,k2,k3")
        s = Settings()
        assert s.get_provider_keys("moonshot") == ["k1", "k2", "k3"]

    def test_provider_rpm_from_env(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_RPM_LIMIT", "120")
        s = Settings()
        assert s.get_provider_rpm("deepseek") == 120

    def test_typed_field_wins_over_env(self, monkeypatch):
        """Typed Settings field (from its own env var) takes precedence."""
        monkeypatch.setenv("NVIDIA_API_KEY", "typed-nvidia-key")
        s = Settings()
        assert s.get_provider_keys("nvidia") == ["typed-nvidia-key"]

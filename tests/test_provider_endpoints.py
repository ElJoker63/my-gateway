"""Regression tests for provider endpoints previously pointing to wrong APIs."""

import os
import importlib
import pytest


class TestFixedProviderEndpoints:
    def test_qianfan_uses_openai_compatible_v2(self):
        from app.providers.qianfan.config import QIANFAN_BASE_URL
        assert QIANFAN_BASE_URL == "https://qianfan.baidubce.com/v2"

    def test_qianfan_adapter_is_bearer_compatible(self):
        from app.providers.qianfan import QianfanProvider
        p = QianfanProvider(api_key="test")
        headers = p._get_headers()
        assert headers["Authorization"] == "Bearer test"
        # Chat URL must be the OpenAI-compatible path under v2
        url = f"{p.base_url}/chat/completions"
        assert url == "https://qianfan.baidubce.com/v2/chat/completions"

    def test_hunyuan_uses_cloud_tencent_endpoint(self):
        from app.providers.hunyuan.config import HUNYUAN_BASE_URL
        assert "hunyuan.cloud.tencent.com" in HUNYUAN_BASE_URL

    def test_opencode_uses_zen_gateway(self):
        from app.providers.opencode.config import OPENCODE_BASE_URL
        assert OPENCODE_BASE_URL == "https://opencode.ai/zen/v1"

    def test_sensenova_uses_compatible_mode(self):
        from app.providers.sensenova.config import SENSENOVA_BASE_URL
        assert "compatible-mode/v1" in SENSENOVA_BASE_URL

    def test_cloudflare_requires_account_id(self, monkeypatch):
        """Without CLOUDFLARE_ACCOUNT_ID the base URL must be empty (provider skipped)."""
        monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
        monkeypatch.delenv("CLOUDFLARE_BASE_URL", raising=False)
        # reload config module to pick up the cleared env
        from app.providers.cloudflare import config as cf_config
        importlib.reload(cf_config)
        assert cf_config.CLOUDFLARE_BASE_URL == ""

    def test_cloudflare_builds_scoped_url(self, monkeypatch):
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc123")
        monkeypatch.delenv("CLOUDFLARE_BASE_URL", raising=False)
        from app.providers.cloudflare import config as cf_config
        importlib.reload(cf_config)
        assert cf_config.CLOUDFLARE_BASE_URL == \
            "https://api.cloudflare.com/client/v4/accounts/acc123/ai/v1"

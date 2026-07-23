"""Tests for LLM providers."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.providers.base import LLMProvider
from app.providers.nvidia import NvidiaProvider
from app.providers.openai import OpenAIProvider
from app.providers import get_provider, init_providers, list_providers


class TestLLMProviderBase:
    """Test the abstract base provider."""

    def test_build_params_basic(self):
        """Should build basic params correctly."""

        class TestProvider(LLMProvider):
            name = "test"
            default_model = "test-model"

            async def chat(self, messages, **kwargs):
                return {}

            async def chat_stream(self, messages, **kwargs):
                yield {}

            async def health_check(self):
                return True

        provider = TestProvider()
        params = provider._build_params(
            messages=[{"role": "user", "content": "hi"}],
            model="custom-model",
            temperature=0.7,
            max_tokens=100,
            top_p=None,
            stop=None,
        )

        assert params["model"] == "custom-model"
        assert params["temperature"] == 0.7
        assert params["max_tokens"] == 100
        assert "top_p" not in params
        assert "stop" not in params

    def test_build_params_defaults(self):
        """Should use default model when none specified."""

        class TestProvider(LLMProvider):
            name = "test"
            default_model = "default-model"

            async def chat(self, messages, **kwargs):
                return {}

            async def chat_stream(self, messages, **kwargs):
                yield {}

            async def health_check(self):
                return True

        provider = TestProvider()
        params = provider._build_params(
            messages=[{"role": "user", "content": "hi"}],
            model=None,
            temperature=None,
            max_tokens=None,
            top_p=None,
            stop=None,
        )

        assert params["model"] == "default-model"


class TestNvidiaProvider:
    """Test the NVIDIA provider."""

    def test_initialization(self, settings):
        """Should initialize with settings."""
        provider = NvidiaProvider()
        assert provider.name == "nvidia"
        assert provider.api_key == "test-nvidia-key"

    @pytest.mark.asyncio
    async def test_health_check_no_key(self):
        """Should return False when no API key."""
        with patch.dict("os.environ", {"NVIDIA_API_KEY": ""}):
            from app.config import get_settings
            get_settings.cache_clear()
            provider = NvidiaProvider()
            provider.api_key = ""
            result = await provider.health_check()
            assert result is False


class TestOpenAIProvider:
    """Test the OpenAI provider."""

    def test_initialization(self, settings):
        """Should initialize with settings."""
        provider = OpenAIProvider()
        assert provider.name == "openai"

    @pytest.mark.asyncio
    async def test_health_check_no_key(self):
        """Should return False when no API key."""
        provider = OpenAIProvider()
        provider.api_key = ""
        result = await provider.health_check()
        assert result is False


class TestProviderRegistry:
    """Test the provider registry."""

    def test_list_providers(self):
        """Should list available providers."""
        providers = list_providers()
        assert isinstance(providers, list)

    def test_get_default_provider(self):
        """Should return a provider."""
        provider = get_provider()
        assert provider is not None
        assert hasattr(provider, "chat")
        assert hasattr(provider, "chat_stream")

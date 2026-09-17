"""Tests for LLM providers."""

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
    """Test the NVIDIA provider (package adapter)."""

    def test_initialization_with_key(self):
        """Should store the injected API key."""
        provider = NvidiaProvider(api_key="nv-test-key")
        assert provider.name == "nvidia"
        assert provider.default_api_key == "nv-test-key"
        assert provider.base_url  # from config / env

    @pytest.mark.asyncio
    async def test_health_check_unhealthy_on_http_error(self):
        """health_check must be False when the provider returns an error status."""
        provider = NvidiaProvider(api_key="bad-key")
        mock_response = MagicMock()
        mock_response.status_code = 401
        provider.client.get = AsyncMock(return_value=mock_response)
        assert await provider.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_healthy_on_ok(self):
        """health_check must be True when /models responds 2xx/3xx."""
        provider = NvidiaProvider(api_key="good-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        provider.client.get = AsyncMock(return_value=mock_response)
        assert await provider.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_false_on_exception(self):
        """health_check must swallow transport errors and return False."""
        provider = NvidiaProvider(api_key="any")
        provider.client.get = AsyncMock(side_effect=Exception("boom"))
        assert await provider.health_check() is False

    @pytest.mark.asyncio
    async def test_embeddings_rejected_when_capability_off(self):
        """Providers without embeddings capability must refuse embedding calls."""
        from app.providers.deepseek import DeepSeekProvider
        provider = DeepSeekProvider(api_key="k")
        with pytest.raises(NotImplementedError):
            await provider.embeddings(["hi"])

    @pytest.mark.asyncio
    async def test_embeddings_requires_model(self):
        """Capable provider without a configured model must ask for one."""
        provider = NvidiaProvider(api_key="k")
        provider.embedding_model = ""
        with pytest.raises(ValueError, match="embedding model"):
            await provider.embeddings(["hi"])


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

    def test_key_injection_at_init(self):
        """init_providers must inject the first pool key into the adapter."""
        from app.providers import PROVIDER_CLASSES, _providers
        init_providers()
        nvidia = _providers["nvidia"]
        # conftest sets NVIDIA_API_KEY=test-nvidia-key
        assert getattr(nvidia, "default_api_key", "") == "test-nvidia-key" or \
               getattr(nvidia, "api_key", "") == "test-nvidia-key"

"""Parametric tests over ALL registered providers — catches mass-generation bugs.

Covers what the old per-package tests never did: real chat round-trips with
mocked HTTP, health checks, and the metadata consistency contract.
"""

import importlib
import json
from pathlib import Path

import pytest
from app.providers import PROVIDER_CLASSES, _providers, init_providers

PROVIDERS_DIR = Path(__file__).resolve().parents[2] / "app" / "providers"

PACKAGE_PROVIDERS = [
    d.name for d in sorted(PROVIDERS_DIR.iterdir())
    if d.is_dir() and not d.name.startswith("_") and (d / "adapter.py").exists()
]


# ---------------------------------------------------------------------------
# Registry-wide invariants
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", PACKAGE_PROVIDERS)
def test_provider_package_registered(name):
    """Every package with an adapter must be registered in PROVIDER_CLASSES."""
    assert name in PROVIDER_CLASSES, f"{name} missing from PROVIDER_CLASSES"


@pytest.mark.parametrize("name", PACKAGE_PROVIDERS)
def test_provider_metadata_matches_config(name):
    """metadata.json must not contradict the Python config."""
    meta = json.loads((PROVIDERS_DIR / name / "metadata.json").read_text(encoding="utf-8"))
    mod = importlib.import_module(f"app.providers.{name}.config")
    cfg_url = getattr(mod, f"{name.upper()}_BASE_URL", None)
    cfg_model = getattr(mod, f"{name.upper()}_DEFAULT_MODEL", None)
    assert cfg_url is not None or name == "cloudflare"  # cloudflare uses account-scoped URL
    if cfg_url:
        assert meta["base_url"].startswith("http") or "{CLOUDFLARE_ACCOUNT_ID}" in meta["base_url"]
    assert cfg_model == meta["default_model"], f"{name}: model drift between config and metadata"


# ---------------------------------------------------------------------------
# Behavior tests on one representative OpenAIAdapter (groq)
# ---------------------------------------------------------------------------

@pytest.fixture
def groq_provider():
    from app.providers.groq import GroqProvider
    return GroqProvider(api_key="test-key")


@pytest.mark.asyncio
async def test_chat_calls_correct_url(monkeypatch):
    import httpx
    from app.providers.groq import GroqProvider

    provider = GroqProvider(api_key="test-key")

    captured = {}

    async def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        captured["headers"] = kwargs.get("headers")
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-x",
                "object": "chat.completion",
                "created": 1,
                "model": "llama-3.3-70b-versatile",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "hi"},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
            request=request,
        )

    monkeypatch.setattr(provider.client, "post", fake_post)
    out = await provider.chat(messages=[{"role": "user", "content": "hi"}], model="llama-3.3-70b-versatile")
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert out["content"] == "hi"


@pytest.mark.asyncio
async def test_health_check_false_on_401(groq_provider, monkeypatch):
    import httpx
    req = httpx.Request("GET", groq_provider.base_url + "/models")
    resp = httpx.Response(401, request=req)

    async def fake_get(*a, **k):
        return resp

    monkeypatch.setattr(groq_provider.client, "get", fake_get)
    assert await groq_provider.health_check() is False


@pytest.mark.asyncio
async def test_embeddings_blocked_when_capability_off():
    """DeepSeek metadata sets embeddings=false → must refuse."""
    from app.providers.deepseek import DeepSeekProvider
    p = DeepSeekProvider(api_key="k")
    with pytest.raises(NotImplementedError):
        await p.embeddings(["x"])


# ---------------------------------------------------------------------------
# init_providers end-to-end smoke
# ---------------------------------------------------------------------------

def test_init_providers_populates_registry():
    init_providers()
    assert len(_providers) >= 1
    for name, inst in _providers.items():
        assert inst.name == name
        assert getattr(inst, "default_model", "")

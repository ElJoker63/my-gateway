"""
Embedding service.
Supports local sentence-transformers or NVIDIA embedding API.
CPU-bound local encoding is offloaded to a worker thread so it never
blocks the asyncio event loop.
"""

import asyncio
import logging
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# Lazy-loaded local model
_local_model = None
_model_lock = asyncio.Lock()


async def _get_local_model_async():
    """Load (once) the local sentence-transformers model without blocking the loop."""
    global _local_model
    if _local_model is not None:
        return _local_model

    async with _model_lock:
        if _local_model is not None:
            return _local_model

        def _load():
            from sentence_transformers import SentenceTransformer

            settings = get_settings()
            model_name = settings.local_embedding_model_name
            logger.info(f"Loading local embedding model: {model_name}")
            model = SentenceTransformer(model_name)
            logger.info(
                f"Local embedding model loaded (dim={model.get_sentence_embedding_dimension()})"
            )
            return model

        _local_model = await asyncio.to_thread(_load)
        return _local_model


async def preload_embedding_model():
    """Eagerly load the local embedding model during app startup."""
    settings = get_settings()
    if settings.embedding_model == "local":
        try:
            await _get_local_model_async()
            logger.info("✓ Embedding model preloaded")
        except Exception as e:
            logger.error(f"✗ Failed to preload embedding model: {e}")


async def get_embedding(text: str) -> list[float]:
    """
    Generate an embedding vector for a single text.

    Uses local model by default, or NVIDIA API if configured.
    """
    settings = get_settings()

    if settings.embedding_model == "nvidia":
        return await _get_nvidia_embedding(text)
    else:
        return await _get_local_embedding(text)


async def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a batch of texts.
    More efficient than calling get_embedding() in a loop.
    """
    settings = get_settings()

    if settings.embedding_model == "nvidia":
        return await _get_nvidia_embeddings_batch(texts)
    else:
        return await _get_local_embeddings_batch(texts)


async def _get_local_embedding(text: str) -> list[float]:
    """Generate embedding using local sentence-transformers model (off-loop)."""
    model = await _get_local_model_async()
    embedding = await asyncio.to_thread(
        model.encode, text, normalize_embeddings=True
    )
    return embedding.tolist()


async def _get_local_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch using local model (off-loop)."""
    model = await _get_local_model_async()
    embeddings = await asyncio.to_thread(
        model.encode, texts, normalize_embeddings=True, batch_size=32
    )
    return [e.tolist() for e in embeddings]


# Shared httpx client for NVIDIA embedding calls (keep-alive across requests)
_nvidia_client: Optional["httpx.AsyncClient"] = None


async def _get_nvidia_client() -> "httpx.AsyncClient":
    """Return a shared async HTTP client for the NVIDIA embeddings API."""
    global _nvidia_client
    if _nvidia_client is None or _nvidia_client.is_closed:
        _nvidia_client = httpx.AsyncClient(timeout=60.0)
    return _nvidia_client


async def _get_nvidia_embedding(text: str) -> list[float]:
    """Generate embedding for a single text via NVIDIA API."""
    vectors = await _get_nvidia_embeddings_batch([text])
    return vectors[0]


async def _get_nvidia_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for many texts using the native batch `input` list
    supported by the NVIDIA embeddings endpoint — one HTTP call per chunk.
    Chunks are capped at 64 texts to respect provider payload limits.
    Acquires keys through the KeyManager so rotation/cooldown apply.
    """
    settings = get_settings()
    from app.services.key_manager import key_manager

    client = await _get_nvidia_client()
    chunk_size = 64
    out: list[list[float]] = []

    for start in range(0, len(texts), chunk_size):
        chunk = texts[start : start + chunk_size]
        key_info = await key_manager.acquire_key("nvidia")
        try:
            response = await client.post(
                f"{settings.nvidia_base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {key_info.key}",
                    "Content-Type": "application/json",
                },
                json={
                    "input": chunk,
                    "model": "nvidia/nv-embedqa-e5-v5",
                    "input_type": "query",
                },
            )
            response.raise_for_status()
            data = response.json()
            # Sort by index to preserve input order
            items = sorted(data["data"], key=lambda d: d.get("index", 0))
            out.extend(item["embedding"] for item in items)
        except Exception:
            await key_manager.report_error("nvidia", key_info.key_id, "api_error")
            raise

    return out

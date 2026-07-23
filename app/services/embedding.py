"""
Embedding service.
Supports local sentence-transformers or NVIDIA embedding API.
"""

import logging
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

# Lazy-loaded local model
_local_model = None


def _get_local_model():
    """Lazy-load the local sentence-transformers model."""
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer

        settings = get_settings()
        model_name = settings.local_embedding_model_name
        logger.info(f"Loading local embedding model: {model_name}")
        _local_model = SentenceTransformer(model_name)
        logger.info(f"Local embedding model loaded (dim={_local_model.get_sentence_embedding_dimension()})")
    return _local_model


async def get_embedding(text: str) -> list[float]:
    """
    Generate an embedding vector for a single text.

    Uses local model by default, or NVIDIA API if configured.
    """
    settings = get_settings()

    if settings.embedding_model == "nvidia":
        return await _get_nvidia_embedding(text)
    else:
        return _get_local_embedding(text)


async def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a batch of texts.
    More efficient than calling get_embedding() in a loop.
    """
    settings = get_settings()

    if settings.embedding_model == "nvidia":
        return [await _get_nvidia_embedding(t) for t in texts]
    else:
        return _get_local_embeddings_batch(texts)


def _get_local_embedding(text: str) -> list[float]:
    """Generate embedding using local sentence-transformers model."""
    model = _get_local_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def _get_local_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch using local model."""
    model = _get_local_model()
    embeddings = model.encode(texts, normalize_embeddings=True, batch_size=32)
    return [e.tolist() for e in embeddings]


async def _get_nvidia_embedding(text: str) -> list[float]:
    """Generate embedding using NVIDIA API."""
    import httpx

    settings = get_settings()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.nvidia_base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {settings.nvidia_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "input": text,
                "model": "nvidia/nv-embedqa-e5-v5",
                "input_type": "query",
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]

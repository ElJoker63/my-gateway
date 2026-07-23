"""
Qdrant-backed vector memory service.
Stores and retrieves project memories using semantic embeddings.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from qdrant_client.models import (
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from app.config import get_settings
from app.database.qdrant import get_qdrant, ensure_collection
from app.services.embedding import get_embedding, get_embeddings_batch

logger = logging.getLogger(__name__)

# Collection naming convention: "project_{name}"
COLLECTION_PREFIX = "project_"


def _collection_name(project: str) -> str:
    """Get the Qdrant collection name for a project."""
    # Sanitize project name for Qdrant (alphanumeric + underscore)
    safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in project.lower())
    return f"{COLLECTION_PREFIX}{safe_name}"


async def store_memory(
    text: str,
    project: str,
    file: Optional[str] = None,
    memory_type: str = "general",
    metadata: Optional[dict] = None,
) -> str:
    """
    Store a single memory entry in Qdrant.

    Args:
        text: Text content to store
        project: Project name
        file: Source file path
        memory_type: Type of memory (code, doc, decision, architecture, etc.)
        metadata: Additional metadata

    Returns:
        The generated point ID
    """
    collection = _collection_name(project)
    ensure_collection(collection)

    # Generate embedding
    vector = await get_embedding(text)

    point_id = str(uuid.uuid4())
    payload = {
        "text": text,
        "project": project,
        "file": file or "",
        "type": memory_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if metadata:
        payload["metadata"] = metadata

    client = get_qdrant()
    client.upsert(
        collection_name=collection,
        points=[
            PointStruct(
                id=point_id,
                vector=vector,
                payload=payload,
            )
        ],
    )

    logger.debug(f"Stored memory in '{collection}': type={memory_type}, len={len(text)}")
    return point_id


async def store_memories_batch(
    entries: list[dict],
    project: str,
) -> int:
    """
    Store multiple memory entries at once (for project indexing).

    Args:
        entries: List of dicts with keys: text, file, type, metadata
        project: Project name

    Returns:
        Number of entries stored
    """
    if not entries:
        return 0

    collection = _collection_name(project)
    ensure_collection(collection)

    # Batch embed all texts
    texts = [e["text"] for e in entries]
    vectors = await get_embeddings_batch(texts)

    points = []
    for entry, vector in zip(entries, vectors):
        point_id = str(uuid.uuid4())
        payload = {
            "text": entry["text"],
            "project": project,
            "file": entry.get("file", ""),
            "type": entry.get("type", "general"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if entry.get("metadata"):
            payload["metadata"] = entry["metadata"]

        points.append(PointStruct(id=point_id, vector=vector, payload=payload))

    # Upsert in batches of 100
    client = get_qdrant()
    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        client.upsert(collection_name=collection, points=batch)

    logger.info(f"Batch stored {len(points)} memories in '{collection}'")
    return len(points)


async def search_memory(
    query: str,
    project: Optional[str] = None,
    memory_type: Optional[str] = None,
    top_k: int = 10,
    score_threshold: Optional[float] = None,
) -> list[dict]:
    """
    Search memory using semantic similarity.

    Args:
        query: Search query text
        project: Filter by project (required if not searching globally)
        memory_type: Filter by memory type
        top_k: Number of results to return
        score_threshold: Minimum relevance score

    Returns:
        List of matching memory entries with scores
    """
    settings = get_settings()
    threshold = score_threshold or settings.memory_score_threshold

    # Generate query embedding
    query_vector = await get_embedding(query)

    # Build filter conditions
    filter_conditions = []
    if memory_type:
        filter_conditions.append(
            FieldCondition(key="type", match=MatchValue(value=memory_type))
        )

    query_filter = Filter(must=filter_conditions) if filter_conditions else None

    # Determine which collections to search
    if project:
        collections = [_collection_name(project)]
    else:
        # Search all project collections
        client = get_qdrant()
        all_collections = [c.name for c in client.get_collections().collections]
        collections = [c for c in all_collections if c.startswith(COLLECTION_PREFIX)]

    results = []
    client = get_qdrant()

    for collection in collections:
        try:
            hits = client.search(
                collection_name=collection,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=top_k,
                score_threshold=threshold,
            )

            for hit in hits:
                results.append({
                    "id": str(hit.id),
                    "text": hit.payload.get("text", ""),
                    "project": hit.payload.get("project", ""),
                    "file": hit.payload.get("file", ""),
                    "type": hit.payload.get("type", "general"),
                    "score": round(hit.score, 4),
                    "timestamp": hit.payload.get("timestamp", ""),
                    "metadata": hit.payload.get("metadata"),
                })
        except Exception as e:
            logger.error(f"Search error in collection '{collection}': {e}")

    # Sort by score descending and limit
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


async def get_project_memories(project: str, limit: int = 100) -> list[dict]:
    """Get all memories for a project."""
    collection = _collection_name(project)
    client = get_qdrant()

    try:
        result = client.scroll(
            collection_name=collection,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        memories = []
        for point in result[0]:
            memories.append({
                "id": str(point.id),
                "text": point.payload.get("text", ""),
                "project": point.payload.get("project", ""),
                "file": point.payload.get("file", ""),
                "type": point.payload.get("type", "general"),
                "timestamp": point.payload.get("timestamp", ""),
                "metadata": point.payload.get("metadata"),
            })

        return memories
    except Exception as e:
        logger.error(f"Error getting memories for project '{project}': {e}")
        return []


async def delete_project_memory(project: str) -> bool:
    """Delete all memories for a project (drops the collection)."""
    collection = _collection_name(project)
    client = get_qdrant()

    try:
        collections = [c.name for c in client.get_collections().collections]
        if collection in collections:
            client.delete_collection(collection_name=collection)
            logger.info(f"Deleted collection: {collection}")
        return True
    except Exception as e:
        logger.error(f"Error deleting project memory '{project}': {e}")
        return False


async def get_project_stats(project: str) -> dict:
    """Get stats for a project's memory collection."""
    collection = _collection_name(project)
    client = get_qdrant()

    try:
        info = client.get_collection(collection_name=collection)
        return {
            "name": project,
            "collection": collection,
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
            "status": info.status.value if info.status else "unknown",
        }
    except Exception as e:
        logger.debug(f"Collection not found for project '{project}': {e}")
        return {
            "name": project,
            "collection": collection,
            "points_count": 0,
            "vectors_count": 0,
            "status": "not_found",
        }


async def list_projects() -> list[str]:
    """List all projects that have memory collections."""
    client = get_qdrant()
    try:
        collections = client.get_collections().collections
        projects = []
        for c in collections:
            if c.name.startswith(COLLECTION_PREFIX):
                project_name = c.name[len(COLLECTION_PREFIX):]
                projects.append(project_name)
        return projects
    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        return []

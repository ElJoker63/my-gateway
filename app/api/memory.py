"""
Memory API endpoints.
CRUD operations for the vector memory system.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.requests import MemoryStoreRequest, MemorySearchRequest
from app.models.responses import MemoryEntry, MemorySearchResponse
from app.services.memory import (
    store_memory,
    search_memory,
    get_project_memories,
    delete_project_memory,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/store", response_model=dict, tags=["Memory"])
async def store_memory_endpoint(request: MemoryStoreRequest):
    """Store a new memory entry in the vector database."""
    try:
        point_id = await store_memory(
            text=request.text,
            project=request.project,
            file=request.file,
            memory_type=request.type,
            metadata=request.metadata,
        )
        return {
            "status": "stored",
            "id": point_id,
            "project": request.project,
            "type": request.type,
        }
    except Exception as e:
        logger.error(f"Memory store error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to store memory: {str(e)}")


@router.post("/search", response_model=MemorySearchResponse, tags=["Memory"])
async def search_memory_endpoint(request: MemorySearchRequest):
    """Search memory entries using semantic similarity."""
    try:
        results = await search_memory(
            query=request.query,
            project=request.project,
            memory_type=request.type,
            top_k=request.top_k,
        )

        entries = [MemoryEntry(**r) for r in results]

        return MemorySearchResponse(
            results=entries,
            total=len(entries),
            query=request.query,
        )
    except Exception as e:
        logger.error(f"Memory search error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/project/{project}", tags=["Memory"])
async def get_project_memories_endpoint(
    project: str,
    limit: int = Query(default=100, ge=1, le=1000),
):
    """List all memories for a specific project."""
    try:
        memories = await get_project_memories(project, limit=limit)
        return {
            "project": project,
            "memories": memories,
            "total": len(memories),
        }
    except Exception as e:
        logger.error(f"Error getting project memories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/project/{project}", tags=["Memory"])
async def delete_project_memories_endpoint(project: str):
    """Delete all memories for a specific project."""
    success = await delete_project_memory(project)
    if success:
        return {"status": "deleted", "project": project}
    raise HTTPException(status_code=500, detail=f"Failed to delete memories for '{project}'")

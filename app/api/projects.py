"""
Projects API endpoints.
Project indexing, listing, and management.
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks

from app.config import get_settings
from app.models.requests import ProjectIndexRequest
from app.models.responses import ProjectInfoResponse
from app.services.memory import (
    list_projects,
    get_project_stats,
    delete_project_memory,
)
from app.workers.tasks import index_project_task

logger = logging.getLogger(__name__)
router = APIRouter()


def _resolve_allowed_path(raw_path: str) -> Path:
    """
    Resolve and validate a directory path against the allowed index roots.

    Raises HTTPException 403 when the path escapes every configured root,
    400 when it does not exist or is not a directory.
    """
    settings = get_settings()
    roots = settings.allowed_index_roots

    if not roots:
        raise HTTPException(
            status_code=403,
            detail=(
                "Project indexing is disabled: configure ALLOWED_INDEX_ROOTS "
                "with the directories the gateway is allowed to scan."
            ),
        )

    resolved = Path(raw_path).expanduser().resolve()
    allowed = any(
        resolved == root or root in resolved.parents
        for root in (Path(r).expanduser().resolve() for r in roots)
    )
    if not allowed:
        logger.warning(f"Rejected indexing attempt outside allowed roots: {raw_path}")
        raise HTTPException(
            status_code=403,
            detail="Path is outside the allowed index roots.",
        )

    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="Directory not found or not a directory.")

    return resolved


@router.post("/index", tags=["Projects"])
async def index_project(
    request: ProjectIndexRequest,
    background_tasks: BackgroundTasks,
):
    """
    Index a project directory.
    Scans files, creates embeddings, and stores in Qdrant.
    Runs as a background task.
    """
    resolved = _resolve_allowed_path(request.path)

    project_name = request.project_name or resolved.name

    # Start indexing in background
    background_tasks.add_task(
        index_project_task,
        path=str(resolved),
        project_name=project_name,
        file_patterns=request.file_patterns,
    )

    return {
        "status": "indexing_started",
        "project": project_name,
        "path": str(resolved),
        "message": f"Project '{project_name}' indexing started in background.",
    }


@router.get("", tags=["Projects"])
async def get_projects():
    """List all indexed projects with real indexing stats."""
    try:
        import asyncio
        from app.database.redis import get_redis

        projects = await list_projects()
        redis = await get_redis()

        async def _build(name: str) -> ProjectInfoResponse:
            stats, raw = await asyncio.gather(
                get_project_stats(name),
                redis.hgetall(f"gw:project:stats:{name}"),
                return_exceptions=True,
            )
            if isinstance(stats, Exception):
                stats = {}
            files_indexed = 0
            if isinstance(raw, dict) and raw:
                val = raw.get(b"files_indexed", raw.get("files_indexed", 0))
                try:
                    files_indexed = int(val)
                except (TypeError, ValueError):
                    files_indexed = 0

            return ProjectInfoResponse(
                name=name,
                files_indexed=files_indexed,
                memory_count=stats.get("points_count", 0),
                status=stats.get("status", "active"),
            )

        project_infos = await asyncio.gather(*(_build(n) for n in projects))

        return {
            "projects": [p.model_dump() for p in project_infos],
            "total": len(project_infos),
        }
    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("/{name}", tags=["Projects"])
async def get_project(name: str):
    """Get details for a specific project."""
    try:
        from app.database.redis import get_redis

        stats = await get_project_stats(name)

        if stats.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

        redis = await get_redis()
        raw = await redis.hgetall(f"gw:project:stats:{name}")
        files_indexed = 0
        if raw:
            val = raw.get(b"files_indexed", raw.get("files_indexed", 0))
            try:
                files_indexed = int(val)
            except (TypeError, ValueError):
                files_indexed = 0

        return ProjectInfoResponse(
            name=name,
            files_indexed=files_indexed,
            memory_count=stats.get("points_count", 0),
            status=stats.get("status", "active"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting project: {e}")
        raise HTTPException(status_code=500, detail="Internal error")


@router.delete("/{name}", tags=["Projects"])
async def delete_project(name: str):
    """Delete a project and all its memories."""
    success = await delete_project_memory(name)
    if success:
        return {"status": "deleted", "project": name}
    raise HTTPException(status_code=500, detail=f"Failed to delete project '{name}'")

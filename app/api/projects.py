"""
Projects API endpoints.
Project indexing, listing, and management.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks

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
    import os

    path = request.path
    if not os.path.isdir(path):
        raise HTTPException(
            status_code=400,
            detail=f"Directory not found: {path}"
        )

    project_name = request.project_name or os.path.basename(path)

    # Start indexing in background
    background_tasks.add_task(
        index_project_task,
        path=path,
        project_name=project_name,
        file_patterns=request.file_patterns,
    )

    return {
        "status": "indexing_started",
        "project": project_name,
        "path": path,
        "message": f"Project '{project_name}' indexing started in background.",
    }


@router.get("", tags=["Projects"])
async def get_projects():
    """List all indexed projects."""
    try:
        projects = await list_projects()
        project_infos = []

        for name in projects:
            stats = await get_project_stats(name)
            project_infos.append(
                ProjectInfoResponse(
                    name=name,
                    files_indexed=0,  # TODO: track separately
                    memory_count=stats.get("points_count", 0),
                    status=stats.get("status", "active"),
                )
            )

        return {
            "projects": [p.model_dump() for p in project_infos],
            "total": len(project_infos),
        }
    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{name}", tags=["Projects"])
async def get_project(name: str):
    """Get details for a specific project."""
    try:
        stats = await get_project_stats(name)

        if stats.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

        return ProjectInfoResponse(
            name=name,
            memory_count=stats.get("points_count", 0),
            status=stats.get("status", "active"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{name}", tags=["Projects"])
async def delete_project(name: str):
    """Delete a project and all its memories."""
    success = await delete_project_memory(name)
    if success:
        return {"status": "deleted", "project": name}
    raise HTTPException(status_code=500, detail=f"Failed to delete project '{name}'")

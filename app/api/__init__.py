"""API routers package."""

from fastapi import APIRouter

from .chat import router as chat_router
from .memory import router as memory_router
from .projects import router as projects_router

# Main API router that aggregates all sub-routers
api_router = APIRouter()
api_router.include_router(chat_router)
api_router.include_router(memory_router, prefix="/api/memory", tags=["Memory"])
api_router.include_router(projects_router, prefix="/api/projects", tags=["Projects"])

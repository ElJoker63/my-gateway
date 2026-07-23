"""Request schemas for all API endpoints."""

from pydantic import BaseModel, Field
from typing import Optional


# --- Chat Messages ---

class ChatMessage(BaseModel):
    """Single chat message in OpenAI format."""
    role: str = Field(..., description="Message role: system, user, assistant")
    content: str = Field(..., description="Message content")


# --- Gateway Simplified Chat ---

class GatewayChatRequest(BaseModel):
    """Simplified gateway chat request."""
    project: str = Field(default="default", description="Project name for context/memory")
    message: str = Field(..., description="User message text")
    provider: Optional[str] = Field(default=None, description="LLM provider override (nvidia, openai)")
    model: Optional[str] = Field(default=None, description="Model override")
    use_memory: bool = Field(default=True, description="Whether to search and inject memory context")
    use_cache: bool = Field(default=True, description="Whether to check/store cache")


# --- OpenAI-Compatible Chat ---

class OpenAIChatRequest(BaseModel):
    """OpenAI-compatible chat completion request."""
    model: str = Field(..., description="Model identifier")
    messages: list[ChatMessage] = Field(..., description="Conversation messages")
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    top_p: Optional[float] = Field(default=None, ge=0, le=1)
    max_tokens: Optional[int] = Field(default=None, gt=0)
    stream: bool = Field(default=False, description="Enable SSE streaming")
    stop: Optional[list[str] | str] = Field(default=None)
    frequency_penalty: Optional[float] = Field(default=None, ge=-2, le=2)
    presence_penalty: Optional[float] = Field(default=None, ge=-2, le=2)
    n: Optional[int] = Field(default=None, ge=1, le=5)
    user: Optional[str] = Field(default=None)

    # Gateway extensions (sent as extra fields or headers)
    project: Optional[str] = Field(default=None, description="Project for memory context")
    use_memory: bool = Field(default=True)
    use_cache: bool = Field(default=True)
    provider: Optional[str] = Field(default=None)

    model_config = {"extra": "allow"}


# --- Anthropic Messages API ---

class AnthropicContentBlock(BaseModel):
    """Content block for Anthropic Messages API."""
    type: str = Field(default="text")
    text: str = Field(...)


class AnthropicMessageRequest(BaseModel):
    """Anthropic Messages API compatible request."""
    model: str = Field(...)
    messages: list[ChatMessage] = Field(...)
    max_tokens: int = Field(default=4096)
    system: Optional[str] = Field(default=None, description="System prompt")
    temperature: Optional[float] = Field(default=None, ge=0, le=1)
    top_p: Optional[float] = Field(default=None, ge=0, le=1)
    stream: bool = Field(default=False)
    stop_sequences: Optional[list[str]] = Field(default=None)

    # Gateway extensions
    project: Optional[str] = Field(default=None)
    use_memory: bool = Field(default=True)
    use_cache: bool = Field(default=True)
    provider: Optional[str] = Field(default=None)

    model_config = {"extra": "allow"}


# --- Memory ---

class MemoryStoreRequest(BaseModel):
    """Request to store a memory entry."""
    text: str = Field(..., description="Text content to store")
    project: str = Field(..., description="Project name")
    file: Optional[str] = Field(default=None, description="Source file path")
    type: str = Field(default="general", description="Memory type: code, doc, decision, architecture, etc.")
    metadata: Optional[dict] = Field(default=None, description="Additional metadata")


class MemorySearchRequest(BaseModel):
    """Request to search memory."""
    query: str = Field(..., description="Search query text")
    project: Optional[str] = Field(default=None, description="Filter by project")
    type: Optional[str] = Field(default=None, description="Filter by memory type")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results")


# --- Projects ---

class ProjectIndexRequest(BaseModel):
    """Request to index a project directory."""
    path: str = Field(..., description="Absolute path to project directory")
    project_name: Optional[str] = Field(default=None, description="Project name (defaults to directory name)")
    file_patterns: Optional[list[str]] = Field(
        default=None,
        description="File glob patterns to include (e.g., ['*.py', '*.js']). None = all text files."
    )

"""Response schemas for all API endpoints."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# --- Gateway Simplified Chat Response ---

class GatewayChatResponse(BaseModel):
    """Simplified gateway chat response."""
    response: str
    provider: str
    cached: bool = False
    project: Optional[str] = None
    usage: Optional[dict] = None


# --- OpenAI-Compatible Chat Response ---

class OpenAIUsage(BaseModel):
    """Token usage statistics."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class OpenAIChoice(BaseModel):
    """Single completion choice."""
    index: int = 0
    message: dict = Field(default_factory=lambda: {"role": "assistant", "content": ""})
    finish_reason: Optional[str] = "stop"


class OpenAIChatResponse(BaseModel):
    """OpenAI-compatible chat completion response."""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[OpenAIChoice]
    usage: OpenAIUsage = Field(default_factory=OpenAIUsage)
    system_fingerprint: Optional[str] = None

    # Gateway extensions
    cached: bool = False
    provider: str = ""


# --- OpenAI SSE Streaming ---

class OpenAIStreamDelta(BaseModel):
    """Delta content in a stream chunk."""
    role: Optional[str] = None
    content: Optional[str] = None


class OpenAIStreamChoice(BaseModel):
    """Single choice in a stream chunk."""
    index: int = 0
    delta: OpenAIStreamDelta = Field(default_factory=OpenAIStreamDelta)
    finish_reason: Optional[str] = None


class OpenAIStreamChunk(BaseModel):
    """OpenAI-compatible streaming chunk."""
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: list[OpenAIStreamChoice]
    system_fingerprint: Optional[str] = None


# --- Anthropic Messages Response ---

class AnthropicContentBlock(BaseModel):
    """Content block in Anthropic response."""
    type: str = "text"
    text: str = ""


class AnthropicUsage(BaseModel):
    """Anthropic usage statistics."""
    input_tokens: int = 0
    output_tokens: int = 0


class AnthropicMessageResponse(BaseModel):
    """Anthropic Messages API compatible response."""
    id: str
    type: str = "message"
    role: str = "assistant"
    content: list[AnthropicContentBlock]
    model: str
    stop_reason: Optional[str] = "end_turn"
    stop_sequence: Optional[str] = None
    usage: AnthropicUsage = Field(default_factory=AnthropicUsage)


# --- Memory ---

class MemoryEntry(BaseModel):
    """Single memory entry from search results."""
    id: str
    text: str
    project: str
    file: Optional[str] = None
    type: str = "general"
    score: float = 0.0
    timestamp: str = ""
    metadata: Optional[dict] = None


class MemorySearchResponse(BaseModel):
    """Response from memory search."""
    results: list[MemoryEntry]
    total: int
    query: str


# --- Projects ---

class ProjectInfoResponse(BaseModel):
    """Project information response."""
    name: str
    files_indexed: int = 0
    memory_count: int = 0
    last_indexed: Optional[str] = None
    status: str = "active"


# --- Health ---

class ServiceHealth(BaseModel):
    """Health status of a single service."""
    status: str = "healthy"
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Gateway health check response."""
    status: str = "healthy"
    version: str = "1.0.0"
    services: dict[str, ServiceHealth] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# --- Rate Limit ---

class RateLimitStatus(BaseModel):
    """Current rate limit status."""
    provider: str
    requests_used: int
    requests_remaining: int
    limit_per_minute: int
    reset_in_seconds: float

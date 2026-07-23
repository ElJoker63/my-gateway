"""
Chat API endpoints.
Supports three formats for agent compatibility:
  - POST /v1/chat/completions  (OpenAI-compatible, used by most agents)
  - POST /v1/messages          (Anthropic Messages API format)
  - POST /api/chat             (Simplified gateway format)
  - POST /response             (Alias, redirects to /v1/chat/completions)

All endpoints share the same core logic via _process_chat().
"""

import json
import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Request, BackgroundTasks
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.models.requests import (
    GatewayChatRequest,
    OpenAIChatRequest,
    AnthropicMessageRequest,
)
from app.models.responses import (
    GatewayChatResponse,
    OpenAIChatResponse,
    OpenAIChoice,
    OpenAIUsage,
    OpenAIStreamChunk,
    OpenAIStreamChoice,
    OpenAIStreamDelta,
    AnthropicMessageResponse,
    AnthropicContentBlock,
    AnthropicUsage,
)
from app.providers import get_provider
from app.services.cache import get_cached_response, set_cached_response
from app.services.key_manager import key_manager
from app.services.context import build_context
from app.services.memory import store_memory

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Core Chat Logic
# =============================================================================


async def _call_with_fallback(
    provider,
    messages: list[dict],
    model: str,
    key_info,
    max_retries: int = 3,
    **kwargs,
) -> dict:
    """
    Call provider.chat() with the acquired key.
    On rate limit (429) or auth error, report the key and retry with next available.
    """
    import httpx
    from app.services.key_manager import key_manager

    last_error = None
    current_key = key_info

    for attempt in range(max_retries):
        try:
            result = await provider.chat(
                messages=messages,
                model=model,
                api_key=current_key.key,
                **kwargs,
            )
            return result

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            last_error = e

            if status == 429:
                error_type = "rate_limit"
            elif status in (401, 403):
                error_type = "auth_error"
            else:
                # Non-retryable HTTP error
                logger.error(f"LLM call failed (HTTP {status}): {e}")
                raise HTTPException(status_code=502, detail=f"LLM provider error: {str(e)}")

            logger.warning(
                f"Key {current_key.key_id} got {status} ({error_type}), "
                f"attempting fallback (attempt {attempt + 1}/{max_retries})"
            )
            await key_manager.report_error(provider.name, current_key.key_id, error_type)

            # Try to get another key
            try:
                current_key = await key_manager.acquire_key(provider.name)
            except (TimeoutError, RuntimeError) as acquire_err:
                raise HTTPException(
                    status_code=429,
                    detail=f"All keys exhausted after fallback: {acquire_err}"
                )

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise HTTPException(status_code=502, detail=f"LLM provider error: {str(e)}")

    # All retries exhausted
    raise HTTPException(
        status_code=502,
        detail=f"LLM call failed after {max_retries} attempts: {last_error}"
    )


async def _process_chat(
    messages: list[dict],
    model: Optional[str] = None,
    provider_name: Optional[str] = None,
    project: str = "default",
    use_memory: bool = True,
    use_cache: bool = True,
    stream: bool = False,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    top_p: Optional[float] = None,
    stop: Optional[list[str]] = None,
    **kwargs,
) -> dict:
    """
    Core chat processing pipeline:
    1. Check cache
    2. Build context from memory
    3. Enforce rate limit (wait if needed)
    4. Call LLM provider
    5. Cache response
    6. Return result
    """
    provider = get_provider(provider_name)
    model_name = model or provider.default_model

    # --- Step 1: Check cache ---
    if use_cache and not stream:
        cached = await get_cached_response(messages, model_name, project)
        if cached:
            logger.info(f"Cache hit for project '{project}'")
            return {
                "content": cached.get("content", ""),
                "model": cached.get("model", model_name),
                "usage": cached.get("usage", {}),
                "provider": provider.name,
                "cached": True,
            }

    # --- Step 2: Build context from memory ---
    enriched_messages = await build_context(messages, project, use_memory)

    # --- Step 3: Acquire key (handles rate limiting + rotation) ---
    try:
        key_info = await key_manager.acquire_key(provider.name)
    except TimeoutError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # --- Step 4: Call LLM provider with acquired key (+ fallback) ---
    result = await _call_with_fallback(
        provider=provider,
        messages=enriched_messages,
        model=model_name,
        key_info=key_info,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        stop=stop,
        **kwargs,
    )

    # --- Step 5: Cache response ---
    if use_cache:
        await set_cached_response(
            messages=messages,  # Cache with ORIGINAL messages (no context)
            model=model_name,
            response={
                "content": result["content"],
                "model": result["model"],
                "usage": result["usage"],
            },
            project=project,
        )

    return {
        "content": result["content"],
        "model": result["model"],
        "usage": result["usage"],
        "provider": provider.name,
        "cached": False,
    }


async def _process_chat_stream(
    messages: list[dict],
    model: Optional[str] = None,
    provider_name: Optional[str] = None,
    project: str = "default",
    use_memory: bool = True,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    top_p: Optional[float] = None,
    stop: Optional[list[str]] = None,
    **kwargs,
):
    """
    Streaming chat processing pipeline.
    Yields SSE-formatted chunks.
    """
    provider = get_provider(provider_name)
    model_name = model or provider.default_model

    # Build context
    enriched_messages = await build_context(messages, project, use_memory)

    # Acquire key
    try:
        key_info = await key_manager.acquire_key(provider.name)
    except (TimeoutError, RuntimeError) as e:
        error_data = json.dumps({"error": {"message": str(e), "type": "rate_limit_error"}})
        yield f"data: {error_data}\n\n"
        return

    # Stream from provider with acquired key
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    try:
        async for chunk in provider.chat_stream(
            messages=enriched_messages,
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stop=stop,
            api_key=key_info.key,
            **kwargs,
        ):
            sse_chunk = OpenAIStreamChunk(
                id=chunk_id,
                created=created,
                model=chunk.get("model", model_name),
                choices=[
                    OpenAIStreamChoice(
                        index=0,
                        delta=OpenAIStreamDelta(
                            role=chunk.get("role"),
                            content=chunk.get("content", ""),
                        ),
                        finish_reason=chunk.get("finish_reason"),
                    )
                ],
            )
            yield f"data: {sse_chunk.model_dump_json()}\n\n"

        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"Stream error: {e}")
        error_data = json.dumps({"error": {"message": str(e), "type": "stream_error"}})
        yield f"data: {error_data}\n\n"


# =============================================================================
# Endpoint: POST /v1/chat/completions (OpenAI-compatible)
# =============================================================================


@router.post("/v1/chat/completions", tags=["Chat"])
async def openai_chat_completions(
    request: OpenAIChatRequest,
    background_tasks: BackgroundTasks,
    x_project: Optional[str] = Header(default=None, alias="X-Project"),
):
    """
    OpenAI-compatible chat completions endpoint.
    Used by Cursor, OpenHands, and most AI coding agents.
    """
    project = request.project or x_project or "default"
    # model_dump() preserves tool_calls / tool_call_id / name on each message,
    # and model_extra carries request-level fields like tools, tool_choice,
    # response_format, stream_options, etc.
    messages = [m.model_dump(exclude_none=True) for m in request.messages]
    request_extra = request.model_dump(exclude_none=True)
    extra_kwargs = {
        k: v
        for k, v in request_extra.items()
        if k in {"tools", "tool_choice", "response_format", "stream_options"}
    }

    # Handle stop as list
    stop = request.stop
    if isinstance(stop, str):
        stop = [stop]

    if request.stream:
        # stream_options must only travel when streaming
        extra_kwargs.pop("stream_options", None)
        return StreamingResponse(
            _process_chat_stream(
                messages=messages,
                model=request.model,
                provider_name=request.provider,
                project=project,
                use_memory=request.use_memory,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                top_p=request.top_p,
                stop=stop,
                **extra_kwargs,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming
    result = await _process_chat(
        messages=messages,
        model=request.model,
        provider_name=request.provider,
        project=project,
        use_memory=request.use_memory,
        use_cache=request.use_cache,
        stream=False,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        top_p=request.top_p,
        stop=stop,
        **extra_kwargs,
    )

    # Store conversation in memory (background)
    if project != "default":
        background_tasks.add_task(
            _store_conversation_memory, messages, result["content"], project
        )

    response = OpenAIChatResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=result["model"],
        choices=[
            OpenAIChoice(
                index=0,
                message={"role": "assistant", "content": result["content"]},
                finish_reason="stop",
            )
        ],
        usage=OpenAIUsage(**result.get("usage", {})),
        cached=result["cached"],
        provider=result["provider"],
    )

    return response


# =============================================================================
# Endpoint: POST /v1/messages (Anthropic Messages API)
# =============================================================================


@router.post("/v1/messages", tags=["Chat"])
async def anthropic_messages(
    request: AnthropicMessageRequest,
    background_tasks: BackgroundTasks,
    x_project: Optional[str] = Header(default=None, alias="X-Project"),
):
    """
    Anthropic Messages API compatible endpoint.
    Translates to internal format and responds in Anthropic format.
    """
    project = request.project or x_project or "default"

    # Build messages list
    messages = []
    if request.system:
        messages.append({"role": "system", "content": request.system})
    messages.extend([m.model_dump(exclude_none=True) for m in request.messages])

    if request.stream:
        # Anthropic streaming uses a different event format,
        # but for gateway compatibility we use the same SSE format
        return StreamingResponse(
            _process_chat_stream(
                messages=messages,
                model=request.model,
                provider_name=request.provider,
                project=project,
                use_memory=request.use_memory,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                top_p=request.top_p,
                stop=request.stop_sequences,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    result = await _process_chat(
        messages=messages,
        model=request.model,
        provider_name=request.provider,
        project=project,
        use_memory=request.use_memory,
        use_cache=request.use_cache,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        top_p=request.top_p,
        stop=request.stop_sequences,
    )

    if project != "default":
        background_tasks.add_task(
            _store_conversation_memory, messages, result["content"], project
        )

    response = AnthropicMessageResponse(
        id=f"msg-{uuid.uuid4().hex[:12]}",
        content=[AnthropicContentBlock(type="text", text=result["content"])],
        model=result["model"],
        stop_reason="end_turn",
        usage=AnthropicUsage(
            input_tokens=result.get("usage", {}).get("prompt_tokens", 0),
            output_tokens=result.get("usage", {}).get("completion_tokens", 0),
        ),
    )

    return response


# =============================================================================
# Endpoint: POST /api/chat (Simplified Gateway format)
# =============================================================================


@router.post("/api/chat", tags=["Chat"])
async def gateway_chat(
    request: GatewayChatRequest,
    background_tasks: BackgroundTasks,
):
    """
    Simplified gateway chat endpoint.
    Accepts a simple message + project and returns the response.
    """
    messages = [{"role": "user", "content": request.message}]

    result = await _process_chat(
        messages=messages,
        provider_name=request.provider,
        model=request.model,
        project=request.project,
        use_memory=request.use_memory,
        use_cache=request.use_cache,
    )

    if request.project != "default":
        background_tasks.add_task(
            _store_conversation_memory, messages, result["content"], request.project
        )

    return GatewayChatResponse(
        response=result["content"],
        provider=result["provider"],
        cached=result["cached"],
        project=request.project,
        usage=result.get("usage"),
    )


# =============================================================================
# Endpoint: POST /response (Alias)
# =============================================================================


@router.post("/response", tags=["Chat"])
async def response_alias(
    request: OpenAIChatRequest,
    background_tasks: BackgroundTasks,
    x_project: Optional[str] = Header(default=None, alias="X-Project"),
):
    """Alias for /v1/chat/completions — some agents use /response."""
    return await openai_chat_completions(request, background_tasks, x_project)


# =============================================================================
# Endpoint: GET /v1/models (Agent model listing)
# =============================================================================


@router.get("/v1/models", tags=["Chat"])
async def list_models():
    """
    Return available models — required by some agents for initialization.
    """
    settings = get_settings()
    from app.providers import list_providers

    models = []
    for p in list_providers():
        provider = get_provider(p)
        models.append({
            "id": provider.default_model,
            "object": "model",
            "created": int(time.time()),
            "owned_by": p,
        })

    return {
        "object": "list",
        "data": models,
    }


# =============================================================================
# Helper: Store conversation in memory
# =============================================================================


async def _store_conversation_memory(
    messages: list[dict],
    response: str,
    project: str,
):
    """Store conversation exchange in project memory (runs in background)."""
    try:
        # Only store if the conversation is substantial
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break

        if len(last_user_msg) < 20 or len(response) < 50:
            return

        # Store a condensed version
        text = f"Q: {last_user_msg[:500]}\nA: {response[:1000]}"
        await store_memory(
            text=text,
            project=project,
            memory_type="conversation",
        )
    except Exception as e:
        logger.error(f"Failed to store conversation memory: {e}")

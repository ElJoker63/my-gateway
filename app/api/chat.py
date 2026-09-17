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

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.models.requests import (
    AnthropicMessageRequest,
    GatewayChatRequest,
    OpenAIChatRequest,
)
from app.models.responses import (
    AnthropicContentBlock,
    AnthropicMessageResponse,
    AnthropicUsage,
    GatewayChatResponse,
    OpenAIChatResponse,
    OpenAIChoice,
    OpenAIStreamChoice,
    OpenAIStreamChunk,
    OpenAIStreamDelta,
    OpenAIUsage,
)
from app.providers import get_provider
from app.services.cache import get_cached_response, set_cached_response
from app.services.circuit_breaker import circuit_breaker
from app.services.combos import combo_store
from app.services.context import build_context
from app.services.key_manager import key_manager
from app.services.memory import store_memory
from app.services.metrics import metrics
from app.services.racing import execute_combo

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

    Client-facing errors use generic messages; upstream details go to the logs
    (they may echo sensitive request data or provider internals).
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
                logger.error(f"LLM call failed (HTTP {status}) for provider '{provider.name}': {e}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Upstream provider '{provider.name}' returned an error",
                ) from e

            logger.warning(
                f"Key {current_key.display} got {status} ({error_type}), "
                f"attempting fallback (attempt {attempt + 1}/{max_retries})"
            )
            await key_manager.report_error(provider.name, current_key.key_id, error_type)

            # Try to get another key
            try:
                current_key = await key_manager.acquire_key(provider.name)
            except (TimeoutError, RuntimeError) as e:
                raise HTTPException(
                    status_code=429,
                    detail="All API keys for this provider are exhausted — try again later",
                ) from e

        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"LLM call failed for provider '{provider.name}'")
            raise HTTPException(
                status_code=502,
                detail=f"Upstream provider '{provider.name}' failed",
            ) from e

    # All retries exhausted
    logger.error(f"LLM call failed after {max_retries} attempts: {last_error}")
    raise HTTPException(
        status_code=502,
        detail=f"Upstream provider '{provider.name}' failed after retries",
    )


async def _call_via_combo(
    combo,
    enriched_messages: list[dict],
    temperature: float | None,
    max_tokens: int | None,
    top_p: float | None,
    stop: list[str] | None,
    **kwargs,
) -> dict:
    """
    Walk a combo's targets honoring its strategy; the first successful call wins.
    Circuit breaker state filters out known-unhealthy targets before trying.
    """
    async def _attempt(target) -> dict:
        if not await circuit_breaker.is_available(target.provider, target.model):
            raise RuntimeError(f"Target {target.provider} circuit-open")

        try:
            provider = get_provider(target.provider)
            model_for_target = target.model or provider.default_model

            key_info = await key_manager.acquire_key(target.provider)
            result = await provider.chat(
                messages=enriched_messages,
                model=model_for_target,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                stop=stop,
                api_key=key_info.key,
                **kwargs,
            )
            await circuit_breaker.record_success(target.provider, target.model)
            return {
                "content": result["content"],
                "model": result["model"],
                "usage": result.get("usage", {}),
                "provider": target.provider,
            }
        except Exception:
            await circuit_breaker.record_failure(target.provider, target.model)
            raise

    outcome = await execute_combo(combo, _attempt)
    if not outcome.ok:
        raise HTTPException(
            status_code=502,
            detail=f"Combo '{combo.name}' failed after {outcome.attempts} attempt(s): {outcome.error}",
        )
    return outcome.result


async def _process_chat(
    messages: list[dict],
    model: str | None = None,
    provider_name: str | None = None,
    project: str = "default",
    use_memory: bool = True,
    use_cache: bool = True,
    stream: bool = False,
    temperature: float | None = None,
    max_tokens: int | None = None,
    top_p: float | None = None,
    stop: list[str] | None = None,
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

    # Cascade for model resolution: explicit model > combo alias > provider default
    combo = None
    if model:
        combo = await combo_store.get(model)
        if combo and not combo.targets:
            combo = None  # empty combo → treat as unknown

    if combo:
        # Combo routing handles key acquisition and fallback per target
        label = f"combo:{combo.name}"
        model_name = label
    else:
        model_name = model or provider.default_model

    cache_params = {
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "stop": stop,
    }

    # --- Step 1: Check cache ---
    if use_cache and not stream:
        cached = await get_cached_response(messages, model_name, project, params=cache_params)
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

    started_at = time.monotonic()

    if combo is not None:
        result = await _call_via_combo(
            combo=combo,
            enriched_messages=enriched_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stop=stop,
            stream=False,
            **kwargs,
        )
        result.setdefault("usage", {})
    else:
        # --- Step 3: Acquire key (handles rate limiting + rotation) ---
        try:
            key_info = await key_manager.acquire_key(provider.name)
        except TimeoutError as e:
            raise HTTPException(status_code=429, detail="API keys exhausted — try again later") from e
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail="No API keys available for this provider") from e

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

    # Metrics for this request
    elapsed_ms = (time.monotonic() - started_at) * 1000
    metrics.record(
        provider=result.get("provider", provider.name),
        model=result.get("model", model_name),
        latency_ms=elapsed_ms,
        ok=True,
        tokens=(result.get("usage") or {}).get("total_tokens", 0),
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
            params=cache_params,
        )

    return {
        "content": result["content"],
        "model": result["model"],
        "usage": result.get("usage", {}),
        "provider": result.get("provider", provider.name),
        "cached": False,
    }


async def _process_chat_stream(
    messages: list[dict],
    model: str | None = None,
    provider_name: str | None = None,
    project: str = "default",
    use_memory: bool = True,
    temperature: float | None = None,
    max_tokens: int | None = None,
    top_p: float | None = None,
    stop: list[str] | None = None,
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
        logger.warning(f"Stream rejected — could not acquire key: {e}")
        error_data = json.dumps({"error": {"message": "No API keys available for this provider", "type": "rate_limit_error"}})
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

    except Exception:
        logger.exception(f"Stream error for provider '{provider.name}'")
        error_data = json.dumps({"error": {"message": "Upstream provider stream failed", "type": "stream_error"}})
        yield f"data: {error_data}\n\n"


# =============================================================================
# Endpoint: POST /v1/chat/completions (OpenAI-compatible)
# =============================================================================


@router.post("/v1/chat/completions", tags=["Chat"])
async def openai_chat_completions(
    request: OpenAIChatRequest,
    background_tasks: BackgroundTasks,
    x_project: str | None = Header(default=None, alias="X-Project"),
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

    # Forward every sampling/generation param the provider understands, not just
    # the tool-related ones (frequency_penalty, presence_penalty, n, user were
    # previously validated and then silently dropped).
    extra_kwargs = {
        k: v
        for k, v in request_extra.items()
        if k in {
            "tools", "tool_choice", "response_format", "stream_options",
            "frequency_penalty", "presence_penalty", "n", "user",
            "logit_bias", "seed", "parallel_tool_calls",
        }
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
    x_project: str | None = Header(default=None, alias="X-Project"),
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
    x_project: str | None = Header(default=None, alias="X-Project"),
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
    Uses the provider metadata registered at startup (capabilities included).
    """
    from app.providers import list_providers
    from app.services.model_sync import get_provider_metadata

    models = []
    seen = set()
    for p in list_providers():
        provider = get_provider(p)
        meta = get_provider_metadata(p)
        model_id = getattr(provider, "default_model", "") or meta.get("default_model", "")
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        models.append({
            "id": model_id,
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
    """Store conversation exchange in project memory (runs in background).

    Multimodal user messages (content as a list of blocks) are normalized to
    their text parts — images/audio are not stored.
    """
    try:
        from app.services.context import extract_text_content

        # Only store if the conversation is substantial
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_msg = extract_text_content(msg.get("content"))
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

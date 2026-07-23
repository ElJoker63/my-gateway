"""
Context builder service.
Automatically enriches LLM requests with relevant project memory and context.
"""

import logging
from typing import Optional

from app.config import get_settings
from app.services.memory import search_memory

logger = logging.getLogger(__name__)


async def build_context(
    messages: list[dict],
    project: str = "default",
    use_memory: bool = True,
) -> list[dict]:
    """
    Build an enriched message list by injecting relevant context from memory.

    Process:
    1. Extract search terms from the user's latest message
    2. Query Qdrant for relevant memories
    3. Build a system context message with relevant information
    4. Prepend it to the messages list

    Args:
        messages: Original conversation messages
        project: Project name for memory search
        use_memory: Whether to search memory at all

    Returns:
        Enriched messages list with context injected
    """
    if not use_memory or project == "default":
        return messages

    settings = get_settings()

    # Find the last user message
    user_message = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_message = msg.get("content", "")
            break

    if not user_message:
        return messages

    # Search for relevant memories
    try:
        memories = await search_memory(
            query=user_message,
            project=project,
            top_k=settings.memory_search_top_k,
            score_threshold=settings.memory_score_threshold,
        )
    except Exception as e:
        logger.error(f"Context search error: {e}")
        return messages

    if not memories:
        logger.debug(f"No relevant memories found for project '{project}'")
        return messages

    # Build context block
    context_parts = [
        f"[Gateway Context — Project: {project}]",
        f"The following is relevant context retrieved from the project's memory.",
        f"Use it to inform your response, but only if relevant to the user's question.",
        "",
    ]

    total_chars = 0
    # Rough token estimate: 1 token ≈ 4 characters
    max_chars = settings.max_context_tokens * 4

    for mem in memories:
        entry_text = _format_memory_entry(mem)
        entry_len = len(entry_text)

        if total_chars + entry_len > max_chars:
            context_parts.append("... (additional context truncated for token limit)")
            break

        context_parts.append(entry_text)
        total_chars += entry_len

    context_message = "\n".join(context_parts)

    logger.info(
        f"Injected context for project '{project}': "
        f"{len(memories)} memories, ~{total_chars // 4} tokens"
    )

    # Inject as a system message at the start
    enriched = list(messages)
    # Check if there's already a system message
    has_system = enriched and enriched[0].get("role") == "system"

    if has_system:
        # Append context to existing system message
        enriched[0] = {
            "role": "system",
            "content": enriched[0]["content"] + "\n\n" + context_message,
        }
    else:
        # Add new system message
        enriched.insert(0, {"role": "system", "content": context_message})

    return enriched


def _format_memory_entry(mem: dict) -> str:
    """Format a single memory entry for context injection."""
    parts = []

    mem_type = mem.get("type", "general")
    file_ref = mem.get("file", "")
    score = mem.get("score", 0)

    header = f"--- [{mem_type.upper()}]"
    if file_ref:
        header += f" ({file_ref})"
    header += f" [relevance: {score:.2f}]"
    parts.append(header)

    parts.append(mem.get("text", ""))
    parts.append("")

    return "\n".join(parts)


def extract_search_terms(text: str) -> list[str]:
    """
    Extract key terms from user message for memory search.
    Simple keyword extraction — the embedding search handles semantic matching.
    """
    # Remove common stop words and short words
    stop_words = {
        "the", "is", "at", "which", "on", "a", "an", "and", "or", "but",
        "in", "with", "to", "for", "of", "this", "that", "it", "from",
        "be", "are", "was", "were", "been", "have", "has", "had", "do",
        "does", "did", "will", "would", "could", "should", "may", "might",
        "can", "not", "no", "my", "your", "me", "you", "we", "they",
        "el", "la", "los", "las", "un", "una", "de", "del", "en", "con",
        "por", "para", "que", "es", "son", "este", "esta", "como",
    }

    words = text.lower().split()
    terms = [w.strip(".,!?;:()[]{}\"'") for w in words if len(w) > 2]
    terms = [t for t in terms if t and t not in stop_words]

    return terms

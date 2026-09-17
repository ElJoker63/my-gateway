"""
Background tasks for the AI Gateway.
Handles project indexing and other long-running operations.

File scanning is CPU/IO-bound and synchronous by nature; it runs in a
worker thread via asyncio.to_thread so the event loop stays responsive.
Embedding + Qdrant storage remain async.
"""

import asyncio
import fnmatch
import logging
import os
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.services.memory import store_memories_batch

logger = logging.getLogger(__name__)

# File extensions considered as text/code files
TEXT_EXTENSIONS = {
    # Programming
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".kt", ".go", ".rs",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift", ".scala",
    ".dart", ".lua", ".r", ".m", ".mm", ".pl", ".pm",
    # Web
    ".html", ".htm", ".css", ".scss", ".sass", ".less", ".vue", ".svelte",
    # Data / Config
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env.example",
    ".xml", ".csv", ".sql", ".graphql",
    # Documentation
    ".md", ".rst", ".txt", ".adoc",
    # Shell / DevOps
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
    ".dockerfile", ".dockerignore", ".gitignore",
    # Specific files
    ".makefile", ".cmake",
}

# Files to always include regardless of extension
INCLUDE_FILENAMES = {
    "Dockerfile", "Makefile", "CMakeLists.txt", "Pipfile",
    "Gemfile", "Cargo.toml", "go.mod", "go.sum",
    "package.json", "tsconfig.json", "requirements.txt",
    "setup.py", "setup.cfg", "pyproject.toml",
    "docker-compose.yml", "docker-compose.yaml",
    ".env.example",
}


def _should_ignore(path: str, ignore_patterns: list[str]) -> bool:
    """Check if a path matches any ignore pattern."""
    name = os.path.basename(path)
    for pattern in ignore_patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
        if fnmatch.fnmatch(path, pattern):
            return True
        # Check if any path component matches
        for part in Path(path).parts:
            if fnmatch.fnmatch(part, pattern):
                return True
    return False


def _is_text_file(filepath: str) -> bool:
    """Check if a file is a text/code file based on extension."""
    name = os.path.basename(filepath)
    if name in INCLUDE_FILENAMES:
        return True

    ext = os.path.splitext(filepath)[1].lower()
    return ext in TEXT_EXTENSIONS


def _detect_file_type(filepath: str) -> str:
    """Detect the type of file for memory categorization."""
    ext = os.path.splitext(filepath)[1].lower()
    name = os.path.basename(filepath).lower()
    parts = {p.lower() for p in Path(filepath).parts}

    if name in {"readme.md", "readme.txt", "readme.rst"}:
        return "documentation"
    if name in {"architecture.md", "design.md", "adr"}:
        return "architecture"
    if name in {"dockerfile", "docker-compose.yml", "docker-compose.yaml"}:
        return "infrastructure"
    if name in {"package.json", "requirements.txt", "pyproject.toml", "cargo.toml", "go.mod"}:
        return "dependencies"
    if name.startswith("test_") or name.endswith("_test.py") or "tests" in parts:
        return "test"
    if ext in {".md", ".rst", ".txt", ".adoc"}:
        return "documentation"
    if ext in {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}:
        return "config"
    if ext == ".sql":
        return "database"
    if ext in {".html", ".htm", ".css", ".scss"}:
        return "frontend"
    return "code"


def _chunk_text(text: str, max_chunk_size: int = 1500, overlap: int = 200) -> list[str]:
    """
    Split text into overlapping chunks for better embedding coverage.
    Uses line-based splitting to preserve code structure.
    """
    lines = text.split("\n")
    chunks = []
    current_chunk = []
    current_size = 0

    for line in lines:
        line_len = len(line) + 1  # +1 for newline
        if current_size + line_len > max_chunk_size and current_chunk:
            chunks.append("\n".join(current_chunk))
            # Keep overlap lines
            overlap_lines = []
            overlap_size = 0
            for prev_line in reversed(current_chunk):
                if overlap_size + len(prev_line) + 1 > overlap:
                    break
                overlap_lines.insert(0, prev_line)
                overlap_size += len(prev_line) + 1
            current_chunk = overlap_lines
            current_size = overlap_size

        current_chunk.append(line)
        current_size += line_len

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


def _scan_project_files(
    path: str,
    file_patterns: Optional[list[str]],
    ignore_patterns: list[str],
    max_file_size: int,
) -> tuple[list[dict], int, int, int]:
    """
    Walk a project directory and prepare memory entries (blocking work).

    Returns:
        (entries, files_scanned, files_skipped, errors)
    """
    entries: list[dict] = []
    files_scanned = 0
    files_skipped = 0
    errors = 0

    for root, dirs, files in os.walk(path):
        # Filter out ignored directories (modify dirs in-place)
        dirs[:] = [
            d for d in dirs
            if not _should_ignore(os.path.join(root, d), ignore_patterns)
        ]

        for filename in files:
            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, path)

            if _should_ignore(filepath, ignore_patterns):
                files_skipped += 1
                continue

            if file_patterns:
                if not any(fnmatch.fnmatch(filename, p) for p in file_patterns):
                    files_skipped += 1
                    continue

            if not _is_text_file(filepath):
                files_skipped += 1
                continue

            try:
                size = os.path.getsize(filepath)
                if size > max_file_size:
                    logger.debug(f"Skipping large file: {rel_path} ({size // 1024}KB)")
                    files_skipped += 1
                    continue
            except OSError:
                continue

            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                if not content.strip():
                    continue

                file_type = _detect_file_type(filepath)
                chunks = _chunk_text(content)

                for i, chunk in enumerate(chunks):
                    header = f"File: {rel_path}"
                    if len(chunks) > 1:
                        header += f" (chunk {i + 1}/{len(chunks)})"

                    entries.append({
                        "text": f"{header}\n\n{chunk}",
                        "file": rel_path,
                        "type": file_type,
                        "metadata": {
                            "chunk_index": i,
                            "total_chunks": len(chunks),
                            "file_size": size,
                        },
                    })

                files_scanned += 1

            except Exception as e:
                logger.warning(f"Error reading {rel_path}: {e}")
                errors += 1
                continue

    return entries, files_scanned, files_skipped, errors


async def index_project_task(
    path: str,
    project_name: str,
    file_patterns: Optional[list[str]] = None,
):
    """
    Background task to index a project directory.

    Scanning runs in a worker thread (blocking FS work); embedding and
    Qdrant storage run async in bounded batches to cap memory usage.
    """
    settings = get_settings()
    ignore_patterns = settings.index_ignore_patterns
    max_file_size = settings.max_file_size_kb * 1024

    logger.info(f"Starting project indexing: '{project_name}' at {path}")

    entries, files_scanned, files_skipped, errors = await asyncio.to_thread(
        _scan_project_files, path, file_patterns, ignore_patterns, max_file_size
    )

    # Store in bounded batches so very large repos don't exhaust memory
    total_stored = 0
    batch_size = 500
    for i in range(0, len(entries), batch_size):
        batch = entries[i : i + batch_size]
        total_stored += await store_memories_batch(batch, project_name)
        # Release the slices as soon as they are stored
        entries[i : i + batch_size] = []

    if total_stored:
        logger.info(
            f"Project '{project_name}' indexed: "
            f"{files_scanned} files, {total_stored} memories, "
            f"{files_skipped} skipped, {errors} errors"
        )
    else:
        logger.warning(f"No indexable files found in '{path}'")

    # Persist indexing stats so the projects API reports real numbers
    try:
        import time
        from app.database.redis import get_redis
        redis = await get_redis()
        await redis.hset(
            f"gw:project:stats:{project_name}",
            mapping={
                "files_indexed": files_scanned,
                "memories_created": total_stored,
                "files_skipped": files_skipped,
                "errors": errors,
                "last_indexed_at": str(int(time.time())),
            },
        )
    except Exception as e:
        logger.warning(f"Failed to persist indexing stats for '{project_name}': {e}")

    return {
        "project": project_name,
        "files_scanned": files_scanned,
        "memories_created": total_stored,
        "files_skipped": files_skipped,
        "errors": errors,
    }

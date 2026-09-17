"""
Centralized configuration for My Gateway AI.
All settings loaded from environment variables with sensible defaults.
"""

import json
from typing import Annotated, Optional

from pydantic_settings import BaseSettings, NoDecode
from pydantic import Field, field_validator
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- Gateway ---
    gateway_api_key: str = Field(default="", description="API key for gateway authentication (empty = auth disabled, NOT for production)")
    log_level: str = Field(default="INFO", description="Logging level")
    gateway_host: str = Field(default="0.0.0.0", description="Host to bind the gateway")
    gateway_port: int = Field(default=8000, description="Port to bind the gateway")
    cors_allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:8080,http://127.0.0.1:3000",
        description="Comma-separated list of allowed CORS origins",
    )

    @property
    def auth_enabled(self) -> bool:
        """Authentication is enabled only when a real gateway key is configured."""
        return bool(self.gateway_api_key) and self.gateway_api_key != "change-me-to-a-secure-key"

    # --- NVIDIA Provider ---
    nvidia_api_key: str = Field(default="", description="NVIDIA API key (single key, backward compat)")
    nvidia_api_keys: Annotated[list[str], NoDecode] = Field(default=[], description="Pool of NVIDIA API keys (JSON array or comma-separated)")
    nvidia_model: str = Field(default="meta/llama-3.1-70b-instruct", description="Default NVIDIA model")
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1", description="NVIDIA API base URL")
    nvidia_rpm_limit: int = Field(default=0, description="RPM limit per key for NVIDIA (0 = inherit default)")

    # --- OpenAI Provider ---
    openai_api_key: str = Field(default="", description="OpenAI API key (single key, backward compat)")
    openai_api_keys: Annotated[list[str], NoDecode] = Field(default=[], description="Pool of OpenAI API keys (JSON array or comma-separated)")
    openai_model: str = Field(default="gpt-4o", description="Default OpenAI model")
    openai_base_url: str = Field(default="https://api.openai.com/v1", description="OpenAI API base URL")
    openai_rpm_limit: int = Field(default=0, description="RPM limit per key for OpenAI (0 = inherit default)")
    openai_embedding_model: str = Field(default="text-embedding-3-small", description="Default OpenAI embedding model")

    # --- Groq Provider ---
    groq_api_key: str = Field(default="", description="Groq API key (single key, backward compat)")
    groq_api_keys: Annotated[list[str], NoDecode] = Field(default=[], description="Pool of Groq API keys (JSON array or comma-separated)")
    groq_model: str = Field(default="llama-3.3-70b-versatile", description="Default Groq model")
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1", description="Groq API base URL")
    groq_rpm_limit: int = Field(default=0, description="RPM limit per key for Groq (0 = inherit default)")

    # --- Ollama Cloud / Remote Provider ---
    ollama_api_key: str = Field(default="", description="Ollama Cloud API key (single key)")
    ollama_api_keys: Annotated[list[str], NoDecode] = Field(default=[], description="Pool of Ollama Cloud API keys (JSON array or comma-separated)")
    ollama_model: str = Field(default="llama3.1", description="Default Ollama Cloud model")
    ollama_base_url: str = Field(default="https://ollama.com/v1", description="Ollama Cloud / Remote API base URL")
    ollama_rpm_limit: int = Field(default=0, description="RPM limit per key for Ollama Cloud (0 = inherit default)")

    # --- Key Management ---
    key_selection_strategy: str = Field(
        default="least_used",
        description="Key selection strategy: 'least_used' or 'round_robin'"
    )
    key_rpm_limit: int = Field(
        default=0,
        description="RPM limit per individual key (0 = use max_requests_per_minute)"
    )
    key_error_cooldown: int = Field(
        default=60,
        description="Seconds to cool down a key after an error (rate limit or auth failure)"
    )

    # --- Default Provider ---
    default_provider: str = Field(default="nvidia", description="Default LLM provider (nvidia, openai)")

    # --- Rate Limiting ---
    max_requests_per_minute: int = Field(default=35, description="Max requests per minute to LLM provider")
    rate_limit_wait_timeout: int = Field(default=60, description="Max seconds to wait when rate limited")

    # --- Redis ---
    redis_host: str = Field(default="redis", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_password: str = Field(default="", description="Redis password (optional)")
    cache_ttl: int = Field(default=86400, description="Cache TTL in seconds (24h default)")

    # --- Qdrant ---
    qdrant_host: str = Field(default="qdrant", description="Qdrant host")
    qdrant_port: int = Field(default=6333, description="Qdrant gRPC port")
    qdrant_api_key: str = Field(default="", description="Qdrant API key (optional)")

    # --- Embedding ---
    embedding_model: str = Field(
        default="local",
        description="Embedding model: 'local' for sentence-transformers or 'nvidia' for NVIDIA API"
    )
    local_embedding_model_name: str = Field(
        default="all-MiniLM-L6-v2",
        description="HuggingFace model name for local embeddings"
    )
    embedding_dimension: int = Field(default=384, description="Embedding vector dimension")

    # --- Context ---
    max_context_tokens: int = Field(default=4000, description="Max tokens of project memory injected into the system prompt (NOT the model's context window; GLM on NVIDIA exposes 128K)")
    memory_search_top_k: int = Field(default=10, description="Number of memory results to retrieve")
    memory_score_threshold: float = Field(default=0.5, description="Minimum relevance score for memory results")

    # --- Project Indexing ---
    index_ignore_patterns: list[str] = Field(
        default=[
            ".git", "node_modules", "build", "dist", "venv",
            "__pycache__", ".env", ".venv", "*.pyc", "*.pyo",
            ".DS_Store", "*.egg-info", ".tox", ".mypy_cache",
        ],
        description="Patterns to ignore during project indexing"
    )
    max_file_size_kb: int = Field(default=500, description="Max file size in KB to index")
    allowed_index_roots: Annotated[list[str], NoDecode] = Field(
        default=[],
        description=(
            "Root directories the indexing API is allowed to read (JSON array or comma-separated). "
            "Any path outside these roots is rejected. Empty = indexing endpoint disabled."
        ),
    )

    # --- Request Limits ---
    max_request_size_mb: int = Field(default=10, description="Max request body size in MB")

    @field_validator(
        "nvidia_api_keys", "openai_api_keys", "groq_api_keys", "ollama_api_keys",
        "index_ignore_patterns", "allowed_index_roots",
        mode="before",
    )
    @classmethod
    def parse_api_keys(cls, v):
        """Parse API keys from JSON string or list."""
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [k for k in parsed if k]  # filter empty strings
                return [str(parsed)]
            except json.JSONDecodeError:
                # Treat as comma-separated
                return [k.strip() for k in v.split(",") if k.strip()]
        if isinstance(v, list):
            return [k for k in v if k]
        return []

    def get_provider_keys(self, provider: str) -> list[str]:
        """
        Get the merged key list for a provider.

        Resolution order:
        1. Typed fields on Settings ({p}_api_keys / {p}_api_key) — where declared.
        2. Direct env var read ({PROVIDER}_API_KEYS / {PROVIDER}_API_KEY) — so all
           24 providers work even without a dedicated typed field.
        """
        key = provider.lower()

        keys = getattr(self, f"{key}_api_keys", None)
        if keys:
            return list(keys)

        single = getattr(self, f"{key}_api_key", "")
        if single:
            return [single]

        # Fallback for providers without typed Settings fields
        import os
        env_keys = os.environ.get(f"{key.upper()}_API_KEYS")
        if env_keys:
            parsed = self.parse_api_keys(env_keys)
            if parsed:
                return parsed
        env_key = os.environ.get(f"{key.upper()}_API_KEY", "")
        return [env_key] if env_key else []

    def get_provider_rpm(self, provider: str) -> int:
        """
        Get the RPM limit per key for a specific provider.
        Precedence:
        1. {provider}_rpm_limit typed field or {PROVIDER}_RPM_LIMIT env var
        2. key_rpm_limit
        3. max_requests_per_minute
        """
        key = provider.lower()
        provider_limit = getattr(self, f"{key}_rpm_limit", 0)
        if provider_limit and provider_limit > 0:
            return provider_limit

        # Fallback: env var for providers without a typed field
        import os
        env_rpm = os.environ.get(f"{key.upper()}_RPM_LIMIT", "")
        if env_rpm:
            try:
                value = int(env_rpm)
                if value > 0:
                    return value
            except ValueError:
                pass

        if self.key_rpm_limit > 0:
            return self.key_rpm_limit
        return self.max_requests_per_minute

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — loaded once per process."""
    return Settings()

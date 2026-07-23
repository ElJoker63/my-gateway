"""
Centralized configuration for the AI Agent Gateway.
All settings loaded from environment variables with sensible defaults.
"""

import json
from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- Gateway ---
    gateway_api_key: str = Field(default="change-me-to-a-secure-key", description="API key for gateway authentication")
    log_level: str = Field(default="INFO", description="Logging level")
    gateway_host: str = Field(default="0.0.0.0", description="Host to bind the gateway")
    gateway_port: int = Field(default=8000, description="Port to bind the gateway")

    # --- NVIDIA Provider ---
    nvidia_api_key: str = Field(default="", description="NVIDIA API key (single key, backward compat)")
    nvidia_api_keys: list[str] = Field(default=[], description="Pool of NVIDIA API keys (JSON array)")
    nvidia_model: str = Field(default="meta/llama-3.1-70b-instruct", description="Default NVIDIA model")
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1", description="NVIDIA API base URL")
    nvidia_rpm_limit: int = Field(default=0, description="RPM limit per key for NVIDIA (0 = inherit default)")

    # --- OpenAI Provider ---
    openai_api_key: str = Field(default="", description="OpenAI API key (single key, backward compat)")
    openai_api_keys: list[str] = Field(default=[], description="Pool of OpenAI API keys (JSON array)")
    openai_model: str = Field(default="gpt-4o", description="Default OpenAI model")
    openai_base_url: str = Field(default="https://api.openai.com/v1", description="OpenAI API base URL")
    openai_rpm_limit: int = Field(default=0, description="RPM limit per key for OpenAI (0 = inherit default)")

    # --- Groq Provider ---
    groq_api_key: str = Field(default="", description="Groq API key (single key, backward compat)")
    groq_api_keys: list[str] = Field(default=[], description="Pool of Groq API keys (JSON array)")
    groq_model: str = Field(default="llama-3.3-70b-versatile", description="Default Groq model")
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1", description="Groq API base URL")
    groq_rpm_limit: int = Field(default=0, description="RPM limit per key for Groq (0 = inherit default)")

    # --- Ollama Cloud / Remote Provider ---
    ollama_api_key: str = Field(default="", description="Ollama Cloud API key (single key)")
    ollama_api_keys: list[str] = Field(default=[], description="Pool of Ollama Cloud API keys (JSON array)")
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
    max_context_tokens: int = Field(default=4000, description="Max tokens for injected context")
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

    # --- Request Limits ---
    max_request_size_mb: int = Field(default=10, description="Max request body size in MB")

    @field_validator("nvidia_api_keys", "openai_api_keys", "groq_api_keys", "ollama_api_keys", mode="before")
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
        Uses *_api_keys pool if available, falls back to singular *_api_key.
        """
        keys_attr = f"{provider}_api_keys"
        key_attr = f"{provider}_api_key"

        keys = getattr(self, keys_attr, [])
        if keys:
            return keys

        single_key = getattr(self, key_attr, "")
        if single_key:
            return [single_key]

        return []

    def get_provider_rpm(self, provider: str) -> int:
        """
        Get the RPM limit per key for a specific provider.
        Precedence:
        1. {provider}_rpm_limit (e.g. nvidia_rpm_limit)
        2. key_rpm_limit
        3. max_requests_per_minute
        """
        provider_limit = getattr(self, f"{provider.lower()}_rpm_limit", 0)
        if provider_limit > 0:
            return provider_limit
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

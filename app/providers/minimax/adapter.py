"""MiniMax LLM Provider Adapter (generated via factory)."""
import os
from pathlib import Path

from app.providers.factory import build_provider_class
from .config import MINIMAX_BASE_URL, MINIMAX_DEFAULT_MODEL

MiniMaxProvider = build_provider_class(
    name="minimax",
    base_url=MINIMAX_BASE_URL,
    default_model=MINIMAX_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="MiniMaxProvider",
)
